"""L4: real Router/source lifecycle; only the final model HTTP response is substituted."""
from __future__ import annotations

import base64
import io
import json

import pytest

from tools.infra import knowledge_index
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.sidecar import server
from tools.sidecar.handlers import evidence, materials, profile

QUOTE = "2023-03，我负责订单服务的接口改造与库存同步验证。"
ACTION = "完成订单服务接口改造与库存同步验证。"
RESULT = "库存同步功能已验收上线。"
BODY = f"# 订单服务周报\n\n{QUOTE}\n{ACTION}\n{RESULT}\n"
BUNDLE = f"# Source: project/work-log.md\n{BODY}"


def _request(app, method, **params):
    return server.process_request({
        "jsonrpc": "2.0", "id": "inference-lifecycle",
        "method": method, "params": {"meta": {"correlation_id": "inference-lifecycle"}, **params},
    })


def _rpc(app, method, **params):
    response = _request(app, method, **params)
    assert "error" not in response, response
    return response["result"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PPF_POLICY_PATH", str(tmp_path / "policy.local.yaml"))
    monkeypatch.setattr(materials, "_MATERIALS_DIR", tmp_path / "materials")
    monkeypatch.setattr(evidence, "_EVIDENCE_DIR", tmp_path / "evidence_cards")
    monkeypatch.setattr(profile, "_PROFILE_PATH", tmp_path / "personal_profile.yaml")
    state = {"root": tmp_path, "calls": [], "during_call": None, "reply_material": None, "quote": QUOTE, "time": "2023-03", "role": "订单服务接口改造负责人", "roots": []}

    def respond(request, **kwargs):
        assert request.full_url == "http://127.0.0.1:8000/v1/chat/completions"
        payload = json.loads(request.data)
        prompt = payload["messages"][-1]["content"]
        inputs = json.loads(prompt.split("INPUT JSON:\n", 1)[1])
        state["calls"].append(inputs)
        if state["during_call"]:
            state["during_call"]()
        chosen = next(
            (item for item in inputs["documents"] if item["material_id"] == state["reply_material"]),
            inputs["documents"][0] if inputs["documents"] else None,
        )
        citation = [] if chosen is None else [{
            "material_id": chosen["material_id"], "document_id": chosen["document_id"],
            "excerpt": state["quote"],
        }]
        reply = {
            "time_range": {"value": state["time"], "precision": "month", "confidence": 0.8, "evidence": citation},
            "role_scope": {"value": state["role"], "confidence": 0.8, "evidence": citation},
        }
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(reply, ensure_ascii=False)}}]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", respond)
    _rpc(state, "settings.update", section="llm_config", payload={
        "provider": "openai_compatible", "model": "synthetic-inference",
        "base_url": "http://127.0.0.1:8000/v1", "thinking_enabled": False,
    })
    _enabled(state, True)
    return state


def _enabled(app, value):
    _rpc(app, "settings.update", section="evidence_inference", payload={"enabled": value})


def _document(app, material_id):
    documents = _rpc(app, "evidence.listMaterialDocuments", material_id=material_id)["items"]
    assert len(documents) == 1, documents
    document = documents[0]
    read = _rpc(app, "evidence.readMaterialDocument", material_id=material_id, document_id=document["document_id"])
    assert read["sha256"] == document["sha256"]
    metadata = parse_simple_yaml((app["root"] / "materials" / f"{material_id}.meta.yaml").read_text())["scalars"]
    return {
        "ref": {"material_id": material_id, **{key: document[key] for key in ("document_id", "sha256", "label")}},
        "path": app["root"] / "materials" / metadata["filename"],
        "text": read["text"],
    }


def _upload(app, text=BUNDLE, label="订单服务工作记录"):
    result = _rpc(app, "material.upload", file={
        "filename": "work-log.txt",
        "content_base64": base64.b64encode(text.encode()).decode(),
    }, label=label)
    return _document(app, result["material_id"])


