"""合成完整本地证据，验证只读审计不会升级未知结果或改动投递。"""
import hashlib
import json
from pathlib import Path
import pytest
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.infra.persistence.review_queue import atomic_write_json
from tools.submission.storage import SubmissionRecorder, API_SUBMISSION_REQUIRED_STEPS, SUCCESS_SUBMISSION_REQUIRED_STEPS


def fixture_submission(root, kind='platform_default'):
    run_id='run_test';sid=('api-' if kind=='platform_default' else 'native-')+'a'*32
    content='# 合成简历';digest=hashlib.sha256(content.encode()).hexdigest()
    candidate={'job_lead_id':'lead_test','company':'合成公司','position':'合成岗位','platform':'liepin',
        'platform_job_id':'123','platform_job_type':'2','job_profile_id':'profile_test','source_jd_sha256':'b'*64,
        'jd_status':'complete_reviewed','source':'liepin_official','job_url':'https://www.liepin.com/job/123.shtml',
        'resume_version':'version_test','delivery_kind':kind,'status':'approved'}
    if kind=='platform_default':candidate['platform_resume_sha256']=digest
    snapshots=ReviewSnapshotStore(root/'outputs/agent_runs')
    candidate['snapshot']=snapshots.create(run_id,candidate,content,dry_run=False,pdf_content=b'%PDF-1.7\nsynthetic\n%%EOF')
    sealed=snapshots.load(run_id,candidate);digest=sealed['markdown_sha256'] if kind=='platform_default' else sealed['pdf_sha256']
    attempts=DeliveryAttemptStore(root/'outputs/submissions/delivery_attempts.sqlite3')
    attempts.authorize_batch('test_batch',1,[]);aid=attempts.reserve('test_job_key',run_id,digest,delivery_kind=kind);attempts.finish(aid,'success')
    rec=SubmissionRecorder(root/'outputs/submissions','liepin','submit',run_id=sid,transport='liepin_api' if kind=='platform_default' else 'browser')
    inputs={'delivery_kind':kind,'parent_run_id':run_id,'candidate_id':'lead_test','delivery_attempt_id':aid,
        'company':candidate['company'],'position':candidate['position'],'resume_version':'version_test','job_profile_id':'profile_test',
        'source_jd_sha256':candidate['source_jd_sha256'],'receipt_source':'app_api' if kind=='platform_default' else 'app_browser'}
    candidate['delivery']={'success':True,'status':'success','submission_id':sid,'receipt_source':inputs['receipt_source'],'app_verified':True}
    q={'run_id':run_id,'candidates':[candidate]}
    if kind=='platform_default':
        inputs['platform_resume_observed_sha256']=digest
        proof={'parent_run_id':run_id,'candidate_id':'lead_test','job_id':123,'job_kind':'2','resume_sha256':digest,
            'response_sha256':'c'*64,'http_status':200,'payload':{'errCode':0,'data':{'result':'应聘成功'}}}
        archive=rec.run_dir/'api_receipt.json';atomic_write_json(archive,proof);archive.chmod(0o600)
        inputs['api_receipt_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
        for step in API_SUBMISSION_REQUIRED_STEPS:
            rec.add_step(step,'success',json.dumps({'http_status':200,'response_sha256':'c'*64}) if step=='receipt' else '合成测试')
    else:
        from tools.infra.liepin_native_receipt import classify_native_resume_receipt,SEND_RESUME_URL
        item={'url':SEND_RESUME_URL,'method':'POST','http_status':200,
            'request':json.dumps({'imUserType':'0','imId':'a'*32,'imApp':'1','oppositeImId':'b'*32,'attachmentId':'attachment'}),
            'response':'{"flag":1,"data":{}}'}
        receipt=classify_native_resume_receipt(item,'attachment')
        proof={'schema_version':1,'parent_run_id':run_id,'candidate_id':'lead_test','pdf_sha256':digest,
            'file_id':'file-id','source_observed_at':'time','receipt':receipt}
        archive=rec.run_dir/'native_receipt.json';atomic_write_json(archive,proof);archive.chmod(0o600)
        inputs.update(resume_pdf_sha256=digest,attachment_id='attachment',native_receipt_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        q['attachment_binding']={'pdf_sha256':digest,'attachment_id':'attachment','file_id':'file-id'}
        q['pdf_delivery']={'state':'success','final_send_started':True,'attempt_id':aid,'submission_id':sid,'native_receipt_sha256':inputs['native_receipt_sha256']}
        for step in SUCCESS_SUBMISSION_REQUIRED_STEPS:rec.add_step(step,'success','合成测试')
        rec.add_step('receipt','success',json.dumps({'receipt_sha256':inputs['native_receipt_sha256']}))
    rec.record.input_artifacts=inputs;rec.finish('success')
    atomic_write_json(root/'outputs/review_queue'/f'{run_id}.json',q)
    return rec.log_json,q,archive


@pytest.mark.parametrize('kind',['platform_default','generated_pdf'])
def test_evidence_checks_both_routes_without_mutation(tmp_path,kind):
    from tools.infra.submission_evidence import inspect_submission_evidence
    log,q,archive=fixture_submission(tmp_path,kind)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=inspect_submission_evidence(tmp_path,log)
    assert result['status']=='verified',result
    assert result['resume_version_id']=='version_test' and result['job_lead_id']=='lead_test'
    assert result['receipt_sha256']==hashlib.sha256(archive.read_bytes()).hexdigest()
    assert result['delivery_kind']==kind and result['resume_sha256']
    assert {p:p.read_bytes() for p in before}==before
    assert 'oppositeImId' not in json.dumps(result) and '应聘成功' not in json.dumps(result)


@pytest.mark.parametrize('change',['receipt','snapshot','unknown','target','database','external'])
def test_incomplete_or_changed_evidence_never_passes(tmp_path,change):
    from tools.infra.submission_evidence import inspect_submission_evidence
    log,q,archive=fixture_submission(tmp_path)
    if change=='receipt':archive.write_text('{}')
    if change=='snapshot':q['candidates'][0]['position']='另一岗位'
    if change in {'unknown','target','external'}:
        payload=json.loads(log.read_text())
        if change=='unknown':payload['status']='unknown'
        if change=='target':payload['input_artifacts']['candidate_id']='another'
        if change=='external':payload['input_artifacts']['receipt_source']='website_history'
        log.write_text(json.dumps(payload))
    if change=='database':(tmp_path/'outputs/submissions/delivery_attempts.sqlite3').unlink()
    atomic_write_json(tmp_path/'outputs/review_queue/run_test.json',q)
    result=inspect_submission_evidence(tmp_path,log)
    assert result['status']=='incomplete' and result['reason']
    assert not (tmp_path/'outputs/submissions/delivery_attempts.sqlite3').exists() if change=='database' else True
