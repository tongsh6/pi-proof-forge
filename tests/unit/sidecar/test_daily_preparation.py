"""每日准备计划是真实 RPC 到选择器的只读链路，不是投递。"""
import sqlite3
from pathlib import Path
from tools.sidecar.server import process_request
from tools.sidecar.handlers import jobs, jobs_matching

def request(maximum=3):
    return process_request({"id":"prepare","method":"jobs.planDailyPreparation",
        "params":{"meta":{"correlation_id":"test"},"maximum":maximum}})

def profile(id="p1", job="42"):
    return {"job_profile_id":id,"title":"Java","company":"公司","status":"active",
        "source_jd":"完整 Java JD","source_url":f"https://www.liepin.com/job/{job}.shtml",
        "platform":"liepin","platform_job_id":job,"platform_job_type":"2",
        "native_pdf_delivery":{"supported":True,"reason":""},
        "fit_precheck":{"state":"promising","rank":2,"source":"rule"}}

def test_rpc_reads_all_pages_and_never_creates_delivery_database(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_SUBMISSIONS_DIR", tmp_path/"missing")
    calls=[]
    def listing(params, **_):
        calls.append(params.get("cursor"))
        return {"items":[profile()] if not params.get("cursor") else [profile("p2")],
                "next_cursor":"100" if not params.get("cursor") else None}
    monkeypatch.setattr(jobs_matching,"handle_jobs_list_profiles",listing)
    response=request()
    assert "result" in response, response
    result=response["result"]
    assert calls==[None,"100"]
    assert len(result["selected"])==1
    assert result["shortfall"]==2 and result["send_ready"] is False
    assert len(result["deferred"])==1
    assert not (tmp_path/"missing").exists()

def test_attempt_history_and_unreadable_history_fail_closed(tmp_path, monkeypatch):
    from tools.channels.base import DeliveryRequest
    from tools.orchestration.approved_delivery import _job_key
    row=profile()
    key=_job_key(DeliveryRequest("", "", "liepin", "", row["source_url"], True, row))
    db=tmp_path/"delivery_attempts.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("create table attempts(job_key text,state text)")
        c.execute("insert into attempts values (?,?)",(key,"unknown"))
    monkeypatch.setattr(jobs,"_SUBMISSIONS_DIR",tmp_path)
    monkeypatch.setattr(jobs_matching,"handle_jobs_list_profiles",lambda p, **kw:{"items":[row],"next_cursor":None})
    before=db.read_bytes()
    response=request()
    assert "result" in response, response
    assert response["result"]["selected"]==[]
    assert response["result"]["shortfall"]==3
    assert db.read_bytes()==before
    db.write_bytes(b"not a sqlite database")
    assert "error" in request(), "unreadable history must not become an empty history"

def test_same_numeric_id_different_platform_type_not_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs,"_SUBMISSIONS_DIR",tmp_path)
    rows=[profile(),profile("p2")]
    rows[1].update(platform_job_type="1",source_url="https://www.liepin.com/a/42.shtml",
                   native_pdf_delivery={"supported":False,"reason":"platform_default_only"})
    monkeypatch.setattr(jobs_matching,"handle_jobs_list_profiles",lambda p, **kw:{"items":rows,"next_cursor":None})
    result=request()["result"]
    assert len(result["selected"])==2
    assert {x["channel"] for x in result["selected"]}=={"generated_pdf","platform_default"}

def test_rpc_rejects_invalid_daily_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs,"_SUBMISSIONS_DIR",tmp_path)
    assert "error" in request(4)


def test_plan_exposes_contract_recheck_only_through_trusted_stale_projection(tmp_path, monkeypatch):
    token = "a"*64
    ready, absent = profile("safe"), profile("other")
    for row in (ready, absent):
        row.update(status="draft", preparation={"state":"fresh", "requirements_grounded":True,
                   "direction":{"status":"aligned"}, "semantic_matching":{"status":"stale"}})
    ready["preparation"]["semantic_matching"]["contract_recheck_digest"] = token
    absent.update(platform_job_id="99", source_url="https://www.liepin.com/job/99.shtml")
    monkeypatch.setattr(jobs, "_SUBMISSIONS_DIR", tmp_path)
    monkeypatch.setattr(jobs_matching, "handle_jobs_list_profiles",lambda _, **kw:{"items":[ready,absent], "next_cursor":None})
    result = request()["result"]
    rows = {r["job_profile_id"]:r for r in result["deferred"]}
    assert rows["safe"]["recovery_action"] == {"kind":"recheck_matching","audit_digest":token}
    assert "contract_recheck_digest" not in rows["safe"]["preparation"]["semantic_matching"]
    assert rows["other"]["recovery_action"] is None
    assert not {"resume_assessment", "start_matching", "recheck_matching"} & rows["safe"].keys()
    assert not result["send_ready"]


def test_duplicate_job_profile_id_does_not_offer_recovery_even_with_distinct_lead_identity(tmp_path, monkeypatch):
    rows = [profile("duplicated","42"), profile("duplicated","99")]
    for row in rows:
        row.update(status="draft", preparation={"state":"fresh", "requirements_grounded":True,
                   "direction":{"status":"aligned"}, "semantic_matching":{"status":"stale",
                   "contract_recheck_digest":"a"*64}})
    monkeypatch.setattr(jobs, "_SUBMISSIONS_DIR", tmp_path)
    monkeypatch.setattr(jobs_matching, "handle_jobs_list_profiles",lambda _, **kw:{ "items":rows, "next_cursor":None})
    plan = request()["result"]
    assert len(plan["deferred"]) == 2 and all(row["recovery_action"] is None for row in plan["deferred"])
    assert not plan["send_ready"]