def _card(app, source=None, **draft_fields):
    source = source or _upload(app)
    ref = source["ref"]
    saved = _rpc(app, "evidence.saveDraft", save_mode="eligible", review={"decision": "approved"}, draft={
        "source_material_ids": [ref["material_id"]], "source_documents": [ref],
        "title": "订单服务", "time_range": "", "role_scope": "", "context": "订单处理与库存同步",
        "actions": [ACTION], "results": [RESULT], "stack": ["Java"], "tags": ["订单服务"],
        "artifacts": [{"type": "text_document", "ref": ref["material_id"], "label": "工作记录"}],
        **draft_fields,
    })
    card = {"id": saved["evidence_id"], "path": app["root"] / "evidence_cards" / f"{saved['evidence_id']}.yaml", "source": source}
    app["card"] = card
    app["reply_material"] = ref["material_id"]
    return card


def _index(app):
    index = knowledge_index.build_index(app["root"])
    knowledge_index.save_index(index, app["root"] / "knowledge-index")
    return index


def _infer(app):
    return _rpc(app, "evidence.inferFields", card_ids=[app["card"]["id"]])


def _candidates(result):
    assert result["status"] == "ok", result
    assert len(result["cards"]) == 1, result
    return result["cards"][0]["candidates"]


def _state_bytes(app):
    path = app["root"] / "app-data" / "evidence_inference.json"
    return path.read_bytes() if path.exists() else None


def _reference(app, name):
    vault = app["root"] / f"vault-{name}"
    (vault / "shared").mkdir(parents=True)
    external = vault / "shared" / "week.md"
    external.write_text(BODY)
    root_id = f"msr_{name}"
    app["roots"].append({"id": root_id, "label": f"工作库{name}", "path": str(vault)})
    _rpc(app, "settings.update", section="material_source_roots", payload=app["roots"])
    result = _rpc(app, "material.reference.create", root_id=root_id, relpath="shared", label="订单服务周报")
    source = _document(app, result["material_id"])
    source["external"] = external
    source["manifest"] = app["root"] / "materials" / ".referenced" / f"{result['material_id']}.manifest.json"
    return source


def _career(app, *, reviewed, linked=True, start="2022-01", end="2025-06"):
    from tests.unit.sidecar.test_career_profile import career

    evidence_id = app["card"]["id"]
    if not linked:
        target, reply_material = app["card"], app["reply_material"]
        other = _card(app, _upload(app, BUNDLE.replace("project/work-log.md", "other/work-log.md")))
        evidence_id = other["id"]
        app["card"], app["reply_material"] = target, reply_material
    value = career()
    value["work"][0].update({
        "scope": "订单服务接口与库存同步", "start": start, "end": end,
        "evidence_ids": [evidence_id],
    })
    value["skills"][0]["evidence_ids"] = [evidence_id]
    current = _rpc(app, "profile.get")["profile"]
    _rpc(app, "profile.update", expected_revision=current["revision"], patch={
        "name": "合成候选人", "phone": "13800000000", "email": "candidate@example.invalid",
        "city": "上海", "current_position": "后端工程师", "career": value,
    })
    current = _rpc(app, "profile.get")["profile"]
    if reviewed:
        current = _rpc(app, "profile.review", expected_revision=current["revision"], confirmed=True)["profile"]
    assert current["career_status"]["reviewed"] is reviewed
    return current


def _assert_invalid_without_publication(app, response, before):
    assert "error" in response, response
    assert response["error"]["code"] == "VALIDATION_ERROR", response
    assert "result" not in response
    assert _state_bytes(app) == before


