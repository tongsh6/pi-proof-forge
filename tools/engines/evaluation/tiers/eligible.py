"""R1 合格层：PDF/摘要/核心经历/首页结构/硬性条件/证据追溯。"""

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


PDF_CHECK_PENDING = "pdf_check_pending"


def pdf_artifact_check(pdf_check: dict | None, thresholds: dict) -> tuple[list[QualityFailure], dict]:
    """Measure pages and clipping independently; absence is never a passing check."""
    check = pdf_check if isinstance(pdf_check, dict) else {}
    pages = check.get("pages")
    clipped = check.get("clipped")
    pages = pages if type(pages) is int and pages > 0 else None
    clipped = clipped if type(clipped) is bool else None
    failures: list[QualityFailure] = []
    max_pages = int(thresholds["eligible"]["max_pdf_pages"])
    if pages is None:
        failures.append(_failure("R1.5", "pdf", "PDF 页数尚未校验", gap_kind=PDF_CHECK_PENDING))
    elif pages > max_pages:
        failures.append(_failure("R1.5", "pdf", f"PDF {pages} 页，超过 {max_pages} 页上限"))
    if clipped is None:
        failures.append(_failure("R1.5", "pdf", "PDF 裁切尚未校验", gap_kind=PDF_CHECK_PENDING))
    elif clipped:
        failures.append(_failure("R1.5", "pdf", "PDF 存在裁切"))
    return failures, {
        "pdf_pages": pages, "clip_check": clipped,
        "pdf_check_state": "verified" if pages is not None and clipped is not None else "unverified",
    }


def _first_screen_failures(first_screen: str, thresholds: dict) -> list[QualityFailure]:
    failures: list[QualityFailure] = []
    if thresholds["eligible"]["require_summary"] and not any(
        token in first_screen for token in ("当前定位", "求职意向", "职业概述", "摘要")
    ):
        failures.append(_failure("R1.5", "首屏", "首屏缺少定位摘要"))
    if thresholds["eligible"]["require_core_experience"] and not re.search(
        r"^\s*(?:[-*]|###\s)", first_screen, re.M
    ):
        failures.append(_failure("R1.5", "首屏", "首屏缺少核心经历或成果条目"))
    return failures


def _provenance(card: dict, field: str) -> dict:
    from tools.infra import evidence_provenance as evidence_provenance

    raw = card.get(f"{field}_provenance")
    if not isinstance(raw, dict):
        raw = evidence_provenance.parse_provenance(card.get(f"{field}_provenance_json"))
    return raw if isinstance(raw, dict) else {}


def _provenance_level(card: dict, field: str) -> str:
    raw = _provenance(card, field)
    level = raw.get("level") or card.get(f"{field}_provenance_level")
    return str(level or "L1")


def _hard_condition_failures(career: dict, job_context: dict) -> list[QualityFailure]:
    failures: list[QualityFailure] = []
    education = career.get("education", []) if isinstance(career.get("education"), list) else []
    required = ""
    for token in ("博士", "硕士", "研究生", "本科", "学士", "大专", "专科"):
        if token in str(job_context.get("education", "")):
            required = token
            break
    if required:
        ranks = [
            _DEGREE_RANK[token]
            for item in education
            if isinstance(item, dict)
            for token in _DEGREE_RANK
            if token in str(item.get("degree", ""))
        ]
        if not ranks or max(ranks) < _DEGREE_RANK[required]:
            failures.append(
                _failure("R1.7", "学历", f"岗位要求 {required}，职业档案学历不满足，需用户决定是否投递")
            )
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-~–—]\s*\d+(?:\.\d+)?)?\s*年", str(job_context.get("work_years", "")))
    if match:
        minimum_years = float(match.group(1))
        months = 0
        for item in career.get("work", []) if isinstance(career.get("work"), list) else []:
            if not isinstance(item, dict):
                continue
            start, end = _period_bounds(f"{item.get('start', '')} ~ {'至今' if item.get('current') else item.get('end', '')}")
            if start is None:
                continue
            months += max(0, (end if end is not None else _now_ym()) - start)
        if months < minimum_years * 12:
            failures.append(
                _failure(
                    "R1.7",
                    "年限",
                    f"岗位要求约 {minimum_years:g} 年，职业档案累计 {months / 12:.1f} 年",
                )
            )
    return failures


