"""R2 对位层：JD 要求 × 证据池/正文的语义对位矩阵与缺口分类。"""

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


def _pending_rules(judgments: dict | None) -> list[str]:
    if not isinstance(judgments, dict):
        return list(PHASE_A_LLM_PENDING)
    sections = set(judgments.get("judged_sections") or [])
    pending: list[str] = []
    for section, rule in (("r1_4", "R1.4"), ("r2_1", "R2.1"), ("r3_1", "R3.1"),
                          ("r3_5", "R3.5"), ("r4_1", "R4.1")):
        if section not in sections:
            pending.append(rule)
    return pending


def _judge_candidates(judgments: dict | None) -> list[dict[str, object]]:
    if not isinstance(judgments, dict) or "r4_1" not in (judgments.get("judged_sections") or []):
        return []
    result: list[dict[str, object]] = []
    for item in judgments.get("r4_1", []) or []:
        if not isinstance(item, dict):
            continue
        bullet = item.get("bullet")
        jd_id = str(item.get("jd_item_id", ""))
        if not isinstance(bullet, int) or not jd_id:
            continue
        result.append({**item, "highlight_id": f"hl_b{bullet}_{jd_id}"})
    return result


def _fit_matrix(resume: str, semantic_review: dict | None, judgments: dict | None = None) -> tuple[list[dict[str, object]], list[dict]]:
    if not isinstance(semantic_review, dict) or semantic_review.get("mode") != "semantic":
        return [], []
    bullets, _marker = _bullet_rows(resume)
    rows: list[dict[str, object]] = []
    gap_rows: list[dict] = []
    for requirement in semantic_review.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        resume_status = str(requirement.get("resume_status", "not_present"))
        status = "supported" if resume_status == "supported" else "weak" if resume_status == "partial" else "absent"
        bullet_refs: list[str] = []
        first_screen = False
        for citation in requirement.get("citations", []) or []:
            quote = _normalize(citation.get("quote", ""))
            if not quote:
                continue
            for bullet in bullets:
                if quote in str(bullet["body"]):
                    ref = f"bullet#{bullet['number']}"
                    if ref not in bullet_refs:
                        bullet_refs.append(ref)
                    first_screen = first_screen or bool(bullet["first_screen"])
        row = {
            "jd_item_id": str(requirement.get("requirement_id", "")),
            "jd_item": _short(requirement.get("text", ""), 120),
            "kind": requirement.get("kind", "must_have"),
            "status": status,
            # 证据池支撑状态：用于区分"未表达"（池 supported）与"证据缺失"（池 partial/insufficient）。
            "evidence_support": str(requirement.get("status", "") or ""),
            "bullet_ref": "、".join(bullet_refs),
            "first_screen": first_screen,
        }
        rows.append(row)
    if isinstance(judgments, dict) and "r2_1" in (judgments.get("judged_sections") or []):
        pool = {str(item.get("requirement_id", "")): item for item in semantic_review.get("requirements", [])}
        judged = {
            str(item.get("jd_item_id", "")): item
            for item in judgments.get("r2_1", []) or []
            if isinstance(item, dict)
        }
        bullet_index = {f"bullet#{int(bullet['number'])}": bullet for bullet in bullets}
        bullet_index.update({str(row["id"]): row for row in resume_lines(resume)})
        for row in rows:
            item = judged.get(str(row.get("jd_item_id", "")))
            if not item:
                continue
            row["status"] = item.get("status", row["status"])
            evidence = pool.get(str(row["jd_item_id"]), {})
            evidence_status = evidence.get("status", "insufficient")
            ceiling = "supported" if evidence_status == "supported" else "weak" if evidence_status == "partial" else "absent"
            rank = {"absent": 0, "weak": 1, "supported": 2}
            capped = rank.get(str(row["status"]), 0) > rank[ceiling]
            if capped:
                row["status"] = ceiling
            refs = [
                ref for ref in re.findall(r"(?:bullet|line)#\d+", str(item.get("bullet_ref", "")))
                if ref in bullet_index
            ]
            if refs:
                row["bullet_ref"] = "、".join(dict.fromkeys(refs))
                row["first_screen"] = any(bool(bullet_index[ref]["first_screen"]) for ref in refs)
            row["judged"] = True
            row["reason"] = (f"证据池支撑为 {evidence_status}：" + str(evidence.get("reason", ""))) if capped else item.get("reason", "")
    for row in rows:
        if row["status"] == "absent":
            gap_rows.append({"item": row["jd_item"], "reason": _short(row.get("reason", ""), 200)})
    return rows, gap_rows


def _fit_gap_kind(row: dict[str, object]) -> str:
    """对位缺口类型：证据池已 supported 但正文未表达/未进首屏 → not_expressed；其余 → evidence_missing。"""
    status = str(row.get("status", ""))
    first_screen = bool(row.get("first_screen"))
    if status == "supported" and first_screen:
        return ""
    if str(row.get("evidence_support", "")) == "supported":
        return "not_expressed"
    return "evidence_missing"


