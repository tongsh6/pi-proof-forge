"""真实网络边界使用合成响应；证明重核读取已有回执，不再发送。"""
import hashlib
import json
import stat
from types import SimpleNamespace

import pytest

from tools.infra import liepin_default_delivery as delivery
from tools.sidecar.handlers import agent, jobs
from tools.sidecar.server import process_request
from tests.unit.sidecar.test_prepare_liepin_default import prepared_inputs, prepare

REAL_APPLY = delivery.LiepinDefaultResumeClient.apply


@pytest.mark.parametrize('value', ['投递成功。', '简历已成功投递！', '{"success":true,"jobId":123}'])
def test_nested_business_receipts(value):
    receipt = delivery.classify_apply_response({'errCode':0,'data':{'result':value}}, 123)
    assert receipt['status'] == 'success'
    assert receipt['parser_version'] and receipt['reason']


@pytest.mark.parametrize('value', ['success', 'ok', '未投递成功', '已投递过该职位',
    '{"success":false,"message":"投递成功"}', '{"success":true,"jobId":456}',
    '{"success":true,"code":3}', '{"success":true,"code":"unknown"}'])
def test_generic_duplicate_or_conflicting_receipts_never_confirm(value):
    assert delivery.classify_apply_response({'errCode':0,'data':{'result':value}},123)['status'] != 'success'


def test_business_evidence_excludes_credentials(monkeypatch):
    token='synthetic-private-token'
    body=json.dumps({'errCode':0,'data':{'result':'未知响应 '+token,'token':token},'headers':{'x-user-token':token}}).encode()
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,*args): return body
    monkeypatch.setattr(delivery,'build_opener',lambda *_:SimpleNamespace(open=lambda *a,**k:Response()))
    result=REAL_APPLY(delivery.LiepinDefaultResumeClient(),token,123,'2')
    assert token not in json.dumps(result)
    assert result['status']=='unknown'
    assert '_replay_payload' in result


@pytest.fixture
def submitted_unknown(prepared_inputs, monkeypatch):
    from tools.infra.liepin_api import LiepinReadOnlyClient
    lead,_=prepared_inputs
    ready=prepare()
    payload={'errCode':0,'data':{'result':'投递成功。'}}
    requests=[]
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,*args): return json.dumps(payload,ensure_ascii=False).encode()
    def post(*a,**k):
        requests.append('post'); return Response()
    monkeypatch.setattr(delivery,'build_opener',lambda *_:SimpleNamespace(open=post))
    monkeypatch.setattr(delivery.LiepinDefaultResumeClient,'apply',REAL_APPLY)
    monkeypatch.setattr(jobs.liepin_readonly._store,'load',lambda:'synthetic-token')
    monkeypatch.setattr(LiepinReadOnlyClient,'get_resume',lambda *_:'合成平台简历：仅用于测试')
    monkeypatch.setattr(delivery,'fetch_liepin_job_detail',lambda *a,**k:{'source_jd_sha256':lead['source_jd_sha256']})
    # 模拟此前解析器未识别的响应；原始业务证据必须仍可被新解析器重核。
    parser=delivery.classify_apply_response
    monkeypatch.setattr(delivery,'classify_apply_response',lambda *a,**k:{'status':'unknown','business_code':0,'schema':{},'parser_version':0,'reason':'unrecognized'})
    result=agent.handle_submit_review({'meta':{'correlation_id':'test'},'run_id':ready['run_id'],
              'decisions':[{'job_lead_id':'lead-1','action':'approve'}]})
    monkeypatch.setattr(delivery,'classify_apply_response',parser)
    row=result['delivery_results'][0]
    assert row['status']=='unknown' and row['submission_id']
    assert requests==['post']
    return ready['run_id'], row, requests


def recheck(run_id):
    response=process_request({'id':'recheck','method':'run.agent.recheckReceipt','params':{
       'meta':{'correlation_id':'test'},'run_id':run_id,'job_lead_id':'lead-1'}})
    assert 'result' in response,response
    return response['result']


def test_recheck_confirms_from_protected_evidence_and_is_idempotent(submitted_unknown):
    run_id,row,requests=submitted_unknown
    log_path=agent._PROJECT_ROOT/'outputs/submissions/liepin'/row['submission_id']/'submission_log.json'
    archive=log_path.parent/'api_receipt.json'
    assert stat.S_IMODE(archive.stat().st_mode)==0o600
    assert stat.S_IMODE(archive.parent.stat().st_mode)==0o700
    assert '投递成功。' not in log_path.read_text()
    result=recheck(run_id)['delivery_results'][0]
    assert result['success'] and result['app_verified'] and result['receipt_source']=='app_api'
    assert recheck(run_id)['delivery_results'][0] == result
    assert requests==['post']
    run=agent.handle_agent_get({'meta':{'correlation_id':'x'},'run_id':run_id})['run']
    assert run['status']=='DONE' and run['app_verified_deliveries']==1
    log=json.loads(log_path.read_text())
    assert any(s['name']=='receipt' and s['status']=='unknown' for s in log['steps'])
    from tools.submission.storage import submission_required_steps_evidence
    assert submission_required_steps_evidence(log)['passed']


def test_changed_receipt_cannot_be_promoted(submitted_unknown):
    run_id,row,requests=submitted_unknown
    archive=agent._PROJECT_ROOT/'outputs/submissions/liepin'/row['submission_id']/'api_receipt.json'
    archive.write_text('{}')
    result=recheck(run_id)
    assert result['status']=='blocked' and result['code']=='RECEIPT_EVIDENCE_UNAVAILABLE'
    assert requests==['post']
    assert not agent.handle_get_pending_review({'meta':{'correlation_id':'x'},'run_id':run_id})['delivery_results'][0]['success']


