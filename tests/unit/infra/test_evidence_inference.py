"""C4/C6：跨文档检索、规则聚合、L3 候选校验、缓存与规则 L2 线索。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("raw,expected", [
    ("主导或深度参与方案设计与核心开发（L3 默认归因候选）","主导或深度参与方案设计与核心开发"),
    ("L3 技术负责人","L3 技术负责人"),
])
def test_role_value_separates_work_description_from_candidate_annotation(raw,expected):
    text="主导或深度参与方案设计与核心开发"
    aggregates=[{"material_id":"m","document_id":"d","sha256":"s","owner_hits":0,"participant_hits":0}]
    content=json.dumps({"role_scope":{"value":raw,"confidence":0.8,
                                    "evidence":[{"document_id":"d","excerpt":text}]}})
    candidates=inference.parse_inference_candidates(content,aggregates=aggregates,texts={"d":text},windows=[])
    assert candidates[0]["value"]==expected
    assert candidates[0]["level"]=="L3"
    assert candidates[0]["evidence"][0]["excerpt"]==text


def test_select_documents_ranks_matches_and_excludes_design_and_fixture():
    documents = inference.select_documents(make_index(), CARD_FIELDS, CARD_LISTS)
    ids = [document["document_id"] for document in documents]
    assert ids[:2] == ["doc_1", "doc_2"]
    assert "doc_design" not in ids and "doc_fixture" not in ids


def test_bound_source_and_project_title_precede_generic_context_matches():
    index=make_index()
    index["materials"]["mat_work"]["documents"]=[
        {"document_id":"source","label":"原始记录","title":"原始记录","sha256":"bound"},
        {"document_id":"related","label":"售后服务上线复盘","title":"售后服务","sha256":"related"},
        {"document_id":"noise","label":"会员消息优惠券订单聚合装配鉴权事务补偿",
         "title":"会员消息优惠券订单聚合装配鉴权事务补偿","sha256":"noise"},
    ]
    fields={"title":"售后服务","context":"会员消息优惠券订单聚合装配鉴权事务补偿",
            "source_documents_json":json.dumps([{"material_id":"mat_work","document_id":"source","sha256":"bound"}])}
    docs=inference.select_documents(index,fields,{},limit=2)
    assert [d["document_id"] for d in docs]==["source","related"]
    fields["source_documents_json"]=json.dumps([{"material_id":"mat_work","document_id":"source","sha256":"stale"}])
    assert inference.select_documents(index,fields,{},limit=1)[0]["document_id"]=="related"


def test_bound_sources_do_not_override_design_or_fixture_exclusion():
    fields={**CARD_FIELDS,"source_documents_json":json.dumps([
        {"material_id":"mat_design","document_id":"doc_design","sha256":"sd"},
        {"material_id":"mat_fixture","document_id":"doc_fixture","sha256":"sf"},
    ])}
    ids=[d["document_id"] for d in inference.select_documents(make_index(),fields,CARD_LISTS)]
    assert "doc_design" not in ids and "doc_fixture" not in ids


def test_participation_signals_require_a_first_person_subject():
    docs=[{"material_id":"mat_work","document_id":"doc_1","label":"售后记录","title":"售后记录"}]
    texts={"doc_1":"未知计划量不能参与确定性比例计算。系统支持物流回调和协同回写。"
                   "我参与售后服务接口联调。本人配合售后维修流程验收。"}
    result=inference.aggregate_documents(docs,texts)[0]
    assert result["participant_hits"]==2
    assert result["snippets"]==["我参与售后服务接口联调","本人配合售后维修流程验收"]


def test_context_without_first_person_is_available_to_the_model_and_bounded():
    text="个人工作汇总\n角色：后端负责人\n2023 年负责售后服务状态机设计与上线。\n"+"背景说明"*600
    docs=[{"material_id":"mat_work","document_id":"doc_1","label":"个人工作汇总","title":"售后服务"}]
    aggregates=inference.aggregate_documents(docs,{"doc_1":text})
    prompt=inference.build_inference_prompt(CARD_FIELDS,CARD_LISTS,aggregates,[],[])
    payload=json.loads(prompt.split("INPUT JSON:\n",1)[1])
    document=payload["documents"][0]
    assert "角色：后端负责人" in document["context_excerpt"]
    assert "2023 年负责售后服务状态机设计与上线" in document["context_excerpt"]
    assert document["context_excerpt"] in text
    assert len(document["context_excerpt"])<=1000
    assert document["excerpt_truncated"] is True
    assert document["owner_hits"]==0


def test_bound_material_personal_summary_is_not_lost_to_generic_documents():
    index=make_index()
    documents=index["materials"]["mat_work"]["documents"]
    documents.append({"document_id":"summary","title":"个人工作总结","label":"工作汇总",
                      "sha256":"summary","person_doc":True})
    fields={**CARD_FIELDS,"source_documents_json":json.dumps([
        {"material_id":"mat_work","document_id":"doc_1","sha256":"s1"}])}
    selected=inference.select_documents(index,fields,CARD_LISTS,limit=2)
    assert [d["document_id"] for d in selected]==["doc_1","summary"]


def test_inference_receives_only_linked_confirmed_work_context_and_invalidates_cache(tmp_path,monkeypatch):
    from tools.prompts import context
    profile={"career_status":{"reviewed":True},"career":{"work":[
        {"id":"work1","company":"公司甲","title":"后端负责人","start":"2021-03","current":True,
         "scope":"售后服务与订单系统","contributions":["负责售后服务状态机设计"],"evidence_ids":["ec1"]},
        {"id":"work2","company":"无关公司","title":"研究员","evidence_ids":["other"]},
    ]}}
    monkeypatch.setattr(inference,"load_career_profile",lambda _:profile)
    monkeypatch.setattr(inference,"select_documents",lambda *a,**k:[])
    monkeypatch.setattr(inference,"read_document_texts",lambda *a,**k:{})
    calls=[]
    def llm(prompt):
        calls.append(json.loads(prompt.split("INPUT JSON:\n",1)[1]))
        return '{"time_range":{},"role_scope":{}}'
    args=dict(root=tmp_path,index={},card_id="ec1",card_sha256="same",
              card_fields=CARD_FIELDS,card_lists={},enabled=True,llm_call=llm)
    inference.infer_card(**args)
    assert calls[0]["confirmed_work_context"][0]["scope"]=="售后服务与订单系统"
    assert len(calls[0]["confirmed_work_context"])==1
    assert inference.infer_card(**args)["cache"]=="hit"
    profile["career"]["work"][0]["contributions"]=["参与售后服务改造"]
    assert inference.infer_card(**args)["cache"]=="miss"
    monkeypatch.setattr(context,"JOB_SEARCH_CONTEXT",context.JOB_SEARCH_CONTEXT+"\n更新产品语境")
    assert inference.infer_card(**args)["cache"]=="miss"
    profile["career_status"]["reviewed"]=False
    assert inference.infer_card(**args)["cache"]=="miss"
    assert calls[-1]["confirmed_work_context"]==[]


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
