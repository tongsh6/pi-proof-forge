import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.sidecar.handlers import jobs, agent
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.sidecar.server import process_request

JD = "岗位职责：\n1. 负责 Java 服务开发和接口维护。\n任职要求：\n1. 熟悉 Java、数据库和自动化测试。"
URL = "https://www.liepin.com/job/19123456.shtml"
LEAD_ID = "jl_official_test"
META = {"correlation_id": "official-binding-test"}


def write_doc(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values.items()) + "\n")


def capture_fixture(lead_id):
    # Simulate a successful public detail receipt before any new official approval.
    detail = {"jd_text":JD, "source_url":URL, "platform_job_id":"123456",
              "fetched_at":"2026-09-28T00:00:00Z", "source_jd_sha256":hashlib.sha256(JD.encode()).hexdigest()}
    with patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail",return_value=detail):
        result=jobs.handle_jobs_fetch_liepin_detail({"meta":META,"job_lead_id":lead_id})
    assert result["status"]=="pass"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_JOB_LEAD_DIR", tmp_path / "job_leads")
    monkeypatch.setattr(jobs, "_JOB_PROFILE_DIR", tmp_path / "job_profiles")
    monkeypatch.setattr(jobs, "_MATCHING_REPORT_DIR", tmp_path / "matching_reports")
    monkeypatch.setattr(agent, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(jobs, "_check_source_url_accessible", lambda _: {"checked": True, "accessible": True})
    write_doc(tmp_path / "job_leads" / f"{LEAD_ID}.yaml", {
        "id": LEAD_ID, "company": "测试公司", "position": "Java 工程师",
        "url": URL, "source": "liepin_official", "platform": "liepin",
        "platform_job_id": "123456", "platform_job_type": "2",
        "jd_status": "summary_only", "status": "new", "favorited": "true",
    })
    capture_fixture(LEAD_ID)
    return tmp_path


def save_bound(**overrides):
    params = {"meta": META, "job_lead_id": LEAD_ID, "save_mode": "complete",
              "review": {"decision": "approved"}, "draft": {
                  "target_role": "Java 工程师", "company": "测试公司", "source_jd": JD,
                  "source_url": URL, "jd_summary": "Java 服务开发与维护",
                  "keywords": ["Java"], "must_have": ["Java"],
                  "platform_job_id": "forged", "platform": "email",
              }}
    params.update(overrides)
    return jobs.handle_jobs_save_profile_draft(params)


def scalars(path):
    return parse_simple_yaml(path.read_text())["scalars"]


def test_review_binds_original_lead_and_preserves_server_identity(workspace):
    result = save_bound()
    assert result["job_lead_id"] == LEAD_ID
    assert len(list((workspace / "job_leads").glob("*.yaml"))) == 1
    lead = scalars(workspace / "job_leads" / f"{LEAD_ID}.yaml")
    profile = scalars(workspace / "job_profiles" / f"{result['job_profile_id']}.yaml")
    assert lead["source"] == "liepin_official" and lead["favorited"] == "true"
    assert lead["job_profile_id"] == result["job_profile_id"]
    assert lead["jd_status"] == "complete_reviewed"
    assert profile["job_lead_id"] == LEAD_ID
    assert profile["platform"] == "liepin" and profile["platform_job_id"] == "123456"
    assert profile["platform_job_type"] == "2"
    assert profile["source_jd_sha256"] == hashlib.sha256(JD.encode()).hexdigest()
    assert lead["source_jd_sha256"] == profile["source_jd_sha256"]
    again = save_bound()
    assert again["job_profile_id"] == result["job_profile_id"]


def test_convert_is_stable_and_review_updates_same_profile(workspace):
    first = jobs.handle_jobs_convert_lead({"meta": META, "job_lead_id": LEAD_ID})
    second = jobs.handle_jobs_convert_lead({"meta": META, "job_lead_id": LEAD_ID})
    assert first["job_profile_id"] == second["job_profile_id"]
    saved = save_bound(job_profile_id=first["job_profile_id"])
    assert saved["job_profile_id"] == first["job_profile_id"]
    assert len(list((workspace / "job_profiles").glob("*.yaml"))) == 1


def test_bound_source_and_profile_cannot_be_swapped(workspace):
    draft = {"target_role": "Java", "source_jd": JD, "source_url": "https://www.liepin.com/job/19999.shtml",
             "jd_summary": "Java", "keywords": ["Java"], "must_have": ["Java"]}
    with pytest.raises(ValueError, match="source_url_mismatch"):
        save_bound(draft=draft)
    first = save_bound()
    with pytest.raises(ValueError, match="job_profile_binding_mismatch"):
        save_bound(job_profile_id="jp_other")
    assert len(list((workspace / "job_profiles").glob("*.yaml"))) == 1


def test_basic_edit_keeps_provenance_but_semantic_change_invalidates_review(workspace):
    saved = save_bound()
    id_ = saved["job_profile_id"]
    jobs.handle_jobs_update_profile({"meta": META, "job_profile_id": id_, "patch": {"status": "archived"}})
    doc = scalars(workspace / "job_profiles" / f"{id_}.yaml")
    assert doc["source_url"] == URL and doc["job_lead_id"] == LEAD_ID
    assert doc["review_decision"] == "approved"
    save_bound()
    jobs.handle_jobs_update_profile({"meta": META, "job_profile_id": id_, "patch": {"title": "新标题", "status": "active"}})
    doc = scalars(workspace / "job_profiles" / f"{id_}.yaml")
    assert doc["status"] == "saved_incomplete" and doc["review_decision"] == ""
    with pytest.raises(ValueError, match="review_required"):
        jobs.handle_jobs_update_profile({"meta": META, "job_profile_id": id_, "patch": {"status": "active"}})


def test_summary_and_wrong_profile_do_not_enter_guided_candidates(workspace):
    path=workspace/"job_leads"/f"{LEAD_ID}.yaml"
    no_body=scalars(path)
    no_body.update(jd_status="summary_only",source_jd="",source_jd_sha256="")
    no_body.pop("jd_capture_json")
    write_doc(path,no_body)
    with pytest.raises(ValueError, match="missing_candidate_job_leads"):
        agent._job_lead_candidates({"candidate_ids": [LEAD_ID]})
    capture_fixture(LEAD_ID)
    saved = save_bound()
    candidate, = agent._job_lead_candidates({"candidate_ids": [LEAD_ID], "job_profile_id": saved["job_profile_id"]})
    assert candidate.platform == "liepin" and candidate.platform_job_id == "123456"
    assert candidate.job_profile_id == saved["job_profile_id"]
    assert candidate.source_jd_sha256 == hashlib.sha256(JD.encode()).hexdigest()
    with pytest.raises(ValueError, match="missing_candidate_job_leads"):
        agent._job_lead_candidates({"candidate_ids": [LEAD_ID], "job_profile_id": "jp_wrong"})
    with pytest.raises(ValueError, match="missing_candidate_job_leads"):
        agent._job_lead_candidates({"candidate_ids": ["jl_missing"]})


def test_edited_source_hash_cannot_reuse_prior_review(workspace):
    saved = save_bound()
    path = workspace / "job_profiles" / f"{saved['job_profile_id']}.yaml"
    path.write_text(path.read_text().replace("Java 服务开发", "Python 服务开发"))
    with pytest.raises(ValueError, match="missing_candidate_job_leads"):
        agent._job_lead_candidates({"candidate_ids": [LEAD_ID]})


def test_full_detail_fetch_keeps_original_lead_unreviewed(workspace, monkeypatch):
    called = []
    def fetch(url, expected_job_id):
        called.append((url, expected_job_id))
        return {"jd_text": JD, "source_url": URL, "platform_job_id": "123456",
                "fetched_at": "2026-09-28T00:00:00Z", "source_jd_sha256": hashlib.sha256(JD.encode()).hexdigest()}
    class DetailError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "tools.infra.liepin_job_detail", SimpleNamespace(
        fetch_liepin_job_detail=fetch, LiepinJobDetailError=DetailError))
    result = process_request({"id": "detail", "method": "jobs.fetchLiepinDetail",
                              "params": {"meta": META, "job_lead_id": LEAD_ID}})
    assert "result" in result, result
    detail = result["result"]
    assert detail["status"] == "pass" and detail["jd_text"] == JD
    assert detail["jd_status"] == "full_unreviewed"
    assert called == [(URL, "123456")]
    lead = scalars(workspace / "job_leads" / f"{LEAD_ID}.yaml")
    assert lead["source_jd"] == JD
    assert lead["platform_job_id"] == "123456"
    with pytest.raises(ValueError, match="missing_candidate_job_leads"):
        agent._job_lead_candidates({"candidate_ids": [LEAD_ID]})


