from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib import request
from urllib.parse import urlparse
from uuid import uuid4

from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import ParsedDoc, parse_simple_yaml
from tools.sidecar.handlers import settings as settings_handler

_ROOT_DIR = Path(".")
_JOB_PROFILE_DIR = _ROOT_DIR / "job_profiles"
_JOB_LEAD_DIR = _ROOT_DIR / "job_leads"
_MATCHING_REPORT_DIR = _ROOT_DIR / "matching_reports"
_SUBMISSIONS_DIR = _ROOT_DIR / "outputs" / "submissions"
_JOB_DRAFT_REQUIRED_FIELDS = {
    "target_role",
    "must_have",
    "keywords",
    "jd_summary",
}


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


class JobLeadItem(TypedDict):
    job_lead_id: str
    company: str
    position: str
    source: str
    status: str
    favorited: bool
    created_at: str
    updated_at: str


def _glob_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.glob(pattern))


def _read_yaml_doc(path: Path) -> ParsedDoc:
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def _utcnow_iso() -> str:
    return _format_utc_datetime(datetime.now(timezone.utc))


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_list(lines: list[str], key: str, values: list[str]) -> None:
    lines.append(f"{key}:")
    for value in values:
        lines.append(f"  - {_quote(value)}")


def _validate_string_list(name: str, value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    items: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"{name} must be a list of strings")
        items.append(item)
    return items


def _validate_non_empty_string_list(name: str, value: object) -> list[str]:
    return [item.strip() for item in _validate_string_list(name, value) if item.strip()]


