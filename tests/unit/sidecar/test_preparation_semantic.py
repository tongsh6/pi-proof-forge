import json
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import Mock

import pytest


def module():
    assert find_spec('tools.sidecar.handlers.preparation_semantic'), 'advisory semantic wrapper missing'
    from tools.sidecar.handlers import preparation_semantic
    return preparation_semantic


@pytest.fixture
def setup(tmp_path, monkeypatch):
    m=module()
    monkeypatch.setattr(m.jobs,'_JOB_PROFILE_DIR',tmp_path/'job_profiles')
    profile=tmp_path/'job_profiles'/'jp_test.yaml';profile.parent.mkdir();profile.write_text('unchanged')
    snap={str(profile):'fixture-hash'}
    direction={'status':'needs_review','reason':'corrected','jd_quote':'original'}
    inputs={'job_path':profile,'personal_profile':tmp_path/'personal.yaml','evidence_files':[tmp_path/'ec1.yaml',tmp_path/'ec2.yaml'],
            'snapshot':snap,'direction':direction,'pool':{'card_count':2,'source_freshness_unverified_count':1,'verified_source_count':1}}
    monkeypatch.setattr(m,'_inputs',lambda _:inputs)
    monkeypatch.setattr(m,'load_llm_config',lambda:{'provider':'openai_compatible','base_url':m.SPLASH,'model':'local/test','api_key_for_request':''})
    result={'card_reviews':[{'id':'ec1'}],'reviewed_card_ids':['ec1','ec2'],'degraded_card_ids':['ec2'],
            'degraded_check_ids':['q1'],'criterion_assessments':[{'requirement_id':'q1','status':'insufficient'}],
            'assessments':[{'requirement_id':'r1','status':'insufficient','reason':'degraded','citations':[]}],
            'assessment_visibility':{'scope':'bounded_fact_subset_not_exhaustive','visible_fact_count':1,'omitted_fact_count':9},
            'direction_review':{'status':'excluded','reason':'old wrong direction'},'statistics':{}}
    engine=Mock(return_value=result);monkeypatch.setattr(m,'run_semantic_matching',engine)
    return m,inputs,engine,result


def test_partial_independent_audit_keeps_corrected_direction_and_degraded_is_unassessed(setup):
    m,inputs,engine,_=setup
    r=m.handle_match_preparation({'meta':{'correlation_id':'t'},'job_profile_id':'jp_test'})
    assert r['status']=='partial' and r['scope']=='advisory_partial' and not r['send_ready']
    assert r['reviewed_card_count']==1 and r['eligible_card_count']==2
    assert r['direction']['status']=='needs_review'
    assert r['assessments'][0]['status']=='unassessed'
    assert engine.call_args.kwargs['evidence_files']==inputs['evidence_files']
    assert inputs['job_path'].read_text()=='unchanged'
    saved=m.read_semantic_preparation('jp_test')
    assert saved['status']=='partial' and saved['input_fresh'] is True


def test_stage_budget_reserves_two_actual_calls_and_reuses_direction(setup):
    m,inputs,engine,raw=setup
    def capture(**kw):
        assert kw['advisory'] is True and kw['reused_direction']==inputs['direction']
        client=kw['client'];hook=kw['before_model_call']
        client.model_calls=1;hook('recall')
        client.model_calls=2
        with pytest.raises(ValueError,match='semantic_stage_budget_deferred'):hook('recall')
        hook('assess')
        assert client.budget_exhausted
        return raw
    engine.side_effect=capture
    result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert result['status']=='partial'
    assert engine.call_count==1
    assert engine.call_args.kwargs.get('advisory') is True
    assert result['code']=='semantic_budget_exhausted'


def test_timeout_after_recall_reservation_remains_timeout(setup):
    m,_,engine,_=setup
    def timed(**kw):
        kw['client'].budget_exhausted=True
        kw['client'].provider_timeout=True
        return engine.return_value
    engine.side_effect=timed
    result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert result['code']=='semantic_provider_timeout' and not result['continuation_needed']


def test_only_unfinished_parent_loses_judgment(setup):
    m,_,_,raw=setup
    raw['requirement_checks']=[{'id':'q1','parent_id':'r1'},{'id':'q2','parent_id':'r2'},{'id':'q3','parent_id':'r3'}]
    raw['budget_deferred_check_ids']=['q3']
    raw['budget_deferred_card_ids']=['ec3']
    raw['assessments']=[
        {'requirement_id':'r1','status':'insufficient','citations':[]},
        {'requirement_id':'r2','status':'partial','citations':[]},
        {'requirement_id':'r3','status':'insufficient','citations':[]}]
    result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert [r['status'] for r in result['assessments']]==['unassessed','partial','unassessed']
    assert result['degraded_check_count']==1 and result['deferred_check_count']==1
    assert result['unassessed_check_count']==2 and result['deferred_card_count']==1
    assert result['unreviewed_card_count']==1


@pytest.mark.parametrize('fault',['none','snapshot','contract','digest','schema','not_fresh','malformed_ids','unknown_policy'])
def test_prior_completed_hint_requires_current_valid_audit(setup,fault):
    m,inputs,engine,raw=setup
    raw['completed_check_ids']=['q1','q1','q2']
    m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    path=m._audit_path('jp_test');record=json.loads(path.read_text())
    if fault=='snapshot':record['snapshot']={'changed':'hash'}
    if fault=='contract':record['snapshot']={**inputs['snapshot'],'contract':'old-contract'}
    if fault=='schema':record['schema_version']=0
    if fault=='not_fresh':record['summary']['input_fresh']=False
    if fault=='malformed_ids':record['result']['completed_check_ids']={'q1':'bad'}
    if fault=='unknown_policy':record['result']['assessment_schedule']={'policy':'unknown','checked_check_ids':['q1']}
    record['digest']=m._record_digest(record)
    if fault=='digest':record['digest']='broken'
    path.write_text(json.dumps(record))
    expected=['q1','q2'] if fault=='none' else []
    assert m._previous_completed_hint('jp_test',inputs['snapshot'])==expected


