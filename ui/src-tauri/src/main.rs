#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod liepin_webview;

use serde_json::{json, Value};
use std::env;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager, State};

struct SidecarLaunchConfig {
    python_bin: String,
    script_path: PathBuf,
    working_dir: PathBuf,
}

impl SidecarLaunchConfig {
    fn from_manifest_dir(
        manifest_dir: &Path,
        python_override: Option<String>,
    ) -> Result<Self, String> {
        let working_dir = resolve_repo_root(manifest_dir)?;
        let script_path = working_dir.join("tools/sidecar/server.py");

        if !script_path.exists() {
            return Err(format!(
                "Python sidecar script not found at {}",
                script_path.display()
            ));
        }

        let python_bin = python_override.unwrap_or_else(|| {
            [".venv/bin/python3", ".venv/bin/python", ".venv/Scripts/python.exe"]
                .iter()
                .map(|relative| working_dir.join(relative))
                .find(|path| path.is_file())
                .map(|path| path.to_string_lossy().into_owned())
                .unwrap_or_else(|| "python3".to_string())
        });
        Ok(Self {
            python_bin,
            script_path,
            working_dir,
        })
    }

    fn from_app_handle(
        app_handle: &AppHandle,
        python_override: Option<String>,
    ) -> Result<Self, String> {
        if cfg!(debug_assertions) {
            return Self::from_manifest_dir(Path::new(env!("CARGO_MANIFEST_DIR")), python_override);
        }

        let resource_dir = app_handle
            .path()
            .resolve(".", BaseDirectory::Resource)
            .map_err(|error| format!("Failed to resolve resource directory: {}", error))?;
        let script_candidates = [
            resource_dir.join("tools/sidecar/server.py"),
            resource_dir.join("resources/tools/sidecar/server.py"),
            resource_dir.join("_up_/_up_/tools/sidecar/server.py"),
        ];

        if let Some(bundled_script) = script_candidates.into_iter().find(|path| path.exists()) {
            let working_dir = resolve_resource_root_from_script(&bundled_script)?;
            return Ok(Self {
                python_bin: resolve_python_bin(&working_dir, python_override),
                script_path: bundled_script,
                working_dir,
            });
        }

        Self::from_manifest_dir(Path::new(env!("CARGO_MANIFEST_DIR")), python_override)
    }
}

struct SidecarProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl SidecarProcess {
    fn spawn(app_handle: &AppHandle) -> Result<Self, String> {
        let python_override = env::var("PIPROOFFORGE_PYTHON_BIN").ok();
        let config = SidecarLaunchConfig::from_app_handle(app_handle, python_override)?;
        let python_path = build_python_path(&config.working_dir)?;

        let mut child = Command::new(&config.python_bin)
            .arg(&config.script_path)
            .current_dir(&config.working_dir)
            .env("PYTHONPATH", python_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| {
                format!(
                    "Failed to launch sidecar with {}: {}",
                    config.python_bin, error
                )
            })?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Failed to open sidecar stdin".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Failed to open sidecar stdout".to_string())?;

        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        })
    }

    fn is_running(&mut self) -> Result<bool, String> {
        match self.child.try_wait().map_err(|error| error.to_string())? {
            None => Ok(true),
            Some(_) => Ok(false),
        }
    }

    fn send_line(&mut self, request: &str) -> Result<String, String> {
        self.stdin
            .write_all(request.as_bytes())
            .map_err(|error| format!("Failed to write request to sidecar: {}", error))?;
        self.stdin
            .write_all(b"\n")
            .map_err(|error| format!("Failed to terminate sidecar request line: {}", error))?;
        self.stdin
            .flush()
            .map_err(|error| format!("Failed to flush request to sidecar: {}", error))?;

        let mut response = String::new();
        let bytes_read = self
            .stdout
            .read_line(&mut response)
            .map_err(|error| format!("Failed to read sidecar response: {}", error))?;

        if bytes_read == 0 {
            return Err("Sidecar closed stdout before sending a response".to_string());
        }

        Ok(response.trim().to_string())
    }

    fn shutdown(&mut self) -> Result<(), String> {
        let shutdown_request = json!({
            "jsonrpc": "2.0",
            "id": "shutdown",
            "method": "system.shutdown",
            "params": {
                "meta": { "correlation_id": "desktop_shutdown" },
                "graceful": true
            }
        });

        let _ = self.send_line(&shutdown_request.to_string());
        self.child
            .wait()
            .map_err(|error| format!("Failed to wait for sidecar shutdown: {}", error))?;
        Ok(())
    }

    fn kill(&mut self) -> Result<(), String> {
        self.child
            .kill()
            .map_err(|error| format!("Failed to kill sidecar process: {}", error))?;
        self.child
            .wait()
            .map_err(|error| format!("Failed to reap sidecar process: {}", error))?;
        Ok(())
    }
}

