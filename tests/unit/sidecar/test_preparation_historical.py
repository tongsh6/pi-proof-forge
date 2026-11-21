import hashlib
import pytest
from tools.sidecar.handlers import preparation_semantic as semantic
from tools.sidecar.handlers.preparation_historical import validate_historical_source

BODY = '任职要求\n1. 业务接口开发\n加分项\n1. 有迁移经验'
HASH = hashlib.sha256(BODY.encode()).hexdigest()
IDENTITY = {'source':'liepin_official','platform':'liepin','platform_job_id':'123',
            'platform_job_type':'2','jd_origin':'public_page','source_jd':BODY,'source_jd_sha256':HASH}
URL = 'https://www.liepin.com/job/123.shtml'


def records():
    return ({**IDENTITY,'job_lead_id':'jl_test','source_url':URL,'status':'active',
             'review_decision':'approved','reviewed_at':'2026-11-10T01:00:00Z',
             'must_have':['业务接口开发'],'nice_to_have':['有迁移经验']},
            {**IDENTITY,'id':'jl_test','url':URL,'job_profile_id':'jp_test',
             'status':'new','jd_status':'complete_reviewed'})


def test_verbatim_requirements_are_read_from_the_reviewed_target():
    fields, lead = records()
    assert validate_historical_source('jp_test',fields,lead)[0]['quote']=='业务接口开发'


@pytest.mark.parametrize('record,key,value,reason', [
    (0,'status','draft','historical_not_reviewed'),
    (0,'reviewed_at','','historical_not_reviewed'),
    (0,'source_jd','changed','historical_source_binding_invalid'),
    (0,'must_have',['杜撰的要求'],'requirement_source_missing'),
    (1,'job_profile_id','jp_other','historical_source_binding_invalid'),
    (1,'jd_status','full_unreviewed','historical_source_binding_invalid'),
    (1,'platform_job_id','other','historical_source_binding_invalid'),
])
def test_historical_contract_rejects_changed_inputs(record,key,value,reason):
    pair=records()
    pair[record][key]=value
    with pytest.raises(ValueError,match=reason):
        validate_historical_source('jp_test',*pair)

@pytest.mark.parametrize('value',['有迁移经验','接口开发'])
def test_must_have_requires_full_clause_in_qualification_section(value):
    fields, lead = records()
    fields['must_have']=[value]
    with pytest.raises(ValueError,match='historical_requirement_section_invalid'):
        validate_historical_source('jp_test',fields,lead)


@pytest.fixture
def handler_case(tmp_path, monkeypatch):
    from tools.sidecar.handlers import preparation_historical as historical
    from tools.engines.matching.semantic_review import job_requirements, requirement_checks, aggregate_assessments
    from tools.engines.matching.semantic_matching import _facts
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    job=tmp_path/'jp_test.yaml'
    job.write_text('target_role: Backend\ncompany: Test Company\nstatus: active\nreview_decision: approved\n')
    card=tmp_path/'ec_test.yaml'
    card.write_text('title: 接口平台\nrole_scope: 参与开发\nactions:\n  - 参与设计并实现可追溯的业务接口服务\n')
    facts=_facts(card.stem, parse_simple_yaml(card.read_text()))
    monkeypatch.setattr(historical.preview,'_profile_facts',lambda _: {})
    fields, _=records()
    preferences={'items':[{'kind':'primary','text':'业务接口'}]}
    snapshot={str(path.resolve()):hashlib.sha256(path.read_bytes()).hexdigest() for path in (job,card)}
    inputs={'snapshot':snapshot,'job_path':job,'personal_profile':tmp_path/'personal.yaml',
            'evidence_files':[card],'preferences':preferences,'job_fields':fields,
            'pool':{'source_freshness_unverified_count':0},'requirement_section_bindings':[]}
    req=job_requirements(fields['must_have'])
    checks=requirement_checks(req)
    fact_id='ec_test:actions:0'
    criterion=[{'requirement_id':checks[0]['id'],'status':'partial','reason':'部分实践',
                'citations':[{'fact_id':fact_id,'quote':facts[fact_id]['text']}]}]
    raw={'job_profile_id':'jp_test','method':historical.preview.VERSION,'advisory_scope':True,
         'requirements':req,'requirement_checks':checks,'criterion_assessments':criterion,
         'assessments':aggregate_assessments(req,checks,criterion),
         'facts':facts,'completed_check_ids':[checks[0]['id']]}
    monkeypatch.setattr(historical,'_inputs',lambda _:inputs)
    monkeypatch.setattr(semantic,'load_llm_config',lambda:{'provider':'openai_compatible','base_url':semantic.SPLASH,'model':'test'})
    from types import SimpleNamespace
    client=SimpleNamespace(model_calls=0, budget_exhausted=False, provider_timeout=False)
    monkeypatch.setattr(semantic,'BoundedLocalClient',lambda **_:client)
    def direction(preferences, body, shared_client, model, cache_dir):
        assert shared_client is client
        client.model_calls+=1
        return {'status':'aligned','reason':'实际职责','criterion_index':0,'jd_quote':'业务接口开发'}
    monkeypatch.setattr(historical,'assess_direction',direction)
    def match(**kwargs):
        assert kwargs['client'] is client and kwargs['advisory'] is True
        assert kwargs['reused_direction']['status']=='aligned'
        client.model_calls+=1
        kwargs['cache_dir'].joinpath('test-cache').write_text('temporary')
        return raw
    monkeypatch.setattr(semantic,'run_semantic_matching',match)
    return historical,inputs,raw,client