def test_cli_discovery_reads_same_reviewed_scalar_lead(workspace):
    from tools.engines.discovery.job_leads_loader import load_candidates_from_job_leads
    assert load_candidates_from_job_leads(workspace / "job_leads") == []
    saved = save_bound()
    candidates = load_candidates_from_job_leads(workspace / "job_leads")
    assert len(candidates) == 1
    assert candidates[0].candidate_id == LEAD_ID
    assert candidates[0].job_profile_id == saved["job_profile_id"]
    assert candidates[0].platform_job_id == "123456"


def test_source_company_cannot_be_invented_by_draft(workspace):
    draft = {"target_role": "Java 工程师", "company": "伪造公司", "source_jd": JD,
             "source_url": URL, "jd_summary": "Java", "keywords": ["Java"], "must_have": ["Java"]}
    result = save_bound(draft=draft)
    profile = scalars(workspace / "job_profiles" / f"{result['job_profile_id']}.yaml")
    assert profile["company"] == "测试公司"


def test_review_payload_preserves_profile_and_job_identity(workspace):
    from tools.orchestration.agent_loop import _build_review_candidate_payload
    saved = save_bound()
    candidate, = agent._job_lead_candidates({"candidate_ids": [LEAD_ID]})
    review = _build_review_candidate_payload(candidate=candidate, matching_score=80,
        evaluation_score=80, round_index=0, resume_version="v-reviewed")
    assert review["job_profile_id"] == saved["job_profile_id"]
    assert review["platform_job_id"] == "123456"
    assert review["source_jd_sha256"] == hashlib.sha256(JD.encode()).hexdigest()


