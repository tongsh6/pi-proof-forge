"""四层简历质量评估：合格（Eligible）→ 对位（Fit）→ 优质（Strong）→ 突出（Distinct）。

Phase A 只做规则可判项；LLM 判项通过 ``llm_pending`` 显式列为未评估，
因此 ``auto_pass`` 在 Phase B 接入前保持 False。所有 failure 必须定位到
具体 bullet、经历条目或证据卡，便于审批页跳转和补证据任务生成。
"""
from __future__ import annotations

import copy
import datetime as _datetime
import re
from dataclasses import dataclass
from pathlib import Path

from tools.domain.models import QualityFailure, TierResult
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.engines.evaluation.llm_judge import resume_lines

ROOT = Path(__file__).resolve().parents[3]

DEFAULT_THRESHOLDS: dict[str, dict[str, float | int | bool]] = {
    "eligible": {
        "max_pdf_pages": 2,
        "require_summary": True,
        "require_core_experience": True,
    },
    "fit": {
        "first_screen_required_jd_items": 3,
        "min_supported_must_have_ratio": 0.6,
    },
    "strong": {
        "quant_first_screen_min_ratio": 0.6,
        "quant_total_min_ratio": 0.4,
        "filler_max_hits": 0,
        "summary_max_lines": 3,
    },
    "distinct": {"min_highlights": 1, "max_highlights": 2, "min_confidence": 0.5},
    "inference": {"min_confidence": 0.5},
}

_FLAT_KEYS: dict[str, tuple[str, str, type]] = {
    "eligible_max_pdf_pages": ("eligible", "max_pdf_pages", int),
    "eligible_require_summary": ("eligible", "require_summary", bool),
    "eligible_require_core_experience": ("eligible", "require_core_experience", bool),
    "fit_first_screen_required_jd_items": ("fit", "first_screen_required_jd_items", int),
    "fit_min_supported_must_have_ratio": ("fit", "min_supported_must_have_ratio", float),
    "strong_quant_first_screen_min_ratio": ("strong", "quant_first_screen_min_ratio", float),
    "strong_quant_total_min_ratio": ("strong", "quant_total_min_ratio", float),
    "strong_filler_max_hits": ("strong", "filler_max_hits", int),
    "strong_summary_max_lines": ("strong", "summary_max_lines", int),
    "distinct_min_highlights": ("distinct", "min_highlights", int),
    "distinct_max_highlights": ("distinct", "max_highlights", int),
    "distinct_min_confidence": ("distinct", "min_confidence", float),
    "inference_min_confidence": ("inference", "min_confidence", float),
}

FALLBACK_FILLER_TERMS = (
    "深入理解",
    "丰富经验",
    "积极推动",
    "良好沟通",
    "有较强的",
    "具备较强的",
    "熟练掌握",
    "proven",
    "extensive experience",
)

# Phase A 尚未接入的 LLM 判项；在 Phase B 清零前 auto_pass 必须保持 False。
PHASE_A_LLM_PENDING = ("R1.4", "R2.1", "R2.3", "R3.1", "R3.5", "R4.1", "R4.4")

_ENTRY_SECTIONS = {"项目经历", "工作经历", "补充成果"}
_CONTACT_RE = re.compile(r"@|\d{7,}")
_INTERNAL_TRACE_RE = re.compile(
    r"Evidence trace|Source report|/Users/|/private/|/tmp/|\bec[-_][0-9a-zA-Z]{4,}"
    r"|mat_[0-9a-f]{6,}|\.trace\.json|outputs/|app-data/|materials/",
    re.I,
)
_STRONG_ROLE_RE = re.compile(r"负责|主导|独立负责|全权负责|设计并落地")
_DEGREE_RANK = {"博士": 4, "硕士": 3, "研究生": 3, "本科": 2, "学士": 2, "大专": 1, "专科": 1}


@dataclass(frozen=True)
class QualityConfig:
    thresholds: dict[str, dict[str, float | int | bool]]
    filler_terms: tuple[str, ...]
    version: int = 1


