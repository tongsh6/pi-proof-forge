import hashlib
import json
from pathlib import Path

import pytest

from tools.sidecar.handlers import agent, jobs
from tools.sidecar.server import process_request


@pytest.fixture
def prepared_inputs(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs')
    monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    monkeypatch.setattr(jobs,'_JOB_LEAD_DIR',tmp_path/'job_leads')
    monkeypatch.setattr(jobs,'_JOB_PROFILE_DIR',tmp_path/'job_profiles')
    text='真实来源的测试岗位职责与要求'
    digest=hashlib.sha256(text.encode()).hexdigest()
    lead={'id':'lead-1','source':'liepin_official','platform':'liepin','platform_job_id':'123','platform_job_type':'2',
          'company':'测试公司','position':'测试岗位','url':'https://www.liepin.com/job/123.shtml',
          'source_jd':text,'source_jd_sha256':digest,'jd_status':'complete_reviewed','job_profile_id':'profile-1'}
    jobs._write_job_lead_file(jobs._lead_path('lead-1'),lead)
    jobs._write_job_profile_file(jobs._profile_path('profile-1'),{
       **lead,'target_role':'测试岗位','source_url':lead['url'],'job_lead_id':'lead-1','status':'active',
       'review_decision':'approved','reviewed_at':'2026-09-29','jd_summary':'测试摘要','keywords':['硬件'],
       'must_have':['硬件验证'],'nice_to_have':[],'seniority_signal':[]})
    calls=[]
    def read_resume():
        calls.append('read')
        return {'status':'pass','code':'OK','resume_text':'合成平台简历：仅用于测试'}
    monkeypatch.setattr(jobs.liepin_readonly,'read_resume',read_resume)
    monkeypatch.setattr('tools.infra.liepin_job_detail.fetch_liepin_job_detail',lambda *a,**kw:{'source_jd_sha256':digest})
    monkeypatch.setattr('tools.infra.liepin_default_delivery.LiepinDefaultResumeClient.apply',lambda *_:pytest.fail('准备不得发送'))
    return lead,calls


def prepare(**extra):
    response=process_request({'id':'prepare-test','method':'run.agent.prepareLiepinDefault',
        'params':{'meta':{'correlation_id':'prepare-test'},'job_lead_id':'lead-1',**extra}})
    assert 'result' in response,response
    return response['result']


def test_preparation_uses_server_identity_and_reuses_pending_snapshot(prepared_inputs):
    lead,calls=prepared_inputs
    result=prepare()
    assert result['status']=='ready'
    assert result['job_profile_id']=='profile-1'
    q=json.loads((agent._REVIEW_QUEUE_DIR/(result['run_id']+'.json')).read_text())
    assert q['candidates'][0]['status']=='pending'
    assert q['candidates'][0]['platform_job_id']=='123'
    assert q['candidates'][0]['delivery_kind']=='platform_default'
    assert q['candidates'][0]['matching_score'] is None
    assert '合成平台简历' not in json.dumps(result,ensure_ascii=False)
    repeated=prepare()
    assert repeated['run_id']==result['run_id'] and repeated['reused']
    assert agent.handle_get_pending_review({'meta':{'correlation_id':'x'},'run_id':result['run_id']})['candidates'][0]['snapshot_status']=='ready'


def test_unreviewed_or_excluded_target_is_blocked_before_credential_use(prepared_inputs):
    lead,calls=prepared_inputs
    lead['jd_status']='full_unreviewed'
    jobs._write_job_lead_file(jobs._lead_path('lead-1'),lead)
    assert prepare()['code']=='JOB_REVIEW_REQUIRED'
    assert calls==[]


def test_previously_attempted_job_never_prepares_again(prepared_inputs):
    from tools.channels.base import DeliveryRequest
    from tools.orchestration.approved_delivery import _job_key
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    lead,calls=prepared_inputs
    key=_job_key(DeliveryRequest('old-run','lead-1','liepin','',lead['url'],False,lead))
    DeliveryAttemptStore().reserve(key,'old-run','old-resume')
    assert prepare()['code']=='ALREADY_ATTEMPTED'
    assert calls==[]


def test_excluded_target_is_blocked_without_reading_resume(prepared_inputs):
    lead, calls = prepared_inputs
    (agent._PROJECT_ROOT/'policy.yaml').write_text('exclusion_list:\n  - "exact:测试公司"\n')
    assert prepare()['code'] == 'EXCLUDED_TARGET'
    assert not calls


def test_changed_jd_requires_review_again(prepared_inputs, monkeypatch):
    lead, calls = prepared_inputs
    monkeypatch.setattr('tools.infra.liepin_job_detail.fetch_liepin_job_detail', lambda *a, **k: {'source_jd_sha256':'changed'})
    assert prepare()['code'] == 'JOB_REVIEW_REQUIRED'
    assert not calls


def test_client_cannot_supply_resume_or_target(prepared_inputs):
    lead, calls = prepared_inputs
    assert prepare(resume_text='forged', platform_job_id='other')['code'] == 'INVALID_INPUT'
    assert not calls



def test_corrupt_delivery_state_blocks_before_network(prepared_inputs):
    _, calls = prepared_inputs
    path = agent._PROJECT_ROOT/'outputs/submissions/delivery_attempts.sqlite3'
    path.parent.mkdir(parents=True)
    path.write_text('corrupted state')
    assert prepare()['code'] == 'PREPARATION_UNAVAILABLE'
    assert not calls


def test_full_batch_blocks_preparation_before_credentials(prepared_inputs):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    _, calls = prepared_inputs
    store=DeliveryAttemptStore()
    prior=store.reserve('existing-job','prior-run','digest');store.finish(prior,'success')
    store.authorize_batch('batch',1,[prior])
    assert prepare()['code']=='BATCH_LIMIT_REACHED'
    assert not calls


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_existing_route_tests(monkeypatch):
    # 内容门禁由 test_resume_content 验证；这里保持岗位身份/回执的独立场景。
    monkeypatch.setattr('tools.infra.resume_content.current_career',lambda *a: {'revision':'confirmed-fixture'})
    monkeypatch.setattr('tools.infra.resume_content.content_body_issues',lambda *a: [])
    monkeypatch.setattr('tools.infra.resume_content.require_default_content',lambda *a: 'confirmed-fixture')