def test_fresh_cumulative_checked_history_is_hint_not_current_result(setup):
    m,inputs,_,raw=setup
    raw['completed_check_ids']=['q3']
    raw['assessment_schedule']={'policy':'pending_source_requirements_v1','checked_check_ids':['q1','q2','q3']}
    result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert m._previous_completed_hint('jp_test',inputs['snapshot'])==['q1','q2','q3']
    assert result['match_outcome']['completed_check_count']==0
    assert not result['continuation_needed']


def test_budget_failure_saved_but_does_not_authorize_continuation(setup):
    m,_,engine,_=setup
    def budget(**kw):
        kw['client'].budget_exhausted=True
        kw['cache_dir'].mkdir(parents=True,exist_ok=True)
        (kw['cache_dir']/'progress.json').write_text('{"validated":true}')
        raise ValueError('semantic_all_cards_degraded')
    engine.side_effect=budget
    r=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert r['continuation_needed'] is False and r['code']=='semantic_budget_exhausted'
    assert m.read_semantic_preparation('jp_test')['status']=='partial'


def test_no_cache_progress_stops_automatic_continuation(setup):
    m,_,engine,_=setup
    def budget(**kw):
        kw['client'].budget_exhausted=True
        raise ValueError('semantic_all_cards_degraded')
    engine.side_effect=budget
    result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert result['budget_exhausted'] and not result['continuation_needed']
    assert result['cache_progress_count']==0


def test_provider_timeout_is_not_budget_or_capability_failure(setup):
    m,_,engine,_=setup
    def timed(**kw):
        kw['client'].provider_timeout=True
        raise ValueError('semantic_all_cards_degraded')
    engine.side_effect=timed
    r=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert r['code']=='semantic_provider_timeout' and not r['continuation_needed']


def test_input_change_prevents_new_result_reuse_and_preserves_profile(setup, monkeypatch):
    m,inputs,engine,_=setup
    def change(**kw):
        inputs['snapshot']={'changed':'hash'}
        return engine.return_value
    original=dict(inputs['snapshot'])
    n=0
    def load(_):
        nonlocal n
        n+=1
        return {**inputs,'snapshot':original if n<=2 else {'changed':'hash'}}
    monkeypatch.setattr(m,'_inputs',load);engine.side_effect=change
    r=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert r['code']=='semantic_inputs_changed'
    assert not r['input_fresh'] and not r['assessments']


def test_owner_change_before_network_blocks_client_and_engine(setup,monkeypatch):
    m,inputs,engine,_=setup
    first={**inputs,'snapshot':dict(inputs['snapshot'])}
    changed={**inputs,'snapshot':{'owner_changed':'new'}}
    monkeypatch.setattr(m,'_inputs',Mock(side_effect=[first,changed]))
    client=Mock();monkeypatch.setattr(m,'BoundedLocalClient',client)
    result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert result['status']=='blocked' and result['code']=='semantic_inputs_changed'
    assert result['model_calls']==0 and not result['input_fresh']
    client.assert_not_called();engine.assert_not_called()
    assert not m._audit_path('jp_test').exists()


def test_remote_config_never_calls_engine(setup, monkeypatch):
    m,_,engine,_=setup
    monkeypatch.setattr(m,'load_llm_config',lambda:{'provider':'openai_compatible','base_url':'https://remote.example','model':'m'})
    r=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert r['status']=='blocked' and r['code']=='local_splash_required'
    engine.assert_not_called()


def test_reader_detects_stale_and_tampered_audit(setup,monkeypatch):
    m,inputs,_,_=setup
    m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    inputs['snapshot']={'changed':'hash'}
    assert m.read_semantic_preparation('jp_test')['status']=='stale'
    path=m._audit_path('jp_test');record=json.loads(path.read_text());record['summary']['code']='tampered'
    path.write_text(json.dumps(record))
    assert m.read_semantic_preparation('jp_test')['status']=='invalid'




@pytest.mark.parametrize(("mode", "expected_wire"),
                         [("missing", None), (None, None), (False, "none"), (True, "low")])
def test_l3b_preparation_settings_reach_bounded_serialized_request(setup, tmp_path, monkeypatch, mode, expected_wire):
    from io import BytesIO
    from tools.infra.llm import bounded_local
    from tools.sidecar.handlers._shared.llm_config import load_llm_config
    from tools.sidecar.handlers.settings import handle_settings_update

    m, _, engine, raw = setup
    monkeypatch.setenv("PPF_POLICY_PATH", str(tmp_path / "policy.yaml"))
    monkeypatch.setenv("LLM_THINKING", "on")
    monkeypatch.setenv("LLM_THINKING_EFFORT", "max")
    payload = {"provider": "openai_compatible", "base_url": m.SPLASH, "model": "synthetic-model",
               "thinking_effort": "low"}
    if mode != "missing":
        payload["thinking_enabled"] = mode
    assert handle_settings_update({"meta": {"correlation_id": "bounded-thinking"},
                                   "section": "llm_config", "payload": payload})["saved"]
    monkeypatch.setattr(m, "load_llm_config", load_llm_config)
    opener = Mock()
    opener.open.side_effect = lambda *_args, **_kwargs: BytesIO(b"{}")
    monkeypatch.setattr(bounded_local.request, "build_opener", lambda *_args: opener)

    def consume(**kwargs):
        client = kwargs["client"]
        client.post_json(client.chat_completions_url, {
            "model": payload["model"], "messages": [], "response_format": {"type": "json_object"},
        })
        return raw

    engine.side_effect = consume
    result = m.handle_match_preparation({"meta": {}, "job_profile_id": "jp_test"})
    assert result["status"] == "partial"
    assert opener.open.call_count == 1
    req = opener.open.call_args.args[0]
    assert req.full_url == m.SPLASH + "/chat/completions"
    wire = json.loads(req.data.decode("utf-8"))
    assert wire.get("reasoning_effort") == expected_wire
    if expected_wire is None:
        assert "reasoning_effort" not in wire
    assert engine.call_args.kwargs["client"].model_calls == 1
    assert "thinking" not in wire


