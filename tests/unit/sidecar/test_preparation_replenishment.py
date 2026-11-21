"""Bounded source replenishment regression tests. No live service calls."""
from unittest.mock import patch
import pytest
from tools.sidecar.handlers import preparation_replenishment as m

@pytest.fixture
def setup(tmp_path):
    profile=tmp_path/"personal_profile.yaml"
    profile.write_text("city: 上海\n")
    lead={"job_lead_id":"jl_1","platform":"liepin","platform_job_id":"1","platform_job_type":"2","url":"https://www.liepin.com/job/1.shtml","location":"上海-浦东","status":"new","company":"Example","position":"Java","source":"liepin_official"}
    with patch.object(m,"profile_path",return_value=profile), patch.object(m.jobs,"_SUBMISSIONS_DIR",tmp_path/"submissions"), patch.object(m,"load_preferences",return_value={"confirmed_at":"today","items":[{"kind":"primary","text":"Java后端，其他描述","quote":"PRIVATE"}]}), patch.object(m,"handle_plan_daily_preparation",return_value={"shortfall":3}), patch.object(m,"_read_current",side_effect=lambda _:dict(lead)), patch.object(m,"handle_jobs_search_liepin",return_value={"status":"pass","code":"OK","items":[lead],"received_count":1,"imported_count":1}) as search, patch.object(m,"handle_jobs_fetch_liepin_detail",return_value={"status":"pass","code":"OK"}) as fetch, patch.object(m,"handle_jobs_convert_lead",return_value={"job_profile_id":"jp_1"}) as convert:
        yield lead,search,fetch,convert

def call():return m.handle_replenish_preparation({"meta":{"correlation_id":"test"},"maximum":3})

def test_rpc_boundary(setup):
    from tools.sidecar.server import process_request
    response=process_request({"id":"replenish","method":"jobs.replenishPreparation","params":{"meta":{"correlation_id":"test"},"maximum":1}})
    assert "result" in response, response
    assert response["result"]["source_prepared_count"]==1
    assert response["result"]["send_ready"] is False


def test_sources_only_and_bounded(setup):
    lead,search,fetch,convert=setup
    result=call()
    assert result["source_prepared_count"]==1
    assert result["send_ready"] is False
    assert result["queries"]==["Java后端","Java后端"]
    assert all(c.args[0]["address"]=="上海" for c in search.call_args_list)
    assert search.call_count==2 and fetch.call_count==1 and convert.call_count==1
    assert "PRIVATE" not in str(search.call_args_list)
    assert convert.call_args.args[0]=={"meta":{"correlation_id":"test"},"job_lead_id":"jl_1"}

@pytest.mark.parametrize("change,reason",[({"location":""},"city_unknown"),({"location":"北京"},"city_mismatch"),({"status":"archived"},"lead_not_new"),({"job_profile_id":"jp_existing"},"profile_already_linked"),({"platform_job_type":""},"job_identity_missing")])
def test_defer_before_detail(setup,change,reason):
    lead,_,fetch,convert=setup
    lead.update(change)
    result=call()
    assert reason in [x["reason"] for x in result["deferred"]]
    fetch.assert_not_called();convert.assert_not_called()

def test_history_fail_closed(setup):
    with patch.object(m,"_attempted_keys",side_effect=ValueError("delivery_state_unavailable")):
        result=call()
    assert result["status"]=="blocked"
    setup[1].assert_not_called()


def test_explicit_space_city(setup):
    setup[0]["location"]="上海 浦东"
    assert call()["source_prepared_count"]==1

def test_source_change_reason_preserved(setup):
    with patch.object(m,"load_preferences",side_effect=ValueError("job_preferences_source_changed")):
        assert call()["code"]=="job_preferences_source_changed"
    setup[1].assert_not_called()

def test_partial_search_does_not_consume_partial_items(setup):
    setup[1].return_value={"status":"blocked","code":"STORAGE_ERROR","items":[setup[0]],"received_count":4,"imported_count":1}
    result=call()
    assert result["imported_count"]==1 and result["errors"][0]["code"]=="STORAGE_ERROR"
    setup[2].assert_not_called()
    assert setup[1].call_count==1

def test_search_auth_no_retry(setup):
    setup[1].return_value={"status":"blocked","code":"AUTH_INVALID"}
    assert call()["errors"][0]["code"]=="AUTH_INVALID"
    assert setup[1].call_count==1

def test_zero_shortfall_no_search(setup):
    with patch.object(m,"handle_plan_daily_preparation",return_value={"shortfall":0}):
        assert call()["source_prepared_count"]==0
    setup[1].assert_not_called()

