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
