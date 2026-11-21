"""四层报告组装、投递建议、auto_pass 重算与 PDF 校验回填。"""

from __future__ import annotations

import copy
import datetime as _datetime
import re
from dataclasses import dataclass
from pathlib import Path

from tools.domain.models import QualityFailure, TierResult
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.evaluation.llm_judge import resume_lines
from tools.infra.persistence.yaml_io import parse_simple_yaml

from .common import *
from .distinct import evaluate_distinct
from .eligible import PDF_CHECK_PENDING, evaluate_eligible, pdf_artifact_check
from .fit import _judge_candidates, _pending_rules, evaluate_fit
from .strong import evaluate_strong

_GAP_KIND_LABELS = {"evidence_missing": "证据缺口", "not_expressed": "未表达"}
_FACT_RULES = frozenset({"R1.1", "R1.2", "R1.7"})
_RECOMMENDATION_LABELS = {
    "apply": "建议投递",
    "strengthen": "建议补强后投递",
    "reconsider": "建议先补证据或更换更匹配目标",
    "fix_facts": "先核对事实与硬性条件",
}
_RECOMMENDATION_SUMMARIES = {
    "apply": "建议投递：合格层与对位层通过，事实追溯与岗位支撑已覆盖。",
    "strengthen": "建议补强后投递：仍有可在生成或内容取舍阶段改进的缺口。",
    "reconsider": "建议先补证据或更换更匹配目标：核心职责证据支撑不足。",
    "fix_facts": "先核对事实与硬性条件：存在不能靠重新生成消除的缺口。",
}



