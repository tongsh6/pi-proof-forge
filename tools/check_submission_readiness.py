#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check submission readiness gates")
    _ = parser.add_argument("--root", default="outputs/submissions")
    _ = parser.add_argument("--platform", default="liepin")
    _ = parser.add_argument("--require-status", default="success")
    _ = parser.add_argument("--min-screenshots", type=int, default=1)
    return parser.parse_args()


def latest_run_dir(root: Path, platform: str) -> Path | None:
    platform_dir = root / platform
    if not platform_dir.exists() or not platform_dir.is_dir():
        return None
    runs = [p for p in platform_dir.iterdir() if p.is_dir()]
    if not runs:
        return None
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0]


def main() -> int:
    args = parse_args()
    root = Path(cast(str, args.root))
    platform = cast(str, args.platform)
    require_status = cast(str, args.require_status)
    min_screenshots = cast(int, args.min_screenshots)

    run_dir = latest_run_dir(root, platform)
    if run_dir is None:
        print(f"[ERROR] no run directory found under: {root / platform}")
        return 1

    log_json = run_dir / "submission_log.json"
    if not log_json.exists() or not log_json.is_file():
        print(f"[ERROR] submission_log.json not found: {log_json}")
        return 1

    payload_obj = cast(object, json.loads(log_json.read_text(encoding="utf-8")))
    if not isinstance(payload_obj, dict):
        print(f"[ERROR] invalid submission_log.json payload: {log_json}")
        return 1
    payload = cast(dict[str, object], payload_obj)
    status = str(payload.get("status", ""))
    mode = str(payload.get("mode", ""))
    screenshots = list((run_dir / "screenshots").glob("*.png"))

    if status != require_status:
        print(f"[ERROR] status mismatch: expected={require_status}, actual={status}")
        print(f"[INFO] run_dir={run_dir}")
        return 1

    if mode != "submit":
        print(f"[ERROR] latest run mode is not submit: {mode}")
        print(f"[INFO] run_dir={run_dir}")
        return 1

    if len(screenshots) < min_screenshots:
        print(f"[ERROR] screenshots too few: expected>={min_screenshots}, actual={len(screenshots)}")
        print(f"[INFO] run_dir={run_dir}")
        return 1

    print("[PASS] submission readiness checks passed")
    print(f"[INFO] run_dir={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