def test_research_keeps_completed_jd_and_binding(workspace, monkeypatch):
    item = {"jobId": "123456", "jobType": "2", "jobName": "Java 工程师",
            "company": "测试公司", "jobDetailUrl": URL}
    monkeypatch.setattr(jobs.liepin_readonly, "search", lambda *args: {"status": "pass", "code": "OK", "data": [item]})
    first = jobs.handle_jobs_search_liepin({"meta": META, "keyword": "Java"})
    lead_id = first["items"][0]["job_lead_id"]
    capture_fixture(lead_id)
    result = save_bound(job_lead_id=lead_id)
    again = jobs.handle_jobs_search_liepin({"meta": META, "keyword": "Java"})
    updated = again["items"][0]
    assert updated["jd_status"] == "complete_reviewed"
    assert updated["job_profile_id"] == result["job_profile_id"]
    assert updated["source_jd"] == JD
    assert updated["source_jd_sha256"] == hashlib.sha256(JD.encode()).hexdigest()


@pytest.mark.parametrize("changed_url,eligible", [(URL + "?mscid=new#detail", True),
                                                ("https://www.liepin.com/job/19888.shtml", False)])
def test_tracking_change_retains_review_but_other_job_path_does_not(workspace, monkeypatch, changed_url, eligible):
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile
    item = {"jobId": "123456", "jobType": "2", "jobName": "Java 工程师",
            "company": "测试公司", "jobDetailUrl": URL}
    monkeypatch.setattr(jobs.liepin_readonly, "search", lambda *args: {"status": "pass", "code": "OK", "data": [item]})
    first = jobs.handle_jobs_search_liepin({"meta": META, "keyword": "Java"})
    lead_id = first["items"][0]["job_lead_id"]
    capture_fixture(lead_id)
    save_bound(job_lead_id=lead_id)
    item["jobDetailUrl"] = changed_url
    jobs.handle_jobs_search_liepin({"meta": META, "keyword": "Java"})
    lead = scalars(workspace / "job_leads" / f"{lead_id}.yaml")
    assert bool(reviewed_official_profile(lead, workspace / "job_profiles")) is eligible



def model_draft(monkeypatch,finish='stop',**overrides):
    parsed={'target_role':'虚构高级架构师','company':'模型猜测公司','source_url':'https://wrong.example/job','must_have':['Java'],'keywords':['Java'],'jd_summary':'Java服务开发',**overrides}
    monkeypatch.setattr(jobs.settings_handler,'_load_llm_config',lambda:{'base_url':'http://127.0.0.1:1234/v1','api_key_for_request':'fixture','timeout':120,'provider':'lm_studio','model':'fixture','temperature':0})
    monkeypatch.setattr(jobs.LLMClient,'post_json',lambda *a,**kw:{'choices':[{'finish_reason':finish,'message':{'content':json.dumps(parsed)}}]})


def test_bound_model_draft_retains_official_title_company_and_source(workspace,monkeypatch):
    model_draft(monkeypatch)
    result=jobs.handle_jobs_generate_profile_draft({'meta':META,'job_lead_id':LEAD_ID,'jd_text':JD,'source_url':URL})
    assert result['draft']['target_role']=='Java 工程师'
    assert result['draft']['company']=='测试公司'
    assert result['draft']['source_url']==URL and result['draft']['source_jd']==JD
    assert not result['active_target_eligible']


def test_token_truncated_model_output_cannot_become_reviewable(workspace,monkeypatch):
    model_draft(monkeypatch,finish='length')
    result=jobs.handle_jobs_generate_profile_draft({'meta':META,'job_lead_id':LEAD_ID,'jd_text':JD,'source_url':URL})
    assert result['draft'] is None and result['active_target_eligible'] is False


