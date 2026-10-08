import hashlib
import json
from types import SimpleNamespace

import pytest

from tools.channels.base import DeliveryRequest
from tools.domain.result import Err, Ok


def test_only_explicit_business_receipt_is_success():
    from tools.infra.liepin_default_delivery import classify_apply_response
    for payload in ({'code':0}, {'code':0,'message':'success'}, {'ok':True},
                    {'code':0,'data':{'success':False}}, {'code':0,'data':{'jobId':999,'message':'投递成功'}}):
        assert classify_apply_response(payload, 123)['status'] == 'unknown'
    assert classify_apply_response({'code':0,'data':{'result':'投递成功'}},123)['status']=='success'
    assert classify_apply_response({'code':12,'message':'rejected'},123)['status']=='failed'


def test_write_request_is_fixed_and_not_retried(monkeypatch):
    from tools.infra import liepin_default_delivery as module
    requests=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'{"code":0,"data":{"success":true}}'
    def send(request,timeout):
        requests.append(request)
        return Response()
    monkeypatch.setattr(module,'build_opener',lambda *_:SimpleNamespace(open=send))
    result=module.LiepinDefaultResumeClient().apply('synthetic-token',123,'2')
    assert result['status']=='success'
    assert len(requests)==1
    assert requests[0].full_url=='https://open-agent.liepin.com/mcp/apply-job'
    assert json.loads(requests[0].data)=={'jobId':123,'jobKind':'2'}
    assert 'synthetic-token' not in json.dumps(result)
    def timeout(*args,**kwargs):
        requests.append(None)
        raise TimeoutError('private-token-error')
    monkeypatch.setattr(module,'build_opener',lambda *_:SimpleNamespace(open=timeout))
    result=module.LiepinDefaultResumeClient().apply('synthetic-token',123,'2')
    assert result['status']=='unknown'
    assert len(requests)==2
    assert 'private-token-error' not in json.dumps(result)


def test_channel_blocks_changed_resume_before_post(tmp_path, monkeypatch):
    from tools.infra import liepin_default_delivery as module
    from tools.orchestration.approved_delivery import deliver_once
    monkeypatch.chdir(tmp_path)
    writer=SimpleNamespace(apply=lambda *_:pytest.fail('简历变化时不得发送'))
    channel=module.LiepinOfficialChannel(token_store=SimpleNamespace(load=lambda:'synthetic-token'),
       read_client=SimpleNamespace(get_resume=lambda _:'changed'),write_client=writer)
    monkeypatch.setattr(module,'fetch_liepin_job_detail',lambda *a,**kw:{'source_jd_sha256':'jd-hash'})
    request=DeliveryRequest('run-1','lead-1','liepin','', 'https://www.liepin.com/job/123.shtml',False,
       {'delivery_kind':'platform_default','platform_resume_sha256':hashlib.sha256(b'approved').hexdigest(),
        'platform_job_id':'123','platform_job_type':'2','source_jd_sha256':'jd-hash'})
    result=deliver_once(request,[channel],source='liepin_official')
    assert isinstance(result,Err) and result.error.reason=='platform_resume_changed'
    # 已明确未发送的前置失败不占据未来可授权尝试。
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    from tools.orchestration.approved_delivery import _job_key
    assert DeliveryAttemptStore().reserve(_job_key(request),'retry','hash')


