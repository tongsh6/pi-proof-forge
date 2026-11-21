"""C4/C5：evidence.inferFields / evidence.confirmInference 的候选、落盘与确认语义。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.infra import evidence_inference as inference
from tools.sidecar.handlers import evidence


CARD_YAML = (
    'id: "ec_1"\ntitle: "订单服务"\ntime_range: ""\ncontext: "订单处理与库存同步"\n'
    'role_scope: ""\nstatus: "saved_incomplete"\ncreated_at: "now"\nupdated_at: "now"\n'
    'actions:\n  - "改造订单服务"\nresults:\n  - "库存同步功能上线"\n'
    'stack:\n  - "Java"\ntags:\n  - "订单"\n'
)

INDEX = {"nonfact_materials": [], "materials": {"mat_work": {
    "material_id": "mat_work", "label": "示例公司工作日志", "filename": "mat_work.txt",
    "documents": [{"document_id": "doc_1", "label": "2023-03 周报", "title": "订单服务周报",
                   "source_name": "2023-03-06.md", "sha256": "s1", "dates": {"window": "2023-03"}}]}}}


def _setup(tmp_path, monkeypatch):
    evidence_dir = tmp_path / "evidence_cards"
    evidence_dir.mkdir()
    path = evidence_dir / "ec_1.yaml"
    path.write_text(CARD_YAML, encoding="utf-8")
    (tmp_path / "knowledge-index").mkdir()
    (tmp_path / "knowledge-index" / "index.json").write_text(json.dumps(INDEX), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evidence, "_EVIDENCE_DIR", evidence_dir)
    monkeypatch.setattr(inference, "select_documents", lambda *a, **k: [
        {"material_id": "mat_work", "document_id": "doc_1", "label": "2023-03 周报",
         "title": "订单服务周报", "sha256": "s1", "material_label": "示例公司工作日志",
         "material_filename": "mat_work.txt", "document_dates": {"window": "2023-03"}}])
    monkeypatch.setattr(inference, "read_document_texts", lambda *a, **k: {
        "doc_1": "2023-03-06 周报。我负责订单服务改造，推动库存同步功能上线。"})
    monkeypatch.setattr(inference, "employment_windows", lambda *a, **k: (
        [(2022 * 12 + 2, 999999)], ["2022-02 ~ 至今"]))
    return path


def _fake_llm(prompt: str) -> str:
    return json.dumps({
        "time_range": {"value": "2023-03", "precision": "month", "confidence": 0.7,
                       "evidence": [{"document_id": "doc_1", "excerpt": "我负责订单服务改造"}]},
        "role_scope": {"value": "订单服务改造负责人", "confidence": 0.6,
                       "evidence": [{"document_id": "doc_1", "excerpt": "我负责订单服务改造"}]},
    }, ensure_ascii=False)


def test_infer_fields_produces_candidates_and_confirms_keeps_l3(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "_inference_llm_call", _fake_llm)
    monkeypatch.setattr(evidence, "load_evidence_inference_enabled", lambda: True)
    result = evidence.handle_evidence_infer_fields({"meta": {"correlation_id": "c"}, "card_ids": ["ec_1"]})
    assert result["status"] == "ok"
    assert result["summary"]["candidates"] == 2
    assert (tmp_path / "app-data" / "evidence_inference.json").is_file()
    card_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    time_candidate = next(item for item in result["cards"][0]["candidates"] if item["field"] == "time_range")
    accepted = evidence.handle_evidence_confirm_inference({
        "meta": {"correlation_id": "c"}, "evidence_id": "ec_1", "card_sha256": card_sha,
        "field": "time_range", "action": "accept"})
    assert accepted["status"] == "accepted"
    assert accepted["provenance"]["level"] == "L3" and accepted["provenance"]["confirmed_by_user"] is True
    detail = evidence._load_evidence_detail("ec_1")
    assert detail["time_range"] == "2023-03"
    assert detail["time_range_provenance"]["level"] == "L3"
    assert detail["time_range_provenance"]["confirmed_by_user"] is True
    assert detail["review_decision"] == "pending"
    state = inference.load_state(tmp_path)
    assert all(item["candidate_hash"] != time_candidate["candidate_hash"]
               for item in state["cards"]["ec_1"]["candidates"])


def test_reject_prevents_renomination_and_modified_accept_becomes_l4(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "_inference_llm_call", _fake_llm)
    monkeypatch.setattr(evidence, "load_evidence_inference_enabled", lambda: True)
    first = evidence.handle_evidence_infer_fields({"meta": {"correlation_id": "c"}, "card_ids": ["ec_1"]})
    role_candidate = next(item for item in first["cards"][0]["candidates"] if item["field"] == "role_scope")
    card_sha = hashlib.sha256((tmp_path / "evidence_cards" / "ec_1.yaml").read_bytes()).hexdigest()
    rejected = evidence.handle_evidence_confirm_inference({
        "meta": {"correlation_id": "c"}, "evidence_id": "ec_1", "card_sha256": card_sha,
        "field": "role_scope", "action": "reject"})
    assert rejected["status"] == "rejected"
    second = evidence.handle_evidence_infer_fields({"meta": {"correlation_id": "c"}, "card_ids": ["ec_1"]})
    role_after = [item for item in second["cards"][0]["candidates"] if item["field"] == "role_scope"]
    assert role_after == []
    # 手工修改值后接受：不再沿用 L3，记 L4 本人陈述。
    card_sha = hashlib.sha256((tmp_path / "evidence_cards" / "ec_1.yaml").read_bytes()).hexdigest()
    state = inference.load_state(tmp_path)
    time_candidate = next(item for item in state["cards"]["ec_1"]["candidates"] if item["field"] == "time_range")
    accepted = evidence.handle_evidence_confirm_inference({
        "meta": {"correlation_id": "c"}, "evidence_id": "ec_1", "card_sha256": card_sha,
        "field": "time_range", "action": "accept", "value": "2023-01 ~ 2023-06"})
    assert accepted["provenance"]["level"] == "L4"
    assert accepted["value"] == "2023-01 ~ 2023-06"
    assert time_candidate["level"] == "L3"


def test_confirm_rejects_stale_card_and_invalid_field(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "_inference_llm_call", _fake_llm)
    monkeypatch.setattr(evidence, "load_evidence_inference_enabled", lambda: True)
    evidence.handle_evidence_infer_fields({"meta": {"correlation_id": "c"}, "card_ids": ["ec_1"]})
    with pytest.raises(ValueError, match="evidence_inference_stale"):
        evidence.handle_evidence_confirm_inference({
            "meta": {"correlation_id": "c"}, "evidence_id": "ec_1", "card_sha256": "0" * 64,
            "field": "time_range", "action": "accept"})
    with pytest.raises(ValueError, match="evidence_inference_field_invalid"):
        evidence.handle_evidence_confirm_inference({
            "meta": {"correlation_id": "c"}, "evidence_id": "ec_1", "card_sha256": "0" * 64,
            "field": "results", "action": "accept"})


@pytest.mark.parametrize("order", [("time_range","role_scope"),("role_scope","time_range")])
def test_sequential_field_confirmation_preserves_both_provenance_records(tmp_path,monkeypatch,order):
    path=_setup(tmp_path,monkeypatch)
    monkeypatch.setattr(evidence,"_inference_llm_call",_fake_llm)
    monkeypatch.setattr(evidence,"load_evidence_inference_enabled",lambda:True)
    evidence.handle_evidence_infer_fields({"meta":{"correlation_id":"c"},"card_ids":["ec_1"]})
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    for field in order:
        result=evidence.handle_evidence_confirm_inference({
            "meta":{"correlation_id":"c"},"evidence_id":"ec_1","card_sha256":sha,"field":field,"action":"accept"})
        assert result["card_sha256"]!=sha
        sha=result["card_sha256"]
    detail=evidence._load_evidence_detail("ec_1")
    for field in order:
        assert detail[field+"_provenance"]["level"]=="L3"
        assert detail[field+"_provenance"]["confirmed_by_user"] is True
        assert detail[field+"_provenance"]["evidence"]
    assert detail["review_decision"]=="pending"
    assert detail["candidate_pool_eligible"] is False


def test_inference_disabled_returns_rules_only_l2(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "load_evidence_inference_enabled", lambda: False)
    result = evidence.handle_evidence_infer_fields({"meta": {"correlation_id": "c"}, "card_ids": ["ec_1"]})
    assert result["status"] == "ok" and result["enabled"] is False
    candidates = result["cards"][0]["candidates"]
    assert candidates and all(item["level"] == "L2" for item in candidates)
    assert result["cards"][0]["status"] == "rules_only"

@pytest.mark.parametrize(
    "provider,base_url,mode,expected_protocol",
    [
        ("openai_compatible", "https://api.example.test/proxy/localhost/v1", None, {}),
        ("openai_compatible", "http://127.0.0.1:9000/v1", None, {}),
        ("deepseek", "http://127.0.0.1:9000/v1", False, {"thinking": {"type": "disabled"}}),
        ("openai_compatible", "http://127.0.0.1:8000/v1", False, {"reasoning_effort": "none"}),
        ("strata", "http://127.0.0.1:47831/v1", False, {"reasoning_effort": "none"}),
    ],
    ids=["remote-path-localhost", "unknown-loopback", "deepseek-off-loopback", "splash-explicit-off", "strata-off"],
)
def test_inference_request_uses_shared_provider_adapter(tmp_path, monkeypatch, provider, base_url, mode, expected_protocol):
    import io

    from tools.sidecar.handlers import evidence_inference as handler

    path = _setup(tmp_path, monkeypatch)
    original = path.read_bytes()
    monkeypatch.setattr(evidence, "load_evidence_inference_enabled", lambda: True)
    monkeypatch.setattr(handler, "load_llm_config", lambda: {
        "provider": provider, "base_url": base_url, "api_key_for_request": "synthetic",
        "model": "synthetic-model", "timeout": 5, "thinking_enabled": mode,
        "thinking_effort": "high",
    })
    requests = []

    def open_response(request, **kwargs):
        requests.append(request)
        payload = json.loads(request.data)
        prompt = next(message["content"] for message in payload["messages"] if message["role"] == "user")
        response = {"choices": [{"message": {"content": _fake_llm(prompt)}, "finish_reason": "stop"}]}
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", open_response)
    result = evidence.handle_evidence_infer_fields({
        "meta": {"correlation_id": "provider-wire"}, "card_ids": ["ec_1"],
    })
    assert result["status"] == "ok" and result["summary"]["candidates"] == 2
    assert path.read_bytes() == original
    assert len(requests) == 1
    assert requests[0].full_url == base_url + "/chat/completions"
    payload = json.loads(requests[0].data)
    assert payload["response_format"] == {"type": "json_object"}
    actual_protocol = {key: payload[key] for key in ("reasoning_effort", "thinking") if key in payload}
    assert actual_protocol == expected_protocol