def _fit_gap_reason(row: dict[str, object]) -> str:
    status = str(row.get("status", ""))
    support = str(row.get("evidence_support", "")) or "未知"
    if _fit_gap_kind(row) == "not_expressed":
        if status == "supported":
            return "正文已支撑但不在首屏（首屏位置缺口，需 supported 且位于首屏）"
        return f"证据池已 supported，正文未充分表达（当前 {status}，需 supported 且位于首屏）"
    return f"证据池支撑为 {support}，正文支撑状态 {status}（需 supported 且位于首屏）"


def evaluate_fit(
    *,
    resume: str,
    semantic_review: dict | None,
    job_context: dict,
    config: QualityConfig,
    judgments: dict | None = None,
) -> TierResult:
    thresholds = config.thresholds["fit"]
    failures: list[QualityFailure] = []
    if not isinstance(semantic_review, dict) or semantic_review.get("mode") != "semantic":
        failures.append(_failure("R2.1", "semantic_review", "缺少语义评审，无法建立 JD 支撑矩阵"))
    matrix, gap_rows = _fit_matrix(resume, semantic_review, judgments)
    responsibilities = [row for row in matrix if row.get("kind") == "responsibility"]
    top_count = int(thresholds["first_screen_required_jd_items"])
    top = responsibilities[:top_count]
    if not top:
        failures.append(_failure("R2.2", "JD 职责", "语义评审未提供岗位职责条目"))
    for row in top:
        gap_kind = _fit_gap_kind(row)
        if not gap_kind:
            continue
        failures.append(
            _failure(
                "R2.2",
                f"JD 职责「{_short(row['jd_item'], 40)}」",
                _fit_gap_reason(row),
                gap_kind=gap_kind,
            )
        )
    # R2.4 与 JD 无关的经历应压缩或退出正文。
    project_entries = [
        entry for entry in _entries(resume).get("项目经历", []) if entry.get("title")
    ]
    mapped_refs = {ref for row in matrix if row["status"] in {"supported", "weak"}
                   for ref in re.findall(r"(?:bullet|line)#\d+", str(row.get("bullet_ref", "")))}
    bullets, _ = _bullet_rows(resume)
    mapped_entries = {str(row["entry"]) for row in bullets if f"bullet#{row['number']}" in mapped_refs}
    mapped_entries.update(str(row["entry"]) for row in resume_lines(resume) if row["id"] in mapped_refs)
    for entry in project_entries:
        title = entry["title"]
        if entry["raw"] not in mapped_entries:
            failures.append(
                _failure("R2.4", f"项目经历「{_short(title)}」", "未映射到任何 JD 条目，考虑压缩或退出正文")
            )
    must_have = [row for row in matrix if row.get("kind") == "must_have"]
    supported = sum(1 for row in must_have if row["status"] == "supported")
    ratio = supported / len(must_have) if must_have else 1.0
    if must_have and ratio < float(thresholds["min_supported_must_have_ratio"]):
        # 支持率只由 supported 决定；“supported 但不在首屏”不属于支持率缺口，不计入本规则计数。
        unsupported = [row for row in must_have if row["status"] != "supported"]
        evidence_gaps = sum(1 for row in unsupported if _fit_gap_kind(row) == "evidence_missing")
        expression_gaps = len(unsupported) - evidence_gaps
        detail = f"硬性要求正文支持率 {ratio:.2f} 低于 {thresholds['min_supported_must_have_ratio']}"
        if evidence_gaps:
            failures.append(
                _failure(
                    "R2.3",
                    "must-have",
                    f"{detail}（证据缺口 {evidence_gaps} 项）",
                    gap_kind="evidence_missing",
                )
            )
        if expression_gaps:
            failures.append(
                _failure(
                    "R2.3",
                    "must-have",
                    f"{detail}（未表达 {expression_gaps} 项）",
                    gap_kind="not_expressed",
                )
            )
        if not evidence_gaps and not expression_gaps:
            failures.append(_failure("R2.3", "must-have", detail))
    metrics = {
        "fit_score": semantic_review.get("fit_score") if isinstance(semantic_review, dict) else None,
        "resume_score": semantic_review.get("resume_score") if isinstance(semantic_review, dict) else None,
        "supported": sum(1 for row in matrix if row["status"] == "supported"),
        "weak": sum(1 for row in matrix if row["status"] == "weak"),
        "absent": sum(1 for row in matrix if row["status"] == "absent"),
        "top_supported_first_screen": sum(
            1 for row in top if row["status"] == "supported" and row["first_screen"]
        ),
    }
    return TierResult(
        passed=not failures,
        failures=tuple(failures),
        metrics=metrics,
        matrix=tuple(matrix),
        highlights=tuple(gap_rows),
    )
