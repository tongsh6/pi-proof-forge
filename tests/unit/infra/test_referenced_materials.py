"""引用式材料 resolver：外部来源清单冻结、逐文件哈希校验与合并文本（App 一级能力）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.infra import referenced_materials as rm


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "proj" / "sub").mkdir(parents=True)
    (tmp_path / "proj" / "a.md").write_text("# 甲文档\n\n内容甲。\n", encoding="utf-8")
    (tmp_path / "proj" / "sub" / "b.txt").write_text("内容乙。\n", encoding="utf-8")
    (tmp_path / "proj" / ".hidden").mkdir()
    (tmp_path / "proj" / ".hidden" / "c.md").write_text("隐藏", encoding="utf-8")
    (tmp_path / "proj" / "secret-token.md").write_text("不该收", encoding="utf-8")
    (tmp_path / "proj" / "empty.md").write_text("", encoding="utf-8")
    (tmp_path / "proj" / "link.md").symlink_to(tmp_path / "proj" / "a.md")
    (tmp_path / "outside.md").write_text("根外", encoding="utf-8")
    (tmp_path / "single.md").write_text("# 单文件\n\n正文。\n", encoding="utf-8")
    return tmp_path


def test_scan_files_filters_and_determinism(root: Path):
    result = rm.scan_files(root / "proj")
    assert [f["relpath"] for f in result["files"]] == ["a.md", "sub/b.txt"]
    assert result["files"][0]["sha256"] == rm._file_sha(root / "proj" / "a.md")
    assert result["total_bytes"] == sum(f["bytes"] for f in result["files"])
    skipped = {item["relpath"]: item["reason"] for item in result["skipped"]}
    assert skipped["secret-token.md"] == "sensitive_name"
    assert skipped["empty.md"] == "empty"
    assert skipped[".hidden/c.md"] == "hidden_path"
    assert skipped["link.md"] == "symlink"
    again = rm.scan_files(root / "proj")
    assert result == again


def test_scan_single_file(root: Path):
    result = rm.scan_files(root / "single.md")
    assert [f["relpath"] for f in result["files"]] == ["single.md"]
    with pytest.raises(ValueError):
        rm.scan_files(root / "secret-token.md")


def test_manifest_digest_tracks_content(root: Path):
    manifest = rm.build_manifest(root / "proj")
    assert manifest["manifest_sha256"] == rm.manifest_digest(manifest["files"])
    (root / "proj" / "a.md").write_text("# 甲文档\n\n内容甲改了。\n", encoding="utf-8")
    changed = rm.build_manifest(root / "proj")
    assert changed["manifest_sha256"] != manifest["manifest_sha256"]


def test_verify_manifest_detects_change_missing_added(root: Path):
    manifest = rm.build_manifest(root / "proj")
    assert rm.verify_manifest(root / "proj", manifest) == {
        "status": "ok", "changed": [], "missing": [], "added": []}
    (root / "proj" / "sub" / "b.txt").write_text("内容乙改了。\n", encoding="utf-8")
    (root / "proj" / "new.md").write_text("新增", encoding="utf-8")
    status = rm.verify_manifest(root / "proj", manifest)
    assert status["status"] == "changed"
    assert status["changed"] == ["sub/b.txt"]
    assert status["added"] == ["new.md"]
    (root / "proj" / "a.md").unlink()
    status = rm.verify_manifest(root / "proj", manifest)
    assert status["missing"] == ["a.md"]
    assert status["status"] == "changed"


def test_resolve_under_roots(root: Path):
    roots = [{"id": "msr_1", "label": "仓", "path": str(root)}]
    assert rm.resolve_under_roots(root / "proj", roots) == (root / "proj").resolve()
    others = [{"id": "msr_2", "label": "别处", "path": str(root / "proj")}]
    with pytest.raises(ValueError):
        rm.resolve_under_roots(root / "outside.md", others)
    with pytest.raises(ValueError):
        rm.resolve_under_roots(root / "proj" / "a.md", [])


def test_merge_text_markers_and_single_file(root: Path):
    manifest = rm.build_manifest(root / "proj")
    text = rm.merge_text(root / "proj", manifest["files"])
    assert "# Source: a.md" in text
    assert "# Source: sub/b.txt" in text
    assert text.index("内容甲") < text.index("内容乙")
    single = rm.merge_text(root / "single.md", rm.build_manifest(root / "single.md")["files"])
    assert single == "# 单文件\n\n正文。\n"
    assert "# Source:" not in single
