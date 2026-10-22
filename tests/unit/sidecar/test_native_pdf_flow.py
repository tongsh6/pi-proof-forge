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


def _pdf_flow_queue(tmp_path,monkeypatch):
    from tools.sidecar.handlers import native_pdf as flow
    from tools.sidecar.handlers import agent
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs')
    monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    candidate={'job_lead_id':'lead','company':'公司','position':'岗位','delivery_kind':'generated_pdf','status':'pending',
               'pdf_filename':'张三-公司-岗-20261008.1.PDF'}
    monkeypatch.setattr(flow,'_validated_generation',lambda _: (candidate,'# 合成候选人',b'%PDF-1.7\ncontent\n%%EOF\n',23))
    prepared=flow.handle_prepare_pdf({'meta':{'correlation_id':'t'},'quick_run_id':'quick'})
    return flow,agent,prepared


def test_deterministic_not_submitted_upload_is_retryable(tmp_path,monkeypatch):
    flow,agent,prepared=_pdf_flow_queue(tmp_path,monkeypatch)
    params={'meta':{'correlation_id':'t'},'run_id':prepared['run_id'],'accept_account_effects':True}
    assert (prepared['upload_state'],prepared['upload_attempts'],prepared['can_retry_upload'])==('',0,True)
    first=flow.handle_begin_upload(params)
    hints=['附件控件不唯一:共0个，候选:','弹窗:未出现，file控件总数:0']
    public=flow.handle_finish_upload({**params,'upload_ref':first['upload_ref'],'observation':{
        'status':'not_submitted','filename':first['filename'],'hints':hints,'responses':[]}})
    assert (public['phase'],public['upload_state'])==('not_submitted','not_submitted')
    assert (public['can_retry_upload'],public['upload_attempts'])==(True,1)
    assert public['upload_hints']==hints
    path=agent._get_queue_file(prepared['run_id'])
    assert agent._load_queue(path)['pdf_upload']['state']=='not_submitted'
    retry=flow.handle_begin_upload(params)
    assert retry['upload_ref']!=first['upload_ref']
    q=agent._load_queue(path)
    assert len(q['pdf_upload_history'])==1
    assert q['pdf_upload_history'][0]['upload_ref']==first['upload_ref']
    assert q['pdf_upload_history'][0]['state']=='not_submitted'
    assert q['pdf_upload']['state']=='in_flight'
    again=flow._public(q)
    assert (again['upload_state'],again['upload_attempts'],again['can_retry_upload'])==('in_flight',2,False)


@pytest.mark.parametrize('responses',[[],[{'method':'POST','url':'https://tdoss.liepin.com/o/upload','http_status':500,'payload':'{}'}]])
def test_unknown_upload_outcome_stays_non_retryable(tmp_path,monkeypatch,responses):
    flow,agent,prepared=_pdf_flow_queue(tmp_path,monkeypatch)
    params={'meta':{'correlation_id':'t'},'run_id':prepared['run_id'],'accept_account_effects':True}
    first=flow.handle_begin_upload(params)
    public=flow.handle_finish_upload({**params,'upload_ref':first['upload_ref'],'observation':{
        'status':'unknown','filename':first['filename'],'hints':['上传超时或结果未知'],'responses':responses}})
    assert (public['phase'],public['upload_state'])==('unknown','unknown')
    assert (public['can_retry_upload'],public['upload_attempts'])==(False,1)
    with pytest.raises(ValueError,match='pdf_upload_already_attempted'):flow.handle_begin_upload(params)


def test_legacy_unknown_not_submitted_observation_is_normalized_read_only(tmp_path,monkeypatch):
    flow,agent,prepared=_pdf_flow_queue(tmp_path,monkeypatch)
    params={'meta':{'correlation_id':'t'},'run_id':prepared['run_id'],'accept_account_effects':True}
    path=agent._get_queue_file(prepared['run_id'])
    legacy={'state':'unknown','upload_ref':'legacy-upload','filename':prepared['pdf_filename'],
            'pdf_sha256':prepared['pdf_sha256'],'accepted_account_effects':True,
            'observation':{'status':'not_submitted','filename':prepared['pdf_filename'],
                           'hints':['附件控件不唯一:共0个，候选:'],'responses':[]}}
    q=agent._load_queue(path);q['pdf_upload']=legacy;q['candidates'][0]['status']='approved'
    agent._save_queue(path,q);before=path.read_bytes()
    public=flow._public(agent._load_queue(path))
    assert path.read_bytes()==before
    assert (public['upload_state'],public['phase'])==('not_submitted','not_submitted')
    assert (public['can_retry_upload'],public['upload_attempts'])==(True,1)
    assert flow._upload_effective_state({'pdf_upload':legacy})=='not_submitted'
    flow.handle_begin_upload(params)
    q=agent._load_queue(path)
    assert q['pdf_upload_history'][0]['state']=='unknown'
    assert q['pdf_upload_history'][0]['upload_ref']=='legacy-upload'
    assert q['pdf_upload']['state']=='in_flight'
    # 队列里若已有上传/附件写请求响应，则结果并非确定未派发，保持 unknown 且不可重试。
    dispatched={**legacy,'observation':{**legacy['observation'],
        'responses':[{'method':'POST','url':'https://tdoss.liepin.com/o/upload','http_status':500,'payload':'{}'}]}}
    q=agent._load_queue(path);q['pdf_upload']=dispatched;q['pdf_upload_history']=[];agent._save_queue(path,q)
    with pytest.raises(ValueError,match='pdf_upload_already_attempted'):flow.handle_begin_upload(params)
    public=flow._public(agent._load_queue(path))
    assert (public['upload_state'],public['can_retry_upload'])==('unknown',False)


