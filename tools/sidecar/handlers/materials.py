from __future__ import annotations

import base64
import binascii
import json
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
        "source_mode": values.get("source_mode", ""),
        "source_root": values.get("source_root", ""),
        "source_relpath": values.get("source_relpath", ""),
        "manifest_sha256": values.get("manifest_sha256", ""),
        "file_count": values.get("file_count", ""),
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
    from tools.infra.career_profile import load_career_profile
    if not load_career_profile(_PROFILE_PATH)["career_status"]["reviewed"]:
        missing_items.append("missing_career_profile")
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


# ---- 引用式材料（外部来源引用，非复制快照）----
# 契约见 AIEF/docs/plans/2026-10-17-referenced-materials.md：
# 清单冻结（逐文件 sha256）；内容变更/删除 → material_source_changed 阻断；新增文件需刷新纳入。


def _referenced_dir() -> Path:
    return _MATERIALS_DIR / ".referenced"


def _allowed_roots() -> list[dict[str, Any]]:
    from tools.policy.exclusions import load_material_source_roots
    return load_material_source_roots()


def _resolve_reference_target(root_id: str, relpath: str) -> tuple[Path, dict[str, Any]]:
    from tools.infra import referenced_materials as rm
    roots = _allowed_roots()
    root = next((item for item in roots if str(item.get("id")) == root_id), None)
    if root is None:
        raise ValueError("material_source_root_required")
    target = (Path(str(root["path"])) / str(relpath or "")).resolve()
    return rm.resolve_under_roots(target, roots), root


def _material_item_by_id(material_id: str) -> dict[str, Any]:
    for item in list_material_source_items():
        if item.get("material_id") == material_id:
            return item
    raise KeyError(f"NOT_FOUND: material {material_id}")


def _load_reference_manifest(material_id: str) -> dict[str, Any]:
    path = _referenced_dir() / f"{material_id}.manifest.json"
    if not path.is_file():
        raise ValueError("material_source_changed")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("material_source_changed") from None


def _normalize_reference_target(root_path: str, relpath: str) -> Path:
    return (Path(str(root_path)) / str(relpath or "")).resolve()


def _reference_items() -> list[dict[str, Any]]:
    return [item for item in list_material_source_items() if item.get("source_mode") == "referenced"]


def _reference_target_from_item(item: dict[str, Any]) -> Path:
    from tools.infra import referenced_materials as rm
    target = Path(str(item.get("source_root") or "")) / str(item.get("source_relpath") or "")
    try:
        return rm.resolve_under_roots(target, _allowed_roots())
    except ValueError as exc:
        raise ValueError("material_source_changed") from exc


def _write_reference_manifest(material_id: str, root: dict[str, Any], relpath: str, manifest: dict[str, Any]) -> None:
    payload = {"root_id": str(root.get("id")), "source_root": str(root.get("path")), "source_relpath": relpath,
               "files": manifest["files"], "skipped": manifest["skipped"],
               "manifest_sha256": manifest["manifest_sha256"], "built_at": manifest.get("built_at", "")}
    directory = _referenced_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{material_id}.manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def ensure_referenced_text(item: dict[str, Any]) -> Path:
    """引用材料读取前校验（meta/清单一致 + 源文件哈希）；不符 → material_source_changed。"""
    from tools.infra import referenced_materials as rm
    manifest = _load_reference_manifest(str(item.get("material_id")))
    if str(item.get("manifest_sha256") or "") != str(manifest.get("manifest_sha256") or ""):
        raise ValueError("material_source_changed")
    target = _reference_target_from_item(item)
    try:
        status = rm.verify_manifest(target, manifest)
    except (OSError, ValueError):
        raise ValueError("material_source_changed") from None
    if status.get("status") != "ok":
        raise ValueError("material_source_changed")
    cache = _MATERIALS_DIR / str(item.get("filename") or "")
    if not cache.is_file():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(rm.merge_text(target, manifest["files"]), encoding="utf-8")
    return cache


