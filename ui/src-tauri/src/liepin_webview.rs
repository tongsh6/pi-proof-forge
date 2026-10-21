//! App 自有原生会话、只读观测及固定审批快照的 PDF 上传和发送；仅限本地主窗口调用。
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::{Mutex, Arc};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

const LABEL: &str = "liepin-native-session";
const BRIDGE_SCHEME: &str = "piproofforge-observe";

#[derive(Default)]
pub struct NativeLiepinSession {
    operation_busy: Arc<AtomicBool>,
    daily_cycle: Mutex<Option<String>>,
    observation: Mutex<Value>,
    pending_nonce: Mutex<String>,
    pdf_nonce: Mutex<String>,
    pdf_observation: Mutex<Option<Value>>,
    chat_navigation_allowed: Mutex<bool>,
    chat_popup_url: Mutex<Option<String>>,
}

pub fn require_main_window(label: &str) -> Result<(), String> {
    if label == "main" { Ok(()) } else { Err("LOCAL_WINDOW_REQUIRED".into()) }
}

fn local_app_origin(url: &Url) -> bool {
    (url.scheme() == "tauri" && url.host_str() == Some("localhost")) ||
    (matches!(url.scheme(), "http" | "https") && url.host_str() == Some("tauri.localhost")) ||
    (cfg!(debug_assertions) && url.scheme() == "http" && matches!(url.host_str(), Some("localhost" | "127.0.0.1")) && url.port() == Some(1420))
}

pub fn require_local_command(window: &WebviewWindow) -> Result<(), String> {
    require_main_window(window.label())?;
    if !local_app_origin(&window.url().map_err(|_| "LOCAL_WINDOW_REQUIRED")?) {
        return Err("LOCAL_WINDOW_REQUIRED".into());
    }
    Ok(())
}