def load_quality_config(root: Path | None = None) -> QualityConfig:
    base = Path(root or ROOT) / "config" / "quality"
    thresholds = copy.deepcopy(DEFAULT_THRESHOLDS)
    version = 1
    thresholds_path = base / "thresholds.yaml"
    if thresholds_path.is_file():
        scalars = parse_simple_yaml(thresholds_path.read_text(encoding="utf-8"))["scalars"]
        raw_version = scalars.get("version", "")
        if raw_version.isdigit():
            version = int(raw_version)
        for key, raw_value in scalars.items():
            target = _FLAT_KEYS.get(key)
            if target is None:
                continue
            group, name, kind = target
            if kind is bool:
                value: object = raw_value.strip().lower() in {"1", "true", "yes", "on"}
            elif kind is int:
                try:
                    value = int(raw_value)
                except ValueError:
                    continue
            else:
                try:
                    value = float(raw_value)
                except ValueError:
                    continue
            thresholds[group][name] = value  # type: ignore[assignment]
    filler_terms = FALLBACK_FILLER_TERMS
    lexicon_path = base / "filler_lexicon.yaml"
    if lexicon_path.is_file():
        parsed = parse_simple_yaml(lexicon_path.read_text(encoding="utf-8"))
        terms = tuple(str(item).strip() for item in parsed["lists"].get("terms", []) if str(item).strip())
        if terms:
            filler_terms = terms
    return QualityConfig(thresholds=thresholds, filler_terms=filler_terms, version=version)


def split_first_screen(resume: str) -> tuple[str, str]:
    first, rest, _mode = _split_first_screen(resume)
    return first, rest


def extract_bullets(resume: str) -> list[dict[str, object]]:
    rows, _marker = _bullet_rows(resume)
    return rows


def strong_wording_bullets(resume: str) -> list[dict[str, object]]:
    return [row for row in extract_bullets(resume) if _STRONG_ROLE_RE.search(str(row.get("text", "")))]


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


def _split_first_screen(resume: str) -> tuple[str, str, str]:
    index = resume.find(FIRST_SCREEN_MARKER)
    if index >= 0:
        return resume[:index], resume[index + len(FIRST_SCREEN_MARKER):], "explicit"
    lines = resume.splitlines()
    cut = min(len(lines), max(12, int(len(lines) * 0.3)))
    return "\n".join(lines[:cut]), "\n".join(lines[cut:]), "fallback"


def _normalize(text: object) -> str:
    return " ".join(str(text).split()).strip()


def _compact(text: object) -> str:
    return re.sub(r"\s+", "", str(text))


def _ym(year: int, month: int) -> int:
    return year * 12 + month


def _now_ym() -> int:
    now = _datetime.datetime.now()
    return _ym(now.year, now.month)


def _period_bounds(period: str) -> tuple[int | None, int | None]:
    matches = re.findall(r"((?:19|20)\d{2})-(0[1-9]|1[0-2])", period)
    if not matches:
        return None, None
    start = _ym(int(matches[0][0]), int(matches[0][1]))
    if "至今" in period or "present" in period.lower():
        return start, _now_ym()
    if len(matches) > 1:
        return start, _ym(int(matches[1][0]), int(matches[1][1]))
    return start, None


def _title_period(raw: str) -> tuple[str, str]:
    match = re.search(r"[（(]([^（）()]*)[）)]\s*$", raw.strip())
    if not match:
        return raw.strip(), ""
    return raw.strip()[: match.start()].strip(), match.group(1).strip()


def _bullet_rows(resume: str) -> tuple[list[dict[str, object]], int]:
    """返回 bullet 行（含 section/entry/行号/是否首屏）与首屏切分行号。"""
    lines = resume.splitlines()
    marker_line = next((index for index, line in enumerate(lines) if line.strip() == FIRST_SCREEN_MARKER), None)
    if marker_line is None:
        marker_line = min(len(lines), max(12, int(len(lines) * 0.3)))
    rows: list[dict[str, object]] = []
    section = ""
    entry = ""
    number = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped == FIRST_SCREEN_MARKER:
            continue
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            entry = ""
            continue
        if stripped.startswith("### "):
            entry = stripped[4:].strip()
            continue
        match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", line)
        if not match:
            continue
        number += 1
        rows.append(
            {
                "number": number,
                "text": match.group(1).strip(),
                "body": _normalize(match.group(1)),
                "section": section,
                "entry": entry,
                "line": index,
                "first_screen": index < marker_line,
            }
        )
    return rows, marker_line


