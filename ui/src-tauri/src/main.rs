#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

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
    fn from_manifest_dir(manifest_dir: &Path, python_override: Option<String>) -> Result<Self, String> {
        let working_dir = resolve_repo_root(manifest_dir)?;
        let script_path = working_dir.join("tools/sidecar/server.py");

        if !script_path.exists() {
            return Err(format!(
                "Python sidecar script not found at {}",
                script_path.display()
            ));
        }

        Ok(Self {
            python_bin: python_override.unwrap_or_else(|| "python3".to_string()),
            script_path,
            working_dir,
        })
    }

    fn from_app_handle(
        app_handle: &AppHandle,
        python_override: Option<String>,
    ) -> Result<Self, String> {
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

        let mut child = Command::new(&config.python_bin)
            .arg(&config.script_path)
            .current_dir(&config.working_dir)
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

fn smoke_test_requested() -> bool {
    matches!(
        env::var("PIPROOFFORGE_SMOKE_TEST")
            .ok()
            .as_deref(),
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

fn run_packaged_smoke_test(app_handle: &AppHandle, manager: &SidecarManager) -> Result<Value, String> {
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
    let handshake_result = parse_rpc_success_response(
        &handshake_response,
        "req_handshake",
        "system.handshake",
    )?;

    let ping_response = manager.send(app_handle, &ping_request)?;
    let ping_result = parse_rpc_success_response(&ping_response, "req_ping", "system.ping")?;

    manager.shutdown()?;

    Ok(build_smoke_test_summary(&handshake_result, &ping_result))
}

#[tauri::command]
fn sidecar_request(
    app_handle: AppHandle,
    request: String,
    manager: State<'_, SidecarManager>,
) -> Result<String, String> {
    manager.send(&app_handle, &request)
}

#[tauri::command]
fn sidecar_shutdown(manager: State<'_, SidecarManager>) -> Result<(), String> {
    manager.shutdown()
}

fn main() {
    tauri::Builder::default()
        .manage(SidecarManager::default())
        .setup(|app| {
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
        .invoke_handler(tauri::generate_handler![sidecar_request, sidecar_shutdown])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::{
        build_smoke_test_summary, parse_rpc_success_response, resolve_python_bin,
        resolve_repo_root, resolve_resource_root_from_script, SidecarLaunchConfig,
    };
    use serde_json::json;
    use std::path::{Path, PathBuf};
    use std::time::{SystemTime, UNIX_EPOCH};

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

        let config = SidecarLaunchConfig::from_manifest_dir(
            &manifest_dir,
            Some("python-test".to_string()),
        )
        .expect("launch config should be created");

        assert_eq!(config.python_bin, "python-test");
        assert_eq!(config.working_dir, repo_root);
        assert_eq!(config.script_path, script_path);

        let _ = std::fs::remove_dir_all(&repo_root);
    }

    #[test]
    fn resolves_bundled_resource_root_from_script_path() {
        let script_path = Path::new(
            "/Applications/PiProofForge.app/Contents/Resources/tools/sidecar/server.py",
        );

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
        let resource_root = std::env::temp_dir().join(format!("piproofforge-resource-{unique_suffix}"));
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
