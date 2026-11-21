"""完整 JD 抓取→转换链路：传递事实，不伪造语义审核。"""
import hashlib
from unittest.mock import patch

import pytest

from tools.domain.job_lead_state import lead_has_complete_jd
from tools.sidecar.handlers import jobs
from tools.sidecar.handlers.jobs_profiles import (
    handle_jobs_convert_lead, handle_jobs_fetch_liepin_detail,
)
from tools.infra.persistence.yaml_io import parse_simple_yaml


@pytest.mark.parametrize("state", ["full_unreviewed", "complete_unreviewed", "complete_reviewed", "complete"])
def test_complete_states_require_body_not_url(state):
    assert lead_has_complete_jd({"source_jd": "负责 Java API，要求后端经验。", "jd_status": state})
    for body in ("", "  ", "https://www.liepin.com/job/123.shtml"):
        assert not lead_has_complete_jd({"source_jd": body, "jd_status": state})


def test_fetch_then_convert_preserves_body_and_does_not_approve(tmp_path, monkeypatch):
    leads, profiles = tmp_path / "leads", tmp_path / "profiles"
    leads.mkdir()
    profiles.mkdir()
    monkeypatch.setattr(jobs, "_JOB_LEAD_DIR", leads)
    monkeypatch.setattr(jobs, "_JOB_PROFILE_DIR", profiles)
    url = "https://www.liepin.com/job/123.shtml"
    jobs._write_job_lead_file(leads / "jl_test.yaml", {
        "id": "jl_test", "source": "liepin_official", "platform": "liepin",
        "platform_job_id": "123", "platform_job_type": "2",
        "url": url, "company": "Example", "position": "Java Engineer",
        "jd_status": "summary_only",
    })
    body = "职位职责：负责 Java 服务与接口。\n任职要求：具备分布式系统开发经验。"
    digest = hashlib.sha256(body.encode()).hexdigest()
    params = {"meta": {"correlation_id": "conversion-test"}, "job_lead_id": "jl_test"}
    with patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail", return_value={
        "jd_text": body, "source_jd_sha256": digest, "fetched_at": "2026-11-18T00:00:00Z",
        "source_url":url,"platform_job_id":"123",
    }):
        fetched = handle_jobs_fetch_liepin_detail(params)
    assert fetched["status"] == "pass"
    assert fetched["jd_status"] == "full_unreviewed"
    converted = handle_jobs_convert_lead(params)
    path = profiles / (converted["job_profile_id"] + ".yaml")
    original = path.read_bytes()
    fields = parse_simple_yaml(original.decode())["scalars"]
    assert fields["status"] == "draft"
    assert fields["source_jd"] == body
    assert fields["source_url"] == url
    assert fields["source_jd_sha256"] == digest
    assert fields["target_role"] == "Java Engineer"
    assert fields["company"] == "Example"
    assert fields["jd_origin"] == "public_page"
    assert fields.get("review_decision", "") == ""
    assert fields.get("reviewed_at", "") == ""
    assert fields["platform_job_id"] == "123"
    assert fields["platform_job_type"] == "2"
    from tools.sidecar.handlers.jobs_matching import _native_pdf_delivery_state
    assert _native_pdf_delivery_state(fields, converted["job_profile_id"]) == {
        "supported": False, "reason": "job_review_required",
    }
    assert parse_simple_yaml((leads / "jl_test.yaml").read_text())["scalars"]["jd_status"] == "full_unreviewed"
    # 既有关联原样返回，不能借本次修复覆盖旧草稿。
    assert handle_jobs_convert_lead(params)["job_profile_id"] == converted["job_profile_id"]
    assert path.read_bytes() == original


