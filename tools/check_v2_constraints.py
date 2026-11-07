#!/usr/bin/env python3
"""v2 架构静态约束检查。

设计目标（openspec/specs/pi-proof-forge-core.md「统一核心引擎架构规范」）：
- 分层依赖单向向内：cli → orchestration → engines → domain ← infra；
- 引擎是唯一业务实现，入口层不重复实现；
- 禁止 legacy 双路由与外部命令串联；
- LLM/YAML 等基础能力各有唯一实现。

本脚本只做静态文本/导入检查，不执行被检查代码。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# 每层允许依赖的 tools 一级包（未列出的即视为越层依赖）。
# - infra 是唯一外部 IO/存储适配层，可依赖 policy/prompts/submission 等基础包；
# - engines 可依赖 infra/config/errors/prompts/policy；
# - orchestration 可依赖 engines/infra/channels 等，但不得依赖 cli/sidecar/acceptance；
# - cli 只做参数解析与调用编排，不得依赖 sidecar/acceptance；
# - sidecar 作为应用适配层可依赖 cli（CLI 入口复用），但不得依赖验收工具。
LAYER_DEPENDENCIES: dict[str, set[str]] = {
    "domain": {"domain"},
    "infra": {"domain", "infra", "policy", "prompts", "submission"},
    "engines": {"domain", "infra", "engines", "config", "errors", "prompts", "policy"},
    "orchestration": {
        "domain",
        "infra",
        "engines",
        "orchestration",
        "config",
        "errors",
        "prompts",
        "policy",
        "channels",
    },
    "cli": {
        "domain",
        "infra",
        "engines",
        "orchestration",
        "cli",
        "config",
        "errors",
        "policy",
        "prompts",
    },
    "sidecar": {
        "domain",
        "infra",
        "engines",
        "orchestration",
        "cli",
        "config",
        "errors",
        "policy",
        "prompts",
        "channels",
        "submission",
        "sidecar",
    },
    "policy": {"domain", "infra", "policy", "prompts"},
    "config": {"domain", "infra", "config", "errors", "policy"},
    "channels": {"domain", "channels", "submission", "infra", "engines"},
    "errors": {"domain", "errors"},
    "prompts": {"prompts", "domain", "infra"},
}

# 已退役的 legacy 入口与双路由开关：不得重新出现。
FORBIDDEN_LEGACY_PATTERNS: tuple[str, ...] = (
    "PPF_FORCE_LEGACY_MAIN",
    "run_legacy_main",
    "from tools.run_pipeline",
    "from tools.run_generation",
    "from tools.run_evaluation",
    "from tools.run_matching_scoring",
    "from tools.run_evidence_extraction",
    "from tools.run_agent",
    "import tools.run_pipeline",
    "import tools.run_generation",
    "import tools.run_evaluation",
    "import tools.run_matching_scoring",
    "import tools.run_evidence_extraction",
    "import tools.run_agent",
)
# 禁止重新放回 tools 根目录的历史脚本名。
FORBIDDEN_ROOT_SCRIPTS: tuple[str, ...] = (
    "run_pipeline.py",
    "run_agent.py",
    "run_generation.py",
    "run_evaluation.py",
    "run_matching_scoring.py",
    "run_evidence_extraction.py",
    "extract_evidence.py",
    "extract_evidence_llm.py",
)
# 允许出现在 tools 根目录的运维/检查脚本模式。
ROOT_SCRIPT_ALLOWED = re.compile(
    r"^(check_|run_gitflow_release|run_github_publish|setup_liepin_session|kb\.py)"
)

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(tools\.[\w.]+)", re.MULTILINE)


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


def check_single_implementations(root: Path, failures: list[str]) -> None:
    infra_files = collect_py_files(root / "tools" / "infra")
    tools_files = collect_py_files(root / "tools")

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


def check_business_layers(root: Path, failures: list[str]) -> None:
    business_files = (
        collect_py_files(root / "tools" / "domain")
        + collect_py_files(root / "tools" / "engines")
        + collect_py_files(root / "tools" / "orchestration")
        + collect_py_files(root / "tools" / "config")
        + collect_py_files(root / "tools" / "channels")
    )
    subprocess_hits = find_pattern(business_files, "subprocess")
    if subprocess_hits:
        failures.append(
            "Business-layer subprocess usage found in: "
            + ", ".join(sorted(str(p.relative_to(root)) for p in subprocess_hits))
        )

    engines_files = collect_py_files(root / "tools" / "engines")
    use_llm_hits = find_pattern(engines_files, "if use_llm")
    if use_llm_hits:
        failures.append(
            "if use_llm found in engines layer: "
            + ", ".join(sorted(str(p.relative_to(root)) for p in use_llm_hits))
        )
    orchestration_files = collect_py_files(root / "tools" / "orchestration")
    argparse_hits = find_pattern(orchestration_files, "import argparse")
    if argparse_hits:
        failures.append(
            "argparse found in orchestration layer (参数解析属于 cli): "
            + ", ".join(sorted(str(p.relative_to(root)) for p in argparse_hits))
        )


def check_layer_dependencies(root: Path, failures: list[str]) -> None:
    for layer, allowed in LAYER_DEPENDENCIES.items():
        base = root / "tools" / layer
        if not base.is_dir():
            continue
        for file in collect_py_files(base):
            text = file.read_text(encoding="utf-8")
            for match in _IMPORT_RE.finditer(text):
                parts = match.group(1).split(".")
                if len(parts) < 2:
                    continue
                target = parts[1]
                if target in allowed:
                    continue
                failures.append(
                    f"Layer dependency violation: {file.relative_to(root)} imports "
                    f"{match.group(1)} (layer {layer} may not depend on {target})"
                )


def check_legacy_entries(root: Path, failures: list[str]) -> None:
    tools_files = [
        p
        for p in collect_py_files(root / "tools")
        if p.name != "check_v2_constraints.py"
    ]
    for pattern in FORBIDDEN_LEGACY_PATTERNS:
        hits = find_pattern(tools_files, pattern)
        if hits:
            failures.append(
                f"Legacy entrypoint pattern {pattern!r} found in: "
                + ", ".join(sorted(str(p.relative_to(root)) for p in hits))
            )
    root_dir = root / "tools"
    for name in FORBIDDEN_ROOT_SCRIPTS:
        if (root_dir / name).exists():
            failures.append(f"Forbidden legacy root script: tools/{name}")
    for file in sorted(root_dir.glob("*.py")):
        if file.name in {"__init__.py"} or ROOT_SCRIPT_ALLOWED.match(file.name):
            continue
        text = file.read_text(encoding="utf-8")
        if "argparse" in text and ("tools.engines" in text or "tools.orchestration" in text):
            failures.append(
                f"Business pipeline script must live in cli/orchestration, found: {file.relative_to(root)}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check v2 architecture static constraints")
    _ = parser.add_argument("--root", default=".", help="Repository root path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    failures: list[str] = []
    check_single_implementations(root, failures)
    check_business_layers(root, failures)
    check_layer_dependencies(root, failures)
    check_legacy_entries(root, failures)

    if failures:
        print("FAIL v2 constraints")
        for item in failures:
            print(f"- {item}")
        return 1

    print("PASS v2 constraints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