def test_unsafe_query_not_sent(setup):
    with patch.object(m,"load_preferences",return_value={"confirmed_at":"now","items":[{"kind":"primary","text":"联系15021120000","quote":"private"}]}):
        assert call()["status"]=="blocked"
    setup[1].assert_not_called()

def test_history_identity_excluded(setup):
    with patch.object(m,"_attempted_keys",return_value={m._identity(setup[0])}):
        assert call()["source_prepared_count"]==0
    setup[2].assert_not_called()

def test_detail_budget_and_failure_no_retry(setup):
    lead,search,fetch,convert=setup
    rows=[{**lead,"job_lead_id":f"jl_{i}","platform_job_id":str(i)} for i in range(8)]
    search.return_value={"status":"pass","code":"OK","items":rows,"received_count":8,"imported_count":8}
    fetch.return_value={"status":"blocked","code":"NETWORK_ERROR"}
    with patch.object(m,"_read_current",side_effect=lambda id:next(dict(row) for row in rows if row["job_lead_id"]==id)):
        result=call()
    assert fetch.call_count==3 and search.call_count==1
    assert len(result["errors"])==3
    convert.assert_not_called()

def test_concurrent_link_before_convert_is_preserved(setup):
    lead,_,fetch,convert=setup
    def fetched(_):
        lead["job_profile_id"]="jp_user_edit"
        return {"status":"pass","code":"OK"}
    fetch.side_effect=fetched
    result=call()
    assert result["source_prepared_count"]==0
    assert "profile_already_linked" in [x["reason"] for x in result["deferred"]]
    convert.assert_not_called()

def test_invalid_maximum_no_effect(setup):
    for maximum in (0,4,True,"3"):
        with pytest.raises(ValueError):
            m.handle_replenish_preparation({"meta":{},"maximum":maximum})
    setup[1].assert_not_called()

def test_real_handler_chain_preserves_jd(tmp_path, monkeypatch):
    import hashlib
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    from tools.sidecar.server import process_request
    from tools.sidecar.handlers.jobs_leads import liepin_readonly
    leads,profiles=tmp_path/"leads",tmp_path/"profiles"
    leads.mkdir();profiles.mkdir()
    monkeypatch.setattr(m.jobs,"_JOB_LEAD_DIR",leads)
    monkeypatch.setattr(m.jobs,"_JOB_PROFILE_DIR",profiles)
    monkeypatch.setattr(m.jobs,"_SUBMISSIONS_DIR",tmp_path/"submissions")
    profile=tmp_path/"profile.yaml";profile.write_text("city: 上海\n")
    monkeypatch.setattr(m,"profile_path",lambda:profile)
    monkeypatch.setattr(m,"load_preferences",lambda _:{"confirmed_at":"today","items":[{"kind":"primary","text":"Java后端","quote":"private"}]})
    body="职责：Java REST服务。要求：Java和SQL。"
    digest=hashlib.sha256(body.encode()).hexdigest()
    with patch.object(liepin_readonly,"search",return_value={"status":"pass","code":"OK","data":[{"jobId":"123","jobType":"2","jobDetailUrl":"https://www.liepin.com/job/123.shtml","jobName":"Java Engineer","company":"Example","location":"上海-浦东"}]}), patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail",return_value={"jd_text":body,"source_jd_sha256":digest,"fetched_at":"2026-11-18T00:00:00Z",
            "source_url":"https://www.liepin.com/job/123.shtml","platform_job_id":"123"}):
        response=process_request({"id":"source","method":"jobs.replenishPreparation","params":{"meta":{"correlation_id":"test"},"maximum":1}})
    assert "result" in response,response
    result=response["result"]
    assert result["source_prepared_count"]==1,result
    assert result["imported_count"]==1
    fields=parse_simple_yaml(next(profiles.glob("*.yaml")).read_text())["scalars"]
    assert fields["status"]=="draft"
    assert fields["source_jd"]==body and fields["source_jd_sha256"]==digest
    assert fields.get("review_decision","")==""
    assert fields["platform_job_id"]=="123"
    assert result["send_ready"] is False
    # Running again never touches an already linked profile.
    original=next(profiles.glob("*.yaml")).read_bytes()
    with patch.object(liepin_readonly,"search",return_value={"status":"pass","code":"OK","data":[]}):
        m.handle_replenish_preparation({"meta":{"correlation_id":"test"},"maximum":1})
    assert next(profiles.glob("*.yaml")).read_bytes()==original

def test_busy_no_search(setup):
    m._LOCK.acquire()
    try:assert call()["code"]=="replenishment_busy"
    finally:m._LOCK.release()
    setup[1].assert_not_called()