#[derive(Default)]
struct SidecarManager {
    process: Mutex<Option<SidecarProcess>>,
}

impl SidecarManager {
    fn send(&self, app_handle: &AppHandle, request: &str) -> Result<String, String> {
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "Failed to lock sidecar manager".to_string())?;

        let needs_spawn = match guard.as_mut() {
            None => true,
            Some(process) => !process.is_running()?,
        };

        if needs_spawn {
            *guard = Some(SidecarProcess::spawn(app_handle)?);
        }

        let process = guard
            .as_mut()
            .ok_or_else(|| "Sidecar process is unavailable".to_string())?;

        match process.send_line(request) {
            Ok(response) => Ok(response),
            Err(error) => {
                let _ = process.kill();
                *guard = None;
                Err(error)
            }
        }
    }

    fn shutdown(&self) -> Result<(), String> {
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "Failed to lock sidecar manager".to_string())?;

        if let Some(mut process) = guard.take() {
            if let Err(error) = process.shutdown() {
                let _ = process.kill();
                return Err(error);
            }
        }

        Ok(())
    }
}

fn resolve_repo_root(manifest_dir: &Path) -> Result<PathBuf, String> {
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| {
            format!(
                "Failed to resolve repository root from {}",
                manifest_dir.display()
            )
        })
}

fn resolve_resource_root_from_script(script_path: &Path) -> Result<PathBuf, String> {
    script_path
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| {
            format!(
                "Failed to resolve bundled resource root from {}",
                script_path.display()
            )
        })
}

fn resolve_python_bin(resource_root: &Path, python_override: Option<String>) -> String {
    if let Some(python_bin) = python_override {
        return python_bin;
    }

    let candidates = [
        resource_root.join("sidecar/bin/python3"),
        resource_root.join("sidecar/bin/python"),
        resource_root.join("python/bin/python3"),
        resource_root.join("python/bin/python"),
        resource_root.join("sidecar/python.exe"),
        resource_root.join("python/python.exe"),
    ];

    for candidate in candidates {
        if candidate.exists() {
            return candidate.to_string_lossy().to_string();
        }
    }

    "python3".to_string()
}

fn build_python_path(working_dir: &Path) -> Result<std::ffi::OsString, String> {
    let mut paths = vec![working_dir.to_path_buf()];
    if let Some(existing) = env::var_os("PYTHONPATH") {
        paths.extend(env::split_paths(&existing));
    }
    env::join_paths(paths).map_err(|error| format!("Failed to build PYTHONPATH: {}", error))
}

