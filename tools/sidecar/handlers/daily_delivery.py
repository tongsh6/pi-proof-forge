"""每日授权的 App 接口；文件与岗位身份只从批准快照读取。"""
from __future__ import annotations
import json
from tools.sidecar.handlers import agent
from tools.infra.persistence.daily_delivery import DailyDeliveryStore
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.infra.persistence.review_queue import locked_review_queue
from tools.channels.base import DeliveryRequest
from tools.orchestration.approved_delivery import _job_key

REASONS={'completed','candidate_shortfall','daily_not_active','daily_expired','daily_date_changed','daily_limit_reached','daily_scope_mismatch','daily_unresolved','daily_execution_stopped','daily_login_required','daily_attachment_capacity','daily_upload_unconfirmed','daily_binding_unconfirmed','daily_receipt_unknown','daily_interrupted','daily_recovery_required'}

def store():
    return DailyDeliveryStore(agent._PROJECT_ROOT/'outputs/submissions/delivery_attempts.sqlite3')

def scope_item(run_id,*,fresh=False):
    agent._validate_run_resource_id('run_id',run_id)
    q=agent._load_queue(agent._get_queue_file(run_id))
    if len(q.get('candidates',[]))!=1:raise ValueError('daily_invalid_candidate')
    c=q['candidates'][0];sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
    if not q.get('quick_run_id') or c.get('delivery_kind')!='generated_pdf' or c.get('jd_status')!='complete_reviewed' or c.get('platform')!='liepin' or sealed['dry_run']:
        raise ValueError('daily_invalid_candidate')
    request=DeliveryRequest(run_id,c['job_lead_id'],'liepin',sealed['resume_path'],c['job_url'],False,c)
    key=_job_key(request)
    if fresh and (c.get('status')!='pending' or q.get('pdf_upload') or q.get('pdf_delivery') or store().has_attempt(key)):
        raise ValueError('daily_candidate_already_used')
    if fresh:
        from tools.infra.resume_content import require_queue_content
        require_queue_content(agent._PROJECT_ROOT,q,require_approval=bool(q.get('pdf_upload') or q.get('pdf_delivery')))
    return dict(run_id=run_id,job_key=key,pdf_sha256=sealed['pdf_sha256'],channel='liepin',delivery_kind='generated_pdf',
                company=c['company'],position=c['position'],pdf_path=sealed['resume_path'],job_url=c['job_url'],matching_score=c.get('matching_score'),
                **({'pdf_filename':c['pdf_filename']} if 'pdf_filename' in c else {}))

def _needs_recovery(queue):
    if queue.get('pdf_delivery',{}).get('state')=='success':return False
    return bool(queue.get('daily_interruption') or queue.get('pdf_upload',{}).get('state')=='unknown')


def _recovery_queues():
    # 上传阶段尚无投递占位，不能只检查当前授权或 attempts 的 unknown。
    with store()._connection() as db:
        completed={r[0] for r in db.execute("SELECT run_id FROM attempts WHERE state IN ('success','failed')")}
    result=[]
    for path in agent._REVIEW_QUEUE_DIR.glob('*.json'):
        try:
            q=agent._load_queue(path)
            if q.get('run_id')==path.stem and q.get('quick_run_id') and path.stem not in completed and _needs_recovery(q):
                result.append((path.stem,q))
        except (OSError,ValueError,AttributeError):continue
    return result


