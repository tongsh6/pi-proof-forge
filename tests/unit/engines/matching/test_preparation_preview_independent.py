"""Independent strict excerpt boundaries; no model, no real user data."""
import copy
import importlib
import pytest


def fixture():
    facts={
      "ec:actions:0":{"source_id":"ec","field":"actions","text":"实现订单状态校验与消息重试机制，保障业务流程一致性","source_role":"负责后端开发"},
      "ec:actions:1":{"source_id":"ec","field":"actions","text":"未引用隐私项目动作不得夹带","source_role":"负责后端开发"},
      "ec:stack:0":{"source_id":"ec","field":"stack","text":"未引用量子计算技能","source_role":"负责后端开发"},
      "ec:title:0":{"source_id":"ec","field":"title","text":"订单消息平台","source_role":"负责后端开发"},
      "ec:role_scope:0":{"source_id":"ec","field":"role_scope","text":"负责后端开发","source_role":"负责后端开发"},
      "personal_profile:career.summary:0":{"source_id":"personal_profile","field":"career.summary","text":"未引用总监级个人总结","source_role":""},
    }
    return dict(assessments=[
      {"requirement_id":"r1","status":"supported","reason":"引用行动","citations":[{"fact_id":"ec:actions:0"}]},
      {"requirement_id":"r2","status":"unassessed","reason":"预算未执行","citations":[]}],
      requirements=[{"id":"r1","text":"可靠性实践"},{"id":"r2","text":"JD要求精通火星导航"}],
      audit_facts=copy.deepcopy(facts),current_facts=copy.deepcopy(facts),
      target={"target_role":"后端负责人","company":"合成公司"})


def build(**kwargs):
    m=importlib.import_module("tools.engines.generation.preparation_preview")
    return m.build_targeted_excerpt(**kwargs)


def test_unreviewed_result_citation_cannot_enter_excerpt():
    kw = fixture()
    value = "隔离测试 P95 从 200ms 降至 120ms"
    fact = {"source_id": "ec", "field": "results", "text": value, "source_role": "负责后端开发"}
    for facts in (kw["audit_facts"], kw["current_facts"]):
        facts["ec:results:0"] = dict(fact)
    kw["assessments"][0]["citations"].append({"fact_id": "ec:results:0", "quote": value})
    result = build(**kw)
    assert value not in result["markdown"]
    assert "实现订单状态校验" in result["markdown"]
    assert not any(c["fact_id"] == "ec:results:0" for c in result["claims"])


@pytest.mark.parametrize("current_review", [True, False])
def test_reviewed_nonquant_result_keeps_full_scope_and_sibling_action(current_review):
    from tests.unit.engines.test_fact_index import reviewed_result

    kw = fixture()
    value = "隔离回归环境中，故障切换无需人工介入即可完成；生产自动切换不在本次职责范围内。"
    fact = {"source_id": "ec", "field": "results", "text": value, "source_role": "负责后端开发"}
    for facts in (kw["audit_facts"], kw["current_facts"]):
        facts["ec:results:0"] = dict(fact)
    kw["assessments"][0]["citations"].append({"fact_id": "ec:results:0", "quote": value})
    kw["result_reviews"] = {"ec:results:0": reviewed_result(
        "ec", 0, value if current_review else "故障切换无需人工介入即可完成")}
    result = build(**kw)
    assert (value in result["markdown"]) is current_review
    assert "实现订单状态校验" in result["markdown"]
    rendered = [c for c in result["claims"] if c["fact_id"] == "ec:results:0"]
    assert len(rendered) == int(current_review)
    if current_review:
        assert rendered[0]["quote"] == value


def test_only_cited_action_and_explicit_context_are_rendered():
    kw=fixture();result=build(**kw)
    assert "实现订单状态校验" in result["markdown"]
    for forbidden in ("未引用隐私项目动作","未引用量子计算技能","未引用总监级个人总结","精通火星导航"):
        assert forbidden not in result["markdown"]
    used={c["fact_id"] for c in result["claims"]}
    assert "ec:actions:0" in used
    assert not used & {"ec:actions:1","ec:stack:0","personal_profile:career.summary:0"}
    assert all(c["usage"]=="context" for c in result["claims"] if c["fact_id"]!="ec:actions:0")
    assert any(x["requirement_id"]=="r2" for x in result["limitations"])