def _write_job_profile_file(path: Path, fields: dict[str, Any]) -> None:
    lines = [
        f"target_role: {_quote(fields.get('target_role', ''))}",
        f"company: {_quote(fields.get('company', ''))}",
        f"source_jd: {_quote(fields.get('source_jd', ''))}",
        f"jd_summary: {_quote(fields.get('jd_summary', ''))}",
        f"source_url: {_quote(fields.get('source_url', ''))}",
        f"job_lead_id: {_quote(fields.get('job_lead_id', ''))}",
        f"business_domain: {_quote(fields.get('business_domain', ''))}",
        f"tone: {_quote(fields.get('tone', ''))}",
        f"description: {_quote(fields.get('description', ''))}",
        f"status: {_quote(fields.get('status', 'draft'))}",
        f"created_at: {_quote(fields.get('created_at', ''))}",
        f"updated_at: {_quote(fields.get('updated_at', ''))}",
        f"review_decision: {_quote(fields.get('review_decision', ''))}",
        f"reviewed_at: {_quote(fields.get('reviewed_at', ''))}",
    ]
    _write_list(lines, "keywords", fields.get("keywords", []))
    _write_list(lines, "must_have", fields.get("must_have", []))
    _write_list(lines, "nice_to_have", fields.get("nice_to_have", []))
    _write_list(lines, "seniority_signal", fields.get("seniority_signal", []))
    _write_list(lines, "missing_items", fields.get("missing_items", []))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_job_lead_file(path: Path, fields: dict[str, Any]) -> None:
    lines = [
        f"id: {_quote(fields.get('id', path.stem))}",
        f"company: {_quote(fields.get('company', ''))}",
        f"position: {_quote(fields.get('position', ''))}",
        f"source: {_quote(fields.get('source', 'manual_jd'))}",
        f"url: {_quote(fields.get('url', ''))}",
        f"status: {_quote(fields.get('status', 'new'))}",
        f"favorited: {_quote(fields.get('favorited', 'false'))}",
        f"job_profile_id: {_quote(fields.get('job_profile_id', ''))}",
        f"created_at: {_quote(fields.get('created_at', ''))}",
        f"updated_at: {_quote(fields.get('updated_at', ''))}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _profile_path(job_profile_id: str) -> Path:
    return _JOB_PROFILE_DIR / f"{job_profile_id}.yaml"


def _lead_path(job_lead_id: str) -> Path:
    return _JOB_LEAD_DIR / f"{job_lead_id}.yaml"


def _try_read_yaml_doc(path: Path) -> ParsedDoc | None:
    try:
        return _read_yaml_doc(path)
    except (OSError, UnicodeDecodeError):
        return None


def _missing_items_for_job_draft(draft: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(draft.get("target_role", "")).strip():
        missing.append("missing_target_role")
    if not str(draft.get("source_jd", "")).strip():
        missing.append("missing_jd_text")
    if not draft.get("must_have"):
        missing.append("missing_must_have")
    if not draft.get("keywords"):
        missing.append("missing_keywords")
    if not str(draft.get("jd_summary", "")).strip():
        missing.append("missing_jd_summary")
    return missing


def _build_job_profile_draft(
    parsed: dict[str, Any], jd_text: str, source_url: str
) -> dict[str, Any]:
    missing_schema_fields = sorted(_JOB_DRAFT_REQUIRED_FIELDS - set(parsed))
    if missing_schema_fields:
        raise ValueError(
            "job profile draft missing required fields: "
            + ", ".join(missing_schema_fields)
        )

    draft = {
        "target_role": str(parsed.get("target_role", "")).strip(),
        "company": str(parsed.get("company", "")).strip(),
        "source_jd": jd_text.strip(),
        "jd_summary": str(parsed.get("jd_summary", "")).strip(),
        "source_url": str(parsed.get("source_url") or source_url).strip(),
        "business_domain": str(parsed.get("business_domain", "")).strip(),
        "tone": str(parsed.get("tone", "")).strip(),
        "description": str(parsed.get("jd_summary", "")).strip(),
        "keywords": _validate_non_empty_string_list(
            "keywords", parsed.get("keywords", [])
        ),
        "must_have": _validate_non_empty_string_list(
            "must_have", parsed.get("must_have", [])
        ),
        "nice_to_have": _validate_non_empty_string_list(
            "nice_to_have", parsed.get("nice_to_have", [])
        ),
        "seniority_signal": _validate_non_empty_string_list(
            "seniority_signal", parsed.get("seniority_signal", [])
        ),
    }
    missing_items = _missing_items_for_job_draft(draft)
    draft["missing_items"] = missing_items
    draft["status"] = "draft_incomplete" if missing_items else "draft_ready_for_review"
    draft["active_target_eligible"] = False
    return draft


def _job_draft_prompt(jd_text: str, source_url: str) -> str:
    return (
        "Parse the pasted job description into a Job Profile draft. Return strict JSON "
        "only with required keys: target_role, must_have, keywords, jd_summary. Optional "
        "keys: company, city, source_url, nice_to_have, business_domain, seniority_signal, tone. "
        "Do not invent facts not present in the JD.\n\n"
        f"source_url: {source_url}\n\nJD:\n{jd_text}"
    )


def _check_source_url_accessible(
    source_url: str, timeout_seconds: int = 5
) -> dict[str, object]:
    if not source_url:
        return {"checked": False, "accessible": False, "status": "not_provided"}
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return {"checked": True, "accessible": False, "status": "invalid_url"}
    if os.environ.get("PPF_JOB_SOURCE_URL_CHECK_MODE") == "stub":
        return {
            "checked": True,
            "accessible": True,
            "status": "accessible",
            "status_code": 200,
            "mode": "stub",
        }
    req = request.Request(
        source_url, method="GET", headers={"User-Agent": "PiProofForge/0.1"}
    )
    try:
        response = request.urlopen(req, timeout=timeout_seconds)
        try:
            status_code = int(getattr(response, "status", 200))
        finally:
            response.close()
    except Exception as exc:
        return {
            "checked": True,
            "accessible": False,
            "status": "job_source_unavailable",
            "error": str(exc),
        }
    accessible = 200 <= status_code < 400
    return {
        "checked": True,
        "accessible": accessible,
        "status": "accessible" if accessible else "job_source_unavailable",
        "status_code": status_code,
    }


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


def _parse_lead_sort_field(value: object) -> str:
    field = str(value or "updated_at")
    if field in {"updated_at", "created_at"}:
        return field
    return "updated_at"


def _parse_sort_order(value: object) -> str:
    order = str(value or "desc")
    if order in {"asc", "desc"}:
        return order
    return "desc"


def _build_lead_item(path: Path) -> JobLeadItem | None:
    doc = _try_read_yaml_doc(path)
    if doc is None:
        return None
    s = doc["scalars"]
    favorited_raw = s.get("favorited", "false").strip().lower()
    created_at = s.get("created_at", _format_utc_timestamp(path.stat().st_mtime))
    return {
        "job_lead_id": s.get("id", path.stem),
        "company": s.get("company", ""),
        "position": s.get("position", s.get("title", "")),
        "source": s.get("source", ""),
        "status": s.get("status", "new"),
        "favorited": favorited_raw in {"true", "1", "yes"},
        "created_at": created_at,
        "updated_at": s.get("updated_at", created_at),
    }


def _apply_lead_filters(
    items: list[JobLeadItem], filters: dict[str, object]
) -> list[JobLeadItem]:
    source_filter = str(filters.get("source") or "").strip()
    status_filter = str(filters.get("status") or "").strip()
    query_filter = str(filters.get("query") or "").strip().casefold()
    favorited_filter = filters.get("favorited")

    filtered: list[JobLeadItem] = []
    for item in items:
        if source_filter and item["source"] != source_filter:
            continue
        if status_filter and item["status"] != status_filter:
            continue
        if favorited_filter is not None and item["favorited"] != bool(favorited_filter):
            continue
        if query_filter:
            haystack = f"{item['company']} {item['position']}".casefold()
            if query_filter not in haystack:
                continue
        filtered.append(item)
    return filtered


def _sort_leads(items: list[JobLeadItem], field: str, order: str) -> list[JobLeadItem]:
    reverse = order != "asc"
    return sorted(
        items, key=lambda item: (item[field], item["job_lead_id"]), reverse=reverse
    )


def _running_submission_profile_ids() -> set[str]:
    profile_ids: set[str] = set()
    if not _SUBMISSIONS_DIR.exists():
        return profile_ids
    for path in _SUBMISSIONS_DIR.rglob("submission_log.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") != "running":
            continue
        profile_path = str(payload.get("profile_path", "")).strip()
        if profile_path:
            profile_ids.add(Path(profile_path).stem)
    return profile_ids


def _clear_lead_profile_reference(job_profile_id: str) -> None:
    if not _JOB_LEAD_DIR.exists():
        return
    for path in _JOB_LEAD_DIR.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        updated_lines: list[str] = []
        changed = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("job_profile_id:"):
                current_value = stripped.split(":", 1)[1].strip().strip('"')
                if current_value == job_profile_id:
                    updated_lines.append('job_profile_id: ""')
                    changed = True
                    continue
            updated_lines.append(line)
        if changed:
            path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def _find_lead_path(job_lead_id: str) -> Path | None:
    direct_path = _lead_path(job_lead_id)
    if direct_path.exists():
        return direct_path
    for path in _glob_files(_JOB_LEAD_DIR, "*.yaml"):
        doc = _try_read_yaml_doc(path)
        if doc is None:
            continue
        if doc["scalars"].get("id", path.stem) == job_lead_id:
            return path
    return None


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


def handle_jobs_generate_profile_draft(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    jd_text = str(params.get("jd_text", "")).strip()
    source_url = str(params.get("source_url", "")).strip()
    if not jd_text:
        raise ValueError("jd_text is required")

    llm_config = settings_handler._load_llm_config()
    base_url = str(llm_config.get("base_url") or "").strip()
    if not base_url:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_blocked_local_provider",
            "code": "BLOCKED_LOCAL_PROVIDER",
            "message": "LLM base_url is not configured.",
            "draft": None,
            "active_target_eligible": False,
        }

    payload = {
        "model": str(llm_config["model"]),
        "messages": [{"role": "user", "content": _job_draft_prompt(jd_text, source_url)}],
        "temperature": float(llm_config["temperature"]),
        "response_format": {"type": "json_object"},
    }
    try:
        client = LLMClient(
            base_url=base_url,
            api_key=str(llm_config["api_key_for_request"]),
            timeout=int(llm_config["timeout"]),
        )
        response = client.post_json(client.chat_completions_url, payload)
        content = LLMClient.extract_content(response).strip()
    except Exception as exc:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_blocked_local_provider",
            "code": "BLOCKED_LOCAL_PROVIDER",
            "message": f"LLM JD parsing is unavailable: {exc}",
            "draft": None,
            "active_target_eligible": False,
        }

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_invalid_json",
            "code": "parse_invalid_json",
            "message": "LLM output is not strict JSON.",
            "draft": None,
            "active_target_eligible": False,
        }
    if not isinstance(parsed, dict):
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_invalid_json",
            "code": "parse_invalid_json",
            "message": "LLM output JSON must be an object.",
            "draft": None,
            "active_target_eligible": False,
        }

    draft = _build_job_profile_draft(cast(dict[str, Any], parsed), jd_text, source_url)
    return {
        "meta": {"correlation_id": correlation_id},
        "status": draft["status"],
        "code": "OK",
        "message": "Job Profile draft generated for user review.",
        "draft": draft,
        "active_target_eligible": False,
    }