def _progress_item(item,batch_id,batch_state,attempt_state):
    result={key:item.get(key,'') for key in ('run_id','company','position')}
    result.update(phase='record_unavailable',quick_run_id=None,recovery_required=False)
    try:
        if scope_item(item['run_id'])!=item:return result
        q=agent._load_queue(agent._get_queue_file(item['run_id']))
        quick=q.get('quick_run_id')
        if not isinstance(quick,str):return result
        result['quick_run_id']=quick
        # 未开始项可能在次日进入新批次；旧批次不借用它的新进度。
        if attempt_state=='success':phase='success'
        elif attempt_state=='failed':phase='failed'
        elif attempt_state=='unknown':phase='receipt_unknown'
        elif q.get('daily_cycle')!=batch_id:phase='not_started'
        else:
            delivery=q.get('pdf_delivery',{});upload=q.get('pdf_upload',{})
            if attempt_state=='in_flight' and batch_state!='running':phase='receipt_unknown'
            elif delivery.get('final_send_started'):phase='awaiting_receipt' if batch_state=='running' else 'receipt_unknown'
            elif delivery or attempt_state=='in_flight':phase='delivery_in_progress' if batch_state=='running' else 'receipt_unknown'
            elif upload.get('state')=='unknown':phase='upload_unconfirmed'
            elif upload.get('state')=='in_flight':phase='uploading' if batch_state=='running' else 'upload_unconfirmed'
            elif q.get('attachment_binding'):phase='attachment_verified'
            elif upload:phase='binding_pending'
            else:phase='not_started'
        result.update(phase=phase,recovery_required=phase not in {'success','failed'} and
                      (phase in {'upload_unconfirmed','receipt_unknown'} or (q.get('daily_cycle')==batch_id and _needs_recovery(q))))
    except (ValueError,KeyError,OSError,TypeError):pass
    return result


def handle_status(params):
    candidates=[]
    for path in sorted(agent._REVIEW_QUEUE_DIR.glob('*.json')):
        try:candidates.append(scope_item(path.stem,fresh=True))
        except (ValueError,KeyError,OSError,TypeError):continue
    status=store().status()
    for batch in status['history']:
        attempts=batch.pop('attempts',{})
        batch['items']=[_progress_item(item,batch['id'],batch['state'],attempts.get(item['run_id'])) for item in batch['items']]
        batch['unresolved']=sum(attempts.get(item['run_id']) in {'unknown','in_flight'} or
                                item['phase'] in {'upload_unconfirmed','receipt_unknown'} for item in batch['items'])
    recovery=[]
    for run_id,q in _recovery_queues():
        try:recovery.append(_progress_item(scope_item(run_id),q.get('daily_cycle'), 'finished', None))
        except (ValueError,KeyError,OSError,TypeError):
            recovery.append(dict(run_id=run_id,company='',position='',phase='record_unavailable',quick_run_id=None,recovery_required=True))
    return {**status,'candidates':candidates[:30],'recovery_required':bool(recovery),'recovery_items':recovery}

def handle_save(params):
    ids=params.get('run_ids')
    if not isinstance(ids,list) or len(ids)>30 or any(not isinstance(v,str) for v in ids) or len(set(ids))!=len(ids):raise ValueError('daily_invalid_scope')
    scope=[scope_item(i,fresh=True) for i in ids]
    store().save_draft(scope,params.get('maximum'),params.get('time'),params.get('expires_at'))
    return handle_status({})

def handle_change(params):
    state=params.get('state');ref=params.get('id');s=store()
    if state=='active':
        if _recovery_queues():raise ValueError('daily_recovery_required')
        auth=s.status()['authorization']
        if not auth or auth['id']!=ref:raise ValueError('daily_authorization_unavailable')
        for item in auth['scope']:
            # 恢复授权允许已成功的旧清单项；新候选仍由 claim 的全局防重排除。
            if scope_item(item['run_id'])!=item:raise ValueError('daily_scope_mismatch')
            q=agent._load_queue(agent._get_queue_file(item['run_id']))
            if not q.get('pdf_delivery',{}).get('state')=='success':
                from tools.infra.export.resume_filename import check_platform_pdf_filename
                if q['candidates'][0].get('pdf_filename'):
                    check_platform_pdf_filename(q['candidates'][0]['pdf_filename'])
                from tools.infra.resume_content import require_queue_content
                require_queue_content(agent._PROJECT_ROOT,q,require_approval=bool(q.get('pdf_upload')))
    s.set_status(ref,state,confirmed=params.get('confirmed') is True)
    return handle_status({})

