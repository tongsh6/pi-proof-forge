"""模板拼装与证据来源等级的呈现。

已采纳的 L3 职责保留主导/负责及原责任限定，来源等级不等于责任强度；
时间按推断精度呈现（年 / 年月）；L5 时间卡不进入正文。本模块只做确定性措辞
与排版，不引入新事实。
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from tools.domain.invariants import check_no_fabrication
from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.errors.exceptions import FabricationGuardError

STRONG_ROLE_WORDS = ("独立负责", "全权负责", "设计并落地", "负责", "主导", "牵头")
WEAK_ROLE_WORDS = {
    "独立负责": "参与",
    "全权负责": "参与",
    "设计并落地": "参与落地",
    "负责": "参与",
    "主导": "推动",
    "牵头": "参与",
}
_VERB_RE = re.compile(r"独立负责|全权负责|设计并落地|负责|主导|牵头")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def level_of(card: EvidenceCard | dict, field: str) -> str:
    """卡字段等级；缺省按 L1（有值）/L5（空值）。"""
    if isinstance(card, dict):
        value = card.get(f"{field}_provenance")
        level = value.get("level") if isinstance(value, dict) else card.get(f"{field}_level")
        if level:
            return str(level)
        raw = card.get(field) if field == "role_scope" else card.get("period", card.get("time_range"))
        return "L1" if str(raw or "").strip() else "L5"
    value = getattr(card, f"{field}_provenance", None)
    if isinstance(value, dict) and value.get("level"):
        return str(value["level"])
    raw = getattr(card, "period", "") if field == "time_range" else ""
    return "L1" if str(raw).strip() else "L5"


def precision_of(card: EvidenceCard | dict, field: str = "time_range") -> str:
    provenance = card.get(f"{field}_provenance") if isinstance(card, dict) else getattr(card, f"{field}_provenance", None)
    if isinstance(provenance, dict) and provenance.get("precision"):
        return str(provenance["precision"])
    return "day"


def visible_in_resume(card: EvidenceCard | dict) -> bool:
    """R1.3/D1：时间字段为 L5 的卡不得进入正文。

    生成主路径传入带字段等级的卡片字典，按 L5 严格过滤；旧编排层/引擎的
    EvidenceCard 若没有任何 provenance（历史夹具/旧数据），保持兼容不过滤，
    避免把“未提供等级”误判为“已确认无依据”。
    """
    if isinstance(card, dict):
        return level_of(card, "time_range") != "L5"
    explicit = getattr(card, "time_range_provenance", None)
    if isinstance(explicit, dict) and str(explicit.get("level", "")).upper() == "L5":
        return False
    return True


def format_time(value: str, level: str, precision: str) -> str:
    """按等级/精度呈现时间；L5 返回空，年精度只保留起始年。"""
    text = " ".join(str(value or "").split())
    if not text or level == "L5":
        return ""
    if precision == "year":
        years = _YEAR_RE.findall(text)
        if years:
            return years[0]
    return text


def role_text(role: str, level: str) -> str:
    """保留已采纳职责的原义；L5 无依据时不写角色。"""
    text = " ".join(str(role or "").split())
    if not text or level == "L5":
        return ""
    return text


def downgrade_wording(text: str, level: str) -> str:
    """保留已采纳的 L1/L3/L4 原文；无职责依据的旧路径保持兼容处理。"""
    value = " ".join(str(text or "").split())
    if not value or level in {"L1", "L3", "L4"}:
        return value
    return _VERB_RE.sub(lambda match: WEAK_ROLE_WORDS.get(match.group(0), "参与"), value)


def cited_card_ids(semantic_report: dict | None) -> list[str]:
    if not isinstance(semantic_report, dict):
        return []
    facts = semantic_report.get("facts") if isinstance(semantic_report.get("facts"), dict) else {}
    ordered: list[str] = []

    def collect(citations: object) -> None:
        for citation in citations if isinstance(citations, list) else []:
            if not isinstance(citation, dict):
                continue
            fact = facts.get(citation.get("fact_id", ""))
            source_id = str((fact or {}).get("source_id", ""))
            if source_id and source_id not in ordered:
                ordered.append(source_id)

    for assessment in semantic_report.get("assessments") or []:
        if not isinstance(assessment, dict):
            continue
        collect(assessment.get("citations"))
        for check in assessment.get("checks") or []:
            if isinstance(check, dict):
                collect(check.get("citations"))
    return ordered


def order_cards_for_resume(
    cards: Sequence[EvidenceCard | dict],
    semantic_report: dict | None,
    *,
    minimum_projects: int = 2,
    maximum_projects: int = 4,
) -> list:
    """JD 引用的卡优先、无关经历压缩；至少保留 minimum_projects 条。"""
    cited = cited_card_ids(semantic_report)
    if not cited:
        return list(cards)[:maximum_projects]
    by_id = {str(card.get("id") if isinstance(card, dict) else card.id): card for card in cards}
    ordered = [by_id[card_id] for card_id in cited if card_id in by_id]
    remaining = [card for card in cards if card not in ordered]
    if len(ordered) < minimum_projects:
        ordered.extend(remaining[: minimum_projects - len(ordered)])
    return ordered[:maximum_projects]


_ASSOC_ASCII = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{1,}")
_ASSOC_CJK = re.compile(r"[\u4e00-\u9fff]{2,}")
_ASSOC_GENERIC = {
    "系统", "业务", "功能", "相关", "开发", "设计", "实现", "支持", "完成", "通过",
    "包括", "项目", "工作", "数据", "服务", "平台", "管理", "优化", "治理", "改造",
    "建设", "方案", "流程", "机制", "能力", "经验", "进行", "以及", "一个", "多个",
}


def _assoc_tokens(text: str) -> set[str]:
    value = str(text or "")
    tokens = {token.casefold() for token in _ASSOC_ASCII.findall(value)}
    for run in _ASSOC_CJK.findall(value):
        tokens.update(run[index:index + 2] for index in range(len(run) - 1))
    return tokens


def _assoc_score(left: set[str], right: set[str]) -> int:
    return sum(1 if token in _ASSOC_GENERIC else 2 for token in left & right)


def _has_quant(value: str) -> bool:
    from tools.domain.quality_text import has_quant_metric

    return has_quant_metric(value)


def pair_actions_results(
    actions: Sequence[str],
    results: Sequence[str],
    *,
    max_bullets: int = 3,
    max_results_per_bullet: int = 2,
) -> tuple[list[tuple[str, list[str]]], list[str], list[str]]:
    """把同卡的行动与成果按词面关联配对；无关联的保持未配对，不按索引硬拼。

    返回 (配对列表[(action, [result...])], 未配对 actions, 未配对 results)。
    配对仅供逐条呈现，不引入因果措辞；结果仍保留原文。
    """
    action_pool = [str(action).strip() for action in actions if str(action).strip()]
    result_pool = [str(result).strip() for result in results if str(result).strip()]
    if not action_pool or not result_pool:
        return [], action_pool, result_pool
    result_tokens = [_assoc_tokens(result) for result in result_pool]
    # 相关度：词面交集为主，量化成果在同分时优先；同时保留原始顺序用于稳定排序。
    ranked_actions: list[tuple[int, int, int, str]] = []
    for action_index, action in enumerate(action_pool):
        tokens = _assoc_tokens(action)
        scored = [
            (_assoc_score(tokens, result_tokens[result_index]), int(_has_quant(result_pool[result_index])), -result_index, result_index)
            for result_index in range(len(result_pool))
        ]
        scored = [row for row in scored if row[0] >= 2]
        scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
        if scored:
            top_score = scored[0][0]
            has_quant = any(row[1] for row in scored)
            ranked_actions.append((-top_score, -int(has_quant), action_index, action))
    ranked_actions.sort()
    used_results: set[int] = set()
    pairs: list[tuple[str, list[str]]] = []
    used_actions: set[int] = set()
    for _neg_score, _neg_quant, action_index, action in ranked_actions:
        if action_index in used_actions or len(pairs) >= max_bullets:
            continue
        tokens = _assoc_tokens(action)
        candidates = [
            (_assoc_score(tokens, result_tokens[result_index]), int(_has_quant(result_pool[result_index])), -result_index, result_index)
            for result_index in range(len(result_pool))
            if result_index not in used_results and _assoc_score(tokens, result_tokens[result_index]) >= 2
        ]
        candidates.sort(key=lambda row: (-row[0], -row[1], row[2]))
        chosen = [row[3] for row in candidates[:max_results_per_bullet]]
        if not chosen:
            continue
        used_actions.add(action_index)
        used_results.update(chosen)
        pairs.append((action, [result_pool[index] for index in chosen]))
    unpaired_actions = [action for index, action in enumerate(action_pool) if index not in used_actions]
    unpaired_results = [result for index, result in enumerate(result_pool) if index not in used_results]
    return pairs, unpaired_actions, unpaired_results


def paired_bullet_text(action: str, results: Sequence[str]) -> str:
    """行动在前、成果在后；用冒号/间隔号连接，trace 分段由 claims 覆盖。"""
    action_text = " ".join(str(action).split()).rstrip("。；;,， ")
    parts = [" ".join(str(result).split()).rstrip("。；;,， ") for result in results if str(result).strip()]
    return f"{action_text}：{' · '.join(parts)}" if parts else action_text


def first_screen_priority(cards: Sequence[EvidenceCard | dict]) -> list:
    """首屏保留语义首卡；其余卡按可配对量化成果数优先，让关键结果尽量落在第一页。"""
    def score(card: EvidenceCard | dict) -> tuple[int, int]:
        actions = list((card.get("actions") if isinstance(card, dict) else card.actions) or [])
        results = list((card.get("results") if isinstance(card, dict) else card.results) or [])
        pairs, _, _ = pair_actions_results(actions, results)
        quant = sum(1 for _action, rows in pairs if any(_has_quant(row) for row in rows))
        return (quant, len(pairs))
    values = list(cards)
    indexed = list(enumerate(values))
    indexed.sort(key=lambda item: (-score(item[1])[0], -score(item[1])[1], item[0]))
    return [card for _index, card in indexed]


class TemplateAssembler:
    def generate(
        self,
        report: MatchingReport,
        cards: Sequence[EvidenceCard],
        version: str,
    ) -> ResumeOutput:
        visible = [card for card in cards if visible_in_resume(card)]
        if not visible:
            raise FabricationGuardError(version)

        lines = [f"# Resume {version}", "", "## Highlights"]
        for card in visible:
            time_level = level_of(card, "time_range")
            role_level = level_of(card, "role_scope")
            period = format_time(card.period, time_level, precision_of(card))
            lines.append(f"- {card.title}" + (f"（{period}）" if period else ""))
            role = role_text(getattr(card, "role_scope", ""), role_level)
            if role:
                lines.append(f"  角色：{role}")
            for result in card.results:
                lines.append("  - " + downgrade_wording(result, role_level))

        content = "\n".join(lines).strip() + "\n"
        check_no_fabrication(content, visible)

        return ResumeOutput(
            version=version,
            job_profile_id=report.job_profile_id,
            content=content,
            format="markdown",
        )