@pytest.mark.parametrize("mutation",["missing","changed_text","changed_role","wrong_source"])
def test_changed_or_missing_cited_fact_rejects_instead_of_rewriting(mutation):
    kw=fixture()
    if mutation=="missing":del kw["current_facts"]["ec:actions:0"]
    else:
        key,value={"changed_text":("text","替换后的另一个成果"),"changed_role":("source_role","仅协助"),
                   "wrong_source":("source_id","other_card")}[mutation]
        kw["current_facts"]["ec:actions:0"][key]=value
    with pytest.raises(ValueError,match="preview_fact_changed"):build(**kw)


@pytest.mark.parametrize("status",["unassessed","insufficient","conflict"])
def test_non_support_status_never_turns_into_resume_evidence(status):
    kw=fixture();kw["assessments"][0]["status"]=status
    with pytest.raises(ValueError,match="no_presentable_supported_work"):build(**kw)


def test_qualification_only_cannot_generate_empty_resume():
    kw=fixture()
    fact={"source_id":"personal_profile","field":"career.education.e.degree","text":"本科","source_role":""}
    kw["audit_facts"]["personal_profile:career.education.e.degree:0"]=fact
    kw["current_facts"]["personal_profile:career.education.e.degree:0"]=dict(fact)
    kw["assessments"][0]["citations"]=[{"fact_id":"personal_profile:career.education.e.degree:0"}]
    with pytest.raises(ValueError,match="no_presentable_supported_work"):build(**kw)


def test_partial_support_retains_limitation_and_does_not_claim_full_match():
    kw=fixture();kw["assessments"][0]["status"]="partial"
    kw["assessments"][0]["reason"]="只支持消息重试，容量验证未完成"
    result=build(**kw)
    assert any(x["requirement_id"]=="r1" and x["status"]=="partial" for x in result["limitations"])
    cited=next(c for c in result["claims"] if c["fact_id"]=="ec:actions:0")
    assert cited["support_statuses"]==["partial"]


def test_missing_role_cannot_borrow_target_title_as_personal_role():
    kw=fixture()
    for facts in (kw["audit_facts"],kw["current_facts"]):
        facts["ec:actions:0"]["source_role"]=""
        facts.pop("ec:role_scope:0")
    with pytest.raises(ValueError,match="no_presentable_supported_work"):build(**kw)


def test_mismatched_citation_quote_is_rejected_not_ignored():
    kw=fixture()
    kw["assessments"][0]["citations"][0]["quote"]="完全不存在的捏造原文"
    with pytest.raises(ValueError,match="preview_fact_changed"):build(**kw)


def test_missing_assessment_remains_visible_as_unassessed_limitation():
    kw=fixture();kw["assessments"]=kw["assessments"][:1]
    result=build(**kw)
    assert any(x["requirement_id"]=="r2" and x["status"]=="unassessed"
               for x in result["limitations"])


def test_string_qualifiers_do_not_get_rendered_character_by_character():
    kw=fixture()
    for facts in (kw["audit_facts"],kw["current_facts"]):
        facts["ec:actions:0"]["source_qualifiers"]="参与或负责"
    with pytest.raises(ValueError):build(**kw)


def test_composed_scope_background_remains_presentation_without_full_card_context(monkeypatch):
    module = importlib.import_module("tools.engines.generation.preparation_preview")
    kw = fixture()
    qualifiers = ["本人仅承担接口对接", "所有验证限于隔离回归环境"]
    full_context = "该项目完整场景未被岗位引用，不得作为片段背景夹带。"
    for facts in (kw["audit_facts"], kw["current_facts"]):
        facts["ec:actions:0"]["source_qualifiers"] = list(qualifiers)
        facts["ec:context:0"] = {
            "source_id": "ec", "field": "context", "text": full_context,
            "source_role": "负责后端开发",
        }
    actual_render = module.render_plan
    rendered_claims = []

    def observe_render(plan, index, **kwargs):
        return actual_render(plan, index, claims=rendered_claims, **kwargs)

    monkeypatch.setattr(module, "render_plan", observe_render)
    result = build(**kw)
    scope = "责任范围原文：" + "；".join(qualifiers)
    assert "背景：" + scope in result["markdown"]
    assert full_context not in result["markdown"]
    assert "未引用隐私项目动作" not in result["markdown"]
    assert result["preview_fact_count"] == 1
    background, = [row for row in rendered_claims if row.get("field") == "context"]
    assert background["text"] == scope
    assert background["source_kind"] == "presentation"
    assert "fact_id" not in background and "render_line" not in background
    assert not any(row.get("fact_id") == "ec:context:0"
                   for row in [*rendered_claims, *result["claims"]])
    cited, = [row for row in result["claims"] if row.get("usage") == "supported_excerpt"]
    assert cited["fact_id"] == "ec:actions:0"
    assert cited["quote"] == kw["current_facts"]["ec:actions:0"]["text"]


