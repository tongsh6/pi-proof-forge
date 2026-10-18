"""证据字段可信等级（L1–L5）与出处结构；纯函数，不做 IO。"""
from __future__ import annotations

import json
import re
from typing import Any

LEVELS = ("L1", "L2", "L3", "L4", "L5")
TIME_PRECISIONS = ("year", "month", "day")
PROVENANCE_SCALARS = {
    "time_range": "time_range_provenance_json",
    "role_scope": "role_scope_provenance_json",
}
SOURCE_FIELDS = ("time_range", "role_scope")
_YEAR_MONTH = re.compile(r"((?:19|20)\d{2})(?:[-./](\d{1,2}))?")


def _coerce_confidence(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return min(1.0, max(0.0, float(value)))
    if isinstance(value, str):
        try:
            return min(1.0, max(0.0, float(value.strip())))
        except ValueError:
            return None
    return None


def _normalize_evidence(items: object) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        entry = {
            key: " ".join(str(item.get(key, "")).split())
            for key in ("material_id", "document_id", "sha256", "excerpt", "key")
            if str(item.get(key, "")).strip()
        }
        if not entry.get("material_id") or not entry.get("document_id"):
            continue
        if len(entry.get("excerpt", "")) > 1000:
            entry["excerpt"] = entry["excerpt"][:1000]
        result.append(entry)
    return result[:8]


def normalize_provenance(value: object, *, field: str) -> dict[str, Any] | None:
    """校验并规范化单个字段的 provenance；L5 或结构不合格返回 None。"""
    if field not in SOURCE_FIELDS or not isinstance(value, dict):
        return None
    level = str(value.get("level", "")).upper()
    if level not in LEVELS or level == "L5":
        return None
    evidence = _normalize_evidence(value.get("evidence"))
    normalized: dict[str, Any] = {"level": level, "evidence": evidence}
    confidence = _coerce_confidence(value.get("confidence"))
    if confidence is not None:
        normalized["confidence"] = round(confidence, 3)
    if field == "time_range":
        precision = str(value.get("precision", "month"))
        normalized["precision"] = precision if precision in TIME_PRECISIONS else "month"
    else:
        raw_hits = value.get("first_person_hits")
        if isinstance(raw_hits, dict):
            hits = {
                str(key): int(count)
                for key, count in raw_hits.items()
                if isinstance(count, (int, float)) and not isinstance(count, bool) and int(count) >= 0
            }
            if hits:
                normalized["first_person_hits"] = dict(sorted(hits.items()))
    if value.get("confirmed_by_user") is True:
        normalized["confirmed_by_user"] = True
    confirmed_at = str(value.get("confirmed_at", "")).strip()
    if confirmed_at:
        normalized["confirmed_at"] = confirmed_at[:40]
    # 依据要求：L1 必须有原句；L2/L3 必须有出处条目；L4 为本人陈述。
    if level == "L1" and not any(entry.get("excerpt") for entry in evidence):
        return None
    if level in {"L2", "L3"} and not evidence:
        return None
    if level == "L4":
        normalized.setdefault("confirmed_by_user", True)
    return normalized


def parse_provenance(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        value = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
        except ValueError:
            return None
    else:
        return None
    return value if isinstance(value, dict) else None


def field_value(fields: dict, field: str) -> str:
    return str(fields.get(field, "")).strip()


def field_provenance(fields: dict, field: str) -> dict[str, Any] | None:
    raw = fields.get(PROVENANCE_SCALARS[field]) if field in PROVENANCE_SCALARS else None
    value = parse_provenance(raw)
    return normalize_provenance(value, field=field) if value is not None else None


def field_level(fields: dict, field: str) -> str:
    value = field_value(fields, field)
    provenance = field_provenance(fields, field)
    if provenance:
        return str(provenance.get("level", "L1"))
    return "L1" if value else "L5"


def provenance_json(provenance: dict[str, Any] | None) -> str:
    return json.dumps(provenance, ensure_ascii=False, sort_keys=True) if provenance else ""


def period_bounds(value: str) -> tuple[int | None, int | None]:
    matches = _YEAR_MONTH.findall(value)
    if not matches:
        return None, None
    start_year, start_month = matches[0]
    start = int(start_year) * 12 + (int(start_month) if start_month else 1)
    if "至今" in value or "present" in value.lower():
        return start, None
    if len(matches) > 1:
        end_year, end_month = matches[1]
        return start, int(end_year) * 12 + (int(end_month) if end_month else 12)
    return start, start


def within_windows(value: str, windows: list[tuple[int, int]]) -> bool:
    """时间候选必须落在任一任职区间内；单年值按该年 1–12 月判断。"""
    if not windows:
        return True
    start, end = period_bounds(value)
    if start is None:
        return False
    end = start if end is None else end
    for window_start, window_end in windows:
        if start >= window_start and end <= window_end:
            return True
    return False


def candidate_evidence_readable(
    provenance: dict[str, Any],
    *,
    metadata_keys: set[str],
    source_text: str,
) -> bool:
    """每条依据要么可在原文回读，要么指向已知文档元数据键；否则整体不可信。"""
    for entry in provenance.get("evidence", []):
        excerpt = entry.get("excerpt", "")
        key = entry.get("key", "")
        if excerpt and source_text and excerpt not in source_text:
            return False
        if not excerpt and key and key not in metadata_keys:
            return False
        if not excerpt and not key:
            return False
    return True