@pytest.mark.parametrize('field,value',[('keywords',['x'*65]),('jd_summary','x'*601),('must_have',['Java']*21)])
def test_model_output_limits_are_enforced_even_if_provider_ignores_schema(field,value):
    parsed={'target_role':'工程师','must_have':['Java'],'keywords':['Java'],'jd_summary':'开发接口',field:value}
    with pytest.raises(ValueError,match='job_profile_draft_output_limit'):
        jobs._build_job_profile_draft(parsed,JD,URL)


def test_unbound_source_url_is_taken_from_input_not_model():
    parsed={'target_role':'工程师','must_have':['Java'],'keywords':['Java'],'jd_summary':'开发接口','source_url':'https://wrong.example/job'}
    assert jobs._build_job_profile_draft(parsed,JD,URL)['source_url']==URL



@pytest.mark.parametrize("fault",["missing","changed_type","changed_body"])
def test_new_official_approval_never_falls_back_without_exact_capture(workspace,monkeypatch,fault):
    path=workspace/"job_leads"/f"{LEAD_ID}.yaml"
    lead=scalars(path)
    if fault=="missing":lead.pop("jd_capture_json")
    if fault=="changed_type":lead["platform_job_type"]="1"
    if fault=="changed_body":
        lead["source_jd"]+="新的内容"
        lead["source_jd_sha256"]=hashlib.sha256(lead["source_jd"].encode()).hexdigest()
    write_doc(path,lead)
    before=path.read_bytes()
    def no_url_check(_):raise AssertionError("HEAD cannot attest captured body")
    monkeypatch.setattr(jobs,"_check_source_url_accessible",no_url_check)
    with pytest.raises(ValueError,match="stored_jd_source_unverified"):
        save_bound()
    assert path.read_bytes()==before and not list((workspace/"job_profiles").glob("*.yaml"))

@pytest.mark.parametrize("action", ["checkDirection", "start"])
@pytest.mark.parametrize("fault", ["invalidated", "wrong_url", "wrong_raw_id", "missing_lead", "unapproved", "unlabelled_profile"])
def test_quick_rpc_rejects_invalid_official_source_before_model_or_run(workspace, monkeypatch, fault, action):
    profile_id = save_bound()["job_profile_id"]
    lead = workspace / "job_leads" / f"{LEAD_ID}.yaml"
    profile = workspace / "job_profiles" / f"{profile_id}.yaml"
    path = profile if fault in ("unapproved", "unlabelled_profile") else lead
    if fault == "missing_lead":
        lead.unlink()
    else:
        fields = jobs._read_yaml_doc(path)["scalars"]
        if fault == "invalidated":
            capture = json.loads(fields["jd_capture_json"])
            fields["jd_capture_json"] = json.dumps({**capture, "invalidated": True})
        if fault == "wrong_url":
            fields["url"] = "https://www.liepin.com/job/19123457.shtml"
        if fault == "wrong_raw_id":
            fields["platform_job_id"] = "123457"
        if fault == "unapproved":
            fields["review_decision"] = ""
        if fault == "unlabelled_profile":
            fields.update({"source": "", "jd_origin": "", "source_jd_sha256": "wrong"})
        if path == profile:
            parsed = jobs._read_yaml_doc(path)
            jobs._write_job_profile_file(path, {**fields, **parsed["lists"]})
        else:
            jobs._write_job_lead_file(path, fields)
    raw = workspace / "raw.txt"
    raw.write_text("synthetic only")
    (workspace / "personal_profile.yaml").write_text("synthetic only")
    monkeypatch.setattr("tools.infra.job_preferences.load_preferences",
                        lambda _: pytest.fail("source gate must run before reading preferences"))
    monkeypatch.setattr(agent, "_persisted_llm_runtime_context",
                        lambda: pytest.fail("source gate must run before loading a model"))
    result = process_request({"id": action, "method": f"run.quick.{action}", "params": {
        "meta": META, "job_profile_id": profile_id, "options": {"raw_path": str(raw)},
    }})
    assert "job_profile_official_source_unverified" in result["error"]["message"], result
    assert not (workspace / "outputs").exists()


@pytest.mark.parametrize("case", ["current", "legacy", "manual"])
def test_quick_direction_accepts_same_bound_official_or_manual_profile(workspace, case):
    if case == "manual":
        profile_id = "jp_manual"
        jobs._write_job_profile_file(workspace / "job_profiles" / f"{profile_id}.yaml", {
            "status": "active", "import_mode": "manual", "platform": "liepin", "source_url": URL,
        })
    else:
        profile_id = save_bound()["job_profile_id"]
        if case == "legacy":
            lead = workspace / "job_leads" / f"{LEAD_ID}.yaml"
            fields = scalars(lead)
            fields.pop("jd_capture_json")
            jobs._write_job_lead_file(lead, fields)
    result = process_request({"id": "direction", "method": "run.quick.checkDirection", "params": {
        "meta": META, "job_profile_id": profile_id,
    }})
    assert result["result"]["unavailable_reason"] == "no_preferences", result


