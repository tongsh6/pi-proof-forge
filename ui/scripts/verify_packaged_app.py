from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast


UI_DIR = Path(__file__).resolve().parents[1]
DEFAULT_APP_PATH = (
    UI_DIR
    / "src-tauri"
    / "target"
    / "release"
    / "bundle"
    / "macos"
    / "PiProofForge.app"
)


class HandshakeSummary(TypedDict, total=False):
    accepted_protocol_version: str
    sidecar_version: str
    capabilities: list[str]


class PingSummary(TypedDict, total=False):
    state: str
    timestamp: str


class SmokeSummary(TypedDict, total=False):
    ok: bool
    handshake: HandshakeSummary
    ping: PingSummary
    error: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--app", type=Path, default=DEFAULT_APP_PATH)
    _ = parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def _resolve_app_binary(app_path: Path) -> Path:
    binary_path = app_path / "Contents" / "MacOS" / "piproofforge"
    if not binary_path.exists():
        raise RuntimeError(f"Packaged app binary not found: {binary_path}")
    return binary_path


def _parse_summary(stdout: str) -> SmokeSummary:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload_obj = cast(object, json.loads(line))
        except json.JSONDecodeError:
            continue
        if isinstance(payload_obj, dict) and "ok" in payload_obj:
            return cast(SmokeSummary, cast(object, payload_obj))
    raise RuntimeError(f"Smoke test summary not found in stdout:\n{stdout}")


def _run_smoke(binary_path: Path, timeout: int) -> SmokeSummary:
    env = os.environ.copy()
    env["PIPROOFFORGE_SMOKE_TEST"] = "1"
    completed = subprocess.run(
        [str(binary_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    summary = _parse_summary(completed.stdout)

    if completed.returncode != 0:
        raise RuntimeError(
            f"Packaged app smoke test failed with non-zero exit code {completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    if summary.get("ok") is not True:
        raise RuntimeError(
            f"Packaged app smoke test reported failure.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    handshake = summary.get("handshake", {})
    ping = summary.get("ping", {})
    if handshake.get("accepted_protocol_version") != "1.0.0":
        raise RuntimeError(
            f"Unexpected handshake summary: {json.dumps(summary, ensure_ascii=True)}"
        )
    if ping.get("state") != "ready":
        raise RuntimeError(
            f"Unexpected ping summary: {json.dumps(summary, ensure_ascii=True)}"
        )

    return summary


def main() -> int:
    args = _parse_args()
    app_path = cast(Path, args.app)
    timeout = cast(int, args.timeout)
    binary_path = _resolve_app_binary(app_path)
    summary = _run_smoke(binary_path, timeout)
    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
