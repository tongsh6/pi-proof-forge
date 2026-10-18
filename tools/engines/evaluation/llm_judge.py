"""受控 JSON 判项通道：LLM 只输出带引用的结构化判断，无引用项 fail-closed。

本模块不执行 IO；调用方（run_evaluation）负责 LLMClient、缓存与决策库。
"""
from __future__ import annotations

import json
import re
from typing import Any

PROMPT_VERSION = 1
JUDGE_SCHEMA_VERSION = 1

_RULES = ("r1_4", "r2_1", "r3_1", "r3_5", "r4_1")
_STATUSES = {"supported", "weak", "absent"}
_EXCEEDS = {"scale", "difficulty", "scope", "scarcity"}
_LEVELS = {"L1", "L2"}


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize_cards(cards: dict[str, dict]) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for card_id in sorted(cards):
        card = cards.get(card_id) or {}
        results = [str(item) for item in (card.get("results") or []) if str(item).strip()]
        summary.append(
            {
                "id": card_id,
                "title": _clip(card.get("title"), 80),
                "time_range": _clip(card.get("time_range"), 40),
                "role_scope": _clip(card.get("role_scope"), 60),
                "context": _clip(card.get("context"), 160),
                "results": [_clip(item, 160) for item in results[:5]],
                "stack": [_clip(item, 40) for item in (card.get("stack") or [])[:8]],
            }
        )
    return summary


