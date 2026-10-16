"""引用式材料：来源白名单、引用 RPC 与证据链校验。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.policy import exclusions
from tools.sidecar.handlers import materials


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    monkeypatch.setattr(materials, "_MATERIALS_DIR", materials_dir)
    monkeypatch.setenv("PPF_POLICY_PATH", str(tmp_path / "policy.local.yaml"))
    vault = tmp_path / "vault"
    (vault / "proj" / "sub").mkdir(parents=True)
    (vault / "proj" / "a.md").write_text("# 甲\n\n甲内容。\n", encoding="utf-8")
    (vault / "proj" / "sub" / "b.md").write_text("乙内容。\n", encoding="utf-8")
    (vault / "proj" / "secret-token.md").write_text("跳过我", encoding="utf-8")
    (vault / "empty").mkdir()
    exclusions.save_material_source_roots([{"id": "msr_test", "label": "仓", "path": str(vault)}])
    return tmp_path, vault, materials_dir


def _scan(**params):
    return materials.handle_material_reference_scan({"meta": {"correlation_id": "t"}, **params})


def _create(**params):
    return materials.handle_material_reference_create({"meta": {"correlation_id": "t"}, **params})


def test_scan_requires_known_root(env):
    _ = env
    with pytest.raises(ValueError):
        _scan(root_id="msr_missing", relpath="proj")
    with pytest.raises(ValueError):
        _scan(root_id="", relpath="proj")


def test_scan_previews_files_and_skips(env):
    _, vault, _ = env
    result = _scan(root_id="msr_test", relpath="proj")
    assert result["file_count"] == 2
    assert sorted(result["sample_files"]) == ["a.md", "sub/b.md"]
    assert result["skipped"] == [{"relpath": "secret-token.md", "reason": "sensitive_name"}]
    with pytest.raises(ValueError):
        _scan(root_id="msr_test", relpath="proj/../..")
    with pytest.raises(ValueError):
        _scan(root_id="msr_test", relpath="empty")


def test_create_writes_manifest_cache_and_meta(env):
    _, vault, materials_dir = env
    result = _create(root_id="msr_test", relpath="proj", label="引用·测试项目")
    material_id = result["material_id"]
    meta = materials._load_meta(materials_dir / f"{material_id}.meta.yaml")
    assert meta["source_mode"] == "referenced"
    assert meta["source_root"] == str(vault)
    assert meta["source_relpath"] == "proj"
    assert meta["file_count"] == "2"
    assert meta["filename"].startswith(".referenced/")
    cache = materials_dir / meta["filename"]
    assert cache.is_file()
    assert "# Source: a.md" in cache.read_text(encoding="utf-8")
    manifest = json.loads((materials_dir / ".referenced" / f"{material_id}.manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_sha256"] == meta["manifest_sha256"]
    assert [f["relpath"] for f in manifest["files"]] == ["a.md", "sub/b.md"]
    item = next(i for i in materials.list_material_source_items() if i["material_id"] == material_id)
    assert item["source_mode"] == "referenced"
    assert item["file_count"] == "2"


def test_status_detects_change_refresh_applies(env):
    _, vault, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·状态")
    material_id = created["material_id"]
    status = materials.handle_material_reference_status({"meta": {"correlation_id": "t"}, "material_id": material_id})
    assert status["status"] == "ok"
    (vault / "proj" / "sub" / "b.md").write_text("乙内容改了。\n", encoding="utf-8")
    (vault / "proj" / "c.md").write_text("新增\n", encoding="utf-8")
    status = materials.handle_material_reference_status({"meta": {"correlation_id": "t"}, "material_id": material_id})
    assert status["status"] == "changed"
    assert status["changed"] == ["sub/b.md"]
    assert status["added"] == ["c.md"]
    refreshed = materials.handle_material_reference_refresh(
        {"meta": {"correlation_id": "t"}, "material_id": material_id, "confirmed": True})
    assert refreshed["manifest_sha256"] != created["manifest_sha256"]
    meta = materials._load_meta(materials_dir / f"{material_id}.meta.yaml")
    assert meta["file_count"] == "3"
    assert (materials_dir / meta["filename"]).is_file()
    status = materials.handle_material_reference_status({"meta": {"correlation_id": "t"}, "material_id": material_id})
    assert status["status"] == "ok"
    with pytest.raises(ValueError):
        materials.handle_material_reference_refresh(
            {"meta": {"correlation_id": "t"}, "material_id": material_id})


def test_remove_reference_only_local(env):
    _, vault, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·移除")
    material_id = created["material_id"]
    result = materials.handle_material_reference_remove(
        {"meta": {"correlation_id": "t"}, "material_id": material_id, "confirmed": True})
    assert result["removed"] is True
    assert not (materials_dir / f"{material_id}.meta.yaml").exists()
    assert not (materials_dir / ".referenced" / f"{material_id}.manifest.json").exists()
    assert not list((materials_dir / ".referenced").glob(f"{material_id}-*.txt"))
    assert (vault / "proj" / "a.md").is_file()


def test_selected_text_materials_verifies_referenced(env):
    from tools.sidecar.handlers import evidence
    _, vault, _ = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·读取")
    material_id = created["material_id"]
    records = evidence._selected_text_materials([material_id])
    assert records[0]["source_mode"] == "referenced"
    assert records[0]["path"].is_file()
    (vault / "proj" / "a.md").write_text("# 甲改了\n\n甲内容改了。\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        evidence._selected_text_materials([material_id])
    assert "material_source_changed" in str(excinfo.value)


def test_fingerprint_roundtrip_blocks_on_source_change(env):
    from tools.sidecar.handlers import evidence
    from tools.infra.evidence_sources import source_fingerprints, validated_source_inputs
    _, vault, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·指纹")
    material_id = created["material_id"]
    records = evidence._selected_text_materials([material_id])
    fingerprints = source_fingerprints(records)
    entry = fingerprints[material_id]
    assert entry["mode"] == "referenced"
    assert entry["filename"].startswith(".referenced/")
    assert entry["manifest_sha256"] == created["manifest_sha256"]
    doc = {"scalars": {"source_material_fingerprints_json": json.dumps(fingerprints)},
           "lists": {"source_material_ids": [material_id]}}
    paths = validated_source_inputs(doc, materials_dir)
    assert list(paths) and paths[list(paths)[0]].is_file()
    (vault / "proj" / "a.md").write_text("# 甲又改了\n\n内容又改。\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        validated_source_inputs(doc, materials_dir)
    assert "material_source_changed" in str(excinfo.value)


def test_kb_index_reports_reference_status_and_verify(env):
    from tools.infra import knowledge_index as ki
    tmp, vault, _ = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·索引")
    material_id = created["material_id"]
    index = ki.build_index(tmp)
    entry = index["materials"][material_id]
    assert entry["source_mode"] == "referenced"
    assert entry["reference_status"] == "ok"
    assert entry["document_count"] == 2
    assert sorted(d["label"] for d in entry["documents"]) == ["a.md", "sub/b.md"]
    assert index["assets"]["referenced_materials"] == 1
    (vault / "proj" / "a.md").write_text("# 改了\n\n改了内容。\n", encoding="utf-8")
    index2 = ki.build_index(tmp)
    assert index2["materials"][material_id]["reference_status"] == "changed"
    stale = ki.verify_index(tmp, index2)
    assert any(item["kind"] == "material" and item["ref"] == material_id for item in stale)
