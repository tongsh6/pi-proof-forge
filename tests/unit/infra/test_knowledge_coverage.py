"""来源目录导航与正文索引覆盖：附件不成为事实，漏项可查询。"""
import json
from pathlib import Path

import pytest

from tools.infra import knowledge_index as ki
from tools import kb


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    monkeypatch.delenv("PPF_POLICY_PATH", raising=False)
    root = tmp_path / "project"
    materials = root / "materials"
    materials.mkdir(parents=True)
    vault = tmp_path / "vault"
    (vault / "work").mkdir(parents=True)
    (vault / "work/known.md").write_text("# 已收录\n\n工作记录。\n")
    (vault / "work/missing.md").write_text("# 工作流设计\n\n规划 DAG。\n")
    (vault / "work/INDEX.md").write_text("# 项目导航\n")
    (vault / "work/architecture.pdf").write_bytes(b"%PDF-1.7 local fixture")
    (vault / "work/requirements.docx").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        + "oid sha256:" + "a" * 64 + "\nsize 12345\n")
    roots = [{"id": "msr_test", "label": "工作资料", "path": str(vault)}]
    (root / "policy.local.yaml").write_text(
        "material_source_roots_json: " + json.dumps(json.dumps(roots, ensure_ascii=False)) + "\n")
    (materials / "mat_known.txt").write_text(
        "# Source: work/known.md\n\n# 已收录\n\n工作记录。\n"
        "# Source: work/INDEX.md\n\n# 项目导航\n")
    (materials / "mat_known.meta.yaml").write_text(
        'material_id: "mat_known"\nfilename: "mat_known.txt"\n'
        'kind: "raw_work_material_directory"\n'
        f'source_path: "{tmp_path / "staged"}"\n')
    return root, vault


def test_source_inventory_distinguishes_text_filters_and_attachments(inventory):
    root, _ = inventory
    index = ki.build_index(root)
    assert "source_coverage" in index
    coverage = index["source_coverage"]
    rows = {r["path"]: r for r in coverage["items"]}
    assert rows["work/known.md"]["status"] == "indexed"
    assert rows["work/known.md"]["references"][0]["material_id"] == "mat_known"
    assert rows["work/missing.md"]["status"] == "unindexed"
    assert rows["work/INDEX.md"]["status"] == "filtered"
    assert rows["work/architecture.pdf"]["status"] == "metadata_only"
    assert rows["work/architecture.pdf"]["availability"] == "local"
    assert rows["work/requirements.docx"]["availability"] == "lfs_pointer"
    assert rows["work/requirements.docx"]["references"] == []
    assert coverage["counts"] == {"indexed": 1, "unindexed": 1, "filtered": 1, "metadata_only": 2}
    assert index["assets"]["documents"] == 1
    md = ki.render_index_md(index)
    assert "来源覆盖" in md and "metadata_only" in md
    assert "全量资产已纳入" not in md


def test_source_inventory_matches_snapshot_content_and_detects_changes(inventory):
    root, vault = inventory
    index = ki.build_index(root)
    assert "source_coverage" in index
    assert ki.verify_index(root, index) == []
    (vault / "work/known.md").write_text("# 已收录\n\n内容已变更。\n")
    updated = ki.build_index(root)
    row = next(r for r in updated["source_coverage"]["items"] if r["path"] == "work/known.md")
    assert row["status"] == "stale"
    assert any(s["kind"] == "source_coverage" for s in ki.verify_index(root, index))


def test_source_inventory_does_not_follow_symlinks_or_read_sensitive_files(inventory):
    root, vault = inventory
    (vault / ".hidden").mkdir()
    (vault / ".hidden/private.md").write_text("不纳入")
    (vault / "work/password.md").write_text("不读取")
    (vault / "work/shortcut.md").symlink_to(vault / "work/missing.md")
    (vault / "escape").symlink_to(root, target_is_directory=True)
    (vault / "work/empty.md").touch()
    index = ki.build_index(root)
    assert "source_coverage" in index
    coverage = index["source_coverage"]
    paths = {r["path"] for r in coverage["items"]}
    assert not paths & {".hidden/private.md", "work/password.md", "work/shortcut.md"}
    assert not any(p.startswith("escape/") for p in paths)
    assert coverage["excluded_counts"]["symlink"] == 2
    assert coverage["excluded_counts"]["sensitive_name"] == 1
    assert next(r for r in coverage["items"] if r["path"] == "work/empty.md")["status"] == "filtered"


def test_missing_source_root_is_reported_and_verify_not_clean(inventory):
    root, vault = inventory
    index = ki.build_index(root)
    vault.rename(vault.with_name("moved"))
    updated = ki.build_index(root)
    assert "source_coverage" in updated
    assert updated["source_coverage"]["errors"]
    assert any(s["kind"] == "source_coverage" for s in ki.verify_index(root, index))