def test_detail_budget_prefers_software_without_changing_search_or_approval(setup):
    lead,search,fetch,convert=setup
    rows=[{**lead,'job_lead_id':f'jl_{i}','platform_job_id':str(i),'url':f'https://www.liepin.com/job/{i}.shtml','position':title}
          for i,title in enumerate(['抗体平台负责人','内部平台负责人','Go 后端负责人'],10)]
    search.return_value={'status':'pass','items':rows,'received_count':3,'imported_count':3}
    with patch.object(m,'_read_current',side_effect=lambda key:dict(next(row for row in rows if row['job_lead_id']==key))):
        result=m.handle_replenish_preparation({'meta':{'correlation_id':'priority'},'maximum':1})
    assert fetch.call_args.args[0]['job_lead_id']=='jl_12'
    assert search.call_count==1 and fetch.call_count==1 and convert.call_count==1
    assert search.call_args.args[0]['keyword']=='Java后端'
    assert result['received_count']==3 and result['source_prepared_count']==1
    assert result['send_ready'] is False
    assert {r['job_lead_id'] for r in result['deferred']}=={'jl_10','jl_11'}
    assert all(r['reason']=='detail_budget' for r in result['deferred'])


@pytest.mark.parametrize("success_before_challenge", [False, True])
def test_security_challenge_stops_all_remaining_replenish_requests(setup, success_before_challenge):
    lead, search, fetch, convert = setup
    records = {
        "prior": {**lead, "job_lead_id":"prior", "platform_job_id":"10"},
        "challenged": {**lead, "job_lead_id":"challenged", "platform_job_id":"11"},
        "same_identity": {**lead, "job_lead_id":"same_identity", "platform_job_id":"11"},
        "other_city": {**lead, "job_lead_id":"other_city", "platform_job_id":"12", "location":"杭州"},
        "not_attempted": {**lead, "job_lead_id":"not_attempted", "platform_job_id":"13"},
    }
    order = (["prior"] if success_before_challenge else []) + [
        "challenged", "same_identity", "other_city", "not_attempted"]
    search.return_value = {"status":"pass", "code":"OK", "items":[records[id] for id in order],
                           "received_count":len(order), "imported_count":len(order)}
    # Preserve given order to independently verify exact requests and no future query.
    query_plan = {"city":"上海", "queries":[{"query":"First"}] + ([{"query":"Second"}] if success_before_challenge else [])}
    fetch.side_effect = ([{"status":"pass","code":"OK"}] if success_before_challenge else []) + [
        {"status":"blocked","code":"SECURITY_CHALLENGE","message":"raw-fixture-never-forwarded"},
        {"status":"pass","code":"OK"}]
    with (patch.object(m,"_read_current",side_effect=lambda id:records[id]),
          patch.object(m,"_query_plan",return_value=query_plan),
          patch.object(m,"prioritize_search_results",side_effect=lambda items,_:items)):
        result = call()
    expected = ["prior","challenged"] if success_before_challenge else ["challenged"]
    assert [c.args[0]["job_lead_id"] for c in fetch.call_args_list] == expected
    assert search.call_count == 1 and result["queries"] == ["First"]
    assert convert.call_count == int(success_before_challenge)
    assert result["source_prepared_count"] == int(success_before_challenge)
    assert result["errors"] == [{"stage":"detail","job_lead_id":"challenged","code":"SECURITY_CHALLENGE"}]
    assert {item["job_lead_id"]:item["reason"] for item in result["deferred"]} == {
        "same_identity":"duplicate_job","other_city":"city_mismatch","not_attempted":"detail_security_deferred"}
    assert not result["send_ready"] and "raw-fixture-never-forwarded" not in str(result)


@pytest.mark.parametrize("reason,exposed", [
    ("access_required", "access_required"),
    ("source_reports_unavailable", "source_reports_unavailable"),
    ("raw-private-reason", None),
    (None, None),
])
def test_detail_observations_are_whitelisted_in_transient_replenishment_receipt(setup, reason, exposed):
    _, _, fetch, convert = setup
    fetch.return_value = {"status":"blocked", "code":"JOB_DETAIL_UNAVAILABLE", "detail_reason":reason,
                          "message":"private failure body"}
    result = call()
    obs = result["errors"][0]
    assert obs["code"] == "JOB_DETAIL_UNAVAILABLE" and obs.get("detail_reason") == exposed
    assert "private" not in str(result) and not result["send_ready"]
    convert.assert_not_called()


