import hashlib
import json
from unittest.mock import patch
import pytest
from tools.sidecar.handlers import preparation_assessment as m
from tools.sidecar.handlers import jobs

@pytest.fixture
def fixture(tmp_path, monkeypatch):
    leads=tmp_path/"leads";profiles=tmp_path/"profiles"
    monkeypatch.setattr(jobs,"_JOB_LEAD_DIR",leads)
    monkeypatch.setattr(jobs,"_JOB_PROFILE_DIR",profiles)
    body="负责 Java 服务开发。\n熟悉 SQL。"
    digest=hashlib.sha256(body.encode()).hexdigest()
    identity={"source":"liepin_official","platform":"liepin","platform_job_id":"123","platform_job_type":"2","source_jd":body,"source_jd_sha256":digest,"jd_origin":"public_page"}
    lead={**identity,"id":"jl_test","job_profile_id":"jp_test","url":"https://www.liepin.com/job/123.shtml","jd_status":"full_unreviewed","status":"new"}
    fields={**identity,"job_lead_id":"jl_test","source_url":lead["url"],"status":"draft","target_role":"Java","company":"Example"}
    lead["jd_capture_json"]=json.dumps({"source_url":lead["url"],"platform_job_id":"123","platform_job_type":"2","source_jd_sha256":digest,
        "fetched_at":"2026-11-18T00:00:00Z","invalidated":False})
    jobs._write_job_lead_file(leads/"jl_test.yaml",lead)
    jobs._write_job_profile_file(profiles/"jp_test.yaml",fields)
    prefs={"confirmed_at":"now","revision":"r1","items":[{"kind":"primary","text":"Java","quote":"Java"}]}
    draft={**fields,"must_have":["熟悉 SQL。"],"nice_to_have":[],"keywords":["Java"],"jd_summary":"服务开发"}
    with patch.object(m,"load_preferences",return_value=prefs), patch.object(m,"load_llm_config",return_value={"provider":"openai_compatible","base_url":"http://127.0.0.1:8000/v1","model":"local/test","timeout":10,"temperature":0,"api_key_for_request":"","thinking_enabled":False}), patch.object(m,"assess_direction",return_value={"status":"aligned","reason":"职责","criterion_index":0,"jd_quote":"Java"}) as direction, patch.object(m,"handle_jobs_generate_profile_draft",return_value={"code":"OK","draft":draft}) as generate:
        yield profiles/"jp_test.yaml",leads/"jl_test.yaml",prefs,direction,generate

def call():return m.handle_assess_preparation({"meta":{"correlation_id":"t"},"job_profile_id":"jp_test"})

def test_persist_unapproved_with_source_spans(fixture):
    path,_,_,_,generate=fixture
    result=call()
    assert result["status"]=="prepared",result
    assert result["send_ready"] is False and result["active_target_eligible"] is False
    assert result["requirements_grounded"] is True
    saved=jobs._read_yaml_doc(path)
    assert saved["scalars"]["status"]=="draft" and not saved["scalars"]["review_decision"]
    meta=json.loads(saved["scalars"]["preparation_json"])
    span=meta["requirement_sources"][0]
    assert saved["scalars"]["source_jd"][span["start"]:span["end"]]=="熟悉 SQL。"
    assert generate.call_args.args[0]["strict_extract"] is True

@pytest.mark.parametrize("field,value,code",[("status","active","profile_not_unapproved"),("source_jd_sha256","bad","source_binding_mismatch"),("platform_job_id","999","source_binding_mismatch")])
def test_bad_binding_no_model(fixture,field,value,code):
    path,_,_,direction,generate=fixture
    fields=jobs._preserved_profile_fields(jobs._read_yaml_doc(path));fields[field]=value
    jobs._write_job_profile_file(path,fields)
    before=path.read_bytes()
    assert call()["code"]==code
    assert path.read_bytes()==before
    direction.assert_not_called();generate.assert_not_called()

def test_remote_provider_no_personal_data_call(fixture):
    with patch.object(m,"load_llm_config",return_value={"provider":"openai_compatible","base_url":"https://example.com/v1","model":"m"}):
        assert call()["code"]=="local_splash_required"
    fixture[3].assert_not_called();fixture[4].assert_not_called()

