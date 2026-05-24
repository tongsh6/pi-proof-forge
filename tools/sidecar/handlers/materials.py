from __future__ import annotations

import base64
import binascii
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


def _decode_uploaded_file(params: dict[str, Any]) -> tuple[str, bytes] | None:
    payload = params.get("file")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("file must be an object")
    filename = Path(str(payload.get("filename", ""))).name.strip()
    content_base64 = str(payload.get("content_base64", "")).strip()
    if not filename:
        raise ValueError("file.filename is required")
    if not content_base64:
        raise ValueError("file.content_base64 is required")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("file.content_base64 must be valid base64") from exc
    return filename, content


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


def _material_files_from_source(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if not source.is_dir():
        return []
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and path.suffix.lower() in _ALLOWED_MATERIAL_SUFFIXES
        and not any(part.startswith(".") for part in path.relative_to(source).parts)
    )


def _read_material_source(source: Path, files: list[Path]) -> str:
    if len(files) == 1 and files[0] == source:
        return source.read_text(encoding="utf-8", errors="replace")

    sections: list[str] = []
    for file_path in files:
        relative = file_path.relative_to(source)
        text = file_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        sections.append(f"# Source: {relative}\n\n{text}")
    return "\n\n".join(sections).strip() + "\n"


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
    uploaded_file = _decode_uploaded_file(params)
    source_paths = params.get("source_paths", [])
    if uploaded_file is None and (
        not isinstance(source_paths, list) or len(source_paths) != 1
    ):
        raise ValueError("source_paths must contain exactly one file")

    if uploaded_file is not None:
        source_name, source_content = uploaded_file
        source_stem = Path(source_name).stem
        suffix = Path(source_name).suffix.lower()
        if suffix not in _ALLOWED_MATERIAL_SUFFIXES:
            raise ValueError("unsupported material file type; expected .md or .txt")
        is_directory = False
        file_count = 1
        raw_text = source_content.decode("utf-8", errors="replace")
        source_path_for_meta = f"uploaded_file:{source_name}"
    else:
        source = Path(str(source_paths[0]))
        if not source.exists():
            raise FileNotFoundError(f"material source not found: {source}")
        if not source.is_file() and not source.is_dir():
            raise ValueError(f"material source must be a file or directory: {source}")
        files = _material_files_from_source(source)
        if not files:
            raise ValueError("unsupported material file type; expected .md or .txt")
        if source.is_file() and source.suffix.lower() not in _ALLOWED_MATERIAL_SUFFIXES:
            raise ValueError("unsupported material file type; expected .md or .txt")

        is_directory = source.is_dir()
        suffix = ".txt" if is_directory else source.suffix.lower()
        raw_text = _read_material_source(source, files)
        source_stem = source.stem
        source_path_for_meta = str(source)
        file_count = len(files)

    label = str(params.get("label", source_stem) or source_stem).strip()
    if len(label) > 100:
        raise ValueError("label must not exceed 100 characters")

    material_id = f"mat_{uuid4().hex[:8]}"
    resource_id = f"res_{uuid4().hex[:8]}"
    uploaded_at = _utcnow_iso()
    preview = _normalize_preview(raw_text)

    _MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _MATERIALS_DIR / f"{material_id}{suffix}"
    if is_directory or uploaded_file is not None:
        destination.write_text(raw_text, encoding="utf-8")
    else:
        shutil.copy2(source, destination)
    _write_material_meta(
        _MATERIALS_DIR / f"{material_id}.meta.yaml",
        {
            "material_id": material_id,
            "resource_id": resource_id,
            "label": label,
            "kind": "raw_work_material_directory" if is_directory else "raw_work_material",
            "filename": destination.name,
            "extension": suffix,
            "uploaded_at": uploaded_at,
            "preview": preview,
            "source_path": source_path_for_meta,
            "source_file_count": str(file_count),
        },
    )
    return {
        "meta": {"correlation_id": correlation_id},
        "material_id": material_id,
        "resource_id": resource_id,
        "label": label,
        "kind": "raw_work_material_directory" if is_directory else "raw_work_material",
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
