"""四层质量评估公共工具：配置、正文解析、bullet/条目/追溯检查与通用判定。"""

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


def split_first_screen(resume: str) -> tuple[str, str]:
    first, rest, _mode = _split_first_screen(resume)
    return first, rest


def extract_bullets(resume: str) -> list[dict[str, object]]:
    rows, _marker = _bullet_rows(resume)
    return rows


def strong_wording_bullets(resume: str) -> list[dict[str, object]]:
    return [row for row in extract_bullets(resume) if _STRONG_ROLE_RE.search(str(row.get("text", "")))]


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
    exact = isinstance(trace, dict) and trace.get("occurrence_lineage_version") == 1
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
            if exact and claim.get("render_line") != row["line"] + 1:
                continue
            text = str(claim.get("text", ""))
            if text and text in remaining:
                remaining = remaining.replace(text, "")
                sources.append(
                    {key: str(claim.get(key, "")) for key in ("source_kind", "field", "evidence_id", "fact_id")}
                    | {"text": text}
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


def _failure(rule: str, target: str, reason: str, gap_kind: str = "") -> QualityFailure:
    return QualityFailure(
        rule=rule,
        target=_normalize(target)[:160],
        reason=_normalize(reason)[:500],
        gap_kind=gap_kind,
    )


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


def _unique(items: object) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item).strip()))


def _pdf_check_pending(eligible: dict[str, object]) -> bool:
    """评估阶段尚未渲染 PDF：只把 R1.5 的 pdf 页数/裁切项视为未校验，首屏缺口仍参与建议。"""
    metrics = eligible.get("metrics") if isinstance(eligible.get("metrics"), dict) else {}
    return str(metrics.get("pdf_check_state", "")) == "unverified"


def _advice_recomputable(tiers: object) -> bool:
    """只有四层结构完整（每层 failures 为 list）时才重算建议，稀疏/异常报告保留原值。"""
    if not isinstance(tiers, dict):
        return False
    for name in ("eligible", "fit", "strong", "distinct"):
        tier = tiers.get(name)
        if not isinstance(tier, dict) or not isinstance(tier.get("failures"), list):
            return False
    return True


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



__all__ = ["split_first_screen", "extract_bullets", "strong_wording_bullets", "_split_first_screen", "_normalize", "_compact", "_ym", "_now_ym", "_period_bounds", "_title_period", "_bullet_rows", "_entries", "inspect_bullet_trace", "_failure", "_short", "_report_metrics", "_unique", "_pdf_check_pending", "_advice_recomputable", "load_quality_config", "ROOT", "DEFAULT_THRESHOLDS", "FALLBACK_FILLER_TERMS", "PHASE_A_LLM_PENDING", "QualityConfig", "_ENTRY_SECTIONS", "_CONTACT_RE", "_INTERNAL_TRACE_RE", "_STRONG_ROLE_RE", "_DEGREE_RANK", "_FLAT_KEYS"]