def handle_jobs_save_profile_draft(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    draft = params.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("draft must be an object")
    review = params.get("review")
    if not isinstance(review, dict) or str(review.get("decision", "")) != "approved":
        raise ValueError("review_required_before_save")

    normalized = {
        "target_role": str(draft.get("target_role", "")).strip(),
        "company": str(draft.get("company", "")).strip(),
        "source_jd": str(draft.get("source_jd", "")).strip(),
        "jd_summary": str(draft.get("jd_summary", "")).strip(),
        "source_url": str(draft.get("source_url", "")).strip(),
        "business_domain": str(draft.get("business_domain", "")).strip(),
        "tone": str(draft.get("tone", "")).strip(),
        "description": str(draft.get("description") or draft.get("jd_summary") or ""),
        "keywords": _validate_non_empty_string_list(
            "keywords", draft.get("keywords", [])
        ),
        "must_have": _validate_non_empty_string_list(
            "must_have", draft.get("must_have", [])
        ),
        "nice_to_have": _validate_non_empty_string_list(
            "nice_to_have", draft.get("nice_to_have", [])
        ),
        "seniority_signal": _validate_non_empty_string_list(
            "seniority_signal", draft.get("seniority_signal", [])
        ),
    }
    missing_items = _missing_items_for_job_draft(normalized)
    save_mode = str(params.get("save_mode") or "incomplete")
    if save_mode not in {"incomplete", "complete"}:
        raise ValueError(f"unsupported save_mode: {save_mode}")
    if save_mode == "complete" and missing_items:
        raise ValueError("complete job profile requires JD text, role, must_have, keywords, and summary")

    source_url_check = (
        _check_source_url_accessible(normalized["source_url"])
        if save_mode == "complete"
        else {"checked": False, "accessible": False, "status": "not_required"}
    )
    if (
        save_mode == "complete"
        and normalized["source_url"]
        and not bool(source_url_check.get("accessible"))
    ):
        raise ValueError(f"job_source_unavailable: {source_url_check.get('status')}")

    now = _utcnow_iso()
    job_profile_id = str(params.get("job_profile_id") or f"jp_{uuid4().hex[:8]}")
    job_lead_id = ""
    if save_mode == "complete" and normalized["source_url"]:
        job_lead_id = f"jl_{uuid4().hex[:8]}"
        _write_job_lead_file(
            _lead_path(job_lead_id),
            {
                "id": job_lead_id,
                "company": normalized["company"],
                "position": normalized["target_role"],
                "source": "manual_jd",
                "url": normalized["source_url"],
                "status": "new",
                "favorited": "false",
                "job_profile_id": job_profile_id,
                "created_at": now,
                "updated_at": now,
            },
        )

    fields = {
        **normalized,
        "status": "active" if save_mode == "complete" else "saved_incomplete",
        "created_at": now,
        "updated_at": now,
        "review_decision": "approved",
        "reviewed_at": str(review.get("reviewed_at") or now),
        "missing_items": missing_items,
        "job_lead_id": job_lead_id,
    }
    _write_job_profile_file(_profile_path(job_profile_id), fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "status": "saved_complete" if save_mode == "complete" else "saved_incomplete",
        "active_target_eligible": save_mode == "complete",
        "missing_items": missing_items,
        "job_lead_id": job_lead_id,
        "source_url_check": source_url_check,
        "updated_at": now,
    }


def handle_jobs_list_leads(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = cast(dict[str, object], params.get("sort") or {})
    filters = cast(dict[str, object], params.get("filters") or {})

    items: list[JobLeadItem] = []
    for path in _glob_files(_JOB_LEAD_DIR, "*.yaml"):
        item = _build_lead_item(path)
        if item is not None:
            items.append(item)
    items = _apply_lead_filters(items, filters)
    items = _sort_leads(
        items,
        _parse_lead_sort_field(sort.get("field")),
        _parse_sort_order(sort.get("order")),
    )
    paged_items = items[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(items) else None
    return {
        "meta": {"correlation_id": correlation_id},
        "items": paged_items,
        "next_cursor": next_cursor,
    }


def handle_jobs_create_profile(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    title = str(params.get("title", "")).strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > 200:
        raise ValueError("title must not exceed 200 characters")
    status = str(params.get("status") or "draft")
    if status not in {"active", "draft"}:
        raise ValueError(f"unsupported status: {status}")
    created_at = _utcnow_iso()
    job_profile_id = f"jp_{uuid4().hex[:8]}"
    fields = {
        "target_role": title,
        "company": "",
        "source_jd": "",
        "business_domain": "",
        "tone": "",
        "description": str(params.get("description", "")),
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "keywords": _validate_string_list("tags", params.get("tags", [])),
        "must_have": [],
        "nice_to_have": [],
        "seniority_signal": [],
    }
    _write_job_profile_file(_profile_path(job_profile_id), fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "status": status,
        "created_at": created_at,
    }


def handle_jobs_update_profile(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    job_profile_id = str(params["job_profile_id"])
    patch = cast(dict[str, object], params.get("patch") or {})
    path = _profile_path(job_profile_id)
    if not path.exists():
        raise KeyError(f"NOT_FOUND: {job_profile_id}")
    if "title" in patch and not str(patch.get("title", "")).strip():
        raise ValueError("title must not be empty")
    if "status" in patch and str(patch["status"]) not in {
        "active",
        "draft",
        "archived",
    }:
        raise ValueError(f"unsupported status: {patch['status']}")

    doc = _read_yaml_doc(path)
    s = doc["scalars"]
    l = doc["lists"]
    updated_at = _utcnow_iso()
    fields = {
        "target_role": str(patch.get("title", s.get("target_role", ""))).strip(),
        "company": s.get("company", ""),
        "source_jd": s.get("source_jd", ""),
        "business_domain": s.get("business_domain", ""),
        "tone": s.get("tone", ""),
        "description": str(patch.get("description", s.get("description", ""))),
        "status": str(patch.get("status", s.get("status", "draft"))),
        "created_at": s.get("created_at", ""),
        "updated_at": updated_at,
        "keywords": _validate_string_list(
            "tags", patch.get("tags", l.get("keywords", []))
        ),
        "must_have": cast(list[str], l.get("must_have", [])),
        "nice_to_have": cast(list[str], l.get("nice_to_have", [])),
        "seniority_signal": cast(list[str], l.get("seniority_signal", [])),
    }
    _write_job_profile_file(path, fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "updated_at": updated_at,
    }


def handle_jobs_delete_profile(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    job_profile_id = str(params["job_profile_id"])
    path = _profile_path(job_profile_id)
    if not path.exists():
        raise KeyError(f"NOT_FOUND: {job_profile_id}")
    if job_profile_id in _running_submission_profile_ids():
        raise RuntimeError(f"CONFLICT: active run references {job_profile_id}")
    path.rename(path.with_suffix(".yaml.deleted"))
    _clear_lead_profile_reference(job_profile_id)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "deleted": True,
    }


def handle_jobs_convert_lead(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    job_lead_id = str(params["job_lead_id"])
    path = _find_lead_path(job_lead_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {job_lead_id}")
    doc = _read_yaml_doc(path)
    s = doc["scalars"]
    created_at = _utcnow_iso()
    job_profile_id = f"jp_{uuid4().hex[:8]}"
    fields = {
        "target_role": s.get("position", s.get("title", "")),
        "company": s.get("company", ""),
        "source_jd": s.get("url", ""),
        "business_domain": "",
        "tone": "",
        "description": "",
        "status": "draft",
        "created_at": created_at,
        "updated_at": created_at,
        "keywords": [],
        "must_have": [],
        "nice_to_have": [],
        "seniority_signal": [],
    }
    _write_job_profile_file(_profile_path(job_profile_id), fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
    }
