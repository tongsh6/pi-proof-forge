"""投递记录列表与详情 handler。

从 ``submission.py`` 拆出；投递日志目录经原模块运行时读取，保证测试
patch ``submission._SUBMISSIONS_DIR`` / ``submission._submission_log_paths`` 生效。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.sidecar.handlers import submission as _origin
from tools.sidecar.handlers.submission import (
    _ALLOWED_RETRY_STRATEGIES,
    _load_submission_log,
    _managed_evidence,
    _now_iso,
    _platform_feedback_summary,
)


def _last_step(payload: dict[str, Any]) -> dict[str, str]:
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return {"name": "", "status": "", "detail": ""}
    raw = steps[-1]
    if not isinstance(raw, dict):
        return {"name": "", "status": "", "detail": ""}
    return {
        "name": str(raw.get("name", "")),
        "status": str(raw.get("status", "")),
        "detail": str(raw.get("detail", "")),
    }


def _step_by_name(payload: dict[str, Any], name: str) -> dict[str, str]:
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        return {"name": "", "status": "", "detail": ""}
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("name", "")) == name:
            return {
                "name": str(raw.get("name", "")),
                "status": str(raw.get("status", "")),
                "detail": str(raw.get("detail", "")),
            }
    return {"name": "", "status": "", "detail": ""}


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


def _managed_delivery(payload: dict[str, Any]) -> bool:
    inputs=payload.get('input_artifacts',{})
    return payload.get('transport')=='liepin_api' or (isinstance(inputs,dict) and bool(inputs.get('delivery_attempt_id')))


def _submission_item(path: Path) -> dict[str, Any]:
    payload = _load_submission_log(path)
    inputs = payload.get('input_artifacts', {}) if _managed_delivery(payload) else {}
    historical_identity = _managed_evidence(path, payload) if _managed_delivery(payload) and (not inputs.get('company') or not inputs.get('position')) else {}
    submitted_at = str(payload.get("ended_at") or payload.get("started_at") or "")
    rate_limit = _step_by_name(payload, "rate_limit")
    return {
        "submission_id": str(payload.get("run_id", path.parent.name)),
        "retry_allowed": not _managed_delivery(payload) and str(payload.get("transport", "")) != "manual",
        "company": str(inputs.get('company') or historical_identity.get("company") or payload.get("company", payload.get("job_company", ""))),
        "position": str(inputs.get('position') or historical_identity.get("position") or payload.get("position", payload.get("job_title", ""))),
        "channel": str(payload.get("platform", path.parent.parent.name)),
        "mode": str(payload.get("mode", "")),
        "status": str(payload.get("status", "")),
        "error": str(payload.get("error", "")),
        "job_url": str(payload.get("job_url", "")),
        "submitted_at": submitted_at,
        "last_step": _last_step(payload),
        "rate_limit_status": rate_limit["status"],
        "rate_limit_detail": rate_limit["detail"],
        "platform_feedback": _platform_feedback_summary(path.parent) if _managed_delivery(payload) else {},
    }


def _find_submission_log(submission_id: str) -> Path | None:
    for path in _origin._submission_log_paths():
        payload = _load_submission_log(path)
        if str(payload.get("run_id", path.parent.name)) == submission_id:
            return path
    return None


def _detail_step(raw: object, run_dir: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "name": "",
            "status": "",
            "detail": "",
            "screenshot": "",
            "screenshot_path": "",
            "screenshot_exists": False,
        }
    screenshot = str(raw.get("screenshot", ""))
    screenshot_path = ""
    screenshot_exists = False
    if screenshot:
        candidate_raw_path = run_dir / screenshot
        candidate_path = candidate_raw_path.resolve()
        run_root = run_dir.resolve()
        if candidate_path.is_relative_to(run_root):
            screenshot_path = str(candidate_raw_path)
            screenshot_exists = candidate_path.exists()
    return {
        "name": str(raw.get("name", "")),
        "status": str(raw.get("status", "")),
        "detail": str(raw.get("detail", "")),
        "screenshot": screenshot,
        "screenshot_path": screenshot_path,
        "screenshot_exists": screenshot_exists,
    }


def handle_submission_detail(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    submission_id = str(params["submission_id"])
    log_path = _find_submission_log(submission_id)
    if log_path is None:
        raise KeyError(f"NOT_FOUND: {submission_id}")

    payload = _load_submission_log(log_path)
    run_dir = log_path.parent
    steps_raw = payload.get("steps", [])
    steps = (
        [_detail_step(step, run_dir) for step in steps_raw]
        if isinstance(steps_raw, list)
        else []
    )
    yaml_path = run_dir / "submission_log.yaml"
    inputs = payload.get('input_artifacts', {}) if _managed_delivery(payload) else {}
    evidence = _managed_evidence(log_path, payload)
    api_attempted = payload.get('mode') == 'submit' and any(s['name'] == 'api_submit' or (_managed_delivery(payload) and s['name']=='submit' and s['status']=='success') for s in steps)
    return {
        "meta": {"correlation_id": correlation_id},
        "submission": {
            **_submission_item(log_path),
            "started_at": str(payload.get("started_at", "")),
            "ended_at": str(payload.get("ended_at", "")),
            "resume_path": str(payload.get("resume_path", "")),
            "profile_path": str(payload.get("profile_path", "")),
            "headless": bool(payload.get("headless", True)),
            "browser_channel": str(payload.get("browser_channel", "")),
            "steps": steps,
            "terminal_status": str(payload.get("terminal_status", payload.get("status", ""))),
            "evidence": evidence,
            "resume_version_id": str(evidence.get("resume_version_id") or inputs.get('resume_version') or payload.get("resume_version_id", "")),
            "parent_run_id": str(inputs.get('parent_run_id', '')),
            "job_lead_id": str(inputs.get('candidate_id', '')),
            "receipt_source": str(inputs.get('receipt_source') or payload.get("receipt_source", "")),
            "adapter_capabilities": payload.get("adapter_capabilities", {}),
            "original_job_lead": payload.get("original_job_lead", {}),
            "final_verified_target": payload.get("final_verified_target", {}),
            "session_metadata": payload.get("session_metadata", {}),
            "target_recovery_attempts": payload.get("target_recovery_attempts", []),
            "recovered_target_confirmation": payload.get("recovered_target_confirmation", {}),
            "resume_target_mismatch_warning": payload.get("resume_target_mismatch_warning", {}),
            "next_action": str(payload.get("next_action", "")),
            "final_submit_attempted": api_attempted or bool(payload.get("final_submit_attempted", False)),
            "external_submission_attempted": api_attempted or bool(payload.get("external_submission_attempted", False)),
            "log_json_path": str(log_path),
            "log_yaml_path": str(yaml_path) if yaml_path.exists() else "",
        },
    }


def handle_submission_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = params.get("sort") or {}
    filters = params.get("filters") or {}

    items = [_submission_item(path) for path in _origin._submission_log_paths()]

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
    for path in _origin._submission_log_paths():
        payload = _load_submission_log(path)
        if str(payload.get("run_id", path.parent.name)) == submission_id:
            if payload.get('transport') == 'liepin_api':
                raise ValueError('api_submission_retry_forbidden')
            if payload.get('transport') == 'manual':
                raise ValueError('manual_record_retry_forbidden')
            if _managed_delivery(payload):
                raise ValueError('managed_submission_retry_forbidden')
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
