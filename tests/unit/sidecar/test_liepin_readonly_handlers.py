import json
import sys
from types import SimpleNamespace

import pytest

from tools.sidecar.server import process_request
from tools.sidecar.handlers import jobs
from tools.infra.persistence.yaml_io import parse_simple_yaml


def rpc(method, **params):
    response = process_request({
        "jsonrpc": "2.0", "id": "readonly-test", "method": method,
        "params": {"meta": {"correlation_id": "readonly-test"}, **params},
    })
    assert "result" in response, response
    return response["result"]


def test_token_is_saved_privately_and_settings_never_return_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    token = "test-only-private-token"
    try:
        before = rpc("settings.liepinCredential", action="clear")["auth"]
        assert before["state"] == "unconfigured"
        saved = rpc("settings.liepinCredential", action="set", token=token)["auth"]
        assert saved["state"] == "unverified"
        assert saved["configured"] is True
        assert saved["storage"] == "local_file"
        assert saved["saved"] is True
        assert saved["scope"] == "read_only"
        settings = rpc("settings.get")
        assert settings["liepin_api"] == saved
        assert token not in json.dumps(settings)
        from pathlib import Path
        token_path = Path(saved['storage_path'])
        assert token_path.read_text() == token
        assert token_path.stat().st_mode & 0o777 == 0o600
        assert token_path.parent.stat().st_mode & 0o777 == 0o700
    finally:
        rpc("settings.liepinCredential", action="clear")


def test_browser_session_does_not_prove_official_auth(monkeypatch):
    monkeypatch.setenv("PPF_LIEPIN_SESSION_DIR", "/tmp/existing-browser-profile")
    rpc("settings.liepinCredential", action="clear")
    auth = rpc("settings.get")["liepin_api"]
    assert auth["configured"] is False
    assert auth["state"] == "unconfigured"
    assert rpc("settings.liepinResume")["code"] == "AUTH_REQUIRED"
    assert rpc("jobs.searchLiepin", keyword="Java")["code"] == "AUTH_REQUIRED"


def test_invalid_replacement_preserves_old_credential_without_echo():
    rpc("settings.liepinCredential", action="set", token="old-private-token")
    invalid_token = "new-private-token\r\nx-injected: yes"
    result = rpc("settings.liepinCredential", action="set", token=invalid_token)
    assert result["auth"]["configured"] is True
    assert result["auth"]["code"] == "INVALID_INPUT"
    assert "private-token" not in json.dumps(result)


def test_shutdown_preserves_saved_token_for_next_session():
    rpc("settings.liepinCredential", action="set", token="shutdown-token")
    assert rpc("system.shutdown")["accepted"] is True
    restored = rpc("settings.get")["liepin_api"]
    assert restored["configured"] is True
    assert restored["state"] == "unverified"


def test_credential_action_is_an_allowlist_and_does_not_echo_params():
    response = process_request({
        "jsonrpc": "2.0", "id": "bad-action", "method": "settings.liepinCredential",
        "params": {"meta": {"correlation_id": "bad-action"},
                   "action": "apply-secret-value", "token": "sensitive-value"},
    })
    assert response.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "apply-secret-value" not in json.dumps(response)
    assert "sensitive-value" not in json.dumps(response)


@pytest.fixture
def official_client(monkeypatch, tmp_path):
    class ApiError(Exception):
        def __init__(self, code, message="private-response-must-not-leak"):
            self.code = code
            super().__init__(message)

    class Client:
        resume = "平台简历，只用于读取对照"
        items = [{"jobId": "123456", "jobType": "2", "jobName": "Java 工程师",
                  "company": "测试公司", "jobDetailUrl": "https://www.liepin.com/job/123456.shtml"}]
        error = None
        calls = []

        def get_resume(self, token):
            self.calls.append(("resume", token))
            if self.error:
                raise self.error
            return self.resume

        def search_jobs(self, token, keyword, page=0):
            self.calls.append(("search", token, keyword, page))
            if self.error:
                raise self.error
            return self.items

    fake = Client()
    monkeypatch.setitem(sys.modules, "tools.infra.liepin_api", SimpleNamespace(
        LiepinReadOnlyClient=lambda: fake, LiepinApiError=ApiError,
    ))
    monkeypatch.setattr(jobs, "_JOB_LEAD_DIR", tmp_path / "job_leads")
    monkeypatch.setattr(jobs, "_JOB_PROFILE_DIR", tmp_path / "profiles")
    yield fake, ApiError, tmp_path
    process_request({"id": "cleanup", "method": "settings.liepinCredential",
                     "params": {"meta": {"correlation_id": "cleanup"}, "action": "clear"}})


