"""按精确正向引用与正文预算选择事实；未提供细粒度评审时保持输入顺序。

选择与去重先于覆盖计算。选中的每个身份只对应自身原文，不能由同卡、
同父要求或同文兄弟事实代替；计划层直接保留本模块交付的正文事实。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from tools.engines.generation.fact_index import Fact, FactIndex, _requirement_map
from tools.engines.generation.fact_quality import judge_fact_text

MAX_PROJECTS = 3
PROJECT_FIELD_LIMITS = {"actions": 3, "results": 2}


@dataclass(frozen=True)
class SelectionBudget:
    """章节配额；min 是希望保留的下限，所有选择仍受全篇与正文上限约束。"""

    min_work_facts: int = 3
    max_work_facts: int = 8
    max_project_facts: int = 8
    max_total_facts: int = 36


@dataclass(frozen=True)
class SelectedFacts:
    work: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    projects: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    profile_highlights: tuple[str, ...] = ()
    excluded: Mapping[str, str] = field(default_factory=dict)
    total: int = 0


def _support_value(
    facts: list[Fact],
    requirements: Mapping[str, tuple[tuple[str, int], ...]],
) -> int:
    """同一候选每父项取最大值；没有全局已覆盖父项/子项状态。"""
    parents: dict[str, int] = {}
    for fact in facts:
        for parent, weight in requirements.get(fact.fact_id, ()):
            parents[parent] = max(weight, parents.get(parent, 0))
    return sum(parents.values())


def _take(
    facts: list[Fact],
    maximum: int,
    requirements: Mapping[str, tuple[tuple[str, int], ...]],
    *,
    chosen: list[Fact] | None = None,
    field_limits: Mapping[str, int] | None = None,
) -> list[Fact]:
    """在单块预算内按父项边际选择，互补正引用先于未引用补充。"""
    result = list(chosen or ())
    while len(result) < maximum:
        used = {fact.fact_id for fact in result}
        visible = {(fact.field, " ".join(fact.text.split())) for fact in result}
        candidates = [
            fact for fact in facts
            if fact.fact_id not in used
            and (fact.field, " ".join(fact.text.split())) not in visible
            and (field_limits is None
                 or sum(row.field == fact.field for row in result) < field_limits[fact.field])
        ]
        if not candidates:
            break
        current = _support_value(result, requirements)
        best = min(candidates, key=lambda fact: (
            -(_support_value([*result, fact], requirements) - current),
            -bool(requirements.get(fact.fact_id)),
            fact.order,
        ))
        result.append(best)
    return result


def select_facts(
    index: FactIndex,
    *,
    budget: SelectionBudget | None = None,
    max_projects: int = MAX_PROJECTS,
    project_groups: dict[str, str] | None = None,
    semantic_report: dict | None = None,
) -> SelectedFacts:
    budget = budget or SelectionBudget()
    if not index.facts:
        return SelectedFacts()

    requirements = _requirement_map(semantic_report)
    granular = (
        isinstance(semantic_report, dict)
        and isinstance(semantic_report.get("requirements"), list)
        and isinstance(semantic_report.get("assessments"), list)
    )
    total_limit = max(0, budget.max_total_facts)
    project_limit = max(0, min(max_projects, MAX_PROJECTS))
    block_limit = max(0, budget.max_project_facts)
    verdicts = {
        fact.fact_id: judge_fact_text(
            fact.text, field=fact.field,
            strict=fact.kind != "profile" and fact.field != "results",
        )
        for fact in index.facts
    }
    allowed = {fid for fid, verdict in verdicts.items() if verdict.presentable}

    # 合并同一项目后才分配 3 行动 / 2 成果。结构上下文由 plan 读取，
    # 不产生 occurrence，因而既不占正文名额也不授引用覆盖。
    groups = project_groups or {}
    grouped: dict[str, list[Fact]] = {}
    for card_id in index.card_ids:
        key = groups.get(card_id) or card_id
        grouped.setdefault(key, []).extend(
            fact for fact in index.by_card(card_id)
            if fact.fact_id in allowed and fact.field in PROJECT_FIELD_LIMITS
        )
    remaining = dict(grouped)
    projects: dict[str, list[Fact]] = {}
    used: set[str] = set()

    # 先选真正新增的正引用；未引用补充不能先耗尽其他项目的引用预算。
    while remaining and len(projects) < project_limit and len(used) < total_limit:
        proposals = []
        capacity = min(block_limit, total_limit - len(used))
        for position, (key, facts) in enumerate(remaining.items()):
            candidates = [
                fact for fact in facts
                if fact.fact_id not in used and (not granular or requirements.get(fact.fact_id))
            ]
            chosen = _take(candidates, capacity, requirements,
                           field_limits=PROJECT_FIELD_LIMITS)
            if chosen:
                proposals.append((_support_value(chosen, requirements), position, key, chosen))
        if not proposals:
            break
        gain, _position, key, chosen = min(proposals, key=lambda row: (-row[0], row[1]))
        if granular and gain == 0:
            break
        projects[key] = chosen
        used.update(fact.fact_id for fact in chosen)
        del remaining[key]

    # 工作块先取得希望保留的最小份额；只会新增当前剩余预算容许的身份，
    # 已在项目中选择的事实不重复计费。后续装配仍按原章节职责处理。
    work: dict[str, list[Fact]] = {}
    work_candidates = {
        work_id: [fact for fact in index.by_work(work_id) if fact.fact_id in allowed]
        for work_id in index.work_ids
    }

    def fill_work(maximum: int) -> None:
        for work_id, facts in work_candidates.items():
            current = work.get(work_id, [])
            candidates = [
                fact for fact in facts
                if fact.fact_id in used or len(used) < total_limit
            ]
            ordered = _take(candidates, max(0, maximum), requirements, chosen=current)
            kept = list(current)
            kept_ids = {fact.fact_id for fact in kept}
            for fact in ordered:
                if fact.fact_id in kept_ids:
                    continue
                if fact.fact_id not in used and len(used) >= total_limit:
                    continue
                kept.append(fact)
                kept_ids.add(fact.fact_id)
                used.add(fact.fact_id)
            if kept:
                work[work_id] = kept

    fill_work(min(budget.min_work_facts, budget.max_work_facts))

    # 对已选项目补足可读的原文，仍沿同一预算、去重与稳定顺序。
    for key, chosen in projects.items():
        capacity = min(block_limit, len(chosen) + total_limit - len(used))
        expanded = _take(grouped[key], capacity, requirements, chosen=chosen,
                         field_limits=PROJECT_FIELD_LIMITS)
        projects[key] = expanded
        used.update(fact.fact_id for fact in expanded)

    # 无直接引用背景最多一项，不制造任何要求支持；无报告的显式输入
    # 已在上面的同一选择循环中按原顺序处理，无另一套词表评分路径。
    if granular and len(projects) < project_limit and len(used) < total_limit:
        for key, facts in remaining.items():
            if any(requirements.get(fact.fact_id) for fact in facts):
                continue
            chosen = _take(facts, min(block_limit, total_limit - len(used)),
                           requirements, field_limits=PROJECT_FIELD_LIMITS)
            if chosen:
                projects[key] = chosen
                used.update(fact.fact_id for fact in chosen)
                break

    fill_work(budget.max_work_facts)
    highlights = tuple(
        fact.fact_id for fact in index.facts
        if fact.kind == "profile" and fact.fact_id in used
        and fact.field.endswith((".scope", ".contributions", ".summary"))
    )
    excluded: dict[str, str] = {}
    for fact in index.facts:
        if fact.fact_id in used:
            continue
        verdict = verdicts[fact.fact_id]
        if not verdict.presentable:
            excluded[fact.fact_id] = f"not_presentable:{verdict.reason}"
        elif len(used) >= total_limit:
            excluded[fact.fact_id] = "budget_exhausted"
        elif fact.support_weight == 0 and fact.field in {"tags", "time_range", "stack"}:
            excluded[fact.fact_id] = "structural_field_not_selected"
        else:
            excluded[fact.fact_id] = "below_block_quota"
    return SelectedFacts(
        work={key: tuple(fact.fact_id for fact in facts) for key, facts in work.items()},
        projects={key: tuple(fact.fact_id for fact in facts) for key, facts in projects.items()},
        profile_highlights=highlights,
        excluded=excluded,
        total=len(used),
    )
