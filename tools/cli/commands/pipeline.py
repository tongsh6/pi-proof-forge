"""单次四阶段 pipeline 命令：解析参数 → 调用 pipeline 编排。"""

from __future__ import annotations

import argparse
import datetime
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from tools.orchestration.pipeline import PipelineFlowConfig, run_pipeline_flow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run end-to-end PiProofForge pipeline")
    _ = parser.add_argument("--raw", required=True, help="Raw material input path")
    _ = parser.add_argument("--job-profile", required=True, help="Job profile yaml path")
    _ = parser.add_argument(
        "--evidence-dir",
        default="evidence_cards",
        help="Evidence cards directory for this run",
    )
    _ = parser.add_argument("--run-id", help="Run id, default timestamp")
    _ = parser.add_argument("--personal-profile", default="personal_profile.yaml", help="个人资料 YAML")
    _ = parser.add_argument(
        "--resume-positioning",
        default="technical_depth",
        choices=("technical_depth", "delivery_owner", "custom"),
    )
    _ = parser.add_argument("--custom-positioning", default="")
    _ = parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable LLM for extraction/matching/generation/evaluation",
    )
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if any LLM step is unavailable"
    )
    _ = parser.add_argument(
        "--skip-evidence-extraction",
        action="store_true",
        help="Use the supplied evidence directory as-is instead of extracting a new card",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    run_id = cast(str | None, args.run_id) or datetime.datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )
    config = PipelineFlowConfig(
        raw_path=Path(cast(str, args.raw)),
        job_profile_path=Path(cast(str, args.job_profile)),
        evidence_dir=Path(cast(str, args.evidence_dir)),
        run_id=run_id,
        personal_profile_path=Path(cast(str, args.personal_profile)),
        resume_positioning=cast(str, args.resume_positioning),
        custom_positioning=cast(str, args.custom_positioning),
        use_llm=cast(bool, args.use_llm),
        require_llm=cast(bool, args.require_llm),
        skip_evidence_extraction=cast(bool, args.skip_evidence_extraction),
    )
    return run_pipeline_flow(config)


if __name__ == "__main__":
    raise SystemExit(main())
