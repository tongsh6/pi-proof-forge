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


def test_create_rejects_duplicate_target_and_normalizes_scan_compare(env):
    _, _, _ = env
    first = _create(root_id="msr_test", relpath="proj", label="引用·A")
    with pytest.raises(ValueError) as excinfo:
        _create(root_id="msr_test", relpath="proj", label="引用·B")
    assert "duplicate" in str(excinfo.value)
    preview = _scan(root_id="msr_test", relpath="proj/")
    assert preview["existing_materials"] == [first["material_id"]]


def test_missing_source_and_corrupt_manifest_normalize_to_changed(env):
    from tools.sidecar.handlers import evidence
    _, vault, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·归一")
    material_id = created["material_id"]
    manifest_path = materials_dir / ".referenced" / f"{material_id}.manifest.json"
    manifest_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        evidence._selected_text_materials([material_id])
    assert "material_source_changed" in str(excinfo.value)
    status = materials.handle_material_reference_status({"meta": {"correlation_id": "t"}, "material_id": material_id})
    assert status["status"] == "changed"
    with pytest.raises(ValueError) as excinfo:
        materials.handle_material_reference_refresh(
            {"meta": {"correlation_id": "t"}, "material_id": material_id, "confirmed": True})
    assert "material_source_changed" in str(excinfo.value)
    manifest_path.write_text("{}", encoding="utf-8")
    import shutil as _shutil
    _shutil.rmtree(vault / "proj")
    with pytest.raises(ValueError) as excinfo:
        evidence._selected_text_materials([material_id])
    assert "material_source_changed" in str(excinfo.value)
    status = materials.handle_material_reference_status({"meta": {"correlation_id": "t"}, "material_id": material_id})
    assert status["status"] == "changed"
    with pytest.raises(ValueError) as excinfo:
        materials.handle_material_reference_refresh(
            {"meta": {"correlation_id": "t"}, "material_id": material_id, "confirmed": True})
    assert "material_source_changed" in str(excinfo.value)


def test_roots_removal_blocks_validation_and_kb(env):
    from tools.infra.evidence_sources import source_fingerprints, validated_source_inputs
    from tools.sidecar.handlers import evidence
    from tools.infra import knowledge_index as ki
    tmp, _, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·撤根")
    material_id = created["material_id"]
    records = evidence._selected_text_materials([material_id])
    fingerprints = source_fingerprints(records)
    doc = {"scalars": {"source_material_fingerprints_json": json.dumps(fingerprints)},
           "lists": {"source_material_ids": [material_id]}}
    _ = validated_source_inputs(doc, materials_dir)
    exclusions.save_material_source_roots([])
    with pytest.raises(ValueError) as excinfo:
        validated_source_inputs(doc, materials_dir)
    assert "material_source_changed" in str(excinfo.value)
    index = ki.build_index(tmp)
    assert index["materials"][material_id]["reference_status"] == "changed"


def test_kb_single_file_reference_read_roundtrip(env):
    from tools.tooling import knowledge as kb
    tmp, vault, _ = env
    (vault / "single.md").write_text("# 单档\n\n单档正文。\n", encoding="utf-8")
    created = _create(root_id="msr_test", relpath="single.md", label="引用·单档")
    assert kb.main(["build", "--root", str(tmp)]) == 0
    index = json.loads((tmp / "knowledge-index" / "index.json").read_text(encoding="utf-8"))
    doc_id = index["materials"][created["material_id"]]["documents"][0]["document_id"]
    assert kb.main(["read", created["material_id"], doc_id, "--root", str(tmp)]) == 0


def test_scan_returns_total_skipped_count(env):
    _, vault, _ = env
    for index in range(60):
        (vault / "proj" / f"secret-{index:02d}.md").write_text("x", encoding="utf-8")
    preview = _scan(root_id="msr_test", relpath="proj")
    assert preview["skipped_count"] == 61
    assert len(preview["skipped"]) == 50


def test_sensitive_name_variants_are_skipped(env):
    _, vault, _ = env
    for name in ("password.md", "密钥.md", "ＴＯＫＥＮ.md", "credentials.txt"):
        (vault / "proj" / name).write_text("敏感", encoding="utf-8")
    from tools.infra import referenced_materials as rm
    scanned = rm.scan_files(vault / "proj")
    skipped = {item["relpath"] for item in scanned["skipped"] if item["reason"] == "sensitive_name"}
    assert {"password.md", "密钥.md", "ＴＯＫＥＮ.md", "credentials.txt"} <= skipped


