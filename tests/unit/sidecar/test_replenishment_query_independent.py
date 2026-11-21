"""Traceable role-only recall; candidate eligibility and budgets stay independent."""
from unittest.mock import Mock
import pytest
from tools.sidecar.handlers import preparation_replenishment as m


@pytest.fixture
def env(tmp_path,monkeypatch):
    profile=tmp_path/"personal_profile.yaml";profile.write_text("city: 上海\n")
    prefs={"confirmed_at":"confirmed","revision":"pref-v1",
           "items":[{"kind":"primary","text":"产品型Tech Lead，负责产品","quote":"PRIVATE_SOURCE"},
                    {"kind":"primary","text":"内部平台负责人，服务内部","quote":"PRIVATE_SOURCE"}]}
    monkeypatch.setattr(m,"profile_path",lambda:profile)
    monkeypatch.setattr(m,"load_preferences",lambda _:prefs)
    monkeypatch.setattr(m,"handle_plan_daily_preparation",lambda _:{"shortfall":3})
    monkeypatch.setattr(m,"_attempted_keys",lambda:set())
    search=Mock(return_value={"status":"pass","items":[],"received_count":0,"imported_count":0})
    fetch=Mock(return_value={"status":"pass"})
    convert=Mock(return_value={"job_profile_id":"jp_new"})
    monkeypatch.setattr(m,"handle_jobs_search_liepin",search)
    monkeypatch.setattr(m,"handle_jobs_fetch_liepin_detail",fetch)
    monkeypatch.setattr(m,"handle_jobs_convert_lead",convert)
    return profile,prefs,search,fetch,convert


def call():return m.handle_replenish_preparation({"meta":{"correlation_id":"test"},"maximum":3})


def row(id,**kw):
    return {"job_lead_id":"jl_"+id,"platform":"liepin","platform_job_type":"2",
            "platform_job_id":id,"url":"https://www.liepin.com/job/"+id+".shtml",
            "source":"liepin_official","status":"new","location":"上海-浦东",
            "position":"后端研发负责人（JVM生态）","company":"Example",**kw}


def test_query_components_are_traceable_and_missing_stack_is_explicit(env):
    profile,prefs,_,_,_=env
    plan=m._query_plan(profile)
    assert plan["technology"] is None
    assert plan["technology_reason"]=="primary_stack_not_structured"
    assert [q["query"] for q in plan["queries"]]==["Tech Lead","平台负责人"]
    for q in plan["queries"]:
        role=q["role"];original=prefs["items"][role["preference_index"]]["text"]
        assert original[role["start"]:role["end"]]==role["text"]
        assert role["preference_revision"]=="pref-v1"
        assert q["city_source"]=={"field":"city","value":"上海"}
        assert q["address"]=="上海"
    assert m._queries(profile)==("上海",["Tech Lead","平台负责人"])


def test_role_only_queries_do_not_send_private_source_quotes(env):
    result=call()
    assert result["query_plan"]["technology"] is None
    calls=[x.args[0] for x in env[2].call_args_list]
    assert [x["keyword"] for x in calls]==["Tech Lead","平台负责人"]
    assert [x["page"] for x in calls]==[0,0]
    assert [x["address"] for x in calls]==["上海","上海"]
    assert "PRIVATE_SOURCE" not in str(calls)
    assert result["send_ready"] is False


@pytest.mark.parametrize("change",["unconfirmed","no_primary"])
def test_unconfirmed_or_missing_primary_stops_before_search(env,change):
    if change=="unconfirmed":env[1]["confirmed_at"]=""
    else:env[1]["items"]=[{"kind":"avoid","text":"客户交付"}]
    assert call()["status"]=="blocked"
    env[2].assert_not_called();env[3].assert_not_called()


def test_alias_role_not_hard_filtered_and_duplicate_linked_attempted_stay_excluded(env,monkeypatch):
    a=row("1");dup={**a,"job_lead_id":"jl_duplicate"}
    linked=row("2",job_profile_id="jp_existing");attempted=row("3")
    d=row("4");e=row("5");extra=row("6")
    rows=[a,dup,linked,attempted,d,e,extra]
    monkeypatch.setattr(m,"_read_current",lambda id:next(dict(r) for r in rows if r["job_lead_id"]==id))
    monkeypatch.setattr(m,"_attempted_keys",lambda:{m._identity(attempted)})
    env[2].return_value={"status":"pass","items":rows,"received_count":7,"imported_count":7}
    result=call()
    assert env[3].call_count==env[4].call_count==3
    assert env[2].call_count<=2
    reasons={x["reason"] for x in result["deferred"]}
    assert {"duplicate_job","profile_already_linked","already_attempted","detail_budget"}<=reasons
    assert "jl_1" in [x["job_lead_id"] for x in result["source_prepared"]]
    assert result["send_ready"] is False


def test_one_role_retains_two_page_cap_with_cross_page_identity_dedup(env,monkeypatch):
    env[1]["items"]=[{"kind":"primary","text":"后端负责人","quote":"PRIVATE_SOURCE"}]
    a=row("1")
    monkeypatch.setattr(m,"_read_current",lambda _:dict(a))
    env[2].return_value={"status":"pass","items":[a],"received_count":1,"imported_count":1}
    result=call()
    assert [x.args[0]["page"] for x in env[2].call_args_list]==[0,1]
    assert env[3].call_count==env[4].call_count==1
    assert any(x["reason"]=="duplicate_job" for x in result["deferred"])


@pytest.mark.parametrize("text",[
    "Tech Lead https://example.test/private",
    "平台负责人 联系15021120000",
    "Tech Lead\n个人信息",
])
def test_short_role_does_not_launder_unsafe_full_preference(env,text):
    env[1]["items"]=[{"kind":"primary","text":text,"quote":"PRIVATE_SOURCE"}]
    assert call()["status"]=="blocked"
    env[2].assert_not_called()


def test_trustworthy_query_does_not_approve_or_semantically_filter_candidate(env,monkeypatch):
    candidate=row("77",position="机械结构研发平台负责人")
    monkeypatch.setattr(m,"_read_current",lambda _:dict(candidate))
    env[2].return_value={"status":"pass","items":[candidate],"received_count":1,"imported_count":1}
    result=call()
    assert result["source_prepared_count"]==1
    assert result["send_ready"] is False
    assert not any(k in result["source_prepared"][0] for k in ("fit","approved","active_target_eligible"))
    assert env[4].call_args.args[0]=={"meta":{"correlation_id":"test"},"job_lead_id":"jl_77"}


@pytest.mark.parametrize("location",["北京",""])
def test_official_address_does_not_bypass_returned_city_validation(env,location):
    candidate=row("81",location=location)
    env[2].return_value={"status":"pass","items":[candidate],"received_count":1,"imported_count":1}
    result=call()
    assert result["source_prepared_count"]==0
    assert result["deferred"]
    env[3].assert_not_called();env[4].assert_not_called()
    assert all(c.args[0]["address"]=="上海" for c in env[2].call_args_list)


def test_normalized_city_is_profile_bound_not_taken_from_keyword(env):
    env[0].write_text("city: 上海 浦东新区\n")
    env[1]["items"]=[{"kind":"primary","text":"Tech Lead","quote":"PRIVATE_SOURCE北京"}]
    result=call()
    assert result["query_plan"]["city"]=="上海"
    assert result["query_plan"]["queries"][0]["city_source"]["value"]=="上海 浦东新区"
    assert all(c.args[0]["keyword"]=="Tech Lead" and c.args[0]["address"]=="上海"
               for c in env[2].call_args_list)