def test_check_validates_backend_and_resume_is_never_persisted(official_client):
    fake, _, tmp = official_client
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    auth = rpc("settings.liepinCredential", action="check")["auth"]
    assert auth["state"] == "valid"
    assert auth["last_checked_at"]
    assert "resume_text" not in auth
    result = rpc("settings.liepinResume")
    assert result["resume_text"] == fake.resume
    assert result["status"] == "pass"
    assert list(tmp.iterdir()) == []


def test_official_salary_location_survive_import_and_refresh_with_review(official_client):
    fake, _, tmp = official_client
    fake.items[0].update(salary='40-70k·15薪', location='上海-浦东新区')
    rpc('settings.liepinCredential', action='set', token='synthetic-token')
    lead = rpc('jobs.searchLiepin', keyword='验证')['items'][0]
    assert (lead['salary'], lead['location']) == ('40-70k·15薪', '上海-浦东新区')
    path = jobs._lead_path(lead['job_lead_id'])
    fields = parse_simple_yaml(path.read_text())['scalars']
    fields.update(source_jd='完整已审核JD', source_jd_sha256='digest',
                  jd_status='complete_reviewed', job_profile_id='profile-bound')
    jobs._write_job_lead_file(path, fields)
    fake.items[0].update(salary='45-75k·15薪', location='上海')
    refreshed = rpc('jobs.searchLiepin', keyword='验证')['items'][0]
    assert (refreshed['salary'], refreshed['location']) == ('45-75k·15薪', '上海')
    assert refreshed['jd_status'] == 'complete_reviewed'
    assert refreshed['job_profile_id'] == 'profile-bound'
    assert refreshed['source_jd_sha256'] == 'digest'
    assert rpc('jobs.listLeads')['items'][0]['salary'] == '45-75k·15薪'


@pytest.mark.parametrize('optional', [{}, {'salary': None, 'location': None}])
def test_missing_pay_location_are_unknown_not_inferred(official_client, optional):
    fake, _, _ = official_client
    fake.items[0].update(optional)
    rpc('settings.liepinCredential', action='set', token='synthetic-token')
    lead = rpc('jobs.searchLiepin', keyword='高薪')['items'][0]
    assert lead['salary'] == lead['location'] == ''


@pytest.mark.parametrize('field', ['salary', 'location'])
def test_malformed_pay_location_are_rejected_before_import(official_client, field):
    fake, _, tmp = official_client
    fake.items.append({**fake.items[0], 'jobId': 'second', field: {'unexpected': 'object'}})
    rpc('settings.liepinCredential', action='set', token='synthetic-token')
    result = rpc('jobs.searchLiepin', keyword='验证')
    assert result['code'] == 'INVALID_RESPONSE'
    assert list(tmp.iterdir()) == []


@pytest.mark.parametrize("code,state", [("AUTH_INVALID", "invalid"),
                                       ("RATE_LIMITED", "rate_limited"),
                                       ("NETWORK_ERROR", "error"),
                                       ("INVALID_RESPONSE", "error")])
def test_failed_check_revokes_valid_readiness_without_error_body(official_client, code, state):
    fake, Error, _ = official_client
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    assert rpc("settings.liepinCredential", action="check")["auth"]["state"] == "valid"
    fake.error = Error(code)
    result = rpc("settings.liepinResume")
    assert result["status"] == "blocked"
    assert result["resume_text"] == ""
    assert result["auth"]["state"] == state
    assert result["code"] == code
    assert "private-response" not in json.dumps(result)
    assert "session-only-token" not in json.dumps(result)


def test_search_imports_summary_lead_and_preserves_existing_review_state(official_client):
    fake, _, tmp = official_client
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    result = rpc("jobs.searchLiepin", keyword="Java", page=0)
    assert result["status"] == "pass"
    assert result["received_count"] == result["imported_count"] == 1
    lead = result["items"][0]
    assert lead["platform_job_id"] == "123456"
    assert lead["platform_job_type"] == "2"
    assert lead["jd_status"] == "summary_only"
    assert lead["fetched_at"]
    assert rpc("jobs.listLeads")["items"][0]["job_lead_id"] == lead["job_lead_id"]
    files = list((tmp / "job_leads").glob("*.yaml"))
    assert len(files) == 1
    saved = files[0].read_text()
    assert "session-only-token" not in saved
    files[0].write_text(saved.replace('status: "new"', 'status: "qualified"'))
    again = rpc("jobs.searchLiepin", keyword="Java")
    assert again["imported_count"] == 0
    assert again["items"][0]["status"] == "qualified"
    assert len(list((tmp / "job_leads").glob("*.yaml"))) == 1
    converted = rpc("jobs.convertLead", job_lead_id=lead["job_lead_id"])
    profile = parse_simple_yaml((tmp / "profiles" / (converted["job_profile_id"] + ".yaml")).read_text())
    assert profile["scalars"]["source_jd"] == ""
    assert profile["scalars"]["source_url"] == lead["url"]
    assert profile["scalars"]["status"] == "saved_incomplete"


