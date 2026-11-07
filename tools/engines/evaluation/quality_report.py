"""四层质量报告：LLM 判项调度、缓存与 Markdown 呈现。

规则判项由 rule_evaluator 负责；本模块负责模型判项的运行/缓存/纠错、
四层报告 Markdown 渲染与投递建议呈现，不改变任何判项结论。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from tools.infra import quality_judge_cache
from tools.infra.llm.client import (
    LLMClient,
    llm_request_available,
    llm_timeout_from_env,
)
from tools.infra.persistence.yaml_io import parse_simple_yaml

from . import llm_judge, tiered_evaluator
from .rule_evaluator import read_text


_QUALITY_INPUT_KEYS = {
    "personal_profile",
    "matching_report",
    "semantic_matching",
    "job_profile",
    "job_description",
}


def _load_quality_cards(trace: dict) -> dict[str, dict]:
    """从生成 trace 的输入指纹中读取本次使用的证据卡（只读）。"""
    cards: dict[str, dict] = {}
    inputs = trace.get("inputs") if isinstance(trace, dict) else None
    if not isinstance(inputs, dict):
        return cards
    for key, meta in inputs.items():
        if key in _QUALITY_INPUT_KEYS or not isinstance(meta, dict):
            continue
        path = meta.get("path")
        if not isinstance(path, str) or not path.endswith(".yaml"):
            continue
        card_id = str(key).split("career_evidence:")[-1]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", card_id):
            continue
        try:
            doc = parse_simple_yaml(read_text(path))
        except (OSError, ValueError):
            continue
        cards[card_id] = {**doc["scalars"], **doc["lists"]}
    return cards


def _load_quality_career(trace: dict) -> dict:
    from tools.infra.career_profile import load_career_profile

    inputs = trace.get("inputs") if isinstance(trace, dict) else None
    meta = inputs.get("personal_profile") if isinstance(inputs, dict) else None
    path = meta.get("path") if isinstance(meta, dict) else None
    if isinstance(path, str) and Path(path).is_file():
        try:
            return load_career_profile(Path(path))
        except (OSError, ValueError):
            return {}
    return {}


def _judge_jd_items(semantic_review: dict | None) -> list[dict[str, str]]:
    if not isinstance(semantic_review, dict) or semantic_review.get("mode") != "semantic":
        return []
    items: list[dict[str, str]] = []
    for row in semantic_review.get("requirements") or []:
        if not isinstance(row, dict):
            continue
        requirement_id = str(row.get("requirement_id") or "")
        text = str(row.get("text") or "")
        if requirement_id and text:
            items.append({"id": requirement_id, "kind": str(row.get("kind", "must_have")), "text": text})
    return items


def _judge_cache_root() -> Path:
    override = os.getenv("PPF_QUALITY_JUDGE_CACHE_DIR", "").strip()
    return Path(override) if override else Path.cwd() / "app-data" / "quality_judgments"


def _run_quality_judge(
    *,
    resume_text: str,
    trace: dict,
    semantic_review: dict | None,
    job_profile_path: str | None,
    use_llm: bool,
    model: str,
    api_key: str,
    base_url: str,
    client_factory: Any = None,
) -> tuple[dict | None, dict[str, Any], dict[str, list[str]]]:
    """复用完整缓存；内容缺项最多纠错一次，不缓存未完成判项。"""
    resume_sha256 = hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
    decisions = quality_judge_cache.load_decisions(Path.cwd(), resume_sha256)
    cards = _load_quality_cards(trace)
    if isinstance(trace.get("claims"), list):
        rendered_ids = {str(claim.get("evidence_id", "")) for claim in trace["claims"] if isinstance(claim, dict)}
        cards = {key: card for key, card in cards.items() if key in rendered_ids}
    jd_items = _judge_jd_items(semantic_review)
    meta: dict[str, Any] = {"cache": "disabled", "reason": "llm_not_configured_or_no_jd_items"}
    llm_available = llm_request_available(
        provider=os.getenv("LLM_PROVIDER", ""), api_key=api_key, model=model
    )
    if not (use_llm and llm_available and jd_items):
        return None, meta, decisions
    bullets = tiered_evaluator.extract_bullets(resume_text)
    prompt = llm_judge.build_judge_prompt(bullets=bullets, cards=cards, jd_items=jd_items,
                                         resume_text=resume_text)
    job_profile_id = Path(job_profile_path).stem if job_profile_path else ""
    key = quality_judge_cache.judge_cache_key(
        resume_sha256=resume_sha256,
        job_profile_id=job_profile_id,
        cards=cards,
        model=model,
        prompt_version=llm_judge.PROMPT_VERSION,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )
    meta = {"cache": "miss", "model": model, "prompt_version": llm_judge.PROMPT_VERSION, "key": key}
    cached = quality_judge_cache.load_judgment(_judge_cache_root(), key)
    if cached is not None:
        meta["cache"] = "hit"
        meta["judged_sections"] = cached.get("judged_sections")
        return cached, meta, decisions
    try:
        client = client_factory() if client_factory is not None else LLMClient(
            base_url=base_url, api_key=api_key, timeout=llm_timeout_from_env(),
            provider=os.getenv("LLM_PROVIDER", ""),
        )
        payload: dict[str, object] = {
            "model": model,
            "temperature": 0,
            "max_tokens": 6000,
            "stream": False,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a strict judge. Return ONLY the JSON object."},
                {"role": "user", "content": prompt},
            ],
        }
        # 本机 LM Studio 的 Qwen reasoning 模型会把预算耗在 thinking 上，导致最终 content 为空；
        # 只对本机 base_url 关闭推理输出，不改变远端模型请求语义。
        if "127.0.0.1" in base_url or "localhost" in base_url:
            payload["reasoning_effort"] = "none"
        elif os.getenv("LLM_PROVIDER", "").strip().lower() == "deepseek":
            # 结构化判项不需要推理输出；DeepSeek thinking 会把 6000 输出预算全部耗在 reasoning 上。
            payload["thinking"] = {"type": "disabled"}
        meta.update(model_calls=0, repair_calls=0)
        parsed: dict | None = None
        merged: dict[str, Any] = {}
        all_sections = ("r1_4", "r2_1", "r3_1", "r3_5", "r4_1")
        requested = tuple(all_sections)
        for attempt in range(2):
            meta["model_calls"] += 1
            if attempt:
                payload = {**payload, "messages": [
                    payload["messages"][0],
                    {"role": "user", "content": llm_judge.build_judge_prompt(
                        bullets=bullets, cards=cards, jd_items=jd_items,
                        resume_text=resume_text, sections=requested)},
                ]}
            response = client.post_json(client.chat_completions_url, payload)
            current = llm_judge.parse_judgments(
                client.extract_content(response), bullets=bullets, jd_items=jd_items, cards=cards,
                resume_text=resume_text,
            )
            if current:
                for section in current.get("judged_sections") or []:
                    merged[section] = current.get(section)
                merged.setdefault("judged_sections", [])
                merged["judged_sections"] = sorted(set(merged["judged_sections"]) | set(current.get("judged_sections") or []))
                merged["rejected_items"] = len(merged.get("rejected_items") or []) if isinstance(merged.get("rejected_items"), list) else merged.get("rejected_items", 0)
            missing = [section for section in all_sections if section not in (merged.get("judged_sections") or [])]
            if not missing:
                parsed = {**merged, "judged_sections": list(all_sections)}
                break
            if attempt:
                parsed = merged if merged.get("judged_sections") else None
                break
            meta["repair_calls"] += 1
            requested = tuple(missing)
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        meta["error"] = str(exc)[:300]
        print(f"[evaluation] LLM 判项不可用，保留 pending：{exc}")
        return None, meta, decisions
    if parsed is None:
        meta["error"] = "invalid_judge_response"
        return None, meta, decisions
    if not missing:
        quality_judge_cache.save_judgment(_judge_cache_root(), key, parsed)
    meta["judged_sections"] = parsed.get("judged_sections")
    meta["rejected_items"] = parsed.get("rejected_items")
    return parsed, meta, decisions


def _load_job_context(job_profile_path: str | None) -> dict:
    if not job_profile_path:
        return {}
    doc = parse_simple_yaml(read_text(job_profile_path))
    context: dict = dict(doc["scalars"])
    context.update(doc["lists"])
    return context


def _quality_markdown(quality_report: dict | None) -> str:
    if not isinstance(quality_report, dict):
        return ""
    labels = {"eligible": "合格", "fit": "对位", "strong": "优质", "distinct": "突出"}
    gap_labels = {"evidence_missing": "证据缺口", "not_expressed": "未表达"}
    tiers = quality_report.get("tiers") if isinstance(quality_report.get("tiers"), dict) else {}
    lines: list[str] = []
    advice = quality_report.get("delivery_advice")
    if isinstance(advice, dict):
        recommendation = str(advice.get("recommendation", ""))
        label = str(advice.get("label", "")) or recommendation
        lines.extend(["", "## 投递建议", f"- 建议：{label}（仅供参考，不拦截投递；最终是否投递由你决定）"])
        if advice.get("summary"):
            lines.append(f"- 摘要：{advice['summary']}")
        for reason in advice.get("reasons") or []:
            lines.append(f"- 依据：{reason}")
        for action in advice.get("next_actions") or []:
            lines.append(f"- 下一步：{action}")
    lines.append("## 质量报告（四层，规则部分）")
    for name, label in labels.items():
        tier = tiers.get(name) if isinstance(tiers, dict) else None
        tier = tier if isinstance(tier, dict) else {}
        lines.append(f"- {label}: {'通过' if tier.get('passed') else '未通过'}")
        for failure in (tier.get("failures") or [])[:10]:
            kind = gap_labels.get(str(failure.get("gap_kind", "")))
            kind_suffix = f"（{kind}）" if kind else ""
            lines.append(
                f"  - {failure.get('rule', '')} {failure.get('target', '')}：{failure.get('reason', '')}{kind_suffix}"
            )
    pending = quality_report.get("llm_pending") or []
    if pending:
        lines.append("- LLM 判项未完成或覆盖不足：" + "、".join(str(item) for item in pending))
    judge = quality_report.get("quality_judge")
    if isinstance(judge, dict) and judge.get("cache") in {"hit", "miss"}:
        lines.append(f"- LLM 判项缓存：{judge.get('cache')}（{judge.get('model', '')} / prompt v{judge.get('prompt_version', '')}）")
    distinct = tiers.get("distinct") if isinstance(tiers, dict) else None
    highlights = (distinct or {}).get("highlights") if isinstance(distinct, dict) else None
    if isinstance(highlights, list):
        for item in highlights:
            if isinstance(item, dict):
                lines.append(
                    f"- 突出点：{item.get('bullet_ref', '')} ↔ JD {item.get('jd_item_id', '')}"
                    f"（{item.get('exceeds', '')}，{item.get('level', '')}）{item.get('reason', '')}"
                )
    lines.append(
        "- 自动通过: "
        + ("是" if quality_report.get("auto_pass") else "否")
        + "（四层全通过且无 LLM 待判项）"
    )
    return "\n".join(lines) + "\n"
