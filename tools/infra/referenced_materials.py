"""引用式材料：允许根内的文件清单冻结、逐文件哈希校验与合并文本（非复制快照）。

契约：清单在创建时冻结（逐文件 sha256）；内容变更/文件删除 → 校验 status=changed
（调用方必须阻断而不是静默使用）；新增文件不自动进入清单（仅在 verify 的 added 中
报告）。合并文本与材料导入器的 `# Source:` 格式一致。
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SENSITIVE_RE = re.compile(r"(secret|token|password|passwd|密码|密钥|凭证|credential|private[_-]?key)", re.I)
ALLOWED_SUFFIXES = {".md", ".txt"}


def is_sensitive_name(name: str) -> bool:
    normalized = unicodedata.normalize("NFKC", str(name))
    return bool(SENSITIVE_RE.search(normalized))


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skip_reason(path: Path, base: Path) -> str | None:
    parts = path.relative_to(base).parts
    if any(part.startswith(".") for part in parts):
        return "hidden_path"
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return "unsupported_suffix"
    if is_sensitive_name(path.name):
        return "sensitive_name"
    if path.stat().st_size == 0:
        return "empty"
    return None


def scan_files(target: Path) -> dict[str, Any]:
    """扫描目标文件/目录；确定性排序；返回 {files, skipped, total_bytes}。"""
    target = Path(target)
    if not target.exists():
        raise ValueError("material_source_missing")
    if target.is_symlink():
        raise ValueError("material_source_symlink_rejected")
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if target.is_file():
        reason = _skip_reason(target, target.parent)
        if reason:
            raise ValueError(f"material_source_{reason}")
        files.append({"relpath": target.name, "sha256": _file_sha(target), "bytes": target.stat().st_size})
    else:
        for path in sorted(target.rglob("*")):
            relpath = path.relative_to(target).as_posix()
            if path.is_symlink():
                skipped.append({"relpath": relpath, "reason": "symlink"})
                continue
            if path.is_dir():
                continue
            reason = _skip_reason(path, target)
            if reason:
                skipped.append({"relpath": relpath, "reason": reason})
                continue
            files.append({"relpath": relpath, "sha256": _file_sha(path), "bytes": path.stat().st_size})
    return {"files": files, "skipped": skipped, "total_bytes": sum(f["bytes"] for f in files)}


def manifest_digest(files: list[dict[str, Any]]) -> str:
    body = json.dumps(
        [{"relpath": f["relpath"], "sha256": f["sha256"], "bytes": f["bytes"]} for f in files],
        ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def build_manifest(target: Path) -> dict[str, Any]:
    scanned = scan_files(target)
    return {
        "files": scanned["files"],
        "skipped": scanned["skipped"],
        "total_bytes": scanned["total_bytes"],
        "manifest_sha256": manifest_digest(scanned["files"]),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def verify_manifest(target: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """重扫源并比对冻结清单；status=ok 表示内容未变（added 仅提示，不算变更）。"""
    current = scan_files(target)
    recorded = {f["relpath"]: f for f in manifest.get("files", [])}
    present = {f["relpath"]: f for f in current["files"]}
    changed = sorted(rel for rel, item in recorded.items()
                     if rel in present and present[rel]["sha256"] != item["sha256"])
    missing = sorted(rel for rel in recorded if rel not in present)
    added = sorted(rel for rel in present if rel not in recorded)
    return {"status": "ok" if not (changed or missing) else "changed",
            "changed": changed, "missing": missing, "added": added}


def resolve_under_roots(path: Path, allowed_roots: list[dict[str, Any]]) -> Path:
    resolved = Path(path).resolve()
    for item in allowed_roots or []:
        root = Path(str(item.get("path") or "")).resolve()
        if resolved == root or resolved.is_relative_to(root):
            return resolved
    raise ValueError("material_source_outside_allowed_roots")


def merge_text(target: Path, files: list[dict[str, Any]]) -> str:
    target = Path(target)
    if target.is_file():
        return target.read_text(encoding="utf-8", errors="replace").strip() + "\n"
    sections: list[str] = []
    for item in files:
        text = (target / item["relpath"]).read_text(encoding="utf-8", errors="replace").strip()
        if text:
            sections.append(f"# Source: {item['relpath']}\n\n{text}")
    return ("\n\n".join(sections).strip() + "\n") if sections else ""


def _relative_parts(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("material_source_changed")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("material_source_changed")
    return parts


def _beneath(root, parts):
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("material_source_changed")
    return current


def verify_bound_documents(material_dir, item, refs, roots, *, fingerprint=None):
    """Reverify only existing document bindings. A cache hit determines a path, never text authority."""
    from collections import Counter
    from tools.infra.material_documents import split_material_documents

    error = "material_source_changed"
    mid = item.get("material_id", "")
    if not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", mid):
        raise ValueError(error)
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    library = Path(material_dir).resolve()
    meta_path = _beneath(library, [f"{mid}.meta.yaml"])
    if not meta_path.is_file():
        raise ValueError(error)
    meta_bytes = meta_path.read_bytes()
    meta = parse_simple_yaml(meta_bytes.decode("utf-8"))["scalars"]
    if any(meta.get(key) != item.get(key) for key in (
            "material_id","source_mode","filename","source_root","source_relpath","manifest_sha256")):
        raise ValueError(error)
    manifest_path = _beneath(library, [".referenced", f"{mid}.manifest.json"])
    if not manifest_path.is_file():
        raise ValueError(error)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    files = manifest["files"]
    digest = manifest_digest(files)
    if (digest != manifest.get("manifest_sha256") or digest != item.get("manifest_sha256")
            or manifest.get("source_root") != item.get("source_root")
            or manifest.get("source_relpath") != item.get("source_relpath")):
        raise ValueError(error)
    root = [root for root in roots
            if root.get("id") == manifest.get("root_id") and root.get("path") == item.get("source_root")]
    if len(root) != 1:
        raise ValueError(error)
    root_path = Path(root[0]["path"]).resolve()
    relative = manifest["source_relpath"]
    target = root_path if relative in ("", ".") else _beneath(root_path, _relative_parts(relative))
    by_path = {}
    for row in files:
        rel = row["relpath"]
        _relative_parts(rel)
        if rel in by_path:
            raise ValueError(error)
        by_path[rel] = row
    filename = f".referenced/{mid}-{digest[:12]}.txt"
    if item.get("filename") != filename:
        raise ValueError(error)
    cache = _beneath(library, _relative_parts(filename))
    if not cache.is_file():
        raise ValueError(error)
    cache_bytes = cache.read_bytes()
    cache_sha = hashlib.sha256(cache_bytes).hexdigest()
    if fingerprint is not None and fingerprint != {
        "filename":filename, "sha256":cache_sha, "mode":"referenced", "manifest_sha256":digest,
        "source_root":item["source_root"], "source_relpath":relative,
    }:
        raise ValueError(error)
    cache_text = cache_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    headers = Counter(match.strip() for match in re.findall(r"^# Source: ([^\n]+)$", cache_text, re.M))
    indexed = {doc["document_id"]:doc for doc in split_material_documents(cache_text, cache.name)}
    verified, originals, snapshots = {}, {}, {}
    is_file = target.is_file()
    for ref in refs:
        cached_doc = indexed.get(ref["document_id"])
        if not cached_doc or cached_doc["sha256"] != ref["sha256"]:
            raise ValueError(error)
        if is_file:
            rel, display = target.name, cache.name
            if headers or cached_doc["source_name"] != display:
                raise ValueError(error)
        else:
            rel = display = cached_doc["source_name"]
            if not target.is_dir() or headers[display] != 1:
                raise ValueError(error)
        if rel not in by_path:
            raise ValueError(error)
        if rel not in originals:
            path = target if is_file else _beneath(target, _relative_parts(rel))
            if not path.is_file():
                raise ValueError(error)
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if sha != by_path[rel]["sha256"] or len(raw) != by_path[rel]["bytes"]:
                raise ValueError(error)
            text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").strip()
            if re.search(r"^# Source: [^\n]+$", text, re.M):
                raise ValueError(error)
            canonical = text if is_file else f"# Source: {display}\n\n{text}\n"
            originals[rel] = (path, sha, {doc["document_id"]:doc for doc in split_material_documents(canonical, cache.name)})
        path, sha, documents = originals[rel]
        fresh = documents.get(ref["document_id"])
        if fresh != cached_doc or ("label" in ref and ref["label"] != fresh["label"]):
            raise ValueError(error)
        verified[ref["document_id"]] = fresh["text"]
        snapshots[f"evidence_document:{mid}:{ref['document_id']}"] = (path,sha)
    snapshots[f"evidence_meta:{mid}"] = (meta_path,hashlib.sha256(meta_bytes).hexdigest())
    snapshots[f"evidence_material:{mid}"] = (cache,cache_sha)
    snapshots[f"evidence_manifest:{mid}"] = (manifest_path,hashlib.sha256(manifest_bytes).hexdigest())
    return cache, verified, snapshots