def test_empty_search_and_bad_parameters_are_not_disguised_as_success(official_client):
    fake, _, tmp = official_client
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    fake.items = []
    result = rpc("jobs.searchLiepin", keyword="Java")
    assert result["status"] == "pass" and result["items"] == []
    assert result["received_count"] == result["imported_count"] == 0
    before = len(fake.calls)
    for params in ({"keyword": ""}, {"keyword": "Java", "page": -1},
                   {"keyword": "Java", "page": True}):
        assert rpc("jobs.searchLiepin", **params)["code"] == "INVALID_INPUT"
    assert len(fake.calls) == before
    assert list(tmp.iterdir()) == []


def test_search_rejects_unsafe_detail_url_before_writing(official_client):
    fake, _, tmp = official_client
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    fake.items = [{**fake.items[0], "jobDetailUrl": "https://liepin.com.evil.example/job/123456"}]
    result = rpc("jobs.searchLiepin", keyword="Java")
    assert result["status"] == "blocked"
    assert result["code"] == "INVALID_RESPONSE"
    assert list(tmp.iterdir()) == []


@pytest.mark.parametrize("field,value", [("jobDetailUrl", 123), ("jobDetailUrl", {}),
                                         ("jobDetailUrl", None), ("company", [])])
def test_malformed_job_fields_revoke_readiness_without_partial_import(official_client, field, value):
    fake, _, tmp = official_client
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    fake.items = [{**fake.items[0], field: value}]
    result = rpc("jobs.searchLiepin", keyword="Java")
    assert result["code"] == "INVALID_RESPONSE"
    assert result["auth"]["state"] == "error"
    assert list(tmp.iterdir()) == []


def test_search_keeps_company_facts_for_small_company_screening(official_client):
    """官方搜索返回的公司规模/融资阶段/行业必须落到线索与画像，供“微小公司”筛选使用。"""
    fake, _, tmp = official_client
    fake.items = [{"jobId": "654321", "jobType": "2", "jobName": "Java 技术负责人", "company": "小而美科技",
                   "jobDetailUrl": "https://www.liepin.com/job/654321.shtml", "location": "上海-张江",
                   "salary": "25-40k", "companySize": "1-49人", "financingStage": "天使轮",
                   "industry": "互联网", "workYears": "5-10年", "education": "本科"}]
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    lead = rpc("jobs.searchLiepin", keyword="Java", page=0)["items"][0]
    assert lead["company_size"] == "1-49人"
    assert lead["financing_stage"] == "天使轮"
    assert lead["industry"] == "互联网"
    assert lead["work_years"] == "5-10年"
    assert lead["education"] == "本科"
    saved = parse_simple_yaml(next((tmp / "job_leads").glob("*.yaml")).read_text())["scalars"]
    assert saved["company_size"] == "1-49人" and saved["financing_stage"] == "天使轮"
    assert rpc("jobs.listLeads", filters={"company_size_max": 99})["items"][0]["job_lead_id"] == lead["job_lead_id"]
    assert rpc("jobs.listLeads", filters={"company_size_max": 20})["items"] == []
    assert rpc("jobs.listLeads", filters={"query": "上海"})["items"][0]["job_lead_id"] == lead["job_lead_id"]
    assert rpc("jobs.listLeads", filters={"query": "北京"})["items"] == []
    converted = rpc("jobs.convertLead", job_lead_id=lead["job_lead_id"])
    profile = parse_simple_yaml((tmp / "profiles" / (converted["job_profile_id"] + ".yaml")).read_text())["scalars"]
    assert profile["company_size"] == "1-49人" and profile["financing_stage"] == "天使轮" and profile["industry"] == "互联网"
    listed = rpc("jobs.listProfiles")["items"][0]
    assert listed["company_size"] == "1-49人" and listed["financing_stage"] == "天使轮"


def test_search_without_company_facts_keeps_lead_contract(official_client):
    fake, _, tmp = official_client
    fake.items = [{"jobId": "777", "jobType": "2", "jobName": "Java", "company": "无规模信息公司",
                   "jobDetailUrl": "https://www.liepin.com/job/777.shtml", "companySize": None}]
    rpc("settings.liepinCredential", action="set", token="session-only-token")
    lead = rpc("jobs.searchLiepin", keyword="Java", page=0)["items"][0]
    assert lead["company_size"] == ""
    assert rpc("jobs.listLeads", filters={"company_size_max": 99})["items"] == []
    assert "company_size" not in parse_simple_yaml(next((tmp / "job_leads").glob("*.yaml")).read_text())["scalars"]
    fake.items = [{**fake.items[0], "companySize": 49}]
    assert rpc("jobs.searchLiepin", keyword="Java", page=0)["code"] == "INVALID_RESPONSE"
