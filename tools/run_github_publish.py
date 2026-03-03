#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from typing import cast


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    _ = subprocess.run(cmd, check=True, text=True)


def run_optional(cmd: list[str]) -> bool:
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if completed.returncode == 0:
        return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish release with GitFlow + tag + GitHub release"
    )
    _ = parser.add_argument("--feature", required=True, help="Feature name (with or without feature/ prefix)")
    _ = parser.add_argument("--release", required=True, help="Release name (with or without release/ prefix)")
    _ = parser.add_argument("--version", required=True, help="Version tag, for example v0.1.0")
    _ = parser.add_argument("--base-dir", default="AIEF", help="AIEF base directory for checks")
    _ = parser.add_argument("--skip-check", action="store_true", help="Skip AIEF L3 check")
    _ = parser.add_argument("--dry-run", action="store_true", help="Print planned steps only")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    feature = cast(str, args.feature)
    release = cast(str, args.release)
    version = cast(str, args.version)
    base_dir = cast(str, args.base_dir)
    skip_check = bool(cast(bool, args.skip_check))
    dry_run = bool(cast(bool, args.dry_run))

    if not version.startswith("v"):
        print("[ERROR] --version must start with 'v', for example v0.1.0", file=sys.stderr)
        return 1

    if dry_run:
        print("[DRY-RUN] publish sequence")
        print(f"[DRY-RUN] feature={feature}, release={release}, version={version}, base_dir={base_dir}")
        if not skip_check:
            print(f"[DRY-RUN] python3 tools/check_aief_l3.py --root . --base-dir {base_dir}")
        print(f"[DRY-RUN] python3 tools/run_gitflow_release.py --feature {feature} --release {release}")
        print("[DRY-RUN] git checkout main && git pull --ff-only origin main")
        print(f"[DRY-RUN] git tag {version} (if not exists) && git push origin {version}")
        print(f"[DRY-RUN] gh release create {version} --title \"{version}\" --generate-notes (if not exists)")
        return 0

    try:
        if not skip_check:
            run(["python3", "tools/check_aief_l3.py", "--root", ".", "--base-dir", base_dir])

        run(["python3", "tools/run_gitflow_release.py", "--feature", feature, "--release", release])

        run(["git", "checkout", "main"])
        run(["git", "pull", "--ff-only", "origin", "main"])

        tag_exists = run_optional(["git", "rev-parse", "--verify", "--quiet", version])
        if not tag_exists:
            run(["git", "tag", version])
        run(["git", "push", "origin", version])

        release_exists = run_optional(["gh", "release", "view", version, "--json", "tagName"])
        if not release_exists:
            run(["gh", "release", "create", version, "--title", version, "--generate-notes"])

        release_url_cmd = ["gh", "release", "view", version, "--json", "url", "--jq", ".url"]
        print(f"$ {' '.join(release_url_cmd)}")
        completed = subprocess.run(release_url_cmd, check=True, text=True, capture_output=True)
        print(f"[DONE] Release published: {completed.stdout.strip()}")
        return 0
    except subprocess.CalledProcessError as exc:
        _ = exc
        print("[ERROR] Command failed during publish flow", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
