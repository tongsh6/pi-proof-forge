import json
from pathlib import Path
import pytest
from tools.sidecar.handlers import native_pdf as flow,agent
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore


def test_native_delivery_reserves_pdf_quota_once_before_browser_action(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs')
    monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    c={'job_lead_id':'lead','company':'公司','position':'岗位','platform':'liepin','source':'liepin_official',
       'platform_job_id':'123','platform_job_type':'2','source_jd_sha256':'jd','job_url':'https://www.liepin.com/job/123.shtml',
       'delivery_kind':'generated_pdf','status':'approved'}
    store=ReviewSnapshotStore(agent._AGENT_RUN_DIR)
    c['snapshot']=store.create('run',c,'# 合成候选人',dry_run=False,pdf_content=b'%PDF-1.7\nfixture\n%%EOF')
    sealed=store.load('run',c)
    q={'run_id':'run','candidates':[c],'attachment_binding':{'pdf_sha256':sealed['pdf_sha256'],'filename':'cv.pdf','attachment_id':'id'},
       'pdf_target_view':{'observation':{'responses':[{'method':'OBSERVE','payload':json.dumps({'url_match':True,'company_present':True,'position_present':True,'challenge':False,'unavailable':False})}]}}}
    agent._save_queue(agent._get_queue_file('run'),q)
    monkeypatch.setattr('tools.infra.liepin_job_detail.fetch_liepin_job_detail',lambda *a,**kw:{'source_jd_sha256':'jd'})
    attempts=DeliveryAttemptStore();attempts.authorize_batch('old',1,[])
    old=attempts.reserve('old','old','x',delivery_kind='platform_default');attempts.finish(old,'success')
    params={'meta':{'correlation_id':'t'},'run_id':'run'}
    with pytest.raises(ValueError,match='pdf_batch_authorization_required'):flow.handle_begin_pdf_delivery(params)
    attempts.authorize_supplementary_batch('pdf','old',1,'generated_pdf','grant')
    packet=flow.handle_begin_pdf_delivery(params)
    assert packet['delivery_ref']
    assert attempts.active_batch()['in_flight']==1
    assert attempts.active_batch()['remaining']==0
    with pytest.raises(ValueError,match='pdf_delivery_already_started'):flow.handle_begin_pdf_delivery(params)
    q=agent._load_queue(agent._get_queue_file('run'));q['pdf_delivery']['state']='communication_started';agent._save_queue(agent._get_queue_file('run'),q)
    inspect=flow.handle_pdf_interaction_packet({**params,'action':'inspect'})
    assert inspect['delivery_ref']==packet['delivery_ref']
    assert flow.handle_pdf_interaction_packet({**params,'action':'prepare'})['action']=='prepare'
    # 尚未抓到确认框时，首次 prepare 的点击可能未生效，允许重试；抓到确认框后重复 prepare 必须阻断。
    assert flow.handle_pdf_interaction_packet({**params,'action':'prepare'})['action']=='prepare'
    with pytest.raises(ValueError):flow.handle_pdf_interaction_packet({**params,'action':'send'})
    q=agent._load_queue(agent._get_queue_file('run'));q['attachment_binding']['file_id']='file-id'
    detail={'context':{'text':'公司 岗位'},'confirmation':[{'text':'选择附件简历 默认在线简历和附件简历 cv',
        'inputs':[{'type':'radio','checked':True,'value':'file-id'}],
        'buttons':[{'text':'立即投递','disabled':False}]}]}
    q['pdf_delivery']['interaction_history']=[{'observation':{'responses':[{'method':'OBSERVE','payload':json.dumps(detail)}]}}]
    agent._save_queue(agent._get_queue_file('run'),q)
    with pytest.raises(ValueError,match='resume_interaction_already_started'):
        flow.handle_pdf_interaction_packet({**params,'action':'prepare'})
    assert flow.handle_pdf_interaction_packet({**params,'action':'send'})['file_id']=='file-id'
    with pytest.raises(ValueError,match='pdf_final_send_already_started'):flow.handle_pdf_interaction_packet({**params,'action':'send'})
    q=agent._load_queue(agent._get_queue_file('run'))
    receipt={'method':'POST','url':'https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume','http_status':200,
        'request':json.dumps({'imUserType':'0','imId':'a'*32,'imApp':'1','oppositeImId':'b'*32,'attachmentId':'id'}),
        'response':'{"flag":1,"data":{}}'}
    detail={'url':c['job_url'],'context':{'class_name':'im-ui-chat-container','text':'公司 岗位'},
        'action':{'click_issued':True,'reason':'approved_attachment_confirmation'},'network':[receipt]}
    q['pdf_delivery']['interaction_history'].append({'action':'send','observed_at':'test','observation':{'responses':[{'method':'OBSERVE','payload':json.dumps(detail)}]}})
    agent._save_queue(agent._get_queue_file('run'),q)
    result=flow.handle_verify_pdf_receipt(params)
    assert result['phase']=='success'
    assert attempts.active_batch()['confirmed']==1
    assert flow.handle_verify_pdf_receipt(params)['phase']=='success'
    assert attempts.active_batch()['consumed']==1
    from tools.submission.storage import submission_required_steps_evidence
    log=json.loads((tmp_path/'outputs/submissions/liepin'/('native-'+packet['delivery_ref'])/'submission_log.json').read_text())
    assert submission_required_steps_evidence(log)['passed']
    from tools.sidecar.handlers import submission
    log_path=tmp_path/'outputs/submissions/liepin'/('native-'+packet['delivery_ref'])/'submission_log.json'
    item=submission._submission_item(log_path)
    assert item['company']=='公司'
    assert item['retry_allowed'] is False
    monkeypatch.setattr(submission,'_submission_log_paths',lambda:[log_path])
    with pytest.raises(ValueError,match='managed_submission_retry_forbidden'):
        submission.handle_submission_retry({'meta':{'correlation_id':'t'},'submission_id':log['run_id']})


def test_confirmation_rejects_duplicate_target_even_when_one_is_selected():
    detail={'context':{'text':'公司 岗位'},'confirmation':[{'text':'选择附件简历 默认在线简历和附件简历 cv_hash',
        'inputs':[{'type':'radio','checked':True,'value':'file-id'},{'type':'radio','checked':False,'value':'file-id'}],
        'buttons':[{'text':'立即投递','disabled':False}]}]}
    q={'candidates':[{'company':'公司','position':'岗位'}],'attachment_binding':{'filename':'cv_hash.pdf','file_id':'file-id'},
        'pdf_delivery':{'state':'resume_interaction_pending','interaction_history':[{'observation':{'responses':[{'method':'OBSERVE','payload':json.dumps(detail)}]}}]}}
    assert flow._confirmation_matches(q) is False


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_transport_tests(monkeypatch):
    # 本文件只验证既有传输/额度；完整内容真假边界见 test_resume_content_gate。
    monkeypatch.setattr('tools.infra.resume_content.require_queue_content',lambda *a,**kw: {})


def test_explicit_single_authorization_preserves_old_quota_and_existing_uploaded_file(tmp_path,monkeypatch):
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path);monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs');monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    c={'job_lead_id':'lead','company':'公司','position':'岗位','platform':'liepin','platform_job_id':'123','platform_job_type':'2','job_url':'https://www.liepin.com/job/123.shtml','delivery_kind':'generated_pdf','status':'approved'}
    snapshots=ReviewSnapshotStore(agent._AGENT_RUN_DIR);c['snapshot']=snapshots.create('run',c,'# 候选人',dry_run=False,pdf_content=b'%PDF-1.7\napproved\n%%EOF')
    sealed=snapshots.load('run',c)
    q={'run_id':'run','candidates':[c],'content_review':{'confirmed':True},'pdf_upload':{'state':'uploaded_unverified','accepted_account_effects':True},'attachment_binding':{'pdf_sha256':sealed['pdf_sha256']}}
    agent._save_queue(agent._get_queue_file('run'),q)
    attempts=DeliveryAttemptStore(tmp_path/'outputs/submissions/delivery_attempts.sqlite3');attempts.authorize_batch('old',1,[])
    old=attempts.reserve('old-job','old','old');attempts.finish(old,'success')
    params={'meta':{},'run_id':'run'}
    with pytest.raises(ValueError,match='confirmation_required'):flow.handle_authorize_single_pdf_delivery(params)
    result=flow.handle_authorize_single_pdf_delivery({**params,'confirmed':True})
    assert result['single_delivery_authorized'] is True
    assert attempts.active_batch()['authorized_max']==1 and attempts.active_batch()['remaining']==1
    again=flow.handle_authorize_single_pdf_delivery({**params,'confirmed':True});assert again['run_id']=='run'
    latest=agent._load_queue(agent._get_queue_file('run'));assert latest['pdf_upload']==q['pdf_upload'] and latest['attachment_binding']==q['attachment_binding']
    with attempts._connection() as db:assert db.execute("SELECT authorized_max,active FROM delivery_batches WHERE batch_id='old'").fetchone()==(1,0)
