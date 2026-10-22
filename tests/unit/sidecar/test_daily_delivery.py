import json
from datetime import datetime, timezone, timedelta
import pytest
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore


def setup(tmp_path,monkeypatch):
    from tools.sidecar.handlers import agent,daily_delivery as flow
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path);monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs');monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    c=dict(job_lead_id='lead',company='公司',position='职位',delivery_kind='generated_pdf',status='pending',jd_status='complete_reviewed',platform='liepin',platform_job_id='123',platform_job_type=2,job_url='https://www.liepin.com/job/19123.shtml')
    c['snapshot']=ReviewSnapshotStore(agent._AGENT_RUN_DIR).create('r1',c,'# synthetic',dry_run=False,pdf_content=b'%PDF-1.7\nsynthetic\n%%EOF')
    agent._save_queue(agent._get_queue_file('r1'),dict(run_id='r1',quick_run_id='q1',candidates=[c]))
    return flow,agent


def draft(flow):
    return flow.handle_save({'run_ids':['r1'],'maximum':3,'time':'09:00','expires_at':(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()})


def test_preview_requires_real_immutable_snapshot_and_explicit_activation(tmp_path,monkeypatch):
    f,a=setup(tmp_path,monkeypatch)
    status=f.handle_status({});assert status['candidates'][0]['company']=='公司'
    result=draft(f);ref=result['authorization']['id']
    assert f.handle_claim({'force':True})['reason']=='daily_not_active'
    with pytest.raises(ValueError,match='daily_confirmation_required'):f.handle_change({'id':ref,'state':'active'})
    f.handle_change({'id':ref,'state':'active','confirmed':True})
    cycle=f.handle_claim({'force':True});assert cycle['claimed']
    f.handle_check({'id':cycle['id'],'run_id':'r1'})
    from tools.sidecar.handlers.native_pdf import handle_begin_upload
    f.handle_change({'id':ref,'state':'paused'})
    with pytest.raises(ValueError,match='daily_not_active'):handle_begin_upload({'run_id':'r1','accept_account_effects':True,'meta':{}})
    assert 'pdf_upload' not in a._load_queue(a._get_queue_file('r1'))


def test_changed_snapshot_not_activated_or_released_to_runner(tmp_path,monkeypatch):
    f,a=setup(tmp_path,monkeypatch);result=draft(f)
    q=a._load_queue(a._get_queue_file('r1'));q['candidates'][0]['company']='替换公司';a._save_queue(a._get_queue_file('r1'),q)
    with pytest.raises(ValueError):f.handle_change({'id':result['authorization']['id'],'state':'active','confirmed':True})
    assert f.handle_status({})['authorization']['state']=='draft'


def test_full_filename_over_platform_limit_cannot_activate_daily_scope(tmp_path,monkeypatch):
    f,a=setup(tmp_path,monkeypatch)
    q=a._load_queue(a._get_queue_file('r1'));c=q['candidates'][0]
    c['pdf_filename']='张三-完整测试公司-研发工程师-20261008.1.PDF'
    c['snapshot']=ReviewSnapshotStore(a._AGENT_RUN_DIR).create('r1',c,'# 张三',dry_run=False,pdf_content=b'%PDF-1.7\nsynthetic\n%%EOF')
    a._save_queue(a._get_queue_file('r1'),q)
    ref=draft(f)['authorization']['id']
    with pytest.raises(ValueError,match='daily_pdf_filename_too_long'):
        f.handle_change({'id':ref,'state':'active','confirmed':True})
    assert f.handle_status({})['authorization']['state']=='draft'


def test_runner_cannot_finish_unrelated_run_or_accept_unbounded_reason(tmp_path,monkeypatch):
    f,_=setup(tmp_path,monkeypatch);ref=draft(f)['authorization']['id'];f.handle_change({'id':ref,'state':'active','confirmed':True});run=f.handle_claim({'force':True})
    with pytest.raises(ValueError):f.handle_finish({'id':'wrong','reason':'completed'})
    f.handle_finish({'id':run['id'],'reason':'private arbitrary error including token'})
    assert f.handle_status({})['history'][0]['reason']=='daily_execution_stopped'


def test_daily_preview_returns_exact_fixed_pdf_and_rejects_arbitrary_paths(tmp_path,monkeypatch):
    import base64,hashlib
    f,_=setup(tmp_path,monkeypatch)
    result=f.handle_preview({'run_id':'r1'})
    assert hashlib.sha256(base64.b64decode(result['pdf_base64'])).hexdigest()==result['pdf_sha256']
    with pytest.raises(ValueError):f.handle_preview({'run_id':'../private'})


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_transport_tests(monkeypatch):
    # 本文件只验证既有传输/额度；完整内容真假边界见 test_resume_content_gate。
    monkeypatch.setattr('tools.infra.resume_content.require_queue_content',lambda *a,**kw: {})


def recovery_batch(tmp_path,monkeypatch):
    from tools.infra.persistence.daily_delivery import DailyDeliveryStore
    f,a=setup(tmp_path,monkeypatch)
    original=a._load_queue(a._get_queue_file('r1'))['candidates'][0]
    for number in (2,3):
        c={k:v for k,v in original.items() if k!='snapshot'}
        c.update(job_lead_id=f'lead{number}',company=f'合成公司{number}',platform_job_id=str(123+number))
        c['snapshot']=ReviewSnapshotStore(a._AGENT_RUN_DIR).create(f'r{number}',c,'# local fixture',dry_run=False,pdf_content=b'%PDF-1.7\nfixture\n%%EOF')
        a._save_queue(a._get_queue_file(f'r{number}'),{'run_id':f'r{number}','quick_run_id':f'q{number}','candidates':[c]})
    clock=[datetime(2026,10,8,1,tzinfo=timezone.utc)]
    s=DailyDeliveryStore(tmp_path/'outputs/submissions/delivery_attempts.sqlite3',clock=lambda:clock[0]);monkeypatch.setattr(f,'store',lambda:s)
    grant=f.handle_save({'run_ids':['r1','r2','r3'],'maximum':3,'time':'09:00','expires_at':'2026-10-12T00:00:00Z'})['authorization']
    f.handle_change({'id':grant['id'],'state':'active','confirmed':True});cycle=f.handle_claim({'force':True})
    return f,a,s,clock,cycle


def test_interrupted_upload_preserves_success_and_unstarted_and_never_retries(tmp_path,monkeypatch):
    f,a,s,clock,cycle=recovery_batch(tmp_path,monkeypatch);items=cycle['items']
    attempt=s.reserve_daily(cycle['id'],'r1',items[0]['job_key'],items[0]['pdf_sha256']);s.finish(attempt,'success')
    q=a._load_queue(a._get_queue_file('r1'));q['pdf_delivery']={'state':'success'};a._save_queue(a._get_queue_file('r1'),q)
    success_before=a._get_queue_file('r1').read_bytes();unstarted_before=a._get_queue_file('r3').read_bytes()
    q=a._load_queue(a._get_queue_file('r2'));q['candidates'][0]['status']='approved';q['pdf_upload']={'state':'in_flight','upload_ref':'u2','filename':'cv_fixture.pdf','pdf_sha256':items[1]['pdf_sha256']};a._save_queue(a._get_queue_file('r2'),q)
    f.handle_finish({'id':cycle['id'],'reason':'daily_interrupted'})
    stopped=a._load_queue(a._get_queue_file('r2'))
    assert stopped['pdf_upload']['state']=='unknown'
    assert stopped['daily_interruption']['cycle_id']==cycle['id']
    assert a._get_queue_file('r1').read_bytes()==success_before
    assert a._get_queue_file('r3').read_bytes()==unstarted_before
    history=f.handle_status({})['history'][0]
    assert [item['phase'] for item in history['items']]==['success','upload_unconfirmed','not_started']
    assert history['confirmed']==1 and history['reason']=='daily_upload_unconfirmed'
    from tools.sidecar.handlers.native_pdf import handle_inspect_pdf_packet,handle_begin_upload,handle_prepare_pdf
    assert handle_inspect_pdf_packet({'meta':{},'run_id':'r2'})['filename']=='cv_fixture.pdf'
    restored=handle_prepare_pdf({'meta':{},'quick_run_id':'q2'})
    assert restored['recovery_only'] is True and restored['can_confirm_send'] is False
    with pytest.raises(ValueError):handle_begin_upload({'meta':{},'run_id':'r2','accept_account_effects':True})
    clock[0]+=timedelta(days=1)
    assert f.handle_claim({'force':True})=={'claimed':False,'reason':'daily_recovery_required'}
    assert len(s.status()['history'])==1


def test_interrupted_send_retains_unknown_slot_and_readback_tracks_verified_receipt(tmp_path,monkeypatch):
    f,a,s,clock,cycle=recovery_batch(tmp_path,monkeypatch);item=cycle['items'][0]
    attempt=s.reserve_daily(cycle['id'],'r1',item['job_key'],item['pdf_sha256'])
    q=a._load_queue(a._get_queue_file('r1'));q['pdf_delivery']={'state':'final_send_pending','attempt_id':attempt,'final_send_started':True,'interaction_history':[]};a._save_queue(a._get_queue_file('r1'),q)
    f.handle_finish({'id':cycle['id'],'reason':'daily_interrupted'})
    history=f.handle_status({})['history'][0]
    assert history['items'][0]['phase']=='receipt_unknown'
    assert history['items'][0]['quick_run_id']=='q1'
    assert history['confirmed']==0 and history['unresolved']==1 and s.has_attempt(item['job_key'])
    with pytest.raises(ValueError,match='daily_run_unavailable'):f.handle_finish({'id':cycle['id'],'reason':'completed'})
    # 已有回执核验器解析业务证明后使用此原存储入口；状态读回自身不能升级成功。
    s.resolve_unknown(attempt,'r1',item['pdf_sha256'],'success')
    q=a._load_queue(a._get_queue_file('r1'));q['pdf_delivery']['state']='success';a._save_queue(a._get_queue_file('r1'),q)
    resolved=f.handle_status({})['history'][0]
    assert resolved['items'][0]['phase']=='success' and resolved['confirmed']==1 and resolved['unresolved']==0
    clock[0]+=timedelta(days=1);next_cycle=f.handle_claim({'force':True});assert next_cycle['claimed']
    assert 'r1' not in [i['run_id'] for i in next_cycle['items']]
    q=a._load_queue(a._get_queue_file('r3'));q['pdf_upload']={'state':'in_flight'};a._save_queue(a._get_queue_file('r3'),q)
    old=next(h for h in f.handle_status({})['history'] if h['id']==cycle['id'])
    assert old['items'][2]['phase']=='not_started','不能把次日同一候选的上传当成昨日进度'


def test_closed_daily_item_cannot_prepare_a_new_send_confirmation(tmp_path,monkeypatch):
    from tools.sidecar.handlers.native_pdf import handle_pdf_interaction_packet
    f,a,s,_,cycle=recovery_batch(tmp_path,monkeypatch);item=cycle['items'][0]
    q=a._load_queue(a._get_queue_file('r1'))
    q['attachment_binding']={'pdf_sha256':item['pdf_sha256'],'filename':'fixture.pdf','attachment_id':'attachment','file_id':'file'}
    q['pdf_delivery']={'state':'communication_started','attempt_id':'fixture-attempt'}
    q['daily_interruption']={'cycle_id':cycle['id']}
    a._save_queue(a._get_queue_file('r1'),q);before=a._get_queue_file('r1').read_bytes()
    with pytest.raises(ValueError,match='daily_recovery_required'):
        handle_pdf_interaction_packet({'meta':{},'run_id':'r1','action':'prepare'})
    assert a._get_queue_file('r1').read_bytes()==before


def test_new_authorization_cannot_bypass_unconfirmed_upload_from_old_batch(tmp_path,monkeypatch):
    f,a,s,clock,cycle=recovery_batch(tmp_path,monkeypatch)
    q=a._load_queue(a._get_queue_file('r1'));q['pdf_upload']={'state':'in_flight'};a._save_queue(a._get_queue_file('r1'),q)
    f.handle_finish({'id':cycle['id'],'reason':'daily_interrupted'})
    old=f.handle_status({})['authorization'];f.handle_change({'id':old['id'],'state':'revoked'})
    new=f.handle_save({'run_ids':['r2','r3'],'maximum':2,'time':'09:00','expires_at':'2026-10-12T00:00:00Z'})['authorization']
    with pytest.raises(ValueError,match='daily_recovery_required'):
        f.handle_change({'id':new['id'],'state':'active','confirmed':True})
    # 即使旧客户端已保存启用状态，执行入口也须独立拦截。
    s.set_status(new['id'],'active',confirmed=True);clock[0]+=timedelta(days=1)
    assert f.handle_claim({'force':True})=={'claimed':False,'reason':'daily_recovery_required'}
    status=f.handle_status({});assert status['recovery_required'] is True
    assert status['recovery_items'][0]['quick_run_id']=='q1'


def test_daily_run_does_not_borrow_unrelated_manual_batch_counter(tmp_path,monkeypatch):
    f,a,s,_,cycle=recovery_batch(tmp_path,monkeypatch)
    a._save_agent_run(a._get_agent_run_file('r1'),{'run':{'run_id':'r1','status':'REVIEW_PENDING','options':{'native_pdf':True}},'events':[]})
    s.authorize_batch('unrelated-manual',3,[])
    result=a.handle_agent_get({'meta':{'correlation_id':'t'},'run_id':'r1'})
    assert result['delivery_batch'] is None,'每日项的进度应来自原daily历史，不借用无关手动批次'
    assert f.handle_status({})['history'][0]['confirmed']==0


def test_deterministic_undispatched_upload_is_not_daily_recovery():
    # 上传脚本已证明“未派发”（not_submitted 且无写请求）时，旧队列的 raw unknown 不得继续阻塞每日投递。
    from tools.sidecar.handlers import daily_delivery
    legacy={'pdf_upload':{'state':'unknown','observation':{'status':'not_submitted','responses':[]}}}
    assert daily_delivery._needs_recovery(legacy) is False
    dispatched={'pdf_upload':{'state':'unknown','observation':{'status':'not_submitted','responses':[
        {'method':'POST','url':'https://api-c.liepin.com/api/com.liepin.cresume.attachment.save-attachment-resume','http_status':200}]}}}
    assert daily_delivery._needs_recovery(dispatched) is True
    timeout={'pdf_upload':{'state':'unknown','observation':{'status':'unknown','responses':[]}}}
    assert daily_delivery._needs_recovery(timeout) is True
    assert daily_delivery._needs_recovery({'daily_interruption':{'cycle_id':'c'}}) is True