def test_ungrounded_requirement_no_write(fixture):
    path,_,_,_,gen=fixture
    gen.return_value["draft"]["must_have"]=["十年 Java 经验"]
    before=path.read_bytes()
    assert call()["code"]=="requirement_source_missing"
    assert path.read_bytes()==before

def test_aligned_avoid_is_invalid(fixture):
    fixture[2]["items"][0]["kind"]="avoid"
    assert call()["code"]=="direction_invalid"
    fixture[4].assert_not_called()

def test_changed_profile_not_overwritten(fixture):
    path,_,_,direction,_=fixture
    def mutate(*a,**kw):
        path.write_text(path.read_text()+"\nmanual_edit: yes\n")
        return {"status":"aligned","reason":"职责","criterion_index":0,"jd_quote":"Java"}
    direction.side_effect=mutate
    assert call()["code"]=="assessment_inputs_changed"
    assert "manual_edit" in path.read_text()

def test_changed_preferences_no_write(fixture):
    path,_,prefs,_,_=fixture
    before=path.read_bytes()
    with patch.object(m,"load_preferences",side_effect=[prefs,{**prefs,"revision":"r2"}]):
        assert call()["code"]=="assessment_inputs_changed"
    assert path.read_bytes()==before

def test_atomic_save_failure_keeps_original(fixture):
    path=fixture[0];before=path.read_bytes()
    with patch.object(jobs,"atomic_write_text",side_effect=OSError("disk unavailable")):
        assert call()["code"]=="assessment_save_failed"
    assert path.read_bytes()==before

def test_fingerprint_is_saved_output_not_input(fixture):
    assert call()["code"]=="OK"
    fields=jobs._preserved_profile_fields(jobs._read_yaml_doc(fixture[0]))
    metadata=json.loads(fields["preparation_json"])
    assert metadata["content_fingerprint"]==m._fingerprint(fields)
    fields["must_have"]=["human changed"]
    assert metadata["content_fingerprint"]!=m._fingerprint(fields)

def test_rpc_boundary(fixture):
    from tools.sidecar.server import process_request
    response=process_request({"id":"assess","method":"jobs.assessPreparation","params":{"meta":{"correlation_id":"test"},"job_profile_id":"jp_test"}})
    assert "result" in response,response
    assert response["result"]["requirements_grounded"] is True

def test_excluded_defers_without_extraction(fixture):
    fixture[2]["items"][0]["kind"]="avoid"
    fixture[3].return_value.update(status="excluded",model_calls=1)
    result=call()
    assert result["status"]=="deferred"
    assert result["requirements_grounded"] is False
    assert result["model_calls"]==1
    fixture[4].assert_not_called()
    fields=jobs._read_yaml_doc(fixture[0])["scalars"]
    assert fields["status"]=="draft" and fields["review_decision"]==""
    assert json.loads(fields["preparation_json"])["direction"]["status"]=="excluded"

@pytest.mark.parametrize("kind",["primary","bridge","explore"])
def test_excluded_nonavoid_is_uncertain_not_automatic_defer(fixture,kind):
    fixture[2]["items"][0].update(kind=kind,text="产品型 Tech Lead")
    original={"status":"excluded","reason":"推断客户交付","criterion_index":0,"jd_quote":"负责 Java 服务开发。","model_calls":0}
    fixture[3].return_value=original
    result=call()
    assert result["status"]=="prepared",result
    assert result["direction"]["status"]=="needs_review"
    assert result["requirements_grounded"] is True
    fixture[4].assert_called_once()
    metadata=json.loads(jobs._read_yaml_doc(fixture[0])["scalars"]["preparation_json"])
    assert metadata["model_direction"]["status"]=="excluded"
    assert metadata["direction_adjustment"]=="excluded_without_avoid_evidence"
    assert metadata["direction"]["reason"]!="推断客户交付"
    assert original["status"]=="excluded"