def test_allowlist_rejects_dangerous_roots_and_dedupes_ids(env):
    _, vault, _ = env
    from pathlib import Path as _Path
    with pytest.raises(ValueError):
        exclusions.save_material_source_roots([{"path": "/"}])
    with pytest.raises(ValueError):
        exclusions.save_material_source_roots([{"path": str(_Path.cwd())}])
    with pytest.raises(ValueError):
        exclusions.save_material_source_roots([{"path": str(_Path.cwd() / "materials")}])
    exclusions.save_material_source_roots([
        {"id": "msr_same", "label": "a", "path": str(vault)},
        {"id": "msr_same", "label": "b", "path": str(vault / "proj")},
    ])
    roots = exclusions.load_material_source_roots()
    assert len({r["id"] for r in roots}) == 2


def test_ensure_detects_meta_manifest_mismatch(env):
    from tools.sidecar.handlers import evidence
    _, _, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·元数据")
    meta_path = materials_dir / f"{created['material_id']}.meta.yaml"
    text = meta_path.read_text(encoding="utf-8").replace(created["manifest_sha256"], "0" * 64)
    meta_path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        evidence._selected_text_materials([created["material_id"]])
    assert "material_source_changed" in str(excinfo.value)


def test_kb_corrupt_manifest_marks_changed(env):
    from tools.infra import knowledge_index as ki
    tmp, _, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·损坏清单")
    (materials_dir / ".referenced" / f"{created['material_id']}.manifest.json").write_text("{ nope", encoding="utf-8")
    index = ki.build_index(tmp)
    assert index["materials"][created["material_id"]]["reference_status"] == "changed"