def test_preview_binds_actual_role_without_counting_it_as_supported_work(monkeypatch):
    from tests.unit.engines.test_fact_index import reviewed_result

    module = importlib.import_module("tools.engines.generation.preparation_preview")
    kw = fixture()
    role = "负责订单接口与消息重试机制的对接；总体架构由平台组负责，本人不承担平台整体改造。"
    result_text = "隔离回归环境中，故障切换无需人工介入即可完成；生产自动切换不在本次职责范围内。"
    qualifiers = ["本人仅承担接口对接", "所有验证限于隔离回归环境"]
    full_context = "该项目完整场景未被岗位引用，不得作为片段背景夹带。"
    for facts in (kw["audit_facts"], kw["current_facts"]):
        for fact in facts.values():
            if fact["source_id"] == "ec":
                fact["source_role"] = role
        facts["ec:role_scope:0"]["text"] = role
        facts["ec:actions:0"]["source_qualifiers"] = list(qualifiers)
        facts["ec:results:0"] = {
            "source_id": "ec", "field": "results", "text": result_text,
            "source_role": role, "source_qualifiers": list(qualifiers),
        }
        facts["ec:context:0"] = {
            "source_id": "ec", "field": "context", "text": full_context, "source_role": role,
        }
    kw["assessments"][0]["citations"].append({"fact_id": "ec:results:0", "quote": result_text})
    kw["result_reviews"] = {"ec:results:0": reviewed_result("ec", 0, result_text)}
    assert "ec:time_range:0" not in kw["current_facts"], "internal excerpts need no invented project period"

    actual_render = module.render_plan
    captured = {"claims": []}

    def observe_render(plan, index, **kwargs):
        captured["text"] = actual_render(plan, index, claims=captured["claims"], **kwargs)
        return captured["text"]

    monkeypatch.setattr(module, "render_plan", observe_render)
    result = build(**kw)
    scope = "责任范围原文：" + "；".join(qualifiers)
    assert "# 内部定向事实预览（片段，非投递版）" in result["markdown"]
    assert "不是完整简历或全岗位匹配结论" in result["markdown"]
    assert "角色：" + role in result["markdown"]
    assert "背景：" + scope in result["markdown"]
    assert full_context not in result["markdown"]
    assert "未引用隐私项目动作" not in result["markdown"]
    assert result["preview_fact_count"] == 2
    assert {row["fact_id"] for row in result["claims"]
            if row["usage"] == "supported_excerpt"} == {"ec:actions:0", "ec:results:0"}
    role_context, = [row for row in result["claims"] if row["field"] == "role_scope"]
    assert role_context["fact_id"] == "ec:role_scope:0"
    assert role_context["quote"] == role and role_context["usage"] == "context"
    assert any(row["requirement_id"] == "r2" and row["status"] == "unassessed"
               for row in result["limitations"])
    background, = [row for row in captured["claims"] if row.get("field") == "context"]
    assert background["source_kind"] == "presentation" and background["text"] == scope
    actual_role, = [row for row in captured["claims"] if row.get("field") == "role_scope"]
    assert actual_role["source_kind"] == "evidence"
    assert actual_role["evidence_id"] == "ec"
    assert actual_role["fact_id"] == "ec:role_scope:0"
    assert actual_role["text"] == role
    assert captured["text"].splitlines()[actual_role["render_line"] - 1] == "角色：" + role
    for fact_id in ("ec:actions:0", "ec:results:0"):
        claim, = [row for row in captured["claims"] if row.get("fact_id") == fact_id]
        assert captured["text"].splitlines()[claim["render_line"] - 1] == "- " + claim["text"]

