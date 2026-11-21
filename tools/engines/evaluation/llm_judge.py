"""受控 JSON 判项通道：LLM 只输出带引用的结构化判断，无引用项 fail-closed。

本模块不执行 IO；调用方（run_evaluation）负责 LLMClient、缓存与决策库。
"""
from __future__ import annotations

import json
import re
from typing import Any
from tools.domain.quality_text import matches_fact_occurrence
from tools.infra.evidence_provenance import parse_provenance

PROMPT_VERSION = 6
JUDGE_SCHEMA_VERSION = 1

_RULES = ("r1_4", "r2_1", "r3_1", "r3_5", "r4_1")
_STATUSES = {"supported", "weak", "absent"}
_EXCEEDS = {"scale", "difficulty", "scope", "scarcity"}
_LEVELS = {"L1", "L2"}


def resume_lines(resume: str) -> list[dict[str, object]]:
    """补足非 bullet 正文；头部联系方式与求职意向不作为能力证据。"""
    lines = []
    section = ""
    entry = ""
    first_screen = True
    for number, raw in enumerate(resume.splitlines(), 1):
        text = raw.strip()
        if text == "<!-- first-screen-end -->":
            first_screen = False
        elif text.startswith("## "):
            section = text[3:].strip()
            entry = ""
        elif section and text and not text.startswith("<!--") and not re.match(r"^(?:[-*]|\d+\.)\s+", text):
            if text.startswith("### "):
                entry = text[4:]
            lines.append({"id": f"line#{number}", "section": section, "text": text,
                          "entry": entry, "first_screen": first_screen})
    return lines


def summarize_cards(cards: dict[str, dict], *, claims: list[dict]) -> list[dict[str, object]]:
    """Complete source context, with result credit restricted to adopted occurrences."""
    adopted_results: dict[str, dict] = {}
    for claim in claims:
        if claim.get("source_kind") != "evidence" or claim.get("field") != "results":
            continue
        card_id = claim["evidence_id"]
        fact_id = claim["fact_id"]
        reviewed = (cards[card_id].get("result_reviews") or {}).get(fact_id, {})
        if (
            reviewed.get("field") == "results"
            and fact_id == f"{card_id}:results:{reviewed.get('index')}"
            and reviewed.get("value") == claim["value"]
            and reviewed.get("result_review", {}).get("outcome") == "established"
        ):
            adopted_results.setdefault(card_id, {})[fact_id] = reviewed

    summary: list[dict[str, object]] = []
    for card_id in sorted(cards):
        card = cards.get(card_id) or {}
        role = parse_provenance(card.get("role_scope_provenance") or card.get("role_scope_provenance_json")) or {}
        summary.append(
            {
                "id": card_id,
                "title": str(card.get("title") or ""),
                "time_range": str(card.get("time_range") or ""),
                "role_scope": str(card.get("role_scope") or ""),
                "role_scope_provenance": role,
                "role_scope_level": role.get("level", "L1" if card.get("role_scope") else "L5"),
                "role_scope_confirmed": role.get("confirmed_by_user") is True,
                "context": str(card.get("context") or ""),
                "actions": [str(item) for item in (card.get("actions") or [])],
                "results": [str(item) for item in (card.get("results") or [])],
                "stack": [str(item) for item in (card.get("stack") or [])],
                "fact_scope_review": card.get("fact_scope_review") or [],
                "result_reviews": adopted_results.get(card_id, {}),
            }
        )
    return summary


