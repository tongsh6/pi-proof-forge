from __future__ import annotations

import argparse
import json
from importlib import import_module
from collections.abc import Sequence
import uuid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run autonomous agent delivery loop")
    _ = parser.add_argument("--policy", required=True, help="Path to policy YAML")
    _ = parser.add_argument(
        "--run-id", default="", help="Run ID; auto generated if omitted"
    )
    _ = parser.add_argument(
        "--dry-run", action="store_true", help="Execute without delivery"
    )
    _ = parser.add_argument(
        "--output-dir",
        default="outputs/agent_runs",
        help="Directory for run logs and round snapshots",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_id = args.run_id or f"run-{uuid.uuid4().hex[:8]}"
    composer_cls = getattr(import_module("tools.config.composer"), "Composer")
    agent_loop_cls = getattr(
        import_module("tools.orchestration.agent_loop"), "AgentLoop"
    )
    file_run_store_cls = getattr(
        import_module("tools.infra.persistence.file_run_store"), "FileRunStore"
    )

    composer = composer_cls.from_policy_path(args.policy)
    store = file_run_store_cls(base_dir=args.output_dir)
    loop = agent_loop_cls(
        policy=composer.policy,
        run_id=run_id,
        dry_run=bool(args.dry_run),
        run_store=store,
    )
    result = loop.run()
    print(json.dumps(result.__dict__, ensure_ascii=False))
    return 0