def _entries(resume: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    section = ""
    for line in resume.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            continue
        if stripped.startswith("### "):
            title, period = _title_period(stripped[4:])
            result.setdefault(section, []).append({"raw": stripped[4:].strip(), "title": title, "period": period})
    return result


def inspect_bullet_trace(resume: str, trace: dict | None) -> dict:
    """校验 bullet 是否被生成 trace 的 claims 完整覆盖。"""
    claims = trace.get("claims") if isinstance(trace, dict) else None
    rows, _marker = _bullet_rows(resume)
    facts = sorted(
        (
            claim
            for claim in (claims or [])
            if isinstance(claim, dict)
            and claim.get("source_kind") in {"evidence", "personal_profile"}
            and claim.get("text")
        ),
        key=lambda claim: len(str(claim["text"])),
        reverse=True,
    )
    checked: list[dict[str, object]] = []
    for row in rows:
        body = str(row["body"])
        remaining = body
        sources: list[dict[str, str]] = []
        for claim in facts:
            text = str(claim.get("text", ""))
            if text and text in remaining:
                remaining = remaining.replace(text, "")
                sources.append(
                    {key: str(claim.get(key, "")) for key in ("source_kind", "field", "evidence_id")}
                )
        covered = bool(sources) and not re.sub(r"[\s:：·、|*]", "", remaining)
        evidence_ids = sorted({source["evidence_id"] for source in sources if source.get("evidence_id")})
        checked.append(
            {
                "number": row["number"],
                "text": row["text"],
                "section": row["section"],
                "first_screen": row["first_screen"],
                "verified": covered,
                "sources": sources,
                "evidence_ids": evidence_ids,
            }
        )
    return {
        "status": "verified" if claims is not None else "unverified",
        "verified_bullets": sum(1 for row in checked if row["verified"]),
        "total_bullets": len(checked),
        "bullets": checked,
    }


def _failure(rule: str, target: str, reason: str) -> QualityFailure:
    return QualityFailure(rule=rule, target=_normalize(target)[:160], reason=_normalize(reason)[:500])


def _short(text: object, limit: int = 60) -> str:
    value = _normalize(text)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _report_metrics(bullet_count: int, trace: dict, extra: dict | None = None) -> dict[str, object]:
    metrics: dict[str, object] = {
        "verified_bullets": trace.get("verified_bullets", 0),
        "total_bullets": trace.get("total_bullets", bullet_count),
    }
    if extra:
        metrics.update(extra)
    return metrics


def _pdf_failures(pdf_check: dict | None, first_screen: str, thresholds: dict) -> list[QualityFailure]:
    failures: list[QualityFailure] = []
    if not isinstance(pdf_check, dict):
        failures.append(_failure("R1.5", "pdf", "PDF 未渲染，页数与裁切尚未校验"))
    else:
        pages = pdf_check.get("pages")
        max_pages = int(thresholds["eligible"]["max_pdf_pages"])
        if not isinstance(pages, int) or pages < 1:
            failures.append(_failure("R1.5", "pdf", "PDF 页数不可用"))
        elif pages > max_pages:
            failures.append(_failure("R1.5", "pdf", f"PDF {pages} 页，超过 {max_pages} 页上限"))
        if pdf_check.get("clipped") is True:
            failures.append(_failure("R1.5", "pdf", "PDF 存在裁切"))
    if thresholds["eligible"]["require_summary"] and not any(
        token in first_screen for token in ("当前定位", "求职意向", "职业概述", "摘要")
    ):
        failures.append(_failure("R1.5", "首屏", "首屏缺少定位摘要"))
    if thresholds["eligible"]["require_core_experience"] and not re.search(
        r"^\s*(?:[-*]|###\s)", first_screen, re.M
    ):
        failures.append(_failure("R1.5", "首屏", "首屏缺少核心经历或成果条目"))
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
    failures.extend(_pdf_failures(pdf_check, first_screen, thresholds))

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
            "pdf_pages": (pdf_check or {}).get("pages"),
            "clip_check": (pdf_check or {}).get("clipped"),
            "first_screen_mode": _mode,
            "reason_count": len(failures),
        },
    )
    return TierResult(passed=not failures, failures=tuple(failures), metrics=metrics)


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
        if row["status"] != "supported" or not row["first_screen"]:
            failures.append(
                _failure(
                    "R2.2",
                    f"JD 职责「{_short(row['jd_item'], 40)}」",
                    f"首屏支撑状态 {row['status']}（需 supported 且位于首屏）",
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
        failures.append(
            _failure(
                "R2.3",
                "must-have",
                f"硬性要求正文支持率 {ratio:.2f} 低于 {thresholds['min_supported_must_have_ratio']}",
            )
        )
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


def _has_verifiable_quant(body: str, results: list[str]) -> bool:
    # 数字必须属于实际呈现的成果片段，技术版本或年份恰好相同不算量化成果。
    from tools.domain.quality_text import compact, has_quant_metric

    normalized = compact(body)
    return any(has_quant_metric(result) and compact(result) in normalized
               for result in results if str(result).strip())


def evaluate_strong(
    *,
    resume: str,
    cards: dict[str, dict],
    trace: dict,
    config: QualityConfig,
    judgments: dict | None = None,
) -> TierResult:
    thresholds = config.thresholds["strong"]
    bullets, _marker = _bullet_rows(resume)
    trace_result = inspect_bullet_trace(resume, trace)
    verified_rows = {int(row["number"]): row for row in trace_result["bullets"]}
    experience = [bullet for bullet in bullets if bullet["section"] in _ENTRY_SECTIONS]
    failures: list[QualityFailure] = []
    if not experience:
        failures.append(_failure("R3.2", "bullets", "正文没有任何经历 bullet，无法判断表达质量"))
        quant_total = quant_first = 0.0
    else:
        quant_flags: list[bool] = []
        for bullet in experience:
            row = verified_rows.get(int(bullet["number"]), {})
            evidence_ids = list(row.get("evidence_ids", []))
            pool = [
                str(value)
                for evidence_id in evidence_ids
                for value in cards.get(evidence_id, {}).get("results", []) or []
            ]
            quant_flags.append(_has_verifiable_quant(str(bullet["body"]), pool))
        quant_total = sum(quant_flags) / len(quant_flags)
        first_flags = [
            flag for bullet, flag in zip(experience, quant_flags) if bullet["first_screen"]
        ]
        quant_first = sum(first_flags) / len(first_flags) if first_flags else 0.0
        if quant_first < float(thresholds["quant_first_screen_min_ratio"]):
            failures.append(
                _failure(
                    "R3.2",
                    "首屏量化",
                    f"首屏可验证量化比例 {quant_first:.2f} 低于 {thresholds['quant_first_screen_min_ratio']}",
                )
            )
        if quant_total < float(thresholds["quant_total_min_ratio"]):
            failures.append(
                _failure(
                    "R3.2",
                    "全文量化",
                    f"全文可验证量化比例 {quant_total:.2f} 低于 {thresholds['quant_total_min_ratio']}",
                )
            )
    filler_hits: list[tuple[str, str]] = []
    for bullet in experience:
        for term in config.filler_terms:
            if term.casefold() in str(bullet["body"]).casefold():
                filler_hits.append((f"bullet#{bullet['number']}", term))
                break
    if len(filler_hits) > int(thresholds["filler_max_hits"]):
        for target, term in filler_hits[:5]:
            failures.append(_failure("R3.3", target, f"出现空话词：{term}"))
    normalized: dict[str, list[int]] = {}
    for bullet in experience:
        key = re.sub(r"[\s:：·、|*“”\"']", "", str(bullet["body"]))
        normalized.setdefault(key, []).append(int(bullet["number"]))
    for key, numbers in normalized.items():
        if key and len(numbers) > 1:
            failures.append(
                _failure("R3.4", "、".join(f"bullet#{number}" for number in numbers), "同一成果在正文重复出现")
            )
    casing: dict[str, set[str]] = {}
    for bullet in experience:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", str(bullet["body"])):
            casing.setdefault(token.casefold(), set()).add(token)
    for variants in casing.values():
        if len(variants) > 1:
            failures.append(_failure("R3.6", "术语大小写", "同一术语大小写不一致：" + " / ".join(sorted(variants))))
    # R3.1 三段判定：每个经历 bullet 必须有带引用的场景/动作/结果判定，缺失按失败处理。
    if isinstance(judgments, dict) and "r3_1" in (judgments.get("judged_sections") or []):
        judged = {
            int(item["bullet"]): item
            for item in judgments.get("r3_1", []) or []
            if isinstance(item, dict) and isinstance(item.get("bullet"), int)
        }
        for bullet in experience:
            item = judged.get(int(bullet["number"]))
            if item is None:
                failures.append(_failure("R3.1", f"bullet#{bullet['number']}", "缺少带引用的三段判定"))
                continue
            verified = verified_rows.get(int(bullet["number"]), {})
            if verified.get("verified") and any(source.get("field") == "results"
                                                for source in verified.get("sources", [])):
                # 直接呈现已核验成果原文即有结果段，非数值交付无需额外量化。
                item = {**item, "result": True}
            missing = [label for label, key in (("场景", "scene"), ("动作", "action"), ("结果", "result")) if not item.get(key)]
            if missing:
                failures.append(
                    _failure("R3.1", f"bullet#{bullet['number']}", "缺少" + "、".join(missing) + "段")
                )
    # R3.5 摘要判定：<=3 行、角色/规模匹配、无通用形容词。
    if isinstance(judgments, dict) and "r3_5" in (judgments.get("judged_sections") or []):
        summary_judgment = judgments.get("r3_5") or {}
        max_lines = int(thresholds.get("summary_max_lines", 3))
        lines = summary_judgment.get("summary_lines")
        if isinstance(lines, int) and lines > max_lines:
            failures.append(_failure("R3.5", "摘要", f"定位摘要 {lines} 行，超过 {max_lines} 行"))
        if summary_judgment.get("role_scale_match") is False:
            failures.append(_failure("R3.5", "摘要", "定位摘要未说明做什么、在什么规模/领域与岗位匹配点"))
        adjectives = summary_judgment.get("generic_adjectives") or []
        if adjectives:
            failures.append(_failure("R3.5", "摘要", "定位摘要含通用形容词：" + "、".join(str(item) for item in adjectives[:5])))
    metrics = {
        "quant_first_screen": round(quant_first, 4),
        "quant_total": round(quant_total, 4),
        "filler_hits": len(filler_hits),
        "duplicate_bullets": sum(len(numbers) - 1 for numbers in normalized.values() if len(numbers) > 1),
        "judged_r3_1": isinstance(judgments, dict) and "r3_1" in (judgments.get("judged_sections") or []),
        "judged_r3_5": isinstance(judgments, dict) and "r3_5" in (judgments.get("judged_sections") or []),
    }
    return TierResult(passed=not failures, failures=tuple(failures), metrics=metrics)


def _candidate_highlights(
    resume: str,
    candidates: list[dict] | None,
    decisions: dict | None,
) -> list[dict[str, object]]:
    bullets, _marker = _bullet_rows(resume)
    by_number = {f"bullet#{int(bullet['number'])}": bullet for bullet in bullets}
    rejected = {str(item) for item in ((decisions or {}).get("rejected") or [])}
    selected = {str(item) for item in ((decisions or {}).get("selected") or [])}
    items: list[dict[str, object]] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        highlight_id = str(candidate.get("highlight_id") or "")
        bullet = candidate.get("bullet")
        if not highlight_id or not isinstance(bullet, int) or highlight_id in rejected:
            continue
        ref = f"bullet#{bullet}"
        row = by_number.get(ref)
        exceeds = [str(value) for value in (candidate.get("exceeds") or [])]
        items.append(
            {
                "highlight_id": highlight_id,
                "bullet_ref": ref,
                "jd_item_id": str(candidate.get("jd_item_id", "")),
                "exceeds": "、".join(exceeds),
                "level": str(candidate.get("level", "")),
                "reason": str(candidate.get("reason", "")),
                "citations": list(candidate.get("citations") or []),
                "first_screen": bool(row["first_screen"]) if row else False,
                "selected_by_user": highlight_id in selected,
            }
        )
    items.sort(
        key=lambda item: (
            0 if item["selected_by_user"] else 1,
            -len(str(item["exceeds"]).split("、")) if item["exceeds"] else 0,
            item["bullet_ref"],
        )
    )
    return items


def evaluate_distinct(
    *,
    resume: str = "",
    highlights: list[dict] | None = None,
    candidates: list[dict] | None = None,
    decisions: dict | None = None,
    config: QualityConfig,
) -> TierResult:
    thresholds = config.thresholds["distinct"]
    if candidates is not None:
        items = _candidate_highlights(resume, candidates, decisions)
    else:
        items = [item for item in (highlights or []) if isinstance(item, dict)]
        if decisions:
            rejected = {str(value) for value in (decisions.get("rejected") or [])}
            items = [item for item in items if str(item.get("highlight_id") or "") not in rejected]
    failures: list[QualityFailure] = []
    minimum = int(thresholds["min_highlights"])
    maximum = int(thresholds["max_highlights"])
    if len(items) < minimum:
        reason = "无合格突出点" if candidates is not None else "无合格突出点（LLM 提名尚未运行或全部被否决）"
        failures.append(_failure("R4.2", "highlights", reason))
    chosen = items[:maximum] if len(items) > maximum else items
    if len(items) > maximum and candidates is None:
        failures.append(
            _failure("R4.2", "highlights", f"突出点 {len(items)} 条，超过 {maximum} 条上限")
        )
    for index, item in enumerate(chosen, start=1):
        level = str(item.get("level", "L1"))
        if level not in {"L1", "L2"}:
            failures.append(
                _failure("R4.3", f"突出点#{index}", f"证据等级 {level} 不能作为突出点")
            )
        if item.get("first_screen") is False:
            failures.append(_failure("R4.2", f"突出点#{index}", "突出点未置于首屏"))
    rejected_ids = {str(value) for value in ((decisions or {}).get("rejected") or [])}
    candidate_details = [
        {
            "highlight_id": item.get("highlight_id", ""),
            "bullet_ref": item.get("bullet_ref", ""),
            "jd_item_id": item.get("jd_item_id", ""),
            "exceeds": item.get("exceeds", ""),
            "level": item.get("level", ""),
            "reason": item.get("reason", ""),
            "first_screen": item.get("first_screen"),
            "rejected": str(item.get("highlight_id", "")) in rejected_ids,
        }
        for item in (items if candidates is not None else [])
    ]
    metrics = {
        "count": len(chosen),
        "candidate_count": len(candidates or []) if candidates is not None else len(items),
        "levels": sorted({str(item.get("level", "L1")) for item in chosen}),
        "rejected": len((decisions or {}).get("rejected") or []),
        "selected": len((decisions or {}).get("selected") or []),
        "candidates": candidate_details,
    }
    return TierResult(passed=not failures, failures=tuple(failures), metrics=metrics, highlights=tuple(chosen))


def _tier_gap_tasks(tiers: dict[str, dict[str, object]], fit_gaps: list[dict]) -> list[str]:
    tasks: list[str] = []
    labels = {"eligible": "合格", "fit": "对位", "strong": "优质", "distinct": "突出"}
    for tier_name, tier in tiers.items():
        for failure in tier.get("failures", []):  # type: ignore[union-attr]
            if not isinstance(failure, dict):
                continue
            tasks.append(
                f"{labels.get(tier_name, tier_name)} {failure.get('rule', '')} {failure.get('target', '')}：{failure.get('reason', '')}"
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
        if isinstance(failure, dict) and failure.get("rule") != "R1.5"
    ]
    pages = pdf_check.get("pages")
    max_pages = int(thresholds["eligible"]["max_pdf_pages"])  # type: ignore[index]
    new_pdf_failures: list[QualityFailure] = []
    if not isinstance(pages, int) or pages < 1:
        new_pdf_failures.append(_failure("R1.5", "pdf", "PDF 页数不可用"))
    elif pages > max_pages:
        new_pdf_failures.append(_failure("R1.5", "pdf", f"PDF {pages} 页，超过 {max_pages} 页上限"))
    if pdf_check.get("clipped") is True:
        new_pdf_failures.append(_failure("R1.5", "pdf", "PDF 存在裁切"))
    eligible["failures"] = failures + [failure.to_dict() for failure in new_pdf_failures]
    metrics = eligible.get("metrics") if isinstance(eligible.get("metrics"), dict) else {}
    metrics["pdf_pages"] = pages
    metrics["clip_check"] = pdf_check.get("clipped")
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
    updated["auto_pass"] = recompute_auto_pass(updated)
    return updated
