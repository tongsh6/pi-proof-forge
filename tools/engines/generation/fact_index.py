"""事实索引：把证据卡与已确认职业档案展开为可排序、可追溯的最小事实单元。

生成阶段的选材从这里取事实，而不是从"卡"取；渲染只消费事实引用。
事实编号沿用语义评审的 `{source_id}:{field}:{index}` 口径，因此
`matching_reports/*.semantic.json` 的引用可以直接映射回事实，无需二次解析文本。

本模块只做只读聚合：不新增、不改写、不推断事实。
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from tools.domain.assessment_support import positive_citations

# 与语义评审的事实展开口径保持一致：字段顺序决定 index，不能随意调整。
FACT_FIELDS: tuple[str, ...] = (
    "title",
    "context",
    "role_scope",
    "time_range",
    "actions",
    "results",
    "stack",
    "tags",
)

PROFILE_GROUPS: dict[str, tuple[str, ...]] = {
    "work": ("title", "company", "start", "end", "scope", "contributions"),
    "education": ("school", "degree", "major", "start", "end"),
    "skills": ("category", "description"),
    "extras": ("title", "description", "url"),
}

PLACEHOLDER_VALUES = frozenset({"", "[]", "{}", "null", "none"})

_OWNER_RE = re.compile(r"独立负责|全权负责|总体技术负责人|总体负责人|独立完成")
_LEAD_RE = re.compile(r"主导|牵头|负责人|带团队|带领")
_PARTICIPATE_RE = re.compile(r"参与|协作|配合|协助")



@dataclass(frozen=True)
class Fact:
    """最小事实单元；`text` 必须逐字来自来源（证据卡字段或已确认档案字段）。"""

    fact_id: str
    source_id: str
    field: str
    text: str
    kind: str  # evidence | profile
    work_id: str = ""
    time_range: str = ""
    has_quant: bool = False
    role_strength: str = "unknown"  # owner | lead | participate | unknown
    requirement_ids: tuple[str, ...] = ()
    support_weight: int = 0
    card_title: str = ""
    order: int = 0


@dataclass(frozen=True)
class FactIndex:
    facts: tuple[Fact, ...]
    by_id: Mapping[str, Fact] = field(default_factory=dict)
    first_screen_priority: Mapping[str, int] = field(default_factory=dict)

    def get(self, fact_id: str) -> Fact | None:
        if self.by_id:
            return self.by_id.get(fact_id)
        for fact in self.facts:
            if fact.fact_id == fact_id:
                return fact
        return None

    def by_card(self, card_id: str) -> tuple[Fact, ...]:
        return tuple(fact for fact in self.facts if fact.kind == "evidence" and fact.source_id == card_id)

    def by_work(self, work_id: str) -> tuple[Fact, ...]:
        return tuple(fact for fact in self.facts if fact.work_id == work_id)

    @property
    def card_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for fact in self.facts:
            if fact.kind == "evidence" and fact.source_id not in seen:
                seen.append(fact.source_id)
        return tuple(seen)

    @property
    def work_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for fact in self.facts:
            if fact.work_id and fact.work_id not in seen:
                seen.append(fact.work_id)
        return tuple(seen)


def _clean(value: object) -> str:
    text = " ".join(str(value or "").split())
    return "" if text.casefold() in PLACEHOLDER_VALUES else text


def role_strength_of(text: str) -> str:
    """责任强度只看已确认原文措辞，不从技术相似度推断。"""
    value = str(text or "")
    if _OWNER_RE.search(value):
        return "owner"
    if _LEAD_RE.search(value):
        return "lead"
    if _PARTICIPATE_RE.search(value):
        return "participate"
    return "unknown"


def _requirement_map(semantic_report: dict | None) -> dict[str, tuple[tuple[str, int], ...]]:
    """fact_id → ((requirement_id, 支持权重), ...)；只接受已定义的 requirement。"""
    if not isinstance(semantic_report, dict):
        return {}
    requirements = semantic_report.get("requirements") or []
    if not isinstance(requirements, list):
        raise ValueError("semantic_requirement_identity_invalid")
    known = set()
    for item in requirements:
        if not isinstance(item, dict):
            raise ValueError("semantic_requirement_identity_invalid")
        key = item.get("id", item.get("requirement_id"))
        if (not isinstance(key, str) or not key or key.strip() != key
                or ("id" in item and "requirement_id" in item and item["id"] != item["requirement_id"])
                or key in known):
            raise ValueError("semantic_requirement_identity_invalid")
        known.add(key)
    rows: dict[str, list[tuple[str, int]]] = {}
    for assessment in semantic_report.get("assessments") or []:
        if not isinstance(assessment, dict):
            continue
        requirement_id = str(assessment.get("requirement_id") or "")
        if requirement_id not in known:
            continue
        for citation, status in positive_citations(assessment):
            weight = {"supported": 2, "partial": 1}[status]
            fact_id = str(citation.get("fact_id") or "")
            if not fact_id:
                continue
            rows.setdefault(fact_id, [])
            if (requirement_id, weight) not in rows[fact_id]:
                rows[fact_id].append((requirement_id, weight))
    return {fact_id: tuple(sorted(values)) for fact_id, values in rows.items()}


def _first_screen_priority(
    report: dict | None, facts: Mapping[str, Fact], evidence_hashes: Mapping[str, str],
) -> dict[str, int]:
    """Exact supported facts for the first three JD responsibilities, then hard requirements."""
    if not isinstance(report, dict) or report.get("advisory_scope") is not False:
        return {}
    requirements = report.get("requirements") or []
    duties = [item for item in requirements if item.get("kind") == "responsibility"][:3]
    hard = [item for item in requirements if item.get("kind") == "must_have"]
    ranks = {row.get("id", row.get("requirement_id")): rank
             for group, first in ((duties, 0), (hard, 3)) for rank, row in enumerate(group, first)}
    report_facts = report.get("facts") or {}
    inputs = report.get("inputs") or {}
    result: dict[str, int] = {}
    for assessment in report.get("assessments") or []:
        if not isinstance(assessment, dict) or assessment.get("status") != "supported":
            continue
        rank = ranks.get(assessment.get("requirement_id"))
        if rank is None:
            continue
        for citation, status in positive_citations(assessment):
            fact_id = citation.get("fact_id")
            if status != "supported" or not isinstance(fact_id, str) or fact_id not in facts:
                continue
            fact = facts[fact_id]
            source = report_facts.get(fact_id)
            binding = inputs.get(fact.source_id)
            if (not isinstance(binding, dict) or not binding.get("sha256")
                    or (fact.kind == "evidence" and binding["sha256"] != evidence_hashes.get(fact.source_id))
                    or not isinstance(source, dict)
                    or source.get("source_id") != fact.source_id or source.get("field") != fact.field
                    or _clean(source.get("text")) != fact.text):
                continue
            result[fact_id] = min(rank, result.get(fact_id, rank))
    return result


def _work_by_card(career: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in career.get("work") or []:
        work_id = str(item.get("id") or "")
        if not work_id:
            continue
        for card_id in item.get("evidence_ids") or []:
            mapping.setdefault(str(card_id), work_id)
    return mapping


def _values_for(doc: dict, field: str) -> list[str]:
    values = doc.get(field)
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return [str(value) for value in values]
    return [str(values)]


def _append(
    out: list[Fact],
    *,
    fact_id: str,
    source_id: str,
    field: str,
    text: str,
    kind: str,
    work_id: str,
    time_range: str,
    role_text: str,
    requirements: dict[str, tuple[tuple[str, int], ...]],
    card_title: str,
    preferred: bool = False,
    has_quant: bool = False,
) -> None:
    cleaned = _clean(text)
    if not cleaned:
        return
    hit = requirements.get(fact_id, ())
    out.append(
        Fact(
            fact_id=fact_id,
            source_id=source_id,
            field=field,
            text=cleaned,
            kind=kind,
            work_id=work_id,
            time_range=time_range,
            has_quant=has_quant,
            role_strength=role_strength_of(role_text),
            requirement_ids=tuple(requirement_id for requirement_id, _weight in hit),
            # 语义选中的岗位相关卡：整卡事实给强权重，否则岗位定向会被
            # 「量化/规模」类事实压过去，不同 JD 生成几乎相同（实测差 2 行）。
            support_weight=max(3 if preferred else 0, max((weight for _requirement_id, weight in hit), default=0)),
            card_title=card_title,
            order=len(out),
        )
    )


def build_fact_index(
    cards: Iterable[dict],
    career: dict | None = None,
    semantic_report: dict | None = None,
    preferred_card_ids: Iterable[str] | None = None,
) -> FactIndex:
    """展开证据卡与职业档案事实；同一 fact_id 只保留首次出现（输入顺序稳定）。

    `preferred_card_ids` 是语义评审选中的项目卡：这些卡是岗位对位后的
    高相关项目，未被仅作为非支持证据引用的事实获得优先权重——否则语义只影响被引用的少数
    事实，岗位定向在简历上几乎看不出来（实测两个不同 JD 仅差 2 行）。
    """
    career_data = career if isinstance(career, dict) else {}
    requirements = _requirement_map(semantic_report)
    # Parent audit citations are the union of all child references. Negative-only
    # references cannot acquire artificial support through a preferred card.
    audit_citations = {
        c["fact_id"] for row in (semantic_report or {}).get("assessments", [])
        if isinstance(row, dict) for c in row.get("citations") or []
        if isinstance(c, dict) and isinstance(c.get("fact_id"), str)
    } if isinstance(semantic_report, dict) else set()
    non_supporting = audit_citations - requirements.keys()
    preferred_cards = {str(card_id) for card_id in (preferred_card_ids or ())}
    work_by_card = _work_by_card(career_data)
    facts: list[Fact] = []
    seen: set[str] = set()
    evidence_hashes: dict[str, str] = {}

    for doc in cards:
        if not isinstance(doc, dict):
            continue
        source_id = str(doc.get("id") or "")
        if not source_id:
            continue
        evidence_hashes.setdefault(source_id, str(doc.get("source_sha256") or ""))
        time_range = _clean(doc.get("time_range"))
        role_text = _clean(doc.get("role_scope"))
        for field in FACT_FIELDS:
            for index, value in enumerate(_values_for(doc, field)):
                fact_id = f"{source_id}:{field}:{index}"
                if fact_id in seen or fact_id in doc.get("personal_claim_exclusions", ()):
                    continue
                reviewed = (doc.get("result_reviews") or {}).get(fact_id, {})
                if field == "results" and (
                    reviewed.get("field") != field or reviewed.get("index") != index
                    or reviewed.get("value") != value
                    or reviewed.get("result_review", {}).get("outcome") != "established"
                ):
                    continue
                seen.add(fact_id)
                _append(
                    facts,
                    fact_id=fact_id,
                    source_id=source_id,
                    field=field,
                    text=value,
                    kind="evidence",
                    work_id=work_by_card.get(source_id, ""),
                    time_range=time_range,
                    role_text=role_text,
                    requirements=requirements,
                    card_title=_clean(doc.get("title")),
                    preferred=source_id in preferred_cards and fact_id not in non_supporting,
                    has_quant=field == "results" and bool(reviewed["result_review"].get("measurement_quote")),
                )

    summary_text = _clean(career_data.get("summary"))
    if summary_text:
        _append(
            facts,
            fact_id="personal_profile:career.summary:0",
            source_id="personal_profile",
            field="career.summary",
            text=summary_text,
            kind="profile",
            work_id="",
            time_range="",
            role_text="",
            requirements=requirements,
            card_title="",
        )

    for group, fields in PROFILE_GROUPS.items():
        if group == "education" and career_data.get("education_visibility") == "omit":
            continue
        for row in career_data.get(group) or []:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "")
            if not row_id:
                continue
            work_id = row_id if group == "work" else ""
            role_text = _clean(row.get("title")) if group == "work" else ""
            for field in fields:
                for index, value in enumerate(_values_for(row, field)):
                    fact_id = f"personal_profile:career.{group}.{row_id}.{field}:{index}"
                    if fact_id in seen:
                        continue
                    seen.add(fact_id)
                    _append(
                        facts,
                        fact_id=fact_id,
                        source_id="personal_profile",
                        field=f"career.{group}.{row_id}.{field}",
                        text=value,
                        kind="profile",
                        work_id=work_id,
                        time_range="",
                        role_text=role_text,
                        requirements=requirements,
                        card_title="",
                    )

    by_id = {fact.fact_id: fact for fact in facts}
    return FactIndex(facts=tuple(facts), by_id=by_id, first_screen_priority=_first_screen_priority(semantic_report, by_id, evidence_hashes))