def _delivery_advice(
    tiers: dict[str, dict[str, object]],
    llm_pending: object = (),
) -> dict[str, object]:
    """把四层结论转成可执行的投递建议；只作参考，不改变 auto_pass，也不拦截投递。"""
    eligible = tiers.get("eligible") if isinstance(tiers.get("eligible"), dict) else {}
    fit = tiers.get("fit") if isinstance(tiers.get("fit"), dict) else {}
    strong = tiers.get("strong") if isinstance(tiers.get("strong"), dict) else {}
    distinct = tiers.get("distinct") if isinstance(tiers.get("distinct"), dict) else {}
    eligible_failures = [failure for failure in (eligible.get("failures") or []) if isinstance(failure, dict)]
    fit_failures = [failure for failure in (fit.get("failures") or []) if isinstance(failure, dict)]
    strong_failures = [failure for failure in (strong.get("failures") or []) if isinstance(failure, dict)]
    pending_rules = [str(rule) for rule in (llm_pending or [])]
    pdf_pending = _pdf_check_pending(eligible)
    # 只排除尚未核验的子项；已证实的超页/裁切和首屏缺口照常参与建议。
    real_eligible = [
        failure for failure in eligible_failures
        if not (
            failure.get("rule") == "R1.5"
            and failure.get("target") == "pdf"
            and failure.get("gap_kind") == PDF_CHECK_PENDING
        )
    ]
    pdf_metrics = eligible.get("metrics") or {}
    unchecked_pdf = "PDF 页数与裁切"
    if pdf_pending and pdf_metrics.get("pdf_pages") is not None:
        unchecked_pdf = "PDF 裁切"
    elif pdf_pending and pdf_metrics.get("clip_check") is not None:
        unchecked_pdf = "PDF 页数"
    gap_counts = {"evidence_missing": 0, "not_expressed": 0}
    for failure in fit_failures:
        if failure.get("rule") != "R2.2":
            continue
        kind = str(failure.get("gap_kind") or "")
        if kind in gap_counts:
            gap_counts[kind] += 1
    core_evidence = sum(
        1 for failure in fit_failures
        if failure.get("rule") == "R2.2" and failure.get("gap_kind") == "evidence_missing"
    )
    fact_failures = [failure for failure in real_eligible if str(failure.get("rule")) in _FACT_RULES]
    reasons: list[str] = []
    actions: list[str] = []
    if fact_failures:
        recommendation = "fix_facts"
        rules = sorted({str(failure.get("rule")) for failure in fact_failures})
        reasons.append("合格层存在事实/硬性条件缺口：" + "、".join(rules))
        reasons.extend(
            f"{failure.get('rule')} {failure.get('target', '')}：{failure.get('reason', '')}".strip()
            for failure in fact_failures[:3]
        )
        actions.append("在简历中心核对并确认职业档案与关键事实")
        actions.append("核对岗位硬性条件（年限/学历/资质）后再决定是否投递")
    elif core_evidence >= 2:
        recommendation = "reconsider"
        reasons.append(
            f"对位前三条职责中 {core_evidence} 项在证据池中支撑不足（证据池非 supported，含 partial/insufficient/conflict/未知），"
            "仅重排或改写正文无法补齐"
        )
        reasons.append(
            f"缺口计数：证据缺口 {gap_counts['evidence_missing']} 项、未表达 {gap_counts['not_expressed']} 项"
        )
        actions.append("补充覆盖核心职责的项目/成果证据卡后再生成")
        actions.append("或优先选择证据支撑更充分的目标岗位")
    elif fit_failures or real_eligible:
        recommendation = "strengthen"
        if gap_counts["not_expressed"]:
            reasons.append(
                f"有 {gap_counts['not_expressed']} 项对位缺口属于未表达：证据已有支撑，但正文未呈现或未进首屏"
            )
        if gap_counts["evidence_missing"]:
            reasons.append(
                f"有 {gap_counts['evidence_missing']} 项对位缺口属于证据缺失：证据池支撑不足"
            )
        other_fit = [failure for failure in fit_failures if str(failure.get("rule")) not in {"R2.2", "R2.3"}]
        if other_fit:
            reasons.append(f"对位层还有 {len(other_fit)} 项内容取舍或其他缺口")
        for must_have in (failure for failure in fit_failures if failure.get("rule") == "R2.3"):
            if must_have.get("gap_kind") == "evidence_missing":
                reasons.append("硬性要求支持率不足：存在证据缺口")
                actions.append("补充硬性要求相关的证据卡")
            elif must_have.get("gap_kind") == "not_expressed":
                reasons.append("硬性要求支持率不足：存在正文未表达")
                actions.append("把已支撑的硬性要求在正文表达出来并前置")
        if real_eligible:
            rules = sorted({str(failure.get("rule")) for failure in real_eligible})
            reasons.append("合格层仍有可修复缺口：" + "、".join(rules))
            if any(
                str(failure.get("rule")) == "R1.5" and failure.get("target") == "首屏"
                for failure in real_eligible
            ):
                reasons.append("其中包含首屏缺少定位摘要或核心经历条目")
        if gap_counts["not_expressed"]:
            actions.append("按对位缺口调整首屏选材：把已有证据前置到第一页并重新生成")
        if gap_counts["evidence_missing"]:
            actions.append("补充相关证据卡，或确认该要求是否可迁移表达")
        if any(str(failure.get("rule")) == "R2.4" for failure in fit_failures):
            actions.append("压缩或移除与目标 JD 无关的项目/经历后重新生成")
        if any(
            str(failure.get("rule")) == "R1.5" and failure.get("target") == "首屏"
            for failure in real_eligible
        ):
            actions.append("补齐首屏定位摘要与核心经历条目后重新生成")
        if any(
            str(failure.get("rule")) == "R1.5" and failure.get("target") == "pdf"
            for failure in real_eligible
        ):
            actions.append("把 PDF 压缩到两页并确认无裁切后重新导出")
        if any(str(failure.get("rule")) in {"R1.3", "R1.8"} for failure in real_eligible):
            actions.append("补齐缺失的经历时间/简历结构后重新生成")
        if not actions:
            actions.append("按质量报告逐项修复后重新生成")
    else:
        recommendation = "apply"
        unverified: list[str] = []
        if pdf_pending:
            unverified.append(unchecked_pdf)
        if pending_rules:
            unverified.append("LLM 判项（" + "、".join(pending_rules) + "）")
        if unverified:
            reasons.append(
                "已校验的合格层与对位层通过；未校验项：" + "、".join(unverified)
                + "，不按简历缺口处理"
            )
        else:
            reasons.append(
                "合格层与对位层通过：事实追溯、篇幅与职业档案一致性已覆盖，JD 职责/要求已在正文呈现"
            )
        if strong_failures:
            reasons.append(
                f"优质层仍有 {len(strong_failures)} 项表达/量化改进项，只作为提升命中率的可选优化，不影响投递"
            )
        if distinct.get("failures"):
            reasons.append("突出层未通过：可作为差异化补充，但不是投递前置条件")
        actions.append("准备投递 PDF 并核对目标岗位；最终发送仍由你确认")
    if pdf_pending and recommendation != "apply":
        reasons.append(f"{unchecked_pdf}尚未核验，不按简历内容缺口处理")
    summaries = dict(_RECOMMENDATION_SUMMARIES)
    if recommendation == "apply" and (pdf_pending or pending_rules):
        summaries["apply"] = "建议投递：除未校验项外，已校验的合格层与对位层通过。"
    return {
        "recommendation": recommendation,
        "label": _RECOMMENDATION_LABELS[recommendation],
        "advisory_only": True,
        "gap_counts": gap_counts,
        "summary": summaries[recommendation],
        "reasons": _unique(reasons),
        "next_actions": _unique(actions),
    }


def _tier_gap_tasks(tiers: dict[str, dict[str, object]], fit_gaps: list[dict]) -> list[str]:
    tasks: list[str] = []
    labels = {"eligible": "合格", "fit": "对位", "strong": "优质", "distinct": "突出"}
    for tier_name, tier in tiers.items():
        for failure in tier.get("failures", []):  # type: ignore[union-attr]
            if not isinstance(failure, dict):
                continue
            kind_label = _GAP_KIND_LABELS.get(str(failure.get("gap_kind", "")))
            suffix = f"（{kind_label}）" if kind_label else ""
            tasks.append(
                f"{labels.get(tier_name, tier_name)} {failure.get('rule', '')} {failure.get('target', '')}：{failure.get('reason', '')}{suffix}"
            )
    for gap in fit_gaps:
        tasks.append(f"对位缺口 {gap.get('item', '')}：{gap.get('reason', '')}")
    deduped: list[str] = []
    for task in tasks:
        if task not in deduped:
            deduped.append(task)
    return deduped