def test_client_max_four_no_transport_retry(monkeypatch):
    m=module()
    response=Mock();response.read.return_value=b'{}';response.close.return_value=None
    opener=Mock();opener.open.return_value=response
    from tools.infra.llm import bounded_local
    monkeypatch.setattr(bounded_local.request,'build_opener',lambda *a:opener)
    c=m.BoundedLocalClient(model='m',api_key='')
    for _ in range(4):
        c.post_json(c.chat_completions_url,{'model':'m','messages':[]})
    with pytest.raises(ValueError,match='semantic_budget_exhausted'):
        c.post_json(c.chat_completions_url,{'model':'m','messages':[]})
    assert opener.open.call_count==4 and c.model_calls==4 and c.budget_exhausted

def test_summary_uses_real_fact_text_not_model_quote(setup):
    m,_,_,raw=setup
    raw['degraded_check_ids']=[]
    raw['requirements']=[{'id':'r1','text':'Know SQL'}]
    raw['facts']={'fact1':{'source_id':'ec1','text':'Original reviewed fact'}}
    raw['assessments']=[{'requirement_id':'r1','status':'supported','reason':'source','citations':[{'fact_id':'fact1','quote':'model invention'}]}]
    r=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert r['assessments'][0]['requirement_text']=='Know SQL'
    assert r['assessments'][0]['citations'][0]['quote']=='Original reviewed fact'
    assert r['assessment_counts']['supported']==1


def test_timeout_and_deadline_stop_without_retry(monkeypatch):
    m=module()
    opener=Mock();opener.open.side_effect=TimeoutError()
    from tools.infra.llm import bounded_local
    monkeypatch.setattr(bounded_local.request,'build_opener',lambda *a:opener)
    c=m.BoundedLocalClient(model='m',api_key='')
    for _ in range(2):
        with pytest.raises(ValueError,match='semantic_provider_timeout'):
            c.post_json(c.chat_completions_url,{'model':'m','messages':[]})
    assert opener.open.call_count==1 and not c.budget_exhausted
    c=m.BoundedLocalClient(model='m',api_key='');c.deadline=0
    with pytest.raises(ValueError,match='semantic_budget_exhausted'):
        c.post_json(c.chat_completions_url,{'model':'m','messages':[]})
    assert c.model_calls==0


def test_response_read_timeout_closes_and_blocks_later_requests(monkeypatch):
    from tools.infra.llm import bounded_local
    response=Mock();response.read.side_effect=TimeoutError()
    opener=Mock();opener.open.return_value=response
    monkeypatch.setattr(bounded_local.request,'build_opener',lambda *a:opener)
    client=bounded_local.BoundedLocalClient(model='m',api_key='')
    for _ in range(2):
        with pytest.raises(ValueError,match='semantic_provider_timeout'):
            client.post_json(client.chat_completions_url,{'model':'m','messages':[]})
    assert client.provider_timeout and not client.budget_exhausted
    assert client.model_calls==1 and opener.open.call_count==1
    response.close.assert_called_once()


def test_inputs_require_confirmed_career_and_include_whole_pool(tmp_path,monkeypatch):
    m=module()
    monkeypatch.setattr(m.jobs,'_JOB_PROFILE_DIR',tmp_path/'job_profiles')
    monkeypatch.setattr(m.jobs,'_JOB_LEAD_DIR',tmp_path/'job_leads')
    monkeypatch.setattr(m.jobs,'_EVIDENCE_CARD_DIR',tmp_path/'evidence_cards')
    m.jobs._EVIDENCE_CARD_DIR.mkdir()
    personal=tmp_path/'personal.yaml';personal.write_text('profile')
    material=tmp_path/'materials';material.mkdir();(material/'preferences.md').write_text('preferences')
    monkeypatch.setattr(m,'profile_path',lambda:personal)
    monkeypatch.setattr(m,'materials_dir_for',lambda _:material)
    monkeypatch.setattr(m,'load_preferences',lambda _:{'revision':'r1','source':{'filename':'preferences.md'}})
    monkeypatch.setattr(m,'describe_preparation',lambda *a,**kw:{'state':'fresh','requirements_grounded':True,'reason':'preparation_saved_unapproved','direction':{'status':'needs_review'}})
    monkeypatch.setattr(m,'load_career_profile',lambda _:{'career_status':{'reviewed':False}})
    m.jobs._write_job_profile_file(m.jobs._JOB_PROFILE_DIR/'jp_test.yaml',{'job_lead_id':'jl_test'})
    m.jobs._write_job_lead_file(m.jobs._JOB_LEAD_DIR/'jl_test.yaml',{'id':'jl_test'})
    with pytest.raises(ValueError,match='semantic_career_unconfirmed'):m._inputs('jp_test')
    monkeypatch.setattr(m,'load_career_profile',lambda _:{'career_status':{'reviewed':True}})
    for name in ['ec1','ec2','draft']:
        (m.jobs._EVIDENCE_CARD_DIR/(name+'.yaml')).write_text('id: '+name+'\ntitle: Real project\nstatus: '+('draft' if name=='draft' else 'saved_eligible')+'\ncandidate_pool_eligible: true\nresults:\n  - result\nartifacts:\n  - source.md\n')
    (m.jobs._EVIDENCE_CARD_DIR/'broken.yaml').write_bytes(b'\xff')
    monkeypatch.setattr(m.jobs,'_load_precheck_corpus',lambda:{'cards':[{'id':'ec1'},{'id':'ec2'}],'card_count':2})
    monkeypatch.setattr(m,'validated_source_inputs',lambda *a:{})
    result=m._inputs('jp_test')
    assert [p.stem for p in result['evidence_files']]==['ec1','ec2']
    assert str((m.jobs._EVIDENCE_CARD_DIR/'broken.yaml').resolve()) in result['snapshot']
    assert str((material/'preferences.md').resolve()) in result['snapshot']
    monkeypatch.setattr(m,'describe_preparation',lambda *a,**kw:{'state':'stale','requirements_grounded':False})
    with pytest.raises(ValueError,match='semantic_preparation_not_fresh_grounded'):m._inputs('jp_test')

