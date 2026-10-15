import hashlib
import json
from pathlib import Path

import pytest

from tools.infra.persistence.review_snapshot import ReviewSnapshotStore


def test_snapshot_copies_exact_reviewed_pdf_bytes(tmp_path):
    store=ReviewSnapshotStore(tmp_path)
    pdf=b'%PDF-1.7\nreviewed bytes\n%%EOF\n'
    candidate={'job_lead_id':'lead','delivery_kind':'generated_pdf'}
    candidate['snapshot']=store.create('run',candidate,'# 合成候选人',dry_run=False,pdf_content=pdf)
    sealed=store.load('run',candidate)
    assert Path(sealed['resume_path']).read_bytes()==pdf
    assert sealed['pdf_sha256']==hashlib.sha256(pdf).hexdigest()


def test_upload_requires_effects_consent_and_reserves_before_releasing_bytes(tmp_path,monkeypatch):
    from tools.sidecar.handlers import native_pdf as flow
    from tools.sidecar.handlers import agent
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs')
    monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    candidate={'job_lead_id':'lead','company':'公司','position':'岗位','delivery_kind':'generated_pdf','status':'pending',
               'pdf_filename':'张三-公司-岗-20261008.1.PDF'}
    monkeypatch.setattr(flow,'_validated_generation',lambda _: (candidate,'# 合成候选人',b'%PDF-1.7\ncontent\n%%EOF\n',23))
    result=flow.handle_prepare_pdf({'meta':{'correlation_id':'t'},'quick_run_id':'quick'})
    def already_attempted(_):raise ValueError('delivery_already_attempted')
    monkeypatch.setattr(flow,'_validated_generation',already_attempted)
    assert flow.handle_prepare_pdf({'meta':{'correlation_id':'t'},'quick_run_id':'quick'})['run_id']==result['run_id']
    params={'meta':{'correlation_id':'t'},'run_id':result['run_id'],'accept_account_effects':False}
    with pytest.raises(ValueError,match='account_effects_consent_required'):flow.handle_begin_upload(params)
    params['accept_account_effects']=True
    payload=flow.handle_begin_upload(params)
    assert payload['pdf_bytes']==list(b'%PDF-1.7\ncontent\n%%EOF\n')
    assert len(payload['filename'])<=24
    assert payload['filename']==candidate['pdf_filename']
    queue=json.loads((agent._REVIEW_QUEUE_DIR/(result['run_id']+'.json')).read_text())
    assert queue['pdf_upload']['state']=='in_flight'
    assert queue['candidates'][0]['status']=='approved'
    with pytest.raises(ValueError,match='pdf_upload_already_attempted'):flow.handle_begin_upload(params)
    finish={'meta':{'correlation_id':'t'},'run_id':result['run_id'],'upload_ref':payload['upload_ref'],'observation':{'status':'unknown','filename':payload['filename'],'hints':[],'responses':[
        {'url':'https://tdoss.liepin.com/o/upload?token=sensitive-query#fragment','payload':json.dumps({'data':{'accessPath':'/recruit-auth/file.pdf?tk=sensitive-query#fragment'}})}]}}
    flow.handle_finish_upload(finish)
    assert 'sensitive-query' not in (agent._REVIEW_QUEUE_DIR/(result['run_id']+'.json')).read_text()
    with pytest.raises(ValueError,match='pdf_upload_already_attempted'):flow.handle_begin_upload(params)
    packet=flow.handle_inspect_pdf_packet({'meta':params['meta'],'run_id':result['run_id']})
    assert 'pdf_bytes' not in packet
    observed=flow.handle_record_pdf_inspection({'meta':params['meta'],'run_id':result['run_id'],
        'observation':finish['observation']})
    assert observed['phase']=='unknown'
    with pytest.raises(ValueError,match='attachment_verification_required'):
        flow.handle_pdf_target_packet({'meta':params['meta'],'run_id':result['run_id']})
    path=agent._get_queue_file(result['run_id']);q=agent._load_queue(path)
    q['pdf_upload']['state']='uploaded_unverified';q['attachment_binding']={'pdf_sha256':payload['pdf_sha256']}
    agent._save_queue(path,q)
    def mismatch(*args):raise ValueError('attachment_current_state_mismatch')
    monkeypatch.setattr('tools.infra.liepin_attachment_contract.verify_uploaded_attachment',mismatch)
    observed=flow.handle_record_pdf_inspection({'meta':params['meta'],'run_id':result['run_id'],'observation':finish['observation']})
    assert observed['phase']=='uploaded_unverified'
    assert observed['verification_error']=='attachment_current_state_mismatch'
    assert 'attachment_binding' not in agent._load_queue(path)
    for state in ['final_send_pending','success']:
        q=agent._load_queue(path);q['pdf_delivery']={'state':state,'final_send_started':True}
        q['attachment_binding']={'pdf_sha256':payload['pdf_sha256']};agent._save_queue(path,q)
        flow.handle_record_pdf_inspection({'meta':params['meta'],'run_id':result['run_id'],'observation':finish['observation']})
        assert agent._load_queue(path)['attachment_binding']['pdf_sha256']==payload['pdf_sha256']


def test_prepare_rejects_untrusted_quick_run_id(tmp_path,monkeypatch):
    from tools.sidecar.handlers import native_pdf as flow
    for value in ['../escape','/tmp/file','',None]:
        with pytest.raises(ValueError):flow.handle_prepare_pdf({'meta':{'correlation_id':'t'},'quick_run_id':value})


def test_long_filename_is_rejected_before_approval_or_upload_reservation(tmp_path,monkeypatch):
    from tools.sidecar.handlers import native_pdf as flow,agent
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs')
    monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    c={'job_lead_id':'lead','company':'长名称公司','position':'研发工程师','delivery_kind':'generated_pdf','status':'pending',
       'pdf_filename':'张三-长名称公司-研发工程师-20261008.1.PDF'}
    monkeypatch.setattr(flow,'_validated_generation',lambda _: (c,'# 张三',b'%PDF-1.7\ncontent\n%%EOF\n',23))
    prepared=flow.handle_prepare_pdf({'meta':{},'quick_run_id':'q'})
    with pytest.raises(ValueError,match='daily_pdf_filename_too_long'):
        flow.handle_begin_upload({'meta':{},'run_id':prepared['run_id'],'accept_account_effects':True})
    q=agent._load_queue(agent._get_queue_file(prepared['run_id']))
    assert 'pdf_upload' not in q and q['candidates'][0]['status']=='pending'


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_transport_tests(monkeypatch):
    # 本文件只验证既有传输/额度；完整内容真假边界见 test_resume_content_gate。
    monkeypatch.setattr('tools.infra.resume_content.require_queue_content',lambda *a,**kw: {})