def test_quick_start_does_not_accept_a_replacement_path_for_official_profile(workspace, monkeypatch):
    profile_id = save_bound()["job_profile_id"]
    substitute = workspace / "replacement.yaml"
    raw = workspace / "raw.txt"
    raw.write_text("synthetic only")
    jobs._write_job_profile_file(substitute, {"status": "active", "import_mode": "manual"})
    monkeypatch.setattr(agent, "_persisted_llm_runtime_context",
                        lambda: pytest.fail("source gate must run before loading a model"))
    result = process_request({"id": "start", "method": "run.quick.start", "params": {
        "meta": META, "job_profile_id": profile_id,
        "options": {"raw_path": str(raw), "job_profile_path": str(substitute)},
    }})
    assert "job_profile_official_source_unverified" in result["error"]["message"], result
    assert not (workspace / "outputs").exists()


@pytest.mark.parametrize("fault", ["profile", "lead", "stage", "argv", "during", "tracking", "late", "none"])
def test_official_quick_worker_uses_and_revalidates_launch_bytes(workspace, monkeypatch, fault):
    from tools.sidecar.handlers import quick_run
    from threading import Event

    profile_id = save_bound()["job_profile_id"]
    profile = jobs._profile_path(profile_id)
    original = profile.read_bytes()
    raw = workspace / "raw.txt"
    raw.write_text("synthetic")
    card = workspace / "eligible.yaml"
    card.write_text("id: ec_fixture\ntitle: fixture\n")
    monkeypatch.setattr(agent, "_QUICK_RUN_DIR", workspace / "outputs" / "quick_runs")
    monkeypatch.setattr(agent, "_persisted_llm_runtime_context", lambda: ({}, {}))
    monkeypatch.setattr(quick_run, "_selected_evidence_cards", lambda *a: [])
    monkeypatch.setattr(quick_run, "_stage_selected_evidence", lambda *a: None)
    monkeypatch.setattr(quick_run.threading.Thread, "start", lambda _: None)
    monkeypatch.setattr(agent, "_build_quick_run_id", lambda: "qr_fixture")
    started = process_request({"id": "start", "method": "run.quick.start", "params": {
        "meta": META, "job_profile_id": profile_id, "options": {"raw_path": str(raw)},
    }})
    assert started["result"]["status"] == "RUNNING", started
    saved = quick_run._load_quick_run("qr_fixture")["run"]
    command = saved["command"]
    staged = workspace / command[command.index("--job-profile") + 1]
    assert staged != profile and staged.name == profile.name and staged.read_bytes() == original
    assert saved["official_target"]["profile_sha256"] == hashlib.sha256(original).hexdigest()
    if fault == "profile":
        profile.write_bytes(original+b"\n")
    if fault == "lead":
        lead = jobs._lead_path(LEAD_ID)
        doc = scalars(lead)
        capture = json.loads(doc["jd_capture_json"])
        doc["jd_capture_json"] = json.dumps({**capture, "invalidated": True})
        jobs._write_job_lead_file(lead, doc)
    if fault == "stage":
        staged.chmod(0o600)
        staged.write_bytes(original+b"\n")
    if fault == "tracking":
        lead = jobs._lead_path(LEAD_ID)
        doc = scalars(lead)
        doc["url"] += "?tracking=only"
        jobs._write_job_lead_file(lead, doc)
    if fault == "argv":
        command[command.index("--job-profile") + 1] = str(profile)
    called = []
    def spawn(argv, **kwargs):
        called.append(argv)
        assert staged.read_bytes() == original
        if fault == "during":
            profile.write_bytes(original+b"\n")
        return SimpleNamespace(poll=lambda: 0)
    monkeypatch.setattr(agent, "Popen", spawn)
    quick_run._execute_quick_run("qr_fixture", command, {}, 1, Event())
    done = quick_run._load_quick_run("qr_fixture")
    assert bool(called) == (fault in {"during", "none", "tracking", "late"})
    assert done["run"]["status"] == ("DONE" if fault in {"none", "tracking", "late"} else "FAILED")
    if fault not in {"none", "tracking", "late"}:
        assert done["reason"] == "quick_official_target_changed"
        assert not done["resume_readiness"]["content_ready"]
    if fault == "late":
        profile.write_bytes(original+b"\n")
        historical = quick_run.handle_quick_get({"run_id":"qr_fixture","meta":META})
        assert historical["status"] == "DONE"  # historical completion remains visible
        assert historical["reason"] == "quick_official_target_changed"
        assert not historical["resume_readiness"]["content_ready"]



