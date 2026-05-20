from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from tools.infra.persistence.yaml_io import parse_simple_yaml

_MATERIALS_DIR = Path("materials")
_UPLOADED_RESUMES_DIR = Path("uploaded_resumes")
_PROFILE_PATH = Path("personal_profile.yaml")
_ALLOWED_MATERIAL_SUFFIXES = {".md", ".txt"}
_PROFILE_REQUIRED_FIELDS = ("name", "phone", "email", "city", "current_position")


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _normalize_preview(text: str, limit: int = 600) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    preview = " ".join(lines)
    if len(preview) <= limit:
        return preview
    return preview[: limit - 1].rstrip() + "..."


def _load_meta(path: Path) -> dict[str, str]:
    doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
    return dict(doc["scalars"])


def _write_material_meta(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "\n".join(f"{key}: {_quote(value)}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )


def _material_item_from_meta(meta_path: Path) -> dict[str, Any]:
    values = _load_meta(meta_path)
    filename = values.get("filename", "")
    file_path = meta_path.parent / filename if filename else Path("")
    size_bytes = file_path.stat().st_size if file_path.exists() else 0
    return {
        "material_id": values.get("material_id", meta_path.stem.removesuffix(".meta")),
        "resource_id": values.get("resource_id", ""),
        "label": values.get("label", ""),
        "kind": values.get("kind", "raw_work_material"),
        "filename": filename,
        "extension": values.get("extension", Path(filename).suffix.lower()),
        "uploaded_at": values.get("uploaded_at", ""),
        "preview": values.get("preview", ""),
        "size_bytes": size_bytes,
    }


def list_material_source_items() -> list[dict[str, Any]]:
    items = []
    if _MATERIALS_DIR.exists():
        items.extend(
            _material_item_from_meta(path)
            for path in sorted(_MATERIALS_DIR.glob("*.meta.yaml"))
        )
    return sorted(items, key=lambda item: str(item.get("uploaded_at", "")), reverse=True)


def handle_material_upload(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    source_paths = params.get("source_paths", [])
    if not isinstance(source_paths, list) or len(source_paths) != 1:
        raise ValueError("source_paths must contain exactly one file")

    source = Path(str(source_paths[0]))
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"material source not found: {source}")
    suffix = source.suffix.lower()
    if suffix not in _ALLOWED_MATERIAL_SUFFIXES:
        raise ValueError("unsupported material file type")

    label = str(params.get("label", source.stem) or source.stem).strip()
    if len(label) > 100:
        raise ValueError("label must not exceed 100 characters")

    material_id = f"mat_{uuid4().hex[:8]}"
    resource_id = f"res_{uuid4().hex[:8]}"
    uploaded_at = _utcnow_iso()
    preview = _normalize_preview(source.read_text(encoding="utf-8", errors="replace"))

    _MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _MATERIALS_DIR / f"{material_id}{suffix}"
    shutil.copy2(source, destination)
    _write_material_meta(
        _MATERIALS_DIR / f"{material_id}.meta.yaml",
        {
            "material_id": material_id,
            "resource_id": resource_id,
            "label": label,
            "kind": "raw_work_material",
            "filename": destination.name,
            "extension": suffix,
            "uploaded_at": uploaded_at,
            "preview": preview,
        },
    )
    return {
        "meta": {"correlation_id": correlation_id},
        "material_id": material_id,
        "resource_id": resource_id,
        "label": label,
        "kind": "raw_work_material",
        "filename": destination.name,
        "extension": suffix,
        "uploaded_at": uploaded_at,
        "preview": preview,
    }


def handle_material_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "items": list_material_source_items(),
    }


def handle_material_readiness(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    missing_items = []
    if not _profile_is_complete():
        missing_items.append("missing_personal_profile")
    if not _has_uploaded_resume():
        missing_items.append("missing_uploaded_resume")
    if not list_material_source_items():
        missing_items.append("missing_raw_work_material")

    return {
        "meta": {"correlation_id": correlation_id},
        "status": "ready" if not missing_items else "incomplete",
        "missing_items": missing_items,
    }


def handle_evidence_list_material_sources(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "items": list_material_source_items(),
    }


def _profile_is_complete() -> bool:
    if not _PROFILE_PATH.exists():
        return False
    values = _load_meta(_PROFILE_PATH)
    return all(values.get(field, "").strip() for field in _PROFILE_REQUIRED_FIELDS)


def _has_uploaded_resume() -> bool:
    if not _UPLOADED_RESUMES_DIR.exists():
        return False
    return any(_UPLOADED_RESUMES_DIR.glob("*.meta.yaml"))
