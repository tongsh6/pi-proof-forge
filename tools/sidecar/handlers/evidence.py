from __future__ import annotations

import json
import hashlib
import mimetypes
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from tools.infra import evidence_inference as inference
from tools.infra import evidence_provenance as provenance
from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.evidence_sources import (SOURCE_FIELDS, field_values, read_source_documents,
    validate_field_sources, source_fingerprints, validated_source_inputs)
from tools.policy.exclusions import load_evidence_inference_enabled
from tools.sidecar.handlers import settings as settings_handler

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
    "artifacts",
    "tags",
    "time_range_provenance",
    "role_scope_provenance",
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
    "raw_source",
    "source_material_ids",
    "review_decision",
    "reviewed_at",
    "candidate_pool_eligible",
    "missing_items",
    "source_documents_json",
    "field_sources_json",
    "source_material_fingerprints_json",
    "reviewed_facts_json",
    "source_whole_material_ids_json",
    "time_range_provenance_json",
    "role_scope_provenance_json",
}
_DRAFT_REQUIRED_FIELDS = {
    "source_material_ids",
    "title",
    "context",
    "actions",
    "results",
    "artifacts",
    "stack",
    "tags",
}



def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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


def _validate_string_list(name: str, value: Any, *, reject_blank: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{name} must be a list of strings")
        if reject_blank and not item.strip():
            raise ValueError(f"{name} must not contain blank items")
        items.append(item)
    return items


def _quote(value: str) -> str:
    # 所有字符串保持在单个 YAML 物理行，既有解析器还原完整文字与换行。
    return json.dumps(value)


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
    if "raw_source" in fields:
        lines.append(f"raw_source: {_quote(str(fields.get('raw_source', '')))}")
    if "source_material_ids" in fields:
        _write_list(lines, "source_material_ids", fields.get("source_material_ids", []))
    if fields.get("source_documents_json"):
        lines.append(f'source_documents_json: {_quote(fields["source_documents_json"])}')
    for key in ('field_sources_json', 'source_material_fingerprints_json', 'reviewed_facts_json', 'source_whole_material_ids_json',
                'time_range_provenance_json', 'role_scope_provenance_json'):
        if fields.get(key):lines.append(f'{key}: {_quote(fields[key])}')
    if "review_decision" in fields:
        lines.append(f"review_decision: {_quote(str(fields.get('review_decision', '')))}")
    if "reviewed_at" in fields:
        lines.append(f"reviewed_at: {_quote(str(fields.get('reviewed_at', '')))}")
    if "candidate_pool_eligible" in fields:
        lines.append(
            f"candidate_pool_eligible: {_quote(str(bool(fields.get('candidate_pool_eligible'))).lower())}"
        )
    if "missing_items" in fields:
        _write_list(lines, "missing_items", fields.get("missing_items", []))
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


def _source_document_count(scalars: dict[str, Any]) -> int:
    try:
        documents = json.loads(str(scalars.get("source_documents_json") or "[]"))
    except (TypeError, ValueError):
        return 0
    return len(documents) if isinstance(documents, list) else 0


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
                "candidate_pool_eligible": s.get("status")=="saved_eligible" and s.get("candidate_pool_eligible")=="true" and bool(doc["lists"].get("results")) and bool(doc["lists"].get("artifacts")) and not _source_error(doc),
                "updated_at": s.get("updated_at", ""),
                "tags": doc["lists"].get("tags", []),
                "time_range_level": provenance.field_level(s, "time_range"),
                "role_scope_level": provenance.field_level(s, "role_scope"),
                "source_document_count": _source_document_count(s),
            }
        )
    return cards


def _source_error(doc):
    from tools.infra.evidence_fact_scope import project_fact_scope
    try:
        sources = validated_source_inputs(doc, materials_dir())
        scalars = doc["scalars"]
        project_fact_scope(doc, json.loads(scalars.get("source_documents_json") or "[]"),
                           json.loads(scalars.get("field_sources_json") or "[]"), documents=sources.documents)
    except ValueError as exc:
        return str(exc)
    return ''