def test_old_approved_official_profile_requires_capture_for_new_quick_run(workspace):
    profile_id = save_bound()["job_profile_id"]
    lead_path = jobs._lead_path(LEAD_ID)
    lead = scalars(lead_path)
    lead.pop("jd_capture_json")
    jobs._write_job_lead_file(lead_path, lead)
    raw = workspace / "raw.txt"
    raw.write_text("synthetic")
    reply = process_request({"id": "start", "method": "run.quick.start", "params": {
        "meta": META, "job_profile_id": profile_id, "options": {"raw_path": str(raw)},
    }})
    assert reply["error"]["message"] == "quick_official_capture_required"
    assert not (workspace / "outputs").exists()


@pytest.mark.parametrize("fault", ["old_run", "different_trace", "late_lead", "none"])
def test_new_native_pdf_preparation_requires_exact_current_quick_run(workspace, monkeypatch, fault):
    from tools.sidecar.handlers import native_pdf
    from tools.policy import exclusions

    profile_id = save_bound()["job_profile_id"]
    lead_path = jobs._lead_path(LEAD_ID)
    profile_path = jobs._profile_path(profile_id)
    run_id = "qr_fixture"
    run_root = workspace / "outputs" / "quick_runs"
    stage = run_root / run_id / "job_profile" / profile_path.name
    stage.parent.mkdir(parents=True)
    stage.write_bytes(profile_path.read_bytes())
    lead = scalars(lead_path)
    pin = {"job_lead_id": LEAD_ID, "profile_sha256": hashlib.sha256(stage.read_bytes()).hexdigest(),
           "capture": json.loads(lead["jd_capture_json"])}
    record = {"run": {"run_id": run_id, "status": "DONE", "job_profile_id": profile_id,
                      "job_profile_path": str(profile_path), "official_target": pin}}
    if fault == "old_run":
        del record["run"]["official_target"]
    (run_root / f"{run_id}.json").write_text(json.dumps(record))
    markdown = workspace / "outputs" / run_id / f"resume_mr-{run_id}_A.md"
    markdown.parent.mkdir()
    markdown.write_text("fixture")
    trace = {"target":{"job_lead_id": LEAD_ID, "source_jd_sha256": lead["source_jd_sha256"]},
             "inputs":{"job_profile":{"sha256":pin["profile_sha256"],
                                     "path":str((profile_path if fault == "different_trace" else stage).resolve())}}}
    if fault == "late_lead":
        lead["jd_capture_json"] = json.dumps({**pin["capture"], "invalidated": True})
        jobs._write_job_lead_file(lead_path, lead)
    monkeypatch.setattr(native_pdf, "read_generation_trace", lambda _: (trace, True))
    monkeypatch.setattr("tools.infra.resume_content.validate_generated_content", lambda *a: {})
    def stop_before_artifact(*args):
        raise ValueError("reached_existing_handoff_gate")
    monkeypatch.setattr(exclusions, "match_exclusion", stop_before_artifact)
    expected = {"old_run": "quick_official_target_changed", "different_trace": "quick_official_target_changed",
                "late_lead": "pdf_job_review_required", "none": "reached_existing_handoff_gate"}
    with pytest.raises(ValueError, match=expected[fault]):
        native_pdf._validated_generation(run_id)
    assert not list((workspace / "outputs").rglob("*.pdf"))  # no generated/queued artifact