def _structure_failures(resume: str, career: dict) -> list[QualityFailure]:
    failures: list[QualityFailure] = []
    headings = {line.strip()[3:].strip() for line in resume.splitlines() if line.strip().startswith("## ")}
    lines = [line.strip() for line in resume.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("# ") or not any(_CONTACT_RE.search(line) for line in lines[:4]):
        failures.append(_failure("R1.8", "头部", "缺少姓名或联系方式头部"))
    if not any(token in headings for token in ("职业概述", "摘要", "10-second summary")):
        failures.append(_failure("R1.8", "摘要", "缺少定位摘要章节"))
    if not any(token in headings for token in ("工作经历", "项目经历")):
        failures.append(_failure("R1.8", "经历", "缺少工作或项目经历章节"))
    if not any(token in headings for token in ("核心技能", "技能", "核心能力")):
        failures.append(_failure("R1.8", "技能", "缺少技能或能力章节"))
    visibility = career.get("education_visibility", "show")
    if visibility != "omit" and not any(token in headings for token in ("教育经历", "教育背景")):
        failures.append(_failure("R1.8", "教育", "缺少教育经历章节（未声明不展示）"))
    return failures


def evaluate_eligible(
    *,
    resume: str,
    trace: dict,
    career_profile: dict,
    cards: dict[str, dict],
    job_context: dict,
    pdf_check: dict | None,
    config: QualityConfig,
    judgments: dict | None = None,
) -> TierResult:
    thresholds = config.thresholds
    first_screen, _rest, _mode = _split_first_screen(resume)
    trace_result = inspect_bullet_trace(resume, trace)
    failures: list[QualityFailure] = []

    # R1.1 正文每条 bullet 可追溯到证据卡或已确认职业档案。
    if trace_result["status"] != "verified" or not trace_result["total_bullets"]:
        failures.append(_failure("R1.1", "trace", "缺少生成追溯（resume_trace 无效或缺失）"))
    else:
        for row in trace_result["bullets"]:
            if not row["verified"]:
                failures.append(
                    _failure(
                        "R1.1",
                        f"bullet#{row['number']} / {row['section']}",
                        "bullet 未被已审核证据或职业档案完整覆盖",
                    )
                )

    career = career_profile.get("career") if isinstance(career_profile, dict) else {}
    career = career if isinstance(career, dict) else {}
    status = career_profile.get("career_status") if isinstance(career_profile, dict) else {}
    if not isinstance(status, dict) or status.get("reviewed") is not True:
        failures.append(_failure("R1.2", "career_profile", "职业档案未确认或已过期"))
    entries = _entries(resume)
    project_cards: list[tuple[str, str]] = []
    for entry in entries.get("项目经历", []):
        title = entry["title"]
        card_id = ""
        for candidate_id, candidate_card in cards.items():
            if _compact(candidate_card.get("title", "")) == _compact(title):
                card_id = candidate_id
                break
        project_cards.append((title, card_id))

    # R1.2 正文公司/职位/任职区间与已确认档案一致；项目时间落在任职区间内。
    work_items = career.get("work", []) if isinstance(career.get("work"), list) else []
    work_windows: dict[str, tuple[int | None, int | None, str]] = {}
    for index, item in enumerate(work_items):
        if not isinstance(item, dict):
            continue
        expected = f"{item.get('start', '')} ~ {'至今' if item.get('current') else item.get('end', '')}"
        work_windows[str(item.get("company", ""))] = (*_period_bounds(expected), expected)
        for ref in item.get("evidence_ids", []) or []:
            work_windows[f"card:{ref}"] = (*_period_bounds(expected), expected)
    for entry in entries.get("工作经历", []):
        company, period = entry["title"].split(" · ")[0], entry["period"]
        for expected_company, (start, _end, expected_period) in work_windows.items():
            if expected_company.startswith("card:") or not expected_company:
                continue
            if _compact(expected_company) and _compact(expected_company) in _compact(company):
                if period and _compact(period) != _compact(expected_period):
                    failures.append(
                        _failure(
                            "R1.2",
                            f"工作经历「{_short(company)}」",
                            f"任职区间与职业档案不一致：正文 {period} / 档案 {expected_period}",
                        )
                    )
                break
    for title, card_id in project_cards:
        if not card_id:
            continue
        window = work_windows.get(f"card:{card_id}")
        if window is None:
            continue
        work_start, work_end, _expected = window
        period = next(
            (entry["period"] for entry in entries.get("项目经历", []) if entry["title"] == title),
            "",
        )
        start, end = _period_bounds(period)
        if start is None:
            continue
        effective_end = end if end is not None else _now_ym()
        effective_work_end = work_end if work_end is not None else _now_ym()
        if work_start is not None and (effective_end < work_start or start > effective_work_end):
            failures.append(
                _failure(
                    "R1.2",
                    f"项目经历「{_short(title)}」（{card_id}）",
                    f"项目时间 {period} 不在对应任职区间内",
                )
            )

    # R1.3 每条经历/项目都有时间；无时间卡不得进入正文。
    for title, card_id in project_cards:
        _title, period = _title_period(title)
        heading_period = next(
            (entry["period"] for entry in entries.get("项目经历", []) if entry["title"] == title),
            "",
        )
        if not re.search(r"(?:19|20)\d{2}", heading_period):
            failures.append(
                _failure("R1.3", f"项目经历「{_short(title)}」", "项目缺少时间（至少到年）")
            )
        if card_id and not re.search(r"(?:19|20)\d{2}", str(cards[card_id].get("time_range", ""))):
            failures.append(
                _failure(
                    "R1.3",
                    f"项目经历「{_short(title)}」（{card_id}）",
                    "证据卡 time_range 缺失",
                )
            )
    for entry in entries.get("工作经历", []):
        if not re.search(r"(?:19|20)\d{2}", entry["period"]):
            failures.append(
                _failure("R1.3", f"工作经历「{_short(entry['title'])}」", "经历缺少时间（至少到年）")
            )

    # R1.4 核对职责是否已采纳；有出处且已确认的 L3 不因来源等级自动降低责任。
    strong_rows = [row for row in trace_result["bullets"] if _STRONG_ROLE_RE.search(str(row.get("text", "")))]
    confirmed_profile_texts: set[str] = set()
    if career_profile.get("career_status", {}).get("reviewed"):
        career = career_profile.get("career", {})
        for group, label in (("skills", "category"), ("extras", "title")):
            for entry in career.get(group, []):
                description = str(entry.get("description", ""))
                confirmed_profile_texts.update((_normalize(description),
                    _normalize(str(entry.get(label, "")) + "：" + description)))
        confirmed_profile_texts.update(_normalize(text) for entry in career.get("work", [])
                                       for text in entry.get("contributions", []))
    flagged_bullets: set[int] = set()
    for row in strong_rows:
        for evidence_id in row.get("evidence_ids", []):
            source = cards.get(evidence_id, {})
            level = _provenance_level(source, "role_scope")
            role = _provenance(source, "role_scope")
            confirmed = role.get("confirmed_by_user") is True and bool(role.get("evidence"))
            if level == "L5" or (level == "L3" and not confirmed):
                failures.append(
                    _failure(
                        "R1.4",
                        f"bullet#{row['number']} / {evidence_id}",
                        f"角色措辞“{_short(row['text'], 20)}”缺少已确认的职责依据（{level}）",
                    )
                )
                flagged_bullets.add(int(row["number"]))
                break
    if isinstance(judgments, dict) and "r1_4" in (judgments.get("judged_sections") or []):
        judged = {
            int(item["bullet"]): item
            for item in judgments.get("r1_4", []) or []
            if isinstance(item, dict) and isinstance(item.get("bullet"), int)
        }
        for row in strong_rows:
            number = int(row["number"])
            if number in flagged_bullets:
                continue
            if (row.get("verified") and _normalize(row["text"]) in confirmed_profile_texts
                    and all(source.get("source_kind") == "personal_profile" for source in row.get("sources", []))):
                continue
            item = judged.get(number)
            if item is None:
                failures.append(_failure("R1.4", f"bullet#{number}", "缺少带引用的角色措辞判定"))
            elif item.get("supported") is False:
                failures.append(
                    _failure(
                        "R1.4",
                        f"bullet#{number} / {'、'.join(item.get('citations') or [])}",
                        f"角色措辞缺少已引用证据支持：{item.get('reason', '')}",
                    )
                )

    # R1.5 篇幅/首屏/裁切。
    pdf_failures, pdf_metrics = pdf_artifact_check(pdf_check, thresholds)
    failures.extend(pdf_failures)
    failures.extend(_first_screen_failures(first_screen, thresholds))

    # R1.6 候选人可见正文不得含内部追溯信息。
    matched = _INTERNAL_TRACE_RE.search(resume)
    if matched:
        failures.append(_failure("R1.6", "resume", f"正文含内部追溯信息：{_short(matched.group(0), 40)}"))

    # R1.7 JD 硬性条件违背必须标记，不能隐瞒。
    failures.extend(_hard_condition_failures(career, job_context))

    # R1.8 简历结构。
    failures.extend(_structure_failures(resume, career))

    metrics = _report_metrics(
        trace_result["total_bullets"],
        trace_result,
        {
            **pdf_metrics,
            "first_screen_mode": _mode,
            "reason_count": len(failures),
        },
    )
    return TierResult(passed=not failures, failures=tuple(failures), metrics=metrics)
