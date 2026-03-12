from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SUBMISSIONS_DIR = Path("outputs") / "submissions"
_ALLOWED_RETRY_STRATEGIES = {"same_channel", "fallback_email"}


def _submission_log_paths() -> list[Path]:
    if not _SUBMISSIONS_DIR.exists():
        return []
    return sorted(_SUBMISSIONS_DIR.rglob("submission_log.json"))


def _load_submission_log(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_cursor(value: object) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


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


def _parse_sort_field(value: object) -> str:
    field = str(value or "submitted_at")
    if field in {"submitted_at", "status"}:
        return field
    return "submitted_at"


def _parse_sort_order(value: object) -> str:
    order = str(value or "desc")
    if order in {"asc", "desc"}:
        return order
    return "desc"


def _safe_parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date_range(value: object) -> tuple[datetime | None, datetime | None]:
    if isinstance(value, dict):
        start_raw = value.get("start") or value.get("from")
        end_raw = value.get("end") or value.get("to")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        start_raw, end_raw = value
    else:
        return None, None
    start = _safe_parse_iso_datetime(str(start_raw)) if start_raw else None
    end = _safe_parse_iso_datetime(str(end_raw)) if end_raw else None
    return start, end


def _submission_item(path: Path) -> dict[str, Any]:
    payload = _load_submission_log(path)
    submitted_at = str(payload.get("ended_at") or payload.get("started_at") or "")
    return {
        "submission_id": str(payload.get("run_id", path.parent.name)),
        "company": str(payload.get("company", payload.get("job_company", ""))),
        "position": str(payload.get("position", payload.get("job_title", ""))),
        "channel": str(payload.get("platform", path.parent.parent.name)),
        "status": str(payload.get("status", "")),
        "submitted_at": submitted_at,
    }


def handle_submission_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = params.get("sort") or {}
    filters = params.get("filters") or {}

    items = [_submission_item(path) for path in _submission_log_paths()]

    status_filter = str(filters.get("status") or "").strip()
    channel_filter = str(filters.get("channel") or "").strip()
    company_filter = str(filters.get("company") or "").strip()
    date_start, date_end = _parse_date_range(filters.get("date_range"))

    filtered: list[dict[str, Any]] = []
    for item in items:
        if status_filter and item["status"] != status_filter:
            continue
        if channel_filter and item["channel"] != channel_filter:
            continue
        if company_filter and item["company"] != company_filter:
            continue
        if date_start or date_end:
            submitted_at = _safe_parse_iso_datetime(str(item.get("submitted_at", "")))
            if submitted_at is None:
                continue
            if date_start and submitted_at < date_start:
                continue
            if date_end and submitted_at > date_end:
                continue
        filtered.append(item)

    sort_field = _parse_sort_field(sort.get("field"))
    sort_order = _parse_sort_order(sort.get("order"))
    reverse = sort_order != "asc"
    if sort_field == "status":
        filtered.sort(key=lambda item: item.get("status", ""), reverse=reverse)
    else:
        filtered.sort(
            key=lambda item: item.get("submitted_at", ""),
            reverse=reverse,
        )

    page = filtered[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(filtered) else None
    return {
        "meta": {"correlation_id": correlation_id},
        "items": page,
        "next_cursor": next_cursor,
    }


def handle_submission_retry(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    submission_id = str(params["submission_id"])
    strategy = str(params.get("strategy", "same_channel"))
    if strategy not in _ALLOWED_RETRY_STRATEGIES:
        raise ValueError(f"unsupported retry strategy: {strategy}")

    found = False
    retried_at = datetime.now(timezone.utc).isoformat()
    for path in _submission_log_paths():
        payload = _load_submission_log(path)
        if str(payload.get("run_id", path.parent.name)) == submission_id:
            payload["status"] = "queued"
            payload["retry_count"] = _parse_cursor(payload.get("retry_count")) + 1
            payload["retry_strategy"] = strategy
            payload["ended_at"] = retried_at
            payload["retried_at"] = retried_at
            _ = path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            found = True
            break
    if not found:
        raise KeyError(f"NOT_FOUND: {submission_id}")

    return {
        "meta": {"correlation_id": correlation_id},
        "submission_id": submission_id,
        "status": "queued",
    }
