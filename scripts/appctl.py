#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROOT_PATTERN = re.escape(str(ROOT))
RUNTIME_DIR = ROOT / ".app-runtime"
PID_FILE = RUNTIME_DIR / "piproofforge-app.pid"
LOG_FILE = RUNTIME_DIR / "piproofforge-app.log"
TAURI_PATTERNS = (
    f"{ROOT_PATTERN}.*/ui.*tauri",
    f"{ROOT_PATTERN}.*/ui/src-tauri/target",
)
SIDECAR_PATTERN = f"{ROOT_PATTERN}.*/tools/sidecar/server.py"


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_pgrep(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            pids.append(pid)
    return pids


def status() -> int:
    pid = _read_pid()
    if pid is not None and _is_running(pid):
        print(f"running pid={pid}")
        print(f"log={LOG_FILE}")
        return 0

    tauri_pids = [
        pid for pattern in TAURI_PATTERNS for pid in _run_pgrep(pattern)
    ]
    sidecar_pids = _run_pgrep(SIDECAR_PATTERN)
    if tauri_pids or sidecar_pids:
        print("partial")
        if tauri_pids:
            print("tauri=" + ",".join(str(pid) for pid in tauri_pids))
        if sidecar_pids:
            print("sidecar=" + ",".join(str(pid) for pid in sidecar_pids))
        return 0

    print("stopped")
    return 0


def start() -> int:
    pid = _read_pid()
    if pid is not None and _is_running(pid):
        print(f"already running pid={pid}")
        print(f"log={LOG_FILE}")
        return 0

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("a", encoding="utf-8")
    log_handle.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_handle.flush()

    process = subprocess.Popen(
        ["pnpm", "--dir", "ui", "run", "tauri", "dev"],
        cwd=ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(f"started pid={process.pid}")
    print(f"log={LOG_FILE}")
    return 0


def _terminate_pid(pid: int, timeout_seconds: float) -> None:
    if not _is_running(pid):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_running(pid):
            return
        time.sleep(0.1)

    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        os.kill(pid, signal.SIGKILL)


def stop() -> int:
    stopped = False
    pid = _read_pid()
    if pid is not None:
        _terminate_pid(pid, 5.0)
        stopped = True

    for pattern in (*TAURI_PATTERNS, SIDECAR_PATTERN):
        for proc_pid in _run_pgrep(pattern):
            try:
                os.kill(proc_pid, signal.SIGTERM)
                stopped = True
            except ProcessLookupError:
                continue

    if PID_FILE.exists():
        PID_FILE.unlink()
    print("stopped" if stopped else "already stopped")
    return 0


def restart() -> int:
    stop()
    return start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PiProofForge desktop app control")
    parser.add_argument("command", choices=("start", "stop", "restart", "status"))
    args = parser.parse_args(argv)

    if args.command == "start":
        return start()
    if args.command == "stop":
        return stop()
    if args.command == "restart":
        return restart()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