def handle_claim(params):
    s=store();auth=s.status()['authorization']
    if auth and auth['state']=='active':
        if _recovery_queues():return {'claimed':False,'reason':'daily_recovery_required'}
    result=s.claim(force=params.get('force') is True)
    if not result.get('claimed'):return result
    try:
        for item in result['items']:
            path=agent._get_queue_file(item['run_id'])
            with locked_review_queue(path):
                if scope_item(item['run_id'],fresh=True)!=item:raise ValueError('daily_scope_mismatch')
                q=agent._load_queue(path);q['daily_cycle']=result['id'];agent._save_queue(path,q)
    except (ValueError,KeyError,OSError):
        store().finish_cycle(result['id'],'daily_scope_mismatch')
        raise ValueError('daily_scope_mismatch') from None
    return result

def check_queue_write(q,digest):
    if q.get('daily_interruption') and q.get('pdf_delivery',{}).get('state')!='success':
        raise ValueError('daily_recovery_required')
    from tools.infra.resume_content import require_queue_content
    require_queue_content(agent._PROJECT_ROOT,q,require_approval=bool(q.get('pdf_upload') or q.get('pdf_delivery')))
    return store().write_permit(q.get('daily_cycle'),q['run_id'],digest,attempt_id=q.get('pdf_delivery',{}).get('attempt_id'))

def handle_permit(params):
    run_id=params.get('run_id');item=scope_item(run_id)
    q=agent._load_queue(agent._get_queue_file(run_id))
    return check_queue_write(q,item['pdf_sha256'])

def handle_check(params):
    item=scope_item(params.get('run_id'))
    checked=store().check_write(params.get('id'),item['run_id'],item['pdf_sha256'])
    if checked!=item:raise ValueError('daily_scope_mismatch')
    return {'valid':True}

def handle_finish(params):
    ref=params.get('id');s=store();reason=params.get('reason')
    if reason not in REASONS:reason='daily_execution_stopped'
    with s._connection() as db:
        row=db.execute("SELECT items FROM daily_runs WHERE id=? AND state='running'",(ref,)).fetchone()
        if not row:raise ValueError('daily_run_unavailable')
        pending=db.execute("SELECT attempt_id FROM attempts WHERE batch_id=? AND state='in_flight'",(ref,)).fetchall()
    for (attempt,) in pending:
        try:s.finish(attempt,'unknown')
        except ValueError as error:
            if str(error)!='delivery_attempt_already_finished':raise
    with s._connection() as db:
        states={r[0]:r[1] for r in db.execute('SELECT run_id,state FROM attempts WHERE batch_id=?',(ref,))}
    upload_unconfirmed=False
    for item in json.loads(row[0]):
        path=agent._get_queue_file(item['run_id'])
        with locked_review_queue(path):
            q=agent._load_queue(path)
            if q.get('daily_cycle')!=ref or states.get(item['run_id']) in {'success','failed'}:continue
            upload=q.get('pdf_upload',{});delivery=q.get('pdf_delivery',{})
            if not upload and not delivery:continue
            if upload.get('state')=='in_flight':upload['state']='unknown'
            upload_unconfirmed=upload_unconfirmed or upload.get('state')=='unknown'
            if not q.get('daily_interruption'):
                q['daily_interruption']={'cycle_id':ref,'stopped_at':s.clock().isoformat(),'reason':reason}
                agent._save_queue(path,q)
    if any(state=='unknown' for state in states.values()):reason='daily_receipt_unknown'
    elif upload_unconfirmed:reason='daily_upload_unconfirmed'
    # “完成”不能由调用方宣称；SQLite 的已确认业务结果才是依据。
    with s._connection() as db:
        confirmed=db.execute("SELECT COUNT(*) FROM attempts WHERE batch_id=? AND state='success'",(ref,)).fetchone()[0]
        maximum=db.execute('SELECT authorized_max FROM delivery_batches WHERE batch_id=?',(ref,)).fetchone()[0]
    if reason=='completed' and confirmed<maximum:reason='candidate_shortfall'
    s.finish_cycle(ref,reason)
    return handle_status(params)


def handle_preview(params):
    import base64
    from pathlib import Path
    item=scope_item(params.get('run_id'))
    return {'pdf_base64':base64.b64encode(Path(item['pdf_path']).read_bytes()).decode('ascii'),'pdf_sha256':item['pdf_sha256']}
