"""四层质量报告：LLM 判项调度、缓存与 Markdown 呈现。

规则判项由 rule_evaluator 负责；本模块负责模型判项的运行/缓存/纠错、
四层报告 Markdown 渲染与投递建议呈现，不改变任何判项结论。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from tools.infra import quality_judge_cache
from tools.infra.llm.client import (
    LLMClient,
    llm_request_available,
    llm_timeout_from_env,
)
from tools.infra.llm.task_contract import (
    QUALITY_JUDGE, REASON_INVALID_JSON, REASON_PARTIAL_COVERAGE, partial, unavailable,
)
from tools.infra.llm.task_runner import execute
from tools.infra.persistence.yaml_io import parse_simple_yaml

from . import llm_judge, tiered_evaluator


def _read_quality_input(meta: dict) -> bytes:
    """校验实际解析的字节，不能用前后重新读到的版本为中途内容背书。"""
    path = Path(meta["path"])
    if not path.is_file() or path.is_symlink():
        raise ValueError("quality_input_changed")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta.get("sha256"):
        raise ValueError("quality_input_changed")
    return raw


def _load_quality_cards(trace: dict) -> dict[str, dict]:
    """只解析生成 trace 所绑定的本次来源版本。"""
    from tools.infra.evidence_fact_scope import current_result_reviews
    from tools.infra.evidence_sources import validated_source_inputs
    from tools.infra.material_paths import materials_dir_for

    cards: dict[str, dict] = {}
    inputs = trace.get("inputs") if isinstance(trace, dict) else None
    ids = trace.get("evidence_card_ids") if isinstance(trace, dict) else None
    if not isinstance(inputs, dict) or not isinstance(ids, list):
        return cards
    # 职业档案依赖另由 inspect_career 核验，不能覆盖正文的同 ID 直接来源。
    for card_id in ids:
        if not isinstance(card_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", card_id):
            continue
        path = Path(inputs[card_id]["path"])
        doc = parse_simple_yaml(_read_quality_input(inputs[card_id]).decode("utf-8"))
        profile_path = Path(inputs.get("personal_profile", {}).get("path") or path)
        material_dir = materials_dir_for(profile_path, fallback=path.parent.parent / "materials")
        sources = validated_source_inputs(doc, material_dir)
        for key, (source_path, digest) in sources.snapshots.items():
            expected = inputs.get(key, {})
            if (not expected.get("path") or Path(expected["path"]).resolve() != source_path.resolve()
                    or expected.get("sha256") != digest):
                raise ValueError("quality_input_changed")
        reviews = current_result_reviews(doc, material_dir, card_id=card_id, validated_sources=sources)
        cards[card_id] = {**doc["scalars"], **doc["lists"], "result_reviews": reviews}
    return cards


def _load_quality_career(trace: dict) -> dict:
    from tools.infra.career_profile import inspect_career

    inputs = trace.get("inputs") if isinstance(trace, dict) else None
    meta = inputs.get("personal_profile") if isinstance(inputs, dict) else None
    if not isinstance(meta, dict):
        return {}
    profile_path = Path(meta["path"])
    fields = dict(parse_simple_yaml(_read_quality_input(meta).decode("utf-8"))["scalars"])
    evidence_dir = profile_path.parent / "evidence_cards"
    if not evidence_dir.is_dir():
        evidence_dir = Path("evidence_cards")
    captured = {}
    profile = {**fields, **inspect_career(fields, evidence_dir, captured_sources=captured)}
    for key, (path, digest) in captured.items():
        expected = inputs.get(key, {})
        if (not expected.get("path") or Path(expected["path"]).resolve() != path.resolve()
                or expected.get("sha256") != digest):
            raise ValueError("quality_input_changed")
    return profile


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
    cards: dict[str, dict],
    semantic_review: dict | None,
    job_profile_path: str | None,
    use_llm: bool,
    model: str,
    api_key: str,
    base_url: str,
    client_factory: Any = None,
) -> tuple[dict | None, dict[str, Any], dict[str, list[str]]]:
    """同份完整请求决定准入和缓存；只修未完成组，失败保留已核 partial。"""
    resume_sha256 = hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
    decisions = quality_judge_cache.load_decisions(Path.cwd(), resume_sha256)
    if isinstance(trace.get("claims"), list):
        rendered_ids = {str(claim.get("evidence_id", "")) for claim in trace["claims"] if isinstance(claim, dict)}
        cards = {key: card for key, card in cards.items() if key in rendered_ids}
    jd_items = _judge_jd_items(semantic_review)
    meta: dict[str, Any] = {"cache": "disabled", "reason": "llm_not_configured_or_no_jd_items"}
    llm_available = llm_request_available(
        provider=os.getenv("LLM_PROVIDER", ""), api_key=api_key, model=model, base_url=base_url
    )
    if not (use_llm and llm_available and jd_items):
        return None, meta, decisions
    bullets = tiered_evaluator.extract_bullets(resume_text)
    job_profile_id = Path(job_profile_path).stem if job_profile_path else ""
    all_sections = tuple(llm_judge._RULES)
    requested = all_sections
    merged: dict[str, Any] = {
        "schema_version": llm_judge.JUDGE_SCHEMA_VERSION,
        "prompt_version": llm_judge.PROMPT_VERSION,
        "judged_sections": [],
        "rejected_items": 0,
    }
    meta = {
        "cache": "miss", "model": model, "prompt_version": llm_judge.PROMPT_VERSION,
        "model_calls": 0, "repair_calls": 0,
    }

    def parse_current(value):
        return llm_judge.parse_judgments(
            json.dumps(value, ensure_ascii=False), bullets=bullets, jd_items=jd_items,
            cards=cards, resume_text=resume_text,
        )

    def validated_cache(cached):
        if not isinstance(cached, dict):
            return None
        sections = cached.get("judged_sections")
        if (
            type(cached.get("schema_version")) is not int
            or cached["schema_version"] != llm_judge.JUDGE_SCHEMA_VERSION
            or type(cached.get("prompt_version")) is not int
            or cached["prompt_version"] != llm_judge.PROMPT_VERSION
            or not isinstance(sections, list)
            or len(sections) != len(all_sections)
            or not all(isinstance(section, str) for section in sections)
            or set(sections) != set(all_sections)
            or any(section not in cached for section in all_sections)
            or type(cached.get("rejected_items")) is not int
            or cached["rejected_items"] < 0
        ):
            return None
        checked = parse_current({section: cached[section] for section in all_sections})
        if (checked is None or set(checked["judged_sections"]) != set(all_sections)
                or any(checked[section] != cached[section] for section in all_sections)):
            return None
        return cached

    def prepare_sections(sections):
        return client.prepare_request(
            client.chat_completions_url,
            {
                "model": model, "temperature": 0,
                "max_tokens": QUALITY_JUDGE.capability.max_output_tokens,
                "stream": False, "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "You are a strict judge. Return ONLY the JSON object."},
                    {"role": "user", "content": llm_judge.build_judge_prompt(
                        bullets=bullets, cards=cards, jd_items=jd_items,
                        resume_text=resume_text, sections=sections)},
                ],
            },
        )

    client = None
    try:
        client = client_factory() if client_factory is not None else LLMClient(
            base_url=base_url, api_key=api_key, timeout=llm_timeout_from_env(),
            provider=os.getenv("LLM_PROVIDER", ""),
        )
        prepared = prepare_sections(all_sections)
        key = quality_judge_cache.judge_cache_key(
            prepared_request=prepared, trace_inputs=trace.get("inputs", {}),
            resume_sha256=resume_sha256, job_profile_id=job_profile_id,
            cards=cards, prompt_version=llm_judge.PROMPT_VERSION,
        )
    except Exception as exc:
        # 构造失败交由执行器记录，不作为传输失败，也不重发原输入。
        prepared = exc
    else:
        meta["key"] = key
        cached = validated_cache(quality_judge_cache.load_judgment(_judge_cache_root(), key))
        if cached is not None:
            meta.update(cache="hit", judged_sections=cached["judged_sections"],
                        rejected_items=cached["rejected_items"])
            return cached, meta, decisions

    def initial_request():
        if isinstance(prepared, Exception):
            raise prepared
        return prepared

    def validate(parsed):
        if not isinstance(parsed, dict):
            raise ValueError("invalid_judge_response")
        current = parse_current({section: parsed[section] for section in requested if section in parsed})
        if current is None:
            raise ValueError("invalid_judge_response")
        for section in requested:
            if section in current["judged_sections"]:
                merged[section] = current[section]
        merged["rejected_items"] += current["rejected_items"]
        merged["judged_sections"] = [section for section in all_sections if section in merged]
        if len(merged["judged_sections"]) != len(all_sections):
            raise ValueError(REASON_PARTIAL_COVERAGE)
        return merged

    def repair(_previous, _error):
        nonlocal requested
        requested = tuple(section for section in all_sections if section not in merged["judged_sections"])
        return prepare_sections(requested)

    run = execute(
        QUALITY_JUDGE, model=model, prepare=initial_request,
        call=lambda request: client.send_request(request),
        extract=lambda response: client.extract_content(response),
        validate=validate, on_retry=repair,
    )
    if run.status != "complete":
        reason = run.reason_code
        if reason == REASON_INVALID_JSON and run.outcome.detail == REASON_PARTIAL_COVERAGE:
            reason = REASON_PARTIAL_COVERAGE
        if merged["judged_sections"]:
            run = replace(run, outcome=partial(
                reason_code=reason, detail=run.outcome.detail, result=merged,
            ))
        elif reason != run.reason_code:
            run = replace(run, outcome=unavailable(
                QUALITY_JUDGE, reason_code=reason, detail=run.outcome.detail,
            ))
    meta.update(model_calls=run.attempts, repair_calls=max(0, run.attempts - 1))
    parsed = run.outcome.result if run.outcome.usable else None
    if run.reason_code:
        detail = run.outcome.detail
        meta["error"] = run.reason_code + (f":{detail}" if detail and detail != run.reason_code else "")
    if parsed is not None:
        meta["judged_sections"] = parsed["judged_sections"]
        meta["rejected_items"] = parsed["rejected_items"]
    print("[evaluation] " + json.dumps(run.to_dict(), ensure_ascii=False))
    if run.status == "complete":
        quality_judge_cache.save_judgment(_judge_cache_root(), key, parsed)
    return parsed, meta, decisions


def _load_job_context(job_profile_path: str | None, *, trace: dict) -> dict:
    if not job_profile_path:
        return {}
    path = Path(job_profile_path)
    if trace:
        meta = trace.get("inputs", {}).get("job_profile", {})
        if not meta.get("path") or Path(meta["path"]).resolve() != path.resolve():
            raise ValueError("quality_target_changed")
        raw = _read_quality_input(meta)
    else:
        # 无有效 trace 的非语义评测仍可给出不获追溯信用的规则建议。
        raw = path.read_bytes()
    doc = parse_simple_yaml(raw.decode("utf-8"))
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