def _load_evidence_detail(evidence_id: str) -> dict[str, Any] | None:
    path = _find_evidence_path(evidence_id)
    if path is None:
        return None

    raw = path.read_bytes()
    doc = parse_simple_yaml(raw.decode("utf-8"))
    s = doc["scalars"]
    l = doc["lists"]
    actions = l.get("actions", [])
    results = l.get("results", [])
    artifacts = [
        _artifact_summary(evidence_id, token) for token in l.get("artifacts", [])
    ]
    source_documents = json.loads(s.get("source_documents_json") or "[]")
    field_sources = json.loads(s.get("field_sources_json") or "[]")
    from tools.infra.evidence_fact_scope import project_fact_scope
    source_error, scopes = "", []
    try:
        sources = validated_source_inputs(doc, materials_dir())
        if path.read_bytes() == raw:
            scopes = project_fact_scope(doc, source_documents, field_sources, documents=sources.documents)
    except ValueError as exc:
        source_error = str(exc)
    return {
        "evidence_id": s.get("id", path.stem),
        "title": s.get("title", ""),
        "time_range": s.get("time_range", ""),
        "context": s.get("context", ""),
        "role_scope": s.get("role_scope", ""),
        "actions": actions,
        "results": results,
        "stack": l.get("stack", []),
        "tags": l.get("tags", []),
        "artifacts": artifacts,
        "raw_source": s.get("raw_source", ""),
        "source_material_ids": l.get("source_material_ids", []),
        "source_documents": source_documents,
        "field_sources": field_sources,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "fact_scope_review": scopes,
        "source_error": source_error,
        "review_decision": s.get("review_decision", ""),
        "reviewed_at": s.get("reviewed_at", ""),
        "candidate_pool_eligible": s.get("candidate_pool_eligible", "false") == "true" and not source_error,
        "missing_items": l.get("missing_items", []),
        "time_range_provenance": provenance.field_provenance(s, "time_range"),
        "role_scope_provenance": provenance.field_provenance(s, "role_scope"),
    }


# 跨 handler 共享的材料选择实现（公开名），同时保留原私有名 re-export 兼容测试。
from tools.sidecar.handlers._shared.material_sources import (  # noqa: E402
    materials_dir,
    document as _document,
    documents as _documents,
    material_record_by_id as _material_record_by_id,
    selected_markdown_materials as _selected_markdown_materials,
    selected_text_materials as _selected_text_materials,
)
from tools.sidecar.handlers.evidence_draft import (  # noqa: E402
    _as_string_list,
    _build_evidence_draft,
    _dates_in_text,
    _document_metadata,
    _draft_source_text,
    _employment_windows,
    _llm_draft_prompt,
    _material_text,
    _missing_items_for_draft,
    _normalize_artifacts,
    _validate_markdown_artifacts,
    _validate_results_trace_materials,
    _validate_source_material_ids,
    _verify_saved_provenance,
    handle_evidence_generate_draft,
    handle_evidence_save_draft,
    handle_list_material_documents,
    handle_read_material_document,
)
from tools.sidecar.handlers.evidence_crud import (  # noqa: E402
    handle_evidence_create,
    handle_evidence_delete,
    handle_evidence_get,
    handle_evidence_import,
    handle_evidence_list,
    handle_evidence_update,
)
from tools.sidecar.handlers._shared.evidence_triage import (  # noqa: E402
    card_sha as _card_sha,
    load_triage as _load_triage,
    triage_path as _triage_path,
)
from tools.sidecar.handlers.evidence_reconcile import (  # noqa: E402
    _reconcile_bigrams,
    _reconcile_material_documents,
    _reconcile_pool_status,
    _reconcile_source_text,
    _reconcile_verbatim_candidates,
    handle_evidence_reconcile,
    handle_evidence_triage_set,
)
from tools.sidecar.handlers.evidence_inference import (  # noqa: E402
    _inference_llm_call,
    _inference_target_cards,
    handle_evidence_confirm_inference,
    handle_evidence_infer_fields,
)
