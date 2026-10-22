import hashlib
import json
from pathlib import Path
import pytest
from tools.sidecar.handlers import native_pdf as flow,agent
from tools.infra.persistence.review_queue import atomic_write_json
from tests.unit.infra.test_submission_evidence import fixture_submission


@pytest.fixture
def ready(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs');monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    log,q,archive=fixture_submission(tmp_path,'generated_pdf');b=q['attachment_binding'];size=len(b'%PDF-1.7\nsynthetic\n%%EOF');b.update(filename='cv_test.pdf',file_size=size)
    current={'fileId':b['file_id'],'encryAttachmentId':b['attachment_id'],'fileName':'cv_test','originalExtension':'pdf','fileSize':size,
        'download':{'http_status':200,'byte_length':size,'sha256':b['pdf_sha256']}}
    # 与真实页面一致：目标附件外还有一张同字节遗留卡；移除只针对唯一目标卡片。
    other={**current,'fileId':'other','encryAttachmentId':'other-attachment','fileName':'cv_other'}
    q['pdf_inspection']={'observed_at':agent._utcnow_iso(),'observation':{'responses':[{'method':'OBSERVE','url':'https://c.liepin.com/resume/edit','payload':json.dumps({'attachment_count':2,'attachments':[current,other]})}]}}
    atomic_write_json(tmp_path/'outputs/review_queue/run_test.json',q)
    return log,archive,q


def _queue(path=Path('outputs/review_queue/run_test.json')):
    return json.loads(path.read_text())


def _evidence(log):
    from tools.infra.submission_evidence import inspect_submission_evidence
    return inspect_submission_evidence(agent._PROJECT_ROOT,Path(log))


def begin(**extra):return flow.handle_begin_pdf_removal({'meta':{'correlation_id':'test'},'run_id':'run_test','confirmed':True,**extra})


def observation(packet,*,valid=True,issued=True):
    detail={'allowed_requests':1 if issued else 0,'action':{'click_issued':issued},'target':{'file_id':packet['file_id'],'attachment_id':packet['attachment_id']},
        'before_ids':[packet['file_id'],'other'],'after_ids':['other'],'network':[]}
    if issued:detail['network']=[{'method':'POST','url':'https://api-c.liepin.com/api/com.liepin.cresume.attachment.remove-attachment-resume','http_status':200,
        'request':json.dumps({'encryAttachmentId':packet['attachment_id'] if valid else 'wrong'}),'response':'{"flag":1,"data":{}}'}]
    return {'filename':packet['filename'],'status':'unknown' if issued else 'not_submitted','hints':[],
        'responses':[{'method':'OBSERVE','url':'https://c.liepin.com/resume/edit','http_status':0,'payload':json.dumps(detail)}]}


def finish(packet,**opts):return flow.handle_finish_pdf_removal({'meta':{'correlation_id':'test'},'run_id':'run_test',
    'removal_ref':packet['removal_ref'],'observation':observation(packet,**opts)})


def test_removal_requires_consent_and_preserves_original_success(ready):
    log,archive,q=ready;before=(log.read_bytes(),archive.read_bytes(),q['pdf_delivery'],q['candidates'][0]['delivery'])
    with pytest.raises(ValueError,match='attachment_removal_confirmation_required'):begin(confirmed=False)
    packet=begin()
    with pytest.raises(ValueError,match='attachment_removal_already_attempted'):begin()
    assert finish(packet)['attachment_removal_state']=='removed'
    saved=json.loads(Path('outputs/review_queue/run_test.json').read_text())
    assert (log.read_bytes(),archive.read_bytes(),saved['pdf_delivery'],saved['candidates'][0]['delivery'])==before
    with pytest.raises(ValueError,match='attachment_removal_already_attempted'):begin()


def test_missing_current_identity_or_bytes_blocks_removal(ready):
    _,_,q=ready;q['pdf_inspection']['observation']['responses'][0]['payload']='{"attachments":[]}'
    atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    with pytest.raises(ValueError,match='attachment_removal_identity_unverified'):begin()


def test_wrong_receipt_is_unknown_and_cannot_repeat(ready):
    packet=begin();assert finish(packet,valid=False)['attachment_removal_state']=='unknown'
    with pytest.raises(ValueError,match='attachment_removal_already_attempted'):begin()


def test_proven_no_final_click_can_be_prepared_again(ready):
    packet=begin();assert finish(packet,issued=False)['attachment_removal_state']=='not_submitted'
    assert begin()['removal_ref']!=packet['removal_ref']


@pytest.mark.parametrize('change',['pending','stale','wrong_hash'])
def test_unsafe_removal_preflight_never_creates_occupancy(ready,change):
    _,_,q=ready
    if change=='pending':q['pdf_delivery']['state']='final_send_pending'
    if change=='stale':q['pdf_inspection']['observed_at']='2000-01-01T00:00:00Z'
    if change=='wrong_hash':
        data=json.loads(q['pdf_inspection']['observation']['responses'][0]['payload']);data['attachments'][0]['download']['sha256']='wrong'
        q['pdf_inspection']['observation']['responses'][0]['payload']=json.dumps(data)
    atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    with pytest.raises(ValueError):begin()
    assert 'pdf_attachment_removal' not in json.loads(Path('outputs/review_queue/run_test.json').read_text())


def test_success_response_with_another_file_missing_is_not_confirmed(ready):
    packet=begin();obs=observation(packet);d=json.loads(obs['responses'][0]['payload']);d['after_ids']=[];obs['responses'][0]['payload']=json.dumps(d)
    result=flow.handle_finish_pdf_removal({'meta':{'correlation_id':'t'},'run_id':'run_test','removal_ref':packet['removal_ref'],'observation':obs})
    assert result['attachment_removal_state']=='unknown'


def test_guard_blocked_request_can_be_reconciled_only_with_unchanged_current_file(ready):
    packet=begin();obs=observation(packet);v=json.loads(obs['responses'][0]['payload']);v.update(allowed_requests=0,blocked_requests=1,network=[],after_ids=v['before_ids']);obs['responses'][0]['payload']=json.dumps(v)
    assert flow.handle_finish_pdf_removal({'meta':{'correlation_id':'t'},'run_id':'run_test','removal_ref':packet['removal_ref'],'observation':obs})['attachment_removal_state']=='unknown'
    result=flow.handle_recheck_pdf_removal({'meta':{'correlation_id':'t'},'run_id':'run_test'})
    assert result['attachment_removal_state']=='not_submitted'
    saved=json.loads(Path('outputs/review_queue/run_test.json').read_text())
    assert saved['pdf_attachment_removal_history'][-1]['state']=='unknown'
    assert saved['pdf_attachment_removal']['reconciliation']['reason']=='request_guard_blocked_before_send'


def test_unknown_after_any_allowed_request_cannot_be_released(ready):
    packet=begin();finish(packet,valid=False)
    with pytest.raises(ValueError,match='attachment_removal_outcome_unverified'):
        flow.handle_recheck_pdf_removal({'meta':{'correlation_id':'t'},'run_id':'run_test'})


def inspect(payload):
    return flow.handle_record_pdf_inspection({'meta':{'correlation_id':'t'},'run_id':'run_test','observation':{'filename':'cv_test.pdf','status':'unknown','hints':[],
        'responses':[{'method':'OBSERVE','url':'https://c.liepin.com/resume/edit','http_status':0,'payload':json.dumps(payload)}]}})


def test_fresh_check_without_the_attachment_marks_missing_on_platform_and_blocks_removal(ready):
    # App 外删除后：对账只观测不改绑定，移除返回明确原因，不留占位。
    _,_,q=ready;q['pdf_upload']={'state':'uploaded_unverified','filename':'cv_test.pdf','pdf_sha256':q['attachment_binding']['pdf_sha256']}
    current=json.loads(q['pdf_inspection']['observation']['responses'][0]['payload'])
    atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    result=inspect({'attachment_count':0,'attachments':[]})
    assert result['platform_attachment_state']=='missing_on_platform' and result['phase']=='success' and result['platform_filename']=='cv_test.pdf'
    with pytest.raises(ValueError,match='attachment_missing_on_platform'):begin()
    saved=json.loads(Path('outputs/review_queue/run_test.json').read_text())
    assert 'pdf_attachment_removal' not in saved and saved['attachment_binding']==q['attachment_binding'] and saved['pdf_delivery']==q['pdf_delivery']
    assert inspect(current)['platform_attachment_state']=='present'
    assert begin()['state']=='in_flight'


def test_check_without_attachment_count_makes_no_platform_claim(ready):
    _,_,q=ready;q['pdf_upload']={'state':'uploaded_unverified','filename':'cv_test.pdf','pdf_sha256':q['attachment_binding']['pdf_sha256']}
    atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    assert inspect({'attachments':[]})['platform_attachment_state']==''
    with pytest.raises(ValueError,match='attachment_removal_identity_unverified'):begin()


def test_multi_card_page_removes_only_the_unique_target_card(ready):
    packet=begin()
    assert packet['state']=='in_flight' and packet['attachment_count']==2
    assert finish(packet)['attachment_removal_state']=='removed'


@pytest.mark.parametrize('change',['target_missing','duplicate_file_id','count_mismatch'])
def test_incomplete_or_ambiguous_multi_card_observation_blocks_removal(ready,change):
    _,_,q=ready;data=json.loads(q['pdf_inspection']['observation']['responses'][0]['payload'])
    if change=='target_missing':data['attachments']=[{**row,'fileId':'other-'+str(index)} for index,row in enumerate(data['attachments'])]
    if change=='duplicate_file_id':data['attachments']=[data['attachments'][0],dict(data['attachments'][0])]
    if change=='count_mismatch':data['attachments']=data['attachments'][:1]
    q['pdf_inspection']['observation']['responses'][0]['payload']=json.dumps(data)
    atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    with pytest.raises(ValueError,match='attachment_removal_identity_unverified'):begin()


def test_non_success_delivery_still_reports_success_required(ready):
    _,_,q=ready;q['pdf_delivery']['state']='final_send_pending'
    atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    with pytest.raises(ValueError,match='attachment_removal_success_required'):begin()


def test_legacy_stale_attachment_identity_is_reconciled_from_verified_receipt(ready):
    log,archive,q=ready;b=q['attachment_binding']
    saved=json.loads(log.read_text());saved['input_artifacts']['attachment_id']='old-attachment';log.write_text(json.dumps(saved))
    assert _evidence(log)['reason']=='receipt_binding_mismatch'
    packet=begin()
    assert packet['state']=='in_flight' and packet['attachment_count']==2
    corrected=json.loads(log.read_text())['input_artifacts']
    assert corrected['attachment_id']==b['attachment_id'] and corrected['attachment_file_id']==b['file_id']
    assert corrected['attachment_id_history'][-1]['attachment_id']=='old-attachment'
    assert corrected['attachment_id_history'][-1]['source']=='native_receipt'
    assert _evidence(log)['status']=='verified'
    reconciliation=_queue()['pdf_delivery']['evidence_reconciliations'][-1]
    assert reconciliation['reason']=='receipt_binding_mismatch' and reconciliation['source']=='native_receipt'
    assert reconciliation['previous_attachment_id']=='old-attachment' and reconciliation['attachment_id']==b['attachment_id']
    assert len(reconciliation['log_sha256_before'])==64 and len(reconciliation['log_sha256_after'])==64
    assert finish(packet)['attachment_removal_state']=='removed'


def test_tampered_native_receipt_never_reconciles_even_with_matching_digest(ready):
    log,archive,q=ready
    saved=json.loads(log.read_text());saved['input_artifacts']['attachment_id']='old-attachment';log.write_text(json.dumps(saved))
    proof=json.loads(archive.read_text());proof['receipt']['request']['attachmentId']='wrong-attachment'
    atomic_write_json(archive,proof);archive.chmod(0o600)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    saved=json.loads(log.read_text());saved['input_artifacts']['native_receipt_sha256']=sha;log.write_text(json.dumps(saved))
    q=_queue();q['pdf_delivery']['native_receipt_sha256']=sha;atomic_write_json(Path('outputs/review_queue/run_test.json'),q)
    before=log.read_bytes()
    with pytest.raises(ValueError,match='attachment_removal_evidence_unverified:receipt_binding_mismatch'):begin()
    assert log.read_bytes()==before
    saved_q=_queue();assert 'pdf_attachment_removal' not in saved_q and not saved_q['pdf_delivery'].get('evidence_reconciliations')


def test_non_binding_evidence_failure_reports_evidence_unverified_without_reconcile(ready):
    log,archive,q=ready
    saved=json.loads(log.read_text());saved['input_artifacts']['attachment_id']='old-attachment'
    saved['steps']=[step for step in saved['steps'] if step['name']!='submit'];log.write_text(json.dumps(saved))
    before=log.read_bytes()
    with pytest.raises(ValueError,match='attachment_removal_evidence_unverified:required_steps_missing'):begin()
    assert log.read_bytes()==before and 'pdf_attachment_removal' not in _queue()
