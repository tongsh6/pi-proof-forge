"""原生 WebView 的 PDF 准备与上传状态；复用审批快照，不在此模拟网站成功。"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from tools.sidecar.handlers import agent, jobs
from tools.infra.ai_disclosure import AI_DISCLOSURE_TEXT, disclosure_sha256
from tools.infra.persistence.review_queue import locked_review_queue, atomic_write_json
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.infra.persistence.job_lead_binding import reviewed_official_profile
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.orchestration.approved_delivery import _job_key
from tools.channels.base import DeliveryRequest


def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value):
        raise ValueError('invalid_native_pdf_id')
    return value


def _sanitize_observation(value, depth=0):
    """签名只用于当次内存中的读取；连同嵌套 JSON 字符串在入库前统一脱敏。"""
    if depth>24:return None
    if isinstance(value,dict):
        return {k:_sanitize_observation(v,depth+1) for k,v in value.items()
                if not re.search(r'token|cookie|secret|password|authorization|signature|csrf|credential|accesskey|^tk$',k,re.I)}
    if isinstance(value,list):return [_sanitize_observation(v,depth+1) for v in value]
    if isinstance(value,str):
        if value.lstrip().startswith(('{','[')):
            try:return json.dumps(_sanitize_observation(json.loads(value),depth+1),ensure_ascii=False,separators=(',',':'))
            except (ValueError,RecursionError):pass
        if re.match(r'^(?:https?://|/)',value,re.I):return re.split(r'[?#]',value,maxsplit=1)[0]
    return value


def _local_file(value, suffix):
    path=Path(value)
    if not path.is_absolute():path=agent._PROJECT_ROOT/path
    if path.is_symlink() or not path.resolve().is_relative_to(agent._PROJECT_ROOT.resolve()) or path.suffix.lower()!=suffix or not path.is_file():
        raise ValueError('invalid_native_pdf_artifact')
    return path


def _validated_generation(quick_run_id):
    saved=json.loads((agent._PROJECT_ROOT/'outputs/quick_runs'/f'{quick_run_id}.json').read_text())
    run=saved['run']
    if run['status']!='DONE' or run['run_id']!=quick_run_id:raise ValueError('pdf_generation_required')
    md=_local_file(agent._PROJECT_ROOT/f'outputs/{quick_run_id}/resume_mr-{quick_run_id}_A.md','.md')
    trace,valid=agent.read_generation_trace(md)
    if not valid:raise ValueError('pdf_generation_trace_invalid')
    from tools.infra.resume_content import validate_generated_content
    content_basis=validate_generated_content(agent._PROJECT_ROOT,quick_run_id)
    lead_id=_id(trace['target']['job_lead_id'])
    bound=jobs._bound_lead(lead_id)
    if not bound:raise ValueError('pdf_job_review_required')
    lead=bound[1]
    if (lead.get('source')!='liepin_official' or not reviewed_official_profile(lead,jobs._JOB_PROFILE_DIR)
            or lead.get('job_profile_id')!=run['job_profile_id']
            or trace['target'].get('source_jd_sha256')!=lead.get('source_jd_sha256')):
        raise ValueError('pdf_job_review_required')
    from tools.policy.exclusions import load_exclusion_policy,match_exclusion,resolve_policy_path
    if match_exclusion(lead.get('company',''),lead.get('legal_entity',''),load_exclusion_policy(resolve_policy_path(agent._PROJECT_ROOT))):
        raise ValueError('pdf_target_excluded')
    request=DeliveryRequest('',lead_id,'liepin','',lead['url'],False,lead)
    if DeliveryAttemptStore(agent._PROJECT_ROOT/'outputs/submissions/delivery_attempts.sqlite3').has_attempt(_job_key(request)):
        raise ValueError('delivery_already_attempted')
    pdf=_local_file(saved['resume_pdf'],'.pdf')
    if not pdf.resolve().is_relative_to((agent._PROJECT_ROOT/'outputs').resolve()) or pdf.stat().st_size>10_000_000:
        raise ValueError('invalid_native_pdf_artifact')
    candidate={key:lead.get(key,'') for key in ('company','position','platform','platform_job_id','platform_job_type',
        'job_profile_id','jd_status','source_jd_sha256','source','legal_entity')}
    candidate.update(job_lead_id=lead_id,job_url=lead['url'],delivery_kind='generated_pdf',
        resume_version='gen_'+md.stem,content_basis=content_basis,matching_score=saved.get('score_total'),
        evaluation_score=saved.get('resume_readiness',{}).get('evaluation_score'),status='pending',round_index=0)
    from tools.infra.export.resume_filename import pdf_filename_for_resume
    candidate['pdf_filename']=pdf_filename_for_resume(md,agent._PROJECT_ROOT/'outputs')
    candidate['quality_snapshot']=_quality_snapshot(saved,md.read_bytes(),pdf.read_bytes())
    candidate['quality_sha256']=_quality_digest(candidate['quality_snapshot'])
    return candidate,md.read_text(),pdf.read_bytes(),saved.get('score_total')


def _quality_digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _quality_snapshot(saved,markdown,pdf):
    try:
        path=_local_file(saved['artifacts']['scorecard'],'.md').with_suffix('.json')
        if path.is_symlink() or not path.is_file():raise ValueError('missing scorecard')
        raw=path.read_bytes();score=json.loads(raw)
        md_sha=hashlib.sha256(markdown).hexdigest()
        if score.get('resume_sha256')!=md_sha:raise ValueError('changed resume')
        semantic=score.get('semantic_review') or {};ready=saved.get('resume_readiness',{})
        number=lambda v:v if type(v) in (int,float) and 0<=v<=100 else None
        expression=number(score.get('expression_score'))
        gaps=list(dict.fromkeys(str(s) for s in score.get('gap_tasks',[])))
        report=score.get('quality_report') if isinstance(score.get('quality_report'),dict) else None
        auto_pass=bool(report.get('auto_pass')) if report else False
        legacy=score.get('legacy_scores') if isinstance(score.get('legacy_scores'),dict) else {
            'rule_total':number(score.get('total_score')),'llm_expression':expression}
        passed=bool(ready.get('content_ready') is True and ready.get('quality_passed') is True and auto_pass
                    and score.get('traceability',{}).get('status')=='verified')
        return {'status':'bound','resume_sha256':md_sha,'pdf_sha256':hashlib.sha256(pdf).hexdigest(),
                'scorecard_sha256':hashlib.sha256(raw).hexdigest(),'evaluation_version':score.get('evaluation_version','legacy'),'matching_mode':'semantic' if semantic else 'rule',
                'matching_score':number(semantic.get('fit_score',saved.get('score_total'))),
                'resume_score':number(semantic.get('resume_score')),'expression_score':expression,
                'content_ready':ready.get('content_ready') is True,'quality_passed':passed,'gap_tasks':gaps,
                'auto_pass':auto_pass,'quality_report':report,
                'quality_failures':list(ready.get('quality_failures') or [])[:20],
                'legacy_scores':legacy}
    except (KeyError,TypeError,OSError,ValueError) as exc:
        raise ValueError('quality_scorecard_missing_or_changed') from exc


def _ai_disclosure_enabled():
    from tools.policy.exclusions import load_ai_disclosure_enabled
    return load_ai_disclosure_enabled()


def _disclosure_recorded(q):
    """返回已记录且与当前固定文案一致的投递声明；开关关闭或文案变化时视为未发送。"""
    record=q.get('pdf_delivery',{}).get('ai_disclosure')
    if not isinstance(record,dict):return None
    if record.get('text')!=AI_DISCLOSURE_TEXT or record.get('text_sha256')!=disclosure_sha256():return None
    return record


def _disclosure_observation_matches(detail,candidate):
    """只认真实聊天页里目标会话中已发出、且带发送证据的声明；不把点击或草稿当成功。"""
    try:
        if detail.get('action')!={'click_issued':True,'reason':'approved_ai_disclosure_send'}:return False
        context=detail.get('context') or {}
        if 'im-ui-chat-container' not in str(context.get('class_name','')).split():return False
        normalize=lambda s:''.join(unicodedata.normalize('NFKC',str(s)).split()).lower()
        if any(normalize(candidate[k]) not in normalize(context.get('text','')) for k in ['company','position']):return False
        sent=detail.get('ai_disclosure') or {}
        if sent.get('text')!=AI_DISCLOSURE_TEXT or sent.get('confirmed') is not True:return False
        evidence=sent.get('evidence')
        if evidence=='network':
            items=sent.get('network') or []
            return any(isinstance(item,dict) and item.get('http_status')==200
                and AI_DISCLOSURE_TEXT in str(item.get('request','')) for item in items)
        if evidence=='dom':return sent.get('dom_confirmed') is True
        return False
    except (KeyError,TypeError,AttributeError):return False


def _public(queue):
    c=queue['candidates'][0]
    sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(queue['run_id'],c)
    quality=c.get('quality_snapshot')
    if c.get('quality_sha256') and not isinstance(quality,dict):raise ValueError('quality_snapshot_changed')
    if quality is not None and (c.get('quality_sha256')!=_quality_digest(quality)
            or quality.get('pdf_sha256')!=sealed['pdf_sha256'] or quality.get('resume_sha256')!=sealed['markdown_sha256']):
        raise ValueError('quality_snapshot_changed')
    recovery_only=bool(queue.get('daily_interruption') and queue.get('pdf_delivery',{}).get('state')!='success')
    return {'run_id':queue['run_id'],'company':c['company'],'position':c['position'],
            'job_lead_id':c['job_lead_id'],'matching_score':c.get('matching_score'),
            'quality':quality if quality is not None else {'status':'unrecorded'},
            'pdf_sha256':sealed['pdf_sha256'],'pdf_path':sealed['resume_path'],'pdf_filename':c.get('pdf_filename',''),
            'account_effects_accepted':bool(queue.get('pdf_upload',{}).get('accepted_account_effects')),
            'verification_error':queue.get('attachment_binding_error',''),
            'single_delivery_authorized':bool(queue.get('single_delivery_authorization')),
            'phase':queue.get('pdf_delivery',{}).get('state') or ('attachment_verified' if queue.get('attachment_binding') else queue.get('pdf_upload',{}).get('state','prepared')),
            'can_confirm_send':not recovery_only and _confirmation_matches(queue),'recovery_only':recovery_only,
            'platform_filename':queue.get('attachment_binding',{}).get('filename',''),
            'ai_disclosure_enabled':_ai_disclosure_enabled(),
            'ai_disclosure_text':AI_DISCLOSURE_TEXT,
            'ai_disclosure_sent':_disclosure_recorded(queue) is not None,
            'platform_attachment_state':queue.get('platform_attachment',{}).get('state',''),
            'platform_attachment_checked_at':queue.get('platform_attachment',{}).get('observed_at',''),
            'attachment_removal_state':queue.get('pdf_attachment_removal',{}).get('state','')}


def handle_prepare_pdf(params):
    quick_run_id=_id(params.get('quick_run_id'))
    with locked_review_queue(agent._REVIEW_QUEUE_DIR/'.prepare-pdf'):
        for path in agent._REVIEW_QUEUE_DIR.glob('*.json'):
            q=json.loads(path.read_text())
            if q.get('quick_run_id')==quick_run_id:
                return {'meta':params['meta'],**_public(q)}
        candidate,content,pdf,score=_validated_generation(quick_run_id)
        run_id=agent._build_agent_run_id()
        candidate['snapshot']=ReviewSnapshotStore(agent._AGENT_RUN_DIR).create(run_id,candidate,content,dry_run=False,pdf_content=pdf)
        queue={'run_id':run_id,'quick_run_id':quick_run_id,'source_pdf_sha256':hashlib.sha256(pdf).hexdigest(),
               'created_at':agent._utcnow_iso(),'candidates':[candidate]}
        agent._save_queue(agent._get_queue_file(run_id),queue)
        atomic_write_json(agent._get_agent_run_file(run_id),{'run':{'run_id':run_id,'status':'REVIEW_PENDING',
            'job_profile_id':candidate.get('job_profile_id',''),'options':{'delivery_kind':'generated_pdf','native_pdf':True},
            'review_queue':queue,'deliveries_completed':0,'app_verified_deliveries':0},'events':[],'gate_checks':[]})
        return {'meta':params['meta'],**_public(queue)}


def handle_begin_upload(params):
    run_id=_id(params.get('run_id'))
    if params.get('accept_account_effects') is not True:raise ValueError('account_effects_consent_required')
    path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path)
        if q.get('run_id')!=run_id or not q.get('quick_run_id'):raise ValueError('pdf_review_required')
        previous=q.get('pdf_upload')
        if previous and (previous.get('state')!='not_submitted' or previous.get('reconciliation',{}).get('reason')!='platform_client_filename_rejected'):
            raise ValueError('pdf_upload_already_attempted')
        candidate=q['candidates'][0]
        if candidate.get('status') not in ({'approved'} if previous else {'pending'}) or candidate.get('delivery_kind')!='generated_pdf':raise ValueError('pdf_review_required')
        _public(q)  # 批准和释放文件前必须校验绑定，不能因质量正文被删除而跳过。
        sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,candidate)
        from tools.sidecar.handlers.daily_delivery import check_queue_write
        permit=check_queue_write(q,sealed['pdf_sha256'])
        filename=candidate.get('pdf_filename') or 'cv_'+sealed['pdf_sha256'][:16]+'.pdf'
        from tools.infra.export.resume_filename import check_platform_pdf_filename
        check_platform_pdf_filename(filename)
        upload_ref=uuid4().hex
        candidate.update(status='approved',decided_by='user',decided_at=agent._utcnow_iso())
        q['content_review']={'confirmed':True,'basis':candidate.get('content_basis'),'reviewed_at':agent._utcnow_iso()}
        if candidate.get('quality_snapshot'):
            # 同一批准动作记录用户已看到的固定质量快照，不增加发送授权。
            q['content_review'].update(quality_sha256=candidate['quality_sha256'],accepted_quality_gaps=candidate['quality_snapshot']['gap_tasks'])
        if previous:q.setdefault('pdf_upload_history',[]).append(previous)
        q['pdf_upload']={'state':'in_flight','upload_ref':upload_ref,'filename':filename,
            'pdf_sha256':sealed['pdf_sha256'],'accepted_account_effects':True,'started_at':agent._utcnow_iso()}
        agent._save_queue(path,q)
        return {'meta':params['meta'],'upload_ref':upload_ref,'filename':filename,
                'pdf_sha256':sealed['pdf_sha256'],'pdf_bytes':list(Path(sealed['resume_path']).read_bytes()),**permit}


def handle_finish_upload(params):
    run_id=_id(params.get('run_id'))
    path=agent._get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_upload_observation')
    with locked_review_queue(path):
        q=agent._load_queue(path); upload=q.get('pdf_upload',{})
        if upload.get('state')!='in_flight' or upload.get('upload_ref')!=params.get('upload_ref'):
            raise ValueError('pdf_upload_not_pending')
        if observation.get('filename')!=upload['filename']:raise ValueError('pdf_upload_identity_mismatch')
        # 即使页面宣称成功，仍须另行验证平台附件身份/内容，不能直接进入发送。
        upload.update(state='uploaded_unverified' if observation.get('status')=='uploaded' else 'unknown',
            observation=_sanitize_observation(observation),finished_at=agent._utcnow_iso())
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_inspect_pdf_packet(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path);u=q.get('pdf_upload',{})
        if not u or u['state']=='in_flight':raise ValueError('pdf_inspection_not_ready')
        return {'meta':params['meta'], 'filename':u['filename'], 'pdf_sha256':u['pdf_sha256']}


def _platform_attachment_state(q,observation):
    """已冻结的发送绑定与当前页面附件对账：只观测平台是否仍有该附件，不改绑定、不删除、不重传。"""
    b=q.get('attachment_binding') or {}
    if not b or not q.get('pdf_delivery',{}).get('final_send_started'):return ''
    from tools.infra.liepin_attachment_contract import attachment_filename_matches
    rows=[];counts=[]
    try:
        for response in observation.get('responses',[]):
            if response.get('method')=='OBSERVE' and response.get('url')=='https://c.liepin.com/resume/edit':
                value=json.loads(response['payload']);rows+=value.get('attachments',[]);counts.append(value.get('attachment_count'))
    except (ValueError,TypeError,AttributeError,KeyError):return ''
    # 没有卡片计数说明不是完整的附件页观察，不做任何平台结论。
    if len(counts)!=1 or type(counts[0]) is not int:return ''
    present=any(isinstance(r,dict) and r.get('fileId')==b.get('file_id') and r.get('encryAttachmentId')==b.get('attachment_id')
                and attachment_filename_matches(r,b.get('filename','')) for r in rows)
    return 'present' if present else 'missing_on_platform'


def handle_record_pdf_inspection(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_upload_observation')
    with locked_review_queue(path):
        q=agent._load_queue(path);u=q.get('pdf_upload',{})
        if not u or observation.get('filename')!=u['filename']:raise ValueError('pdf_upload_identity_mismatch')
        q['pdf_inspection']={'observed_at':agent._utcnow_iso(),'observation':_sanitize_observation(observation)}
        state=_platform_attachment_state(q,observation)
        if state:q['platform_attachment']={'state':state,'observed_at':q['pdf_inspection']['observed_at']}
        from tools.infra.liepin_attachment_contract import verify_legacy_filename_rejection
        reconciliation=verify_legacy_filename_rejection(u,observation)
        if reconciliation:u.update(state='not_submitted',reconciliation=reconciliation)
        # 从最终发送开始，绑定属于不可变发送历史；当前平台附件的后续变化另作观测。
        if u.get('state')=='uploaded_unverified' and not q.get('pdf_delivery',{}).get('final_send_started'):
            from tools.infra.liepin_attachment_contract import verify_uploaded_attachment
            sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,q['candidates'][0])
            try:
                binding=verify_uploaded_attachment(u,observation,sealed['pdf_sha256'],Path(sealed['resume_path']).stat().st_size)
                q['attachment_binding']={**binding,'verified_at':agent._utcnow_iso()}
                q.pop('attachment_binding_error',None)
            except ValueError as error:
                q['attachment_binding_error']=str(error)
                q.pop('attachment_binding',None)
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_pdf_target_packet(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path);c=q['candidates'][0]
        sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
        binding=q.get('attachment_binding',{})
        if not binding or binding.get('pdf_sha256')!=sealed['pdf_sha256']:raise ValueError('attachment_verification_required')
        return {'meta':params['meta'],'filename':binding['filename'],'job_url':c['job_url'],
                'company':c['company'],'position':c['position'],'attachment_id':binding['attachment_id']}


def handle_record_pdf_target(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_target_observation')
    with locked_review_queue(path):
        q=agent._load_queue(path)
        if not q.get('attachment_binding'):raise ValueError('attachment_verification_required')
        q['pdf_target_view']={'observed_at':agent._utcnow_iso(),'observation':_sanitize_observation(observation)}
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_authorize_single_pdf_delivery(params):
    if params.get('confirmed') is not True:raise ValueError('single_pdf_confirmation_required')
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path)
        if q.get('daily_cycle') or q.get('pdf_delivery') or len(q.get('candidates',[]))!=1:
            raise ValueError('single_pdf_scope_invalid')
        c=q['candidates'][0];sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
        if (c.get('status')!='approved' or c.get('delivery_kind')!='generated_pdf'
                or not q.get('content_review',{}).get('confirmed')
                or not q.get('pdf_upload',{}).get('accepted_account_effects')
                or q.get('attachment_binding',{}).get('pdf_sha256')!=sealed['pdf_sha256']):
            raise ValueError('attachment_verification_required')
        from tools.sidecar.handlers.daily_delivery import check_queue_write
        check_queue_write(q,sealed['pdf_sha256'])
        from tools.infra.persistence.delivery_attempt_store import scoped_pdf_authorization_ref
        request=DeliveryRequest(run_id,c['job_lead_id'],'liepin',sealed['resume_path'],c['job_url'],False,c)
        job_key=_job_key(request);ref=scoped_pdf_authorization_ref(run_id,job_key,sealed['pdf_sha256'])
        attempts=DeliveryAttemptStore(agent._PROJECT_ROOT/'outputs/submissions/delivery_attempts.sqlite3')
        batch=attempts.active_batch();batch_id='single_pdf_'+run_id
        if not batch:raise ValueError('pdf_batch_authorization_required')
        if batch.get('authorization_ref')!=ref:
            attempts.authorize_supplementary_batch(batch_id,batch['batch_id'],1,'generated_pdf',ref)
        elif batch['batch_id']!=batch_id:raise ValueError('delivery_scope_mismatch')
        q['single_delivery_authorization']={'batch_id':batch_id,'authorization_ref':ref,
            'pdf_sha256':sealed['pdf_sha256'],'job_key':job_key,'maximum':1,'confirmed_at':agent._utcnow_iso()}
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_begin_pdf_delivery(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path);c=q['candidates'][0]
        if q.get('pdf_delivery'):raise ValueError('pdf_delivery_already_started')
        sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
        binding=q.get('attachment_binding',{})
        if c.get('status')!='approved' or not binding or binding.get('pdf_sha256')!=sealed['pdf_sha256']:
            raise ValueError('attachment_verification_required')
        target={}
        for response in q.get('pdf_target_view',{}).get('observation',{}).get('responses',[]):
            if response.get('method')=='OBSERVE':target=json.loads(response['payload'])
        if not all(target.get(k) is True for k in ('url_match','company_present','position_present')) or target.get('challenge') or target.get('unavailable'):
            raise ValueError('pdf_target_verification_required')
        from tools.policy.exclusions import load_exclusion_policy,match_exclusion,resolve_policy_path
        if match_exclusion(c.get('company',''),c.get('legal_entity',''),load_exclusion_policy(resolve_policy_path(agent._PROJECT_ROOT))):
            raise ValueError('pdf_target_excluded')
        from tools.infra.liepin_job_detail import fetch_liepin_job_detail
        current=fetch_liepin_job_detail(c['job_url'],expected_job_id=str(c['platform_job_id']))
        if current['source_jd_sha256']!=c['source_jd_sha256']:raise ValueError('job_detail_changed')
        attempts=DeliveryAttemptStore(agent._PROJECT_ROOT/'outputs/submissions/delivery_attempts.sqlite3')
        from tools.sidecar.handlers.daily_delivery import check_queue_write,store as daily_store
        check_queue_write(q,sealed['pdf_sha256'])
        request=DeliveryRequest(run_id,c['job_lead_id'],'liepin',sealed['resume_path'],c['job_url'],False,c)
        if q.get('daily_cycle'):
            ref=daily_store().reserve_daily(q['daily_cycle'],run_id,_job_key(request),sealed['pdf_sha256'])
        else:
            batch=attempts.active_batch()
            if not batch or batch.get('allowed_delivery_kind')!='generated_pdf':raise ValueError('pdf_batch_authorization_required')
            ref=attempts.reserve(_job_key(request),run_id,sealed['pdf_sha256'],delivery_kind='generated_pdf')
        if not ref:raise ValueError('delivery_already_attempted')
        from tools.submission.storage import SubmissionRecorder
        recorder=SubmissionRecorder(agent._PROJECT_ROOT/'outputs/submissions','liepin','submit',run_id='native-'+ref,transport='browser')
        recorder.run_dir.chmod(0o700)
        recorder.set_meta(c['job_url'],sealed['resume_path'],'',False,browser_channel='tauri_webkit',redact_inputs=True)
        recorder.record.input_artifacts.update({'parent_run_id':run_id,'candidate_id':c['job_lead_id'],'company':c['company'],
            'position':c['position'],'resume_version':c.get('resume_version',''),'delivery_kind':'generated_pdf',
            'resume_pdf_sha256':sealed['pdf_sha256'],'delivery_attempt_id':ref,'attachment_id':binding['attachment_id'],
            'attachment_binding_kind':binding.get('binding_kind',''),'receipt_source':'app_browser'})
        for name,detail in [('rate_limit','每日授权批次已原子占位' if q.get('daily_cycle') else '额外单笔 generated_pdf 批次已原子占位'),('target_verify','已审核岗位与当前完整 JD 指纹一致'),
            ('submit_safety','仅本次已批准 PDF 与目标岗位'),('resume_attachment_binding','平台唯一附件 ID、上传响应与已批准文件关联')]:
            recorder.add_step(name,'success',detail)
        recorder.finish('running')
        q['pdf_delivery']={'state':'delivery_in_flight','attempt_id':ref,'submission_id':'native-'+ref,'started_at':agent._utcnow_iso()}
        agent._save_queue(path,q)
        return {'meta':params['meta'],'run_id':run_id,'delivery_ref':ref,'filename':binding['filename'],
                'attachment_id':binding['attachment_id'],'job_url':c['job_url'],'company':c['company'],'position':c['position'],
                **check_queue_write(q,sealed['pdf_sha256'])}


def handle_record_pdf_communication(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_chat_observation')
    with locked_review_queue(path):
        q=agent._load_queue(path);delivery=q.get('pdf_delivery',{})
        if delivery.get('state')!='delivery_in_flight' or delivery.get('attempt_id')!=params.get('delivery_ref'):
            raise ValueError('pdf_delivery_not_pending')
        delivery.update(state='communication_started',observation=_sanitize_observation(observation))
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def _confirmation_matches(q):
    try:
        d=q['pdf_delivery']
        if d.get('state')!='resume_interaction_pending' or d.get('final_send_started'):return False
        # AI 声明是独立聊天写入，会插在 prepare 与 send 之间；确认框事实取最近一次非声明观察，
        # 仍要求该观察自带 context/确认框/唯一目标附件与原按钮，不因跳过声明而放宽。
        detail=None
        for event in reversed(d.get('interaction_history',[])):
            if event.get('action')=='ai_disclosure':continue
            responses=event.get('observation',{}).get('responses') or []
            if not responses:return False
            detail=json.loads(responses[0].get('payload') or '{}');break
        if detail is None:return False
        dialogs=detail.get('confirmation',[])
        if len(dialogs)!=1:return False
        dialog=dialogs[0];binding=q['attachment_binding'];c=q['candidates'][0]
        normalize=lambda s:''.join(unicodedata.normalize('NFKC',str(s)).split()).lower()
        if any(normalize(c[k]) not in normalize(detail.get('context',{}).get('text','')) for k in ['company','position']):return False
        if Path(binding['filename']).stem not in dialog['text'] or '默认在线简历和附件简历' not in dialog['text']:return False
        radios=[i for i in dialog.get('inputs',[]) if i.get('type')=='radio']
        targets=[i for i in radios if i.get('value')==binding['file_id']]
        selected=[i for i in radios if i.get('checked') is True]
        buttons=[b for b in dialog.get('buttons',[]) if b.get('text')=='立即投递' and b.get('disabled') is False]
        return len(targets)==1 and targets[0].get('disabled',False) is False and len(selected)==1 and selected[0].get('value')==binding['file_id'] and len(buttons)==1
    except (KeyError,ValueError,TypeError,IndexError,AttributeError):return False


def _dialog_captured(q):
    """是否已从真实确认框抓到过字段；只用于允许一次未生效的 prepare 重试，不授予发送权限。"""
    try:
        for event in q.get('pdf_delivery',{}).get('interaction_history',[]):
            for response in event.get('observation',{}).get('responses',[]):
                if response.get('method')!='OBSERVE':continue
                detail=json.loads(response['payload'])
                if isinstance(detail.get('confirmation'),list) and detail['confirmation']:return True
    except (KeyError,TypeError,ValueError):
        pass
    return False


def _ai_disclosure_requirement(params,action,d,binding,c):
    return {'meta':params['meta'],'action':action,'delivery_ref':d['attempt_id'],'filename':binding['filename'],
            'attachment_id':binding['attachment_id'],'file_id':binding.get('file_id',''),
            'job_url':c['job_url'],'company':c['company'],'position':c['position'],
            'requires_ai_disclosure':True,
            'ai_disclosure':{'text':AI_DISCLOSURE_TEXT,'sha256':disclosure_sha256()}}


def handle_pdf_interaction_packet(params):
    run_id=_id(params.get('run_id'));action=params.get('action');path=agent._get_queue_file(run_id)
    if action not in {'inspect','prepare','send'}:raise ValueError('unsupported_pdf_interaction')
    with locked_review_queue(path):
        q=agent._load_queue(path);d=q.get('pdf_delivery',{});c=q['candidates'][0]
        sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
        binding=q.get('attachment_binding',{})
        if d.get('state') not in {'communication_started','resume_interaction_pending','final_send_pending'} or binding.get('pdf_sha256')!=sealed['pdf_sha256']:
            raise ValueError('pdf_delivery_not_pending')
        if action=='prepare':
            if q.get('daily_interruption'):raise ValueError('daily_recovery_required')
            # 开关开启时，准备前必须先发出 AI 声明；声明本身是独立、可核对的一次聊天写入。
            if (not d.get('final_send_started') and _ai_disclosure_enabled() and _disclosure_recorded(q) is None):
                return _ai_disclosure_requirement(params,action,d,binding,c)
            # 首次 prepare 的点击可能未生效（入口未打开/目标未核验）；确认框抓取成功前允许重试，避免一次失败锁死投递。
            if d.get('resume_interaction_started') and _dialog_captured(q):raise ValueError('resume_interaction_already_started')
            d.update(state='resume_interaction_pending',resume_interaction_started=True)
            agent._save_queue(path,q)
        if action=='send':
            from tools.sidecar.handlers.daily_delivery import check_queue_write
            # 每日中断/恢复、内容与额度门禁先于声明写入，避免恢复态借助声明步骤产生新的平台写入。
            check_queue_write(q,sealed['pdf_sha256'])
            if d.get('final_send_started'):raise ValueError('pdf_final_send_already_started')
            if _ai_disclosure_enabled() and _disclosure_recorded(q) is None:
                return _ai_disclosure_requirement(params,action,d,binding,c)
            if not _confirmation_matches(q):raise ValueError('pdf_confirmation_not_verified')
            d.update(state='final_send_pending',final_send_started=True,final_send_started_at=agent._utcnow_iso())
            agent._save_queue(path,q)
        return {'meta':params['meta'],'action':action,'delivery_ref':d['attempt_id'],'filename':binding['filename'],
                'attachment_id':binding['attachment_id'],'file_id':binding.get('file_id',''),'job_url':c['job_url'],'company':c['company'],'position':c['position']}


def handle_record_pdf_interaction(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id);observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_chat_observation')
    with locked_review_queue(path):
        q=agent._load_queue(path);d=q.get('pdf_delivery',{})
        if d.get('attempt_id')!=params.get('delivery_ref'):raise ValueError('pdf_delivery_not_pending')
        sanitized=_sanitize_observation(observation)
        d.setdefault('interaction_history',[]).append({'action':params.get('action'),'observed_at':agent._utcnow_iso(),'observation':sanitized})
        if params.get('action')=='ai_disclosure':
            detail={}
            try:
                for response in sanitized.get('responses',[]):
                    if response.get('method')=='OBSERVE':detail=json.loads(response['payload'])
            except (ValueError,TypeError):detail={}
            if _disclosure_observation_matches(detail,q['candidates'][0]):
                d['ai_disclosure']={'text':AI_DISCLOSURE_TEXT,'text_sha256':disclosure_sha256(),
                    'observed_at':agent._utcnow_iso()}
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_verify_pdf_receipt(params):
    """仅核验已保存的 App 业务响应，不联网、不补发。"""
    from tools.infra.liepin_native_receipt import classify_native_resume_receipt
    from tools.submission.storage import SubmissionRecorder,SubmissionRecord,SubmissionStep
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path);c=q['candidates'][0];d=q.get('pdf_delivery',{});binding=q.get('attachment_binding',{})
        sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
        if not d.get('final_send_started') or binding.get('pdf_sha256')!=sealed['pdf_sha256']:raise ValueError('pdf_receipt_unconfirmed')
        normalize=lambda s:''.join(unicodedata.normalize('NFKC',str(s)).split()).lower()
        expected_url=urlsplit(c['job_url'])._replace(query='',fragment='').geturl()
        issued=False;receipt=None;source_time=''
        for event in d.get('interaction_history',[]):
            for response in event.get('observation',{}).get('responses',[]):
                if response.get('method')!='OBSERVE':continue
                detail=json.loads(response['payload']);context=detail.get('context') or {}
                if (detail.get('url')!=expected_url or 'im-ui-chat-container' not in str(context.get('class_name','')).split()
                    or any(normalize(c[k]) not in normalize(context.get('text','')) for k in ['company','position'])):continue
                if event.get('action')=='send' and detail.get('action')=={'click_issued':True,'reason':'approved_attachment_confirmation'}:issued=True
                if not issued:continue
                matches=[classify_native_resume_receipt(item,binding['attachment_id']) for item in detail.get('network',[])]
                matches=[item for item in matches if item['status']=='success']
                if len(matches)==1:
                    receipt=matches[0];source_time=event.get('observed_at','');break
            if receipt:break
        if not receipt:raise ValueError('pdf_receipt_unconfirmed')
        submission_id=_id(d['submission_id']);directory=agent._PROJECT_ROOT/'outputs/submissions/liepin'/submission_id
        archived={'schema_version':1,'parent_run_id':run_id,'candidate_id':c['job_lead_id'],
                  'pdf_sha256':sealed['pdf_sha256'],'file_id':binding['file_id'],
                  'source_observed_at':source_time,'receipt':receipt}
        archive=directory/'native_receipt.json'
        if archive.exists():
            if json.loads(archive.read_text())!=archived:raise ValueError('native_receipt_archive_mismatch')
        else:atomic_write_json(archive,archived)
        archive.chmod(0o600)
        archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
        saved=json.loads((directory/'submission_log.json').read_text())
        if (saved.get('input_artifacts',{}).get('delivery_attempt_id')!=d['attempt_id']
            or saved['input_artifacts'].get('resume_pdf_sha256')!=sealed['pdf_sha256']):raise ValueError('native_receipt_log_mismatch')
        if saved.get('status')!='success':
            recorder=SubmissionRecorder(agent._PROJECT_ROOT/'outputs/submissions','liepin','submit',run_id=submission_id,transport='browser')
            steps=[SubmissionStep(**step) for step in saved.pop('steps')]
            recorder.record=SubmissionRecord(**saved,steps=steps)
            recorder.record.input_artifacts.update(native_receipt_sha256=archive_sha,receipt_source='app_browser',
                receipt_business_flag=1,native_receipt_source_observed_at=source_time)
            recorder.add_step('login_check','success','App 原生登录会话成功读取、上传并回读指定附件')
            if d.get('ai_disclosure'):
                recorder.add_step('ai_disclosure','success','投递前已向招聘方发送 AI 自动化声明')
            recorder.add_step('chat_send_resume','success','确认框所选平台附件 ID 与已批准 PDF 一致；发送请求携带同一附件 ID')
            recorder.add_step('submit','success','send-resume 业务响应 HTTP 200 / flag 1 / data {}，无再次发送')
            recorder.add_step('receipt','success',json.dumps({'parser_version':1,'http_status':200,'business_flag':1,'receipt_sha256':archive_sha}))
            recorder.finish('success')
            recorder.log_json.chmod(0o600);recorder.log_yaml.chmod(0o600)
        attempts=DeliveryAttemptStore(agent._PROJECT_ROOT/'outputs/submissions/delivery_attempts.sqlite3')
        try:attempts.finish(d['attempt_id'],'success')
        except ValueError as error:
            if str(error)!='delivery_attempt_already_finished':raise
            attempts.resolve_unknown(d['attempt_id'],run_id,sealed['pdf_sha256'],'success')
        d.update(state='success',native_receipt_sha256=archive_sha,verified_at=d.get('verified_at') or agent._utcnow_iso())
        c['delivery']={'job_lead_id':c['job_lead_id'],'success':True,'submission_id':submission_id,
            'receipt_source':'app_browser','app_verified':True,'status':'success','code':'submitted',
            'resume_pdf_sha256':sealed['pdf_sha256'],'attachment_id':binding['attachment_id'],'native_receipt_sha256':archive_sha}
        agent._save_queue(path,q)
        run_file=agent._get_agent_run_file(run_id)
        if run_file.exists():
            run=agent._load_agent_run(run_id);run['run'].setdefault('started_at',q.get('created_at',''));run['run'].setdefault('round',0)
            atomic_write_json(run_file,run)
        agent._sync_review_run(run_id,q,[c['delivery']])
        return {'meta':params['meta'],**_public(q),'submission_id':submission_id}


class _AttachmentMissing(Exception):
    pass


def _checked_removal_target(q,run_id):
    from tools.infra.liepin_attachment_contract import attachment_filename_matches
    c=q['candidates'][0];d=q.get('pdf_delivery',{});b=q.get('attachment_binding',{})
    if d.get('state')!='success':raise ValueError('attachment_removal_success_required')
    from tools.infra.submission_evidence import inspect_submission_evidence
    proof=inspect_submission_evidence(agent._PROJECT_ROOT,agent._PROJECT_ROOT/'outputs/submissions/liepin'/_id(d['submission_id'])/'submission_log.json')
    if proof['status']!='verified':raise ValueError('attachment_removal_success_required')
    sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load(run_id,c)
    try:
        from datetime import datetime,timezone
        current=q['pdf_inspection'];age=(datetime.now(timezone.utc)-datetime.fromisoformat(current['observed_at'].replace('Z','+00:00'))).total_seconds()
        rows=[];counts=[]
        for response in current['observation']['responses']:
            if response.get('method')=='OBSERVE' and response.get('url')=='https://c.liepin.com/resume/edit':
                value=json.loads(response['payload']);rows+=value.get('attachments',[]);counts.append(value.get('attachment_count'))
        if not -5<=age<=120 or len(counts)!=1 or type(counts[0]) is not int or not 0<=counts[0]<=50:raise ValueError()
        if not rows:raise _AttachmentMissing()
        if len(rows)!=1 or counts[0]<1:raise ValueError()
        record=rows[0];download=record.get('download',{});size=Path(sealed['resume_path']).stat().st_size
        if (record.get('fileId')!=b['file_id'] or record.get('encryAttachmentId')!=b['attachment_id']
            or not attachment_filename_matches(record,b['filename'])
            or record.get('fileSize')!=size or download.get('http_status')!=200 or download.get('byte_length')!=size
            or download.get('sha256')!=sealed['pdf_sha256'] or b.get('pdf_sha256')!=sealed['pdf_sha256']):raise ValueError()
    except _AttachmentMissing:
        # 页面已完整观察但没有这份附件：多半已在 App 外移除，给出可读原因，不留占位。
        raise ValueError('attachment_missing_on_platform') from None
    except (ValueError,KeyError,TypeError,AttributeError,OSError):
        raise ValueError('attachment_removal_identity_unverified') from None
    return b,sealed,counts[0]


def handle_begin_pdf_removal(params):
    """仅移除已成功投递、当前字节再次核实且用户明确确认的那份平台附件。"""
    if params.get('confirmed') is not True:raise ValueError('attachment_removal_confirmation_required')
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path);c=q['candidates'][0];d=q.get('pdf_delivery',{});b=q.get('attachment_binding',{})
        prior=q.get('pdf_attachment_removal',{})
        if prior and prior.get('state')!='not_submitted':raise ValueError('attachment_removal_already_attempted')
        if d.get('state')!='success':raise ValueError('attachment_removal_success_required')
        b,sealed,count=_checked_removal_target(q,run_id)
        removal={'state':'in_flight','removal_ref':uuid4().hex,'confirmed_by_user':True,'started_at':agent._utcnow_iso(),
            'filename':b['filename'],'file_id':b['file_id'],'attachment_id':b['attachment_id'],
            'pdf_sha256':sealed['pdf_sha256'],'attachment_count':count}
        if prior:q.setdefault('pdf_attachment_removal_history',[]).append(prior)
        q['pdf_attachment_removal']=removal;agent._save_queue(path,q)
        return {'meta':params['meta'],'run_id':run_id,**removal}


def handle_finish_pdf_removal(params):
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id);observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_upload_observation')
    with locked_review_queue(path):
        q=agent._load_queue(path);r=q.get('pdf_attachment_removal',{})
        if r.get('state')!='in_flight' or r.get('removal_ref')!=params.get('removal_ref') or observation.get('filename')!=r.get('filename'):
            raise ValueError('attachment_removal_not_pending')
        state='unknown'
        try:
            reports=[json.loads(v['payload']) for v in observation.get('responses',[]) if v.get('method')=='OBSERVE' and v.get('url')=='https://c.liepin.com/resume/edit']
            if len(reports)!=1:raise ValueError()
            value=reports[0];network=value.get('network',[]);issued=value.get('action',{}).get('click_issued')
            if issued is False and not network and observation.get('status')=='not_submitted':state='not_submitted'
            elif issued is True:
                target=value.get('target',{});before=value.get('before_ids',[]);after=value.get('after_ids',[])
                if (type(value.get('allowed_requests')) is not int or value['allowed_requests']!=1
                    or target.get('file_id')!=r['file_id'] or target.get('attachment_id')!=r['attachment_id']
                    or len(before)!=r['attachment_count'] or len(set(before))!=len(before) or before.count(r['file_id'])!=1
                    or sorted(after)!=sorted(x for x in before if x!=r['file_id'])):raise ValueError()
                receipts=[]
                for item in network:
                    if item.get('method')!='POST' or item.get('url')!='https://api-c.liepin.com/api/com.liepin.cresume.attachment.remove-attachment-resume' or item.get('http_status')!=200:continue
                    request=json.loads(item['request']);response=json.loads(item['response'])
                    if request.get('encryAttachmentId')==r['attachment_id'] and type(response.get('flag')) is int and response['flag']==1:receipts.append(item)
                if len(receipts)==1:state='removed'
        except (ValueError,KeyError,TypeError,AttributeError):pass
        r.update(state=state,finished_at=agent._utcnow_iso(),observation=_sanitize_observation(observation))
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_recheck_pdf_removal(params):
    """只核验原请求前拦截证据和当前同一文件，绝不调用移除脚本。"""
    run_id=_id(params.get('run_id'));path=agent._get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent._load_queue(path);r=q.get('pdf_attachment_removal',{})
        if r.get('state')!='unknown':raise ValueError('attachment_removal_outcome_unverified')
        try:
            reports=[json.loads(v['payload']) for v in r['observation']['responses'] if v.get('method')=='OBSERVE' and v.get('url')=='https://c.liepin.com/resume/edit']
            if len(reports)!=1:raise ValueError()
            v=reports[0];before=v.get('before_ids',[]);after=v.get('after_ids',[])
            if (type(v.get('allowed_requests')) is not int or v['allowed_requests']!=0 or type(v.get('blocked_requests')) is not int or v['blocked_requests']<1
                or v.get('network')!=[] or v.get('target',{}).get('file_id')!=r['file_id'] or v.get('target',{}).get('attachment_id')!=r['attachment_id']
                or before.count(r['file_id'])!=1 or len(before)!=r['attachment_count'] or len(set(before))!=len(before) or sorted(before)!=sorted(after)):raise ValueError()
        except (ValueError,KeyError,TypeError,AttributeError):raise ValueError('attachment_removal_outcome_unverified') from None
        _checked_removal_target(q,run_id)
        q.setdefault('pdf_attachment_removal_history',[]).append(json.loads(json.dumps(r)))
        r.update(state='not_submitted',reconciliation={'reason':'request_guard_blocked_before_send','checked_at':agent._utcnow_iso(),
            'current_attachment_original_bytes_verified':True,'source_observation_sha256':hashlib.sha256(json.dumps(r['observation'],sort_keys=True).encode()).hexdigest()})
        agent._save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}
