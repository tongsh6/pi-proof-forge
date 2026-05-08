from __future__ import annotations

import argparse
import json
import uuid
from collections.abc import Sequence
from pathlib import Path

from tools.domain.models import EvidenceCard
from tools.engines.evidence.store import EvidenceStore
from tools.infra.persistence.yaml_io import parse_simple_yaml


def _load_job_profile(path: str) -> object | None:
    p = Path(path)
    if not p.exists():
        return None
    from tools.domain.models import JobProfile

    parsed = parse_simple_yaml(p.read_text(encoding="utf-8"))
    scalars = parsed.get("scalars", {})
    lists = parsed.get("lists", {})
    return JobProfile(
        id=scalars.get("id", p.stem),
        title=scalars.get("title", scalars.get("target_role", "")),
        keywords=tuple(lists.get("keywords", [])),
        level=scalars.get("level", "mid"),
        tone=scalars.get("tone", ""),
        must_have=tuple(lists.get("must_have", [])),
        nice_to_have=tuple(lists.get("nice_to_have", [])),
    )


def _load_evidence_cards(evidence_dir: str) -> Sequence[EvidenceCard]:
    store = EvidenceStore(evidence_dir)
    cards: list[EvidenceCard] = []
    for p in sorted(Path(evidence_dir).glob("ec-*.yaml")):
        card = store.get(p.stem)
        if card is not None and card.is_eligible():
            cards.append(card)
    return tuple(cards)


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
    _ = parser.add_argument(
        "--evidence-dir",
        default="evidence_cards",
        help="Directory containing evidence card YAML files",
    )
    _ = parser.add_argument(
        "--job-profile",
        default="",
        help="Path to job profile YAML (e.g. job_profiles/jp-2026-001.yaml)",
    )
    _ = parser.add_argument(
        "--full-pipeline",
        action="store_true",
        default=True,
        help="Use full pipeline (default). Use --no-full-pipeline for legacy simplified mode.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_id = args.run_id or f"run-{uuid.uuid4().hex[:8]}"

    from importlib import import_module

    composer_cls = getattr(import_module("tools.config.composer"), "Composer")
    file_run_store_cls = getattr(
        import_module("tools.infra.persistence.file_run_store"), "FileRunStore"
    )

    composer = composer_cls.from_policy_path(args.policy)
    store = file_run_store_cls(base_dir=args.output_dir)

    evidence_cards: Sequence[EvidenceCard] = ()
    job_profile = None

    if args.full_pipeline:
        evidence_cards = _load_evidence_cards(args.evidence_dir)
        if args.job_profile:
            job_profile = _load_job_profile(args.job_profile)
        if not evidence_cards:
            print(
                "[WARN] No eligible evidence cards found; falling back to simplified mode"
            )

    if evidence_cards and args.full_pipeline:
        loop = composer.build_agent_loop(
            run_id=run_id,
            dry_run=bool(args.dry_run),
            run_store=store,
            evidence_cards=evidence_cards,
            job_profile=job_profile,
        )
    else:
        agent_loop_cls = getattr(
            import_module("tools.orchestration.agent_loop"), "AgentLoop"
        )
        loop = agent_loop_cls(
            policy=composer.policy,
            run_id=run_id,
            dry_run=bool(args.dry_run),
            run_store=store,
        )

    result = loop.run()
    print(json.dumps(result.__dict__, ensure_ascii=False))
    return 0
