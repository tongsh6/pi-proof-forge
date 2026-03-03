#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from collections.abc import Mapping
from http.client import HTTPResponse
from typing import cast
from urllib import request


DEFAULT_BASE_URL = "https://api.openai.com/v1"


def read_text(path: str) -> str:
    if path == "-":
        return Path("/dev/stdin").read_text(encoding="utf-8")
    return Path(path).read_text(encoding="utf-8")


def load_prompt_template(template_path: str, raw_material: str) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    return template.replace("<RAW_MATERIAL>", raw_material)


def post_json(url: str, headers: dict[str, str], payload: Mapping[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    response = cast(HTTPResponse, request.urlopen(req, timeout=120))
    try:
        body = response.read().decode("utf-8")
    finally:
        response.close()
    parsed = cast(object, json.loads(body))
    if isinstance(parsed, dict):
        return cast(dict[str, object], parsed)
    return {}


def extract_content(response: dict[str, object]) -> str:
    choices_obj = response.get("choices")
    if not isinstance(choices_obj, list) or not choices_obj:
        return ""
    choices = cast(list[object], choices_obj)
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    first_dict = cast(dict[str, object], first)
    message = first_dict.get("message")
    if not isinstance(message, dict):
        return ""
    message_dict = cast(dict[str, object], message)
    content = message_dict.get("content")
    if not isinstance(content, str):
        return ""
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-based evidence extraction")
    _ = parser.add_argument("--input", required=True, help="Raw material path or '-' for stdin")
    _ = parser.add_argument("--prompt", default="tools/prompts/evidence-extraction.md", help="Prompt template path")
    _ = parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Model name")
    _ = parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL), help="OpenAI-compatible base URL")
    _ = parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key")
    _ = parser.add_argument("--output", help="Output YAML path (optional)")
    args = parser.parse_args()

    model = cast(str, args.model)
    base_url = cast(str, args.base_url)
    api_key = cast(str, args.api_key)
    prompt_path = cast(str, args.prompt)
    input_path = cast(str, args.input)
    output_path = cast(str | None, args.output)

    if not model:
        print("Missing model. Set --model or LLM_MODEL.", file=sys.stderr)
        return 1
    if not api_key:
        print("Missing API key. Set --api-key or LLM_API_KEY.", file=sys.stderr)
        return 1

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
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = base_url.rstrip("/") + "/chat/completions"

    response = post_json(url, headers, payload)
    content = extract_content(response)
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
