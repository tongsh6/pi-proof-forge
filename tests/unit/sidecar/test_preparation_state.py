import hashlib
import json
from copy import deepcopy
from importlib.util import find_spec

import pytest

from tools.infra.job_preferences import validate_direction


def helper():
    assert find_spec('tools.engines.discovery.preparation_state'), 'saved preparation reader missing'
    from tools.engines.discovery.preparation_state import describe_preparation, content_fingerprint
    return describe_preparation, content_fingerprint


def case():
    describe, fingerprint = helper()
    body = 'Build Java APIs. Know SQL.'
    digest = hashlib.sha256(body.encode()).hexdigest()
    fields = dict(status='draft', review_decision='', reviewed_at='', source='liepin_official',
                  platform='liepin', platform_job_id='42', platform_job_type='2',
                  job_lead_id='jl_42', source_url='https://www.liepin.com/job/42.shtml',
                  source_jd=body, source_jd_sha256=digest, must_have=['Know SQL.'], nice_to_have=[])
    lead = {**fields, 'id':'jl_42', 'job_profile_id':'jp_42', 'url':fields['source_url'],
            'status':'new', 'jd_status':'full_unreviewed', 'jd_origin':'public_page'}
    lead["jd_capture_json"]=json.dumps({"source_url":lead["url"],"platform_job_id":"42","platform_job_type":"2",
        "source_jd_sha256":digest,"fetched_at":"2026-11-18T00:00:00Z","invalidated":False})
    prefs = {'confirmed_at':'now', 'revision':'r1',
             'items':[{'kind':'primary','text':'Java','quote':'Java'}]}
    direction = {'status':'needs_review','reason':'boundary uncertain','criterion_index':0,
                 'jd_quote':'Java','preference':prefs['items'][0]}
    meta = {'status':'prepared_unapproved','source_jd_sha256':digest,'preferences_revision':'r1',
            'content_fingerprint':fingerprint(fields),'extraction_contract':'verbatim_requirements_v1',
            'assessment_scope':'advisory_not_fit_or_approval','direction':direction,
            'model_direction':direction,'direction_adjustment':'',
            'model':'old-model','provider':'openai_compatible','endpoint':'http://127.0.0.1:8000/v1',
            'requirement_sources':[{'kind':'must_have','index':0,'quote':'Know SQL.','start':body.index('Know SQL.'),'end':body.index('Know SQL.')+len('Know SQL.')}]}
    return fields, lead, prefs, meta


def describe_case(fields, lead, prefs, meta, **kw):
    describe, _ = helper()
    fields = {**fields, 'preparation_json':json.dumps(meta) if isinstance(meta,dict) else meta}
    return describe('jp_42', fields, lead, prefs, validate_direction=validate_direction, **kw)


def test_fresh_means_input_consistency_only_and_does_not_mutate():
    f,l,p,m = case(); before=deepcopy((f,l,p,m))
    r=describe_case(f,l,p,m)
    assert r['state']=='fresh',r
    assert r['scope']=='input_consistency_only' and r['send_ready'] is False
    assert r['direction']['status']=='needs_review'
    assert r['requirements_grounded'] is True and r['requirement_count']==1
    assert (f,l,p,m)==before
    f['updated_at']='changed'
    assert describe_case(f,l,p,m)['state']=='fresh'
    m['model']='another-historical-alias'
    assert describe_case(f,l,p,m)['state']=='fresh'


@pytest.mark.parametrize('field,value',[('source_jd','changed'),('must_have',['changed']),('platform_job_id','99'),('status','active')])
def test_changed_profile_stales_saved_result(field,value):
    f,l,p,m=case();f[field]=value
    assert describe_case(f,l,p,m)['state']=='stale'


@pytest.mark.parametrize('field,value',[('job_profile_id','jp_other'),('source_jd','changed'),('platform_job_type','1')])
def test_changed_source_stales_result(field,value):
    f,l,p,m=case();l[field]=value
    assert describe_case(f,l,p,m)['state']=='stale'


def test_preferences_revision_and_invalid_source_stale():
    f,l,p,m=case();p['revision']='r2'
    assert describe_case(f,l,p,m)['state']=='stale'
    p['revision']='r1'
    assert describe_case(f,l,p,m,preferences_error='preferences_source_unavailable')['state']=='stale'


@pytest.mark.parametrize('mutation',['json','missing','contract','offset','count','old_excluded'])
def test_invalid_metadata_is_not_reused(mutation):
    f,l,p,m=case()
    if mutation=='json':m='{bad'
    elif mutation=='missing':del m['model_direction']
    elif mutation=='contract':m['extraction_contract']='unknown'
    elif mutation=='offset':m['requirement_sources'][0]['start']=0
    elif mutation=='count':m['requirement_sources']=[]
    else:
        m['status']='direction_deferred';m['direction']['status']='excluded';m['requirement_sources']=[]
    r=describe_case(f,l,p,m)
    assert r['state']=='invalid',r
    assert r['direction'] is None and not r['requirements_grounded']


def test_deferred_avoid_can_be_current_without_grounded_requirements():
    f,l,p,m=case();p['items'][0]['kind']='avoid'
    m['direction']['status']='excluded';m['status']='direction_deferred';m['requirement_sources']=[]
    r=describe_case(f,l,p,m)
    assert r['state']=='fresh' and not r['requirements_grounded'] and r['requirement_count']==0



def test_corrected_exclusion_remains_uncertain_not_fit():
    f,l,p,m=case()
    m['model_direction']={**m['direction'],'status':'excluded'}
    m['direction_adjustment']='excluded_without_avoid_evidence'
    r=describe_case(f,l,p,m)
    assert r['state']=='fresh' and r['direction']['status']=='needs_review'
    assert r['send_ready'] is False
    m['direction_adjustment']=''
    assert describe_case(f,l,p,m)['state']=='invalid'