def test_submission_record_remains_bound_to_target_and_version(submitted_unknown):
    from tools.sidecar.handlers import submission
    run_id,row,_=submitted_unknown
    detail=submission.handle_submission_detail({'meta':{'correlation_id':'test'},'submission_id':row['submission_id']})['submission']
    assert detail['company']=='测试公司' and detail['position']=='测试岗位'
    assert detail['resume_version_id'].startswith('platform-default-')
    assert detail['parent_run_id']==run_id and detail['job_lead_id']=='lead-1'
    assert detail['final_submit_attempted'] is True


def test_observed_liepin_application_receipt():
    # 2026-09-29 App 的真实回执仅保留此无个人信息业务模板。
    receipt=delivery.classify_apply_response({'data':{'result':'应聘成功'},'errCode':0},85381999)
    assert receipt['status']=='success'
    assert receipt['reason']=='explicit_business_success'
    for text in ('未应聘成功', '应聘成功？', '之前已应聘成功', '应聘失败'):
        assert delivery.classify_apply_response({'errCode':0,'data':{'result':text}},85381999)['status']!='success'
    assert delivery.classify_apply_response({'errCode':0,'message':'应聘失败','data':{'result':'应聘成功'}},85381999)['status']!='success'


def test_api_attempt_cannot_be_requeued_by_legacy_retry(submitted_unknown):
    from tools.sidecar.handlers import submission
    _,row,requests=submitted_unknown
    path=agent._PROJECT_ROOT/'outputs/submissions/liepin'/row['submission_id']/'submission_log.json'
    before=path.read_bytes()
    with pytest.raises(ValueError,match='api_submission_retry_forbidden'):
        submission.handle_submission_retry({'meta':{'correlation_id':'test'},'submission_id':row['submission_id']})
    assert path.read_bytes()==before and requests==['post']
    assert submission._submission_item(path)['retry_allowed'] is False


def legacy_hash_only_attempt(submitted_unknown):
    import copy
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    from tools.infra.persistence.review_queue import atomic_write_json
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    run_id,row,requests=submitted_unknown
    root=agent._PROJECT_ROOT
    candidate=copy.deepcopy(json.loads((root/'outputs/review_queue'/f'{run_id}.json').read_text())['candidates'][0])
    candidate.update(platform_job_id='456',job_url='https://www.liepin.com/job/456.shtml')
    content='合成平台简历：仅用于测试'
    candidate['snapshot']=ReviewSnapshotStore(agent._AGENT_RUN_DIR).create('legacy-run',candidate,content,dry_run=False)
    old_id='api-'+'1'*32
    candidate['delivery']={'job_lead_id':'lead-1','submission_id':old_id,'success':True,'status':'success','code':'submitted','receipt_source':'website_history'}
    atomic_write_json(root/'outputs/review_queue/legacy-run.json',{'run_id':'legacy-run','candidates':[candidate]})
    atomic_write_json(root/'outputs/agent_runs/legacy-run.json',{'run':{'run_id':'legacy-run','status':'DONE'},'events':[]})
    payload=json.loads((root/'outputs/submissions/liepin'/row['submission_id']/'submission_log.json').read_text())
    attempt=DeliveryAttemptStore().reserve('old-real-target','legacy-run',hashlib.sha256(content.encode()).hexdigest())
    DeliveryAttemptStore().finish(attempt,'success')
    payload.update(run_id=old_id,status='success')
    payload['input_artifacts'].update(parent_run_id='legacy-run',delivery_attempt_id=attempt,receipt_source='website_history')
    payload['input_artifacts'].pop('api_receipt_sha256')
    path=root/'outputs/submissions/liepin'/old_id/'submission_log.json'
    atomic_write_json(path,payload)
    return path,requests


def test_legacy_receipt_uses_exact_observed_response_hash_without_new_send(submitted_unknown):
    path,requests=legacy_hash_only_attempt(submitted_unknown)
    result=recheck('legacy-run')['delivery_results'][0]
    assert result['app_verified'] and result['receipt_source']=='app_api'
    data=json.loads(path.read_text())
    assert data['input_artifacts']['prior_receipt_source']=='website_history'
    assert data['input_artifacts']['api_receipt_reference']['source']=='matching_response_sha256'
    assert not (path.parent/'api_receipt.json').exists(), '不能伪造旧请求的原始接收文件'
    assert requests==['post']


def test_different_hash_cannot_promote_old_external_observation(submitted_unknown):
    path,requests=legacy_hash_only_attempt(submitted_unknown)
    data=json.loads(path.read_text())
    first=next(s for s in data['steps'] if s['name']=='receipt')
    summary=json.loads(first['detail']);summary['response_sha256']='0'*64;first['detail']=json.dumps(summary)
    path.write_text(json.dumps(data))
    response=recheck('legacy-run')
    assert response['status']=='blocked'
    assert requests==['post']


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_existing_route_tests(monkeypatch):
    # 内容门禁由 test_resume_content 验证；这里保持岗位身份/回执的独立场景。
    monkeypatch.setattr('tools.infra.resume_content.current_career',lambda *a: {'revision':'confirmed-fixture'})
    monkeypatch.setattr('tools.infra.resume_content.content_body_issues',lambda *a: [])
    monkeypatch.setattr('tools.infra.resume_content.require_default_content',lambda *a: 'confirmed-fixture')
