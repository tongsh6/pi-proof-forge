#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from .liepin import LiepinSubmissionConfig, run_liepin_submission


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run submission flow")
    _ = parser.add_argument("--platform", required=True, choices=["liepin"])
    _ = parser.add_argument("--job-url", required=True)
    _ = parser.add_argument("--resume", required=True)
    _ = parser.add_argument("--profile", required=True)
    _ = parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run browser in headless mode",
    )
    _ = parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    job_url = cast(str, args.job_url)
    if not (job_url.startswith("http://") or job_url.startswith("https://")):
        raise RuntimeError("--job-url must start with http:// or https://")

    resume_path = Path(cast(str, args.resume))
    profile_path = Path(cast(str, args.profile))
    if not resume_path.exists() or not resume_path.is_file():
        raise RuntimeError(f"resume file not found: {resume_path}")
    if not profile_path.exists() or not profile_path.is_file():
        raise RuntimeError(f"profile file not found: {profile_path}")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    platform = cast(str, args.platform)
    if platform == "liepin":
        config = LiepinSubmissionConfig(
            job_url=cast(str, args.job_url),
            resume_path=cast(str, args.resume),
            profile_path=cast(str, args.profile),
            headless=bool(cast(bool, args.headless)),
            dry_run=bool(cast(bool, args.dry_run)),
        )
        return run_liepin_submission(config)

    print(f"[ERROR] Unsupported platform: {platform}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