@pytest.mark.parametrize("initial", ("missing", "corrupt", "restored_body"))
def test_infer_prepares_current_index_after_real_upload_and_save(app, initial):
    card = _card(app)
    before = card["path"].read_bytes()
    index_dir = app["root"] / "knowledge-index"
    if initial == "corrupt":
        index_dir.mkdir()
        (index_dir / "index.json").write_text("{broken")
    elif initial == "restored_body":
        path = card["source"]["path"]
        original = path.read_bytes()
        path.unlink()
        skipped = _index(app)
        assert any(item["error"] == "filename_missing" for item in skipped["skipped"])
        path.write_bytes(original)
    else:
        assert not index_dir.exists()
    result = _infer(app)
    candidates = _candidates(result)
    assert {item["field"] for item in candidates} == {"time_range", "role_scope"}
    assert all(item["level"] == "L3" for item in candidates)
    expected = card["source"]["ref"]
    assert all(item["evidence"][0]["material_id"] == expected["material_id"] for item in candidates)
    assert all(item["evidence"][0]["sha256"] == expected["sha256"] for item in candidates)
    assert len(app["calls"]) == 1
    assert card["path"].read_bytes() == before
    refreshed = json.loads((index_dir / "index.json").read_text())
    assert expected["material_id"] in refreshed["materials"]
    assert (index_dir / "INDEX.md").is_file()


def test_no_targets_needs_neither_index_nor_model(app):
    result = _rpc(app, "evidence.inferFields", card_ids=[])
    assert result["status"] == "no_target_cards", result
    assert not app["calls"]
    assert not (app["root"] / "knowledge-index").exists()
    assert _state_bytes(app) is None


def test_stable_current_sources_reuse_cache_without_mutating_card(app):
    card = _card(app)
    _index(app)
    original = card["path"].read_bytes()
    first = _infer(app)
    second = _infer(app)
    assert _candidates(first)
    assert _candidates(second) == _candidates(first)
    assert first["cards"][0]["cache"] == "miss"
    assert second["cards"][0]["cache"] == "hit"
    assert len(app["calls"]) == 1
    assert card["path"].read_bytes() == original


def test_unrelated_job_changes_do_not_invalidate_source_cache_or_enter_prompt(app):
    _card(app)
    jobs = app["root"] / "job_profiles"
    jobs.mkdir()
    path = jobs / "jp_unrelated.yaml"
    path.write_text('id: "jp_unrelated"\ntitle: "Unrelated forensic keyword"\n')
    _index(app)
    first = _infer(app)
    path.write_text('id: "jp_unrelated"\ntitle: "Changed unrelated forensic keyword"\n')
    second = _infer(app)
    assert _candidates(first)
    assert _candidates(second) == _candidates(first)
    assert second["cards"][0]["cache"] == "hit"
    assert len(app["calls"]) == 1
    assert "forensic keyword" not in json.dumps(app["calls"], ensure_ascii=False)


def test_same_document_replacement_material_cannot_borrow_previous_cache(app):
    card = _card(app)
    source_a = _reference(app, "a")
    app["reply_material"] = source_a["ref"]["material_id"]
    _index(app)
    first = _infer(app)
    assert _candidates(first)[0]["evidence"][0]["material_id"] == source_a["ref"]["material_id"]
    original = card["path"].read_bytes()
    _rpc(app, "material.reference.remove", material_id=source_a["ref"]["material_id"], confirmed=True)
    source_b = _reference(app, "b")
    assert source_a["ref"]["document_id"] == source_b["ref"]["document_id"]
    assert source_a["ref"]["sha256"] == source_b["ref"]["sha256"]
    app["reply_material"] = source_b["ref"]["material_id"]
    _index(app)
    second = _infer(app)
    assert second["cards"][0]["cache"] == "miss", second
    assert len(app["calls"]) == 2
    candidates = _candidates(second)
    assert candidates
    assert all(item["evidence"][0]["material_id"] == source_b["ref"]["material_id"] for item in candidates)
    third = _infer(app)
    assert third["cards"][0]["cache"] == "hit"
    assert _candidates(third) == candidates
    assert len(app["calls"]) == 2
    assert card["path"].read_bytes() == original


