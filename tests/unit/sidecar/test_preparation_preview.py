"""Preview RPC is read-only and cannot promote a draft or stale audit."""
from importlib.util import find_spec
from types import SimpleNamespace
import pytest
import json
from tools.engines.matching.semantic_review import job_requirements, requirement_checks, aggregate_assessments
from tools.engines.matching.semantic_matching import _facts
from tools.infra.persistence.yaml_io import parse_simple_yaml


def module():
    assert find_spec("tools.sidecar.handlers.preparation_preview"), "preview handler missing"
    from tools.sidecar.handlers import preparation_preview
    return preparation_preview


def test_missing_audit_is_blocked_without_model_or_write(monkeypatch,tmp_path):
    m=module()
    monkeypatch.setattr(m.semantic,"_inputs",lambda _:{"snapshot":{"fixture":"hash"}})
    monkeypatch.setattr(m.semantic,"_audit_path",lambda _:tmp_path/"missing.json")
    result=m.handle_preview_preparation({"meta":{},"job_profile_id":"jp_test"})
    assert result["status"]=="blocked" and result["code"]=="preview_audit_missing"
    assert not result["markdown"] and result["model_calls"]==0
    assert not result["send_ready"] and not result["deliverable"]
    assert list(tmp_path.iterdir())==[]


@pytest.fixture
def context(tmp_path,monkeypatch):
    m=module()
    job=tmp_path/"jp_test.yaml";job.write_text('company: TestCo\ntarget_role: Engineer\n')
    card=tmp_path/"ec_one.yaml";card.write_text('title: 服务平台\nrole_scope: 参与开发\nactions:\n  - 参与设计并实现可追溯的业务接口服务\nresults:\n  - 提升了服务稳定性与交付效率\n')
    facts=_facts("ec_one",parse_simple_yaml(card.read_text()))
    requirements=job_requirements(["业务接口开发"])
    checks=requirement_checks(requirements)
    criteria=[{"requirement_id":checks[0]["id"],"status":"partial","reason":"有部分实践，其他范围未核",
               "citations":[{"fact_id":"ec_one:actions:0","quote":facts["ec_one:actions:0"]["text"]}]}]
    raw={"job_profile_id":"jp_test","method":m.VERSION,"advisory_scope":True,"requirements":requirements,
         "requirement_checks":checks,"criterion_assessments":criteria,
         "assessments":aggregate_assessments(requirements,checks,criteria),"completed_check_ids":[checks[0]["id"]],
         "facts":facts,"card_reviews":[],"degraded_card_ids":[],"degraded_check_ids":[]}
    inputs={"snapshot":{"fixture":"same","contract":"v2"},"job_path":job,"personal_profile":tmp_path/"personal.yaml",
            "evidence_files":[card],"direction":{"status":"needs_review"},"pool":{}}
    record={"schema_version":1,"snapshot":inputs["snapshot"],"summary":{"scope":"advisory_partial","job_profile_id":"jp_test","input_fresh":True},"result":raw}
    path=tmp_path/"audit.json"
    def save():
        record["digest"]=m.semantic._record_digest(record)
        path.write_text(json.dumps(record,ensure_ascii=False))
    save()
    monkeypatch.setattr(m.semantic,"_inputs",lambda _:inputs)
    monkeypatch.setattr(m.semantic,"_audit_path",lambda _:path)
    monkeypatch.setattr(m,"_profile_facts",lambda _: {})
    return m,inputs,raw,record,path,save


def test_actual_handler_returns_partial_excerpt_without_writes(context):
    m,inputs,_,_,path,_=context
    before={p:p.read_bytes() for p in [path,inputs["job_path"],*inputs["evidence_files"]]}
    result=m.handle_preview_preparation({"meta":{},"job_profile_id":"jp_test"})
    assert result["status"]=="preview" and result["code"]=="preview_partial_ready"
    assert result["partial"] and not result["deliverable"] and not result["send_ready"]
    assert "参与设计并实现可追溯的业务接口服务" in result["markdown"]
    assert "提升了服务稳定性与交付效率" not in result["markdown"]
    assert result["limitations"][0]["status"]=="partial"
    assert all(p.read_bytes()==content for p,content in before.items())


@pytest.mark.parametrize("fault",["target","snapshot","digest","incomplete","missing_citation"])
def test_actual_handler_rejects_bad_binding_or_unfinished_parent(context,fault):
    m,inputs,raw,record,path,save=context
    if fault=="target":raw["job_profile_id"]="jp_other"
    elif fault=="snapshot":record["snapshot"]={"other":"snapshot"}
    elif fault=="incomplete":raw["completed_check_ids"]=[]
    elif fault=="missing_citation":raw["assessments"][0]["citations"].append({"fact_id":"missing","quote":"fake"})
    save()
    if fault=="digest":path.write_text(path.read_text().replace(record["digest"],"bad"))
    result=m.handle_preview_preparation({"meta":{},"job_profile_id":"jp_test"})
    assert result["status"]=="blocked" and result["markdown"]==""
    if fault=="incomplete":assert result["code"]=="no_presentable_supported_work"


@pytest.mark.parametrize("changed",["inputs","audit"])
def test_final_revalidation_discards_preview(context,monkeypatch,changed):
    m,inputs,raw,record,path,save=context
    original=m.build_targeted_excerpt
    def mutate(**kwargs):
        result=original(**kwargs)
        if changed=="inputs":
            monkeypatch.setattr(m.semantic,"_inputs",lambda _:{**inputs,"snapshot":{"changed":"new"}})
        else:
            record["provenance"]={"changed":"new"}
            save()
        return result
    monkeypatch.setattr(m,"build_targeted_excerpt",mutate)
    result=m.handle_preview_preparation({"meta":{},"job_profile_id":"jp_test"})
    assert result["status"]=="blocked" and result["code"]=="preview_inputs_changed"
    assert result["markdown"]=="" and not result["claims"]


def test_preview_keeps_negative_child_in_limitation_not_supported_claim(context):
    from tools.engines.matching.semantic_review import validate_assessments

    m, _, raw, _, _, save = context
    requirements = [{"id": "r1", "text": "业务接口开发；线上发布负责"}]
    checks = requirement_checks(requirements)
    judgments = validate_assessments({"assessments": [
        {"requirement_id": "r1.c1", "status": "supported", "reason": "有接口开发记录",
         "citations": [{"fact_id": "ec_one:actions:0"}]},
        {"requirement_id": "r1.c2", "status": "insufficient", "reason": "稳定性结果不足以证明本人负责上线",
         "citations": [{"fact_id": "ec_one:results:0"}]},
    ]}, raw["facts"], checks)
    raw.update(requirements=requirements, requirement_checks=checks, criterion_assessments=judgments,
               assessments=aggregate_assessments(requirements, checks, judgments),
               completed_check_ids=[c["id"] for c in checks])
    save()
    result = m.handle_preview_preparation({"meta": {}, "job_profile_id": "jp_test"})
    assert result["status"] == "preview"
    assert [c["fact_id"] for c in result["claims"] if c["usage"] == "supported_excerpt"] == ["ec_one:actions:0"]
    assert any(row["status"] == "partial" and "不足以证明本人负责上线" in row["reason"] for row in result["limitations"])
    assert "提升了服务稳定性与交付效率" not in result["markdown"]
    assert not result["send_ready"]