@pytest.mark.parametrize("historical",[False,True])
@pytest.mark.parametrize("last_card_has_source",[False,True])
def test_inputs_keep_jd_requirement_bindings_independent_of_evidence_sources(
        tmp_path,monkeypatch,historical,last_card_has_source):
    """A final card's source map must never replace JD clause provenance."""
    import hashlib
    m=module()
    for attr,name in (('_JOB_PROFILE_DIR','job_profiles'),('_JOB_LEAD_DIR','job_leads'),
                      ('_EVIDENCE_CARD_DIR','evidence_cards')):
        monkeypatch.setattr(m.jobs,attr,tmp_path/name)
    m.jobs._EVIDENCE_CARD_DIR.mkdir()
    personal=tmp_path/'personal.yaml';personal.write_text('profile')
    material=tmp_path/'materials';material.mkdir()
    (material/'preferences.md').write_text('preferences')
    monkeypatch.setattr(m,'profile_path',lambda:personal)
    monkeypatch.setattr(m,'materials_dir_for',lambda _:material)
    monkeypatch.setattr(m,'load_preferences',lambda _:{
        'revision':'r1','confirmed_at':'now','source':{'filename':'preferences.md'}})
    monkeypatch.setattr(m,'load_career_profile',lambda _:{'career_status':{'reviewed':True}})
    monkeypatch.setattr(m,'describe_preparation',lambda *a,**kw:{
        'state':'fresh','requirements_grounded':True,'reason':'preparation_saved_unapproved',
        'direction':{'status':'needs_review'}})
    body='任职要求\n1. 核心技术栈硬性要求\n（1）精通Java或Python\n（2）有迁移经验优先\n2. 综合能力\n沟通能力'
    def row(kind,index,quote):
        start=body.index(quote)
        return {'kind':kind,'index':index,'quote':quote,'start':start,'end':start+len(quote)}
    sources=[row('must_have',0,'精通Java或Python'),row('nice_to_have',0,'有迁移经验优先'),
             row('must_have',1,'沟通能力')]
    job_fields={'job_lead_id':'jl_test','source_jd':body,
                'preparation_json':json.dumps({'requirement_sources':sources},ensure_ascii=False)}
    m.jobs._write_job_profile_file(m.jobs._JOB_PROFILE_DIR/'jp_test.yaml',job_fields)
    m.jobs._write_job_lead_file(m.jobs._JOB_LEAD_DIR/'jl_test.yaml',{'id':'jl_test'})
    proof=material/'source.md';proof.write_text('evidence')
    fingerprints=json.dumps({'proof':{'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}})
    for name in ['ec1','ec2']:
        (m.jobs._EVIDENCE_CARD_DIR/(name+'.yaml')).write_text(
            f'id: {name}\ntitle: Real project\nstatus: saved_eligible\ncandidate_pool_eligible: true\n'
            f'source_material_fingerprints_json: {json.dumps(fingerprints)}\n'
            'results:\n  - result\nartifacts:\n  - source.md\n')
    monkeypatch.setattr(m,'validated_source_inputs',lambda doc,_:
        {'material:proof':proof} if doc['scalars']['id']=='ec1' or last_card_has_source else {})
    options={'historical_validator':lambda *_:sources} if historical else {}
    result=m._inputs('jp_test',**options)
    assert len(result['evidence_files'])==2
    assert result['pool']['verified_source_count']==1+last_card_has_source
    binding,=result['requirement_section_bindings']
    assert binding['kind']=='must_have' and binding['index']==0
    assert binding['quote']=='精通Java或Python'
    assert binding['source_jd_sha256']==hashlib.sha256(body.encode()).hexdigest()
    for key in ('heading','child'):
        span=binding[key]
        assert body[span['start']:span['end']]==span['quote']


@pytest.mark.parametrize("audit", ["absent", "fresh", "stale", "timeout", "malformed", "broken_symlink"])
def test_start_match_only_if_no_audit_was_saved(setup, audit):
    m, inputs, engine, _ = setup
    args = {"meta":{"correlation_id":"test"}, "job_profile_id":"jp_test", "start_if_no_audit":True}
    path = m._audit_path("jp_test")
    if audit in ("fresh","stale","timeout"):
        if audit == "timeout":
            def timeout(**kwargs):
                kwargs["client"].provider_timeout = True
                return None
            engine.side_effect = timeout
        original = m.handle_match_preparation({**args, "start_if_no_audit":False})
        assert path.is_file()
        if audit=="timeout":
            assert original["code"] == "semantic_provider_timeout"
        if audit=="stale":
            inputs["snapshot"] = {"changed":"now"}
            assert m.read_semantic_preparation("jp_test")["status"] == "stale"
        engine.reset_mock()
    elif audit in ("malformed","broken_symlink"):
        path.parent.mkdir(parents=True)
        if audit=="malformed":
            path.write_text("invalid")
        else:
            path.symlink_to(path.parent/"missing.json")
        assert m.read_semantic_preparation("jp_test")["status"] == "invalid"
    result = m.handle_match_preparation(args)
    if audit == "absent":
        assert result["status"] == "partial" and path.is_file()
        assert engine.call_count == 1
        repeat = m.handle_match_preparation(args)
        assert repeat["code"] == "semantic_start_unavailable" and engine.call_count == 1
    else:
        assert result["code"] == "semantic_start_unavailable"
        engine.assert_not_called()
    assert result["send_ready"] is False


def test_concurrent_first_start_cannot_dispatch_duplicate_before_audit_write(setup):
    m, _, engine, raw = setup
    args = {"meta":{"correlation_id":"test"}, "job_profile_id":"jp_test", "start_if_no_audit":True}

    def first(**_):
        assert not m.can_start_without_audit("jp_test")
        assert m._read_audit_record("jp_test")["pass_budget"]["state"]=="reserved"
        assert m.handle_match_preparation(args)["code"] == "semantic_preparation_busy"
        return raw

    engine.side_effect = first
    assert m.handle_match_preparation(args)["status"] == "partial"
    assert engine.call_count == 1


def _contract_stale_fixture(setup, *, old_code=None, old_result=True):
    m, inputs, engine, raw = setup
    inputs["snapshot"].update(contract=m.VERSION + ":old:advisory-preparation-v2", preferences_revision="same")
    raw.update(method=m.VERSION, advisory_scope=True, job_profile_id="jp_test",
               completed_check_ids=["q1"], requirement_checks=[{"id":"q1","parent_id":"r1"}],
               criterion_assessments=[{"requirement_id":"q1","status":"supported"}], degraded_check_ids=[])
    original = m.handle_match_preparation({"meta":{"correlation_id":"old"}, "job_profile_id":"jp_test"})
    assert original["input_fresh"]
    path = m._audit_path("jp_test")
    record = json.loads(path.read_text())
    if old_code:
        record["summary"].update(code=old_code)
    if not old_result:
        record["result"] = None
    record["digest"] = m._record_digest(record)
    path.write_text(json.dumps(record))
    inputs["snapshot"]["contract"] = m.VERSION + ":new:advisory-preparation-v2"
    engine.reset_mock()
    return m, inputs, engine, raw, path, record


def test_contract_stale_refresh_uses_expected_digest_once_and_replaces_only_valid_result(setup):
    m, _, engine, _, path, old = _contract_stale_fixture(setup)
    assert m.read_semantic_preparation("jp_test")["contract_recheck_digest"] == old["digest"]
    req = {"meta":{"correlation_id":"new"}, "job_profile_id":"jp_test", "recheck_contract_digest":old["digest"]}
    done = m.handle_match_preparation(req)
    assert done["input_fresh"] and not done["send_ready"]
    assert engine.call_count == 1
    assert engine.call_args.kwargs["previous_completed_check_ids"] == []
    assert json.loads(path.read_text())["snapshot"]["contract"] == m.VERSION + ":new:advisory-preparation-v2"
    stale_click = m.handle_match_preparation(req)
    assert stale_click["code"] == "semantic_contract_recheck_unavailable"
    assert engine.call_count == 1


@pytest.mark.parametrize("old_version,method,scope,completion,expect_action", [
    ("v5", "v5", "advisory-preparation-v2", True, True),
    ("v5", "v5", "advisory-preparation-v2", False, False),
    ("v5", "v4", "advisory-preparation-v2", True, False),
    ("v4", "v4", "advisory-preparation-v2", True, False),
    ("v99", "v99", "advisory-preparation-v2", True, False),
    ("v5", "v5", "wrong:advisory-preparation-v2", True, False),
])
def test_old_engine_contract_only_supports_explicit_recheck_from_its_matching_receipt(
        setup, old_version, method, scope, completion, expect_action):
    m, inputs, engine, _, path, old = _contract_stale_fixture(setup)
    old["snapshot"]["contract"] = f"evidence-semantic-{old_version}:ctx:{scope}"
    method = "evidence-semantic-" + method
    old["result"] = {**old["result"], "method":method, "completed_check_ids":["q1"] if completion else []}
    old["digest"] = m._record_digest(old)
    path.write_text(json.dumps(old))
    unchanged = path.read_bytes()
    inputs["snapshot"]["contract"] = m.VERSION + ":ctx:advisory-preparation-v2"
    historical = m.read_semantic_preparation("jp_test")
    assert historical["status"] == "stale" and historical["input_fresh"] is False
    assert historical["assessments"] == [] and historical["send_ready"] is False
    assert path.read_bytes() == unchanged
    engine.assert_not_called()
    assert ("contract_recheck_digest" in historical) is expect_action
    args = {"meta":{"correlation_id":"current"}, "job_profile_id":"jp_test", "recheck_contract_digest":old["digest"]}
    result = m.handle_match_preparation(args)
    assert result["send_ready"] is False
    if expect_action:
        assert result["input_fresh"] and engine.call_count == 1
        assert engine.call_args.kwargs["previous_completed_check_ids"] == []
        assert json.loads(path.read_text())["result"]["method"] == m.VERSION
        assert m.handle_match_preparation(args)["code"] == "semantic_contract_recheck_unavailable"
        assert engine.call_count == 1
    else:
        assert result["code"] == "semantic_contract_recheck_unavailable"
        engine.assert_not_called()
        assert path.read_bytes() == unchanged


@pytest.mark.parametrize("fault", ["other_snapshot_change", "timeout_record", "failed_old", "ambiguous_null_budget", "manual", "bad_token", "malformed", "engine_failure", "empty_new_result", "timeout_new_result", "inputs_change_midway"])
def test_contract_stale_refresh_retains_prior_audit_on_unsupported_input_or_failed_result(setup, fault):
    m, inputs, engine, raw, path, old = _contract_stale_fixture(
        setup, old_code={"timeout_record":"semantic_provider_timeout", "failed_old":"semantic_engine_unavailable",
                         "ambiguous_null_budget":"semantic_budget_exhausted"}.get(fault),
        old_result=fault != "ambiguous_null_budget")
    if fault == "other_snapshot_change":
        inputs["snapshot"]["preferences_revision"] = "changed"
    elif fault == "manual":
        inputs["job_fields"] = {"import_mode":"manual"}
    elif fault == "malformed":
        path.write_text("{}")
    elif fault == "engine_failure":
        engine.side_effect = RuntimeError("do not expose me")
    elif fault == "empty_new_result":
        engine.return_value = None
    elif fault == "timeout_new_result":
        def timed_out(**kwargs):
            kwargs["client"].provider_timeout = True
            return raw
        engine.side_effect = timed_out
    elif fault == "inputs_change_midway":
        def input_changed(**_):
            inputs["snapshot"] = {**inputs["snapshot"], "preferences_revision":"changed"}
            return raw
        engine.side_effect = input_changed
    before = path.read_bytes()
    if fault in {"other_snapshot_change","timeout_record","failed_old","ambiguous_null_budget","manual","malformed"}:
        assert "contract_recheck_digest" not in m.read_semantic_preparation("jp_test")
    token = "a"*64 if fault == "bad_token" else old["digest"]
    reply = m.handle_match_preparation({"meta":{"correlation_id":"new"}, "job_profile_id":"jp_test", "recheck_contract_digest":token})
    assert not reply["input_fresh"] and not reply["send_ready"]
    assert path.read_bytes() == before
    if fault in {"other_snapshot_change","timeout_record","failed_old","ambiguous_null_budget","manual","bad_token","malformed"}:
        engine.assert_not_called()


def test_contract_recheck_does_not_replace_a_record_updated_during_the_run(setup):
    m, _, engine, raw, path, old = _contract_stale_fixture(setup)
    changed = {**old, "provenance":{**old["provenance"], "created_at":"different"}}
    changed["digest"] = m._record_digest(changed)
    newer = json.dumps(changed).encode()

    def change_during_run(**_):
        path.write_bytes(newer)
        return raw

    engine.side_effect = change_during_run
    reply = m.handle_match_preparation({"meta":{"correlation_id":"new"}, "job_profile_id":"jp_test",
                                       "recheck_contract_digest":old["digest"]})
    assert reply["code"] == "semantic_contract_recheck_unavailable"
    assert path.read_bytes() == newer
    assert engine.call_count == 1


@pytest.mark.parametrize("scenario", ["budget_and_failure", "both_stops_and_failure", "timeout_with_completed", "returned_no_checks", "success"])
def test_match_outcome_separates_engine_stop_checks_and_cache_in_durable_audit(setup, scenario):
    m, _, engine, raw = setup
    raw.update(method=m.VERSION, advisory_scope=True, job_profile_id="jp_test",
        check_assessments=[], completed_check_ids=["q1"],
        requirement_checks=[{"id":"q1","parent_id":"r1"}],
        criterion_assessments=[{"requirement_id":"q1","status":"insufficient"}], degraded_check_ids=[])
    def execute(**kwargs):
        client = kwargs["client"]
        cache = kwargs["cache_dir"]
        cache.mkdir(parents=True, exist_ok=True)
        (cache/"fixture.json").write_text("{}")
        if scenario in {"budget_and_failure", "both_stops_and_failure"}:
            client.budget_exhausted = True
            client.provider_timeout = scenario == "both_stops_and_failure"
            raise RuntimeError("sensitive-fixture")
        if scenario == "timeout_with_completed":
            client.provider_timeout = True
        if scenario == "returned_no_checks":
            raw["completed_check_ids"] = []
        return raw
    engine.side_effect = execute
    result = m.handle_match_preparation({"meta":{"correlation_id":"t"}, "job_profile_id":"jp_test"})
    count = int(scenario in {"timeout_with_completed", "success"})
    failed = scenario in {"budget_and_failure", "both_stops_and_failure"}
    expected = {"engine":"failed" if failed else "returned",
                "reason":"semantic_engine_unavailable" if failed else None,
                "stop_causes":{"budget_and_failure":["budget"],"both_stops_and_failure":["timeout","budget"],
                               "timeout_with_completed":["timeout"]}.get(scenario, []),
                "completed_check_count":count, "usable_current_result":bool(count)}
    assert result["match_outcome"] == expected
    assert result["cache_progress_count"] == 1 and not result["send_ready"]
    assert result["code"] == ("semantic_budget_exhausted" if scenario == "budget_and_failure" else
                              "semantic_provider_timeout" if scenario in {"timeout_with_completed","both_stops_and_failure"} else "semantic_advisory_partial")
    path = m._audit_path("jp_test")
    old = json.loads(path.read_text())
    assert old["summary"]["match_outcome"] == expected
    assert "sensitive-fixture" not in path.read_text()
    assert m.read_semantic_preparation("jp_test")["match_outcome"] == expected


def test_preflight_match_outcome_means_engine_not_entered(setup, monkeypatch):
    m, _, engine, _ = setup
    monkeypatch.setattr(m,"load_llm_config",lambda:{"base_url":"not-local"})
    result = m.handle_match_preparation({"meta":{"correlation_id":"t"}, "job_profile_id":"jp_test"})
    assert result["match_outcome"] == {"engine":"preflight","reason":"local_splash_required",
        "stop_causes":[], "completed_check_count":0, "usable_current_result":False}
    assert not m._audit_path("jp_test").exists()
    engine.assert_not_called()


@pytest.mark.parametrize("kind", ["legacy", "malformed", "corrupt", "stale"])
def test_saved_match_outcome_is_unknown_if_missing_or_untrusted(setup, kind):
    m, inputs, _, _ = setup
    m.handle_match_preparation({"meta":{"correlation_id":"t"}, "job_profile_id":"jp_test"})
    path = m._audit_path("jp_test")
    record = json.loads(path.read_text())
    if kind == "legacy":
        del record["summary"]["match_outcome"]
    if kind in {"malformed","corrupt"}:
        record["summary"]["match_outcome"].update(reason="private malformed data", completed_check_count=999)
    if kind != "corrupt":
        record["digest"] = m._record_digest(record)
    if kind == "stale":
        inputs["snapshot"] = {"changed":"now"}
    path.write_text(json.dumps(record))
    result = m.read_semantic_preparation("jp_test")
    assert "match_outcome" not in result and "private malformed data" not in str(result)
    assert result["status"] == {"stale":"stale", "corrupt":"invalid"}.get(kind,"partial")


def test_snapshot_pass_budget_is_durable_and_cannot_be_replayed(setup):
    m, _, engine, raw = setup
    args = {"meta":{}, "job_profile_id":"jp_test"}
    raw.update(method=m.VERSION, advisory_scope=True, job_profile_id="jp_test",
        completed_check_ids=["q1"], requirement_checks=[{"id":"q1","parent_id":"r1"},{"id":"q2","parent_id":"r2"}],
        criterion_assessments=[{"requirement_id":"q1","status":"insufficient"}],
        degraded_check_ids=[], budget_deferred_check_ids=["q2"])
    consumed=[]
    def execute(**kw):
        record=m._read_audit_record("jp_test")
        budget=record["pass_budget"]
        assert budget["state"]=="reserved"
        consumed.append(budget["used"])
        # Simulate changed cache and a budget stop after producing a valid check.
        cache=kw["cache_dir"];cache.mkdir(parents=True,exist_ok=True)
        (cache/f'{len(consumed)}.json').write_text('{}')
        kw["client"].budget_exhausted=True
        return raw
    engine.side_effect=execute
    first=m.handle_match_preparation({**args,"start_if_no_audit":True})
    assert consumed==[1]
    assert m.handle_match_preparation(args)["code"]=="semantic_continuation_unavailable"
    second=m.handle_match_preparation({**args,"continue_matching_digest":first["continuation_digest"]})
    assert m.handle_match_preparation({**args,"continue_matching_digest":first["continuation_digest"]})["code"]=="semantic_continuation_unavailable"
    third=m.handle_match_preparation({**args,"continue_matching_digest":second["continuation_digest"]})
    assert consumed==[1,2,3] and not third["continuation_needed"]
    assert "continuation_digest" not in third


def _make_continuable(setup):
    m, inputs, engine, raw = setup
    raw.update(method=m.VERSION, advisory_scope=True, job_profile_id="jp_test",
        completed_check_ids=["q1"], requirement_checks=[{"id":"q1","parent_id":"r1"},{"id":"q2","parent_id":"r2"}],
        criterion_assessments=[{"requirement_id":"q1","status":"insufficient"}],
        degraded_check_ids=[], budget_deferred_check_ids=["q2"])
    def first(**kw):
        cache=kw["cache_dir"];cache.mkdir(parents=True,exist_ok=True)
        (cache/'first.json').write_text('{}')
        kw["client"].budget_exhausted=True
        return raw
    engine.side_effect=first
    result=m.handle_match_preparation({"meta":{}, "job_profile_id":"jp_test","start_if_no_audit":True})
    return m, inputs, engine, result["continuation_digest"], m._read_audit_record("jp_test")


@pytest.mark.parametrize("finish", ["timeout","engine_failure","snapshot_changed","audit_changed"])
def test_continuation_never_replaces_last_usable_audit_on_failure(setup, finish, monkeypatch):
    m,inputs,engine,token,old=_make_continuable(setup)
    raw=old["result"]
    def bad(**kw):
        if finish=="timeout":
            kw["client"].provider_timeout=True
            return raw
        if finish=="engine_failure":
            kw["client"].budget_exhausted=True
            raise ValueError("semantic_all_cards_degraded")
        if finish=="snapshot_changed":
            monkeypatch.setattr(m,"_inputs",lambda _: {**inputs,"snapshot":{"changed":"source"}})
        if finish=="audit_changed":
            m._save_audit(m._audit_path("jp_test"), {**old,"competing_fixture":True})
        return raw
    engine.side_effect=bad
    args={"meta":{}, "job_profile_id":"jp_test", "continue_matching_digest":token}
    receipt=m.handle_match_preparation(args)
    final=m._read_audit_record("jp_test")
    assert final["result"]==old["result"] and not receipt["send_ready"]
    if finish=="audit_changed":
        assert final["competing_fixture"] is True and receipt["code"]=="semantic_continuation_unavailable"
    else:
        assert final["pass_budget"]["used"]==2 and final["pass_budget"]["state"]=="closed"
        assert receipt["code"]=="semantic_continuation_retained" and not receipt["continuation_needed"]
        assert "continuation_digest" not in receipt


def test_os_process_crash_cannot_replay_reserved_pass(setup,tmp_path):
    import os
    import subprocess
    import sys
    import time

    m,inputs,_,token,old=_make_continuable(setup)
    entered=tmp_path/'entered'
    script=r"""
import json, os, sys, time
from pathlib import Path
from tools.sidecar.handlers import preparation_semantic as m
profile, snapshot, token, entered = sys.argv[1:]
m.jobs._JOB_PROFILE_DIR = Path(profile).parent
m._inputs=lambda _: {'snapshot':json.loads(snapshot),'job_path':Path(profile),
    'personal_profile':Path(profile),'evidence_files':[],'direction':{},'pool':{}}
m.load_llm_config=lambda: {'provider':'openai_compatible','base_url':m.SPLASH,'model':'test'}
def engine(**kw):
    # The real handler must seal the reservation before giving the engine control.
    budget=m._read_audit_record('jp_test')['pass_budget']
    assert budget['state']=='reserved' and budget['used']==2
    marker=Path(entered)
    assert not marker.exists()
    marker.write_text('reserved before transport')
    time.sleep(30)
    raise AssertionError('interrupted process must be killed by test')
m.run_semantic_matching=engine
result=m.handle_match_preparation({'meta':{},'job_profile_id':'jp_test','continue_matching_digest':token})
print(result['code'])
"""
    args=[sys.executable,"-c",script,str(inputs["job_path"]),json.dumps(inputs["snapshot"]),token,str(entered)]
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}
    worker=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        end=time.monotonic()+8
        while not entered.exists() and worker.poll() is None and time.monotonic()<end:
            time.sleep(.02)
        assert entered.exists()
        competing=subprocess.run(args,env=env,text=True,capture_output=True,timeout=8,check=True)
        assert competing.stdout.strip()=="semantic_continuation_unavailable"
    finally:
        if worker.poll() is None: worker.kill()
        worker.communicate(timeout=8)
    replay=subprocess.run(args,env=env,text=True,capture_output=True,timeout=8,check=True)
    assert replay.stdout.strip()=="semantic_continuation_unavailable"
    reserved=m._read_audit_record("jp_test")
    assert reserved["pass_budget"]["used"]==2 and reserved["pass_budget"]["state"]=="reserved"
    assert reserved["result"]==old["result"]
    assert not m.read_semantic_preparation("jp_test")["continuation_needed"]


def test_old_audit_with_usable_partial_does_not_imply_remaining_passes(setup):
    m,inputs,engine,_,old=_make_continuable(setup)
    legacy=dict(old)
    legacy.pop("pass_budget")
    record=m._save_audit(m._audit_path("jp_test"),legacy)
    engine.reset_mock()
    read=m.read_semantic_preparation("jp_test")
    assert read["match_outcome"]["usable_current_result"] and not read["continuation_needed"]
    result=m.handle_match_preparation({"meta":{},"job_profile_id":"jp_test","continue_matching_digest":record["digest"]})
    assert result["code"]=="semantic_continuation_unavailable"
    assert m._read_audit_record("jp_test")==record
    engine.assert_not_called()


@pytest.mark.parametrize("fault", ["none","finished","exhausted","timeout","no_result","legacy","corrupt","drift"])
def test_daily_only_exposes_current_continuation_through_recovery_action(setup, monkeypatch, tmp_path,fault):
    from tools.sidecar.handlers import jobs_matching, preparation
    m,inputs,engine,token,old=_make_continuable(setup)
    path=m._audit_path("jp_test")
    if fault=="finished":old["result"]["budget_deferred_check_ids"]=[]
    if fault=="exhausted":old["pass_budget"]["used"]=3
    if fault=="timeout":old["summary"]["match_outcome"]["stop_causes"]=["timeout","budget"]
    if fault=="no_result":old["result"]=None
    if fault=="legacy":old.pop("pass_budget")
    if fault=="drift":inputs["snapshot"]={"changed":"evidence"}
    if fault!="none":
        m._save_audit(path,old)
        if fault=="corrupt":path.write_text("{}")
    before=path.read_bytes()
    engine.reset_mock()
    generic=m.read_semantic_preparation("jp_test")
    row={"job_profile_id":"jp_test","title":"Engineer","company":"Synthetic","status":"draft",
        "source":"liepin_official","platform":"liepin","platform_job_id":"42","platform_job_type":"2",
        "source_url":"https://www.liepin.com/job/42.shtml","preparation":{"state":"fresh",
        "requirements_grounded":True,"direction":{"status":"aligned"},"reason":"preparation_saved_unapproved",
        "semantic_matching":generic}}
    monkeypatch.setattr(m.jobs,"_SUBMISSIONS_DIR",tmp_path/"submissions")
    def listing(_, *, continuation_tickets):
        current=m.read_semantic_preparation("jp_test",continuation_tickets=continuation_tickets)
        return {"items":[{**row,"preparation":{**row["preparation"],"semantic_matching":current}}],"next_cursor":None}
    monkeypatch.setattr(jobs_matching,"handle_jobs_list_profiles",listing)
    result=preparation.handle_plan_daily_preparation({"meta":{},"maximum":3})
    saved,=result["deferred"]
    assert saved["recovery_action"]==({"kind":"continue_matching","audit_digest":token} if fault=="none" else None)
    assert "continuation_digest" not in generic
    assert "continuation_digest" not in saved["preparation"]["semantic_matching"]
    assert (token in json.dumps(result)) is (fault=="none")
    assert not result["send_ready"] and path.read_bytes()==before
    engine.assert_not_called()


def test_restart_continuation_executes_real_matcher_once_with_saved_budget(setup, tmp_path):
    import os
    import subprocess
    import sys

    import hashlib
    _,inputs,_,_=setup
    inputs["job_path"].write_text('target_role: Engineer\nmust_have:\n  - 服务恢复\n')
    card=tmp_path/'ec_fixture.yaml'
    card.write_text('id: ec_fixture\ntitle: 服务\nrole_scope: 参与开发\nactions:\n  - 开发了服务恢复流程\nresults:\n  - 通过恢复测试并能完成验证\nartifacts:\n  - fixture\n')
    inputs["snapshot"]={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (inputs["job_path"],card)}
    m,_,_,token,_=_make_continuable(setup)
    script=r"""
import hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
from tools.sidecar.server import process_request
from tools.sidecar.handlers import preparation_semantic as m
from tools.infra import job_preferences
profile, card, snapshot, token = sys.argv[1:]
p=Path(profile)
m.jobs._JOB_PROFILE_DIR=p.parent
def synthetic_inputs(_):
    current={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (p,Path(card))}
    assert current==json.loads(snapshot)
    return {'snapshot':current,'job_path':p,'personal_profile':p.with_name('missing.yaml'),
        'evidence_files':[Path(card)],'direction':None,'pool':{}}
m._inputs=synthetic_inputs
m.load_llm_config=lambda: {'provider':'openai_compatible','base_url':m.SPLASH,'model':'synthetic'}
job_preferences.load_preferences=lambda _:None
stages=[]
init=m.BoundedLocalClient.__init__
def setup_client(self, **kw):
    init(self,**kw)
    def open_fixture(req,timeout):
        assert req.full_url==m.SPLASH+'/chat/completions'
        wire=json.loads(req.data);body=json.loads(wire['messages'][-1]['content'])
        kind=body['stage'];stages.append(kind)
        cite={'fact_id':'ec_fixture:actions:0','quote':'开发了服务恢复流程'}
        if kind=='recall':
            out={'cards':[{'id':'ec_fixture','score':80,'reason':'有证据','requirement_ids':['r1'],'citations':[cite]}]}
        elif kind=='assess':
            out={'assessments':[{'requirement_id':r['id'],'status':'supported','reason':'有证据','citations':[cite]}
                                for r in body['requirements']]}
        else:raise AssertionError(kind)
        data=json.dumps({'choices':[{'message':{'content':json.dumps(out)},'finish_reason':'stop'}]}).encode()
        class Response:
            def read(self):return data
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def close(self):pass
        return Response()
    self._opener=SimpleNamespace(open=open_fixture)
m.BoundedLocalClient.__init__=setup_client
args={'meta':{'correlation_id':'restart-fixture'},'job_profile_id':'jp_test','continue_matching_digest':token}
def call():
    result=process_request({'id':'run','method':'jobs.matchPreparation','params':args})
    assert 'result' in result,result
    return result['result']
one=call()
assert stages==['recall','assess'],(stages,one['code'])
assert one['model_calls']==2 and one['match_outcome']['usable_current_result']
assert not one['continuation_needed'] and not one['send_ready']
assert call()['code']=='semantic_continuation_unavailable' and len(stages)==2
print('real engine, two scripted transport responses, replay denied')
"""
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}
    result=subprocess.run([sys.executable,"-c",script,str(inputs["job_path"]),str(card),
                           json.dumps(inputs["snapshot"]),token],env=env,text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    stored=m._read_audit_record("jp_test")
    assert stored["pass_budget"]["used"]==2
    assert stored["summary"]["match_outcome"]["completed_check_count"]==1
    assert stored["summary"]["send_ready"] is False