def test_uploaded_ack_still_enters_uploaded_unverified_and_blocks_retry(tmp_path,monkeypatch):
    flow,agent,prepared=_pdf_flow_queue(tmp_path,monkeypatch)
    params={'meta':{'correlation_id':'t'},'run_id':prepared['run_id'],'accept_account_effects':True}
    first=flow.handle_begin_upload(params)
    public=flow.handle_finish_upload({**params,'upload_ref':first['upload_ref'],'observation':{
        'status':'uploaded','filename':first['filename'],'hints':[],
        'responses':[{'method':'POST','url':'https://tdoss.liepin.com/o/upload','http_status':200,'payload':'{}'}]}})
    assert (public['phase'],public['upload_state'])==('uploaded_unverified','uploaded_unverified')
    assert public['can_retry_upload'] is False
    with pytest.raises(ValueError,match='pdf_upload_already_attempted'):flow.handle_begin_upload(params)


def test_upload_hints_are_bounded_and_sanitized(tmp_path,monkeypatch):
    flow,agent,prepared=_pdf_flow_queue(tmp_path,monkeypatch)
    params={'meta':{'correlation_id':'t'},'run_id':prepared['run_id'],'accept_account_effects':True}
    first=flow.handle_begin_upload(params)
    hints=['附件控件不唯一:共0个，候选:',
           '上传失败 https://tdoss.liepin.com/o/upload?token=sensitive-query&cookie=sid#fragment',
           'https://tdoss.liepin.com/o/upload?token=secret-value']+['提示%d'%index for index in range(12)]
    public=flow.handle_finish_upload({**params,'upload_ref':first['upload_ref'],'observation':{
        'status':'not_submitted','filename':first['filename'],'hints':hints,'responses':[]}})
    assert public['upload_hints'][:3]==['附件控件不唯一:共0个，候选:',
        '上传失败 https://tdoss.liepin.com/o/upload','https://tdoss.liepin.com/o/upload']
    assert len(public['upload_hints'])==10
    blob=json.dumps(public['upload_hints'],ensure_ascii=False)
    assert not any(item in blob for item in ('sensitive-query','sid#','secret-value','token=','cookie='))


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_transport_tests(monkeypatch):
    # 本文件只验证既有传输/额度；完整内容真假边界见 test_resume_content_gate。
    monkeypatch.setattr('tools.infra.resume_content.require_queue_content',lambda *a,**kw: {})


def test_existing_attempt_hint_points_to_prepared_run_and_pdf(tmp_path, monkeypatch):
    """同岗位已有尝试时，错误里应带上已固定运行的 quick_run_id 与 PDF 名，供界面引导继续该流程。"""
    from tools.sidecar.handlers import native_pdf as flow, agent
    monkeypatch.setattr(agent, "_REVIEW_QUEUE_DIR", tmp_path / "review_queue")
    agent._REVIEW_QUEUE_DIR.mkdir(parents=True)
    prepared = {
        "run_id": "ar_old", "quick_run_id": "qr_old",
        "candidates": [{"job_lead_id": "lead-1", "job_url": "https://www.liepin.com/job/1.shtml",
                         "platform_job_id": "1", "platform_job_type": "2",
                         "pdf_filename": "张三-某司-后端-20261022.1.PDF"}],
    }
    (agent._REVIEW_QUEUE_DIR / "ar_old.json").write_text(json.dumps(prepared, ensure_ascii=False), encoding="utf-8")
    hint = flow._existing_attempt_hint(lead_id="lead-1")
    assert hint == ":quick_run_id=qr_old|pdf=张三-某司-后端-20261022.1.PDF"
    # 不存在任何同 lead 的队列时不附提示，保持错误码可被前端识别。
    (agent._REVIEW_QUEUE_DIR / "ar_old.json").unlink()
    assert flow._existing_attempt_hint(lead_id="lead-1") == ""