@pytest.mark.parametrize("method,action,case", [
    ("run.agent.beginPdfUpload","prepare","revoked"),
    ("run.agent.pdfTargetPacket","prepare","revoked"),
    ("run.agent.beginPdfDelivery","prepare","revoked"),
    ("run.agent.pdfInteractionPacket","prepare","revoked"),
    ("run.agent.pdfInteractionPacket","inspect","revoked"),
    ("run.agent.pdfInteractionPacket","send","revoked"),
    ("daily.check","prepare","revoked"), ("daily.permit","prepare","revoked"),
    ("daily.permit","prepare","wrong_id"), ("daily.permit","prepare","changed_profile"),
    ("daily.permit","prepare","missing_pin"), ("daily.permit","prepare","tracking_only"),
    ("daily.preview","prepare","revoked"),
])
def test_current_official_queue_actions_use_live_source_and_sealed_identity(workspace, monkeypatch, method, action, case):
    from tools.sidecar.handlers import daily_delivery, native_pdf
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore

    profile_id = save_bound()["job_profile_id"]
    lead_path = jobs._lead_path(LEAD_ID)
    profile_path = jobs._profile_path(profile_id)
    lead = scalars(lead_path)
    capture = json.loads(lead["jd_capture_json"])
    run_id, quick_id = "aq_fixture", "qr_fixture"
    run_dir = workspace / "outputs" / "quick_runs"
    stage = run_dir / quick_id / "job_profile" / profile_path.name
    stage.parent.mkdir(parents=True)
    stage.write_bytes(profile_path.read_bytes())
    record={"run": {
        "run_id": quick_id, "status": "DONE", "job_profile_id": profile_id, "job_profile_path": str(profile_path),
        "official_target": {"job_lead_id": LEAD_ID, "capture": capture,
                            "profile_sha256": hashlib.sha256(stage.read_bytes()).hexdigest()},
    }}
    if case == "missing_pin":
        del record["run"]["official_target"]
    (run_dir / f"{quick_id}.json").write_text(json.dumps(record))
    c = {**{k:lead[k] for k in ("company", "position", "platform", "platform_job_id", "platform_job_type",
                              "job_profile_id", "jd_status", "source_jd_sha256", "source")},
         "job_lead_id":LEAD_ID, "job_url":URL, "delivery_kind":"generated_pdf",
         "status":"pending" if method.endswith("beginPdfUpload") else "approved"}
    if case == "wrong_id":
        c["platform_job_id"] = "999"
    q = {"run_id":run_id, "quick_run_id":quick_id, "candidates":[c]}
    if not method.endswith("beginPdfUpload"):
        q["attachment_binding"] = {"filename":"cv.pdf", "pdf_sha256":"sealed", "attachment_id":"fixture"}
        q["pdf_target_view"] = {"observation":{"responses":[{"method":"OBSERVE","payload":
            json.dumps({"url_match":True,"company_present":True,"position_present":True})}]}}
    if method.endswith("pdfInteractionPacket"):
        q["pdf_delivery"] = {"state":"communication_started","attempt_id":"sealed"}
    monkeypatch.setattr(agent, "_REVIEW_QUEUE_DIR", workspace / "outputs" / "review_queue")
    agent._save_queue(agent._get_queue_file(run_id),q)
    path=agent._get_queue_file(run_id);original=path.read_bytes()
    fixture_pdf = workspace / "fixture.pdf"
    fixture_pdf.write_bytes(b"%PDF-1.7\nfixture")
    monkeypatch.setattr(ReviewSnapshotStore,"load",lambda *a: {"pdf_sha256":"sealed","resume_path":str(fixture_pdf),"dry_run":False})
    monkeypatch.setattr(native_pdf,"_public",lambda *a:{})
    monkeypatch.setattr(native_pdf,"_ai_disclosure_enabled",lambda:True)
    monkeypatch.setattr("tools.infra.resume_content.require_queue_content",lambda *a,**kw: {})
    monkeypatch.setattr(daily_delivery,"store",lambda:pytest.fail("source gate must run before permit"))
    monkeypatch.setattr("tools.infra.liepin_job_detail.fetch_liepin_job_detail",
                        lambda *a,**kw:pytest.fail("source gate must run before platform"))
    if case == "revoked":
        lead["jd_capture_json"] = json.dumps({**capture, "invalidated":True})
        jobs._write_job_lead_file(lead_path, lead)
    if case == "changed_profile":
        profile_path.write_bytes(profile_path.read_bytes() + b"\n")
    if case == "tracking_only":
        lead["url"] += "?tracking=fixture"
        jobs._write_job_lead_file(lead_path, lead)
        def permit(ref, run_id, digest, **kw):
            assert digest == "sealed" and run_id == "aq_fixture"
            return {"write_deadline_ms":123}
        monkeypatch.setattr(daily_delivery, "store", lambda: SimpleNamespace(write_permit=permit))
    result = process_request({"id":method,"method":method,"params":{"meta":META,"run_id":run_id,
        "accept_account_effects":True,"action":action,"id":"daily_fixture"}})
    if case == "tracking_only":
        assert result["result"]["write_deadline_ms"] == 123
    elif method == "daily.preview":
        assert result["result"]["pdf_base64"]
    else:
        assert result["error"]["message"] == "quick_official_target_changed", result
    assert path.read_bytes() == original


@pytest.mark.parametrize("capture_state,expected", [
    ("current", {"supported": True, "reason": ""}),
    ("missing", {"supported": False, "reason": "quick_official_capture_required"}),
    ("invalidated", {"supported": False, "reason": "job_review_required"}),
])
def test_current_native_hint_and_daily_channel_follow_official_receipt(workspace, capture_state, expected):
    from tools.engines.discovery.preparation_plan import build_preparation_plan
    from tools.sidecar.handlers.jobs_matching import _native_pdf_delivery_state

    pid = save_bound()["job_profile_id"]
    profile = jobs._profile_path(pid)
    lead_path = jobs._lead_path(LEAD_ID)
    before_profile = profile.read_bytes()
    lead = scalars(lead_path)
    if capture_state == "missing":
        lead.pop("jd_capture_json")
    if capture_state == "invalidated":
        receipt = json.loads(lead["jd_capture_json"])
        lead["jd_capture_json"] = json.dumps({**receipt, "invalidated": True})
    jobs._write_job_lead_file(lead_path, lead)
    before_lead = lead_path.read_bytes()
    fields = scalars(profile)
    native = _native_pdf_delivery_state(fields, pid)
    assert native == expected
    plan = build_preparation_plan([{
        **fields, "job_profile_id": pid, "preparation_key": "official:test",
        "native_pdf_delivery": native, "fit_precheck": {"state": "consider"},
    }], maximum=1)
    assert plan["send_ready"] is False
    if capture_state == "current":
        assert plan["selected"][0]["channel"] == "generated_pdf"
    else:
        assert not plan["selected"]
        assert plan["deferred"][0]["reason"] == expected["reason"]
    assert profile.read_bytes() == before_profile and lead_path.read_bytes() == before_lead


