"""C1/C2：证据字段 provenance 结构、等级与推断校验。"""
from __future__ import annotations

import pytest

from tools.infra import evidence_provenance as prov


def test_normalize_l1_l2_l3_l4_and_invalid():
    l1 = prov.normalize_provenance(
        {"level": "L1", "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "excerpt": "2023 年我负责统一运动中心"}]},
        field="time_range",
    )
    assert l1["level"] == "L1" and l1["precision"] == "month" and l1["evidence"][0]["excerpt"]
    l2 = prov.normalize_provenance(
        {"level": "L2", "precision": "year", "confidence": 1.7,
         "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "key": "filename_date:2023-08-15"}]},
        field="time_range",
    )
    assert l2["level"] == "L2" and l2["precision"] == "year" and l2["confidence"] == 1.0
    l3 = prov.normalize_provenance(
        {"level": "L3", "confidence": 0.62,
         "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "excerpt": "我推动统一运动中心改造"}],
         "first_person_hits": {"owner": 7, "participant": 2}},
        field="role_scope",
    )
    assert l3["level"] == "L3" and l3["first_person_hits"] == {"owner": 7, "participant": 2}
    l4 = prov.normalize_provenance({"level": "L4", "evidence": []}, field="role_scope")
    assert l4["level"] == "L4" and l4["confirmed_by_user"] is True
    assert prov.normalize_provenance({"level": "L5"}, field="time_range") is None
    assert prov.normalize_provenance({"level": "L2", "evidence": []}, field="time_range") is None
    assert prov.normalize_provenance({"level": "L1", "evidence": [{"material_id": "m", "document_id": "d"}]}, field="time_range") is None
    assert prov.normalize_provenance({"level": "L3", "evidence": [{"material_id": "m", "document_id": "d", "excerpt": "x"}]}, field="unsupported") is None


def test_field_level_defaults_old_cards_to_l1_or_l5():
    assert prov.field_level({"time_range": "2023-03 ~ 2023-09"}, "time_range") == "L1"
    assert prov.field_level({"time_range": ""}, "time_range") == "L5"
    assert prov.field_level({"role_scope": "负责人"}, "role_scope") == "L1"
    card = {"time_range": "2023-03", "time_range_provenance_json": '{"level":"L2","evidence":[{"material_id":"m","document_id":"d","key":"filename"}]}'}
    assert prov.field_level(card, "time_range") == "L2"
    assert prov.field_provenance(card, "role_scope") is None


def test_period_bounds_and_employment_window():
    assert prov.period_bounds("2023-03 ~ 2023-09") == (2023 * 12 + 3, 2023 * 12 + 9)
    assert prov.period_bounds("2023")[0] == 2023 * 12 + 1
    windows = [(2021 * 12 + 3, 2024 * 12 + 3)]
    assert prov.within_windows("2023-03 ~ 2023-09", windows) is True
    assert prov.within_windows("2019-01 ~ 2019-06", windows) is False
    assert prov.within_windows("2023", [(2021 * 12 + 3, 2023 * 12 + 12)]) is True


def test_candidate_evidence_must_be_readable_or_metadata_keyed():
    provenance = {"evidence": [{"material_id": "m", "document_id": "d", "excerpt": "连续出现该项目"}]}
    assert prov.candidate_evidence_readable(provenance, metadata_keys=set(), source_text="周报里连续出现该项目三个月") is True
    assert prov.candidate_evidence_readable(provenance, metadata_keys=set(), source_text="完全无关") is False
    keyed = {"evidence": [{"material_id": "m", "document_id": "d", "key": "filename_date:2023-08-15"}]}
    assert prov.candidate_evidence_readable(keyed, metadata_keys={"filename_date:2023-08-15"}, source_text="") is True
    assert prov.candidate_evidence_readable(keyed, metadata_keys=set(), source_text="") is False


def test_provenance_json_roundtrip():
    normalized = prov.normalize_provenance(
        {"level": "L2", "evidence": [{"material_id": "m", "document_id": "d", "key": "modified_at"}]},
        field="time_range",
    )
    encoded = prov.provenance_json(normalized)
    assert '"L2"' in encoded
    assert prov.provenance_json(None) == ""


def test_evidence_inference_toggle_policy_roundtrip(tmp_path):
    from tools.policy.exclusions import load_evidence_inference_enabled, save_evidence_inference_enabled

    path = tmp_path / "policy.local.yaml"
    assert load_evidence_inference_enabled(path) is True
    save_evidence_inference_enabled(False, path)
    assert load_evidence_inference_enabled(path) is False
    save_evidence_inference_enabled(True, path)
    assert load_evidence_inference_enabled(path) is True
