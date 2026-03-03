#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
from collections.abc import Mapping
from http.client import HTTPResponse
from pathlib import Path
from typing import TypedDict, cast
from urllib import request


DEFAULT_BASE_URL = "https://api.openai.com/v1"


class ParsedDoc(TypedDict):
    scalars: dict[str, str]
    lists: dict[str, list[str]]


class CardView(TypedDict):
    id: str
    title: str
    time_range: str
    context: str
    role_scope: str
    actions: list[str]
    results: list[str]
    stack: list[str]
    artifacts: list[str]


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def unquote(value: str) -> str:
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value


def parse_simple_yaml(text: str) -> ParsedDoc:
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list_key: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        list_match = re.match(r"^\s*-\s*(.+)$", line)
        if list_match and current_list_key is not None:
            value = unquote(list_match.group(1).strip())
            lists[current_list_key].append(value)
            continue

        key_list_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*$", line)
        if key_list_match:
            key = key_list_match.group(1)
            current_list_key = key
            lists[key] = []
            continue

        key_scalar_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.+)$", line)
        if key_scalar_match:
            key = key_scalar_match.group(1)
            value = unquote(key_scalar_match.group(2).strip())
            scalars[key] = value
            current_list_key = None

    return {"scalars": scalars, "lists": lists}


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


def load_prompt(template_path: str, report_text: str, evidence_text: str, version: str) -> str:
    template = read_text(template_path)
    content = template.replace("<MATCHING_REPORT>", report_text)
    content = content.replace("<EVIDENCE_CARDS>", evidence_text)
    return content.replace("{{A|B}}", version)


def extract_score_total(report_text: str) -> int:
    match = re.search(r"^score_total:\s*(\d+)", report_text, re.MULTILINE)
    if match:
        return int(match.group(1))
    return 0


def extract_top_card_ids(report_text: str) -> list[str]:
    top_ids = cast(list[str], re.findall(r"^\s*-\s*id:\s*\"?([^\"\n]+)\"?\s*$", report_text, re.MULTILINE))
    if top_ids:
        return top_ids[:3]
    fallback_ids = cast(list[str], re.findall(r"^\s*-\s*\"?(ec-[^\"\n]+)\"?\s*$", report_text, re.MULTILINE))
    unique: list[str] = []
    for card_id in fallback_ids:
        if card_id not in unique:
            unique.append(card_id)
    return unique[:3]


def load_cards(evidence_dir: Path, card_ids: list[str]) -> list[CardView]:
    card_map: dict[str, CardView] = {}
    for file_path in sorted(evidence_dir.glob("*.yaml")):
        doc = parse_simple_yaml(read_text(str(file_path)))
        card_id = file_path.stem
        card_map[card_id] = {
            "id": card_id,
            "title": doc["scalars"].get("title", card_id),
            "time_range": doc["scalars"].get("time_range", ""),
            "context": doc["scalars"].get("context", ""),
            "role_scope": doc["scalars"].get("role_scope", ""),
            "actions": doc["lists"].get("actions", []),
            "results": doc["lists"].get("results", []),
            "stack": doc["lists"].get("stack", []),
            "artifacts": doc["lists"].get("artifacts", []),
        }

    cards: list[CardView] = []
    for card_id in card_ids:
        if card_id in card_map:
            cards.append(card_map[card_id])
    if not cards:
        cards = list(card_map.values())[:3]
    return cards


def unique_stack(cards: list[CardView], limit: int = 8) -> list[str]:
    values: list[str] = []
    for card in cards:
        for item in card["stack"]:
            if item not in values:
                values.append(item)
            if len(values) >= limit:
                return values
    return values


def pick_action(card: CardView, version: str) -> str:
    if not card["actions"]:
        return ""
    if version == "A":
        preferred = ["架构", "重构", "链路", "一致性", "性能", "稳定性", "扩展"]
    else:
        preferred = ["推进", "治理", "协作", "交付", "灰度", "回滚", "owner", "负责人"]
    for action in card["actions"]:
        lower = action.lower()
        if any(token.lower() in lower for token in preferred):
            return action
    return card["actions"][0]