def test_verify_detects_added_entity_and_added_source_file(inventory):
    root, vault = inventory
    index = ki.build_index(root)
    (root / "materials/mat_new.md").write_text("新材料")
    (root / "materials/mat_new.meta.yaml").write_text('material_id: "mat_new"\nfilename: "mat_new.md"\n')
    assert any(s["kind"] == "inventory" for s in ki.verify_index(root, index))
    (vault / "work/new.md").write_text("新来源")
    assert any(s["kind"] == "source_coverage" for s in ki.verify_index(root, index))


def test_coverage_cli_filters_and_limits_without_exposing_attachment_text(inventory, capsys):
    root, _ = inventory
    assert kb.main(["build", "--root", str(root)]) == 0
    capsys.readouterr()
    assert "source_coverage" in ki.load_index(root / "knowledge-index")
    assert kb.main(["coverage", "--root", str(root), "--status", "metadata_only",
                    "--path", "work/", "--root-id", "msr_test", "--limit", "1", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["matched"] == 2 and result["shown"] == 1
    assert result["items"][0]["path"] == "work/architecture.pdf"
    assert "text" not in result["items"][0]


def test_unconfigured_inventory_is_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("PPF_POLICY_PATH", raising=False)
    index = ki.build_index(tmp_path)
    assert "source_coverage" in index
    assert index["source_coverage"]["roots"] == []
    assert "未配置材料来源根" in ki.render_index_md(index)


def test_non_utf8_text_remains_metadata_only_without_fabricating_body(inventory):
    root, vault = inventory
    (vault / "work/legacy.txt").write_bytes("历史文本".encode('gb18030'))
    index = ki.build_index(root)
    row = next(r for r in index['source_coverage']['items'] if r['path'] == 'work/legacy.txt')
    assert row['status'] == 'metadata_only'
    assert row['reason'] == 'unsupported_text_encoding'
    assert row['references'] == []
    assert index['source_coverage']['errors'] == []
    assert ki.verify_index(root, index) == []


def test_crlf_source_matches_importer_normalized_snapshot(inventory):
    root, vault = inventory
    (vault / 'work/known.md').write_bytes('# 已收录\r\n\r\n工作记录。\r\n'.encode())
    index = ki.build_index(root)
    row = next(r for r in index['source_coverage']['items'] if r['path'] == 'work/known.md')
    assert row['status'] == 'indexed'


def test_reordered_chunks_do_not_count_as_same_document(inventory):
    root, vault = inventory
    first, second = '甲' * 23999, '乙' * 23999
    (root / 'materials/mat_known.txt').write_text('# Source: work/known.md\n' + first + '\n' + second)
    (vault / 'work/known.md').write_text(second + '\n' + first)
    index = ki.build_index(root)
    row = next(r for r in index['source_coverage']['items'] if r['path'] == 'work/known.md')
    assert row['status'] == 'stale'


def test_partial_snapshots_cannot_be_combined_into_full_coverage(inventory):
    root, vault = inventory
    first, second = '甲' * 23999, '乙' * 23999
    (root / 'materials/mat_known.txt').write_text('# Source: work/known.md\n' + first)
    (root / 'materials/mat_second.txt').write_text('# Source: work/known.md\n' + second)
    (root / 'materials/mat_second.meta.yaml').write_text(
        (root / 'materials/mat_known.meta.yaml').read_text().replace('mat_known', 'mat_second'))
    (vault / 'work/known.md').write_text(first + '\n' + second)
    index = ki.build_index(root)
    row = next(r for r in index['source_coverage']['items'] if r['path'] == 'work/known.md')
    assert row['status'] == 'stale'


def test_referenced_material_roundtrip_uses_selected_project_policy(inventory, monkeypatch):
    from tools.sidecar.handlers import materials
    root, vault = inventory
    monkeypatch.setattr(materials, '_MATERIALS_DIR', root / 'materials')
    monkeypatch.setenv('PPF_POLICY_PATH', str(root / 'policy.local.yaml'))
    created = materials.handle_material_reference_create({
        'meta': {'correlation_id': 'test'}, 'root_id': 'msr_test',
        'relpath': 'work/missing.md', 'label': '设计来源'})
    monkeypatch.delenv('PPF_POLICY_PATH')
    index = ki.build_index(root)
    assert index['materials'][created['material_id']]['reference_status'] == 'ok'
    row = next(r for r in index['source_coverage']['items'] if r['path'] == 'work/missing.md')
    assert row['status'] == 'indexed'
    assert row['references'][0]['material_id'] == created['material_id']
    assert ki.verify_index(root, index) == []


def test_verify_ignores_mtime_only_change(inventory):
    import os
    root, vault = inventory
    index = ki.build_index(root)
    path = vault / "work/known.md"
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
    assert ki.verify_index(root, index) == []
