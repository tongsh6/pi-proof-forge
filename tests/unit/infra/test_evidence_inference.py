"""C4/C6：跨文档检索、规则聚合、L3 候选校验、缓存与规则 L2 线索。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.infra import evidence_inference as inference


def _infer_once(**args):
    """Exercise the existing preparation, inference, validation and publication functions."""
    sources = inference.ValidatedSourcePaths()
    state = inference.load_state(args["root"], captured_sources=sources)
    result = inference.infer_card(**args, state=state, captured_sources=sources)
    inference.assert_current_inputs(root=args["root"], index=args["index"],
                                   card_fields=args["card_fields"], card_lists=args["card_lists"],
                                   captured_sources=sources)
    if result["cache"] == "miss" and result["status"] != "llm_error":
        inference.save_state(args["root"], state,
                             expected_sha256=sources.snapshots["inference_state"][1])
    return result


def make_index():
    return {
        "nonfact_materials": [{"material_id": "mat_fixture"}],
        "materials": {
            "mat_work": {
                "material_id": "mat_work", "label": "示例公司工作日志", "filename": "mat_work.txt",
                "documents": [
                    {"document_id": "doc_1", "label": "2023-03 周报", "title": "订单服务周报",
                     "source_name": "2023-03-06.md", "sha256": "s1", "dates": {"window": "2023-03"}},
                    {"document_id": "doc_2", "label": "2023-08 周报", "title": "订单服务上线复盘",
                     "source_name": "2023-08-15.md", "sha256": "s2", "dates": {}},
                ],
            },
            "mat_design": {
                "material_id": "mat_design", "label": "设计/实施计划（非完成证明）", "filename": "mat_design.txt",
                "documents": [{"document_id": "doc_design", "label": "订单服务设计", "title": "订单服务",
                               "source_name": "design.md", "sha256": "sd", "dates": {}}],
            },
            "mat_fixture": {
                "material_id": "mat_fixture", "label": "合成测试夹具", "filename": "mat_fixture.txt",
                "documents": [{"document_id": "doc_fixture", "label": "订单服务", "title": "订单服务",
                               "source_name": "fixture.md", "sha256": "sf", "dates": {}}],
            },
        },
    }


CARD_FIELDS = {"title": "订单服务", "context": "订单处理与库存同步链路"}
CARD_LISTS = {"tags": ["订单"], "stack": ["Java"]}


@pytest.mark.parametrize("raw,expected", [
    ("主导或深度参与方案设计与核心开发（L3 默认归因候选）","主导或深度参与方案设计与核心开发"),
    ("L3 技术负责人","L3 技术负责人"),
])
def test_role_value_separates_work_description_from_candidate_annotation(raw,expected):
    text="主导或深度参与方案设计与核心开发"
    aggregates=[{"material_id":"m","document_id":"d","sha256":"s","owner_hits":0,"participant_hits":0}]
    content=json.dumps({"role_scope":{"value":raw,"confidence":0.8,
                                    "evidence":[{"material_id":"m","document_id":"d","excerpt":text}]}})
    candidates=inference.parse_inference_candidates(content,aggregates=aggregates,texts={("m","d"):text},windows=[])
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
    texts={("mat_work", "doc_1"):"未知计划量不能参与确定性比例计算。系统支持物流回调和协同回写。"
                   "我参与售后服务接口联调。本人配合售后维修流程验收。"}
    result=inference.aggregate_documents(docs,texts)[0]
    assert result["participant_hits"]==2
    assert result["snippets"]==["我参与售后服务接口联调","本人配合售后维修流程验收"]


def test_context_without_first_person_is_available_to_the_model_and_bounded():
    text="个人工作汇总\n角色：后端负责人\n2023 年负责售后服务状态机设计与上线。\n"+"背景说明"*600
    docs=[{"material_id":"mat_work","document_id":"doc_1","label":"个人工作汇总","title":"售后服务"}]
    aggregates=inference.aggregate_documents(docs,{("mat_work", "doc_1"):text})
    prompt=inference.build_inference_prompt(CARD_FIELDS,CARD_LISTS,aggregates,[],[])
    payload=json.loads(prompt.split("INPUT JSON:\n",1)[1])
    document=payload["documents"][0]
    assert "角色：后端负责人" in document["context_excerpt"]
    assert "2023 年负责售后服务状态机设计与上线" in document["context_excerpt"]
    assert document["context_excerpt"] in text
    assert len(document["context_excerpt"])<=1000
    assert document["excerpt_truncated"] is True
    assert document["owner_hits"]==0


def test_personal_document_hint_does_not_override_exact_source_and_relevance():
    index = make_index()
    documents = index["materials"]["mat_work"]["documents"]
    documents.append({"document_id": "summary", "title": "个人工作总结", "label": "工作汇总",
                      "sha256": "summary", "person_doc": True})
    fields = {**CARD_FIELDS, "source_documents_json": json.dumps([
        {"material_id": "mat_work", "document_id": "doc_1", "sha256": "s1"}])}
    selected = inference.select_documents(index, fields, CARD_LISTS, limit=2)
    assert [d["document_id"] for d in selected] == ["doc_1", "doc_2"]
    assert all("source_kind" not in document for document in selected)

    # 任意文档被精确绑定时仍优先召回；个人标签或同材料关系不是绑定。
    fields["source_documents_json"] = json.dumps([
        {"material_id": "mat_work", "document_id": "summary", "sha256": "summary"}])
    selected = inference.select_documents(index, fields, CARD_LISTS, limit=1)
    assert [d["document_id"] for d in selected] == ["summary"]


def test_inference_receives_only_linked_confirmed_work_context_and_invalidates_cache(
        current_inference_inputs, monkeypatch):
    from tools.prompts import context
    case = current_inference_inputs
    fields = dict(case["profile_fields"])
    career = json.loads(fields["career_json"])
    career["work"][0]["scope"] = "售后服务与订单系统"
    career["work"][0]["contributions"] = ["负责售后服务状态机设计"]
    other = case["card"].with_name("other.yaml")
    other.write_text(case["card"].read_text(encoding="utf-8").replace('id: "ec_1"', 'id: "other"'),
                     encoding="utf-8")
    career["work"].append({**career["work"][0], "id": "work2", "company": "无关公司",
                           "title": "研究员", "evidence_ids": ["other"]})
    fields["career_json"] = json.dumps(career, ensure_ascii=False)
    case["profile"].write_text(_l4_confirm_profile(case["args"]["root"], fields), encoding="utf-8")
    calls = []

    def llm(prompt):
        calls.append(json.loads(prompt.split("INPUT JSON:\n", 1)[1]))
        return '{"time_range":{},"role_scope":{}}'

    args = {**case["args"], "llm_call": llm}
    _infer_once(**args)
    assert calls[0]["confirmed_work_context"][0]["scope"] == "售后服务与订单系统"
    assert len(calls[0]["confirmed_work_context"]) == 1
    assert _infer_once(**args)["cache"] == "hit"
    career["work"][0]["contributions"] = ["参与售后服务改造"]
    fields["career_json"] = json.dumps(career, ensure_ascii=False)
    case["profile"].write_text(_l4_confirm_profile(case["args"]["root"], fields), encoding="utf-8")
    assert _infer_once(**args)["cache"] == "miss"
    monkeypatch.setattr(context, "JOB_SEARCH_CONTEXT", context.JOB_SEARCH_CONTEXT + "\n更新产品语境")
    assert _infer_once(**args)["cache"] == "miss"
    case["profile"].write_text(_l4_scalar_yaml(fields), encoding="utf-8")
    assert _infer_once(**args)["cache"] == "miss"
    assert calls[-1]["confirmed_work_context"] == []


def test_aggregate_documents_extracts_dates_and_first_person_statements():
    texts = {
        ("mat_work", "doc_1"): "2023-03-06 周报。我负责订单服务改造，推动库存同步功能。我参与库存接口联调。",
        ("mat_work", "doc_2"): "2023-08-15 上线复盘。我主导订单服务上线，完成订单链路重构。",
    }
    documents = [{"material_id": "mat_work", "document_id": "doc_1", "label": "2023-03 周报",
                  "title": "订单服务周报", "sha256": "s1", "material_label": "示例公司工作日志",
                  "document_dates": {"window": "2023-03"}},
                 {"material_id": "mat_work", "document_id": "doc_2", "label": "2023-08 周报",
                  "title": "订单服务上线复盘", "sha256": "s2", "material_label": "示例公司工作日志",
                  "document_dates": {}}]
    aggregates = inference.aggregate_documents(documents, texts)
    assert aggregates[0]["owner_hits"] == 1 and aggregates[0]["participant_hits"] == 1
    assert "2023-03" in aggregates[0]["dates"] and "2023-03-06" in aggregates[0]["dates"]
    assert any("我负责订单服务改造" in snippet for snippet in aggregates[0]["snippets"])


def test_parse_candidates_validates_window_and_readable_excerpts():
    texts = {("mat_work", "doc_1"): "2023-03-06 我负责订单服务改造，推动库存同步功能上线。",
             ("mat_work", "doc_2"): "2023-08-15 我主导订单服务上线。"}
    aggregates = [
        {"material_id": "mat_work", "document_id": "doc_1", "label": "2023-03 周报", "sha256": "s1",
         "owner_hits": 1, "participant_hits": 0, "snippets": []},
        {"material_id": "mat_work", "document_id": "doc_2", "label": "2023-08 周报", "sha256": "s2",
         "owner_hits": 1, "participant_hits": 0, "snippets": []},
    ]
    windows = [(2022 * 12 + 2, 999999)]
    payload = {
        "time_range": {"value": "2023-03 ~ 2023-08", "precision": "month", "confidence": 0.7,
                       "evidence": [{"security": "x", "material_id": "mat_work", "document_id": "doc_1", "excerpt": "我负责订单服务改造"},
                                    {"material_id": "mat_work", "document_id": "doc_2", "excerpt": "原文没有这句"}]},
        "role_scope": {"value": "订单服务负责人", "confidence": 0.6,
                       "evidence": [{"material_id": "mat_work", "document_id": "doc_2", "excerpt": "我主导订单服务上线"}]},
    }
    candidates = inference.parse_inference_candidates(json.dumps(payload, ensure_ascii=False),
                                                      aggregates=aggregates, texts=texts, windows=windows)
    time_candidate = next(item for item in candidates if item["field"] == "time_range")
    role_candidate = next(item for item in candidates if item["field"] == "role_scope")
    assert time_candidate["level"] == "L3" and len(time_candidate["evidence"]) == 1
    assert role_candidate["first_person_hits"] == {"owner": 1, "participant": 0}
    outside = dict(payload)
    outside["time_range"] = {"value": "2019-01 ~ 2019-06", "confidence": 0.9,
                             "evidence": [{"material_id": "mat_work", "document_id": "doc_1", "excerpt": "我负责订单服务改造"}]}
    assert [item for item in inference.parse_inference_candidates(json.dumps(outside), aggregates=aggregates,
                                                                texts=texts, windows=windows)
            if item["field"] == "time_range"] == []


def test_rules_only_candidates_are_l2_and_within_window():
    aggregates = [{"material_id": "mat_work", "document_id": "doc_1", "sha256": "s1",
                   "dates": ["2023-03", "2019-01"]}]
    candidates = inference.rules_only_candidates(aggregates, [(2022 * 12 + 2, 999999)])
    assert len(candidates) == 1
    assert candidates[0]["level"] == "L2" and candidates[0]["value"] == "2023-03"
    assert candidates[0]["evidence"][0]["key"] == "document_date:2023-03"


def test_infer_card_caches_and_filters_rejected_candidates(current_inference_inputs):
    case = current_inference_inputs
    calls = []

    def llm(prompt):
        payload = json.loads(prompt.split("INPUT JSON:\n", 1)[1])
        calls.append(payload)
        document = payload["documents"][0]
        return json.dumps({"time_range": {"value": "2023-03", "confidence": 0.7,
                           "evidence": [{"material_id": document["material_id"],
                                         "document_id": document["document_id"],
                                         "excerpt": "我负责订单服务改造"}]}, "role_scope": {}},
                          ensure_ascii=False)

    args = {**case["args"], "llm_call": llm}
    first = _infer_once(**args)
    assert first["cache"] == "miss" and len(calls) == 1 and len(first["candidates"]) == 1
    second = _infer_once(**args)
    assert second["cache"] == "hit" and len(calls) == 1
    state = inference.load_state(args["root"])
    state["cards"]["ec_1"]["rejected"] = [first["candidates"][0]["candidate_hash"]]
    inference.save_state(args["root"], state)
    third = _infer_once(**args)
    assert third["cache"] == "hit" and third["candidates"] == []


def test_infer_card_disabled_returns_rules_only(current_inference_inputs):
    result = _infer_once(**{**current_inference_inputs["args"], "enabled": False},
                         llm_call=lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))
    assert result["status"] == "rules_only"
    assert result["candidates"] and result["candidates"][0]["level"] == "L2"


# L4 inputs are real registered materials and a genuinely inspected synthetic profile.
def _l4_scalar_yaml(fields):
    return "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in fields.items())


def _l4_material(root, material_id, text):
    material_dir = root / "materials"
    material_dir.mkdir(exist_ok=True)
    path = material_dir / f"{material_id}.txt"
    path.write_text(text, encoding="utf-8")
    meta = material_dir / f"{material_id}.meta.yaml"
    meta.write_text(_l4_scalar_yaml({
        "material_id": material_id, "filename": path.name, "label": "合成工作记录",
        "kind": "work", "extension": ".txt",
    }), encoding="utf-8")
    return path, meta


def _l4_confirm_profile(root, fields):
    from unittest.mock import patch
    from tools.sidecar.handlers import profile
    path = root / "personal_profile.yaml"
    previous = path.read_bytes() if path.exists() else None
    path.write_text(_l4_scalar_yaml(fields), encoding="utf-8")
    with patch.object(profile, "_PROFILE_PATH", path):
        current = profile.handle_profile_get({"meta": {"correlation_id": "l4-unit"}})["profile"]
        assert current["career_status"]["missing"] == []
        profile.handle_profile_review({"meta": {"correlation_id": "l4-unit"},
                                       "expected_revision": current["revision"], "confirmed": True})
        assert profile.handle_profile_get({"meta": {"correlation_id": "l4-unit"}})["profile"]["career_status"]["reviewed"]
        reviewed_text = path.read_text(encoding="utf-8")
    if previous is not None:
        path.write_bytes(previous)
    return reviewed_text


@pytest.fixture
def current_inference_inputs(tmp_path, monkeypatch):
    from tools.infra.career_profile import empty_career, load_career_profile
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    from tools.infra.knowledge_index import build_index

    monkeypatch.chdir(tmp_path)
    source_text = "# Source: work/2023-03.md\n\n# 订单服务周报\n2023-03-06 我负责订单服务改造，推动库存同步功能上线。\n"
    source_path, meta_path = _l4_material(tmp_path, "mat_a", source_text)
    evidence_dir = tmp_path / "evidence_cards"
    evidence_dir.mkdir()
    card_path = evidence_dir / "ec_1.yaml"
    card_path.write_text(
        'id: "ec_1"\ntitle: "订单服务"\ncontext: "订单处理与库存同步"\n'
        'time_range: ""\nrole_scope: ""\nstatus: "saved_eligible"\ncandidate_pool_eligible: "true"\n'
        'actions:\n  - "改造订单服务与库存同步接口"\nresults:\n  - "库存同步功能上线"\n'
        'artifacts:\n  - "合成上线记录"\ntags:\n  - "订单"\nstack:\n  - "Java"\n',
        encoding="utf-8")
    career = empty_career()
    career.update({
        "education_visibility": "omit",
        "work": [{"id": "work1", "company": "合成公司", "department": "研发",
                  "title": "后端工程师", "start": "2022-02", "end": "2024-06", "current": False,
                  "scope": "订单服务与库存同步", "contributions": ["负责订单服务改造"],
                  "evidence_ids": ["ec_1"]}],
        "skills": [{"id": "skill1", "category": "后端开发", "description": "订单接口与库存一致性",
                    "evidence_ids": ["ec_1"]}],
    })
    fields = {"name": "合成候选人", "phone": "13800000000", "email": "test@example.com",
              "city": "上海", "current_position": "后端工程师",
              "career_json": json.dumps(career, ensure_ascii=False)}
    profile_path = tmp_path / "personal_profile.yaml"
    profile_path.write_text(_l4_confirm_profile(tmp_path, fields), encoding="utf-8")
    assert load_career_profile(profile_path)["career_status"]["reviewed"] is True
    raw = card_path.read_bytes()
    card = parse_simple_yaml(raw.decode("utf-8"))
    args = dict(root=tmp_path, index=build_index(tmp_path), card_id="ec_1", card_path=card_path,
                card_sha256=hashlib.sha256(raw).hexdigest(),
                card_fields=card["scalars"], card_lists=card["lists"], enabled=True)
    return dict(args=args, card=card_path, profile=profile_path, source=source_path,
                meta=meta_path, source_text=source_text, profile_fields=fields)


def _l4_reply(prompt, calls):
    payload = json.loads(prompt.split("INPUT JSON:\n", 1)[1])
    calls.append(payload)
    source = payload["documents"][0]
    return json.dumps({"role_scope": {
        "value": "订单服务改造负责人", "confidence": 0.8,
        "evidence": [{"material_id": source["material_id"], "document_id": source["document_id"],
                      "excerpt": "我负责订单服务改造"}],
    }}, ensure_ascii=False)


def test_l4_attempt_fingerprint_keeps_material_identity():
    left = {"snapshots": {}, "documents": [
        {"material_id": "mat_a", "document_id": "same_doc", "sha256": "same_sha"},
    ], "prompt_version": inference.INFERENCE_PROMPT_VERSION, "task_context": inference.context_fingerprint()}
    right = {**left, "documents": [{**left["documents"][0], "material_id": "mat_b"}]}
    assert inference.attempt_fingerprint(left) != inference.attempt_fingerprint(right)


@pytest.mark.parametrize("cited_material", ["mat_a", "mat_b", "unselected"])
def test_l4_parser_does_not_reassign_a_material(cited_material):
    text = "我负责订单服务改造，推动库存同步功能上线。"
    aggregates = [{"material_id": mid, "document_id": "same_doc", "sha256": "same_sha",
                   "owner_hits": 1, "participant_hits": 0} for mid in ("mat_a", "mat_b")]
    payload = {"role_scope": {"value": "订单服务改造负责人", "confidence": 0.8,
                              "evidence": [{"material_id": cited_material, "document_id": "same_doc",
                                            "excerpt": "我负责订单服务改造"}]}}
    candidates = inference.parse_inference_candidates(
        json.dumps(payload, ensure_ascii=False), aggregates=aggregates,
        texts={(mid, "same_doc"): text for mid in ("mat_a", "mat_b")}, windows=[])
    if cited_material == "unselected":
        assert candidates == []
    else:
        assert len(candidates) == 1
        assert candidates[0]["evidence"] == [{"material_id": cited_material, "document_id": "same_doc",
                                             "sha256": "same_sha", "excerpt": "我负责订单服务改造"}]


def test_l4_replaced_material_cannot_reuse_the_old_source_candidate(current_inference_inputs):
    from tools.infra.knowledge_index import build_index
    case = current_inference_inputs
    calls = []
    args = {**case["args"], "llm_call": lambda prompt: _l4_reply(prompt, calls)}
    first = _infer_once(**args)
    assert first["candidates"][0]["evidence"][0]["material_id"] == "mat_a"
    case["meta"].unlink()
    _l4_material(args["root"], "mat_b", case["source_text"])
    args["index"] = build_index(args["root"])
    second = _infer_once(**args)
    assert second["cache"] == "miss"
    assert len(calls) == 2
    assert second["candidates"][0]["evidence"][0]["material_id"] == "mat_b"
    assert _infer_once(**args)["cache"] == "hit"
    assert len(calls) == 2


@pytest.mark.parametrize("first_enabled", [False, True])
def test_l4_cache_respects_the_current_inference_mode(current_inference_inputs, first_enabled):
    case = current_inference_inputs
    calls = []
    args = {**case["args"], "enabled": first_enabled, "llm_call": lambda prompt: _l4_reply(prompt, calls)}
    first = _infer_once(**args)
    assert first["status"] == ("ok" if first_enabled else "rules_only")
    assert first["candidates"]
    args["enabled"] = not first_enabled
    second = _infer_once(**args)
    assert second["status"] == ("rules_only" if first_enabled else "ok")
    assert {item["level"] for item in second["candidates"]} == ({"L2"} if first_enabled else {"L3"})
    assert len(calls) == 1


@pytest.mark.parametrize("changed_input", ["card", "source", "meta", "profile"])
def test_l4_changed_input_during_model_does_not_publish_or_overwrite(
        current_inference_inputs, monkeypatch, changed_input):
    from tools.prompts import context
    case = current_inference_inputs
    calls = []
    args = {**case["args"], "llm_call": lambda prompt: _l4_reply(prompt, calls)}
    _infer_once(**args)
    state_path = inference.state_path(args["root"])
    previous_state = state_path.read_bytes()
    monkeypatch.setattr(context, "JOB_SEARCH_CONTEXT", context.JOB_SEARCH_CONTEXT + "\n合成任务版本更新")
    changed_path = case[changed_input]
    changed_bytes = changed_path.read_bytes() + b"\n# concurrent change\n"

    def changing_model(prompt):
        reply = _l4_reply(prompt, calls)
        changed_path.write_bytes(changed_bytes)
        return reply

    args["llm_call"] = changing_model
    with pytest.raises(ValueError, match="changed|stale"):
        _infer_once(**args)
    assert len(calls) == 2
    assert state_path.read_bytes() == previous_state
    assert changed_path.read_bytes() == changed_bytes


def test_l4_old_parsed_source_cannot_receive_a_new_file_hash(current_inference_inputs, monkeypatch):
    from tools.infra import material_documents
    case = current_inference_inputs
    calls = []
    args = {**case["args"], "llm_call": lambda prompt: _l4_reply(prompt, calls)}
    _infer_once(**args)
    state_path = inference.state_path(args["root"])
    previous_state = state_path.read_bytes()
    split = material_documents.split_material_documents
    replacement = case["source_text"].replace("我负责订单服务改造", "同事负责订单服务改造")
    changed = False

    def split_then_change(text, filename):
        nonlocal changed
        documents = split(text, filename)
        if filename == case["source"].name and not changed:
            changed = True
            case["source"].write_text(replacement, encoding="utf-8")
        return documents

    monkeypatch.setattr(material_documents, "split_material_documents", split_then_change)
    with pytest.raises(ValueError, match="changed|stale"):
        _infer_once(**args)
    assert changed
    assert len(calls) == 1
    assert state_path.read_bytes() == previous_state
    assert case["source"].read_text(encoding="utf-8") == replacement


def test_l4_profile_windows_and_context_cannot_mix_two_versions(current_inference_inputs, monkeypatch):
    from tools.infra import career_profile
    case = current_inference_inputs
    original = case["profile"].read_text(encoding="utf-8")
    changed_fields = dict(case["profile_fields"])
    career = json.loads(changed_fields["career_json"])
    career["work"][0]["scope"] = "另一版本中的独立合成职责"
    career["work"][0]["start"] = "2021-02"
    changed_fields["career_json"] = json.dumps(career, ensure_ascii=False)
    replacement = _l4_confirm_profile(case["args"]["root"], changed_fields)
    inspect = career_profile.inspect_career
    consumed = []

    def inspect_then_switch(fields, evidence_dir, **kwargs):
        result = inspect(fields, evidence_dir, **kwargs)
        consumed.append(fields["career_json"])
        case["profile"].write_text(replacement if len(consumed) == 1 else original, encoding="utf-8")
        return result

    monkeypatch.setattr(career_profile, "inspect_career", inspect_then_switch)
    calls = []
    with pytest.raises(ValueError, match="changed|stale"):
        _infer_once(**case["args"], llm_call=lambda prompt: _l4_reply(prompt, calls))
    assert calls == []
    assert not inference.state_path(case["args"]["root"]).exists()


@pytest.mark.parametrize("profile_state", ["unconfirmed", "invalid", "missing"])
def test_l4_unadopted_profile_does_not_constrain_or_block_sources(current_inference_inputs, profile_state):
    case = current_inference_inputs
    if profile_state == "unconfirmed":
        case["profile"].write_text(_l4_scalar_yaml(case["profile_fields"]), encoding="utf-8")
    elif profile_state == "invalid":
        case["profile"].write_text('career_json: "{"\n', encoding="utf-8")
    else:
        case["profile"].unlink()
    calls = []
    result = _infer_once(**case["args"], llm_call=lambda prompt: _l4_reply(prompt, calls))
    assert result["status"] == "ok" and result["candidates"]
    assert calls[0]["employment_window"] == []
    assert calls[0]["window_bounds_months"] == []
    assert calls[0]["confirmed_work_context"] == []


def test_l4_stable_current_sources_keep_legal_cache_and_confirmed_context(current_inference_inputs):
    case = current_inference_inputs
    calls = []
    args = {**case["args"], "llm_call": lambda prompt: _l4_reply(prompt, calls)}
    first = _infer_once(**args)
    second = _infer_once(**args)
    assert first["cache"] == "miss" and second["cache"] == "hit"
    assert first["candidates"] == second["candidates"] and first["candidates"]
    assert len(calls) == 1
    assert calls[0]["employment_window"] == ["2022-02 ~ 2024-06"]
    assert calls[0]["confirmed_work_context"][0]["scope"] == "订单服务与库存同步"


def test_l4_unbound_recall_is_not_limited_to_eight_card_bindings(current_inference_inputs):
    from tools.infra.knowledge_index import build_index
    case = current_inference_inputs
    text = "".join(f"# Source: work/订单服务-{i}.md\n\n订单服务记录。我负责订单服务改造，推动库存同步功能上线。\n"
                   for i in range(10))
    case["source"].write_text(text, encoding="utf-8")
    calls = []
    args = {**case["args"], "index": build_index(case["args"]["root"])}
    result = _infer_once(**args, llm_call=lambda prompt: _l4_reply(prompt, calls))
    assert result["status"] == "ok" and result["candidates"]
    assert len(calls) == 1
    assert len(calls[0]["documents"]) == 10


@pytest.mark.parametrize("changed_contract", ["stable", "protocol", "context", "pruned_basis"])
def test_l5_confirmation_requires_the_original_inference_contract(
    current_inference_inputs, monkeypatch, changed_contract,
):
    from tools.prompts import context
    from tools.sidecar.handlers import evidence
    from tools.sidecar.server import process_request

    case = current_inference_inputs
    monkeypatch.setattr(evidence, "_EVIDENCE_DIR", case["card"].parent)
    configured = process_request({
        "jsonrpc": "2.0", "id": "l5-contract-config", "method": "settings.update",
        "params": {"meta": {"correlation_id": "l5-contract-config"},
                   "section": "evidence_inference", "payload": {"enabled": True}},
    })
    assert "error" not in configured
    calls = []
    result = _infer_once(**case["args"], llm_call=lambda prompt: _l4_reply(prompt, calls))
    assert result["status"] == "ok" and len(calls) == 1
    candidate = result["candidates"][0]
    state = inference.load_state(case["args"]["root"])
    stored = state["cards"]["ec_1"]
    assert stored["candidates"] == result["candidates"]
    original_card = case["card"].read_bytes()
    original_state = inference.state_path(case["args"]["root"]).read_bytes()
    original_context = inference.context_fingerprint()
    if changed_contract == "protocol":
        monkeypatch.setattr(inference, "INFERENCE_PROMPT_VERSION", inference.INFERENCE_PROMPT_VERSION + 1)
    elif changed_contract == "context":
        monkeypatch.setattr(context, "JOB_SEARCH_CONTEXT", context.JOB_SEARCH_CONTEXT + "\n合成协议更新。")
        assert inference.context_fingerprint() != original_context
    elif changed_contract == "pruned_basis":
        snapshots = stored["input_basis"]["snapshots"]
        assert "personal_profile" in snapshots and "career_evidence:ec_1" in snapshots
        stored["input_basis"]["snapshots"] = {
            key: value for key, value in snapshots.items()
            if key != "personal_profile" and not key.startswith("career_evidence:")
        }
        inference.save_state(case["args"]["root"], state)
        original_state = inference.state_path(case["args"]["root"]).read_bytes()
    params = {
        "meta": {"correlation_id": "l5-contract-confirm"}, "evidence_id": "ec_1",
        "card_sha256": hashlib.sha256(original_card).hexdigest(), "field": candidate["field"],
        "candidate_hash": candidate["candidate_hash"], "action": "accept",
    }
    if changed_contract == "stable":
        accepted = evidence.handle_evidence_confirm_inference(params)
        assert accepted["status"] == "accepted" and accepted["provenance"]["level"] == "L3"
    else:
        with pytest.raises(ValueError, match="evidence_inference|material_source"):
            evidence.handle_evidence_confirm_inference(params)
        assert case["card"].read_bytes() == original_card
        assert inference.state_path(case["args"]["root"]).read_bytes() == original_state


@pytest.mark.parametrize("basis_state", ["missing", "damaged"])
def test_l5_unbound_inference_state_cannot_supply_a_cache_hit(
    current_inference_inputs, basis_state,
):
    case = current_inference_inputs
    calls = []
    args = {**case["args"], "llm_call": lambda prompt: _l4_reply(prompt, calls)}
    first = _infer_once(**args)
    assert first["cache"] == "miss" and len(calls) == 1 and first["candidates"]
    state = inference.load_state(case["args"]["root"])
    stored = state["cards"]["ec_1"]
    if basis_state == "missing":
        stored.pop("input_basis", None)
    else:
        stored["input_basis"] = {"snapshots": "not a source snapshot"}
    stored["rejected"] = ["0" * 64]
    inference.save_state(case["args"]["root"], state)
    second = _infer_once(**args)
    assert second["cache"] == "miss" and len(calls) == 2
    assert inference.load_state(case["args"]["root"])["cards"]["ec_1"]["rejected"] == ["0" * 64]