def test_explicit_receipt_produces_api_steps_not_fake_browser_steps(tmp_path, monkeypatch):
    from tools.infra import liepin_default_delivery as module
    from tools.orchestration.approved_delivery import deliver_once
    from tools.submission.storage import submission_required_steps_evidence
    monkeypatch.chdir(tmp_path)
    text='approved platform resume'
    md=tmp_path/'platform.md';md.write_text(text)
    channel=module.LiepinOfficialChannel(token_store=SimpleNamespace(load=lambda:'synthetic-token'),
       read_client=SimpleNamespace(get_resume=lambda _:text),
       write_client=SimpleNamespace(apply=lambda *_:{'status':'success','http_status':200,'business_code':0,'response_sha256':'receipt-digest','schema':{'code':'int'}}))
    monkeypatch.setattr(module,'fetch_liepin_job_detail',lambda *a,**kw:{'source_jd_sha256':'jd-hash'})
    req=DeliveryRequest('run-1','lead-1','liepin','', 'https://www.liepin.com/job/123.shtml',False,
       {'delivery_kind':'platform_default','platform_resume_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'platform_job_id':'123','platform_job_type':'2','source_jd_sha256':'jd-hash','resume_markdown_path':str(md)})
    result=deliver_once(req,[channel],source='liepin_official')
    assert isinstance(result,Ok) and result.value.success
    logs=list((tmp_path/'outputs/submissions').rglob('submission_log.json'))
    assert len(logs)==1
    payload=json.loads(logs[0].read_text())
    assert payload['transport']=='liepin_api'
    assert submission_required_steps_evidence(payload)['passed']
    assert not {'login_check','chat_send_resume'} & {s['name'] for s in payload['steps']}
    assert 'synthetic-token' not in logs[0].read_text()
    assert text not in logs[0].read_text()


def test_external_receipt_can_resolve_unknown_without_sending_again(tmp_path, monkeypatch):
    from datetime import datetime,timezone
    from tools.infra import liepin_default_delivery as module
    from tools.orchestration.approved_delivery import deliver_once
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    from tools.infra.persistence.review_queue import atomic_write_json
    from tools.infra.liepin_receipt_reconciliation import confirm_from_external_receipt
    monkeypatch.chdir(tmp_path)
    text='approved';digest=hashlib.sha256(text.encode()).hexdigest()
    item={'job_lead_id':'lead-1','company':'test','position':'role','job_url':'https://www.liepin.com/job/123.shtml',
      'platform':'liepin','platform_job_id':'123','platform_job_type':'2','source':'liepin_official',
      'resume_version':'platform-v1','delivery_kind':'platform_default','platform_resume_sha256':digest,
      'source_jd_sha256':'jd','status':'approved','round_index':0}
    item['snapshot']=ReviewSnapshotStore().create('run-1',item,text,dry_run=False)
    data=ReviewSnapshotStore().load('run-1',item)
    channel=module.LiepinOfficialChannel(token_store=SimpleNamespace(load=lambda:'synthetic-token'),
       read_client=SimpleNamespace(get_resume=lambda _:text),write_client=SimpleNamespace(apply=lambda *_:{
        'status':'unknown','http_status':200,'business_code':0,'response_sha256':'digest','schema':{}}))
    monkeypatch.setattr(module,'fetch_liepin_job_detail',lambda *a,**kw:{'source_jd_sha256':'jd'})
    req=DeliveryRequest('run-1','lead-1','liepin','',item['job_url'],False,
                       {**item,'resume_markdown_path':data['resume_markdown_path']})
    assert isinstance(deliver_once(req,[channel],source='liepin_official'),Err)
    item['delivery']={'job_lead_id':'lead-1','status':'unknown','code':'delivery_result_unknown','success':False,'submission_id':''}
    atomic_write_json(tmp_path/'outputs/review_queue/run-1.json',{'run_id':'run-1','candidates':[item]})
    proof={'origin':'external_native_browser','record_page':'https://c.liepin.com/job/record/apply',
      'job_url':item['job_url'],'status':'已投递','platform_applied_at':datetime.now(timezone.utc).isoformat(),
      'recorded_at':datetime.now(timezone.utc).isoformat()}
    path=tmp_path/'proof.json';atomic_write_json(path,proof)
    result=confirm_from_external_receipt(tmp_path,'run-1','lead-1',path)
    assert result['success'] is True and result['receipt_source']=='website_history'
    assert result['app_verified'] is False
    assert result['code'] == 'external_observation_confirmed'
    assert confirm_from_external_receipt(tmp_path,'run-1','lead-1',path)==result
    proof['job_url']='https://www.liepin.com/job/456.shtml';atomic_write_json(path,proof)
    with pytest.raises(ValueError):confirm_from_external_receipt(tmp_path,'run-1','lead-1',path)


def test_default_api_rechecks_reservation_day_after_readonly_preflight(tmp_path,monkeypatch):
    from datetime import datetime,timezone,timedelta
    from tools.infra import liepin_default_delivery as module
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    monkeypatch.chdir(tmp_path)
    digest=hashlib.sha256(b'approved').hexdigest()
    store=DeliveryAttemptStore(clock=lambda:datetime.now(timezone.utc)-timedelta(days=1))
    attempt=store.reserve('job','run',digest)
    channel=module.LiepinOfficialChannel(token_store=SimpleNamespace(load=lambda:'synthetic-token'),read_client=SimpleNamespace(get_resume=lambda _:'approved'),write_client=SimpleNamespace(apply=lambda *_:pytest.fail('昨日占位不应发送')))
    monkeypatch.setattr(module,'fetch_liepin_job_detail',lambda *a,**kw:{'source_jd_sha256':'jd'})
    result=channel.deliver(DeliveryRequest('run','lead','liepin','','https://www.liepin.com/job/123.shtml',False,{'delivery_kind':'platform_default','delivery_attempt_id':attempt,'platform_resume_sha256':digest,'platform_job_id':'123','platform_job_type':'2','source_jd_sha256':'jd'}))
    assert isinstance(result,Err) and result.error.reason=='daily_date_changed' and result.error.not_submitted


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_protocol_tests(monkeypatch):
    # 本文件关注协议和回执；完整职业档案门禁在 test_resume_content 中不打桩。
    monkeypatch.setattr('tools.infra.resume_content.require_default_content',lambda *a: 'confirmed-fixture')
