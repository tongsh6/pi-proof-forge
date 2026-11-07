"""简历生成命令：解析参数 → 调用生成编排。"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from tools.infra.llm.client import default_base_url
from tools.orchestration.generation_flow import (
    DEFAULT_PROMPT_PATH,
    GenerationFlowConfig,
    run_generation_flow,
)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run resume generation workflow")
    _ = parser.add_argument("--matching-report", required=True, help="Matching report path")
    _ = parser.add_argument("--output-dir", required=True, help="Output directory")
    _ = parser.add_argument(
        "--personal-profile", default="personal_profile.yaml", help="个人资料 YAML"
    )
    _ = parser.add_argument("--job-profile", default="", help="目标岗位 YAML")
    _ = parser.add_argument(
        "--resume-positioning",
        default="technical_depth",
        choices=("technical_depth", "delivery_owner", "custom"),
    )
    _ = parser.add_argument("--custom-positioning", default="", help="自定义求职方向")
    _ = parser.add_argument("--use-llm", action="store_true", help="Use LLM for generation")
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if LLM path is unavailable"
    )
    _ = parser.add_argument("--prompt", default=DEFAULT_PROMPT_PATH, help="Prompt template path")
    _ = parser.add_argument(
        "--evidence-dir", default="evidence_cards", help="Evidence cards directory"
    )
    _ = parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Model name")
    _ = parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "") or default_base_url(fallback=_DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL",
    )
    _ = parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    job_profile = cast(str, args.job_profile)
    config = GenerationFlowConfig(
        matching_report_path=Path(cast(str, args.matching_report)),
        output_dir=Path(cast(str, args.output_dir)),
        personal_profile_path=Path(cast(str, args.personal_profile)),
        evidence_dir=Path(cast(str, args.evidence_dir)),
        job_profile_path=Path(job_profile) if job_profile else None,
        resume_positioning=cast(str, args.resume_positioning),
        custom_positioning=cast(str, args.custom_positioning),
        use_llm=cast(bool, args.use_llm),
        require_llm=cast(bool, args.require_llm),
        prompt_path=cast(str, args.prompt),
        model=cast(str, args.model),
        base_url=cast(str, args.base_url),
        api_key=cast(str, args.api_key),
    )
    return run_generation_flow(config)


if __name__ == "__main__":
    raise SystemExit(main())