def handle_material_reference_scan(params: dict[str, Any]) -> dict[str, Any]:
    from tools.infra import referenced_materials as rm
    correlation_id = params["meta"]["correlation_id"]
    relpath = str(params.get("relpath") or "")
    target, root = _resolve_reference_target(str(params.get("root_id") or ""), relpath)
    scanned = rm.scan_files(target)
    if not scanned["files"]:
        raise ValueError("material_source_empty")
    existing = [item["material_id"] for item in _reference_items()
                if _normalize_reference_target(item.get("source_root", ""), item.get("source_relpath", "")) == target]
    return {"meta": {"correlation_id": correlation_id}, "root_id": root["id"], "relpath": relpath,
            "file_count": len(scanned["files"]), "total_bytes": scanned["total_bytes"],
            "sample_files": [f["relpath"] for f in scanned["files"][:20]],
            "skipped": scanned["skipped"][:50], "skipped_count": len(scanned["skipped"]),
            "existing_materials": existing}


def handle_material_reference_create(params: dict[str, Any]) -> dict[str, Any]:
    from tools.infra import referenced_materials as rm
    correlation_id = params["meta"]["correlation_id"]
    label = str(params.get("label") or "").strip()
    if not label:
        raise ValueError("label is required")
    if len(label) > 100:
        raise ValueError("label must not exceed 100 characters")
    relpath = str(params.get("relpath") or "")
    target, root = _resolve_reference_target(str(params.get("root_id") or ""), relpath)
    duplicates = [item["material_id"] for item in _reference_items()
                  if _normalize_reference_target(item.get("source_root", ""), item.get("source_relpath", "")) == target]
    if duplicates:
        raise ValueError(f"material_reference_duplicate:{duplicates[0]}")
    manifest = rm.build_manifest(target)
    if not manifest["files"]:
        raise ValueError("material_source_empty")
    material_id = f"mat_{uuid4().hex[:8]}"
    resource_id = f"res_{uuid4().hex[:8]}"
    _write_reference_manifest(material_id, root, relpath, manifest)
    text = rm.merge_text(target, manifest["files"])
    cache_name = f"{material_id}-{manifest['manifest_sha256'][:12]}.txt"
    (_referenced_dir() / cache_name).write_text(text, encoding="utf-8")
    uploaded_at = _utcnow_iso()
    preview = _normalize_preview(text)
    filename = f".referenced/{cache_name}"
    _write_material_meta(_MATERIALS_DIR / f"{material_id}.meta.yaml", {
        "material_id": material_id, "resource_id": resource_id, "label": label,
        "kind": "raw_work_material_directory" if target.is_dir() else "raw_work_material",
        "filename": filename, "extension": ".txt", "uploaded_at": uploaded_at, "preview": preview,
        "source_mode": "referenced", "source_root": str(root["path"]), "source_relpath": relpath,
        "manifest_sha256": manifest["manifest_sha256"], "file_count": str(len(manifest["files"])),
    })
    return {"meta": {"correlation_id": correlation_id}, "material_id": material_id, "resource_id": resource_id,
            "label": label, "filename": filename, "extension": ".txt", "uploaded_at": uploaded_at,
            "preview": preview, "source_mode": "referenced", "manifest_sha256": manifest["manifest_sha256"],
            "file_count": len(manifest["files"])}