def build_template_resume(version: str, report_id: str, score_total: int, now: str, cards: list[CardView]) -> str:
    if version == "A":
        position = "Backend Tech Lead（架构/技术深度）"
    else:
        position = "Backend Tech Lead（交付治理/Owner）"

    stacks = unique_stack(cards)
    stack_line = ", ".join(stacks) if stacks else "n/a"

    lines: list[str] = [
        f"# Resume Version {version}",
        f"Generated at: {now}",
        f"Source report: {report_id}",
        "",
        "## 10-Second Summary",
        f"- 定位：{position}",
        f"- 匹配得分：{score_total}/100",
        f"- 核心技术栈：{stack_line}",
        "",
        "## Highlights",
    ]

    for card in cards[:3]:
        result = card["results"][0] if card["results"] else "结果待补充"
        action = pick_action(card, version)
        context = card["context"]
        lines.append(f"- {result}；在{context}场景下通过{action}达成。")

    lines.extend(["", "## Experience"])
    for card in cards:
        lines.append(f"### {card['title']}（{card['time_range']}）")
        lines.append(f"- 角色与范围：{card['role_scope']}")
        lines.append(f"- 场景约束：{card['context']}")
        actions = card["actions"][:2]
        if actions:
            lines.append(f"- 关键动作：{'；'.join(actions)}")
        results = card["results"][:2]
        if results:
            lines.append(f"- 结果：{'；'.join(results)}")
        if card["stack"]:
            lines.append(f"- 技术栈：{', '.join(card['stack'][:6])}")
        if card["artifacts"]:
            lines.append(f"- 证据：{', '.join(card['artifacts'][:2])}")
        lines.append("")

    lines.append("## Projects")
    for card in cards[:3]:
        challenge = card["context"] if card["context"] else "挑战待补充"
        action = pick_action(card, version)
        result = card["results"][0] if card["results"] else "结果待补充"
        lines.append(f"- {card['title']}：挑战={challenge}；动作={action}；结果={result}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run resume generation workflow")
    _ = parser.add_argument("--matching-report", required=True, help="Matching report path")
    _ = parser.add_argument("--output-dir", required=True, help="Output directory")
    _ = parser.add_argument("--use-llm", action="store_true", help="Use LLM for generation")
    _ = parser.add_argument("--require-llm", action="store_true", help="Fail if LLM path is unavailable")
    _ = parser.add_argument("--prompt", default="tools/prompts/generation.md", help="Prompt template path")
    _ = parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Model name")
    _ = parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL), help="OpenAI-compatible base URL")
    _ = parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key")
    args = parser.parse_args()

    report_path = cast(str, args.matching_report)
    output_dir_arg = cast(str, args.output_dir)
    prompt_path = cast(str, args.prompt)
    model = cast(str, args.model)
    base_url = cast(str, args.base_url)
    api_key = cast(str, args.api_key)
    use_llm = cast(bool, args.use_llm)
    require_llm = cast(bool, args.require_llm)

    if require_llm and not use_llm:
        print("--require-llm requires --use-llm")
        return 1

    report_id = Path(report_path).stem
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    output_dir = Path(output_dir_arg)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_text = read_text(report_path)
    score_total = extract_score_total(report_text)
    top_card_ids = extract_top_card_ids(report_text)
    cards = load_cards(Path("evidence_cards"), top_card_ids)
    evidence_text = "\n\n".join([read_text(str(Path("evidence_cards") / f"{card['id']}.yaml")) for card in cards if (Path("evidence_cards") / f"{card['id']}.yaml").exists()])

    for version in ["A", "B"]:
        content = build_template_resume(version, report_id, score_total, now, cards)
        if use_llm:
            if not model or not api_key:
                if require_llm:
                    print("LLM mode required but model/api_key is missing")
                    return 1
            else:
                prompt = load_prompt(prompt_path, report_text, evidence_text, version)
                payload: dict[str, object] = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是简历生成器，必须按提示词输出 Markdown，不得编造事实。",
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
                llm_content = extract_content(response)
                if llm_content:
                    content = llm_content.strip() + "\n"
                elif require_llm:
                    print("LLM mode required but received empty response")
                    return 1

        output_path = output_dir / f"resume_{report_id}_{version}.md"
        _ = output_path.write_text(content, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
