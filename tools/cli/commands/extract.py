"""证据提炼命令：规则模式与 LLM 模式共用同一入口。

- 规则模式：确定性抽取 Evidence Card 草稿并写 YAML。
- LLM 模式：调用统一 LLMClient 生成结构化卡文本；provider/base_url 安全规则
  由引擎层的 resolve_base_url 负责。

本命令只做参数解析、文件读写与退出码映射，不实现抽取规则。
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from tools.engines.evidence import llm_extractor, rule_extractor
from tools.infra.llm.client import (
    LLMClient,
    llm_request_available,
    llm_timeout_from_env,
)


def _read_text(input_path: str) -> str:
    if input_path == "-":
        return Path("/dev/stdin").read_text(encoding="utf-8")
    return Path(input_path).read_text(encoding="utf-8")


def _write_output(path: str | None, text: str) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def _run_rule(args: argparse.Namespace) -> int:
    input_path = cast(str, args.input)
    text = _read_text(input_path)
    card_id = cast(str | None, args.id) or datetime.datetime.now().strftime(
        "ec-%Y%m%d%H%M%S"
    )
    draft = rule_extractor.build_draft(
        text,
        card_id=card_id,
        title=cast(str | None, args.title) or "",
        raw_source=input_path,
    )
    gaps = rule_extractor.build_gaps(draft)
    _write_output(cast(str | None, args.output), rule_extractor.dump_yaml(draft, gaps))
    return 0


def _run_llm(args: argparse.Namespace) -> int:
    model = cast(str, args.model)
    api_key = cast(str, args.api_key)
    provider = os.getenv("LLM_PROVIDER", "")

    if not model:
        print("Missing model. Set --model or LLM_MODEL.", file=sys.stderr)
        return 1
    if not llm_request_available(provider=provider, api_key=api_key, model=model):
        print("Missing API key. Set --api-key or LLM_API_KEY.", file=sys.stderr)
        return 1
    try:
        base_url = llm_extractor.resolve_base_url(
            provider=provider, base_url=cast(str, args.base_url)
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    prompt = llm_extractor.load_prompt_template(
        cast(str, args.prompt), _read_text(cast(str, args.input))
    )
    client = LLMClient(
        base_url=base_url,
        api_key=api_key,
        timeout=llm_timeout_from_env(),
        provider=provider,
    )
    try:
        content = llm_extractor.extract_yaml_text(client, model=model, prompt=prompt)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _write_output(cast(str | None, args.output), content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract evidence card from raw material")
    _ = parser.add_argument("--input", required=True, help="Raw material path or '-' for stdin")
    _ = parser.add_argument("--output", help="Output YAML path (optional)")
    _ = parser.add_argument("--id", help="Evidence card id (optional)")
    _ = parser.add_argument("--title", help="Title override (optional)")
    _ = parser.add_argument("--use-llm", action="store_true", help="Use LLM extraction")
    _ = parser.add_argument(
        "--prompt",
        default="tools/prompts/evidence-extraction.md",
        help="Prompt template path (LLM mode)",
    )
    _ = parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Model name")
    _ = parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", ""), help="OpenAI-compatible base URL")
    _ = parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if cast(bool, args.use_llm):
        return _run_llm(args)
    return _run_rule(args)


if __name__ == "__main__":
    raise SystemExit(main())