fn smoke_test_requested() -> bool {
    matches!(
        env::var("PIPROOFFORGE_SMOKE_TEST").ok().as_deref(),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
}

fn build_rpc_request(request_id: &str, method: &str, params: Value) -> String {
    json!({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    })
    .to_string()
}

fn parse_rpc_success_response(
    response: &str,
    request_id: &str,
    method: &str,
) -> Result<Value, String> {
    let payload: Value = serde_json::from_str(response)
        .map_err(|error| format!("Failed to parse {} response JSON: {}", method, error))?;

    if payload.get("id") != Some(&Value::String(request_id.to_string())) {
        return Err(format!(
            "{} response id mismatch: expected {}, got {}",
            method,
            request_id,
            payload
                .get("id")
                .map(Value::to_string)
                .unwrap_or_else(|| "null".to_string())
        ));
    }

    if let Some(error) = payload.get("error") {
        let code = error
            .get("code")
            .and_then(Value::as_str)
            .unwrap_or("UNKNOWN_ERROR");
        let message = error
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("unknown sidecar error");
        return Err(format!("{} failed with {}: {}", method, code, message));
    }

    payload
        .get("result")
        .cloned()
        .ok_or_else(|| format!("{} response missing result payload", method))
}

fn build_smoke_test_summary(handshake: &Value, ping: &Value) -> Value {
    json!({
        "ok": true,
        "handshake": {
            "accepted_protocol_version": handshake.get("accepted_protocol_version").cloned().unwrap_or(Value::Null),
            "sidecar_version": handshake.get("sidecar_version").cloned().unwrap_or(Value::Null),
            "capabilities": handshake.get("capabilities").cloned().unwrap_or(Value::Null),
        },
        "ping": {
            "state": ping.get("state").cloned().unwrap_or(Value::Null),
            "timestamp": ping.get("timestamp").cloned().unwrap_or(Value::Null),
        }
    })
}

fn run_packaged_smoke_test(
    app_handle: &AppHandle,
    manager: &SidecarManager,
) -> Result<Value, String> {
    let handshake_request = build_rpc_request(
        "req_handshake",
        "system.handshake",
        json!({
            "meta": { "correlation_id": "smoke_handshake" },
            "ui_version": env!("CARGO_PKG_VERSION"),
            "protocol_version": "1.0.0",
            "capabilities": ["events", "file-preview", "pdf-export"],
        }),
    );
    let ping_request = build_rpc_request(
        "req_ping",
        "system.ping",
        json!({
            "meta": { "correlation_id": "smoke_ping" },
        }),
    );

    let handshake_response = manager.send(app_handle, &handshake_request)?;
    let handshake_result =
        parse_rpc_success_response(&handshake_response, "req_handshake", "system.handshake")?;

    let ping_response = manager.send(app_handle, &ping_request)?;
    let ping_result = parse_rpc_success_response(&ping_response, "req_ping", "system.ping")?;

    manager.shutdown()?;

    Ok(build_smoke_test_summary(&handshake_result, &ping_result))
}

#[tauri::command]
async fn sidecar_request(
    app_handle: AppHandle,
    window: tauri::WebviewWindow,
    request: String,
) -> Result<String, String> {
    liepin_webview::require_local_command(&window)?;
    // 模型提炼和 PDF 渲染可较慢；沿用同一 sidecar 串行协议，但不占用主窗口事件线程。
    tauri::async_runtime::spawn_blocking(move || {
        app_handle.state::<SidecarManager>().send(&app_handle, &request)
    }).await.map_err(|_| "SIDECAR_REQUEST_INTERRUPTED".to_string())?
}

#[tauri::command]
fn sidecar_shutdown(window: tauri::WebviewWindow, manager: State<'_, SidecarManager>) -> Result<(), String> {
    liepin_webview::require_local_command(&window)?;
    manager.shutdown()
}

fn open_liepin_authorization_with<F>(launch: F) -> Result<(), String>
where
    F: FnOnce(&str) -> std::io::Result<bool>,
{
    // 固定官方授权入口，不开放任意 URL 或命令执行能力。
    match launch("https://www.liepin.com/mcp/auth") {
        Ok(true) => Ok(()),
        _ => Err("OPEN_AUTHORIZATION_FAILED".to_string()),
    }
}

#[tauri::command]
async fn open_liepin_authorization(window: tauri::WebviewWindow) -> Result<(), String> {
    liepin_webview::require_local_command(&window)?;
    tauri::async_runtime::spawn_blocking(|| {
        open_liepin_authorization_with(|url| {
            #[cfg(target_os = "macos")]
            let mut command = Command::new("/usr/bin/open");
            #[cfg(target_os = "windows")]
            let mut command = {
                let mut command = Command::new("rundll32.exe");
                command.arg("url.dll,FileProtocolHandler");
                command
            };
            #[cfg(not(any(target_os = "macos", target_os = "windows")))]
            let mut command = Command::new("xdg-open");
            command.arg(url).stdout(Stdio::null()).stderr(Stdio::null())
                .status().map(|status| status.success())
        })
    }).await.map_err(|_| "OPEN_AUTHORIZATION_FAILED".to_string())?
}

fn main() {
    tauri::Builder::default()
        // 窗口状态插件：启动时恢复上次的尺寸与位置，退出时保存；最小尺寸仍由 tauri.conf.json 约束。
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .manage(SidecarManager::default())
        .manage(liepin_webview::NativeLiepinSession::default())
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                // 开发用文件触发器：App 内自动上传不必依赖窗口前台点击。
                let app_handle = app.handle().clone();
                let root = resolve_repo_root(std::path::Path::new(env!("CARGO_MANIFEST_DIR")))
                    .unwrap_or_else(|_| std::path::PathBuf::from("."));
                std::thread::spawn(move || loop {
                    std::thread::sleep(std::time::Duration::from_millis(500));
                    let request_path = root.join("app-data/auto_upload_request.json");
                    if !request_path.is_file() { continue; }
                    let raw = std::fs::read_to_string(&request_path).unwrap_or_default();
                    let _ = std::fs::remove_file(&request_path);
                    let parsed = serde_json::from_str::<serde_json::Value>(&raw).ok();
                    let action = parsed.as_ref().and_then(|v| v.get("action").and_then(|x| x.as_str())).unwrap_or("upload").to_string();
                    let run_id = parsed.as_ref().and_then(|v| v.get("run_id").and_then(|x| x.as_str())).map(str::to_string);
                    if action != "diagnose" && run_id.is_none() {
                        let _ = std::fs::write(root.join("app-data/auto_upload_result.json"), json!({"ok":false,"error":"missing_run_id"}).to_string());
                        continue;
                    }
                    let handle = app_handle.clone();
                    let root2 = root.clone();
                    tauri::async_runtime::spawn(async move {
                        let outcome = match (action.as_str(), handle.get_webview_window("main")) {
                            ("diagnose", Some(window)) => liepin_webview::diagnose_from_trigger(handle.clone(), window).await,
                            ("upload", Some(window)) => liepin_webview::auto_upload_from_trigger(handle.clone(), window, run_id.clone().unwrap_or_default()).await,
                            (_, Some(_)) => Err("UNKNOWN_TRIGGER_ACTION".to_string()),
                            (_, None) => Err("MAIN_WINDOW_MISSING".to_string()),
                        };
                        let payload = match outcome {
                            Ok(value) => json!({"ok":true,"action":action,"result":value}),
                            Err(error) => json!({"ok":false,"action":action,"error":error}),
                        };
                        let _ = std::fs::write(root2.join("app-data/auto_upload_result.json"), payload.to_string());
                    });
                });
            }
            if smoke_test_requested() {
                let app_handle = app.handle().clone();
                let manager = app.state::<SidecarManager>();
                let outcome = run_packaged_smoke_test(&app_handle, &manager);

                match outcome {
                    Ok(summary) => {
                        println!("{}", summary);
                        app_handle.exit(0);
                    }
                    Err(error) => {
                        println!("{}", json!({ "ok": false, "error": error }));
                        app_handle.exit(1);
                    }
                }
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_request,
            sidecar_shutdown,
            open_liepin_authorization,
            liepin_webview::open_liepin_native_session,
            liepin_webview::check_liepin_native_session,
            liepin_webview::inspect_liepin_native_attachments,
            liepin_webview::sync_liepin_feedback,
            liepin_webview::upload_liepin_native_pdf,
            liepin_webview::cleanup_liepin_native_attachments,
            liepin_webview::diagnose_liepin_native_attachments,
            liepin_webview::inspect_uploaded_liepin_pdf,
            liepin_webview::inspect_liepin_pdf_target,
            liepin_webview::start_liepin_pdf_communication,
            liepin_webview::continue_liepin_pdf_delivery,
            liepin_webview::remove_liepin_native_pdf_attachment,
            liepin_webview::recheck_liepin_native_pdf_removal,
            liepin_webview::run_daily_delivery,
            liepin_webview::change_daily_authorization,
            liepin_webview::close_interrupted_daily
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::{
        build_smoke_test_summary, parse_rpc_success_response, resolve_python_bin,
        resolve_repo_root, resolve_resource_root_from_script, SidecarLaunchConfig,
        open_liepin_authorization_with,
    };
    use serde_json::json;
    use std::path::{Path, PathBuf};
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn authorization_opens_only_fixed_official_https_destination() {
        let result = open_liepin_authorization_with(|url| {
            assert_eq!(url, "https://www.liepin.com/mcp/auth");
            Ok(true)
        });
        assert_eq!(result, Ok(()));
    }

    #[test]
    fn authorization_reports_unsuccessful_launcher() {
        assert_eq!(open_liepin_authorization_with(|_| Ok(false)),
                   Err("OPEN_AUTHORIZATION_FAILED".to_string()));
    }

    #[test]
    fn authorization_does_not_expose_launcher_error_details() {
        let result = open_liepin_authorization_with(|_| {
            Err(std::io::Error::new(std::io::ErrorKind::NotFound, "private launcher details"))
        });
        assert_eq!(result, Err("OPEN_AUTHORIZATION_FAILED".to_string()));
    }

    #[test]
    fn resolves_repo_root_from_manifest_dir() {
        let manifest_dir = Path::new("/tmp/pi-proof-forge/ui/src-tauri");
        let root = resolve_repo_root(manifest_dir).expect("repo root should resolve");

        assert_eq!(root, PathBuf::from("/tmp/pi-proof-forge"));
    }

    #[test]
    fn builds_sidecar_launch_paths_from_manifest_dir() {
        let unique_suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after epoch")
            .as_nanos();
        let repo_root = std::env::temp_dir().join(format!("pi-proof-forge-{unique_suffix}"));
        let manifest_dir = repo_root.join("ui/src-tauri");
        let script_path = repo_root.join("tools/sidecar/server.py");

        std::fs::create_dir_all(script_path.parent().expect("script parent should exist"))
            .expect("script parent should be created");
        std::fs::create_dir_all(&manifest_dir).expect("manifest dir should be created");
        std::fs::write(&script_path, "print('ok')").expect("script should be written");

        let config =
            SidecarLaunchConfig::from_manifest_dir(&manifest_dir, Some("python-test".to_string()))
                .expect("launch config should be created");

        assert_eq!(config.python_bin, "python-test");
        assert_eq!(config.working_dir, repo_root);
        assert_eq!(config.script_path, script_path);

        let fallback = SidecarLaunchConfig::from_manifest_dir(&manifest_dir, None).unwrap();
        assert_eq!(fallback.python_bin, "python3");
        let project_python = repo_root.join(".venv/bin/python3");
        std::fs::create_dir_all(project_python.parent().unwrap()).unwrap();
        std::fs::write(&project_python, "").unwrap();
        let automatic = SidecarLaunchConfig::from_manifest_dir(&manifest_dir, None).unwrap();
        assert_eq!(automatic.python_bin, project_python.to_string_lossy());
        let explicit = SidecarLaunchConfig::from_manifest_dir(&manifest_dir, Some("python-test".into())).unwrap();
        assert_eq!(explicit.python_bin, "python-test");

        let _ = std::fs::remove_dir_all(&repo_root);
    }

    #[test]
    fn resolves_bundled_resource_root_from_script_path() {
        let script_path =
            Path::new("/Applications/PiProofForge.app/Contents/Resources/tools/sidecar/server.py");

        let resource_root =
            resolve_resource_root_from_script(script_path).expect("resource root should resolve");

        assert_eq!(
            resource_root,
            PathBuf::from("/Applications/PiProofForge.app/Contents/Resources")
        );
    }

    #[test]
    fn prefers_bundled_python_binary_when_present() {
        let unique_suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after epoch")
            .as_nanos();
        let resource_root =
            std::env::temp_dir().join(format!("piproofforge-resource-{unique_suffix}"));
        let bundled_python = resource_root.join("sidecar/bin/python3");

        std::fs::create_dir_all(
            bundled_python
                .parent()
                .expect("bundled python parent should exist"),
        )
        .expect("bundled python parent should be created");
        std::fs::write(&bundled_python, "").expect("bundled python marker should be written");

        let python_bin = resolve_python_bin(&resource_root, None);

        assert_eq!(python_bin, bundled_python.to_string_lossy().to_string());

        let _ = std::fs::remove_dir_all(&resource_root);
    }

    #[test]
    fn parses_successful_rpc_response() {
        let response = r#"{"jsonrpc":"2.0","id":"req_handshake","result":{"accepted_protocol_version":"1.0.0","meta":{"correlation_id":"corr_smoke"}}}"#;

        let result = parse_rpc_success_response(response, "req_handshake", "system.handshake")
            .expect("handshake response should parse");

        assert_eq!(result["accepted_protocol_version"], "1.0.0");
        assert_eq!(result["meta"]["correlation_id"], "corr_smoke");
    }

    #[test]
    fn rejects_rpc_error_response_in_smoke_test() {
        let response = r#"{"jsonrpc":"2.0","id":"req_ping","error":{"code":"SIDECAR_UNAVAILABLE","message":"down"}}"#;

        let error = parse_rpc_success_response(response, "req_ping", "system.ping")
            .expect_err("error response should fail smoke parsing");

        assert!(error.contains("system.ping"));
        assert!(error.contains("SIDECAR_UNAVAILABLE"));
    }

    #[test]
    fn builds_smoke_test_summary_from_handshake_and_ping() {
        let summary = build_smoke_test_summary(
            &json!({
                "accepted_protocol_version": "1.0.0",
                "sidecar_version": "0.1.0",
                "capabilities": ["events"],
            }),
            &json!({
                "state": "ready",
                "timestamp": "2026-03-08T12:00:00Z",
            }),
        );

        assert_eq!(summary["ok"], true);
        assert_eq!(summary["handshake"]["accepted_protocol_version"], "1.0.0");
        assert_eq!(summary["ping"]["state"], "ready");
    }
}
