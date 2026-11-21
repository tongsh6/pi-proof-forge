"""证据提炼使用的材料选择与文档切分（跨 handler 共享）。

从 ``evidence.py`` 抽出：``_selected_text_materials`` / ``_documents`` 等原被
``job_preferences`` 直接 import 的私有函数，统一收敛到本模块的公开名。
物料目录经 ``materials`` 模块属性读取，测试对 ``materials._MATERIALS_DIR``
的 patch 依然生效。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.sidecar.handlers import materials as materials_handler


def material_record_by_id(material_id: str) -> dict[str, Any]:
    for item in materials_handler.list_material_source_items():
        if item.get("material_id") == material_id:
            if item.get("source_mode") == "referenced":
                # 引用材料：读取前校验清单与源文件哈希；不符 → material_source_changed
                file_path = materials_handler.ensure_referenced_text(item)
            else:
                file_path = materials_handler._MATERIALS_DIR / str(item.get("filename", ""))
            record = dict(item)
            record["path"] = file_path
            return record
    raise KeyError(f"NOT_FOUND: material {material_id}")


def selected_text_materials(material_ids: object) -> list[dict[str, Any]]:
    if not isinstance(material_ids, list) or not material_ids:
        raise ValueError("material_ids must be a non-empty list")
    records = []
    for raw_id in material_ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValueError("material_ids must be a non-empty list of strings")
        record = material_record_by_id(raw_id.strip())
        if record.get("extension") not in {".md", ".txt"}:
            raise ValueError("unsupported material type; expected uploaded text material")
        path = record["path"]
        if not isinstance(path, Path) or not path.exists() or not path.is_file():
            raise ValueError(f"material source file not found: {raw_id}")
        if path.is_symlink() or not path.resolve().is_relative_to(materials_handler._MATERIALS_DIR.resolve()):
            raise ValueError('material source must remain in the material library')
        records.append(record)
    return records


def selected_markdown_materials(material_ids: object) -> list[dict[str, Any]]:
    records = selected_text_materials(material_ids)
    if any(record.get('extension') != '.md' for record in records):
        raise ValueError('unsupported material type; expected uploaded .md material')
    return records


def documents(record):
    from tools.infra.material_documents import split_material_documents
    return split_material_documents(record['path'].read_text(encoding='utf-8'),record['path'].name)


def document(record,document_id):
    matches=[d for d in documents(record) if d['document_id']==document_id]
    if len(matches)!=1:raise ValueError('material_document_changed_or_missing')
    return matches[0]


def materials_dir() -> Path:
    """物料库目录；运行时读取 materials 模块属性以兼容测试 patch。"""
    return materials_handler._MATERIALS_DIR


def list_material_source_items() -> list[dict[str, Any]]:
    return materials_handler.list_material_source_items()


def ensure_referenced_text(item: dict[str, Any]) -> Path:
    return materials_handler.ensure_referenced_text(item)


def evidence_bound_materials(material_ids, references, whole_material_ids, *, fingerprints=None):
    """Only already persisted refs may be passed here; new selection uses the standard reader."""
    from tools.infra.evidence_sources import exact_document_groups
    from tools.infra.referenced_materials import verify_bound_documents
    groups = exact_document_groups(material_ids, references, whole_material_ids)
    if not groups:
        return selected_text_materials(material_ids), {}
    items = {}
    for item in list_material_source_items():
        mid = item["material_id"]
        if mid in groups:
            if mid in items:
                raise ValueError("material_source_changed")
            items[mid] = item
    records, snapshots = [], {}
    for mid in material_ids:
        item = items.get(mid)
        if not item:
            raise ValueError("material_source_changed")
        if item.get("source_mode") != "referenced":
            records.extend(selected_text_materials([mid]))
            continue
        try:
            cache, docs, verified = verify_bound_documents(
                materials_dir(), item, groups[mid], materials_handler._allowed_roots(),
                fingerprint=fingerprints[mid] if fingerprints else None)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError("material_source_changed") from exc
        snapshots.update(verified)
        records.append({**item, "path":cache, "verified_documents":docs})
    return records, snapshots
