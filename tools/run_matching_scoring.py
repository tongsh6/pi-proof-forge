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


class ScoreItem(TypedDict):
    score: int
    reason: str


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


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


def unquote(value: str) -> str:
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value


def load_prompt(template_path: str, job_profile_text: str, evidence_text: str) -> str:
    template = read_text(template_path)
    content = template.replace("<JOB_PROFILE>", job_profile_text)
    return content.replace("<EVIDENCE_CARDS>", evidence_text)


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


def parse_end_month(time_range: str) -> tuple[int, int] | None:
    matches = cast(list[tuple[str, str]], re.findall(r"(20\d{2})[-/.](0[1-9]|1[0-2])", time_range))
    if not matches:
        return None
    year, month = matches[-1]
    return int(year), int(month)


def months_ago(year: int, month: int, now: datetime.datetime) -> int:
    return (now.year - year) * 12 + (now.month - month)


def contains_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def build_rule_report(job_profile_path: str, evidence_files: list[Path], output_path: str) -> str:
    now_dt = datetime.datetime.now().astimezone()
    now_iso = now_dt.isoformat(timespec="seconds")
    job_doc = parse_simple_yaml(read_text(job_profile_path))

    keywords = job_doc["lists"].get("keywords", [])
    seniority_signals = job_doc["lists"].get("seniority_signal", [])
    business_domain = job_doc["scalars"].get("business_domain", "")

    evidence_ids: list[str] = []
    card_docs: list[ParsedDoc] = []
    card_texts: list[str] = []
    latest_months_ago: int | None = None

    for card_file in evidence_files:
        card_doc = parse_simple_yaml(read_text(str(card_file)))
        evidence_ids.append(card_file.stem)
        card_docs.append(card_doc)
        text_parts: list[str] = []
        text_parts.extend(card_doc["scalars"].values())
        for items in card_doc["lists"].values():
            text_parts.extend(items)
        joined = "\n".join(text_parts)
        card_texts.append(joined)

        time_range = card_doc["scalars"].get("time_range", "")
        end_month = parse_end_month(time_range)
        if end_month is not None:
            diff = months_ago(end_month[0], end_month[1], now_dt)
            latest_months_ago = diff if latest_months_ago is None else min(latest_months_ago, diff)

    all_text = "\n\n".join(card_texts)

    covered_keywords = [kw for kw in keywords if kw.lower() in all_text.lower()]
    missing_keywords = [kw for kw in keywords if kw.lower() not in all_text.lower()]
    keyword_cov = (len(covered_keywords) / len(keywords)) if keywords else 0.0
    k_score = int(round(keyword_cov * 25))

    domain_signals_map: dict[str, list[str]] = {
        "电商": ["订单", "库存", "大促", "支付", "促销", "店铺"],
        "零售": ["门店", "库存", "促销", "会员"],
        "金融": ["风控", "交易", "清算", "合规"],
    }
    domain_signals = domain_signals_map.get(business_domain, [business_domain] if business_domain else [])
    domain_hit_count = sum(1 for token in domain_signals if token and token in all_text)
    domain_ratio = (domain_hit_count / len(domain_signals)) if domain_signals else 0.0
    d_score = int(round(domain_ratio * 15)) if business_domain else 8

    seniority_hits = 0
    for signal in seniority_signals:
        if "owner" in signal.lower() and contains_any(all_text, ["owner", "负责人"]):
            seniority_hits += 1
        elif "跨团队" in signal and contains_any(all_text, ["跨团队", "协作", "推进"]):
            seniority_hits += 1
        elif "带人" in signal and contains_any(all_text, ["带人", "管理", "mentor"]):
            seniority_hits += 1
        elif "决策" in signal and contains_any(all_text, ["决策", "取舍", "方案"]):
            seniority_hits += 1
    seniority_ratio = (seniority_hits / len(seniority_signals)) if seniority_signals else 0.0
    s_score = int(round(seniority_ratio * 15)) if seniority_signals else 8

    numeric_results_count = 0
    artifact_count = 0
    for doc in card_docs:
        results = doc["lists"].get("results", [])
        artifacts = doc["lists"].get("artifacts", [])
        numeric_results_count += sum(1 for item in results if re.search(r"\d", item))
        artifact_count += len(artifacts)

    q_score = min(20, numeric_results_count * 5)
    e_score = min(15, artifact_count * 3)

    if latest_months_ago is None:
        r_score = 4
    elif latest_months_ago <= 6:
        r_score = 10
    elif latest_months_ago <= 12:
        r_score = 8
    elif latest_months_ago <= 18:
        r_score = 6
    elif latest_months_ago <= 24:
        r_score = 4
    else:
        r_score = 2

    score_breakdown: dict[str, ScoreItem] = {
        "K": {"score": k_score, "reason": f"关键词覆盖 {len(covered_keywords)}/{len(keywords) if keywords else 0}"},
        "D": {"score": d_score, "reason": f"业务域信号命中 {domain_hit_count}/{len(domain_signals) if domain_signals else 0}"},
        "S": {"score": s_score, "reason": f"级别信号命中 {seniority_hits}/{len(seniority_signals) if seniority_signals else 0}"},
        "Q": {"score": q_score, "reason": f"量化结果条数 {numeric_results_count}"},
        "E": {"score": e_score, "reason": f"证据附件条数 {artifact_count}"},
        "R": {"score": r_score, "reason": f"最近经历距今 {latest_months_ago if latest_months_ago is not None else 'unknown'} 月"},
    }
    total_score = sum(item["score"] for item in score_breakdown.values())

    card_rank: list[tuple[str, int, str]] = []
    for idx, doc in enumerate(card_docs):
        card_id = evidence_ids[idx]
        card_text = card_texts[idx]
        card_keyword_hits = sum(1 for kw in keywords if kw.lower() in card_text.lower())
        card_numeric = sum(1 for item in doc["lists"].get("results", []) if re.search(r"\d", item))
        card_artifacts = len(doc["lists"].get("artifacts", []))
        role_scope = doc["scalars"].get("role_scope", "")
        role_bonus = 2 if contains_any(role_scope, ["Owner", "Tech Lead", "负责人"]) else 0
        card_score = card_keyword_hits * 3 + card_numeric * 2 + min(3, card_artifacts) + role_bonus
        card_reason = f"关键词命中 {card_keyword_hits}，量化 {card_numeric}，证据 {card_artifacts}"
        card_rank.append((card_id, card_score, card_reason))

    card_rank.sort(key=lambda x: x[1], reverse=True)
    top_cards = card_rank[:3]

    gaps: list[str] = []
    gap_tasks: list[str] = []
    if missing_keywords:
        gaps.append("缺少关键词覆盖: " + ", ".join(missing_keywords[:5]))
        gap_tasks.append("补充包含缺失关键词的经历卡或证据")
    if q_score < 10:
        gaps.append("量化结果不足")
        gap_tasks.append("为关键经历补充可量化结果（时延/成功率/成本）")
    if e_score < 9:
        gaps.append("证据附件不足")
        gap_tasks.append("补充 PR、监控截图、复盘文档等 artifacts")
    if s_score < 8:
        gaps.append("级别信号不足")
        gap_tasks.append("补充 Owner、跨团队推进或决策类证据")
    if d_score < 7:
        gaps.append("业务域信号偏弱")
        gap_tasks.append("补充与目标业务域直接相关的经历表述")

    if not gaps:
        gaps.append("暂无明显缺口")
        gap_tasks.append("保持当前证据完整度，按新 JD 微调关键词")

    version_id = Path(output_path).stem

    lines = [
        f"job_profile_id: \"{Path(job_profile_path).stem}\"",
        "evidence_card_ids:",
    ]
    for evidence_id in evidence_ids:
        lines.append(f"  - \"{evidence_id}\"")

    lines.append(f"score_total: {total_score}")
    lines.append("score_breakdown:")
    for key in ["K", "D", "S", "Q", "E", "R"]:
        item = score_breakdown[key]
        lines.append(f"  {key}: {{ score: {item['score']}, reason: \"{item['reason']}\" }}")

    lines.append("top_cards:")
    for card_id, _score, reason in top_cards:
        lines.append(f"  - id: \"{card_id}\"")
        lines.append(f"    reason: \"{reason}\"")

    lines.append("gaps:")
    for gap in gaps:
        lines.append(f"  - \"{gap}\"")

    lines.append("gap_tasks:")
    for task in gap_tasks:
        lines.append(f"  - \"{task}\"")

    lines.append(f"generated_at: \"{now_iso}\"")
    lines.append(f"version_id: \"{version_id}\"")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run matching & scoring workflow")
    _ = parser.add_argument("--job-profile", required=True, help="Job profile path")
    _ = parser.add_argument("--evidence-dir", required=True, help="Evidence cards directory")
    _ = parser.add_argument("--output", required=True, help="Matching report output path")
    _ = parser.add_argument("--use-llm", action="store_true", help="Use LLM for scoring")
    _ = parser.add_argument("--require-llm", action="store_true", help="Fail if LLM path is unavailable")
    _ = parser.add_argument("--prompt", default="tools/prompts/matching-scoring.md", help="Prompt template path")
    _ = parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Model name")
    _ = parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL), help="OpenAI-compatible base URL")
    _ = parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key")
    args = parser.parse_args()

    evidence_dir = cast(str, args.evidence_dir)
    job_profile = cast(str, args.job_profile)
    output_path = cast(str, args.output)
    prompt_path = cast(str, args.prompt)
    model = cast(str, args.model)
    base_url = cast(str, args.base_url)
    api_key = cast(str, args.api_key)
    use_llm = cast(bool, args.use_llm)
    require_llm = cast(bool, args.require_llm)

    if require_llm and not use_llm:
        print("--require-llm requires --use-llm")
        return 1

    evidence_files = sorted(Path(evidence_dir).glob("*.yaml"))
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if use_llm:
        if not model or not api_key:
            if require_llm:
                print("LLM mode required but model/api_key is missing")
                return 1
        else:
            job_profile_text = read_text(job_profile)
            evidence_text = "\n\n".join([read_text(str(p)) for p in evidence_files])
            prompt = load_prompt(prompt_path, job_profile_text, evidence_text)
            payload: dict[str, object] = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是匹配评分引擎，必须按提示词格式输出 YAML，不得编造事实。",
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
            if content:
                _ = output_file.write_text(content, encoding="utf-8")
                return 0
            if require_llm:
                print("LLM mode required but received empty response")
                return 1

    rule_report = build_rule_report(job_profile, evidence_files, output_path)
    _ = output_file.write_text(rule_report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
