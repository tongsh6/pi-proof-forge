from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast

from tools.infra.persistence.yaml_io import ParsedDoc, parse_simple_yaml

_ROOT_DIR = Path(".")
_JOB_PROFILE_DIR = _ROOT_DIR / "job_profiles"
_MATCHING_REPORT_DIR = _ROOT_DIR / "matching_reports"


class MatchSnapshot(TypedDict):
    score: int
    evidence_count: int
    updated_at: str
    sort_key: float


class JobProfileItem(TypedDict):
    job_profile_id: str
    title: str
    company: str
    status: str
    match_score: int
    evidence_count: int
    resume_count: int
    updated_at: str
    business_domain: str
    source_jd: str
    tone: str
    keywords: list[str]
    must_have: list[str]
    nice_to_have: list[str]
    seniority_signal: list[str]


class JobsListResult(TypedDict):
    meta: dict[str, str]
    items: list[JobProfileItem]
    next_cursor: str | None


def _glob_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.glob(pattern))


def _read_yaml_doc(path: Path) -> ParsedDoc:
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def _try_read_yaml_doc(path: Path) -> ParsedDoc | None:
    try:
        return _read_yaml_doc(path)
    except (OSError, UnicodeDecodeError):
        return None


def _format_utc_datetime(value: datetime) -> str:
    normalized = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_utc_timestamp(value: float) -> str:
    return _format_utc_datetime(datetime.fromtimestamp(value, tz=timezone.utc))


def _safe_parse_iso_date(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _load_matching_snapshots() -> dict[str, MatchSnapshot]:
    snapshots: dict[str, MatchSnapshot] = {}

    for path in _glob_files(_MATCHING_REPORT_DIR, "*.yaml"):
        doc = _try_read_yaml_doc(path)
        if doc is None:
            continue
        job_profile_id = doc["scalars"].get("job_profile_id", "").strip()
        if not job_profile_id:
            continue

        generated_at = doc["scalars"].get("generated_at", "")
        parsed_generated_at = _safe_parse_iso_date(generated_at)
        sort_key = (
            parsed_generated_at.timestamp()
            if parsed_generated_at is not None
            else path.stat().st_mtime
        )
        updated_at = (
            _format_utc_datetime(parsed_generated_at)
            if parsed_generated_at is not None
            else _format_utc_timestamp(sort_key)
        )

        try:
            score = int(doc["scalars"].get("score_total", "0") or "0")
        except ValueError:
            score = 0

        snapshot: MatchSnapshot = {
            "score": score,
            "evidence_count": len(doc["lists"].get("evidence_card_ids", [])),
            "updated_at": updated_at,
            "sort_key": sort_key,
        }
        existing = snapshots.get(job_profile_id)
        if existing is None or snapshot["sort_key"] >= existing["sort_key"]:
            snapshots[job_profile_id] = snapshot

    return snapshots


def _derive_status(doc: ParsedDoc, snapshot: MatchSnapshot | None) -> str:
    explicit_status = doc["scalars"].get("status", "").strip()
    if explicit_status:
        return explicit_status
    if snapshot is not None:
        return "active"
    return "draft"


def _build_profile_item(
    path: Path, snapshots: dict[str, MatchSnapshot]
) -> JobProfileItem | None:
    doc = _try_read_yaml_doc(path)
    if doc is None:
        return None
    job_profile_id = path.stem
    snapshot = snapshots.get(job_profile_id)
    updated_at = (
        snapshot["updated_at"]
        if snapshot is not None
        else _format_utc_timestamp(path.stat().st_mtime)
    )
    return {
        "job_profile_id": job_profile_id,
        "title": doc["scalars"].get("target_role", job_profile_id),
        "company": doc["scalars"].get("company", ""),
        "status": _derive_status(doc, snapshot),
        "match_score": snapshot["score"] if snapshot is not None else 0,
        "evidence_count": snapshot["evidence_count"] if snapshot is not None else 0,
        "resume_count": 0,
        "updated_at": updated_at,
        "business_domain": doc["scalars"].get("business_domain", ""),
        "source_jd": doc["scalars"].get("source_jd", ""),
        "tone": doc["scalars"].get("tone", ""),
        "keywords": doc["lists"].get("keywords", []),
        "must_have": doc["lists"].get("must_have", []),
        "nice_to_have": doc["lists"].get("nice_to_have", []),
        "seniority_signal": doc["lists"].get("seniority_signal", []),
    }


def _matches_query(item: JobProfileItem, query: str) -> bool:
    if not query:
        return True
    normalized_query = query.casefold()
    haystack = " ".join(
        [
            item["title"],
            item["company"],
            item["business_domain"],
            item["source_jd"],
            item["tone"],
            *item["keywords"],
            *item["must_have"],
            *item["nice_to_have"],
            *item["seniority_signal"],
        ]
    ).casefold()
    return normalized_query in haystack


def _matches_tags(item: JobProfileItem, tags: list[str]) -> bool:
    if not tags:
        return True
    normalized_keywords = {value.casefold() for value in item["keywords"]}
    return all(tag.casefold() in normalized_keywords for tag in tags)


def _coerce_tag_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    tags: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            tags.append(item)
    return tags


def _parse_page_size(value: object) -> int:
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            parsed = 20
    else:
        parsed = 20
    return max(1, min(parsed, 100))


def _parse_cursor(value: object) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _parse_sort_field(value: object) -> str:
    field = str(value or "updated_at")
    if field in {"match_score", "updated_at"}:
        return field
    return "updated_at"


def _parse_sort_order(value: object) -> str:
    order = str(value or "desc")
    if order in {"asc", "desc"}:
        return order
    return "desc"


def _apply_filters(
    items: list[JobProfileItem], filters: dict[str, object]
) -> list[JobProfileItem]:
    status_filter = str(filters.get("status") or "").strip()
    query_filter = str(filters.get("query") or "").strip()
    tags_filter = _coerce_tag_list(filters.get("tags"))

    filtered: list[JobProfileItem] = []
    for item in items:
        if status_filter and item["status"] != status_filter:
            continue
        if not _matches_query(item, query_filter):
            continue
        if not _matches_tags(item, tags_filter):
            continue
        filtered.append(item)
    return filtered


def _sort_items(
    items: list[JobProfileItem], field: str, order: str
) -> list[JobProfileItem]:
    reverse = order != "asc"
    if field == "match_score":
        return sorted(
            items,
            key=lambda item: (
                item["match_score"],
                item["updated_at"],
                item["job_profile_id"],
            ),
            reverse=reverse,
        )
    return sorted(
        items,
        key=lambda item: (item["updated_at"], item["job_profile_id"]),
        reverse=reverse,
    )


def handle_jobs_list_profiles(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = cast(dict[str, str], params.get("sort") or {})
    filters = cast(dict[str, object], params.get("filters") or {})

    snapshots = _load_matching_snapshots()
    items: list[JobProfileItem] = []
    for path in _glob_files(_JOB_PROFILE_DIR, "*.yaml"):
        item = _build_profile_item(path, snapshots)
        if item is not None:
            items.append(item)
    items = _apply_filters(items, filters)
    items = _sort_items(
        items,
        _parse_sort_field(sort.get("field")),
        _parse_sort_order(sort.get("order")),
    )

    paged_items = items[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(items) else None

    result: dict[str, object] = {
        "meta": {"correlation_id": correlation_id},
        "items": paged_items,
        "next_cursor": next_cursor,
    }
    return result