def test_job_preferences_roundtrip_from_referenced_material(env):
    from tools.sidecar.handlers import job_preferences as jp_handler
    from tools.infra.job_preferences import load_preferences
    from tools.infra.material_documents import split_material_documents
    tmp, vault, materials_dir = env
    created = _create(root_id="msr_test", relpath="proj", label="引用·偏好")
    cache = (materials_dir / created["filename"]).read_text(encoding="utf-8")
    docs = split_material_documents(cache, Path(created["filename"]).name)
    doc = next(d for d in docs if d["label"] == "a.md")
    source, text = jp_handler._source(created["material_id"], doc["document_id"])
    assert source["filename"].startswith(".referenced/")
    quote = next(line for line in ("甲内容。", "乙内容。") if line in text)
    payload = {"schema_version": 1, "source": source,
               "items": [{"kind": "primary", "text": "产品平台方向", "quote": quote}],
               "confirmed_at": "2026-10-17T00:00:00Z"}
    profile_path = tmp / "personal_profile.yaml"
    profile_path.write_text(f'job_preferences_json: {json.dumps(json.dumps(payload, ensure_ascii=False))}\n', encoding="utf-8")
    value = load_preferences(profile_path)
    assert value["items"][0]["text"] == "产品平台方向"
    (vault / "proj" / "a.md").write_text("# 甲改\n\n甲内容改了。\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_preferences(profile_path)


def _exact_card(env, monkeypatch, *, whole=False):
    from tools.sidecar.handlers import evidence
    from tools.infra.material_documents import split_material_documents
    tmp, vault, library = env
    bound = vault / "proj" / "a.md"
    bound.write_text("原始可核结果。\n编辑后可核结果。\n", encoding="utf-8")
    created = _create(root_id="msr_test", relpath="proj", label="引用·已有卡片")
    mid = created["material_id"]
    cache = library / created["filename"]
    doc = next(d for d in split_material_documents(cache.read_text(), cache.name) if d["source_name"]=="a.md")
    refs = [{"material_id":mid,"document_id":doc["document_id"],"sha256":doc["sha256"]}]
    card_dir = tmp / "evidence_cards"
    monkeypatch.setattr(evidence, "_EVIDENCE_DIR", card_dir)
    card = card_dir / "ec_exact.yaml"
    evidence._write_evidence_file(card, {
        "id":"ec_exact","title":"已有卡片","status":"saved_eligible","review_decision":"approved",
        "candidate_pool_eligible":True,"source_material_ids":[mid],
        "source_documents_json":json.dumps(refs),"source_whole_material_ids_json":json.dumps([mid] if whole else []),
        "results":["原始可核结果。"],"artifacts":[mid],"time_range":"","context":"","role_scope":"",
        "created_at":"","updated_at":"","actions":[],"stack":[],"tags":[]
    })
    return evidence,card,bound,cache,mid,refs


def test_exact_card_edit_rereview_and_snapshot_across_unrelated_collection_drift(env,monkeypatch):
    import hashlib
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    from tools.infra.evidence_sources import assert_captured_source, validated_source_inputs
    from tools.sidecar.handlers._shared.material_sources import selected_text_materials

    evidence,card,bound,cache,mid,refs = _exact_card(env,monkeypatch)
    (bound.parent/"sub"/"b.md").write_text("无关源文件改动。",encoding="utf-8")
    (bound.parent/"new.md").write_text("新增文件未被选定。",encoding="utf-8")
    cache_before=cache.read_bytes()
    with pytest.raises(ValueError, match="material_source_changed"):
        selected_text_materials([mid])
    evidence.handle_evidence_update({"meta":{"correlation_id":"t"},"evidence_id":"ec_exact",
                                     "patch":{"results":['编辑后可核结果。']}})
    saved=parse_simple_yaml(card.read_text())
    assert saved["lists"]["results"]==["编辑后可核结果。"]
    assert saved["scalars"]["status"]=="needs_review"
    assert saved["scalars"]["review_decision"]=="pending"
    assert saved["scalars"]["candidate_pool_eligible"]=="false"
    params={"meta":{"correlation_id":"t"},"evidence_id":"ec_exact","save_mode":"eligible",
            "expected_sha256":hashlib.sha256(card.read_bytes()).hexdigest(),"review":{"decision":"approved"},
            "draft":{"title":"已有卡片","results":['编辑后可核结果。'],"artifacts":[{"ref":mid,"type":"text_document","label":"原始材料"}],
                     "source_material_ids":[mid],"source_documents":refs,
                     "field_sources":[{"field":"results","value":"编辑后可核结果。","quote":"编辑后可核结果。",**refs[0]}]}}
    evidence.handle_evidence_save_draft(params)
    saved=parse_simple_yaml(card.read_text())
    assert saved["scalars"]["status"]=="saved_eligible"
    sources=validated_source_inputs(saved, cache.parent.parent)
    assert bound.resolve() in {path.resolve() for path in sources.values()}
    assert cache.read_bytes()==cache_before
    bound.write_text(bound.read_text()+"所绑定文件有改动。",encoding="utf-8")
    source_key=next(key for key,path in sources.items() if path.resolve()==bound.resolve())
    with pytest.raises(ValueError,match="material_source_changed"):
        assert_captured_source(sources,source_key,hashlib.sha256(bound.read_bytes()).hexdigest())
    with pytest.raises(ValueError,match="material_source_changed"):
        validated_source_inputs(saved,cache.parent.parent)


@pytest.mark.parametrize("fault",["bound_edited","bound_missing","cached_tampered","ambiguous","forged_label","unbound_new","whole_material"])
def test_scoped_edit_fails_closed_and_preserves_card_on_integrity_failure(env,monkeypatch,fault):
    evidence,card,bound,cache,mid,_=_exact_card(env,monkeypatch,whole=fault=="whole_material")
    (bound.parent/"sub"/"b.md").write_text("无关源文件改动。",encoding="utf-8")
    proposal="编辑后可核结果。"
    if fault=="bound_edited":
        bound.write_text(bound.read_text()+"所绑定文件有改动。",encoding="utf-8")
    elif fault=="bound_missing":
        bound.unlink()
    elif fault=="cached_tampered":
        cache.write_text(cache.read_text().replace("编辑后可核结果。","缓存伪造。"),encoding="utf-8")
    elif fault=="ambiguous":
        cache.write_text(cache.read_text()+"\n# Source: a.md\n\n"+bound.read_text(),encoding="utf-8")
    elif fault=="forged_label":
        from tools.infra.persistence.yaml_io import parse_simple_yaml
        text=card.read_text()
        refs=json.loads(parse_simple_yaml(text)["scalars"]["source_documents_json"])
        refs[0]["label"]="伪来源"
        encoded=json.dumps(json.dumps(refs,ensure_ascii=False),ensure_ascii=False)
        card.write_text("\n".join("source_documents_json: "+encoded if line.startswith("source_documents_json:")
                                    else line for line in text.splitlines())+"\n",encoding="utf-8")
    elif fault=="unbound_new":
        proposal="新增文件未被选定。"
        (bound.parent/"new.md").write_text(proposal,encoding="utf-8")
    before=card.read_bytes()
    with pytest.raises(ValueError):
        evidence.handle_evidence_update({"meta":{"correlation_id":"t"},"evidence_id":"ec_exact",
                                         "patch":{"results":[proposal]}})
    assert card.read_bytes()==before


def test_bound_file_race_does_not_commit_evidence_edit(env,monkeypatch):
    from tools.sidecar.handlers import evidence_crud
    evidence,card,bound,cache,mid,_=_exact_card(env,monkeypatch)
    original=evidence_crud.read_source_documents
    def after_read(*args,**kwargs):
        selected=original(*args,**kwargs)
        bound.write_text(bound.read_text()+"所绑定文件竞态改动。",encoding="utf-8")
        return selected
    monkeypatch.setattr(evidence_crud,"read_source_documents",after_read)
    before=card.read_bytes()
    with pytest.raises(ValueError,match="material_source_changed"):
        evidence.handle_evidence_update({"meta":{"correlation_id":"t"},"evidence_id":"ec_exact",
                                        "patch":{"results":['编辑后可核结果。']}})
    assert card.read_bytes()==before


@pytest.mark.parametrize("case", ["success", "same_material_expansion", "whole", "changed_new", "changed_old", "stale", "reordered", "new_race", "card_race"])
def test_merge_scopes_only_unchanged_exact_materials(env, monkeypatch, case):
    import hashlib
    from tools.infra.evidence_sources import validated_source_inputs
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    evidence,card,bound,cache,mid,refs = _exact_card(env,monkeypatch,whole=case=="whole")
    tmp,vault,library = env
    extra=vault/"new.md"; extra.write_text("独立材料证实本人职责。",encoding="utf-8")
    fresh=_create(root_id="msr_test",relpath="new.md",label="新增材料")["material_id"]
    same_docs=evidence.handle_list_material_documents({"material_id":mid})["items"]
    fresh_doc=evidence.handle_list_material_documents({"material_id":fresh})["items"][0]
    extra_ref={"material_id":fresh,**{k:fresh_doc[k] for k in ("document_id","sha256","label")}}
    source_docs=refs+[extra_ref]
    if case=="same_material_expansion":
        same_doc=next(d for d in same_docs if d["document_id"]!=refs[0]["document_id"])
        source_docs=source_docs+[{"material_id":mid,**{k:same_doc[k] for k in ("document_id","sha256","label")}}]
    (bound.parent/"sub"/"b.md").write_text("无关文件另有改动。",encoding="utf-8")
    if case=="changed_new": extra.write_text("新增证据已改变。",encoding="utf-8")
    if case=="changed_old": bound.write_text("所选正文已改变。",encoding="utf-8")
    if case=="reordered": source_docs.reverse()
    before=card.read_bytes()
    role="独立材料证实本人职责。"
    params={"meta":{"correlation_id":"synthetic-qa"},"evidence_id":"ec_exact","save_mode":"eligible",
        "expected_sha256":hashlib.sha256(before).hexdigest() if case!="stale" else "stale",
        "review":{"decision":"approved","merge_sources":True},
        "draft":{"title":"已有卡片","role_scope":role,"results":['原始可核结果。'],
                 "source_material_ids":[mid,fresh],"source_documents":source_docs,
                 "artifacts":[{"ref":mid,"type":"text_document","label":"原始材料"}],
                 "field_sources":[{"field":"role_scope","value":role,"quote":role,**extra_ref}]}}
    if case in {"new_race", "card_race"}:
        from tools.sidecar.handlers import evidence_draft
        read = evidence_draft.read_source_documents
        def read_then_change(*args, **kwargs):
            result = read(*args, **kwargs)
            if case == "new_race":
                extra.write_text("合并验证后的变更。", encoding="utf-8")
            else:
                card.write_bytes(before+b"# concurrent\n")
            return result
        monkeypatch.setattr(evidence_draft, "read_source_documents", read_then_change)
    if case!="success":
        error={"stale":"evidence_review_changed","card_race":"evidence_review_changed","reordered":"evidence_review_source_mismatch"}.get(case,"material_source_changed")
        with pytest.raises(ValueError,match=error):
            evidence.handle_evidence_save_draft(params)
        assert card.read_bytes()==(before+b"# concurrent\n" if case=="card_race" else before)
        return
    result=evidence.handle_evidence_save_draft(params)
    assert result["candidate_pool_eligible"] is True
    saved=parse_simple_yaml(card.read_text())
    assert json.loads(saved["scalars"]["source_documents_json"])==source_docs
    sources=validated_source_inputs(saved,library)
    assert {bound.resolve(),extra.resolve()}<={path.resolve() for path in sources.values()}