def test_pending_or_successful_attempt_does_not_promote_prepared_draft():
    from tools.engines.discovery.preparation_plan import build_preparation_plan
    f,l,p,m=case()
    row={**f,'job_profile_id':'jp_42','preparation':describe_case(f,l,p,m),'preparation_key':'occupied'}
    r=build_preparation_plan([row],1,attempted_keys=['occupied'])
    assert not r['selected'] and r['shortfall']==1 and r['send_ready'] is False


def test_absent_does_not_need_preferences():
    describe,_=helper()
    assert describe('jp',{},None,None,validate_direction=validate_direction)['state']=='absent'


def test_daily_plan_surfaces_saved_draft_without_promoting_or_reducing_shortfall():
    from tools.engines.discovery.preparation_plan import build_preparation_plan
    f,l,p,m=case();prep=describe_case(f,l,p,m)
    row={**f,'job_profile_id':'jp_42','preparation':prep,'preparation_key':'key',
         'native_pdf_delivery':{'supported':True},'fit_precheck':{'state':'recommended'}}
    r=build_preparation_plan([row],1)
    assert r['selected']==[] and r['shortfall']==1
    assert r['deferred'][0]['preparation']==prep
    assert r['deferred'][0]['reason']=='preparation_saved_unapproved'

def test_list_loads_preferences_once_reuses_no_snapshot_overlap_and_is_read_only(tmp_path, monkeypatch):
    from tools.sidecar.handlers import jobs, jobs_matching as listing
    _, fingerprint = helper()
    f,l,p,m=case()
    monkeypatch.setattr(jobs,'_JOB_PROFILE_DIR',tmp_path/'profiles')
    monkeypatch.setattr(jobs,'_JOB_LEAD_DIR',tmp_path/'leads')
    monkeypatch.setattr(listing,'_load_matching_snapshots',lambda:{})
    monkeypatch.setattr(listing,'_load_precheck_corpus',lambda:{'card_count':1,'text':'know sql','cards':[], 'source_freshness_unverified_count':1,'verified_source_count':0,'excluded_count':2,'excluded_reasons':{'invalid_source':2}})
    loads=[]
    monkeypatch.setattr(listing,'load_preferences',lambda path:loads.append(path) or p)
    for n in (1,2):
        pid=f'jp_{n}';lid=f'jl_{n}'
        ff={**f,'job_lead_id':lid}
        jobs._write_job_profile_file(jobs._JOB_PROFILE_DIR/f'{pid}.yaml',ff)
        ff=jobs._preserved_profile_fields(jobs._read_yaml_doc(jobs._JOB_PROFILE_DIR/f'{pid}.yaml'))
        mm={**m,'content_fingerprint':fingerprint(ff)}
        jobs._write_job_profile_file(jobs._JOB_PROFILE_DIR/f'{pid}.yaml',{**ff,'preparation_json':json.dumps(mm)})
        jobs._write_job_lead_file(jobs._JOB_LEAD_DIR/f'{lid}.yaml',{**l,'id':lid,'job_profile_id':pid})
    before={str(path):path.read_bytes() for path in tmp_path.rglob('*.yaml')}
    rows=listing.handle_jobs_list_profiles({'meta':{'correlation_id':'read'}})['items']
    assert len(loads)==1
    assert all(row['preparation']['state']=='fresh' for row in rows)
    assert all(row['preparation']['evidence_precheck']['source']=='rule' for row in rows)
    assert all(row['preparation']['evidence_precheck']['source_freshness_unverified_count']==1 for row in rows)
    assert all(row['preparation']['evidence_precheck']['excluded_count']==2 for row in rows)
    assert before=={str(path):path.read_bytes() for path in tmp_path.rglob('*.yaml')}
    # Corrupt one lead: neither preparation nor native capability can break all list rows.
    (jobs._JOB_LEAD_DIR/'jl_1.yaml').write_bytes(b'\\xff')
    rows=listing.handle_jobs_list_profiles({'meta':{'correlation_id':'read'}})['items']
    assert len(rows)==2
    assert {row['preparation']['state'] for row in rows}=={'fresh','stale'}
    bad_path=jobs._JOB_PROFILE_DIR/'jp_2.yaml'
    bad_fields=jobs._preserved_profile_fields(jobs._read_yaml_doc(bad_path))
    jobs._write_job_profile_file(bad_path,{**bad_fields,'preparation_json':'{bad'})
    rows=listing.handle_jobs_list_profiles({'meta':{'correlation_id':'read'}})['items']
    assert len(rows)==2
    assert {row['preparation']['state'] for row in rows}=={'invalid','stale'}
    assert all(row['preparation']['evidence_precheck'] is None for row in rows)


def test_list_without_preparation_does_not_load_preferences(tmp_path, monkeypatch):
    from tools.sidecar.handlers import jobs, jobs_matching as listing
    monkeypatch.setattr(jobs,'_JOB_PROFILE_DIR',tmp_path)
    monkeypatch.setattr(listing,'_load_matching_snapshots',lambda:{})
    monkeypatch.setattr(listing,'_load_precheck_corpus',lambda:{'card_count':0,'text':'','cards':[]})
    def fail(_):raise AssertionError('unnecessary preference source read')
    monkeypatch.setattr(listing,'load_preferences',fail)
    jobs._write_job_profile_file(tmp_path/'jp_empty.yaml',{'target_role':'Java'})
    row=listing.handle_jobs_list_profiles({'meta':{'correlation_id':'read'}})['items'][0]
    assert row['preparation']['state']=='absent'