fn allowed_navigation(url: &Url) -> bool {
    url.scheme() == "https" && url.username().is_empty() && url.password().is_none()
        && url.port_or_known_default() == Some(443)
        && matches!(url.host_str(), Some("www.liepin.com" | "c.liepin.com" | "passport.liepin.com" | "safe.liepin.com"))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Observation {
    url: String,
    authenticated: bool,
    login_form: bool,
    challenge: bool,
    #[serde(default)]
    attachment_view: Option<AttachmentView>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AttachmentView {
    entry_count: usize,
    inputs: Vec<FileInputView>,
    hints: Vec<String>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct FileInputView { accept: String, multiple: bool, disabled: bool }

#[derive(Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
struct UploadObservation { status:String, filename:String, hints:Vec<String>, responses:Vec<UploadResponse> }
#[derive(Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
struct UploadResponse { method:String, url:String, http_status:u16, payload:String }

fn normalize_upload_observation(value:Value)->Result<Value,String>{
    let mut item:UploadObservation=serde_json::from_value(value).map_err(|_|"INVALID_UPLOAD_OBSERVATION")?;
    if !matches!(item.status.as_str(),"uploaded"|"unknown"|"not_submitted") || item.filename.len()>180
        || item.hints.len()>20 || item.hints.iter().any(|s|s.chars().count()>180) || item.responses.len()>8 {
        return Err("INVALID_UPLOAD_OBSERVATION".into());
    }
    for response in &mut item.responses {
        let mut url:Url=response.url.parse().map_err(|_|"INVALID_UPLOAD_OBSERVATION")?;
        if url.scheme()!="https" || !url.username().is_empty() || url.password().is_some() || response.method.len()>8 || response.payload.len()>12000 {
            return Err("INVALID_UPLOAD_OBSERVATION".into());
        }
        url.set_query(None);url.set_fragment(None);response.url=url.to_string();
    }
    serde_json::to_value(item).map_err(|_|"INVALID_UPLOAD_OBSERVATION".into())
}


fn normalize_observation(value: Value) -> Result<Value, String> {
    let item: Observation = serde_json::from_value(value).map_err(|_| "INVALID_OBSERVATION")?;
    let mut url: Url = item.url.parse().map_err(|_| "INVALID_OBSERVATION")?;
    let blank = item.url == "about:blank";
    if !blank && !allowed_navigation(&url) { return Err("INVALID_OBSERVATION".into()); }
    url.set_query(None);
    url.set_fragment(None);
    let status = if blank { "blank" } else if item.challenge || url.host_str() == Some("safe.liepin.com") {
        "security_challenge"
    } else if item.login_form { "waiting_for_login" } else if item.authenticated {
        "authenticated"
    } else { "unverified" };
    let can_return = url.host_str() == Some("c.liepin.com") && url.path() == "/resume/parse-result"
        && matches!(status, "unverified" | "authenticated");
    let mut output = json!({"status":status, "url":url.as_str(), "authenticated":status == "authenticated",
                           "can_return_to_attachments":can_return});
    if let Some(view) = item.attachment_view {
        if status != "authenticated" || view.inputs.len() > 20 || view.hints.len() > 20
            || view.inputs.iter().any(|i| i.accept.len() > 256)
            || view.hints.iter().any(|s| s.chars().count() > 180) {
            return Err("INVALID_OBSERVATION".into());
        }
        output["attachment_view"] = serde_json::to_value(view).map_err(|_| "INVALID_OBSERVATION")?;
    }
    Ok(output)
}

fn set_observation(app: &AppHandle, observation: Value) {
    if let Ok(mut current) = app.state::<NativeLiepinSession>().observation.lock() {
        *current = observation;
    }
}

async fn open_liepin_native_session_inner(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    if let Some(existing) = app.get_webview_window(LABEL) {
        existing.show().map_err(|_| "NATIVE_SESSION_OPEN_FAILED")?;
        existing.set_focus().map_err(|_| "NATIVE_SESSION_OPEN_FAILED")?;
        return Ok(json!({"status":"opened"}));
    }
    set_observation(&app, json!({"status":"opening"}));
    let observe_app = app.clone();
    let load_app = app.clone();
    let popup_app = app.clone();
    let builder = WebviewWindowBuilder::new(&app, LABEL,
        WebviewUrl::External("https://www.liepin.com/".parse().unwrap()))
        .title("PiProofForge · 猎聘会话")
        .inner_size(1200.0, 850.0)
        .on_new_window(move |url, _| {
            let state=popup_app.state::<NativeLiepinSession>();
            let allowed=state.chat_navigation_allowed.lock().map(|v|*v).unwrap_or(false);
            if allowed {
                if let Ok(mut observed)=state.chat_popup_url.lock(){*observed=Some(url.to_string());}
                if allowed_navigation(&url) && (url.path().starts_with("/im") || url.path().starts_with("/chat")) {
                    if let Some(browser)=popup_app.get_webview_window(LABEL){let _=browser.navigate(url);}
                }
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .on_navigation(move |url| {
            if url.scheme() == "piproofforge-pdf" {
                let state=observe_app.state::<NativeLiepinSession>();
                let pairs: std::collections::HashMap<_,_>=url.query_pairs().into_owned().collect();
                let expected=state.pdf_nonce.lock().map(|s|s.clone()).unwrap_or_default();
                if url.host_str()==Some("result") && !expected.is_empty() && pairs.get("nonce")==Some(&expected) {
                    if let Some(raw)=pairs.get("payload").filter(|s|s.len()<=65536) {
                        if let Ok(value)=serde_json::from_str::<Value>(raw).map_err(|_|"INVALID_UPLOAD_OBSERVATION".to_string()).and_then(normalize_upload_observation) {
                            if let Ok(mut observation)=state.pdf_observation.lock() { *observation=Some(value); }
                            if let Some(main)=observe_app.get_webview_window("main") {let _=main.show();let _=main.set_focus();}
                        }
                    }
                }
                return false;
            }
            if url.scheme() == BRIDGE_SCHEME {
                let pairs: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
                let state = observe_app.state::<NativeLiepinSession>();
                let expected = state.pending_nonce.lock().map(|n| n.clone()).unwrap_or_default();
                if url.host_str() == Some("result") && !expected.is_empty() && pairs.get("nonce") == Some(&expected) {
                    if let Some(payload) = pairs.get("payload").filter(|value| value.len() <= 8192) {
                        if let Ok(value) = serde_json::from_str(payload).map_err(|_| "INVALID_OBSERVATION".to_string()).and_then(normalize_observation) {
                            let authenticated = value["status"] == "authenticated";
                            set_observation(&observe_app, value);
                            if authenticated {
                                if let Some(main) = observe_app.get_webview_window("main") {
                                    let _ = main.unminimize();
                                    let _ = main.show();
                                    let _ = main.set_focus();
                                }
                            }
                            if let Ok(mut nonce) = state.pending_nonce.lock() { nonce.clear(); }
                        }
                    }
                }
                return false;
            }
            // 空白跳转保持原行为并报告；不通过拦截跳转规避网站检查。
            if url.as_str() == "about:blank" {
                set_observation(&observe_app, json!({"status":"blank","authenticated":false}));
                return true;
            }
            allowed_navigation(url)
        })
        .on_page_load(move |browser, payload| {
            if payload.url().as_str() == "about:blank" {
                set_observation(&load_app, json!({"status":"blank","authenticated":false}));
            } else if payload.event() == tauri::webview::PageLoadEvent::Finished && allowed_navigation(payload.url()) {
                let _ = start_observation(&load_app, &browser, 1500, false);
            }
        });
    #[cfg(target_os = "macos")]
    let builder = builder.data_store_identifier(*b"PiProofForgeLPN1");
    builder.build().map_err(|_| "NATIVE_SESSION_OPEN_FAILED")?;
    Ok(json!({"status":"opened"}))
}

fn start_observation(app: &AppHandle, browser: &WebviewWindow, delay_ms: u32, inspect_attachments: bool) -> Result<(), String> {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?.as_nanos().to_string();
    *app.state::<NativeLiepinSession>().pending_nonce.lock().map_err(|_| "NATIVE_SESSION_CHECK_FAILED")? = nonce.clone();
    let nonce_json = serde_json::to_string(&nonce).unwrap();
    let script = include_str!("liepin_native_observe.js").replace("NONCE_VALUE", &nonce_json)
        .replace("INSPECT_ATTACHMENTS", if inspect_attachments { "true" } else { "false" });
    browser.eval(format!("setTimeout(() => {{ {} }}, {});", script, delay_ms)).map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?;
    Ok(())
}

async fn check_liepin_native_session_inner(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let browser = app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let actual_url = browser.url().map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?;
    if actual_url.as_str() == "about:blank" {
        return Ok(json!({"status":"blank","authenticated":false}));
    }
    if !allowed_navigation(&actual_url) { return Err("NATIVE_SESSION_ORIGIN_INVALID".into()); }
    start_observation(&app, &browser, 0, false)?;
    let observation = wait_observation(app.clone()).await?;
    if observation["can_return_to_attachments"] == true {
        let current = browser.url().map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?;
        if current.host_str() != Some("c.liepin.com") || current.path() != "/resume/parse-result" {
            return Err("NATIVE_SESSION_PAGE_NOT_READY".into());
        }
        // 解析同步是独立表单；返回固定附件页并重新认证，不提交或补写经历。
        browser.navigate("https://c.liepin.com/resume/edit".parse().unwrap()).map_err(|_| "NATIVE_SESSION_PAGE_NOT_READY")?;
        tauri::async_runtime::spawn_blocking(|| std::thread::sleep(Duration::from_millis(3000)))
            .await.map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?;
        start_observation(&app, &browser, 0, false)?;
        return wait_observation(app).await;
    }
    Ok(observation)
}

async fn wait_observation(app: AppHandle) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        for _ in 0..60 {
            let state = app.state::<NativeLiepinSession>();
            let pending = state.pending_nonce.lock().map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?.clone();
            if pending.is_empty() {
                return state.observation.lock().map(|v| v.clone()).map_err(|_| "NATIVE_SESSION_CHECK_FAILED".to_string());
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        Err("NATIVE_SESSION_CHECK_TIMEOUT".to_string())
    }).await.map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?
}

async fn inspect_liepin_native_attachments_inner(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let result = check_liepin_native_session_inner(app.clone(), window).await?;
    if result["status"] != "authenticated" { return Err("NATIVE_SESSION_LOGIN_REQUIRED".into()); }
    let browser = app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let url = browser.url().map_err(|_| "NATIVE_SESSION_CHECK_FAILED")?;
    if url.host_str() != Some("c.liepin.com") || !matches!(url.path(), "/" | "/resume/edit") { return Err("NATIVE_SESSION_PAGE_NOT_READY".into()); }
    start_observation(&app, &browser, 0, true)?;
    wait_observation(app).await
}

async fn pdf_rpc(app: AppHandle, method: &'static str, mut params: Value) -> Result<Value,String> {
    params["meta"]=json!({"correlation_id":"native-pdf"});
    tauri::async_runtime::spawn_blocking(move || {
        let request=crate::build_rpc_request("native-pdf",method,params);
        let response=app.state::<crate::SidecarManager>().send(&app,&request)?;
        crate::parse_rpc_success_response(&response,"native-pdf",method)
    }).await.map_err(|_|"NATIVE_PDF_BACKEND_FAILED".to_string())?
}

async fn upload_liepin_native_pdf_inner(app: AppHandle, window: WebviewWindow, run_id: String, accept_account_effects: bool) -> Result<Value,String> {
    require_local_command(&window)?;
    let mut checked=check_liepin_native_session_inner(app.clone(),window.clone()).await?;
    if checked["status"]!="authenticated" {return Err("NATIVE_SESSION_LOGIN_REQUIRED".into());}
    // 会话可能停在猎聘首页；上传脚本固定要求简历附件页，已认证时只做站内导航，不提交任何表单。
    if checked["url"]!="https://c.liepin.com/resume/edit" {
        let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
        browser.navigate("https://c.liepin.com/resume/edit".parse().unwrap()).map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        checked=check_liepin_native_session_inner(app.clone(),window).await?;
    }
    if checked["status"]!="authenticated" || checked["url"]!="https://c.liepin.com/resume/edit" {return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let payload=pdf_rpc(app.clone(),"run.agent.beginPdfUpload",json!({"run_id":run_id,"accept_account_effects":accept_account_effects})).await?;
    let nonce=payload["upload_ref"].as_str().ok_or("NATIVE_PDF_BACKEND_FAILED")?.to_string();
    let observation=run_pdf_script(&app,&browser,include_str!("liepin_native_upload.js"),&payload,&nonce).await?;
    pdf_rpc(app,"run.agent.finishPdfUpload",json!({"run_id":run_id,"upload_ref":nonce,"observation":observation})).await
}

async fn run_pdf_script(app:&AppHandle,browser:&WebviewWindow,source:&str,payload:&Value,nonce:&str)->Result<Value,String>{
    *app.state::<NativeLiepinSession>().pdf_nonce.lock().map_err(|_|"NATIVE_PDF_STATE_FAILED")?=nonce.to_string();
    *app.state::<NativeLiepinSession>().pdf_observation.lock().map_err(|_|"NATIVE_PDF_STATE_FAILED")?=None;
    let script=source.replace("UPLOAD_NONCE",&json!(nonce).to_string()).replace("UPLOAD_PAYLOAD",&payload.to_string());
    let started=browser.eval(script).is_ok();
    let wait_app=app.clone();
    let observation=tauri::async_runtime::spawn_blocking(move || {
        if started {for _ in 0..440 {
            if let Ok(current)=wait_app.state::<NativeLiepinSession>().pdf_observation.lock() {if let Some(value)=current.as_ref(){return Some(value.clone());}}
            std::thread::sleep(Duration::from_millis(50));
        }}
        None
    }).await.map_err(|_|"NATIVE_PDF_CHECK_FAILED")?.unwrap_or(json!({"status":"unknown","filename":payload["filename"],"hints":["上传结果超时，禁止自动重传"],"responses":[]}));
    if let Ok(mut value)=app.state::<NativeLiepinSession>().pdf_nonce.lock(){value.clear();}
    if payload.get("write_deadline_ms").is_some() && (payload.get("pdf_bytes").is_some() || payload["action"]=="send") {
        // 页面守卫在采集结束后保持关闭；重载销毁旧文档及其延迟任务，再释放执行锁。
        // 已发出的请求可能已有业务效果，仍只能由原回执确认，不能自动重试。
        let current=browser.url().map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        if !allowed_navigation(&current){return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
        browser.navigate(current).map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    }
    Ok(observation)
}

async fn diagnose_liepin_native_attachments_inner(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let mut checked=check_liepin_native_session_inner(app.clone(),window.clone()).await?;
    if checked["status"]!="authenticated" {return Err("NATIVE_SESSION_LOGIN_REQUIRED".into());}
    if checked["url"]!="https://c.liepin.com/resume/edit" {
        let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
        browser.navigate("https://c.liepin.com/resume/edit".parse().unwrap()).map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        checked=check_liepin_native_session_inner(app.clone(),window.clone()).await?;
    }
    if checked["status"]!="authenticated" || checked["url"]!="https://c.liepin.com/resume/edit" {return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let payload=json!({"diagnostic":true,"filename":""});
    run_pdf_script(&app,&browser,include_str!("liepin_native_attachment_diagnostics.js"),&payload,&nonce).await
}

async fn cleanup_liepin_native_attachments_inner(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let mut checked=check_liepin_native_session_inner(app.clone(),window.clone()).await?;
    if checked["status"]!="authenticated" {return Err("NATIVE_SESSION_LOGIN_REQUIRED".into());}
    if checked["url"]!="https://c.liepin.com/resume/edit" {
        let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
        browser.navigate("https://c.liepin.com/resume/edit".parse().unwrap()).map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        checked=check_liepin_native_session_inner(app.clone(),window.clone()).await?;
    }
    if checked["status"]!="authenticated" || checked["url"]!="https://c.liepin.com/resume/edit" {return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let payload=json!({"cleanup":true,"filename":""});
    run_pdf_script(&app,&browser,include_str!("liepin_native_cleanup_attachments.js"),&payload,&nonce).await
}

async fn inspect_uploaded_liepin_pdf_inner(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let packet=pdf_rpc(app.clone(),"run.agent.inspectPdfPacket",json!({"run_id":run_id})).await?;
    let current=browser.url().map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    if !allowed_navigation(&current){return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
    if current.host_str()!=Some("c.liepin.com") || current.path()!="/resume/edit" {
        // 上传后平台可能进入解析确认页；只导航回附件页，不提交解析的经历字段。
        browser.navigate("https://c.liepin.com/resume/edit".parse().unwrap()).map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
        tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    }
    let checked=check_liepin_native_session_inner(app.clone(),window).await?;
    if checked["status"]!="authenticated" || checked["url"]!="https://c.liepin.com/resume/edit" {return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let observation=run_pdf_script(&app,&browser,include_str!("liepin_native_pdf_inspect.js"),&packet,&nonce).await?;
    pdf_rpc(app,"run.agent.recordPdfInspection",json!({"run_id":run_id,"observation":observation})).await
}

async fn recheck_liepin_native_pdf_removal_inner(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    inspect_uploaded_liepin_pdf_inner(app.clone(),window,run_id.clone()).await?;
    pdf_rpc(app,"run.agent.recheckPdfRemoval",json!({"run_id":run_id})).await
}

async fn remove_liepin_native_pdf_attachment_inner(app:AppHandle,window:WebviewWindow,run_id:String,confirmed:bool) -> Result<Value,String> {
    require_local_command(&window)?;
    if !confirmed{return Err("ATTACHMENT_REMOVAL_CONFIRMATION_REQUIRED".into());}
    // 复用当前平台卡片与原文件字节的只读检查，历史发送绑定不会被覆盖。
    inspect_uploaded_liepin_pdf_inner(app.clone(),window,run_id.clone()).await?;
    let packet=pdf_rpc(app.clone(),"run.agent.beginPdfRemoval",json!({"run_id":run_id,"confirmed":confirmed})).await?;
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let nonce=packet["removal_ref"].as_str().ok_or("NATIVE_PDF_STATE_FAILED")?.to_string();
    let observation=run_pdf_script(&app,&browser,include_str!("liepin_native_pdf_remove.js"),&packet,&nonce).await?;
    pdf_rpc(app,"run.agent.finishPdfRemoval",json!({"run_id":run_id,"removal_ref":nonce,"observation":observation})).await
}

async fn inspect_liepin_pdf_target_inner(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let packet=pdf_rpc(app.clone(),"run.agent.pdfTargetPacket",json!({"run_id":run_id})).await?;
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let url:Url=packet["job_url"].as_str().ok_or("INVALID_PDF_TARGET")?.parse().map_err(|_|"INVALID_PDF_TARGET")?;
    if !allowed_navigation(&url){return Err("INVALID_PDF_TARGET".into());}
    browser.navigate(url).map_err(|_|"NATIVE_PDF_TARGET_OPEN_FAILED")?;
    tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3500))).await.map_err(|_|"NATIVE_PDF_TARGET_OPEN_FAILED")?;
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let observation=run_pdf_script(&app,&browser,include_str!("liepin_native_pdf_target.js"),&packet,&nonce).await?;
    pdf_rpc(app,"run.agent.recordPdfTarget",json!({"run_id":run_id,"observation":observation})).await
}

async fn start_liepin_pdf_communication_inner(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    inspect_uploaded_liepin_pdf_inner(app.clone(),window.clone(),run_id.clone()).await?;
    inspect_liepin_pdf_target_inner(app.clone(),window,run_id.clone()).await?;
    let packet=pdf_rpc(app.clone(),"run.agent.beginPdfDelivery",json!({"run_id":run_id})).await?;
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    *app.state::<NativeLiepinSession>().chat_navigation_allowed.lock().map_err(|_|"NATIVE_PDF_STATE_FAILED")?=true;
    *app.state::<NativeLiepinSession>().chat_popup_url.lock().map_err(|_|"NATIVE_PDF_STATE_FAILED")?=None;
    let script=include_str!("liepin_native_pdf_chat_open.js").replace("CHAT_PAYLOAD",&packet.to_string());
    let _=browser.eval(script);
    tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_PDF_STATE_FAILED")?;
    *app.state::<NativeLiepinSession>().chat_navigation_allowed.lock().map_err(|_|"NATIVE_PDF_STATE_FAILED")?=false;
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let mut observation=run_pdf_script(&app,&browser,include_str!("liepin_native_pdf_chat_inspect.js"),&packet,&nonce).await?;
    observation["popup_url"]=json!(app.state::<NativeLiepinSession>().chat_popup_url.lock().map_err(|_|"NATIVE_PDF_STATE_FAILED")?.clone());
    pdf_rpc(app,"run.agent.recordPdfCommunication",json!({"run_id":run_id,"delivery_ref":packet["delivery_ref"],"observation":observation})).await
}

async fn continue_liepin_pdf_delivery_inner(app:AppHandle,window:WebviewWindow,run_id:String,action:String) -> Result<Value,String> {
    require_local_command(&window)?;
    if !matches!(action.as_str(),"inspect"|"prepare"|"send"){return Err("INVALID_PDF_ACTION".into());}
    let mut packet=pdf_rpc(app.clone(),"run.agent.pdfInteractionPacket",json!({"run_id":run_id,"action":action})).await?;
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let expected:Url=packet["job_url"].as_str().ok_or("INVALID_PDF_TARGET")?.parse().map_err(|_|"INVALID_PDF_TARGET")?;
    if !allowed_navigation(&expected){return Err("INVALID_PDF_TARGET".into());}
    let current=browser.url().map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    if current.host_str()!=expected.host_str() || current.path()!=expected.path(){
        browser.navigate(expected).map_err(|_|"NATIVE_PDF_TARGET_OPEN_FAILED")?;
        tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_PDF_TARGET_OPEN_FAILED")?;
    }
    // 导航/等待后重验，页面再以截止时间及取消标志约束真正点击和网络写入。
    if action=="send" {
        let permit=pdf_rpc(app.clone(),"daily.permit",json!({"run_id":run_id})).await?;
        if let (Some(target),Some(fields))=(packet.as_object_mut(),permit.as_object()) {target.extend(fields.clone());}
    }
    // 与前端开发服务器同样重载固定的自有适配文件；发行版嵌入同一份源码，IPC 不接受脚本或路径。
    let embedded=include_str!("liepin_native_pdf_interact.js");
    let source=if cfg!(debug_assertions){std::fs::read_to_string(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src/liepin_native_pdf_interact.js")).unwrap_or_else(|_|embedded.to_string())}else{embedded.to_string()};
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let observation=run_pdf_script(&app,&browser,&source,&packet,&nonce).await?;
    pdf_rpc(app,"run.agent.recordPdfInteraction",json!({"run_id":run_id,"action":action,"delivery_ref":packet["delivery_ref"],"observation":observation})).await
}


struct NativeOperationGuard(Arc<AtomicBool>);
impl NativeOperationGuard {
    fn acquire(flag:Arc<AtomicBool>)->Result<Self,String>{
        flag.compare_exchange(false,true,Ordering::SeqCst,Ordering::SeqCst).map_err(|_|"NATIVE_OPERATION_BUSY".to_string())?;
        Ok(Self(flag))
    }
}
impl Drop for NativeOperationGuard {
    fn drop(&mut self){self.0.store(false,Ordering::SeqCst);}
}
fn require_daily_phase(value:&Value,expected:&str,error:&str)->Result<(),String>{
    if value["phase"].as_str()==Some(expected){Ok(())}else{Err(error.into())}
}
async fn daily_check(app:&AppHandle,id:&str,run_id:&str)->Result<(),String>{
    pdf_rpc(app.clone(),"daily.check",json!({"id":id,"run_id":run_id})).await?;
    Ok(())
}
async fn daily_item(app:AppHandle,window:WebviewWindow,id:&str,run_id:String)->Result<(),String>{
    daily_check(&app,id,&run_id).await?;
    open_liepin_native_session_inner(app.clone(),window.clone()).await?;
    let browser=app.get_webview_window(LABEL).ok_or("daily_login_required")?;
    browser.navigate("https://c.liepin.com/resume/edit".parse().unwrap()).map_err(|_|"daily_login_required")?;
    tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"daily_execution_stopped")?;
    let checked=check_liepin_native_session_inner(app.clone(),window.clone()).await?;
    if checked["status"]!="authenticated"{return Err("daily_login_required".into());}
    let view=inspect_liepin_native_attachments_inner(app.clone(),window.clone()).await?;
    if view["attachment_view"]["inputs"].as_array().map(|v|v.len())!=Some(1){return Err("daily_attachment_capacity".into());}
    daily_check(&app,id,&run_id).await?;
    let result=upload_liepin_native_pdf_inner(app.clone(),window.clone(),run_id.clone(),true).await?;
    require_daily_phase(&result,"uploaded_unverified","daily_upload_unconfirmed")?;
    let result=inspect_uploaded_liepin_pdf_inner(app.clone(),window.clone(),run_id.clone()).await?;
    require_daily_phase(&result,"attachment_verified","daily_binding_unconfirmed")?;
    daily_check(&app,id,&run_id).await?;
    let result=start_liepin_pdf_communication_inner(app.clone(),window.clone(),run_id.clone()).await?;
    require_daily_phase(&result,"communication_started","daily_execution_stopped")?;
    let result=continue_liepin_pdf_delivery_inner(app.clone(),window.clone(),run_id.clone(),"prepare".into()).await?;
    if result["can_confirm_send"]!=true{return Err("daily_binding_unconfirmed".into());}
    daily_check(&app,id,&run_id).await?;
    let result=continue_liepin_pdf_delivery_inner(app.clone(),window,run_id.clone(),"send".into()).await?;
    require_daily_phase(&result,"final_send_pending","daily_receipt_unknown")?;
    let result=pdf_rpc(app,"run.agent.verifyPdfReceipt",json!({"run_id":run_id})).await?;
    require_daily_phase(&result,"success","daily_receipt_unknown")
}

#[tauri::command]
pub async fn run_daily_delivery(app:AppHandle,window:WebviewWindow,force:bool)->Result<Value,String>{
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    let claim=pdf_rpc(app.clone(),"daily.claim",json!({"force":force})).await?;
    if claim["claimed"]!=true{return Ok(claim);}
    let id=claim["id"].as_str().ok_or("daily_execution_stopped")?;
    let items=claim["items"].as_array().ok_or("daily_execution_stopped")?;
    *app.state::<NativeLiepinSession>().daily_cycle.lock().map_err(|_|"daily_execution_stopped")?=Some(id.to_string());
    let mut reason="completed".to_string();
    for item in items {
        let run_id=item["run_id"].as_str().ok_or("daily_execution_stopped")?.to_string();
        if let Err(error)=daily_item(app.clone(),window.clone(),id,run_id).await {reason=error.rsplit(' ').next().unwrap_or("daily_execution_stopped").to_string();break;}
    }
    let result=pdf_rpc(app.clone(),"daily.finish",json!({"id":id,"reason":reason})).await;
    if let Ok(mut current)=app.state::<NativeLiepinSession>().daily_cycle.lock(){*current=None;}
    // 恢复主业务页焦点；不改平台页面数据。
    let _=window.set_focus();
    result
}

#[tauri::command]
pub async fn change_daily_authorization(app:AppHandle,window:WebviewWindow,id:String,state:String,confirmed:bool)->Result<Value,String>{
    require_local_command(&window)?;
    let result=pdf_rpc(app.clone(),"daily.change",json!({"id":id,"state":state,"confirmed":confirmed})).await?;
    if matches!(state.as_str(),"paused"|"revoked") {
        let cycle=app.state::<NativeLiepinSession>().daily_cycle.lock().map_err(|_|"daily_execution_stopped")?.clone();
        if let (Some(cycle),Some(browser))=(cycle,app.get_webview_window(LABEL)) {
            browser.eval(format!("window.__ppfCancelledDailyCycle={};",json!(cycle))).map_err(|_|"daily_execution_stopped")?;
        }
    }
    Ok(result)
}

#[tauri::command]
pub async fn close_interrupted_daily(app:AppHandle,window:WebviewWindow,id:String)->Result<Value,String>{
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    pdf_rpc(app,"daily.finish",json!({"id":id,"reason":"daily_interrupted"})).await
}

#[tauri::command]
pub async fn open_liepin_native_session(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    open_liepin_native_session_inner(app,window).await
}

#[tauri::command]
pub async fn check_liepin_native_session(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    check_liepin_native_session_inner(app,window).await
}

fn pick_records_link(discovery:&Value)->Option<Url>{
    // 只跟随白名单域名下的非首页链接；发现结果是数据，不是指令。
    discovery["links"].as_array()?.iter().filter_map(|link|link["url"].as_str()?.parse::<Url>().ok())
        .find(|url|allowed_navigation(url) && !matches!(url.path(),""|"/"))
}

fn feedback_payload(observation:&Value)->Value{
    // 记录页按块回传多条 OBSERVE 载荷：状态与发现取第一条可解析的，行合并；全部解析失败视为未找到记录页。
    let mut rows=Vec::new();let mut status=String::from("records_page_not_found");let mut discovery=json!({"links":[]});let mut page_url=String::new();let mut first=true;
    for response in observation["responses"].as_array().cloned().unwrap_or_default(){
        let parsed=match response["payload"].as_str().and_then(|raw|serde_json::from_str::<Value>(raw).ok()){Some(value)=>value,None=>continue};
        if first{
            first=false;page_url=response["url"].as_str().unwrap_or("").to_string();
            status=parsed["status"].as_str().unwrap_or("records_page_not_found").to_string();
            if parsed["discovery"].is_object(){discovery=parsed["discovery"].clone();}
        }
        if let Some(items)=parsed["rows"].as_array(){rows.extend(items.iter().cloned());}
    }
    json!({"status":status,"page_url":page_url,"discovery":discovery,"rows":rows,"hints":observation["hints"].clone()})
}

async fn navigate_and_settle(browser:&WebviewWindow,target:Url)->Result<(),String>{
    if !allowed_navigation(&target){return Err("NATIVE_SESSION_PAGE_NOT_READY".into());}
    browser.navigate(target).map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(3000))).await.map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    Ok(())
}

async fn sync_liepin_feedback_inner(app:AppHandle,window:WebviewWindow)->Result<Value,String>{
    // 只读同步：发现投递记录页、读取状态、交给后端匹配；不发送、不点击业务控件。
    let checked=check_liepin_native_session_inner(app.clone(),window).await?;
    if checked["status"]!="authenticated"{return Err("NATIVE_SESSION_LOGIN_REQUIRED".into());}
    let packet=pdf_rpc(app.clone(),"submission.feedback.syncPacket",json!({})).await?;
    let browser=app.get_webview_window(LABEL).ok_or("NATIVE_SESSION_CLOSED")?;
    let start:Url=packet["discovery"]["start_url"].as_str().unwrap_or("https://c.liepin.com/").parse().map_err(|_|"NATIVE_SESSION_PAGE_NOT_READY")?;
    navigate_and_settle(&browser,start).await?;
    let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
    let discovery=run_pdf_script(&app,&browser,include_str!("liepin_native_feedback_discover.js"),&packet,&nonce).await?;
    let mut observation=feedback_payload(&discovery);
    if let Some(target)=pick_records_link(&observation["discovery"]){
        navigate_and_settle(&browser,target).await?;
        let nonce=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_|"NATIVE_PDF_STATE_FAILED")?.as_nanos().to_string();
        let records=run_pdf_script(&app,&browser,include_str!("liepin_native_feedback_records.js"),&packet,&nonce).await?;
        let mut found=feedback_payload(&records);
        found["discovery"]=observation["discovery"].clone();
        observation=found;
    }
    pdf_rpc(app,"submission.feedback.recordPlatformStatus",json!({"observation":observation})).await
}

#[tauri::command]
pub async fn sync_liepin_feedback(app:AppHandle,window:WebviewWindow)->Result<Value,String>{
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    sync_liepin_feedback_inner(app,window).await
}

#[tauri::command]
pub async fn inspect_liepin_native_attachments(app: AppHandle, window: WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    inspect_liepin_native_attachments_inner(app,window).await
}

#[tauri::command]
pub async fn upload_liepin_native_pdf(app: AppHandle, window: WebviewWindow, run_id: String, accept_account_effects: bool) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    upload_liepin_native_pdf_inner(app,window,run_id,accept_account_effects).await
}

#[tauri::command]
pub async fn inspect_uploaded_liepin_pdf(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    inspect_uploaded_liepin_pdf_inner(app,window,run_id).await
}

#[tauri::command]
pub async fn recheck_liepin_native_pdf_removal(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    recheck_liepin_native_pdf_removal_inner(app,window,run_id).await
}

#[tauri::command]
pub async fn diagnose_liepin_native_attachments(app:AppHandle,window:WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    diagnose_liepin_native_attachments_inner(app,window).await
}

#[tauri::command]
pub async fn cleanup_liepin_native_attachments(app:AppHandle,window:WebviewWindow) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    cleanup_liepin_native_attachments_inner(app,window).await
}

#[tauri::command]
pub async fn remove_liepin_native_pdf_attachment(app:AppHandle,window:WebviewWindow,run_id:String,confirmed:bool) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    remove_liepin_native_pdf_attachment_inner(app,window,run_id,confirmed).await
}

#[tauri::command]
pub async fn inspect_liepin_pdf_target(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    inspect_liepin_pdf_target_inner(app,window,run_id).await
}

#[tauri::command]
pub async fn start_liepin_pdf_communication(app:AppHandle,window:WebviewWindow,run_id:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    start_liepin_pdf_communication_inner(app,window,run_id).await
}

#[tauri::command]
pub async fn continue_liepin_pdf_delivery(app:AppHandle,window:WebviewWindow,run_id:String,action:String) -> Result<Value,String> {
    require_local_command(&window)?;
    let _guard=NativeOperationGuard::acquire(app.state::<NativeLiepinSession>().operation_busy.clone())?;
    continue_liepin_pdf_delivery_inner(app,window,run_id,action).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn native_operation_guard_is_exclusive_and_releases_on_drop() {
        let busy=std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
        let first=NativeOperationGuard::acquire(busy.clone()).unwrap();
        assert!(NativeOperationGuard::acquire(busy.clone()).is_err());
        drop(first);
        assert!(NativeOperationGuard::acquire(busy).is_ok());
    }

    #[test]
    fn daily_pipeline_requires_each_observed_phase_before_next_action() {
        assert!(require_daily_phase(&json!({"phase":"uploaded_unverified"}),"uploaded_unverified","daily_upload_unconfirmed").is_ok());
        for phase in ["unknown","in_flight","success",""] {
            assert!(require_daily_phase(&json!({"phase":phase}),"uploaded_unverified","daily_upload_unconfirmed").is_err());
        }
        assert!(require_daily_phase(&json!({"phase":"success"}),"success","daily_receipt_unknown").is_ok());
    }

    #[test]
    fn remote_window_cannot_use_local_commands() {
        assert!(require_main_window("main").is_ok());
        assert!(require_main_window("liepin-native-session").is_err());
        assert!(require_main_window("other").is_err());
    }

    #[test]
    fn login_signals_require_official_origin_and_no_conflict() {
        let observe = |url, authenticated, login_form, challenge| normalize_observation(
            json!({"url":url,"authenticated":authenticated,"login_form":login_form,"challenge":challenge}));
        let value = observe("https://c.liepin.com/?session=private#secret", true, false, false).unwrap();
        assert_eq!(value["status"], "authenticated");
        assert_eq!(value["url"], "https://c.liepin.com/");
        assert_eq!(observe("https://www.liepin.com/",true,true,false).unwrap()["status"], "waiting_for_login");
        assert_eq!(observe("https://safe.liepin.com/",true,false,true).unwrap()["status"], "security_challenge");
        assert_eq!(observe("about:blank",true,false,false).unwrap()["status"], "blank");
        assert!(observe("https://liepin.com.evil.example/",true,false,false).is_err());
        assert!(observe("https://user:password@www.liepin.com/",true,false,false).is_err());
        assert!(normalize_observation(json!({"url":"https://www.liepin.com/","authenticated":true,
            "login_form":false,"challenge":false,"cookie":"private"})).is_err());
    }

    #[test]
    fn attachment_observation_is_bounded_and_keeps_only_file_metadata() {
        let input = json!({"url":"https://c.liepin.com/", "authenticated":true,
            "login_form":false,"challenge":false,
            "attachment_view":{"entry_count":1,"inputs":[{"accept":".pdf,.docx","multiple":false,"disabled":false}],
                               "hints":["支持 PDF，大小不超过 20MB"]}});
        let output = normalize_observation(input).unwrap();
        assert_eq!(output["attachment_view"]["inputs"][0]["accept"], ".pdf,.docx");
        assert!(output.to_string().contains("20MB"));
    }

    #[test]
    fn parse_result_recovery_never_promotes_login_or_bypasses_challenges() {
        let observe = |url: &str, authenticated: bool, login: bool, challenge: bool| normalize_observation(json!({
            "url":url,"authenticated":authenticated,"login_form":login,"challenge":challenge}));
        let pending = observe("https://c.liepin.com/resume/parse-result", false, false, false).unwrap();
        assert_eq!(pending["status"], "unverified");
        assert_eq!(pending["can_return_to_attachments"], true);
        for (url, login, challenge) in [
            ("https://c.liepin.com/resume/parse-result", true, false),
            ("https://c.liepin.com/resume/parse-result", false, true),
            ("https://safe.liepin.com/", false, true),
            ("https://www.liepin.com/job/123.shtml", false, false),
            ("about:blank", false, false),
        ] {
            assert_eq!(observe(url, false, login, challenge).unwrap()["can_return_to_attachments"], false);
        }
    }

    #[test]
    fn feedback_records_link_only_follows_allowed_non_root_pages() {
        let discovery=json!({"links":[{"label":"首页","url":"https://c.liepin.com/"},{"label":"我的投递","url":"https://evil.example/apply"},{"label":"投递记录","url":"https://c.liepin.com/resume/apply-record?x=1"}]});
        assert_eq!(pick_records_link(&discovery).unwrap().as_str(),"https://c.liepin.com/resume/apply-record?x=1");
        assert!(pick_records_link(&json!({"links":[{"url":"https://c.liepin.com/"}]})).is_none());
        let envelope=json!({"status":"unknown","filename":"feedback","hints":[],"responses":[{"method":"OBSERVE","url":"https://c.liepin.com/resume/apply-record","http_status":0,"payload":"{\"status\":\"records\",\"rows\":[{\"job_id\":\"1\"}],\"discovery\":{\"links\":[]}}"}]});
        let payload=feedback_payload(&envelope);
        assert_eq!(payload["status"],"records");
        assert_eq!(payload["page_url"],"https://c.liepin.com/resume/apply-record");
        assert_eq!(payload["rows"][0]["job_id"],"1");
        assert_eq!(feedback_payload(&json!({"responses":[]}))["status"],"records_page_not_found");
        let chunked=json!({"hints":["待查看"],"responses":[
            {"method":"OBSERVE","url":"https://c.liepin.com/job/record/apply","http_status":0,"payload":"{\"status\":\"records\",\"rows\":[{\"job_id\":\"1\"}],\"discovery\":{\"links\":[]}}"},
            {"method":"OBSERVE","url":"https://c.liepin.com/job/record/apply","http_status":0,"payload":"{\"status\":\"records\",\"rows\":[{\"job_id\":\"2\"}],\"discovery\":{\"links\":[]}}"}]});
        let merged=feedback_payload(&chunked);
        assert_eq!(merged["rows"].as_array().unwrap().len(),2);
        assert_eq!(merged["hints"][0],"待查看");
    }

    #[test]
    fn upload_bridge_rejects_unbounded_or_unexpected_fields() {
        let value=json!({"status":"uploaded","filename":"resume_ab.pdf","hints":[],"responses":[
            {"method":"POST","url":"https://api-c.liepin.com/upload?private=1","http_status":200,"payload":"{\"code\":0}"}]});
        assert_eq!(normalize_upload_observation(value.clone()).unwrap()["responses"][0]["url"],"https://api-c.liepin.com/upload");
        let mut extra=value.clone();extra["cookie"]=json!("secret");assert!(normalize_upload_observation(extra).is_err());
        let mut wrong=value.clone();wrong["responses"][0]["url"]=json!("file:///tmp/file");assert!(normalize_upload_observation(wrong).is_err());
        let mut long=value;long["hints"]=json!(vec!["x";21]);assert!(normalize_upload_observation(long).is_err());
    }

    #[test]
    fn native_navigation_only_keeps_expected_https_origins() {
        for target in ["https://www.liepin.com/", "https://c.liepin.com/resume", "https://passport.liepin.com/"] {
            assert!(allowed_navigation(&target.parse().unwrap()));
        }
        for target in ["http://www.liepin.com/", "file:///etc/passwd", "https://example.com/", "https://www.liepin.com:8443/"] {
            assert!(!allowed_navigation(&target.parse().unwrap()));
        }
    }
}
