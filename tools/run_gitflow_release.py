#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def run(cmd: list[str], dry_run: bool = False) -> None:
    print(f"$ {' '.join(cmd)}")
    if dry_run:
        return
    _ = subprocess.run(cmd, check=True, text=True)


def run_capture(cmd: list[str], dry_run: bool = False) -> str:
    print(f"$ {' '.join(cmd)}")
    if dry_run:
        return ""
    completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def has_ref(ref: str) -> bool:
    completed = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        check=False,
        text=True,
    )
    return completed.returncode == 0


def ensure_clean_worktree(dry_run: bool = False) -> None:
    result = run_capture(["git", "status", "--porcelain"], dry_run=dry_run)
    if not dry_run and result:
        raise RuntimeError("Working tree is not clean. Please commit/stash changes before running.")


def normalize_feature(name: str) -> str:
    return name if name.startswith("feature/") else f"feature/{name}"


def normalize_release(name: str) -> str:
    return name if name.startswith("release/") else f"release/{name}"


def checkout_branch(branch: str, dry_run: bool = False) -> None:
    run(["git", "checkout", branch], dry_run=dry_run)


def checkout_from_base(branch: str, base: str, dry_run: bool = False) -> None:
    run(["git", "checkout", "-b", branch, base], dry_run=dry_run)


def ensure_branch_from_remote_or_base(branch: str, base: str, remote: str, dry_run: bool = False) -> None:
    if dry_run:
        checkout_from_base(branch, base, dry_run=True)
        return
    local_ref = f"refs/heads/{branch}"
    remote_ref = f"refs/remotes/{remote}/{branch}"
    if has_ref(local_ref):
        checkout_branch(branch, dry_run=False)
        return
    if has_ref(remote_ref):
        run(["git", "checkout", "-b", branch, "--track", f"{remote}/{branch}"], dry_run=False)
        return
    checkout_from_base(branch, base, dry_run=False)


def pull_ff(branch: str, remote: str, dry_run: bool = False) -> None:
    checkout_branch(branch, dry_run=dry_run)
    run(["git", "pull", "--ff-only", remote, branch], dry_run=dry_run)


def ensure_feature_has_delta(feature_branch: str, main_branch: str, dry_run: bool = False) -> None:
    if dry_run:
        return
    count_text = run_capture(["git", "rev-list", "--count", f"{main_branch}..{feature_branch}"])
    count = int(count_text or "0")
    if count <= 0:
        raise RuntimeError(
            f"{feature_branch} has no commits ahead of {main_branch}; refusing to merge empty feature flow."
        )


def merge_branch(target: str, source: str, dry_run: bool = False) -> None:
    checkout_branch(target, dry_run=dry_run)
    run(["git", "merge", "--no-ff", source, "-m", f"merge: {source} -> {target}"], dry_run=dry_run)


def push_branch(branch: str, remote: str, dry_run: bool = False, set_upstream: bool = False) -> None:
    if set_upstream:
        run(["git", "push", "-u", remote, branch], dry_run=dry_run)
        return
    run(["git", "push", remote, branch], dry_run=dry_run)


def maybe_push_branch(branch: str, remote: str, push: bool, dry_run: bool, set_upstream: bool = False) -> None:
    if push:
        push_branch(branch, remote, dry_run=dry_run, set_upstream=set_upstream)


def delete_feature_branch(feature_branch: str, remote: str, push: bool, dry_run: bool = False) -> None:
    run(["git", "branch", "-d", feature_branch], dry_run=dry_run)
    if push:
        run(["git", "push", remote, "--delete", feature_branch], dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote GitFlow branches: main -> feature -> develop -> release -> main"
    )
    _ = parser.add_argument("--feature", required=True, help="Feature name or feature/<name>")
    _ = parser.add_argument("--release", required=True, help="Release name or release/<name>")
    _ = parser.add_argument("--main-branch", default="main", help="Main branch name (default: main)")
    _ = parser.add_argument("--develop-branch", default="develop", help="Develop branch name (default: develop)")
    _ = parser.add_argument("--remote", default="origin", help="Remote name (default: origin)")
    _ = parser.add_argument("--create-feature", action="store_true", help="Create/switch feature from main first")
    _ = parser.add_argument(
        "--delete-feature",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete merged feature branch after flow (default: true)",
    )
    _ = parser.add_argument(
        "--keep-release",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep release branch after merge to main (default: true)",
    )
    _ = parser.add_argument("--no-push", action="store_true", help="Do not push branches to remote")
    _ = parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    push = not bool(args.no_push)
    dry_run = bool(args.dry_run)
    feature_branch = normalize_feature(str(args.feature))
    release_branch = normalize_release(str(args.release))
    main_branch = str(args.main_branch)
    develop_branch = str(args.develop_branch)
    remote = str(args.remote)

    try:
        ensure_clean_worktree(dry_run=dry_run)
        run(["git", "fetch", remote, "--prune"], dry_run=dry_run)

        pull_ff(main_branch, remote, dry_run=dry_run)

        feature_prepared = False
        if bool(args.create_feature):
            ensure_branch_from_remote_or_base(feature_branch, main_branch, remote, dry_run=dry_run)
            maybe_push_branch(feature_branch, remote, push=push, dry_run=dry_run, set_upstream=True)
            feature_prepared = True

        if not feature_prepared:
            ensure_branch_from_remote_or_base(feature_branch, main_branch, remote, dry_run=dry_run)
        ensure_feature_has_delta(feature_branch, main_branch, dry_run=dry_run)

        ensure_branch_from_remote_or_base(develop_branch, main_branch, remote, dry_run=dry_run)
        if push:
            pull_ff(develop_branch, remote, dry_run=dry_run)
        merge_branch(develop_branch, feature_branch, dry_run=dry_run)
        maybe_push_branch(develop_branch, remote, push=push, dry_run=dry_run)

        ensure_branch_from_remote_or_base(release_branch, develop_branch, remote, dry_run=dry_run)
        maybe_push_branch(release_branch, remote, push=push, dry_run=dry_run, set_upstream=True)

        if push:
            pull_ff(main_branch, remote, dry_run=dry_run)
        else:
            checkout_branch(main_branch, dry_run=dry_run)
        merge_branch(main_branch, release_branch, dry_run=dry_run)
        maybe_push_branch(main_branch, remote, push=push, dry_run=dry_run)

        if bool(args.delete_feature):
            checkout_branch(main_branch, dry_run=dry_run)
            delete_feature_branch(feature_branch, remote=remote, push=push, dry_run=dry_run)

        if bool(args.keep_release):
            print(f"[INFO] Keeping release branch: {release_branch}")
        else:
            print("[INFO] keep-release disabled; no automatic release deletion is executed by this script.")

        print("[DONE] GitFlow promotion completed.")
        print(f"[FLOW] {main_branch} -> {feature_branch} -> {develop_branch} -> {release_branch} -> {main_branch}")
        print(f"[POLICY] feature delete={bool(args.delete_feature)}, release keep={bool(args.keep_release)}")
        return 0
    except subprocess.CalledProcessError as exc:
        if isinstance(exc.cmd, list):
            cmd = " ".join(str(part) for part in exc.cmd)
        else:
            cmd = str(exc.cmd)
        print(f"[ERROR] Command failed: {cmd}", file=sys.stderr)
        return exc.returncode or 1
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
