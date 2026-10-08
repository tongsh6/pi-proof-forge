import hashlib
import json
import sys
from types import SimpleNamespace

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
    with pytest.raises(ValueError, match="missing_candidate_job_leads"):
        agent._job_lead_candidates({"candidate_ids": [LEAD_ID]})
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
