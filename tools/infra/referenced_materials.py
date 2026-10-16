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