def test_simultaneous_same_document_materials_preserve_explicit_citation_identity(app):
    _card(app)
    sources = sorted([_reference(app, "a"), _reference(app, "b")], key=lambda item: item["ref"]["material_id"])
    assert sources[0]["ref"]["document_id"] == sources[1]["ref"]["document_id"]
    app["reply_material"] = sources[0]["ref"]["material_id"]
    _index(app)
    result = _infer(app)
    docs = app["calls"][0]["documents"]
    assert {item["material_id"] for item in docs if item["document_id"] == sources[0]["ref"]["document_id"]} == {
        item["ref"]["material_id"] for item in sources
    }
    candidates = _candidates(result)
    assert candidates
    assert all(item["evidence"][0]["material_id"] == sources[0]["ref"]["material_id"] for item in candidates)


@pytest.mark.parametrize("warm", (False, True))
def test_changed_selected_reference_is_not_sent_or_returned_from_cache_without_refresh(app, warm):
    _card(app)
    source = _reference(app, "changed")
    app["reply_material"] = source["ref"]["material_id"]
    _index(app)
    if warm:
        assert _candidates(_infer(app))
    before = _state_bytes(app)
    calls = len(app["calls"])
    manifest = source["manifest"].read_bytes()
    cached = source["path"].read_bytes()
    source["external"].write_text(BODY.replace("我负责", "同事负责"))
    response = _request(app, "evidence.inferFields", card_ids=[app["card"]["id"]])
    _assert_invalid_without_publication(app, response, before)
    assert len(app["calls"]) == calls
    assert source["manifest"].read_bytes() == manifest
    assert source["path"].read_bytes() == cached
    assert _rpc(app, "material.reference.status", material_id=source["ref"]["material_id"])["status"] == "changed"


def test_explicit_reference_refresh_can_restore_new_current_document(app):
    _card(app)
    source = _reference(app, "refreshed")
    source["external"].write_text(BODY.replace("2023-03", "2024-05"))
    _rpc(app, "material.reference.refresh", material_id=source["ref"]["material_id"], confirmed=True)
    current = _document(app, source["ref"]["material_id"])
    assert current["ref"]["sha256"] != source["ref"]["sha256"]
    app["reply_material"] = current["ref"]["material_id"]
    app["quote"] = QUOTE.replace("2023-03", "2024-05")
    app["time"] = "2024-05"
    _index(app)
    candidates = _candidates(_infer(app))
    assert candidates
    assert all(item["evidence"][0]["sha256"] == current["ref"]["sha256"] for item in candidates)
    assert len(app["calls"]) == 1


@pytest.mark.parametrize("initial_enabled", (False, True))
def test_inference_mode_switch_does_not_reuse_opposite_mode_cache(app, initial_enabled):
    _card(app)
    _index(app)
    _enabled(app, initial_enabled)
    first = _infer(app)
    first_candidates = _candidates(first)
    assert first_candidates
    assert {item["level"] for item in first_candidates} == ({"L3"} if initial_enabled else {"L2"})
    _enabled(app, not initial_enabled)
    second = _infer(app)
    assert second["cards"][0]["cache"] == "miss", second
    assert {item["level"] for item in _candidates(second)} == ({"L2"} if initial_enabled else {"L3"})
    assert len(app["calls"]) == 1


@pytest.mark.parametrize(("reviewed", "linked"), ((False, True), (True, False)))
def test_only_confirmed_related_profile_can_bound_inference_dates(app, reviewed, linked):
    _card(app)
    _career(app, reviewed=reviewed, linked=linked, start="2024-01", end="2025-06")
    _index(app)
    candidates = _candidates(_infer(app))
    assert app["calls"][0]["employment_window"] == []
    assert app["calls"][0]["confirmed_work_context"] == []
    assert any(item["field"] == "time_range" and item["value"] == "2023-03" for item in candidates)