def build_judge_prompt(
    *,
    bullets: list[dict[str, object]],
    cards: dict[str, dict],
    jd_items: list[dict[str, str]],
    resume_text: str = "",
    trace: dict | None = None,
    sections: tuple[str, ...] | None = None,
) -> str:
    bullet_lines = [
        {
            "bullet": int(row["number"]),
            "section": row.get("section", ""),
            "entry": str(row.get("entry") or ""),
            "render_line": row["line"] + 1 if type(row.get("line")) is int else None,
            "first_screen": bool(row.get("first_screen")),
            "text": str(row.get("text", "")),
        }
        for row in bullets
        if row.get("section") in {"项目经历", "工作经历", "补充成果", "核心能力"}
    ]
    lines = resume_lines(resume_text)
    visible_lines = {int(row["id"].split("#", 1)[1]) for row in lines}
    visible_lines.update(row["render_line"] for row in bullet_lines if row["render_line"] is not None)
    claims: list[dict] = []
    for original in (trace.get("claims") or []) if isinstance(trace, dict) else []:
        if not isinstance(original, dict) or original.get("render_line") not in visible_lines:
            continue
        claim = dict(original)
        field = claim.get("field")
        if claim.get("source_kind") == "evidence" and field in {"actions", "results"}:
            card_id = claim.get("evidence_id", "")
            values = (cards.get(card_id) or {}).get(field) or []
            if not matches_fact_occurrence(card_id, field, values, claim):
                raise ValueError("quality_claim_source_mismatch")
            index = int(claim["fact_id"].rsplit(":", 1)[1])
            claim.update(index=index, value=values[index])
        claims.append(claim)
    payload = {
        "resume_lines": lines,
        "bullets": bullet_lines,
        "claims": claims,
        "cards": summarize_cards(cards, claims=claims),
        "jd_items": [
            {"id": item.get("id", ""), "kind": item.get("kind", "must_have"), "text": str(item.get("text", ""))}
            for item in jd_items
        ],
    }
    selected = tuple(section for section in (sections or _RULES) if section in _RULES)
    schema = {
        "r1_4": '  "r1_4": [{"bullet": <int>, "supported": <bool>, "citations": ["ec_..."], "reason": "<short>"}]',
        "r2_1": '  "r2_1": [{"jd_item_id": "<id>", "status": "supported|weak|absent", "bullet_ref": "bullet#N 或 line#N；absent 时为空", '
                '"citations": ["bullet#N 或 line#N 或 ec_...；absent 可用 resume"], "reason": "<short>"}]',
        "r3_1": '  "r3_1": [{"bullet": <int>, "scene": <bool>, "action": <bool>, "result": <bool>, '
                '"citations": ["ec_..."], "reason": "<short>"}]',
        "r3_5": '  "r3_5": {"summary_lines": <int>, "role_scale_match": <bool>, "generic_adjectives": ["<word>"], '
                '"citations": ["bullet#<int>"], "reason": "<short>"}',
        "r4_1": '  "r4_1": [{"bullet": <int>, "jd_item_id": "<id>", "exceeds": ["scale|difficulty|scope|scarcity"], '
                '"level": "L1|L2", "citations": ["ec_..."], "reason": "<short>"}]',
    }
    schema_text = "{\n" + ",\n".join(schema[section] for section in selected) + "\n}\n"
    return (
        "You are a strict resume-quality judge. Judge ONLY from the provided bullets, evidence cards and JD items.\n"
        "每项判断必须引用输入中存在的 bullet#N、line#N 或证据卡 id。仅 absent 可引用 resume，"
        "表示已审阅本次完整正文。理由用简短中文，不虚构事实。\n"
        "claims 按实际 render_line 记录正文已采用的来源身份；行动和结果的 index/value 是原字段位置与完整原文，"
        "不能按同文或同卡替换身份。cards 是完整原卡核验语境，role_scope_provenance 和 fact_scope_review "
        "提供已有职责与范围；它们可以支持或反驳正文已经表达的职责和条件，但不能补出未呈现的行动、成果、"
        "JD 覆盖、规模或亮点。unknown、缺核定或不同范围本身不等于相反事实。"
        "cards.result_reviews 只包含正文实际采用且当前已核的完整结果原 row；使用同一 row 的 value、scope、"
        "source 和 result_review，不拼接另一事实的信用。其他原卡结果即便同文或真实，也不是本次正文成果。"
        "正文场景须实际呈现；仅在原卡 context 中出现不等于已在正文表达。"
        "时间等结构 claims 可能按已核来源降低显示精度，不把完整日期未展示当作事实冲突。\n"
        "Return ONLY a JSON object (no markdown fence) with EXACTLY these keys: " + ", ".join(selected) + "\n"
        + schema_text
        + "Rules: r1_4 covers every bullet whose wording claims ownership (负责/主导/独立负责/全权负责/设计并落地); "
        "判断责任强度要结合卡内已审核职责与具体行动；不要求简历或证据句反复出现“我”，"
        "已经用户确认的 L3 职责可以保留主导/负责人，不因等级自动否定；仍须核对行动与职责范围，"
        "也不能将团队成果、系统功能或限定参与提升为独立负责。"
        "r2_1 must cover EVERY jd_item id exactly once. supported/weak 的 bullet_ref 必须填写正文 bullet#N 或 line#N，"
        "不可用卡中未出现在正文的内容补足正文覆盖。可引用多个正文位置。absent 引用 [\"resume\"] 表示已核对全部正文，"
        "并说明缺少什么，不引用无关成果。其余 citations 可用真实 bullet#N、line#N 或卡 id，不能留空。"
        "要求中的或/等是备选或示例，不增加同时掌握、生产上线或全部独立负责等原文没有的条件。"
        "r3_1 must cover every experience bullet (项目经历/工作经历/补充成果). "
        "场景可来自同一经历的标题、场景行；结果包括可验证的非数值交付或完成状态，"
        "例如“实现跨系统接口集成”是可验证的交付结果，“计划接入系统”则不是已完成结果。"
        "不是每条都必须有量化指标（量化比例由 R3.2 单独检查）。个人项目可引用其正文 bullet，"
        "不因无独立卡 id 而省略判定。只评价实际正文，不从证据卡补出未呈现的行动和成果。"
        "r3_5 judges 职业概述 in resume_lines (<=3 lines, role/scale match, no generic adjectives). "
        "r4_1 nominates 0-3 differentiated highlights that exceed the JD requirement in one of the four dimensions; "
        "only use L1 when the actual rendered claim and its complete source evidence directly show it.\n"
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
    resume_text: str = "",
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
    line_ids = {str(row["id"]) for row in resume_lines(resume_text)}
    card_ids = set(cards or {}) | line_ids
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
            status = str(item.get("status", ""))
            cites = _citations(item.get("citations"), bullet_numbers,
                               card_ids | ({"resume"} if status == "absent" and resume_text else set()))
            bullet_ref = _clean_string(item.get("bullet_ref"), 40)
            refs = re.findall(r"(?:bullet|line)#\d+", bullet_ref)
            allowed_refs = {f"bullet#{number}" for number in bullet_numbers} | line_ids
            if not bullet_ref and status != "absent":
                refs = [ref for ref in cites if ref in allowed_refs]
                bullet_ref = "、".join(refs)
            if (jd_id not in jd_ids or jd_id in seen or status not in _STATUSES or not cites
                    or (status != "absent" and (not refs or not set(refs) <= allowed_refs))):
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
    expected = {int(row["number"]) for row in bullets
                if row.get("section") in {"项目经历", "工作经历", "补充成果"}}
    if not expected <= {row["bullet"] for row in r3_1} and "r3_1" in judged_sections:
        judged_sections.remove("r3_1")

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