def build_quality_report(
    *,
    resume: str,
    trace: dict,
    career_profile: dict,
    cards: dict[str, dict],
    semantic_review: dict | None,
    job_context: dict,
    pdf_check: dict | None = None,
    highlights: list[dict] | None = None,
    judgments: dict | None = None,
    decisions: dict | None = None,
    judge_meta: dict[str, object] | None = None,
    config: QualityConfig | None = None,
    resume_version: str = "",
    job_profile_id: str = "",
    legacy_scores: dict[str, object] | None = None,
) -> dict[str, object]:
    config = config or load_quality_config()
    _first, _rest, mode = _split_first_screen(resume)
    eligible = evaluate_eligible(
        resume=resume,
        trace=trace,
        career_profile=career_profile,
        cards=cards,
        job_context=job_context,
        pdf_check=pdf_check,
        config=config,
        judgments=judgments,
    )
    fit = evaluate_fit(
        resume=resume, semantic_review=semantic_review, job_context=job_context,
        config=config, judgments=judgments,
    )
    strong = evaluate_strong(resume=resume, cards=cards, trace=trace, config=config, judgments=judgments)
    judge_candidates = _judge_candidates(judgments) if judgments is not None else None
    distinct = evaluate_distinct(
        resume=resume,
        highlights=highlights,
        candidates=judge_candidates,
        decisions=decisions,
        config=config,
    )
    evaluated = {
        "eligible": eligible.to_dict(),
        "fit": fit.to_dict(),
        "strong": strong.to_dict(),
        "distinct": distinct.to_dict(),
    }
    blocked_by = "" if eligible.passed else "eligible"
    if blocked_by:
        for tier in ("fit", "strong", "distinct"):
            evaluated[tier]["blocked_by"] = blocked_by
    llm_pending = _pending_rules(judgments)
    all_passed = all(bool(tier["passed"]) for tier in evaluated.values())
    report: dict[str, object] = {
        "schema_version": 1,
        "resume_version": resume_version,
        "job_profile_id": job_profile_id,
        "thresholds_version": config.version,
        "first_screen": {"mode": mode},
        "thresholds": copy.deepcopy(config.thresholds),
        "tiers": evaluated,
        "auto_pass": bool(all_passed and not llm_pending),
        "quality_judge": judge_meta or None,
        "llm_pending": llm_pending,
        "gap_tasks": _tier_gap_tasks(evaluated, list(fit.highlights)),
        "delivery_advice": _delivery_advice(evaluated, llm_pending),
        "legacy_scores": legacy_scores or {"rule_total": None, "llm_expression": None},
    }
    return report


def recompute_auto_pass(report: dict[str, object]) -> bool:
    tiers = report.get("tiers") or {}
    return bool(
        isinstance(tiers, dict)
        and tiers
        and all(bool(tier.get("passed")) for tier in tiers.values() if isinstance(tier, dict))
        and not report.get("llm_pending")
    )


def apply_pdf_check(report: dict[str, object], pdf_check: dict) -> dict[str, object]:
    """渲染 PDF 后回填 R1.5，并重算 auto_pass；不改变其余判项。"""
    updated = copy.deepcopy(report)
    tiers = updated.get("tiers") or {}
    eligible = tiers.get("eligible") if isinstance(tiers, dict) else None
    if not isinstance(eligible, dict):
        return updated
    thresholds = updated.get("thresholds") if isinstance(updated.get("thresholds"), dict) else DEFAULT_THRESHOLDS
    failures = [
        failure
        for failure in eligible.get("failures", [])
        # 只替换 PDF 页数/裁切相关项；首屏摘要/核心经历等可判缺口在回填后仍保留。
        if isinstance(failure, dict)
        and not (failure.get("rule") == "R1.5" and failure.get("target") == "pdf")
    ]
    new_pdf_failures, pdf_metrics = pdf_artifact_check(pdf_check, thresholds)
    eligible["failures"] = failures + [failure.to_dict() for failure in new_pdf_failures]
    metrics = eligible.get("metrics") if isinstance(eligible.get("metrics"), dict) else {}
    metrics.update(pdf_metrics)
    metrics["reason_count"] = len(eligible["failures"])
    eligible["metrics"] = metrics
    eligible["passed"] = not eligible["failures"]
    for name in ("fit", "strong", "distinct"):
        tier = tiers.get(name)
        if not isinstance(tier, dict):
            continue
        if eligible["passed"]:
            if tier.get("blocked_by") == "eligible":
                tier.pop("blocked_by", None)
        else:
            tier["blocked_by"] = "eligible"
    fit = tiers.get("fit") or {}
    updated["gap_tasks"] = _tier_gap_tasks(tiers, list(fit.get("highlights") or []))
    if "delivery_advice" in updated and _advice_recomputable(tiers):
        updated["delivery_advice"] = _delivery_advice(tiers, updated.get("llm_pending") or ())
    updated["auto_pass"] = recompute_auto_pass(updated)
    return updated
