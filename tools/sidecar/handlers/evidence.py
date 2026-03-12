from __future__ import annotations

import json
import mimetypes
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from tools.infra.persistence.yaml_io import parse_simple_yaml

_EVIDENCE_DIR = Path("evidence_cards")
_MATCHING_REPORT_DIR = Path("matching_reports")
_SUBMISSIONS_DIR = Path("outputs") / "submissions"
_APP_DATA_DIR = Path("app-data")
_UPDATABLE_FIELDS = {
    "title",
    "time_range",
    "context",
    "role_scope",
    "actions",
    "results",
    "stack",
    "tags",
}
_MANAGED_EVIDENCE_KEYS = {
    "id",
    "title",
    "time_range",
    "context",
    "role_scope",
    "status",
    "created_at",
    "updated_at",
    "actions",
    "results",
    "stack",
    "artifacts",
    "tags",
}


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _split_multiline_text(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


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
    field = str(value or "updated_at")
    if field in {"updated_at", "score"}:
        return field
    return "updated_at"


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


def _validate_string_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{name} must be a list of strings")
        items.append(item)
    return items


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_list(lines: list[str], key: str, values: list[str]) -> None:
    lines.append(f"{key}:")
    for value in values:
        lines.append(f"  - {_quote(value)}")


def _artifact_dir(evidence_id: str) -> Path:
    return _APP_DATA_DIR / "evidence" / evidence_id / "artifacts"


def _artifact_meta_path(evidence_id: str, resource_id: str) -> Path:
    return _artifact_dir(evidence_id) / f"{resource_id}.meta.json"


def _load_artifact_meta(evidence_id: str, resource_id: str) -> dict[str, Any] | None:
    meta_path = _artifact_meta_path(evidence_id, resource_id)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _artifact_summary(evidence_id: str, token: str) -> dict[str, Any]:
    meta = _load_artifact_meta(evidence_id, token)
    if meta is not None:
        return {
            "resource_id": meta.get("resource_id", token),
            "filename": meta.get("filename", ""),
            "mime_type": meta.get("mime_type", ""),
            "size_bytes": meta.get("size_bytes", 0),
            "created_at": meta.get("created_at", ""),
        }
    return {
        "resource_id": token,
        "filename": token,
        "mime_type": "",
        "size_bytes": 0,
        "created_at": "",
    }


def _split_top_level_blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
        if match:
            if current_key is not None:
                blocks.append((current_key, current_lines))
            current_key = match.group(1)
            current_lines = [line]
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        blocks.append((current_key, current_lines))
    return blocks


def _preserved_blocks(text: str) -> list[list[str]]:
    preserved: list[list[str]] = []
    for key, lines in _split_top_level_blocks(text):
        if key not in _MANAGED_EVIDENCE_KEYS:
            preserved.append(lines)
    return preserved


def _write_evidence_file(
    path: Path, fields: dict[str, Any], preserved_blocks: list[list[str]] | None = None
) -> None:
    lines = [
        f"id: {_quote(fields['id'])}",
        f"title: {_quote(fields['title'])}",
        f"time_range: {_quote(fields['time_range'])}",
        f"context: {_quote(fields['context'])}",
        f"role_scope: {_quote(fields['role_scope'])}",
        f"status: {_quote(fields['status'])}",
        f"created_at: {_quote(fields['created_at'])}",
        f"updated_at: {_quote(fields['updated_at'])}",
    ]
    _write_list(lines, "actions", fields["actions"])
    _write_list(lines, "results", fields["results"])
    _write_list(lines, "stack", fields["stack"])
    _write_list(lines, "artifacts", fields.get("artifacts", []))
    _write_list(lines, "tags", fields["tags"])
    if preserved_blocks:
        for block in preserved_blocks:
            lines.extend(block)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _running_submission_profile_ids() -> set[str]:
    profile_ids: set[str] = set()
    if not _SUBMISSIONS_DIR.exists():
        return profile_ids
    for path in _SUBMISSIONS_DIR.rglob("submission_log.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("status") != "running":
            continue
        profile_path = str(payload.get("profile_path", "")).strip()
        if not profile_path:
            continue
        profile_ids.add(Path(profile_path).stem)
    return profile_ids


def _is_evidence_referenced_by_active_run(evidence_id: str) -> bool:
    profile_ids = _running_submission_profile_ids()
    if not profile_ids or not _MATCHING_REPORT_DIR.exists():
        return False
    for path in _MATCHING_REPORT_DIR.glob("*.yaml"):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if doc["scalars"].get("job_profile_id", "") not in profile_ids:
            continue
        if evidence_id in doc["lists"].get("evidence_card_ids", []):
            return True
    return False


def _find_evidence_path(evidence_id: str) -> Path | None:
    if not _EVIDENCE_DIR.exists():
        return None
    for path in sorted(_EVIDENCE_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        doc = parse_simple_yaml(text)
        if doc["scalars"].get("id", path.stem) == evidence_id:
            return path
    return None


def _load_evidence_cards() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    if not _EVIDENCE_DIR.exists():
        return cards
    for path in sorted(_EVIDENCE_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        doc = parse_simple_yaml(text)
        s = doc["scalars"]
        score_raw = s.get("score", s.get("score_total", "0"))
        try:
            score = int(score_raw) if score_raw else 0
        except ValueError:
            score = 0
        cards.append(
            {
                "evidence_id": s.get("id", path.stem),
                "title": s.get("title", ""),
                "time_range": s.get("time_range", ""),
                "role_scope": s.get("role_scope", ""),
                "score": score,
                "status": s.get("status", "ready"),
                "updated_at": s.get("updated_at", ""),
                "tags": doc["lists"].get("tags", []),
            }
        )
    return cards


def _load_evidence_detail(evidence_id: str) -> dict[str, Any] | None:
    path = _find_evidence_path(evidence_id)
    if path is None:
        return None

    text = path.read_text(encoding="utf-8")
    doc = parse_simple_yaml(text)
    s = doc["scalars"]
    l = doc["lists"]
    actions = l.get("actions", [])
    results = l.get("results", [])
    artifacts = [
        _artifact_summary(evidence_id, token) for token in l.get("artifacts", [])
    ]
    return {
        "evidence_id": s.get("id", path.stem),
        "title": s.get("title", ""),
        "time_range": s.get("time_range", ""),
        "context": s.get("context", ""),
        "role_scope": s.get("role_scope", ""),
        "actions": "\n".join(actions),
        "results": "\n".join(results),
        "stack": l.get("stack", []),
        "tags": l.get("tags", []),
        "artifacts": artifacts,
    }


def handle_evidence_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = params.get("sort") or {}
    filters = params.get("filters") or {}
    cards = _load_evidence_cards()

    query_filter = str(filters.get("query") or "").strip().casefold()
    status_filter = str(filters.get("status") or "").strip()
    role_filter = str(filters.get("role") or "").strip().casefold()
    tags_filter = filters.get("tags")
    date_start, date_end = _parse_date_range(filters.get("date_range"))

    normalized_tags: list[str] = []
    if isinstance(tags_filter, list):
        normalized_tags = [
            str(tag).casefold() for tag in tags_filter if str(tag).strip()
        ]

    filtered: list[dict[str, Any]] = []
    for card in cards:
        if status_filter and card["status"] != status_filter:
            continue
        if role_filter and role_filter not in str(card["role_scope"]).casefold():
            continue
        if query_filter:
            haystack = " ".join(
                [
                    str(card["title"]),
                    str(card["role_scope"]),
                    str(card["time_range"]),
                ]
            ).casefold()
            if query_filter not in haystack:
                continue
        if normalized_tags:
            card_tags = {str(tag).casefold() for tag in card.get("tags", [])}
            if not all(tag in card_tags for tag in normalized_tags):
                continue
        if date_start or date_end:
            updated_at = _safe_parse_iso_datetime(str(card.get("updated_at", "")))
            if updated_at is None:
                continue
            if date_start and updated_at < date_start:
                continue
            if date_end and updated_at > date_end:
                continue
        filtered.append(card)

    sort_field = _parse_sort_field(sort.get("field"))
    sort_order = _parse_sort_order(sort.get("order"))
    reverse = sort_order != "asc"
    if sort_field == "score":
        filtered.sort(
            key=lambda item: (int(item.get("score", 0)), item.get("updated_at", "")),
            reverse=reverse,
        )
    else:
        filtered.sort(
            key=lambda item: item.get("updated_at", ""),
            reverse=reverse,
        )

    paginated = filtered[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(filtered) else None

    return {
        "meta": {"correlation_id": correlation_id},
        "items": [
            {
                "evidence_id": item["evidence_id"],
                "title": item["title"],
                "time_range": item["time_range"],
                "role_scope": item["role_scope"],
                "score": item["score"],
                "status": item["status"],
                "updated_at": item["updated_at"],
            }
            for item in paginated
        ],
        "next_cursor": next_cursor,
    }


def handle_evidence_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = params["evidence_id"]

    detail = _load_evidence_detail(evidence_id)
    if detail is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")

    return {
        "meta": {"correlation_id": correlation_id},
        "evidence": detail,
    }


def handle_evidence_create(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    title = str(params.get("title", "")).strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > 200:
        raise ValueError("title must not exceed 200 characters")

    created_at = _utcnow_iso()
    evidence_id = f"ec_{uuid4().hex[:8]}"
    fields = {
        "id": evidence_id,
        "title": title,
        "time_range": str(params.get("time_range", "")),
        "context": str(params.get("context", "")),
        "role_scope": str(params.get("role_scope", "")),
        "status": "draft",
        "created_at": created_at,
        "updated_at": created_at,
        "actions": _split_multiline_text(str(params.get("actions", ""))),
        "results": _split_multiline_text(str(params.get("results", ""))),
        "stack": _validate_string_list("stack", params.get("stack", [])),
        "artifacts": [],
        "tags": _validate_string_list("tags", params.get("tags", [])),
    }
    _write_evidence_file(_EVIDENCE_DIR / f"{evidence_id}.yaml", fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "evidence_id": evidence_id,
        "status": "draft",
        "created_at": created_at,
    }


def handle_evidence_update(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = str(params["evidence_id"])
    patch = params.get("patch", {})
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")

    unsupported_fields = set(patch) - _UPDATABLE_FIELDS
    if unsupported_fields:
        unsupported = ", ".join(sorted(unsupported_fields))
        raise ValueError(f"unsupported evidence patch fields: {unsupported}")

    path = _find_evidence_path(evidence_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")

    text = path.read_text(encoding="utf-8")
    doc = parse_simple_yaml(text)
    s = doc["scalars"]
    l = doc["lists"]
    preserved_blocks = _preserved_blocks(text)

    title = str(patch.get("title", s.get("title", ""))).strip()
    if not title:
        raise ValueError("title must not be empty")
    if len(title) > 200:
        raise ValueError("title must not exceed 200 characters")

    updated_at = _utcnow_iso()
    fields = {
        "id": s.get("id", evidence_id),
        "title": title,
        "time_range": str(patch.get("time_range", s.get("time_range", ""))),
        "context": str(patch.get("context", s.get("context", ""))),
        "role_scope": str(patch.get("role_scope", s.get("role_scope", ""))),
        "status": s.get("status", "draft"),
        "created_at": s.get("created_at", updated_at),
        "updated_at": updated_at,
        "actions": _split_multiline_text(
            str(patch.get("actions", "\n".join(l.get("actions", []))))
        ),
        "results": _split_multiline_text(
            str(patch.get("results", "\n".join(l.get("results", []))))
        ),
        "stack": _validate_string_list("stack", patch.get("stack", l.get("stack", []))),
        "artifacts": l.get("artifacts", []),
        "tags": _validate_string_list("tags", patch.get("tags", l.get("tags", []))),
    }
    _write_evidence_file(path, fields, preserved_blocks=preserved_blocks)
    return {
        "meta": {"correlation_id": correlation_id},
        "evidence_id": evidence_id,
        "updated_at": updated_at,
    }


def handle_evidence_delete(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = str(params["evidence_id"])

    path = _find_evidence_path(evidence_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")
    if _is_evidence_referenced_by_active_run(evidence_id):
        raise RuntimeError(f"CONFLICT: active run references {evidence_id}")

    path.rename(path.with_suffix(".yaml.deleted"))
    return {
        "meta": {"correlation_id": correlation_id},
        "evidence_id": evidence_id,
        "deleted": True,
    }


def _store_artifact(evidence_id: str, source: Path) -> str:
    resource_id = f"res_{uuid4().hex[:8]}"
    dest_dir = _artifact_dir(evidence_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{resource_id}_{source.name}"
    shutil.copy2(source, dest_path)
    mime_type, _ = mimetypes.guess_type(dest_path.name)
    created_at = _utcnow_iso()
    meta = {
        "resource_id": resource_id,
        "filename": source.name,
        "mime_type": mime_type or "",
        "size_bytes": dest_path.stat().st_size,
        "created_at": created_at,
    }
    _artifact_meta_path(evidence_id, resource_id).write_text(
        json.dumps(meta, ensure_ascii=False),
        encoding="utf-8",
    )
    return resource_id


def handle_evidence_import(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    source_paths = params.get("source_paths")
    if not isinstance(source_paths, list) or not source_paths:
        raise ValueError("source_paths must be a non-empty list")

    mode = str(params.get("mode") or "create").strip()
    if mode not in {"create", "append", "replace"}:
        raise ValueError(f"unsupported import mode: {mode}")

    target_id = str(params.get("target_evidence_id") or "").strip()
    evidence_id = target_id
    preserved_blocks: list[list[str]] | None = None
    target_path: Path | None = None
    existing_artifacts: list[str] = []
    if mode in {"append", "replace"}:
        if not evidence_id:
            raise ValueError("target_evidence_id is required for append/replace")
        target_path = _find_evidence_path(evidence_id)
        if target_path is None:
            raise KeyError(f"NOT_FOUND: {evidence_id}")
        text = target_path.read_text(encoding="utf-8")
        doc = parse_simple_yaml(text)
        preserved_blocks = _preserved_blocks(text)
        s = doc["scalars"]
        l = doc["lists"]
        existing_artifacts = l.get("artifacts", [])
        fields = {
            "id": s.get("id", evidence_id),
            "title": s.get("title", ""),
            "time_range": s.get("time_range", ""),
            "context": s.get("context", ""),
            "role_scope": s.get("role_scope", ""),
            "status": s.get("status", "draft"),
            "created_at": s.get("created_at", _utcnow_iso()),
            "updated_at": _utcnow_iso(),
            "actions": l.get("actions", []),
            "results": l.get("results", []),
            "stack": l.get("stack", []),
            "tags": l.get("tags", []),
        }
    else:
        evidence_id = f"ec_{uuid4().hex[:8]}"
        created_at = _utcnow_iso()
        first_name = Path(str(source_paths[0])).stem
        title = first_name[:200] if first_name else "Imported evidence"
        fields = {
            "id": evidence_id,
            "title": title,
            "time_range": "",
            "context": "",
            "role_scope": "",
            "status": "draft",
            "created_at": created_at,
            "updated_at": created_at,
            "actions": [],
            "results": [],
            "stack": [],
            "tags": [],
        }

    imported_resources: list[str] = []
    for raw in source_paths:
        source = Path(str(raw))
        if not source.exists() or not source.is_file():
            raise ValueError(f"source path not found: {source}")
        imported_resources.append(_store_artifact(evidence_id, source))

    if mode == "replace":
        artifacts = imported_resources
    elif mode == "append":
        artifacts = existing_artifacts + imported_resources
    else:
        artifacts = imported_resources

    fields["artifacts"] = artifacts
    destination = target_path or (_EVIDENCE_DIR / f"{evidence_id}.yaml")
    _write_evidence_file(destination, fields, preserved_blocks)

    return {
        "meta": {"correlation_id": correlation_id},
        "evidence_id": evidence_id,
        "imported_resources": imported_resources,
    }
