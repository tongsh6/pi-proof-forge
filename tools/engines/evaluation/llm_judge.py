"""受控 JSON 判项通道：LLM 只输出带引用的结构化判断，无引用项 fail-closed。

本模块不执行 IO；调用方（run_evaluation）负责 LLMClient、缓存与决策库。
"""
from __future__ import annotations

import json
import re
from typing import Any
from tools.domain.quality_text import matches_fact_occurrence
from tools.infra.evidence_provenance import parse_provenance
from tools.engines.generation.fact_index import Fact, build_fact_index

PROMPT_VERSION = 10
JUDGE_SCHEMA_VERSION = 2

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


def _profile_facts(career_profile: dict) -> tuple[Fact, ...]:
    """以同次已确认档案展开既有规范身份；不读取或补写来源。"""
    if not isinstance(career_profile, dict):
        return ()
    status = career_profile.get("career_status")
    if not isinstance(status, dict) or status.get("reviewed") is not True:
        return ()
    return build_fact_index([], career_profile.get("career")).facts


def build_judge_prompt(
    *,
    bullets: list[dict[str, object]],
    cards: dict[str, dict],
    jd_items: list[dict[str, str]],
    r1_4_required_lines: set[int],
    r1_4_lines: list[dict[str, object]],
    career_profile: dict,
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
    visible_lines.update(int(row["render_line"]) for row in r1_4_lines)
    profile_facts = _profile_facts(career_profile)
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
        "r1_4_required_lines": sorted(r1_4_required_lines),
        "r1_4_lines": [
            {key: row.get(key, "") for key in ("render_line", "text", "section", "entry")}
            for row in r1_4_lines
        ],
        "career": career_profile.get("career", {}) if profile_facts else {},
        "profile_facts": [
            {"fact_id": fact.fact_id, "source_id": fact.source_id, "field": fact.field,
             "text": fact.text, "work_id": fact.work_id}
            for fact in profile_facts
        ],
        "cards": summarize_cards(cards, claims=claims),
        "jd_items": [
            {"id": item.get("id", ""), "kind": item.get("kind", "must_have"), "text": str(item.get("text", ""))}
            for item in jd_items
        ],
    }
    selected = tuple(section for section in (sections or _RULES) if section in _RULES)
    schema = {
        "r1_4": '  "r1_4": [{"render_line": <int>, "status": "not_applicable|supported|unsupported", "citations": ["ec_..."], "reason": "<short>"}]',
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
        "You are a strict resume-quality judge. Judge ONLY from the provided resume lines, evidence cards, current career sources and JD items.\n"
        "每项判断必须引用输入中存在的 bullet#N、line#N 或证据卡 id；R1 还可引用 profile_facts 的原 Fact ID。仅 absent 可引用 resume，"
        "表示已审阅本次完整正文。理由用简短中文，不虚构事实。\n"
        "各组分别评价其约定对象。相关正文和来源可以帮助理解，但不能把别组或别处的成功、失败直接当作本组的正反证，"
        "也不能补出本组对象没有表达的内容。每项理由须说明其被评对象与相关来源及 JD 的实际关系。\n"
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
        + "Rules: when r1_4 is requested, cover exactly INPUT r1_4_required_lines, "
        "each once by render_line with status/citations/reason; no omissions, duplicates or extra targets. "
        "r1_4_lines 是本次真实完整表达。先在完整语境中识别是否向候选人归属工作行为、交付或相应职责身份，"
        "包括隐含关系；不按章节、对象名称或动词筛选适用性。共同核对主体、否定、时态、环境、"
        "本人参与/主导强度和分工范围；不要求每句出现我，不把同事成果归本人，也不抹掉本人有限对接或参与价值。"
        "一般事实有出处不等于完整责任命题成立，字段中出现某项事实也不能代替对责任关系的判断。"
        "not_applicable 仅表示完整表达没有向候选人归属职责，不表示缺来源；supported 表示当前来源支持完整责任表达；"
        "unsupported 表示当前来源不足以支持或明确反驳该表达，不表示本人不具备能力或事实已经证伪。"
        "无法完成合法判断保留缺项，不能改成 not_applicable。"
        "supported 至少引用一个当前卡 id 或 profile_facts 的原 Fact ID；仅正文 line#/bullet# 不能证明自身责任。"
        "每个引用都必须真实存在，不能混入无效引用；引用不限于被评行本身已绑定来源，充分独立语境可支持已有表达。"
        "reason 简短说明有无责任归属、决定状态的真实来源关系及关键限定；仅说名称相同、字段存在或可追溯不足以支持责任主张。"
        "career 与 profile_facts 来自同一当前已确认档案，原工作 id/current/期间/分工共同约束来源，不跨任职拼接。"
        "当前定位是专业定位，不必表示现受雇于某家公司。综合已确认经历、现职业概述与技能中的实际实践和职责依据，"
        "连同各自时间条件判断该职业身份；current=false 不自动否定，历史同名职位也不能单独证明当前专业定位。"
        "当前定位没有 occurrence 不自动失败，也不能伪造来源直通。"
        "各字段等级只约束实际字段：角色字段 L5 或未确认 L3 不跨字段否定独立有来源的行动/成果。"
        "已确认且有出处的 L3 可保原主导范围；同 Fact 当前 scope/result row 是核验依据，"
        "established/self 不自动证明主导、独立完成或全权负责。"
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
        "被评对象仅为实际职业概述原句，不把其他位置的表述并入摘要。role_scale_match 核对摘要实际表达的定位、"
        "职责强度和规模与相关来源及 JD 是否相符；其他正文可作来源对照，但其独立缺陷不能证明摘要失配。"
        "摘要及其相关来源内容、JD 未变时，不因其他位置的错误改变本项结论。"
        "职责强度与岗位匹配按完整含义判断，不要求特定动词。把表达润色建议与已有判项依据分开，"
        "缺少某个动词或存在可优化写法，不自动构成职责或规模不匹配。"
        "不能从任务颗粒度、工作环境或工作类型外推个人资历、职级或总体能力。"
        "来源及 JD 未给出的资历与层级保持未知，未知本身不是职责或规模冲突的反证。"
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


def validate_role_judgments(
    value: object,
    *,
    required_lines: set[int],
    r1_4_lines: list[dict[str, object]],
    bullets: list[dict[str, object]],
    cards: dict[str, dict] | None,
    career_profile: dict,
) -> tuple[list[dict[str, Any]], bool, int]:
    """原目标先核唯一性；任一非法引用均不能被过滤成完整判项。"""
    if not isinstance(value, list):
        return [], False, 0
    actual_lines = {row["render_line"] for row in r1_4_lines if type(row.get("render_line")) is int}
    bullet_numbers = {int(row["number"]) for row in bullets if type(row.get("number")) is int}
    independent_ids = set(cards or {}) | {fact.fact_id for fact in _profile_facts(career_profile)}
    citation_ids = independent_ids | {f"line#{number}" for number in actual_lines}
    seen: set[int] = set()
    duplicated: set[int] = set()
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for item in value:
        if not isinstance(item, dict):
            rejected += 1
            continue
        number = item.get("render_line")
        if type(number) is not int or number not in required_lines or number not in actual_lines:
            rejected += 1
            continue
        if number in seen:
            duplicated.add(number)
            rejected += 1
            continue
        seen.add(number)
        status = item.get("status")
        references = item.get("citations")
        if (
            set(item) != {"render_line", "status", "citations", "reason"}
            or not isinstance(status, str)
            or status not in {"not_applicable", "supported", "unsupported"}
            or not isinstance(references, list) or not references
            or not isinstance(item.get("reason"), str) or not item["reason"].strip()
        ):
            rejected += 1
            continue
        checked = [_citations([reference], bullet_numbers, citation_ids) for reference in references]
        if any(len(reference) != 1 for reference in checked):
            rejected += 1
            continue
        cites = sorted({reference[0] for reference in checked})
        if status == "supported" and not independent_ids.intersection(cites):
            rejected += 1
            continue
        accepted.append({
            "render_line": number, "status": status, "citations": cites,
            "reason": _clean_string(item.get("reason"), 300),
        })
    rejected += sum(item["render_line"] in duplicated for item in accepted)
    accepted = [item for item in accepted if item["render_line"] not in duplicated]
    complete = not duplicated and {item["render_line"] for item in accepted} == required_lines
    return accepted, complete, rejected

def parse_judgments(
    content: str,
    *,
    bullets: list[dict[str, object]],
    jd_items: list[dict[str, str]],
    r1_4_required_lines: set[int],
    r1_4_lines: list[dict[str, object]],
    career_profile: dict,
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

    r1_4, role_complete, rejected = validate_role_judgments(
        loaded.get("r1_4"), required_lines=r1_4_required_lines,
        r1_4_lines=r1_4_lines, bullets=bullets, cards=cards, career_profile=career_profile,
    )
    if role_complete:
        judged_sections.append("r1_4")
    result["rejected_items"] += rejected
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
