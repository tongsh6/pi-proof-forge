#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.infra.llm.client import (
    LLMClient,
    STRATA_UNIFIED_BASE_URL,
    llm_request_available,
    llm_timeout_from_env,
    provider_is_keyless,
)


DEFAULT_BASE_URL = "https://api.openai.com/v1"


def read_text(path: str) -> str:
    if path == "-":
        return Path("/dev/stdin").read_text(encoding="utf-8")
    return Path(path).read_text(encoding="utf-8")


def load_prompt_template(template_path: str, raw_material: str) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    return template.replace("<RAW_MATERIAL>", raw_material)


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-based evidence extraction")
    _ = parser.add_argument(
        "--input", required=True, help="Raw material path or '-' for stdin"
    )
    _ = parser.add_argument(
        "--prompt",
        default="tools/prompts/evidence-extraction.md",
        help="Prompt template path",
    )
    _ = parser.add_argument(
        "--model", default=os.getenv("LLM_MODEL", ""), help="Model name"
    )
    _ = parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", ""),
        help="OpenAI-compatible base URL",
    )
    _ = parser.add_argument(
        "--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key"
    )
    _ = parser.add_argument("--output", help="Output YAML path (optional)")
    args = parser.parse_args()

    model = cast(str, args.model)
    base_url = cast(str, args.base_url).strip()
    api_key = cast(str, args.api_key)
    prompt_path = cast(str, args.prompt)
    input_path = cast(str, args.input)
    output_path = cast(str | None, args.output)
    provider = os.getenv("LLM_PROVIDER", "")

    if not model:
        print("Missing model. Set --model or LLM_MODEL.", file=sys.stderr)
        return 1
    if not llm_request_available(provider=provider, api_key=api_key, model=model):
        print("Missing API key. Set --api-key or LLM_API_KEY.", file=sys.stderr)
        return 1
    if not base_url:
        if provider.strip().lower() == "strata":
            # Strata App 管理的统一推理后台有唯一固定入口，无需逐次配置地址。
            base_url = STRATA_UNIFIED_BASE_URL
        elif provider_is_keyless(provider):
            # keyless 本地 provider 缺少地址时不能悄悄落到 OpenAI 默认地址。
            print(
                "Missing base URL for keyless local provider. Set --base-url or LLM_BASE_URL.",
                file=sys.stderr,
            )
            return 1
        else:
            base_url = DEFAULT_BASE_URL

    raw_text = read_text(input_path)
    prompt = load_prompt_template(prompt_path, raw_text)

    payload: dict[str, object] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是证据提炼器，必须严格遵循提示词格式输出，不得编造事实。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    client = LLMClient(
        base_url=base_url,
        api_key=api_key,
        timeout=llm_timeout_from_env(),
        provider=provider,
    )
    response = client.post_json(client.chat_completions_url, payload)
    content = client.extract_content(response)
    if not content:
        print("Empty response content.", file=sys.stderr)
        return 1

    if output_path:
        _ = Path(output_path).write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
