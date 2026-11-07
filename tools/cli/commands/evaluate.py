"""质量评测命令：解析参数 → 调用评测编排。"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from tools.infra.llm.client import default_base_url
from tools.orchestration.evaluation_flow import (
    DEFAULT_PROMPT_PATH,
    EvaluationFlowConfig,
    run_evaluation_flow,
)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run evaluation workflow")
    _ = parser.add_argument("--input", required=True, help="Generated resume path")
    _ = parser.add_argument("--output", required=True, help="Scorecard output path")
    _ = parser.add_argument("--job-profile", help="Job profile path for keyword coverage")
    _ = parser.add_argument(
        "--use-llm", action="store_true", help="Use LLM for explanation layer"
    )
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if LLM explanation is unavailable"
    )
    _ = parser.add_argument("--prompt", default=DEFAULT_PROMPT_PATH, help="Prompt template path")
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
    job_profile = cast(str | None, args.job_profile)
    config = EvaluationFlowConfig(
        input_path=Path(cast(str, args.input)),
        output_path=Path(cast(str, args.output)),
        job_profile_path=Path(job_profile) if job_profile else None,
        use_llm=cast(bool, args.use_llm),
        require_llm=cast(bool, args.require_llm),
        prompt_path=cast(str, args.prompt),
        model=cast(str, args.model),
        base_url=cast(str, args.base_url),
        api_key=cast(str, args.api_key),
    )
    return run_evaluation_flow(config)


if __name__ == "__main__":
    raise SystemExit(main())