def build_judge_prompt(
    *,
    bullets: list[dict[str, object]],
    cards: dict[str, dict],
    jd_items: list[dict[str, str]],
) -> str:
    bullet_lines = [
        {
            "bullet": int(row["number"]),
            "section": row.get("section", ""),
            "entry": _clip(row.get("entry"), 80),
            "first_screen": bool(row.get("first_screen")),
            "text": _clip(row.get("text"), 300),
        }
        for row in bullets
        if row.get("section") in {"项目经历", "工作经历", "补充成果", "核心能力"}
    ]
    payload = {
        "bullets": bullet_lines[:60],
        "cards": summarize_cards(cards)[:60],
        "jd_items": [
            {"id": item.get("id", ""), "kind": item.get("kind", "must_have"), "text": _clip(item.get("text"), 300)}
            for item in jd_items
        ][:60],
    }
    return (
        "You are a strict resume-quality judge. Judge ONLY from the provided bullets, evidence cards and JD items.\n"
        "Every judgement item MUST cite at least one bullet number and/or evidence-card id from the input. "
        "Items without citations are invalid and will be discarded. Do not invent facts.\n"
        "Return ONLY a JSON object (no markdown fence) with EXACTLY these keys:\n"
        "{\n"
        '  "r1_4": [{"bullet": <int>, "supported": <bool>, "citations": ["ec_..."], "reason": "<short>"}],\n'
        '  "r2_1": [{"jd_item_id": "<id>", "status": "supported|weak|absent", "bullet_ref": "bullet#<int> or empty", '
        '"citations": ["ec_..." or "bullet#<int>"], "reason": "<short>"}],\n'
        '  "r3_1": [{"bullet": <int>, "scene": <bool>, "action": <bool>, "result": <bool>, '
        '"citations": ["ec_..."], "reason": "<short>"}],\n'
        '  "r3_5": {"summary_lines": <int>, "role_scale_match": <bool>, "generic_adjectives": ["<word>"], '
        '"citations": ["bullet#<int>"], "reason": "<short>"},\n'
        '  "r4_1": [{"bullet": <int>, "jd_item_id": "<id>", "exceeds": ["scale|difficulty|scope|scarcity"], '
        '"level": "L1|L2", "citations": ["ec_..."], "reason": "<short>"}]\n'
        "}\n"
        "Rules: r1_4 covers every bullet whose wording claims ownership (负责/主导/独立负责/全权负责/设计并落地); "
        "supported=true only when the cited card shows first-person ownership. "
        "r2_1 must cover EVERY jd_item id exactly once. r3_1 must cover every experience bullet. "
        "r3_5 judges the positioning summary (<=3 lines, role/scale match, no generic adjectives). "
        "r4_1 nominates 0-3 differentiated highlights that exceed the JD requirement in one of the four dimensions; "
        "only use L1 when the cited card text directly shows it.\n"
        "INPUT JSON:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _citations(value: object, bullet_numbers: set[int], card_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    valid: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if token in card_ids:
            valid.append(token)
            continue
        match = re.fullmatch(r"bullet#?(\d+)", token)
        if match and int(match.group(1)) in bullet_numbers:
            valid.append(f"bullet#{match.group(1)}")
    return sorted(set(valid))


def _clean_string(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def parse_judgments(
    content: str,
    *,
    bullets: list[dict[str, object]],
    jd_items: list[dict[str, str]],
    cards: dict[str, dict] | None = None,
) -> dict[str, Any] | None:
    """解析并校验判项；整体不可解析返回 None，单项无引用/无效则丢弃。"""
    if not isinstance(content, str) or not content.strip():
        return None
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        loaded = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(loaded, dict):
        return None
    bullet_numbers = {int(row["number"]) for row in bullets if isinstance(row.get("number"), int)}
    card_ids = set(cards or {})
    jd_ids = {str(item.get("id", "")) for item in jd_items if item.get("id")}
    judged_sections: list[str] = []
    result: dict[str, Any] = {"schema_version": JUDGE_SCHEMA_VERSION, "prompt_version": PROMPT_VERSION,
                              "judged_sections": judged_sections, "rejected_items": 0}

    r1_4: list[dict[str, Any]] = []
    if isinstance(loaded.get("r1_4"), list):
        judged_sections.append("r1_4")
        for item in loaded["r1_4"]:
            if not isinstance(item, dict):
                continue
            bullet = _as_int(item.get("bullet"))
            cites = _citations(item.get("citations"), bullet_numbers, card_ids)
            if bullet not in bullet_numbers or not cites or not isinstance(item.get("supported"), bool):
                result["rejected_items"] += 1
                continue
            r1_4.append({"bullet": bullet, "supported": item["supported"], "citations": cites,
                         "reason": _clean_string(item.get("reason"), 300)})
    result["r1_4"] = r1_4

    r2_1: list[dict[str, Any]] = []
    if isinstance(loaded.get("r2_1"), list):
        seen: set[str] = set()
        for item in loaded["r2_1"]:
            if not isinstance(item, dict):
                continue
            jd_id = str(item.get("jd_item_id", ""))
            cites = _citations(item.get("citations"), bullet_numbers, card_ids)
            status = str(item.get("status", ""))
            bullet_ref = _clean_string(item.get("bullet_ref"), 40)
            if jd_id not in jd_ids or jd_id in seen or status not in _STATUSES or not cites:
                result["rejected_items"] += 1
                continue
            seen.add(jd_id)
            r2_1.append({"jd_item_id": jd_id, "status": status, "bullet_ref": bullet_ref,
                         "citations": cites, "reason": _clean_string(item.get("reason"), 300)})
        if jd_ids and seen == jd_ids:
            judged_sections.append("r2_1")
    result["r2_1"] = r2_1

    r3_1: list[dict[str, Any]] = []
    if isinstance(loaded.get("r3_1"), list):
        judged_sections.append("r3_1")
        for item in loaded["r3_1"]:
            if not isinstance(item, dict):
                continue
            bullet = _as_int(item.get("bullet"))
            cites = _citations(item.get("citations"), bullet_numbers, card_ids)
            flags = {key: item.get(key) for key in ("scene", "action", "result")}
            if bullet not in bullet_numbers or not cites or any(not isinstance(v, bool) for v in flags.values()):
                result["rejected_items"] += 1
                continue
            r3_1.append({"bullet": bullet, **flags, "citations": cites,
                         "reason": _clean_string(item.get("reason"), 300)})
    result["r3_1"] = r3_1

    r3_5: dict[str, Any] | None = None
    raw = loaded.get("r3_5")
    if isinstance(raw, dict):
        cites = _citations(raw.get("citations"), bullet_numbers, card_ids)
        lines = _as_int(raw.get("summary_lines"))
        if cites and lines is not None and isinstance(raw.get("role_scale_match"), bool):
            judged_sections.append("r3_5")
            adjectives = raw.get("generic_adjectives")
            r3_5 = {
                "summary_lines": lines,
                "role_scale_match": raw["role_scale_match"],
                "generic_adjectives": [str(item)[:40] for item in (adjectives if isinstance(adjectives, list) else [])][:10],
                "citations": cites,
                "reason": _clean_string(raw.get("reason"), 300),
            }
        else:
            result["rejected_items"] += 1
    result["r3_5"] = r3_5

    r4_1: list[dict[str, Any]] = []
    if isinstance(loaded.get("r4_1"), list):
        judged_sections.append("r4_1")
        for item in loaded["r4_1"]:
            if not isinstance(item, dict):
                continue
            bullet = _as_int(item.get("bullet"))
            cites = _citations(item.get("citations"), bullet_numbers, card_ids)
            jd_id = str(item.get("jd_item_id", ""))
            exceeds = [str(value) for value in (item.get("exceeds") if isinstance(item.get("exceeds"), list) else []) if str(value) in _EXCEEDS]
            level = str(item.get("level", ""))
            if bullet not in bullet_numbers or not cites or jd_id not in jd_ids or not exceeds or level not in _LEVELS:
                result["rejected_items"] += 1
                continue
            r4_1.append({"bullet": bullet, "jd_item_id": jd_id, "exceeds": sorted(set(exceeds)),
                         "level": level, "citations": cites, "reason": _clean_string(item.get("reason"), 300)})
    result["r4_1"] = r4_1
    return result


def highlight_id(candidate: dict[str, Any]) -> str:
    return f"hl_b{int(candidate.get('bullet', 0))}_{candidate.get('jd_item_id', '')}"