def handle_material_reference_status(params: dict[str, Any]) -> dict[str, Any]:
    from tools.infra import referenced_materials as rm
    correlation_id = params["meta"]["correlation_id"]
    item = _material_item_by_id(str(params.get("material_id") or ""))
    if item.get("source_mode") != "referenced":
        raise ValueError("material_not_referenced")
    checked_at = _utcnow_iso()
    try:
        manifest = _load_reference_manifest(item["material_id"])
    except ValueError:
        return {"meta": {"correlation_id": correlation_id}, "material_id": item["material_id"],
                "status": "changed", "changed": [], "missing": [], "added": [],
                "manifest_sha256": str(item.get("manifest_sha256") or ""), "checked_at": checked_at}
    target = Path(str(item.get("source_root") or "")) / str(item.get("source_relpath") or "")
    blocked = {"status": "changed", "changed": [], "added": [],
               "missing": sorted(f["relpath"] for f in manifest.get("files", []))}
    if not target.exists():
        status = blocked
    else:
        try:
            rm.resolve_under_roots(target, _allowed_roots())
            status = rm.verify_manifest(target, manifest)
        except (OSError, ValueError):
            status = blocked
    return {"meta": {"correlation_id": correlation_id}, "material_id": item["material_id"],
            "status": status["status"], "changed": status["changed"], "missing": status["missing"],
            "added": status["added"], "manifest_sha256": manifest.get("manifest_sha256", ""),
            "checked_at": checked_at}


def handle_material_reference_refresh(params: dict[str, Any]) -> dict[str, Any]:
    from tools.infra import referenced_materials as rm
    correlation_id = params["meta"]["correlation_id"]
    if params.get("confirmed") is not True:
        raise ValueError("material_reference_confirmation_required")
    item = _material_item_by_id(str(params.get("material_id") or ""))
    if item.get("source_mode") != "referenced":
        raise ValueError("material_not_referenced")
    material_id = item["material_id"]
    manifest = _load_reference_manifest(material_id)
    target = _reference_target_from_item(item)
    try:
        diff = rm.verify_manifest(target, manifest)
    except (OSError, ValueError):
        diff = {"status": "changed", "changed": [], "missing": [], "added": []}
    try:
        new_manifest = rm.build_manifest(target)
    except (OSError, ValueError):
        raise ValueError("material_source_changed") from None
    if not new_manifest["files"]:
        raise ValueError("material_source_empty")
    root = {"id": manifest.get("root_id", ""), "path": str(item.get("source_root") or "")}
    relpath = str(item.get("source_relpath") or "")
    _write_reference_manifest(material_id, root, relpath, new_manifest)
    text = rm.merge_text(target, new_manifest["files"])
    cache_name = f"{material_id}-{new_manifest['manifest_sha256'][:12]}.txt"
    (_referenced_dir() / cache_name).write_text(text, encoding="utf-8")
    for stale in _referenced_dir().glob(f"{material_id}-*.txt"):
        if stale.name != cache_name:
            stale.unlink()
    meta_path = _MATERIALS_DIR / f"{material_id}.meta.yaml"
    _write_material_meta(meta_path, {
        **_load_meta(meta_path),
        "filename": f".referenced/{cache_name}",
        "manifest_sha256": new_manifest["manifest_sha256"],
        "file_count": str(len(new_manifest["files"])),
        "preview": _normalize_preview(text),
    })
    return {"meta": {"correlation_id": correlation_id}, "material_id": material_id,
            "manifest_sha256": new_manifest["manifest_sha256"],
            "previous_manifest_sha256": manifest.get("manifest_sha256", ""),
            "file_count": len(new_manifest["files"]), "diff": diff}


def handle_material_reference_remove(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    if params.get("confirmed") is not True:
        raise ValueError("material_reference_confirmation_required")
    item = _material_item_by_id(str(params.get("material_id") or ""))
    if item.get("source_mode") != "referenced":
        raise ValueError("material_not_referenced")
    material_id = item["material_id"]
    (_MATERIALS_DIR / f"{material_id}.meta.yaml").unlink(missing_ok=True)
    (_referenced_dir() / f"{material_id}.manifest.json").unlink(missing_ok=True)
    for cache in _referenced_dir().glob(f"{material_id}-*.txt"):
        cache.unlink()
    return {"meta": {"correlation_id": correlation_id}, "material_id": material_id, "removed": True}
