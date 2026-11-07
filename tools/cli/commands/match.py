"""匹配评分命令：解析参数 → 调用匹配编排。

参数与退出码语义：
- 0：规则报告或语义评审成功写出；
- 1：LLM 必需但不可用/失败；
- 2：岗位命中企业例外清单。
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from tools.engines.matching import rule_scorer
from tools.infra.llm.client import default_base_url
from tools.orchestration.matching_flow import MatchingFlowConfig, run_matching_flow

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run matching & scoring workflow")
    _ = parser.add_argument("--job-profile", required=True, help="Job profile path")
    _ = parser.add_argument(
        "--llm-max-cards",
        type=int,
        default=int(os.getenv("PPF_MATCH_LLM_MAX_CARDS") or rule_scorer.DEFAULT_LLM_MAX_CARDS),
        help="每批语义评审的卡数上限；全部证据均会分批评审",
    )
    _ = parser.add_argument(
        "--personal-profile", default="personal_profile.yaml", help="已确认职业档案"
    )
    _ = parser.add_argument("--evidence-dir", required=True, help="Evidence cards directory")
    _ = parser.add_argument("--output", required=True, help="Matching report output path")
    _ = parser.add_argument("--use-llm", action="store_true", help="Use LLM for scoring")
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if LLM path is unavailable"
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
    config = MatchingFlowConfig(
        job_profile_path=Path(cast(str, args.job_profile)),
        evidence_dir=Path(cast(str, args.evidence_dir)),
        output_path=Path(cast(str, args.output)),
        personal_profile_path=Path(cast(str, args.personal_profile)),
        use_llm=cast(bool, args.use_llm),
        require_llm=cast(bool, args.require_llm),
        model=cast(str, args.model),
        base_url=cast(str, args.base_url),
        api_key=cast(str, args.api_key),
        llm_max_cards=cast(int, args.llm_max_cards),
    )
    return run_matching_flow(config)


if __name__ == "__main__":
    raise SystemExit(main())
