"""C4/C6：跨文档检索、规则聚合、L3 候选校验、缓存与规则 L2 线索。"""
from __future__ import annotations

import json
from pathlib import Path

from tools.infra import evidence_inference as inference


def make_index():
    return {
        "nonfact_materials": [{"material_id": "mat_fixture"}],
        "materials": {
            "mat_work": {
                "material_id": "mat_work", "label": "EC+ 工作日志", "filename": "mat_work.txt",
                "documents": [
                    {"document_id": "doc_1", "label": "2023-03 周报", "title": "统一运动中心周报",
                     "source_name": "2023-03-06.md", "sha256": "s1", "dates": {"window": "2023-03"}},
                    {"document_id": "doc_2", "label": "2023-08 周报", "title": "统一运动中心上线复盘",
                     "source_name": "2023-08-15.md", "sha256": "s2", "dates": {}},
                ],
            },
            "mat_design": {
                "material_id": "mat_design", "label": "设计/实施计划（非完成证明）", "filename": "mat_design.txt",
                "documents": [{"document_id": "doc_design", "label": "统一运动中心设计", "title": "统一运动中心",
                               "source_name": "design.md", "sha256": "sd", "dates": {}}],
            },
            "mat_fixture": {
                "material_id": "mat_fixture", "label": "合成测试夹具", "filename": "mat_fixture.txt",
                "documents": [{"document_id": "doc_fixture", "label": "统一运动中心", "title": "统一运动中心",
                               "source_name": "fixture.md", "sha256": "sf", "dates": {}}],
            },
        },
    }


CARD_FIELDS = {"title": "统一运动中心", "context": "会员中心活动报名链路"}
CARD_LISTS = {"tags": ["会员"], "stack": ["Java"]}


def test_select_documents_ranks_matches_and_excludes_design_and_fixture():
    documents = inference.select_documents(make_index(), CARD_FIELDS, CARD_LISTS)
    ids = [document["document_id"] for document in documents]
    assert ids[:2] == ["doc_1", "doc_2"]
    assert "doc_design" not in ids and "doc_fixture" not in ids


def test_aggregate_documents_extracts_dates_and_first_person_statements():
    texts = {
        "doc_1": "2023-03-06 周报。我负责统一运动中心改造，推动活动报名聚合。我参与会员中心联调。",
        "doc_2": "2023-08-15 上线复盘。我主导统一运动中心上线，完成报名链路重构。",
    }
    documents = [{"material_id": "mat_work", "document_id": "doc_1", "label": "2023-03 周报",
                  "title": "统一运动中心周报", "sha256": "s1", "material_label": "EC+ 工作日志",
                  "document_dates": {"window": "2023-03"}},
                 {"material_id": "mat_work", "document_id": "doc_2", "label": "2023-08 周报",
                  "title": "统一运动中心上线复盘", "sha256": "s2", "material_label": "EC+ 工作日志",
                  "document_dates": {}}]
    aggregates = inference.aggregate_documents(documents, texts)
    assert aggregates[0]["owner_hits"] == 1 and aggregates[0]["participant_hits"] == 1
    assert "2023-03" in aggregates[0]["dates"] and "2023-03-06" in aggregates[0]["dates"]
    assert any("我负责统一运动中心改造" in snippet for snippet in aggregates[0]["snippets"])


def test_parse_candidates_validates_window_and_readable_excerpts():
    texts = {"doc_1": "2023-03-06 我负责统一运动中心改造，推动活动报名聚合上线。",
             "doc_2": "2023-08-15 我主导统一运动中心上线。"}
    aggregates = [
        {"material_id": "mat_work", "document_id": "doc_1", "label": "2023-03 周报", "sha256": "s1",
         "owner_hits": 1, "participant_hits": 0, "snippets": []},
        {"material_id": "mat_work", "document_id": "doc_2", "label": "2023-08 周报", "sha256": "s2",
         "owner_hits": 1, "participant_hits": 0, "snippets": []},
    ]
    windows = [(2021 * 12 + 3, 999999)]
    payload = {
        "time_range": {"value": "2023-03 ~ 2023-08", "precision": "month", "confidence": 0.7,
                       "evidence": [{"security": "x", "document_id": "doc_1", "excerpt": "我负责统一运动中心改造"},
                                    {"document_id": "doc_2", "excerpt": "原文没有这句"}]},
        "role_scope": {"value": "统一运动中心负责人", "confidence": 0.6,
                       "evidence": [{"document_id": "doc_2", "excerpt": "我主导统一运动中心上线"}]},
    }
    candidates = inference.parse_inference_candidates(json.dumps(payload, ensure_ascii=False),
                                                      aggregates=aggregates, texts=texts, windows=windows)
    time_candidate = next(item for item in candidates if item["field"] == "time_range")
    role_candidate = next(item for item in candidates if item["field"] == "role_scope")
    assert time_candidate["level"] == "L3" and len(time_candidate["evidence"]) == 1
    assert role_candidate["first_person_hits"] == {"owner": 1, "participant": 0}
    outside = dict(payload)
    outside["time_range"] = {"value": "2019-01 ~ 2019-06", "confidence": 0.9,
                             "evidence": [{"document_id": "doc_1", "excerpt": "我负责统一运动中心改造"}]}
    assert [item for item in inference.parse_inference_candidates(json.dumps(outside), aggregates=aggregates,
                                                                texts=texts, windows=windows)
            if item["field"] == "time_range"] == []


