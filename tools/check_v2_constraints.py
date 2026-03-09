#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def collect_py_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if p.is_file()]


def count_definitions(files: list[Path], signature: str) -> int:
    count = 0
    for file in files:
        text = file.read_text(encoding="utf-8")
        count += text.count(signature)
    return count


def find_pattern(files: list[Path], pattern: str) -> list[Path]:
    hits: list[Path] = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        if pattern in text:
            hits.append(file)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check v2 architecture static constraints"
    )
    _ = parser.add_argument("--root", default=".", help="Repository root path")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    infra_files = collect_py_files(root / "tools" / "infra")
    engines_files = collect_py_files(root / "tools" / "engines")
    tools_files = collect_py_files(root / "tools")
    business_files = (
        collect_py_files(root / "tools" / "domain")
        + collect_py_files(root / "tools" / "engines")
        + collect_py_files(root / "tools" / "orchestration")
        + collect_py_files(root / "tools" / "config")
        + collect_py_files(root / "tools" / "channels")
    )

    failures: list[str] = []

    post_json_defs = count_definitions(infra_files, "def post_json(")
    extract_content_defs = count_definitions(infra_files, "def extract_content(")
    parse_yaml_defs = count_definitions(infra_files, "def parse_simple_yaml(")

    if post_json_defs != 1:
        failures.append(
            f"Expected exactly 1 def post_json in tools/infra, found {post_json_defs}"
        )
    if extract_content_defs != 1:
        failures.append(
            f"Expected exactly 1 def extract_content in tools/infra, found {extract_content_defs}"
        )
    if parse_yaml_defs != 1:
        failures.append(
            f"Expected exactly 1 def parse_simple_yaml in tools/infra, found {parse_yaml_defs}"
        )

    non_infra_tools = [
        p
        for p in tools_files
        if "tools/infra/" not in p.as_posix()
        and not p.name.startswith("check_v2_constraints")
    ]
    duplicate_llm_defs = count_definitions(
        non_infra_tools, "def post_json("
    ) + count_definitions(non_infra_tools, "def extract_content(")
    duplicate_yaml_defs = count_definitions(non_infra_tools, "def parse_simple_yaml(")
    if duplicate_llm_defs != 0:
        failures.append(
            f"Duplicate LLM client helper defs outside tools/infra found: {duplicate_llm_defs}"
        )
    if duplicate_yaml_defs != 0:
        failures.append(
            f"Duplicate YAML parser defs outside tools/infra found: {duplicate_yaml_defs}"
        )

    subprocess_hits = find_pattern(business_files, "subprocess")
    if subprocess_hits:
        failures.append(
            "Business-layer subprocess usage found in: "
            + ", ".join(sorted(str(p.relative_to(root)) for p in subprocess_hits))
        )

    use_llm_hits = find_pattern(engines_files, "if use_llm")
    if use_llm_hits:
        failures.append(
            "if use_llm found in engines layer: "
            + ", ".join(sorted(str(p.relative_to(root)) for p in use_llm_hits))
        )

    if failures:
        print("FAIL v2 constraints")
        for item in failures:
            print(f"- {item}")
        return 1

    print("PASS v2 constraints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
