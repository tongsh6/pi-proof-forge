"""L5: real confirmation RPC/source flow, with final HTTP and narrow I/O fault injection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.unit.sidecar.test_evidence_inference_lifecycle_rpc import (
    ACTION, BODY, BUNDLE, QUOTE, RESULT,
    app, _card, _career, _candidates, _enabled, _infer, _reference,
    _request, _rpc, _state_bytes, _upload,
)
from tools.infra import evidence_provenance as provenance
from tools.infra.persistence import atomic_io
from tools.infra.persistence.yaml_io import parse_simple_yaml


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stored(app, card):
    return json.loads(_state_bytes(app))["cards"][card["id"]]


def _start(app, card=None):
    card = card or _card(app)
    app["card"] = card
    result = _infer(app)
    candidates = _candidates(result)
    assert candidates
    return card, result["cards"][0], candidates


def _confirm(app, card, candidate, **overrides):
    params = {
        "evidence_id": card["id"], "card_sha256": _sha(card["path"]),
        "candidate_hash": candidate["candidate_hash"], "field": candidate["field"],
        "action": "accept",
    }
    params.update(overrides)
    return _request(app, "evidence.confirmInference", **params)


def _accepted(response):
    assert "error" not in response, response
    assert response["result"]["status"] == "accepted", response
    return response["result"]


def _invalid_unchanged(app, card, response, before_card, before_state):
    assert "error" in response, response
    assert response["error"]["code"] == "VALIDATION_ERROR", response
    assert "result" not in response
    assert card["path"].read_bytes() == before_card
    assert _state_bytes(app) == before_state


def _two_dates(app):
    source = _upload(app, BUNDLE.replace(QUOTE, "2022-04，我负责订单服务改造。\n" + QUOTE))
    card = _card(app, source)
    _enabled(app, False)
    card, row, candidates = _start(app, card)
    assert len(candidates) == 2
    assert all(item["field"] == "time_range" and item["level"] == "L2" for item in candidates)
    assert candidates[0]["value"] != candidates[1]["value"]
    assert not app["calls"]
    return card, row, candidates


@pytest.mark.parametrize("invalid", ("missing_hash", "unknown_hash", "different_field"))
def test_confirmation_requires_exact_candidate_identity(app, invalid):
    card, row, candidates = _start(app)
    candidate = candidates[0]
    params = {
        "evidence_id": card["id"], "card_sha256": row["card_sha256"],
        "candidate_hash": candidate["candidate_hash"], "field": candidate["field"], "action": "accept",
    }
    if invalid == "missing_hash":
        params.pop("candidate_hash")
    elif invalid == "unknown_hash":
        params["candidate_hash"] = "0" * 64
    else:
        params["field"] = "role_scope" if candidate["field"] == "time_range" else "time_range"
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    response = _request(app, "evidence.confirmInference", **params)
    _invalid_unchanged(app, card, response, before_card, before_state)
    assert len(app["calls"]) == 1


@pytest.mark.parametrize("action", ("accept", "reject"))
def test_second_candidate_of_same_field_is_the_one_decided(app, action):
    card, row, candidates = _two_dates(app)
    first, second = candidates
    before_card = card["path"].read_bytes()
    response = _confirm(app, card, second, action=action, card_sha256=row["card_sha256"])
    assert "error" not in response, response
    current = _stored(app, card)
    if action == "accept":
        result = _accepted(response)
        assert result["value"] == second["value"]
        assert result["provenance"]["level"] == "L2"
        assert result["provenance"]["evidence"] == second["evidence"]
        assert parse_simple_yaml(card["path"].read_text())["scalars"]["time_range"] == second["value"]
    else:
        assert response["result"]["candidate_hash"] == second["candidate_hash"]
        assert second["candidate_hash"] in current["rejected"]
        assert first["candidate_hash"] not in current["rejected"]
        assert [item["candidate_hash"] for item in current["candidates"]] == [first["candidate_hash"]]
        assert card["path"].read_bytes() == before_card
    assert not app["calls"]


def test_editing_first_candidate_to_second_value_is_l4_and_retires_remaining(app):
    card, _, candidates = _two_dates(app)
    first, second = candidates
    response = _confirm(app, card, first, value=second["value"])
    result = _accepted(response)
    assert result["value"] == second["value"]
    assert result["provenance"]["level"] == "L4"
    assert result["provenance"]["evidence"] == []
    current = _stored(app, card)
    assert current["candidates"] == []
    assert current["rejected"] == []
    assert not app["calls"]


@pytest.mark.parametrize("order", (("time_range", "role_scope"), ("role_scope", "time_range")))
def test_original_accepts_continue_same_card_with_historical_confirmed_profile(app, order):
    card = _card(app)
    _career(app, reviewed=True)
    card, row, candidates = _start(app, card)
    assert app["calls"][0]["confirmed_work_context"]
    origin = _stored(app, card)
    by_field = {item["field"]: item for item in candidates}
    sha = row["card_sha256"]
    for field in order:
        result = _accepted(_confirm(app, card, by_field[field], card_sha256=sha))
        assert result["provenance"]["level"] == "L3"
        assert result["provenance"]["confirmed_by_user"] is True
        assert result["provenance"]["evidence"] == by_field[field]["evidence"]
        assert result["card_sha256"] != sha
        sha = result["card_sha256"]
        current = _stored(app, card)
        assert current["card_sha256"] == sha
        assert current["attempt_fingerprint"] == origin["attempt_fingerprint"]
        assert current.get("input_basis") == origin.get("input_basis")
        assert _rpc(app, "profile.get")["profile"]["career_status"]["reviewed"] is False
    assert isinstance(origin.get("input_basis"), dict)
    detail = _rpc(app, "evidence.get", evidence_id=card["id"])["evidence"]
    for field in order:
        assert detail[field + "_provenance"]["level"] == "L3"
        assert detail[field + "_provenance"]["evidence"] == by_field[field]["evidence"]
    assert detail["review_decision"] == "pending"
    assert detail["candidate_pool_eligible"] is False
    assert _stored(app, card)["candidates"] == []
    assert len(app["calls"]) == 1


@pytest.mark.parametrize("version", ("stale_client", "fresh_client_with_old_stored_card"))
def test_current_client_card_cannot_authorize_an_old_stored_candidate(app, version):
    card, _, candidates = _start(app)
    if version == "fresh_client_with_old_stored_card":
        _rpc(app, "evidence.update", evidence_id=card["id"], patch={"context": "订单服务已由另一轮编辑更新"})
        client_sha = _sha(card["path"])
        assert _stored(app, card)["card_sha256"] != client_sha
    else:
        client_sha = "0" * 64
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    response = _confirm(app, card, candidates[0], card_sha256=client_sha)
    _invalid_unchanged(app, card, response, before_card, before_state)


@pytest.mark.parametrize("changed", ("copied_source", "reference_source", "material_identity", "root", "uncited_input", "profile"))
def test_accept_rechecks_original_used_inputs_and_current_permission(app, changed):
    card = _card(app)
    reference = None
    peer = None
    if changed in {"reference_source", "material_identity", "root"}:
        reference = _reference(app, "original")
        app["reply_material"] = reference["ref"]["material_id"]
    elif changed == "uncited_input":
        peer = _upload(app, BUNDLE.replace("project/work-log.md", "project/related-note.md"))
    elif changed == "profile":
        _career(app, reviewed=True)
    card, _, candidates = _start(app, card)
    candidate = next(item for item in candidates if item["field"] == "role_scope")
    if reference:
        assert {item["material_id"] for item in candidate["evidence"]} == {reference["ref"]["material_id"]}
    if peer:
        assert peer["ref"]["material_id"] in {item["material_id"] for item in app["calls"][0]["documents"]}
        assert peer["ref"]["material_id"] not in {item["material_id"] for item in candidate["evidence"]}
    if changed == "copied_source":
        card["source"]["path"].write_text(BUNDLE.replace("我负责", "同事负责"))
    elif changed == "reference_source":
        reference["external"].write_text(BODY.replace("我负责", "同事负责"))
    elif changed == "material_identity":
        _rpc(app, "material.reference.remove", material_id=reference["ref"]["material_id"], confirmed=True)
        replacement = _reference(app, "replacement")
        assert replacement["ref"]["document_id"] == reference["ref"]["document_id"]
        assert replacement["ref"]["sha256"] == reference["ref"]["sha256"]
        assert replacement["ref"]["material_id"] != reference["ref"]["material_id"]
    elif changed == "root":
        _rpc(app, "settings.update", section="material_source_roots", payload=[])
    elif changed == "uncited_input":
        peer["path"].write_text(peer["text"].replace("我负责", "同事负责"))
    else:
        assert app["calls"][0]["confirmed_work_context"]
        current = _rpc(app, "profile.get")["profile"]
        career = current["career"]
        career["work"][0]["scope"] = "原确认后发生实际变化的职责范围"
        _rpc(app, "profile.update", expected_revision=current["revision"], patch={"career": career})
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    response = _confirm(app, card, candidate)
    _invalid_unchanged(app, card, response, before_card, before_state)
    assert len(app["calls"]) == 1


def test_unused_material_profile_and_navigation_changes_do_not_block_accept(app):
    card = _card(app, stack=[])
    unused = _upload(app, "# Source: garden/flowers.md\n# 花卉养护\n\n盆栽需要补充水分。\n", label="原始资料")
    _career(app, reviewed=False)
    card, _, candidates = _start(app, card)
    assert app["calls"][0]["confirmed_work_context"] == []
    assert {item["material_id"] for item in app["calls"][0]["documents"]} == {card["source"]["ref"]["material_id"]}
    unused["path"].write_text(unused["text"] + "\n新增花卉记录。\n")
    current = _rpc(app, "profile.get")["profile"]
    career = current["career"]
    career["work"][0]["scope"] = "尚未确认的编辑"
    _rpc(app, "profile.update", expected_revision=current["revision"], patch={"career": career})
    jobs = app["root"] / "job_profiles"
    jobs.mkdir()
    (jobs / "jp_unrelated.yaml").write_text('id: "jp_unrelated"\ntitle: "无关岗位"\n')
    (app["root"] / "knowledge-index" / "index.json").write_text("{broken-navigation")
    result = _accepted(_confirm(app, card, candidates[0]))
    assert result["provenance"]["level"] == "L3"
    assert len(app["calls"]) == 1


def test_editing_a_stale_candidate_cannot_bypass_input_validation(app):
    card, _, candidates = _start(app)
    candidate = next(item for item in candidates if item["field"] == "time_range")
    card["source"]["path"].write_text(BUNDLE.replace("我负责", "同事负责"))
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    response = _confirm(app, card, candidate, value="2021-01")
    _invalid_unchanged(app, card, response, before_card, before_state)


def test_edited_l3_retires_other_candidates_without_rejecting_or_reinferring(app):
    card, _, candidates = _start(app)
    candidate = next(item for item in candidates if item["field"] == "time_range")
    result = _accepted(_confirm(app, card, candidate, value="2021-01"))
    assert result["provenance"]["level"] == "L4"
    assert result["provenance"]["evidence"] == []
    current = _stored(app, card)
    assert current["candidates"] == []
    assert current["rejected"] == []
    assert len(app["calls"]) == 1


@pytest.mark.parametrize("operation", ("accept_l3", "edit_l3", "reject_l3", "accept_l2"))
def test_disabled_inference_allows_withdrawal_and_l2_but_not_l3_accept(app, operation):
    if operation == "accept_l2":
        card, row, candidates = _two_dates(app)
    else:
        card, row, candidates = _start(app)
        _enabled(app, False)
    candidate = candidates[0]
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    overrides = {"card_sha256": row["card_sha256"]}
    if operation == "reject_l3":
        overrides["action"] = "reject"
        card["source"]["path"].write_text(BUNDLE.replace("我负责", "同事负责"))
    elif operation == "edit_l3":
        overrides["value"] = "2021-01"
    response = _confirm(app, card, candidate, **overrides)
    if operation in {"accept_l3", "edit_l3"}:
        _invalid_unchanged(app, card, response, before_card, before_state)
    elif operation == "reject_l3":
        assert "error" not in response, response
        assert response["result"]["candidate_hash"] == candidate["candidate_hash"]
        assert card["path"].read_bytes() == before_card
        assert candidate["candidate_hash"] in _stored(app, card)["rejected"]
    else:
        assert _accepted(response)["provenance"]["level"] == "L2"


@pytest.mark.parametrize("invalid_basis", ("missing", "malformed"))
def test_unverifiable_old_state_requires_explicit_reinfer_and_keeps_rejections(app, invalid_basis):
    card, _, candidates = _start(app)
    rejected = next(item for item in candidates if item["field"] == "role_scope")
    result = _confirm(app, card, rejected, action="reject")
    assert "error" not in result and result["result"]["status"] == "rejected", result
    candidate = next(item for item in candidates if item["field"] == "time_range")
    path = app["root"] / "app-data" / "evidence_inference.json"
    state = json.loads(path.read_bytes())
    # Negative persisted-state fixture: emulate an old or corrupt basis, never approval.
    if invalid_basis == "missing":
        state["cards"][card["id"]].pop("input_basis", None)
    else:
        state["cards"][card["id"]]["input_basis"] = {"invalid": True}
    path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True))
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    response = _confirm(app, card, candidate)
    _invalid_unchanged(app, card, response, before_card, before_state)
    regenerated = _candidates(_infer(app))
    assert regenerated
    assert len(app["calls"]) == 2
    current = _stored(app, card)
    assert rejected["candidate_hash"] in current["rejected"]
    assert all(item["candidate_hash"] != rejected["candidate_hash"] for item in regenerated)
    assert isinstance(current.get("input_basis"), dict)


def _two_cards_with_confirmed_profile(app):
    first = _card(app, stack=[])
    quote = "2023-04，我负责账单核验的差异追踪与结算对账。"
    action = "完成账单差异追踪与结算对账验证。"
    result = "结算对账功能已验收。"
    source = _upload(app, f"# Source: ledger/billing.md\n# 账单核验\n\n{quote}\n{action}\n{result}\n", label="账单核验记录")
    second = _card(app, source, title="账单核验", context="账单差异追踪与结算对账",
                   stack=[], tags=["账单核验"], actions=[action], results=[result],
                   field_sources=[{
                       "field": "actions", "value": action, "quote": action,
                       "material_id": source["ref"]["material_id"],
                       "document_id": source["ref"]["document_id"],
                   }])
    app["card"], app["reply_material"] = first, first["source"]["ref"]["material_id"]
    _career(app, reviewed=False)
    current = _rpc(app, "profile.get")["profile"]
    career = current["career"]
    career["work"][0]["scope"] = "订单与账单的数据处理"
    career["work"][0]["evidence_ids"] = [first["id"], second["id"]]
    career["skills"][0]["evidence_ids"] = [first["id"], second["id"]]
    _rpc(app, "profile.update", expected_revision=current["revision"], patch={"career": career})
    current = _rpc(app, "profile.get")["profile"]
    reviewed = _rpc(app, "profile.review", expected_revision=current["revision"], confirmed=True)["profile"]
    assert reviewed["career_status"]["reviewed"] is True

    def reply_for_card():
        inputs = app["calls"][-1]
        target = first if inputs["card"]["title"] == "订单服务" else second
        app["reply_material"] = target["source"]["ref"]["material_id"]
        app["quote"] = QUOTE if target is first else quote
        app["time"] = "2023-03" if target is first else "2023-04"
        app["role"] = "订单服务接口改造负责人" if target is first else "账单核验与结算对账负责人"

    app["during_call"] = reply_for_card
    response = _rpc(app, "evidence.inferFields", card_ids=[first["id"], second["id"]])
    assert response["status"] == "ok"
    assert len(response["cards"]) == 2 and all(row["candidates"] for row in response["cards"])
    assert len(app["calls"]) == 2
    assert all(inputs["confirmed_work_context"] for inputs in app["calls"])
    assert {item["material_id"] for item in app["calls"][0]["documents"]}.isdisjoint(
        item["material_id"] for item in app["calls"][1]["documents"]
    )
    assert any(
        Path(snapshot["path"]).resolve() == source["path"].resolve()
        and snapshot["sha256"] == _sha(source["path"])
        for snapshot in _stored(app, first)["input_basis"]["snapshots"].values()
    ), "the confirmed profile must actually capture the other card\'s bound source"
    return first, second, {row["card_id"]: row for row in response["cards"]}


@pytest.mark.parametrize("change", ("other_source", "other_confirmation"))
def test_only_target_card_can_use_controlled_confirmation_progress(app, change):
    first, second, rows = _two_cards_with_confirmed_profile(app)
    if change == "other_source":
        target, changed = first, second
        changed["source"]["path"].write_text(changed["source"]["text"].replace("我负责", "同事负责"))
    else:
        target, changed = second, first
        accepted = _accepted(_confirm(app, changed, rows[changed["id"]]["candidates"][0]))
        assert accepted["card_sha256"] != rows[changed["id"]]["card_sha256"]
    before_card, before_state = target["path"].read_bytes(), _state_bytes(app)
    response = _confirm(app, target, rows[target["id"]]["candidates"][0])
    _invalid_unchanged(app, target, response, before_card, before_state)
    assert len(app["calls"]) == 2


@pytest.mark.parametrize("changed", ("source", "card", "state"))
def test_observed_updates_before_confirmation_publication_are_preserved(app, monkeypatch, changed):
    card, row, candidates = _start(app)
    chosen = next(item for item in candidates if item["field"] == "role_scope")
    time = next(item for item in candidates if item["field"] == "time_range")
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    original = provenance.normalize_provenance
    observed = {}

    def normalize_then_change(*args, **kwargs):
        normalized = original(*args, **kwargs)
        if not observed:
            observed["entered"] = True
            if changed == "source":
                path = card["source"]["path"]
                path.write_text(BUNDLE.replace("我负责", "同事负责"))
                observed["path"], observed["bytes"] = path, path.read_bytes()
            elif changed == "card":
                _rpc(app, "evidence.update", evidence_id=card["id"], patch={"context": "并发写入的真实卡上下文"})
                observed["card"] = card["path"].read_bytes()
            else:
                rejected = _confirm(app, card, time, action="reject", card_sha256=row["card_sha256"])
                assert "error" not in rejected and rejected["result"]["status"] == "rejected", rejected
                observed["state"] = _state_bytes(app)
        return normalized

    # Observe the real normalization result; only schedule a real concurrent update here.
    monkeypatch.setattr(provenance, "normalize_provenance", normalize_then_change)
    response = _confirm(app, card, chosen, card_sha256=row["card_sha256"])
    assert observed
    _invalid_unchanged(
        app, card, response, observed.get("card", before_card), observed.get("state", before_state),
    )
    if changed == "source":
        assert observed["path"].read_bytes() == observed["bytes"]
    assert len(app["calls"]) == 1


@pytest.mark.parametrize("failed_write", ("card", "state"))
def test_confirmation_write_failure_preserves_real_persistence_and_blocks_replay(app, monkeypatch, failed_write):
    card, row, candidates = _start(app)
    candidate = candidates[0]
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    target = card["path"] if failed_write == "card" else app["root"] / "app-data" / "evidence_inference.json"
    original_replace = atomic_io.os.replace
    reached = []

    def fail_selected_replace(source, destination, *args, **kwargs):
        if Path(destination).resolve() == target.resolve():
            reached.append(str(destination))
            raise OSError("synthetic atomic replacement failure")
        return original_replace(source, destination, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(atomic_io.os, "replace", fail_selected_replace)
        response = _confirm(app, card, candidate, card_sha256=row["card_sha256"])
    assert "error" in response and "result" not in response, response
    assert reached, "the card and candidate state must use the existing atomic writer"
    assert _state_bytes(app) == before_state
    if failed_write == "card":
        assert card["path"].read_bytes() == before_card
    else:
        written = card["path"].read_bytes()
        assert written != before_card
        detail = _rpc(app, "evidence.get", evidence_id=card["id"])["evidence"]
        assert detail[candidate["field"]] == candidate["value"]
        assert detail["review_decision"] == "pending"
        assert detail["candidate_pool_eligible"] is False
        fresh_sha = _sha(card["path"])
        assert fresh_sha != row["card_sha256"]
        retry = _confirm(app, card, candidate, card_sha256=fresh_sha)
        _invalid_unchanged(app, card, retry, written, before_state)
    assert len(app["calls"]) == 1


@pytest.mark.parametrize("value", ("", " \t\n ", None, 42), ids=("empty", "blank", "null", "number"))
def test_explicit_invalid_confirmation_value_cannot_accept_original_candidate(app, value):
    card, row, candidates = _start(app)
    candidate = next(item for item in candidates if item["field"] == "role_scope")
    assert candidate["level"] == "L3"
    before_card, before_state = card["path"].read_bytes(), _state_bytes(app)
    response = _confirm(app, card, candidate, card_sha256=row["card_sha256"], value=value)
    _invalid_unchanged(app, card, response, before_card, before_state)
    assert len(app["calls"]) == 1


def test_explicit_original_confirmation_value_retains_l3_and_remaining_candidate(app):
    card, row, candidates = _start(app)
    candidate = next(item for item in candidates if item["field"] == "role_scope")
    assert candidate["level"] == "L3" and candidate["value"].strip()
    origin = _stored(app, card)
    result = _accepted(_confirm(
        app, card, candidate, card_sha256=row["card_sha256"], value=candidate["value"],
    ))
    assert result["value"] == candidate["value"]
    assert result["candidate_hash"] == candidate["candidate_hash"]
    assert result["provenance"]["level"] == "L3"
    assert result["provenance"]["evidence"] == candidate["evidence"]
    current = _stored(app, card)
    assert current["candidates"] == [item for item in candidates if item["candidate_hash"] != candidate["candidate_hash"]]
    assert current["rejected"] == origin["rejected"]
    assert current["attempt_fingerprint"] == origin["attempt_fingerprint"]
    assert current["input_basis"] == origin["input_basis"]
    assert len(app["calls"]) == 1