def test_end_to_end_internal_rpc_does_not_change_approval_or_persist_cache(handler_case,tmp_path):
    from tools.sidecar.server import process_request
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result=process_request({'id':'historical','method':'jobs.reviewHistoricalPreparation',
        'params':{'meta':{'correlation_id':'offline'},'job_profile_id':'jp_test'}})['result']
    assert result['status']=='preview'
    assert result['scope']=='historical_internal_quality_only'
    assert result['model_calls']==2
    assert not result['active_target_eligible'] and not result['deliverable'] and not result['send_ready']
    assert '参与设计并实现可追溯的业务接口服务' in result['markdown']
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


@pytest.mark.parametrize('fault,code', [
    ('missing_evidence','semantic_no_eligible_evidence'),
    ('remote','local_splash_required'),
    ('unsupported_claim','preview_audit_invalid'),
    ('incomplete','no_presentable_supported_work'),
    ('source_race','semantic_inputs_changed'),
    ('excluded_fact','historical_preview_excluded_fact'),
])
def test_negative_paths_preserve_approval(handler_case,tmp_path,monkeypatch,fault,code):
    historical,inputs,raw,client=handler_case
    if fault=='missing_evidence':
        def unavailable(_): raise ValueError('semantic_no_eligible_evidence')
        monkeypatch.setattr(historical,'_inputs',unavailable)
    if fault=='remote':
        monkeypatch.setattr(semantic,'load_llm_config',lambda:{'provider':'openai_compatible','base_url':'https://not-local.invalid','model':'test'})
    if fault=='unsupported_claim':
        raw['assessments'][0]['citations'][0]['fact_id']='invented'
    if fault=='incomplete':
        raw['completed_check_ids']=[]
    if fault=='excluded_fact':
        raw['presentation_exclusions']={'ec_test':['missing career provenance']}
    if fault=='source_race':
        responses=iter([inputs,inputs,inputs,{**inputs,'snapshot':{'changed':'yes'}}])
        monkeypatch.setattr(historical,'_inputs',lambda _:next(responses))
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result=historical.handle_review_historical_preparation({'meta':{},'job_profile_id':'jp_test'})
    assert result['status']=='blocked' and result['code']==code
    assert not result['markdown'] and not result['claims'] and not result['send_ready']
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before
    if fault in {'missing_evidence','remote'}:
        assert client.model_calls==0


@pytest.mark.parametrize('job_type,url', [('2','https://www.liepin.com/a/999.shtml'),
    ('1','https://www.liepin.com/a/999.shtml'),('1','https://www.liepin.com/job/123.shtml')])
def test_simultaneously_changed_urls_cannot_cross_route_or_change_headhunter_id(job_type,url):
    fields,lead=records()
    fields.update(platform_job_type=job_type,source_url=url)
    lead.update(platform_job_type=job_type,url=url)
    with pytest.raises(ValueError,match='historical_source_binding_invalid'):
        validate_historical_source('jp_test',fields,lead)


def test_company_display_id_is_not_assumed_to_equal_platform_job_id():
    fields,lead=records()
    fields['source_url']=lead['url']='https://www.liepin.com/job/1985701549.shtml'
    assert validate_historical_source('jp_test',fields,lead)