def test_confirmed_related_profile_retains_its_actual_date_constraint(app):
    _card(app)
    _career(app, reviewed=True, start="2024-01", end="2025-06")
    _index(app)
    candidates = _candidates(_infer(app))
    assert app["calls"][0]["employment_window"] == ["2024-01 ~ 2025-06"]
    assert app["calls"][0]["confirmed_work_context"][0]["scope"] == "订单服务接口与库存同步"
    assert not any(item["field"] == "time_range" for item in candidates)


@pytest.mark.parametrize("changed", ("card", "source", "profile"))
def test_input_change_during_model_does_not_publish_or_replace_previous_state(app, changed):
    card = _card(app)
    if changed == "profile":
        _career(app, reviewed=True)
    _index(app)
    assert _candidates(_infer(app))
    before = _state_bytes(app)
    # A new real document causes a miss without changing the reviewed card/profile.
    _upload(app, BUNDLE.replace("project/work-log.md", "project/follow-up.md"))
    _index(app)
    mutated = {}

    def mutate():
        if changed == "card":
            _rpc(app, "evidence.update", evidence_id=card["id"], patch={"context": "并发更新后的订单服务职责上下文"})
            path = card["path"]
        elif changed == "source":
            path = card["source"]["path"]
            path.write_text(BUNDLE.replace("我负责", "同事负责"))
        else:
            current = _rpc(app, "profile.get")["profile"]
            career = current["career"]
            career["work"][0]["scope"] = "并发更新后的本人职责范围"
            _rpc(app, "profile.update", expected_revision=current["revision"], patch={"career": career})
            path = app["root"] / "personal_profile.yaml"
        mutated["path"], mutated["bytes"] = path, path.read_bytes()

    app["during_call"] = mutate
    response = _request(app, "evidence.inferFields", card_ids=[card["id"]])
    assert len(app["calls"]) == 2
    if changed == "profile":
        assert app["calls"][-1]["confirmed_work_context"][0]["scope"] == "订单服务接口与库存同步"
    _assert_invalid_without_publication(app, response, before)
    assert mutated["path"].read_bytes() == mutated["bytes"]



def test_revoking_selected_reference_root_during_model_does_not_publish(app):
    card = _card(app)
    source = _reference(app, "revoked")
    app["reply_material"] = source["ref"]["material_id"]
    _index(app)
    assert _candidates(_infer(app))
    before = _state_bytes(app)
    _upload(app, BUNDLE.replace("project/work-log.md", "project/follow-up.md"))
    _index(app)
    unchanged = {key: source[key].read_bytes() for key in ("path", "external", "manifest")}
    revoked = {}

    def revoke():
        assert source["ref"]["material_id"] in {item["material_id"] for item in app["calls"][-1]["documents"]}
        _rpc(app, "settings.update", section="material_source_roots", payload=[])
        revoked["policy"] = (app["root"] / "policy.local.yaml").read_bytes()

    app["during_call"] = revoke
    response = _request(app, "evidence.inferFields", card_ids=[card["id"]])
    assert len(app["calls"]) == 2
    assert revoked
    assert {key: source[key].read_bytes() for key in unchanged} == unchanged
    _assert_invalid_without_publication(app, response, before)
    assert (app["root"] / "policy.local.yaml").read_bytes() == revoked["policy"]