def test_real_generation_strict_prompt(fixture):
    from tools.sidecar.handlers.jobs_profiles import handle_jobs_generate_profile_draft
    parsed={"target_role":"Java","must_have":["熟悉 SQL。"],"keywords":["Java"],"jd_summary":"服务","nice_to_have":[]}
    response={"choices":[{"message":{"content":json.dumps(parsed)},"finish_reason":"stop"}]}
    with patch.object(m,"handle_jobs_generate_profile_draft",handle_jobs_generate_profile_draft), patch.object(jobs.LLMClient,"post_json",return_value=response) as post:
        assert call()["status"]=="prepared"
    payload=post.call_args.args[1]
    assert "严格来源模式" in payload["messages"][0]["content"]
    assert "must_have" in payload["messages"][0]["content"]

def test_real_rpc_two_stages_network_only_mock(fixture):
    from tools.infra.job_preferences import assess_direction
    from tools.sidecar.handlers.jobs_profiles import handle_jobs_generate_profile_draft
    from tools.sidecar.server import process_request
    direction={"status":"aligned","reason":"职责","criterion_index":0,"jd_quote":"Java"}
    draft={"target_role":"Java","must_have":["熟悉 SQL。"],"keywords":["Java"],"jd_summary":"服务","nice_to_have":[]}
    responses=[{"choices":[{"message":{"content":json.dumps(value)},"finish_reason":"stop"}]} for value in (direction,draft)]
    with patch.object(m,"assess_direction",assess_direction), patch.object(m,"handle_jobs_generate_profile_draft",handle_jobs_generate_profile_draft), patch.object(jobs.LLMClient,"post_json",side_effect=responses) as post:
        response=process_request({"id":"real","method":"jobs.assessPreparation","params":{"meta":{"correlation_id":"test"},"job_profile_id":"jp_test"}})
    assert response["result"]["status"]=="prepared",response
    assert response["result"]["model_calls"]==2
    assert post.call_count==2
    assert "严格来源模式" in post.call_args_list[1].args[1]["messages"][0]["content"]
    assert jobs._read_yaml_doc(fixture[0])["scalars"]["review_decision"]==""

def test_invalid_direction_quote_no_write(fixture):
    fixture[3].return_value["jd_quote"]="not in jd"
    assert call()["code"]=="direction_invalid"



@pytest.mark.parametrize("fault", ["none", "manual", "manual_import_mode", "archived", "jd_changed", "wrong_link", "duplicate", "attempted", "already_prepared"])
def test_daily_plan_only_resumes_bound_source_only_draft(fixture, tmp_path, monkeypatch, fault):
    import sqlite3
    from tools.channels.base import DeliveryRequest
    from tools.orchestration.approved_delivery import _job_key
    from tools.sidecar.handlers import jobs_matching, preparation

    profile_path, lead_path, _, direction, generate = fixture
    fields = jobs._preserved_profile_fields(jobs._read_yaml_doc(profile_path))
    lead = jobs._read_yaml_doc(lead_path)["scalars"]
    row = dict(fields, job_profile_id="jp_test", title="Java")
    if fault == "manual":
        fields["source"] = row["source"] = "manual"
    elif fault == "manual_import_mode":
        fields["import_mode"] = row["import_mode"] = "manual"
    elif fault == "archived":
        fields["status"] = row["status"] = "archived"
    elif fault == "jd_changed":
        fields["source_jd_sha256"] = "wrong"
    elif fault == "wrong_link":
        lead["job_profile_id"] = "other"
        jobs._write_job_lead_file(lead_path, lead)
    elif fault == "already_prepared":
        fields["preparation_json"] = '{"status":"direction_deferred"}'
    jobs._write_job_profile_file(profile_path, fields)
    rows = [row, {**row, "job_profile_id":"other"}] if fault == "duplicate" else [row]
    monkeypatch.setattr(jobs_matching, "handle_jobs_list_profiles", lambda _, **kw: {"items": rows, "next_cursor": None})
    monkeypatch.setattr(jobs, "_SUBMISSIONS_DIR", tmp_path)
    if fault == "attempted":
        with sqlite3.connect(tmp_path / "delivery_attempts.sqlite3") as db:
            key = _job_key(DeliveryRequest("", "", "liepin", "", row["source_url"], True, row))
            db.execute("create table attempts(job_key text)")
            db.execute("insert into attempts values (?)", (key,))
    before = (profile_path.read_bytes(), lead_path.read_bytes())
    plan = preparation.handle_plan_daily_preparation({"meta": {"correlation_id":"test"}, "maximum":3})
    assert plan["selected"] == [] and plan["send_ready"] is False
    assert plan["deferred"][0]["recovery_action"] == ({"kind":"resume_assessment"} if fault == "none" else None)
    assert (profile_path.read_bytes(), lead_path.read_bytes()) == before
    direction.assert_not_called()
    generate.assert_not_called()