def test_existing_attempt_hint_prefers_attempt_table_run_over_older_prepared_queue(tmp_path, monkeypatch):
    """同岗位可能有多个历史准备队列；必须优先指向 attempts 表占位的那一笔运行。"""
    import sqlite3
    from tools.sidecar.handlers import native_pdf as flow, agent
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    project = tmp_path
    review = project / "outputs" / "review_queue"
    review.mkdir(parents=True)
    monkeypatch.setattr(agent, "_PROJECT_ROOT", project)
    monkeypatch.setattr(agent, "_REVIEW_QUEUE_DIR", review)
    monkeypatch.setattr(agent, "_AGENT_RUN_DIR", project / "outputs" / "agent_runs")
    queues = {
        "ar_old": {"run_id": "ar_old", "quick_run_id": "qr_old", "candidates": [
            {"job_lead_id": "lead-1", "job_url": "https://www.liepin.com/job/1.shtml",
             "platform_job_id": "1", "platform_job_type": "2", "pdf_filename": "旧版.PDF"}]},
        "ar_attempt": {"run_id": "ar_attempt", "quick_run_id": "qr_attempt", "candidates": [
            {"job_lead_id": "lead-1", "job_url": "https://www.liepin.com/job/1.shtml",
             "platform_job_id": "1", "platform_job_type": "2", "pdf_filename": "固定版.PDF"}],
            "pdf_upload": {"state": "uploaded_unverified"}},
    }
    for name, payload in queues.items():
        (review / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store = DeliveryAttemptStore(project / "outputs/submissions/delivery_attempts.sqlite3")
    with store._connection() as db:
        db.execute(
            "INSERT INTO attempts (job_key, attempt_id, run_id, pdf_sha256, state, updated_at, batch_id, reserved_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("job-k", "attempt-1", "ar_attempt", "sha", "in_flight", "now", "batch", "now"),
        )
    hint = flow._existing_attempt_hint(lead_id="lead-1", job_key="job-k")
    assert hint == ":quick_run_id=qr_attempt|pdf=固定版.PDF"


def _prepared_pdf_queue(tmp_path, monkeypatch):
    from tools.sidecar.handlers import native_pdf as flow
    from tools.sidecar.handlers import agent
    monkeypatch.setattr(agent, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent, "_AGENT_RUN_DIR", tmp_path / "outputs/agent_runs")
    monkeypatch.setattr(agent, "_REVIEW_QUEUE_DIR", tmp_path / "outputs/review_queue")
    candidate = {"job_lead_id": "lead", "company": "公司", "position": "岗位", "delivery_kind": "generated_pdf",
                 "status": "pending", "pdf_filename": "张三-公司-岗-20261008.1.PDF"}
    monkeypatch.setattr(flow, "_validated_generation", lambda _: (candidate, "# 合成候选人", b"%PDF-1.7\ncontent\n%%EOF\n", 23))
    prepared = flow.handle_prepare_pdf({"meta": {"correlation_id": "t"}, "quick_run_id": "quick"})
    path = agent._get_queue_file(prepared["run_id"])
    q = agent._load_queue(path)
    q["candidates"][0]["status"] = "approved"
    q["content_review"] = {"confirmed": True}
    q["pdf_upload"] = {"state": "uploaded_unverified", "filename": candidate["pdf_filename"],
                       "pdf_sha256": prepared["pdf_sha256"], "accepted_account_effects": True}
    q["attachment_binding"] = {"pdf_sha256": prepared["pdf_sha256"], "filename": candidate["pdf_filename"],
                                "attachment_id": "old", "file_id": "old-file"}
    q["pdf_delivery"] = {"state": "resume_interaction_pending"}
    agent._save_queue(path, q)
    return flow, agent, prepared, q, path


def test_pre_send_missing_attachment_can_reupload_same_approved_pdf(tmp_path, monkeypatch):
    flow, agent, prepared, q, path = _prepared_pdf_queue(tmp_path, monkeypatch)
    q = agent._load_queue(path)
    q.pop("attachment_binding", None)  # 平台附件已被移除：旧绑定不再存在
    agent._save_queue(path, q)
    public = flow._public(agent._load_queue(path))
    assert public["can_reupload_attachment"] is True
    assert public["attachment_bound"] is False
    payload = flow.handle_begin_upload({"meta": {}, "run_id": prepared["run_id"], "accept_account_effects": True})
    updated = agent._load_queue(path)
    assert updated["pdf_upload"]["state"] == "in_flight"
    assert updated["pdf_upload"]["upload_ref"] == payload["upload_ref"]
    assert updated["pdf_upload_history"][0]["state"] == "uploaded_unverified"
    assert "attachment_binding" not in updated, "重新上传前必须清掉旧绑定的 fileId/attachmentId"
    assert flow._public(updated)["can_reupload_attachment"] is False


def test_final_send_started_blocks_reupload_recovery(tmp_path, monkeypatch):
    flow, agent, prepared, q, path = _prepared_pdf_queue(tmp_path, monkeypatch)
    q = agent._load_queue(path)
    q["pdf_delivery"]["final_send_started"] = True
    agent._save_queue(path, q)
    assert flow._public(q)["can_reupload_attachment"] is False
    with pytest.raises(ValueError, match="pdf_upload_already_attempted"):
        flow.handle_begin_upload({"meta": {}, "run_id": prepared["run_id"], "accept_account_effects": True})