@pytest.mark.parametrize("changed_card", ("second", "first"))
def test_multi_card_inference_publishes_only_after_all_used_inputs_are_current(app, changed_card):
    first = _card(app, stack=[])
    second_quote = "2024-06，我负责气象观测的数据校准与传感器联调。"
    second_action = "完成气象观测的数据校准与传感器联调。"
    second_result = "气象观测数据采集已经验收。"
    second_text = f"# Source: weather/observations.md\n# 气象观测\n\n{second_quote}\n{second_action}\n{second_result}\n"
    second_source = _upload(app, second_text, label="气象观测记录")
    second = _card(
        app, second_source, title="气象观测", context="气温与降水数据校准",
        tags=["气象观测"], stack=[], actions=[second_action], results=[second_result],
    )
    by_title = {
        "订单服务": (first, QUOTE, "2023-03", "订单服务接口改造负责人"),
        "气象观测": (second, second_quote, "2024-06", "气象观测数据校准负责人"),
    }
    mutated = {}
    phase = {"mutate": False}

    def respond_for_card():
        inputs = app["calls"][-1]
        card, quote, time, role = by_title[inputs["card"]["title"]]
        app["reply_material"], app["quote"], app["time"], app["role"] = card["source"]["ref"]["material_id"], quote, time, role
        mids = {item["material_id"] for item in inputs["documents"]}
        assert card["source"]["ref"]["material_id"] in mids
        peer = second if card is first else first
        assert peer["source"]["ref"]["material_id"] not in mids
        if phase["mutate"] and card is second:
            target = second if changed_card == "second" else first
            path = target["source"]["path"]
            path.write_text(target["source"]["text"].replace("我负责", "同事负责"))
            mutated["path"], mutated["bytes"] = path, path.read_bytes()

    app["during_call"] = respond_for_card
    _index(app)
    initial = _rpc(app, "evidence.inferFields", card_ids=[first["id"], second["id"]])
    assert initial["status"] == "ok", [(row["card_id"], row.get("error")) for row in initial["cards"]]
    assert [row["card_id"] for row in initial["cards"]] == [first["id"], second["id"]]
    assert all(row["candidates"] for row in initial["cards"])
    assert len(app["calls"]) == 2
    before = _state_bytes(app)
    _upload(app, BUNDLE.replace("project/work-log.md", "project/follow-up.md"))
    _upload(app, second_text.replace("weather/observations.md", "weather/follow-up.md"), label="气象观测记录")
    _index(app)
    phase["mutate"] = True

    response = _request(app, "evidence.inferFields", card_ids=[first["id"], second["id"]])
    assert len(app["calls"]) == 4
    assert [item["card"]["title"] for item in app["calls"][-2:]] == ["订单服务", "气象观测"]
    assert {item["material_id"] for item in app["calls"][-2]["documents"]}.isdisjoint(
        item["material_id"] for item in app["calls"][-1]["documents"]
    )
    assert mutated
    _assert_invalid_without_publication(app, response, before)
    assert mutated["path"].read_bytes() == mutated["bytes"]


def test_candidate_rejected_during_model_is_not_restored_by_old_inference_state(app):
    card = _card(app)
    _index(app)
    initial = _infer(app)
    candidates = _candidates(initial)
    rejected_candidate = next(item for item in candidates if item["field"] == "time_range")
    card_sha = initial["cards"][0]["card_sha256"]
    before = _state_bytes(app)
    _upload(app, BUNDLE.replace("project/work-log.md", "project/follow-up.md"))
    _index(app)
    concurrent = {}

    def reject():
        result = _rpc(
            app, "evidence.confirmInference", evidence_id=card["id"], card_sha256=card_sha,
            candidate_hash=rejected_candidate["candidate_hash"],
            field="time_range", action="reject", value=rejected_candidate["value"],
        )
        assert result["status"] == "rejected"
        assert result["candidate_hash"] == rejected_candidate["candidate_hash"]
        concurrent["state"] = _state_bytes(app)
        assert concurrent["state"] != before

    app["during_call"] = reject
    response = _request(app, "evidence.inferFields", card_ids=[card["id"]])
    assert len(app["calls"]) == 2
    assert concurrent
    current = json.loads(_state_bytes(app))["cards"][card["id"]]
    assert rejected_candidate["candidate_hash"] in current["rejected"]
    assert all(item["candidate_hash"] != rejected_candidate["candidate_hash"] for item in current["candidates"])
    if "result" in response:
        assert all(item["candidate_hash"] != rejected_candidate["candidate_hash"] for item in _candidates(response["result"]))
    else:
        assert response["error"]["code"] == "VALIDATION_ERROR"
        assert _state_bytes(app) == concurrent["state"]



