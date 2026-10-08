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
    q['pdf_inspection']={'observed_at':agent._utcnow_iso(),'observation':{'responses':[{'method':'OBSERVE','url':'https://c.liepin.com/resume/edit','payload':json.dumps({'attachment_count':2,'attachments':[current]})}]}}
    atomic_write_json(tmp_path/'outputs/review_queue/run_test.json',q)
    return log,archive,q


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
