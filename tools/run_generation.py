#!/usr/bin/env python3
import argparse
import datetime
import os
import re
from pathlib import Path
import sys
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import parse_simple_yaml


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


def load_prompt(
    template_path: str, report_text: str, evidence_text: str, version: str
) -> str:
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
    top_ids = cast(
        list[str],
        re.findall(r"^\s*-\s*id:\s*\"?([^\"\n]+)\"?\s*$", report_text, re.MULTILINE),
    )
    if top_ids:
        return top_ids[:3]
    fallback_ids = cast(
        list[str],
        re.findall(r"^\s*-\s*\"?(ec-[^\"\n]+)\"?\s*$", report_text, re.MULTILINE),
    )
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


def build_template_resume(
    version: str, report_id: str, score_total: int, now: str, cards: list[CardView]
) -> str:
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
        lines.append(
            f"- {card['title']}：挑战={challenge}；动作={action}；结果={result}"
        )

    return "\n".join(lines) + "\n"


def _legacy_main() -> int:
    parser = argparse.ArgumentParser(description="Run resume generation workflow")
    _ = parser.add_argument(
        "--matching-report", required=True, help="Matching report path"
    )
    _ = parser.add_argument("--output-dir", required=True, help="Output directory")
    _ = parser.add_argument(
        "--use-llm", action="store_true", help="Use LLM for generation"
    )
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if LLM path is unavailable"
    )
    _ = parser.add_argument(
        "--prompt", default="tools/prompts/generation.md", help="Prompt template path"
    )
    _ = parser.add_argument(
        "--model", default=os.getenv("LLM_MODEL", ""), help="Model name"
    )
    _ = parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL",
    )
    _ = parser.add_argument(
        "--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key"
    )
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
    evidence_text = "\n\n".join(
        [
            read_text(str(Path("evidence_cards") / f"{card['id']}.yaml"))
            for card in cards
            if (Path("evidence_cards") / f"{card['id']}.yaml").exists()
        ]
    )

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
                client = LLMClient(base_url=base_url, api_key=api_key, timeout=120)
                response = client.post_json(client.chat_completions_url, payload)
                llm_content = client.extract_content(response)
                if llm_content:
                    content = llm_content.strip() + "\n"
                elif require_llm:
                    print("LLM mode required but received empty response")
                    return 1

        output_path = output_dir / f"resume_{report_id}_{version}.md"
        _ = output_path.write_text(content, encoding="utf-8")

    return 0


def main() -> int:
    if os.getenv("PPF_FORCE_LEGACY_MAIN") == "1":
        return _legacy_main()

    from tools.cli.commands.generate import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
