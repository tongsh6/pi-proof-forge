"""简历计划：把选中的事实装配成"背景—关键工作—成果"的可渲染结构。

分层意图：
- `FactIndex` 提供事实；`fact_selector` 决定用哪些事实；
- 本模块只决定"这些事实放在哪个章节、按什么顺序、每块展示多少"；
- 渲染器只把计划排版为 Markdown，不再做选材与截断。

因此"每段工作经历只有 2 条职责""无时间整卡丢弃""配对失败即丢弃"这三个旧缺陷
在这一层被消除：事实已经由选材层决定，计划层只做章节归属与展示上限。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from tools.engines.generation.fact_index import Fact, FactIndex
from tools.domain.quality_text import has_quant_metric
from tools.engines.generation.fact_quality import presentable
from tools.engines.generation.fact_selector import has_impact_signal
from tools.engines.generation.fact_selector import SelectedFacts

# 展示上限只控制单块可读性（比旧版每段 2 条职责宽），完整事实仍留在证据卡与 trace。
MAX_WORK_DUTIES = 4
MAX_WORK_ACHIEVEMENTS = 2
MAX_PROJECT_WORK_ITEMS = 4
MAX_PROJECT_OUTCOMES = 3
MAX_CAPABILITIES = 4
MAX_EXTRAS = 2
MAX_STACK = 12
MAX_BACKGROUND_CHARS = 120


@dataclass(frozen=True)
class WorkBlock:
    work_id: str
    company: str
    title: str
    period: str
    scope: str
    duties: tuple[Fact, ...] = ()
    achievements: tuple[Fact, ...] = ()
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectBlock:
    card_id: str
    title: str
    period: str
    role: str
    background: str
    key_work: tuple[Fact, ...] = ()
    outcomes: tuple[Fact, ...] = ()
    work_company: str = ""
    stack: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityBlock:
    category: str
    description: str
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EducationBlock:
    school: str
    major: str
    degree: str
    period: str
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtraBlock:
    title: str
    description: str
    url: str
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResumePlan:
    summary: str = ""
    summary_fact_ids: tuple[str, ...] = ()
    capabilities: tuple[CapabilityBlock, ...] = ()
    work: tuple[WorkBlock, ...] = ()
    projects: tuple[ProjectBlock, ...] = ()
    stack: tuple[str, ...] = ()
    stack_fact_ids: tuple[str, ...] = ()
    education: tuple[EducationBlock, ...] = ()
    extras: tuple[ExtraBlock, ...] = ()
    untimed_projects: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()


def _squash(text: str) -> str:
    return " ".join(str(text or "").split())


def _truncate(text: str, limit: int) -> str:
    value = _squash(text)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip("，。；、,; ") + "…"


def _period_of(item: Mapping[str, object]) -> str:
    start = str(item.get("start") or "")
    end = "至今" if item.get("current") else str(item.get("end") or "")
    return " ~ ".join(part for part in (start, end) if part)


def _texts(index: FactIndex, fact_ids: tuple[str, ...], field_name: str) -> list[Fact]:
    return [
        fact
        for fact_id in fact_ids
        if (fact := index.get(fact_id)) is not None and fact.field == field_name
    ]


def _quant_first(values: list[Fact], *, limit: int, other_limit: int) -> list[Fact]:
    """量化成果优先展示，非量化最多 other_limit 条：避免技术细节稀释成果密度。"""
    quantified = [value for value in values if has_quant_metric(value.text)]
    others = [value for value in values if not has_quant_metric(value.text)][:other_limit]
    return (quantified + others)[:limit]


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        cleaned = _squash(value)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _dedupe_facts(values: list[Fact]) -> list[Fact]:
    # A duplicate visible string retains exactly the selected first occurrence.
    result: dict[str, Fact] = {}
    for value in values:
        if text := _squash(value.text):
            result.setdefault(text, value)
    return list(result.values())


def build_resume_plan(
    index: FactIndex,
    selected: SelectedFacts,
    career: Mapping[str, object],
    *,
    job_context: Mapping[str, object] | None = None,
    variant: str = "A",
    project_groups: Mapping[str, str] | None = None,
) -> ResumePlan:
    """把选中的事实装配为章节计划；不新增句子，只引用 fact_id 对应的原文。"""
    career = career or {}
    job_context = job_context or {}
    groups = dict(project_groups or {})
    used: list[str] = []

    no_priority = float("inf")

    def prioritized(facts: list[Fact]) -> tuple[Fact, ...]:
        # Only reorder the surviving, already-selected facts inside their group.
        return tuple(sorted(facts, key=lambda f: index.first_screen_priority.get(f.fact_id, no_priority)))

    def push(fact_ids: tuple[str, ...]) -> None:
        for fact_id in fact_ids:
            if fact_id not in used:
                used.append(fact_id)

    work_rows = sorted(
        [item for item in career.get("work") or [] if isinstance(item, dict) and item.get("id")],
        key=lambda item: str(item.get("start") or ""),
        reverse=True,
    )
    work_by_id = {str(item["id"]): item for item in work_rows}

    projects: list[ProjectBlock] = []
    untimed: list[str] = []
    for group_key, fact_ids in selected.projects.items():
        facts = [index.get(fact_id) for fact_id in fact_ids]
        facts = [fact for fact in facts if fact is not None]
        if not facts:
            continue
        # 同一项目簇的多张卡合并成一个项目块：标题用簇名（项目级），而不是
        # 其中某张 feature 卡的标题，避免"feature 挤掉项目"。
        is_group = group_key in groups.values() and group_key not in {
            fact.source_id for fact in facts
        }
        group_cards = {fact.source_id for fact in facts if fact.kind == "evidence"}
        merged_card = len(group_cards) > 1
        title = next((fact.text for fact in facts if fact.field == "title"), "")
        if merged_card and group_key:
            title = group_key
        if not title:
            title = facts[0].card_title or group_key
        card_id = facts[0].source_id
        # 标题/时间/场景/角色是结构性事实：从证据卡直接取，不依赖选材是否选中
        # （否则"项目缺时间"会让合格层 R1.3 恒失败）。
        group_card_ids = list(dict.fromkeys(fact.source_id for fact in facts if fact.kind == "evidence"))
        structured: dict[str, str] = {}
        for cid in group_card_ids:
            for fact in index.by_card(cid):
                structured.setdefault(fact.field, fact.text)
        context = structured.get("context", "") or next(
            (fact.text for fact in facts if fact.field == "context"), ""
        )
        role_text = structured.get("role_scope", "")
        period_text = structured.get("time_range", "")
        actions = [fact for fact in facts if fact.field == "actions" and presentable(fact.text, field="actions")]
        results = [fact for fact in facts if fact.field == "results" and presentable(fact.text, field="results")]
        stacks = [fact.text for fact in facts if fact.field == "stack"]
        work_id = facts[0].work_id
        company = _squash((work_by_id.get(work_id) or {}).get("company"))
        period = period_text
        if not period:
            untimed.append(card_id)
        push(tuple(fact.fact_id for fact in facts))
        projects.append(
            ProjectBlock(
                card_id=card_id,
                title=title,
                period=period,
                role=role_text,
                background=_truncate(context, MAX_BACKGROUND_CHARS) if presentable(context, field="context") else "",
                key_work=prioritized(_dedupe_facts(actions)[:MAX_PROJECT_WORK_ITEMS]),
                outcomes=prioritized(
                    _quant_first(
                        _dedupe_facts(results),
                        limit=MAX_PROJECT_OUTCOMES,
                        other_limit=2,
                    )
                ),
                work_company=company,
                stack=tuple(_dedupe(stacks)),
                fact_ids=tuple(fact.fact_id for fact in facts),
            )
        )
    # 跨章节去重：项目已呈现的事实不再在工作经历重复。
    project_texts: set[str] = set()
    for block in projects:
        project_texts.update(_squash(fact.text) for fact in (*block.key_work, *block.outcomes))

    work_blocks: list[WorkBlock] = []
    for item in work_rows:
        work_id = str(item["id"])
        # 任职范围与已确认职责是结构性事实：直接取已确认档案，不参与选材打分，
        # 否则"每段工作经历只有 2 条概括职责"会以另一种形式复发。
        scope_fact = index.get(f"personal_profile:career.work.{work_id}.scope:0")
        contribution_facts = [
            fact
            for fact in index.facts
            if fact.field == f"career.work.{work_id}.contributions"
        ]
        assigned = selected.work.get(work_id, ())
        action_fact_ids = tuple(fid for fid in assigned if (f := index.get(fid)) and f.field == "actions")
        result_fact_ids = tuple(fid for fid in assigned if (f := index.get(fid)) and f.field == "results")

        # 工作经历职责：已确认档案的 contributions 为主；档案过短时（如只有
        # 1 条），从证据卡 actions 里补最多 2 条通过闸门与影响信号的高价值行动。
        primary = [
            fact for fact in _dedupe_facts(contribution_facts)
            if _squash(fact.text) not in project_texts
        ]
        _duty_verb = re.compile(r"负责|主导|管理|组织|协调|推动|带领|牵头|设计|规划|把控|评审")
        supplement = [
            fact for fact in _dedupe_facts(_texts(index, action_fact_ids, "actions"))
            if _squash(fact.text) not in project_texts
            and _duty_verb.search(fact.text)
            and presentable(fact.text, field="actions")
        ][:2]
        duties = (primary + supplement)[:MAX_WORK_DUTIES]
        achievements = _quant_first([
            fact for fact in _dedupe_facts(_texts(index, result_fact_ids, "results"))
            if _squash(fact.text) not in project_texts
            and presentable(fact.text, field="results") and has_impact_signal(fact.text)
        ], limit=MAX_WORK_ACHIEVEMENTS, other_limit=2)
        scope = scope_fact.text if scope_fact else ""
        fact_ids = tuple(
            dict.fromkeys(
                (
                    *((scope_fact.fact_id,) if scope_fact else ()),
                    *(fact.fact_id for fact in contribution_facts),
                    *action_fact_ids,
                    *result_fact_ids,
                )
            )
        )
        push(fact_ids)
        if not (duties or achievements or scope):
            continue
        work_blocks.append(
            WorkBlock(
                work_id=work_id,
                company=_squash(item.get("company")),
                title=_squash(item.get("title")),
                period=_period_of(item),
                scope=scope,
                duties=prioritized(duties),
                achievements=prioritized(achievements),
                fact_ids=fact_ids,
            )
        )

    capabilities: list[CapabilityBlock] = []
    selected_cards = set(selected.projects)
    keywords = {str(term).casefold() for term in job_context.get("keywords") or []}
    skill_rows = [item for item in career.get("skills") or [] if isinstance(item, dict) and item.get("category")]
    skill_rows.sort(
        key=lambda item: (
            not bool(selected_cards.intersection(map(str, item.get("evidence_ids") or []))),
            not any(term in _squash(item.get("description")).casefold() for term in keywords),
        )
    )
    for item in skill_rows[:MAX_CAPABILITIES]:
        category_fact = index.get(f"personal_profile:career.skills.{item['id']}.category:0")
        description_fact = index.get(f"personal_profile:career.skills.{item['id']}.description:0")
        fact_ids = tuple(
            fact.fact_id for fact in (category_fact, description_fact) if fact is not None
        )
        if not fact_ids:
            continue
        push(fact_ids)
        capabilities.append(
            CapabilityBlock(
                category=_squash(item.get("category")),
                description=_squash(item.get("description")),
                fact_ids=fact_ids,
            )
        )

    capabilities.sort(key=lambda block: min(
        (index.first_screen_priority.get(fid, no_priority) for fid in block.fact_ids),
        default=no_priority,
    ))

    stack_pairs: list[tuple[str, str]] = []
    seen_stack: set[str] = set()
    for card_id in selected.projects:
        for fact in index.by_card(card_id):
            if fact.field != "stack" or fact.text in seen_stack:
                continue
            seen_stack.add(fact.text)
            stack_pairs.append((fact.text, fact.fact_id))
    stack_pairs.sort(key=lambda pair: pair[0].casefold() not in keywords)
    stack_pairs = stack_pairs[:MAX_STACK]
    stack = tuple(value for value, _fact_id in stack_pairs)
    ordered_stack_fact_ids = tuple(fact_id for _value, fact_id in stack_pairs)
    push(ordered_stack_fact_ids)

    education: list[EducationBlock] = []
    if career.get("education_visibility") != "omit":
        for item in career.get("education") or []:
            if not isinstance(item, dict) or not item.get("school") or not item.get("degree"):
                continue
            fact_ids = tuple(
                fact.fact_id
                for key in ("school", "major", "degree", "start", "end")
                if (fact := index.get(f"personal_profile:career.education.{item['id']}.{key}:0")) is not None
            )
            push(fact_ids)
            education.append(
                EducationBlock(
                    school=_squash(item.get("school")),
                    major=_squash(item.get("major")),
                    degree=_squash(item.get("degree")),
                    period=_period_of(item),
                    fact_ids=fact_ids,
                )
            )

    extras: list[ExtraBlock] = []
    for item in (career.get("extras") or [])[:MAX_EXTRAS]:
        if not isinstance(item, dict) or not item.get("title") or not item.get("description"):
            continue
        fact_ids = tuple(
            fact.fact_id
            for key in ("title", "description", "url")
            if (fact := index.get(f"personal_profile:career.extras.{item['id']}.{key}:0")) is not None
        )
        push(fact_ids)
        extras.append(
            ExtraBlock(
                title=_squash(item.get("title")),
                description=_squash(item.get("description")),
                url=_squash(item.get("url")),
                fact_ids=fact_ids,
            )
        )

    summary_fact = index.get("personal_profile:career.summary:0")
    summary = summary_fact.text if summary_fact else ""
    summary_fact_ids: tuple[str, ...] = ()
    if not summary and work_blocks:
        summary = work_blocks[0].scope or f"{work_blocks[0].company} {work_blocks[0].title}".strip()
        summary_fact_ids = tuple(
            fact_id for fact_id in work_blocks[0].fact_ids if (f := index.get(fact_id)) and f.field.endswith(".scope")
        )
    elif summary_fact:
        summary_fact_ids = (summary_fact.fact_id,)
    push(summary_fact_ids)

    return ResumePlan(
        summary=summary,
        summary_fact_ids=summary_fact_ids,
        capabilities=tuple(capabilities),
        work=tuple(work_blocks),
        projects=tuple(projects),
        stack=stack,
        stack_fact_ids=ordered_stack_fact_ids,
        education=tuple(education),
        extras=tuple(extras),
        untimed_projects=tuple(untimed),
        fact_ids=tuple(used),
    )