def test_rules_only_candidates_are_l2_and_within_window():
    aggregates = [{"material_id": "mat_work", "document_id": "doc_1", "sha256": "s1",
                   "dates": ["2023-03", "2019-01"]}]
    candidates = inference.rules_only_candidates(aggregates, [(2021 * 12 + 3, 999999)])
    assert len(candidates) == 1
    assert candidates[0]["level"] == "L2" and candidates[0]["value"] == "2023-03"
    assert candidates[0]["evidence"][0]["key"] == "document_date:2023-03"


def test_infer_card_caches_and_filters_rejected_candidates(tmp_path, monkeypatch):
    root = tmp_path
    monkeypatch.setattr(inference, "select_documents", lambda *a, **k: [
        {"material_id": "mat_work", "document_id": "doc_1", "label": "周报", "title": "统一运动中心",
         "sha256": "s1", "material_label": "工作日志", "material_filename": "mat_work.txt", "document_dates": {}}])
    monkeypatch.setattr(inference, "read_document_texts", lambda *a, **k: {"doc_1": "2023-03 我负责统一运动中心改造上线。"})
    monkeypatch.setattr(inference, "employment_windows", lambda *a, **k: ([(2021 * 12 + 3, 999999)], ["2021-03 ~ 至今"]))
    payload = {"time_range": {"value": "2023-03", "confidence": 0.7,
                              "evidence": [{"document_id": "doc_1", "excerpt": "我负责统一运动中心改造上线"}]},
               "role_scope": {}}
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return json.dumps(payload, ensure_ascii=False)

    first = inference.infer_card(root=root, index={}, card_id="ec_1", card_sha256="sha1",
                                 card_fields={"title": "统一运动中心", "context": ""}, card_lists={},
                                 enabled=True, llm_call=llm)
    assert first["cache"] == "miss" and len(calls) == 1 and len(first["candidates"]) == 1
    second = inference.infer_card(root=root, index={}, card_id="ec_1", card_sha256="sha1",
                                  card_fields={"title": "统一运动中心", "context": ""}, card_lists={},
                                  enabled=True, llm_call=llm)
    assert second["cache"] == "hit" and len(calls) == 1
    state = inference.load_state(root)
    state["cards"]["ec_1"]["rejected"] = [first["candidates"][0]["candidate_hash"]]
    inference.save_state(root, state)
    third = inference.infer_card(root=root, index={}, card_id="ec_1", card_sha256="sha1",
                                 card_fields={"title": "统一运动中心", "context": ""}, card_lists={},
                                 enabled=True, llm_call=llm)
    assert third["cache"] == "hit" and third["candidates"] == []


def test_infer_card_disabled_returns_rules_only(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "select_documents", lambda *a, **k: [
        {"material_id": "mat_work", "document_id": "doc_1", "label": "2023-03 周报", "title": "统一运动中心",
         "sha256": "s1", "material_label": "工作日志", "material_filename": "mat_work.txt",
         "document_dates": {"window": "2023-03"}}])
    monkeypatch.setattr(inference, "read_document_texts", lambda *a, **k: {"doc_1": "2023-03 我负责统一运动中心改造。"})
    monkeypatch.setattr(inference, "employment_windows", lambda *a, **k: ([(2021 * 12 + 3, 999999)], ["2021-03 ~ 至今"]))
    result = inference.infer_card(root=tmp_path, index={}, card_id="ec_1", card_sha256="sha1",
                                  card_fields={"title": "统一运动中心", "context": ""}, card_lists={},
                                  enabled=False, llm_call=lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))
    assert result["status"] == "rules_only"
    assert result["candidates"] and result["candidates"][0]["level"] == "L2"
