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
    'id: "ec_1"\ntitle: "统一运动中心"\ntime_range: ""\ncontext: "会员中心活动报名"\n'
    'role_scope: ""\nstatus: "saved_incomplete"\ncreated_at: "now"\nupdated_at: "now"\n'
    'actions:\n  - "改造会员中心"\nresults:\n  - "活动报名聚合上线"\n'
    'stack:\n  - "Java"\ntags:\n  - "会员"\n'
)

INDEX = {"nonfact_materials": [], "materials": {"mat_work": {
    "material_id": "mat_work", "label": "EC+ 工作日志", "filename": "mat_work.txt",
    "documents": [{"document_id": "doc_1", "label": "2023-03 周报", "title": "统一运动中心周报",
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
         "title": "统一运动中心周报", "sha256": "s1", "material_label": "EC+ 工作日志",
         "material_filename": "mat_work.txt", "document_dates": {"window": "2023-03"}}])
    monkeypatch.setattr(inference, "read_document_texts", lambda *a, **k: {
        "doc_1": "2023-03-06 周报。我负责统一运动中心改造，推动活动报名聚合上线。"})
    monkeypatch.setattr(inference, "employment_windows", lambda *a, **k: (
        [(2021 * 12 + 3, 999999)], ["2021-03 ~ 至今"]))
    return path


def _fake_llm(prompt: str) -> str:
    return json.dumps({
        "time_range": {"value": "2023-03", "precision": "month", "confidence": 0.7,
                       "evidence": [{"document_id": "doc_1", "excerpt": "我负责统一运动中心改造"}]},
        "role_scope": {"value": "会员中心改造负责人", "confidence": 0.6,
                       "evidence": [{"document_id": "doc_1", "excerpt": "我负责统一运动中心改造"}]},
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


def test_inference_disabled_returns_rules_only_l2(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "load_evidence_inference_enabled", lambda: False)
    result = evidence.handle_evidence_infer_fields({"meta": {"correlation_id": "c"}, "card_ids": ["ec_1"]})
    assert result["status"] == "ok" and result["enabled"] is False
    candidates = result["cards"][0]["candidates"]
    assert candidates and all(item["level"] == "L2" for item in candidates)
    assert result["cards"][0]["status"] == "rules_only"