def test_official_source_capture_is_not_relabelled_by_search(monkeypatch, tmp_path):
    import json
    import runpy
    from pathlib import Path
    from tools.sidecar.handlers import jobs, preparation_assessment
    from tools.sidecar.handlers.jobs_leads import liepin_readonly
    from tools.sidecar.server import process_request

    fixture=runpy.run_path(str(Path(__file__).resolve().parents[1]/"infra/test_liepin_job_detail.py"))
    respond,requests=fixture["transport"].__wrapped__(monkeypatch)
    leads=tmp_path/"leads";profiles=tmp_path/"profiles"
    monkeypatch.setattr(jobs,"_JOB_LEAD_DIR",leads)
    monkeypatch.setattr(jobs,"_JOB_PROFILE_DIR",profiles)
    source=fixture["URL"];raw_id=fixture["RAW_ID"]
    current=[source]
    monkeypatch.setattr(liepin_readonly,"search",lambda *a,**_:{
        "status":"pass","code":"OK","data":[{"jobId":raw_id,"jobType":"2","jobName":"Engineer",
            "jobDetailUrl":current[0],"company":"Fixture","location":"上海-浦东"}]})
    def rpc(name, **params):
        full=process_request({"id":name,"method":"jobs."+name,
                             "params":{"meta":{"correlation_id":"capture"},**params}})
        assert "result" in full,full
        return full["result"]
    def search():
        return rpc("searchLiepin",keyword="Java",page=0)["items"][0]["job_lead_id"]
    lead_id=search()
    def stored():
        return jobs._read_yaml_doc(leads/(lead_id+".yaml"))["scalars"]
    def capture():
        return json.loads(stored()["jd_capture_json"])
    respond()
    reply=rpc("fetchLiepinDetail",job_lead_id=lead_id)
    assert reply["status"]=="pass" and len(requests)==1
    original=capture()
    assert original["source_url"]==source and original["platform_job_id"]==raw_id
    assert original["source_jd_sha256"]==reply["source_jd_sha256"]
    current[0]=source+"?tracking=changed"
    assert search()==lead_id and capture()==original and len(requests)==1
    current[0]="https://www.liepin.com/job/1999042.shtml"
    assert search()==lead_id
    assert stored()["source_jd"]==reply["jd_text"] and capture()["invalidated"] is True
    current[0]=source
    assert search()==lead_id and capture()["invalidated"] is True
    denied=process_request({"id":"denied","method":"jobs.convertLead",
        "params":{"meta":{"correlation_id":"capture"},"job_lead_id":lead_id}})
    assert "stored_jd_source_unverified" in denied["error"]["message"]
    assert not list(profiles.glob("*.yaml")) and len(requests)==1
    respond(fixture["page"](identifier="777"))
    assert rpc("fetchLiepinDetail",job_lead_id=lead_id)["code"]=="JOB_ID_MISMATCH"
    assert capture()["invalidated"] is True and stored()["source_jd"]==reply["jd_text"]
    respond(fixture["page"](extra="<p>该职位已下线</p>"))
    assert rpc("fetchLiepinDetail",job_lead_id=lead_id)["code"]=="JOB_DETAIL_UNAVAILABLE"
    assert capture()["invalidated"] is True and stored()["source_jd"]==reply["jd_text"]
    respond()
    assert rpc("fetchLiepinDetail",job_lead_id=lead_id)["status"]=="pass"
    profile=rpc("convertLead",job_lead_id=lead_id)["job_profile_id"]
    fields=jobs._read_yaml_doc(profiles/(profile+".yaml"))["scalars"]
    assert fields["status"]=="draft" and not fields["review_decision"]
    assert fields["source_url"]==source and fields["source_jd"]==reply["jd_text"]
    assert preparation_assessment._bound(profile)[2]["source_jd_sha256"]==reply["source_jd_sha256"]
    historical=stored(); historical.pop("jd_capture_json")
    jobs._write_job_lead_file(leads/(lead_id+".yaml"),historical)
    with pytest.raises(ValueError,match="source_binding_mismatch"):
        preparation_assessment._bound(profile)
    profile_path=profiles/(profile+".yaml")
    pending_bytes=profile_path.read_bytes()
    respond()
    assert rpc("fetchLiepinDetail",job_lead_id=lead_id)["status"]=="pass"
    assert profile_path.read_bytes()==pending_bytes
    assert preparation_assessment._bound(profile)[2]["status"]=="draft"
    # Changing both body and ordinary fingerprint must not change the immutable capture hash.
    import hashlib
    changed={**stored(),"source_jd":stored()["source_jd"]+"\n追加"}
    changed["source_jd_sha256"]=hashlib.sha256(changed["source_jd"].encode()).hexdigest()
    jobs._write_job_lead_file(leads/(lead_id+".yaml"),changed)
    with pytest.raises(ValueError,match="source_binding_mismatch"):
        preparation_assessment._bound(profile)
    assert len(requests)==5
