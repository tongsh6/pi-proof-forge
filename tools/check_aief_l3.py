#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import cast


def check_exists(root: Path, rel_path: str) -> tuple[bool, str]:
    path = root / rel_path
    if path.exists():
        return True, f"OK  {rel_path}"
    return False, f"MISS {rel_path}"


def check_contains(root: Path, rel_path: str, needle: str, label: str) -> tuple[bool, str]:
    path = root / rel_path
    if not path.exists():
        return False, f"MISS {rel_path} ({label})"
    content = path.read_text(encoding="utf-8")
    if needle in content:
        return True, f"OK  {rel_path} ({label})"
    return False, f"MISS {rel_path} ({label})"


def check_min_files(root: Path, rel_dir: str, pattern: str, min_count: int, label: str) -> tuple[bool, str]:
    target = root / rel_dir
    if not target.exists() or not target.is_dir():
        return False, f"MISS {rel_dir} ({label})"
    count = len(list(target.glob(pattern)))
    if count >= min_count:
        return True, f"OK  {rel_dir} ({label}: {count})"
    return False, f"MISS {rel_dir} ({label}: {count}<{min_count})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AIEF L3 readiness")
    _ = parser.add_argument("--root", default=".", help="Project root path")
    _ = parser.add_argument("--base-dir", default="AIEF", help="AIEF base directory under root")
    args = parser.parse_args()

    root = Path(cast(str, args.root)).resolve()
    base_dir = cast(str, args.base_dir).strip()
    aief_root = root / base_dir if base_dir else root

    checks: list[tuple[bool, str]] = []

    required_files = [
        "AGENTS.md",
        "context/INDEX.md",
        "context/tech/REPO_SNAPSHOT.md",
        "workflow/INDEX.md",
        "docs/standards/INDEX.md",
        "docs/standards/agent-spec.md",
        "docs/standards/command-spec.md",
        "docs/standards/skill-spec.md",
        "docs/standards/patterns/INDEX.md",
        "docs/standards/patterns/phase-routing.md",
        "docs/standards/patterns/experience-management.md",
        "docs/standards/patterns/context-loading.md",
        "context/experience/INDEX.md",
    ]

    for rel_path in required_files:
        checks.append(check_exists(aief_root, rel_path))

    checks.append(check_contains(aief_root, "AGENTS.md", "L3", "AIEF level"))
    checks.append(check_contains(aief_root, "context/tech/REPO_SNAPSHOT.md", "Current: L3", "snapshot level"))
    checks.append(check_min_files(aief_root, "context/experience/lessons", "*.md", 1, "lessons"))
    checks.append(check_min_files(aief_root, "context/experience/summaries", "*.md", 1, "summaries"))

    all_ok = True
    for ok, message in checks:
        print(message)
        if not ok:
            all_ok = False

    if all_ok:
        print("PASS AIEF L3 checks")
        return 0

    print("FAIL AIEF L3 checks")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