@pytest.mark.parametrize("corrupt_fingerprint", (False, True), ids=("valid-binding", "null-fingerprint"))
def test_only_valid_persisted_fingerprint_can_narrow_reference_revalidation(app, corrupt_fingerprint):
    vault = app["root"] / "vault-boundary"
    folder = vault / "records"
    folder.mkdir(parents=True)
    selected_path = folder / "orders.md"
    selected_path.write_text(BODY)
    unrelated_path = folder / "garden.md"
    unrelated_path.write_text("# 花卉养护\n\n清晨补充盆栽水分并记录温度。\n")
    app["roots"].append({"id": "msr_boundary", "label": "资料目录", "path": str(vault)})
    _rpc(app, "settings.update", section="material_source_roots", payload=app["roots"])
    created = _rpc(app, "material.reference.create", root_id="msr_boundary", relpath="records", label="原始材料")
    material_id = created["material_id"]
    documents = _rpc(app, "evidence.listMaterialDocuments", material_id=material_id)["items"]
    assert len(documents) == 2
    read = [
        (document, _rpc(app, "evidence.readMaterialDocument", material_id=material_id, document_id=document["document_id"]))
        for document in documents
    ]
    document, body = next((document, body) for document, body in read if QUOTE in body["text"])
    metadata = parse_simple_yaml((app["root"] / "materials" / f"{material_id}.meta.yaml").read_text())["scalars"]
    source = {
        "ref": {"material_id": material_id, **{key: document[key] for key in ("document_id", "sha256", "label")}},
        "path": app["root"] / "materials" / metadata["filename"],
        "text": body["text"],
    }
    card = _card(app, source, stack=[], field_sources=[{
        "field": "actions", "value": ACTION, "quote": ACTION,
        "material_id": material_id, "document_id": document["document_id"],
    }])
    initial = _infer(app)
    initial_candidates = _candidates(initial)
    assert initial_candidates
    assert len(app["calls"]) == 1
    expected_source = {(material_id, document["document_id"])}
    assert {(row["material_id"], row["document_id"]) for row in app["calls"][0]["documents"]} == expected_source
    before = _state_bytes(app)
    original_source = selected_path.read_bytes()
    original_cache = source["path"].read_bytes()
    unrelated_path.write_text("# 花卉养护\n\n傍晚补充盆栽水分并记录温度。\n")

    fields = parse_simple_yaml(card["path"].read_text())["scalars"]
    fingerprints = json.loads(fields["source_material_fingerprints_json"])
    assert isinstance(fingerprints[material_id], dict) and fingerprints[material_id]
    if corrupt_fingerprint:
        # Negative fixture: corrupt the persisted binding, without simulating any approval.
        fingerprints[material_id] = None
        rows = card["path"].read_text().splitlines()
        assert sum(row.startswith("source_material_fingerprints_json:") for row in rows) == 1
        replacement = "source_material_fingerprints_json: " + json.dumps(json.dumps(fingerprints, ensure_ascii=False), ensure_ascii=False)
        card["path"].write_text("\n".join(replacement if row.startswith("source_material_fingerprints_json:") else row for row in rows) + "\n")
    current_card = card["path"].read_bytes()
    response = _request(app, "evidence.inferFields", card_ids=[card["id"]])
    assert selected_path.read_bytes() == original_source
    assert source["path"].read_bytes() == original_cache
    assert card["path"].read_bytes() == current_card
    assert all(
        {(row["material_id"], row["document_id"]) for row in inputs["documents"]} == expected_source
        for inputs in app["calls"]
    )
    if corrupt_fingerprint:
        assert len(app["calls"]) == 1, response
        _assert_invalid_without_publication(app, response, before)
    else:
        assert "error" not in response, response
        assert _candidates(response["result"]) == initial_candidates
        assert response["result"]["cards"][0]["cache"] == "hit"
        assert len(app["calls"]) == 1
        assert _state_bytes(app) == before
