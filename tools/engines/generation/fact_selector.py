"""事实级选材：按 JD 需求覆盖与事实价值分配，替代"按卡硬截断"。

旧机制的两个结构性缺陷在这里被替换：
1. 选材单元从"证据卡"变为"事实"，卡不再决定 bullet 数量上限；
2. 排序发生在分配之前——先给每段经历/每个项目保留最低配额，再按边际价值补充，
   不会出现"先截断到 3 张卡、再排序"导致的高价值事实永远进不来。

本模块只做选择，不改写事实；`SelectedFacts` 里的每个 fact_id 都能回到
`FactIndex` 的原始文本与来源。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from tools.engines.generation.fact_index import Fact, FactIndex
from tools.engines.generation.fact_quality import judge_fact_text

# 开发任务清单/技术待办：事实为真，但不是简历语言，选材时降权而非硬拒绝。
_TASK_LIKE_RE = re.compile(
    r"可参考|未考虑|需要添加|需要修改|需要补充|逐步形成|推广使用|统一使用接口|"
    r"添加参数|改为调用|去掉易误导|按需调整|封装\w{0,20}参数|检查\w{0,20}事务|"
    r"番茄钟|工时|打卡|日报|周报|初步完成|待验证|进行中|"
    r"内存达到|占用率|查询SQL|监控指标|统一使用|状态为待|调用.*的.*接口"
)
# 类/方法级标识符（GetInfoTypesAction、SaveInfoTypeAction 等）：只在非标题字段降权。
_METHOD_IDENT_RE = re.compile(
    r"[A-Z][a-zA-Z0-9]*(?:Action|Service|Manager|Handler|Controller|Repository|DTO|Impl|Task)(?![a-z])"
)

# 量化成果必须同时表达"变化/影响"，否则"内存达到 85% 占用"这类监控数据
# 会被当成成果。
_IMPACT_RE = re.compile(
    r"提升|降低|减少|缩短|降至|提升至|从.+?到|→|覆盖|支撑|节约|节省|下降|增长|不超过|降低到"
)

_SCALE_RE = re.compile(
    r"\d[\d,.]*\s*(?:[–-]\s*\d+\s*)?(?:\+|以上|余)?\s*(?:人|个|家|款|项|条|套|台|次|万|亿|品牌|系统|模块|服务|文件)"
)
_ROLE_WEIGHT = {"owner": 1.0, "lead": 0.7, "participate": 0.4, "unknown": 0.2}
_FIELD_WEIGHT = {
    "results": 1.0,
    "actions": 0.8,
    "title": 0.5,
    "context": 0.45,
    "role_scope": 0.35,
    "stack": 0.2,
    "time_range": 0.1,
    "tags": 0.0,
}


@dataclass(frozen=True)
class SelectionBudget:
    """章节配额；min 是保底，max 是单块上限，max_total 是全篇上限。"""

    min_work_facts: int = 3
    max_work_facts: int = 8
    min_project_facts: int = 2
    max_project_facts: int = 8
    max_total_facts: int = 36


_TECHNICAL_TERMS = (
    "架构", "设计", "性能", "存储", "索引", "分布式", "重构", "协议",
    "并发", "一致性", "容量", "改造", "状态机", "策略", "领域事件", "锁",
    "迁移", "查询", "接口", "缓存", "事务",
)
_DELIVERY_TERMS = (
    "团队", "交付", "协作", "品牌", "规模", "迭代", "上线", "运营", "客户",
    "流程", "治理", "Feature", "跨职能", "从 0 到 1", "带", "推动", "组织",
)


@dataclass(frozen=True)
class VariantWeights:
    """A/B 变体的差异来自事实打分权重与领域词偏好，而不是措辞替换。"""

    requirement: float = 3.0
    quant: float = 2.0
    scale: float = 1.2
    role: float = 1.0
    terms: tuple[str, ...] = ()
    term_bonus: float = 2.0


# 技术深度版：架构、机制、性能、存储类事实优先。
# requirement 权重高于 quant：岗位相关性优先于"数字漂亮"的事实，否则
# 与 JD 无关的量化内容会挤进来（评估层 R2.4「未映射到任何 JD 条目」）。
TECHNICAL_DEPTH = VariantWeights(requirement=4.5, quant=4.0, scale=0.8, role=0.8, terms=_TECHNICAL_TERMS)
# 业务交付版：规模、团队、治理、交付闭环类事实优先。
DELIVERY_OWNER = VariantWeights(requirement=4.5, quant=2.2, scale=2.6, role=2.2, terms=_DELIVERY_TERMS)

VARIANTS: dict[str, VariantWeights] = {"A": TECHNICAL_DEPTH, "B": DELIVERY_OWNER}


@dataclass(frozen=True)
class SelectedFacts:
    work: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    projects: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    profile_highlights: tuple[str, ...] = ()
    excluded: Mapping[str, str] = field(default_factory=dict)
    total: int = 0


def _scale_signal(text: str) -> float:
    return 1.0 if _SCALE_RE.search(text) else 0.0


def has_impact_signal(text: str) -> bool:
    """成果必须表达变化/规模，否则"查询 SQL：xxx"这类日志痕迹不能当成果。"""
    value = str(text or "")
    return bool(_IMPACT_RE.search(value) or _SCALE_RE.search(value))


def task_like_penalty(text: str) -> float:
    """开发任务清单/类方法标识符的降权值；正常职责描述不受影响。"""
    value = str(text or "")
    penalty = 0.0
    if _TASK_LIKE_RE.search(value):
        penalty += 1.8
    if _METHOD_IDENT_RE.search(value):
        penalty += 2.2
    return penalty


def score_fact(fact: Fact, weights: VariantWeights) -> float:
    term_hit = 1.0 if any(term in fact.text for term in weights.terms) else 0.0
    structural = fact.field.rsplit(".", 1)[-1] in {"title", "stack", "time_range", "role_scope", "tags"}
    penalty = 0.0 if structural else task_like_penalty(fact.text)
    quant_hit = 1.0 if (fact.has_quant and _IMPACT_RE.search(fact.text)) else 0.0
    return (
        weights.requirement * fact.support_weight
        + weights.quant * quant_hit
        + weights.scale * _scale_signal(fact.text)
        + weights.role * _ROLE_WEIGHT.get(fact.role_strength, 0.2)
        + weights.term_bonus * term_hit
        + _FIELD_WEIGHT.get(fact.field.rsplit(".", 1)[-1], 0.0)
        - penalty
    )


def _ordered(facts: list[Fact], scores: Mapping[str, float]) -> list[Fact]:
    """引用事实优先，其次价值分，最后来源顺序（稳定）。"""
    return sorted(
        facts,
        key=lambda fact: (
            -fact.support_weight,
            -scores.get(fact.fact_id, 0.0),
            fact.order,
        ),
    )


def _take(
    facts: list[Fact],
    minimum: int,
    maximum: int,
    scores: Mapping[str, float],
    *,
    floor: float = 0.6,
) -> list[str]:
    """取事实：引用事实优先、价值降序；低于 floor 的事实不选（宁缺毋滥）。

    `minimum` 只表达"希望保留的下限"，不能靠低价值事实凑数——工作经历宁可
    少一条成果，也不该写"内存达到 85% 占用""查询 SQL：xxx"这类日志痕迹。
    """

    ordered = [fact for fact in _ordered(facts, scores) if scores.get(fact.fact_id, 0.0) >= floor]
    return [fact.fact_id for fact in ordered[:maximum]]


def select_facts(
    index: FactIndex,
    *,
    budget: SelectionBudget | None = None,
    weights: VariantWeights | None = None,
    max_projects: int = 4,
    project_groups: dict[str, str] | None = None,
) -> SelectedFacts:
    budget = budget or SelectionBudget()
    weights = weights or TECHNICAL_DEPTH
    if not index.facts:
        return SelectedFacts()

    verdicts = {
        fact.fact_id: judge_fact_text(fact.text, field=fact.field, strict=fact.kind != "profile")
        for fact in index.facts
    }
    allowed = {fact_id for fact_id, verdict in verdicts.items() if verdict.presentable}
    scores = {fact.fact_id: score_fact(fact, weights) for fact in index.facts if fact.fact_id in allowed}

    work_selected: dict[str, tuple[str, ...]] = {}
    for work_id in index.work_ids:
        facts = [fact for fact in index.by_work(work_id) if fact.fact_id in allowed]
        if not facts:
            continue
        chosen = _take(facts, budget.min_work_facts, budget.max_work_facts, scores)
        if chosen:
            work_selected[work_id] = tuple(chosen)

    card_rank: list[tuple[float, int, str]] = []
    for position, card_id in enumerate(index.card_ids):
        facts = [fact for fact in index.by_card(card_id) if fact.fact_id in allowed]
        if not facts:
            continue
        coverage = sum(weights.requirement * fact.support_weight for fact in facts)
        best = max(scores.get(fact.fact_id, 0.0) for fact in facts)
        card_rank.append((-(coverage + best), position, card_id))
    card_rank.sort()

    # 同一 project_key 的多张卡共享一个项目名额：先合并事实，再按项目切分，
    # 避免"feature 级卡挤掉项目级卡"。
    groups = project_groups or {}
    grouped: dict[str, list[str]] = {}
    for card_id in index.card_ids:
        key = groups.get(card_id) or card_id
        grouped.setdefault(key, []).append(card_id)

    ranked_groups: list[tuple[float, int, str, list[str]]] = []
    for position, (key, card_ids) in enumerate(grouped.items()):
        group_facts = [
            fact
            for cid in card_ids
            for fact in index.by_card(cid)
            if fact.fact_id in allowed
        ]
        if not group_facts:
            continue
        coverage = sum(weights.requirement * fact.support_weight for fact in group_facts)
        best = max(scores.get(fact.fact_id, 0.0) for fact in group_facts)
        # 项目簇内卡越多说明该项目的证据越厚，优先给项目名额。
        ranked_groups.append((-(coverage + best + 0.6 * len(card_ids)), position, key, card_ids))
    ranked_groups.sort()

    projects: dict[str, tuple[str, ...]] = {}
    for _neg_score, _position, key, card_ids in ranked_groups[:max_projects]:
        group_facts = [
            fact for cid in card_ids for fact in index.by_card(cid) if fact.fact_id in allowed
        ]
        chosen = _take(group_facts, budget.min_project_facts, budget.max_project_facts, scores)
        if chosen:
            projects[key] = tuple(chosen)

    # 全篇预算：先保护每块的最低配额，再按价值从低到高裁掉可选项。
    protected: set[str] = set()
    for work_id, fact_ids in work_selected.items():
        protected.update(fact_ids[: budget.min_work_facts])
    for card_id, fact_ids in projects.items():
        protected.update(fact_ids[: budget.min_project_facts])

    used: list[str] = []
    for fact_ids in [*work_selected.values(), *projects.values()]:
        for fact_id in fact_ids:
            if fact_id not in used:
                used.append(fact_id)

    if len(used) > budget.max_total_facts:
        order_of = {fact.fact_id: fact.order for fact in index.facts}
        removable = sorted(
            (fact_id for fact_id in used if fact_id not in protected),
            key=lambda fact_id: (scores.get(fact_id, 0.0), -order_of.get(fact_id, 0)),
        )
        while len(used) > budget.max_total_facts and removable:
            drop = removable.pop(0)
            used.remove(drop)

    kept = set(used)
    work_final = {
        work_id: tuple(fact_id for fact_id in fact_ids if fact_id in kept)
        for work_id, fact_ids in work_selected.items()
    }
    projects_final = {
        card_id: tuple(fact_id for fact_id in fact_ids if fact_id in kept)
        for card_id, fact_ids in projects.items()
    }
    work_final = {key: value for key, value in work_final.items() if value}
    projects_final = {key: value for key, value in projects_final.items() if value}

    highlights = tuple(
        fact.fact_id
        for fact in index.facts
        if fact.kind == "profile"
        and fact.fact_id in kept
        and fact.field.endswith((".scope", ".contributions", ".summary"))
    )

    excluded: dict[str, str] = {}
    for fact in index.facts:
        if fact.fact_id in kept:
            continue
        verdict = verdicts.get(fact.fact_id)
        if verdict is not None and not verdict.presentable:
            excluded[fact.fact_id] = f"not_presentable:{verdict.reason}"
            continue
        if len(used) >= budget.max_total_facts:
            excluded[fact.fact_id] = "budget_exhausted"
        elif fact.support_weight == 0 and fact.field in {"tags", "time_range", "stack"}:
            excluded[fact.fact_id] = "structural_field_not_selected"
        else:
            excluded[fact.fact_id] = "below_block_quota"

    return SelectedFacts(
        work=work_final,
        projects=projects_final,
        profile_highlights=highlights,
        excluded=excluded,
        total=len(kept),
    )