def test_changed_official_detail_revokes_old_approval_before_profile_list(workspace, monkeypatch):
    saved = save_bound()
    pid = saved["job_profile_id"]
    updated = JD + "\n新增一条真实的合成职责。"
    detail = {"jd_text":updated, "source_url":URL, "platform_job_id":"123456",
              "fetched_at":"2026-09-29T00:00:00Z", "source_jd_sha256":hashlib.sha256(updated.encode()).hexdigest()}
    with patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail", return_value=detail):
        action = process_request({"id":"detail", "method":"jobs.fetchLiepinDetail",
                                  "params":{"meta":META,"job_lead_id":LEAD_ID}})["result"]
    assert action["status"] == "pass" and action["jd_status"] == "full_unreviewed"
    assert action["job_profile_id"] == pid
    doc = scalars(jobs._profile_path(pid))
    assert doc["status"] == "saved_incomplete" and not doc["review_decision"]


@pytest.mark.parametrize("code,reason,revokes", [
    ("JOB_ID_MISMATCH", None, True),
    ("JOB_DETAIL_UNAVAILABLE", "source_reports_unavailable", True),
    ("JOB_DETAIL_UNAVAILABLE", "source_page_not_found", True),
    ("JOB_DETAIL_UNAVAILABLE", "no_verified_detail", False),
    ("JOB_DETAIL_UNAVAILABLE", "access_required", False),
    ("SECURITY_CHALLENGE", None, False),
    ("NETWORK_ERROR", None, False),
])
def test_failed_detail_only_reports_a_profile_on_new_current_revocation(workspace, code, reason, revokes):
    from tools.domain.job_lead_state import current_jd_capture
    from tools.infra.liepin_job_detail import LiepinJobDetailError

    pid = save_bound()["job_profile_id"]
    path = jobs._lead_path(LEAD_ID)
    before = path.read_bytes()
    profile_path = jobs._profile_path(pid)
    approval_history = profile_path.read_bytes()
    assert current_jd_capture(scalars(path))
    def read():
        with patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail",
                   side_effect=LiepinJobDetailError(code, detail_reason=reason)):
            return process_request({"id":"detail","method":"jobs.fetchLiepinDetail",
                "params":{"job_lead_id":LEAD_ID,"meta":META}})["result"]
    first = read()
    assert first["status"] == "blocked" and first["code"] == code
    assert bool(current_jd_capture(scalars(path))) is (not revokes)
    assert (path.read_bytes() != before) is revokes
    assert profile_path.read_bytes() == approval_history
    assert first["job_profile_id"] == (pid if revokes else "")
    assert first["jd_text"] == ""
    assert read()["job_profile_id"] == ""  # no new transition from a prior invalid state


def test_failed_detail_does_not_revoke_newer_capture(workspace):
    from tools.domain.job_lead_state import current_jd_capture
    from tools.infra.liepin_job_detail import LiepinJobDetailError

    pid = save_bound()["job_profile_id"]
    lead_path = jobs._lead_path(LEAD_ID)
    profile_path = jobs._profile_path(pid)
    original = profile_path.read_bytes()
    def newer_receipt(*args, **kwargs):
        lead = scalars(lead_path)
        receipt = current_jd_capture(lead)
        assert receipt
        receipt["fetched_at"] = "2026-09-29T00:00:00Z"
        jobs._write_job_lead_file(lead_path, {**lead, "jd_capture_json":json.dumps(receipt)})
        raise LiepinJobDetailError("JOB_ID_MISMATCH")
    with patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail", side_effect=newer_receipt):
        result = process_request({"id":"detail","method":"jobs.fetchLiepinDetail",
            "params":{"job_lead_id":LEAD_ID,"meta":META}})["result"]
    assert result["status"] == "blocked" and result["job_profile_id"] == ""
    assert current_jd_capture(scalars(lead_path))["fetched_at"] == "2026-09-29T00:00:00Z"
    assert profile_path.read_bytes() == original