def test_resume_click_does_not_overwrite_a_draft_assessed_since_planning(fixture):
    profile_path, _, _, direction, generate = fixture
    assert call()["status"] == "prepared"
    direction.reset_mock()
    generate.reset_mock()
    before = profile_path.read_bytes()
    retry = m.handle_assess_preparation({"meta":{"correlation_id":"t"}, "job_profile_id":"jp_test", "resume_source_only":True})
    assert retry["code"] == "preparation_resume_unavailable" and retry["model_calls"] == 0
    assert not retry["send_ready"] and profile_path.read_bytes() == before
    direction.assert_not_called()
    generate.assert_not_called()


@pytest.mark.parametrize("stage", ["ready", "direction_deferred", "stale_source", "malformed_audit", "duplicate", "attempted"])
def test_daily_plan_only_starts_fresh_grounded_draft_without_audit(fixture, tmp_path, monkeypatch, stage):
    import sqlite3
    from tools.channels.base import DeliveryRequest
    from tools.orchestration.approved_delivery import _job_key
    from tools.sidecar.handlers import jobs_matching, preparation, preparation_semantic

    path, lead_path, prefs, direction, generate = fixture
    if stage == "direction_deferred":
        prefs["items"][0]["kind"] = "avoid"
        direction.return_value = {"status":"excluded","reason":"not desired","criterion_index":0,"jd_quote":"Java"}
    result = call()
    assert result["status"] == ("deferred" if stage == "direction_deferred" else "prepared")
    direction.reset_mock()
    generate.reset_mock()
    fields = jobs._preserved_profile_fields(jobs._read_yaml_doc(path))
    if stage == "stale_source":
        fields["source_jd_sha256"] = "changed"
        jobs._write_job_profile_file(path, fields)
    if stage == "malformed_audit":
        audit = preparation_semantic._audit_path("jp_test")
        audit.parent.mkdir(parents=True)
        audit.symlink_to(audit.parent / "missing.json")
    saved = jobs_matching._saved_preparation("jp_test", fields, lambda:(prefs,""), {})
    row = dict(fields, job_profile_id="jp_test", title="Java", preparation=saved)
    rows = [row, {**row, "job_profile_id":"other"}] if stage == "duplicate" else [row]
    monkeypatch.setattr(jobs_matching, "handle_jobs_list_profiles", lambda _, **kw: {"items": rows, "next_cursor":None})
    monkeypatch.setattr(jobs, "_SUBMISSIONS_DIR", tmp_path)
    if stage == "attempted":
        with sqlite3.connect(tmp_path/"delivery_attempts.sqlite3") as db:
            key = _job_key(DeliveryRequest("", "", "liepin", "", row["source_url"], True, row))
            db.execute("create table attempts(job_key text)")
            db.execute("insert into attempts values (?)", (key,))
    before = (path.read_bytes(), lead_path.read_bytes())
    plan = preparation.handle_plan_daily_preparation({"meta":{"correlation_id":"t"}})
    assert not plan["selected"] and not plan["send_ready"]
    assert plan["deferred"][0]["recovery_action"] == ({"kind":"start_matching"} if stage == "ready" else None)
    assert not {"resume_assessment", "start_matching", "recheck_matching"} & plan["deferred"][0].keys()
    assert (path.read_bytes(), lead_path.read_bytes()) == before
    direction.assert_not_called()
    generate.assert_not_called()
