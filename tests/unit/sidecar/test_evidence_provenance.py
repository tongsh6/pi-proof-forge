"""C1–C3：证据卡 provenance 读写、单文档元数据推断与手工修改降级。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.sidecar.handlers import evidence


SELECTED = [{"material_id": "mat_1", "label": "工作日志/2023-08-15.md", "filename": "mat_1.txt",
             "extension": ".md", "path": Path("mat_1.txt")}]

METADATA = {
    "keys": {"filename_date:2023-08-15", "employment_window:2021-03 ~ 至今"},
    "windows": [(2021 * 12 + 3, 999999)],
    "values": {"filename_dates": ["2023-08-15"], "employment_window": ["2021-03 ~ 至今"]},
    "text": "# Document metadata\n{}",
}


def _parsed(**overrides):
    base = {
        "source_material_ids": ["mat_1"],
        "title": "统一运动中心改造",
        "context": "会员中心活动报名链路复杂。",
        "actions": ["我负责统一运动中心改造，推动活动报名聚合"],
        "results": ["我推动统一运动中心改造上线"],
        "artifacts": [{"type": "text_document", "ref": "mat_1", "label": "工作日志"}],
        "stack": ["Java"],
        "tags": ["会员"],
    }
    base.update(overrides)
    return base


def test_build_draft_accepts_l2_metadata_time_and_l1_role():
    draft = evidence._build_evidence_draft(
        _parsed(
            time_range="2023-08",
            time_range_provenance={"level": "L2", "precision": "month", "confidence": 0.7,
                                   "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "key": "filename_date:2023-08-15"}]},
            role_scope="活动报名聚合负责人",
            role_scope_provenance={"level": "L1", "confidence": 0.8,
                                   "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "excerpt": "我负责统一运动中心改造"}]},
        ),
        SELECTED,
        metadata=METADATA,
        source_text="2023-08 工作日志。我负责统一运动中心改造，推动活动报名聚合上线。",
    )
    assert draft["time_range_provenance"]["level"] == "L2"
    assert draft["role_scope_provenance"]["level"] == "L1"
    assert "provenance_warnings" not in draft


def test_build_draft_drops_unverifiable_or_contradictory_candidates():
    draft = evidence._build_evidence_draft(
        _parsed(
            time_range="2019",
            time_range_provenance={"level": "L3", "confidence": 0.6,
                                   "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "excerpt": "原文没有这句"}]},
            role_scope="平台负责人",
            role_scope_provenance={"level": "L2", "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "key": "filename_date:2023-08-15"}]},
        ),
        SELECTED,
        metadata=METADATA,
        source_text="2023-08 工作日志。我负责统一运动中心改造。",
    )
    assert "time_range_provenance" not in draft
    assert "role_scope_provenance" not in draft
    warnings = draft.get("provenance_warnings", [])
    assert any("time_range" in item for item in warnings)
    assert any("role_scope" in item for item in warnings)


def test_prompt_injects_metadata_and_level_rules():
    prompt = evidence._llm_draft_prompt("# Material mat_1\n正文", METADATA["text"])
    assert "Document metadata" in prompt
    assert "time_range_provenance" in prompt and "role_scope_provenance" in prompt
    assert "L1" in prompt and "L2" in prompt and "excerpt" in prompt
    assert "Never infer ownership" in prompt


def test_write_and_load_roundtrip_keeps_provenance(tmp_path):
    provenance = {"level": "L3", "confidence": 0.62, "evidence": [
        {"material_id": "mat_1", "document_id": "doc_1", "excerpt": "我推动统一运动中心改造"}]}
    fields = {
        "id": "ec_1", "title": "统一运动中心", "time_range": "2023-03 ~ 2023-09",
        "context": "活动报名", "role_scope": "推动者", "status": "saved_incomplete",
        "created_at": "now", "updated_at": "now", "actions": ["改造"], "results": ["上线"],
        "stack": [], "artifacts": [], "tags": [],
        "time_range_provenance_json": json.dumps(provenance, ensure_ascii=False),
    }
    evidence._write_evidence_file(tmp_path / "ec_1.yaml", fields)
    with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", tmp_path):
        detail = evidence._load_evidence_detail("ec_1")
        cards = evidence._load_evidence_cards()
    assert detail["time_range_provenance"]["level"] == "L3"
    assert detail["time_range_provenance"]["evidence"][0]["excerpt"] == "我推动统一运动中心改造"
    assert cards[0]["time_range_level"] == "L3"
    assert cards[0]["role_scope_level"] == "L1"


def _card_yaml(provenance_json: str = "") -> str:
    return (
        'id: "ec_1"\ntitle: "统一运动中心"\ntime_range: "2023-03 ~ 2023-09"\n'
        'context: "活动报名"\nrole_scope: "负责人"\nstatus: "saved_incomplete"\n'
        'created_at: "now"\nupdated_at: "now"\n'
        f'time_range_provenance_json: {json.dumps(provenance_json) if provenance_json else "\"\""}\n'
        'actions:\n  - "改造"\nresults:\n  - "上线"\n'
    )


def test_manual_time_edit_downgrades_to_l4_and_explicit_provenance_is_kept(tmp_path):
    path = tmp_path / "ec_1.yaml"
    original = {"level": "L2", "precision": "month", "confidence": 0.7,
                "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "key": "filename_date:2023-08-15"}]}
    path.write_text(_card_yaml(json.dumps(original, ensure_ascii=False)), encoding="utf-8")
    with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", tmp_path):
        evidence.handle_evidence_update({"meta": {"correlation_id": "c"}, "evidence_id": "ec_1",
                                         "patch": {"time_range": "2023-01 ~ 2023-06"}})
        detail = evidence._load_evidence_detail("ec_1")
    assert detail["time_range_provenance"]["level"] == "L4"
    assert detail["time_range_provenance"]["confirmed_by_user"] is True

    path.write_text(_card_yaml(json.dumps(original, ensure_ascii=False)), encoding="utf-8")
    explicit = {"level": "L2", "precision": "year", "confidence": 0.6,
                "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "key": "first_heading_date:2023-08-14"}]}
    with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", tmp_path):
        evidence.handle_evidence_update({"meta": {"correlation_id": "c"}, "evidence_id": "ec_1",
                                         "patch": {"role_scope": "推动者", "role_scope_provenance": explicit}})
        detail = evidence._load_evidence_detail("ec_1")
    assert detail["role_scope_provenance"]["level"] == "L2"
    assert detail["role_scope"] == "推动者"