@pytest.mark.parametrize("case,maximum,expected", [
    ("distinct",3,["s:Java后端:0","d:1","d:2","s:Go 后端:0","d:4"]),
    ("overlap",2,["s:Java后端:0","d:1","s:Go 后端:0","d:2"]),
    ("shared_only",3,["s:Java后端:0","d:1","d:2","s:Go 后端:0","d:3"]),
    ("empty_second",3,["s:Java后端:0","d:1","d:2","s:Go 后端:0","d:3"]),
    ("one_slot",1,["s:Java后端:0","d:1"]),
    ("one_query",3,["s:Java后端:0","d:1","s:Java后端:1","d:4"]),
    ("auth_second",3,["s:Java后端:0","d:1","d:2","s:Go 后端:0"]),
    ("safety_first",3,["s:Java后端:0","d:1"]),
    ("login_first",3,["s:Java后端:0","d:1"]),
    ("challenge_second",3,["s:Java后端:0","d:1","d:2"]),
])
def test_query_lane_preserves_distinct_sources_and_stops_on_access(tmp_path, monkeypatch, case, maximum, expected):
    import hashlib
    from tools.infra.liepin_job_detail import LiepinJobDetailError
    from tools.sidecar.server import process_request
    from tools.sidecar.handlers.jobs_leads import liepin_readonly

    leads,profiles=tmp_path/"leads",tmp_path/"profiles"
    leads.mkdir();profiles.mkdir()
    monkeypatch.setattr(m.jobs,"_JOB_LEAD_DIR",leads)
    monkeypatch.setattr(m.jobs,"_JOB_PROFILE_DIR",profiles)
    monkeypatch.setattr(m.jobs,"_SUBMISSIONS_DIR",tmp_path/"submissions")
    profile=tmp_path/"profile.yaml";profile.write_text("city: 上海\n")
    monkeypatch.setattr(m,"profile_path",lambda:profile)
    preferences=[{"kind":"primary","text":name,"quote":"fixture"} for name in
                 (["Java后端"] if case=="one_query" else ["Java后端","Go 后端"])]
    monkeypatch.setattr(m,"load_preferences",lambda _:{"confirmed_at":"today","items":preferences})
    calls=[]
    def row(id,city="上海-浦东"):
        return {"jobId":str(id),"jobType":"2","jobDetailUrl":f"https://www.liepin.com/job/{id}.shtml",
                "jobName":"Backend Engineer","company":"Example","location":city}
    def search(keyword,page=0,**filters):
        assert filters["address"]=="上海"
        calls.append(f"s:{keyword}:{page}")
        first=keyword=="Java后端" and page==0
        if not first and case=="auth_second":
            return {"status":"blocked","code":"AUTH_INVALID"}
        rows=([row(1)] if case=="one_query" else [row(1),row(2),row(3)]) if first else (
            [] if case=="empty_second" else [row(2)] if case=="shared_only" else [row(5,"杭州"),row(2),row(4)])
        if case=="one_query" and not first:
            rows=[row(4)]
        return {"status":"pass","code":"OK","data":rows}
    def fetch(url,expected_job_id):
        calls.append(f"d:{expected_job_id}")
        if (case,expected_job_id) in {("safety_first","1"),("challenge_second","2")}:
            raise LiepinJobDetailError("SECURITY_CHALLENGE")
        if case=="login_first":
            raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE",detail_reason="access_required")
        body="职责：Java REST 服务。要求：Java 和 SQL。"
        return {"jd_text":body,"source_jd_sha256":hashlib.sha256(body.encode()).hexdigest(),
                "fetched_at":"2026-11-18T00:00:00Z","source_url":url,"platform_job_id":expected_job_id}
    with patch.object(liepin_readonly,"search",side_effect=search), patch("tools.infra.liepin_job_detail.fetch_liepin_job_detail",side_effect=fetch):
        reply=process_request({"id":"source","method":"jobs.replenishPreparation",
                               "params":{"maximum":maximum,"meta":{"correlation_id":"route-test"}}})
    assert "result" in reply,reply
    assert calls==expected
    result=reply["result"]
    assert result["send_ready"] is False
    if case=="auth_second":
        assert result["errors"]==[{"stage":"search","code":"AUTH_INVALID"}]
        assert any(row["reason"]=="detail_search_deferred" for row in result["deferred"])
    if case=="login_first":
        assert result["errors"][0]["detail_reason"]=="access_required"
        assert all(row["reason"]=="detail_security_deferred" for row in result["deferred"])
    assert len(list(profiles.glob("*.yaml")))==result["source_prepared_count"]
    assert all(not m.jobs._read_yaml_doc(path)["scalars"].get("review_decision") for path in profiles.glob("*.yaml"))
