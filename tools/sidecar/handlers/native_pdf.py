"""原生 WebView 的 PDF 准备与上传状态；复用审批快照，不在此模拟网站成功。"""
from __future__ import annotations

import hashlib
import sqlite3
import json
import re
import unicodedata
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from tools.sidecar.handlers._shared import agent_state, job_repository
from tools.sidecar.handlers._shared.delivery_state import (
    upload_dispatched as _upload_dispatched,
    upload_effective_state as _upload_effective_state,
)
from tools.sidecar.handlers._shared.observations import (
    sanitize_observation as _sanitize_observation,
)
from tools.sidecar.handlers._shared.pdf_attachment import (
    record_verified_attachment_identity as _record_verified_attachment_identity,
)
from tools.sidecar.handlers._shared.pdf_quality import (
    local_file as _local_file,
    quality_snapshot as _quality_snapshot,
)
from tools.infra.ai_disclosure import AI_DISCLOSURE_TEXT, disclosure_sha256
from tools.infra.persistence.review_queue import locked_review_queue, atomic_write_json
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore, read_generation_trace, quality_digest as _quality_digest
from tools.infra.persistence.job_lead_binding import reviewed_official_profile
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.orchestration.approved_delivery import _job_key
from tools.channels.base import DeliveryRequest

_EMBEDDED_URL_QUERY=re.compile(r'(?i)\b(https?://[^\s?#]+)[?#][^\s]*')
_HINT_CREDENTIAL=re.compile(r'(?i)\b(?:token|cookie|secret|password|authorization|signature|csrf|credential|accesskey|tk)=[^\s&#,;]*')

def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value):
        raise ValueError('invalid_native_pdf_id')
    return value

def _public_upload_hints(upload):
    observation=upload.get('observation') if isinstance(upload,dict) else None
    hints=observation.get('hints') if isinstance(observation,dict) else None
    if not isinstance(hints,list):return []
    result=[]
    for hint in hints:
        if not isinstance(hint,str):continue
        text=_sanitize_observation(hint)
        if not isinstance(text,str):continue
        # 页面提示可能夹带上传/附件 URL：去掉任意位置的 query/fragment，并遮盖文本里的凭据键值。
        text=_EMBEDDED_URL_QUERY.sub(r'\1',text)
        text=_HINT_CREDENTIAL.sub(lambda match:re.split(r'=',match.group(0),maxsplit=1)[0]+'=***',text)
        result.append(text[:180])
        if len(result)>=10:break
    return result


def _existing_attempt_hint(*, lead_id='', job_key=''):
    """同岗位已有投递尝试时，返回已固定运行的 quick_run_id/PDF 名，供错误提示引导继续原流程。

    优先按 attempts 表里的 job_key→run_id 精确找已占位运行（避免同岗位多个历史准备队列挑错），
    找不到时退回只读扫描 review_queue。不读平台、不改队列，找不到返回空串。
    """
    def hint_from_queue(prior, candidate):
        return f":quick_run_id={prior.get('quick_run_id')}|pdf={candidate.get('pdf_filename','')}"

    def load_queue_if_valid(run_id):
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',run_id):
            return None
        try:
            prior=json.loads((agent_state.review_queue_dir()/f'{run_id}.json').read_text(encoding='utf-8'))
        except (OSError,ValueError,TypeError):
            return None
        return prior if isinstance(prior,dict) and prior.get('run_id')==run_id and prior.get('quick_run_id') else None

    if job_key:
        try:
            store=DeliveryAttemptStore(agent_state.project_root()/'outputs/submissions/delivery_attempts.sqlite3')
            with store._connection() as db:
                row=db.execute("SELECT run_id FROM attempts WHERE job_key=? ORDER BY rowid DESC LIMIT 1",(job_key,)).fetchone()
            prior=load_queue_if_valid(row[0] if row else '')
            if prior:
                candidates=prior.get('candidates') if isinstance(prior.get('candidates'),list) else []
                candidate=candidates[0] if candidates and isinstance(candidates[0],dict) else {}
                return hint_from_queue(prior,candidate)
        except (OSError,ValueError,TypeError,sqlite3.Error):
            pass

    entries=[]
    try:
        for path in agent_state.review_queue_dir().glob('*.json'):
            try:
                prior=json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError,TypeError):
                continue
            if not isinstance(prior,dict) or prior.get('run_id')!=path.stem or not prior.get('quick_run_id'):
                continue
            candidates=prior.get('candidates')
            candidate=candidates[0] if isinstance(candidates,list) and candidates and isinstance(candidates[0],dict) else {}
            if lead_id and candidate.get('job_lead_id')!=lead_id:
                continue
            if job_key:
                try:
                    request=DeliveryRequest('',candidate.get('job_lead_id',''),'liepin','',candidate.get('job_url',''),False,candidate)
                    if _job_key(request)!=job_key:
                        continue
                except (KeyError,TypeError,AttributeError):
                    continue
            # 优先已有上传/投递进度的队列，其次按最近修改。
            started=1 if (prior.get('pdf_upload') or prior.get('pdf_delivery')) else 0
            entries.append((started,path.stat().st_mtime_ns,prior,candidate))
    except OSError:
        return ''
    if not entries:
        return ''
    entries.sort(key=lambda item:(item[0],item[1]),reverse=True)
    _,_,prior,candidate=entries[0]
    return hint_from_queue(prior,candidate)

def _validated_generation(quick_run_id):
    saved=json.loads((agent_state.project_root()/'outputs/quick_runs'/f'{quick_run_id}.json').read_text())
    run=saved['run']
    if run['status']!='DONE' or run['run_id']!=quick_run_id:raise ValueError('pdf_generation_required')
    md=_local_file(agent_state.project_root()/f'outputs/{quick_run_id}/resume_mr-{quick_run_id}_A.md','.md')
    trace,valid=read_generation_trace(md)
    if not valid:raise ValueError('pdf_generation_trace_invalid')
    from tools.infra.resume_content import validate_generated_content
    content_basis=validate_generated_content(agent_state.project_root(),quick_run_id)
    lead_id=_id(trace['target']['job_lead_id'])
    bound=job_repository.bound_lead(lead_id)
    if not bound:raise ValueError('pdf_job_review_required')
    lead=bound[1]
    if (lead.get('source')!='liepin_official' or not reviewed_official_profile(lead,job_repository.job_profile_dir())
            or lead.get('job_profile_id')!=run['job_profile_id']
            or trace['target'].get('source_jd_sha256')!=lead.get('source_jd_sha256')):
        raise ValueError('pdf_job_review_required')
    from tools.sidecar.handlers.quick_run_results import _official_stage_path, require_current_official_run
    pin = require_current_official_run(run, agent_state.project_root())
    profile_trace = trace.get('inputs', {}).get('job_profile', {})
    if (pin['job_lead_id'] != lead_id or profile_trace.get('sha256') != pin['profile_sha256']
            or profile_trace.get('path') != str(_official_stage_path(agent_state.project_root(), quick_run_id, run['job_profile_id']).resolve())):
        raise ValueError('quick_official_target_changed')
    from tools.policy.exclusions import load_exclusion_policy,match_exclusion,resolve_policy_path
    if match_exclusion(lead.get('company',''),lead.get('legal_entity',''),load_exclusion_policy(resolve_policy_path(agent_state.project_root()))):
        raise ValueError('pdf_target_excluded')
    request=DeliveryRequest('',lead_id,'liepin','',lead['url'],False,lead)
    request_job_key=_job_key(request)
    if DeliveryAttemptStore(agent_state.project_root()/'outputs/submissions/delivery_attempts.sqlite3').has_attempt(request_job_key):
        raise ValueError('delivery_already_attempted'+_existing_attempt_hint(lead_id=lead_id,job_key=request_job_key))
    pdf=_local_file(saved['resume_pdf'],'.pdf')
    if not pdf.resolve().is_relative_to((agent_state.project_root()/'outputs').resolve()) or pdf.stat().st_size>10_000_000:
        raise ValueError('invalid_native_pdf_artifact')
    candidate={key:lead.get(key,'') for key in ('company','position','platform','platform_job_id','platform_job_type',
        'job_profile_id','jd_status','source_jd_sha256','source','legal_entity')}
    candidate.update(job_lead_id=lead_id,job_url=lead['url'],delivery_kind='generated_pdf',
        resume_version='gen_'+md.stem,content_basis=content_basis,matching_score=saved.get('score_total'),
        evaluation_score=saved.get('resume_readiness',{}).get('evaluation_score'),status='pending',round_index=0)
    from tools.infra.export.resume_filename import pdf_filename_for_resume
    candidate['pdf_filename']=pdf_filename_for_resume(md,agent_state.project_root()/'outputs')
    candidate['quality_snapshot']=_quality_snapshot(saved,md.read_bytes(),pdf.read_bytes())
    candidate['quality_sha256']=_quality_digest(candidate['quality_snapshot'])
    return candidate,md.read_text(),pdf.read_bytes(),saved.get('score_total')

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
            # 发送脚本历史上把证据放在 observation 顶层 network；兼容两种位置，但证据要求不变。
            items=sent.get('network') or detail.get('network') or []
            return any(isinstance(item,dict) and item.get('http_status')==200
                and AI_DISCLOSURE_TEXT in str(item.get('request','')) for item in items)
        if evidence=='dom':return sent.get('dom_confirmed') is True
        return False
    except (KeyError,TypeError,AttributeError):return False


def _pre_send_reupload_allowed(queue):
    """附件在平台被移除但尚未最终发送时，允许重新上传同一份已批准 PDF 以继续本次投递。

    只放行“已进入投递但 final_send_started 之前”的附件重传，不解除候选/内容/额度门禁，
    也不改变发送阶段的一次性确认；真正 final send 开始后必须走回执核验，不能再重传。
    """
    delivery=queue.get('pdf_delivery') if isinstance(queue.get('pdf_delivery'),dict) else {}
    if not delivery or delivery.get('final_send_started') or delivery.get('state')=='success':
        return False
    if delivery.get('state') not in {'delivery_in_flight','communication_started','resume_interaction_pending'}:
        return False
    if (queue.get('pdf_upload') or {}).get('state')=='in_flight':
        return False
    binding=queue.get('attachment_binding')
    if isinstance(binding,dict) and binding.get('pdf_sha256'):
        return False
    candidates=queue.get('candidates')
    candidate=candidates[0] if isinstance(candidates,list) and candidates and isinstance(candidates[0],dict) else {}
    return (candidate.get('status')=='approved' and candidate.get('delivery_kind')=='generated_pdf'
            and bool((queue.get('content_review') or {}).get('confirmed')))


def _public(queue):
    c=queue['candidates'][0]
    sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(queue['run_id'],c)
    quality=sealed['quality_snapshot']
    recovery_only=bool(queue.get('daily_interruption') and queue.get('pdf_delivery',{}).get('state')!='success')
    upload=queue.get('pdf_upload') if isinstance(queue.get('pdf_upload'),dict) else {}
    upload_state=_upload_effective_state(queue)
    history=queue.get('pdf_upload_history')
    history=history if isinstance(history,list) else []
    return {'run_id':queue['run_id'],'company':c['company'],'position':c['position'],
            'job_lead_id':c['job_lead_id'],'matching_score':c.get('matching_score'),
            'quality':quality if quality is not None else {'status':'unrecorded'},
            'pdf_sha256':sealed['pdf_sha256'],'pdf_path':sealed['resume_path'],'pdf_filename':c.get('pdf_filename',''),
            'account_effects_accepted':bool(queue.get('pdf_upload',{}).get('accepted_account_effects')),
            'verification_error':queue.get('attachment_binding_error',''),
            'single_delivery_authorized':bool(queue.get('single_delivery_authorization')),
            'phase':queue.get('pdf_delivery',{}).get('state') or ('attachment_verified' if queue.get('attachment_binding') else upload_state or 'prepared'),
            'upload_state':upload_state,
            'upload_attempts':len(history)+(1 if upload else 0),
            'upload_hints':_public_upload_hints(upload),
            'can_retry_upload':upload_state in ('','not_submitted'),
            'can_reupload_attachment':_pre_send_reupload_allowed(queue),
            'attachment_bound':bool(isinstance(queue.get('attachment_binding'),dict) and queue['attachment_binding'].get('pdf_sha256')),
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
    with locked_review_queue(agent_state.review_queue_dir()/'.prepare-pdf'):
        for path in agent_state.review_queue_dir().glob('*.json'):
            q=json.loads(path.read_text())
            if q.get('quick_run_id')==quick_run_id:
                return {'meta':params['meta'],**_public(q)}
        candidate,content,pdf,score=_validated_generation(quick_run_id)
        run_id=agent_state.build_agent_run_id()
        candidate['snapshot']=ReviewSnapshotStore(agent_state.agent_run_dir()).create(run_id,candidate,content,dry_run=False,pdf_content=pdf)
        queue={'run_id':run_id,'quick_run_id':quick_run_id,'source_pdf_sha256':hashlib.sha256(pdf).hexdigest(),
               'created_at':agent_state.utcnow_iso(),'candidates':[candidate]}
        agent_state.save_queue(agent_state.get_queue_file(run_id),queue)
        atomic_write_json(agent_state.get_agent_run_file(run_id),{'run':{'run_id':run_id,'status':'REVIEW_PENDING',
            'job_profile_id':candidate.get('job_profile_id',''),'options':{'delivery_kind':'generated_pdf','native_pdf':True},
            'review_queue':queue,'deliveries_completed':0,'app_verified_deliveries':0},'events':[],'gate_checks':[]})
        return {'meta':params['meta'],**_public(queue)}


def handle_begin_upload(params):
    run_id=_id(params.get('run_id'))
    if params.get('accept_account_effects') is not True:raise ValueError('account_effects_consent_required')
    path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path)
        if q.get('run_id')!=run_id or not q.get('quick_run_id'):raise ValueError('pdf_review_required')
        previous=q.get('pdf_upload')
        reupload_recovery=bool(previous) and _pre_send_reupload_allowed(q)
        # 只有已证明未派发（not_submitted，含旧队列只读归一）或“已进入投递但尚未最终发送且平台附件缺失”的恢复场景才允许重传；
        # unknown/in_flight/uploaded_unverified 的普通重试仍拒绝。
        if previous and _upload_effective_state(q)!='not_submitted' and not reupload_recovery:
            raise ValueError('pdf_upload_already_attempted')
        if reupload_recovery:
            # 旧绑定的 fileId/attachmentId 已随平台附件失效，必须清掉，等新上传核验后再绑定。
            q.pop('attachment_binding',None)
            q.pop('attachment_binding_error',None)
        candidate=q['candidates'][0]
        if candidate.get('status') not in ({'approved'} if previous else {'pending'}) or candidate.get('delivery_kind')!='generated_pdf':raise ValueError('pdf_review_required')
        _public(q)  # 批准和释放文件前必须校验绑定，不能因质量正文被删除而跳过。
        sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,candidate)
        from tools.sidecar.handlers.daily_delivery import check_queue_write
        permit=check_queue_write(q,sealed['pdf_sha256'])
        filename=candidate.get('pdf_filename') or 'cv_'+sealed['pdf_sha256'][:16]+'.pdf'
        from tools.infra.export.resume_filename import check_platform_pdf_filename
        check_platform_pdf_filename(filename)
        upload_ref=uuid4().hex
        candidate.update(status='approved',decided_by='user',decided_at=agent_state.utcnow_iso())
        q['content_review']={'confirmed':True,'basis':candidate.get('content_basis'),'reviewed_at':agent_state.utcnow_iso()}
        if candidate.get('quality_snapshot'):
            # 同一批准动作记录用户已看到的固定质量快照，不增加发送授权。
            q['content_review'].update(quality_sha256=candidate['quality_sha256'],accepted_quality_gaps=candidate['quality_snapshot']['gap_tasks'])
        if previous:q.setdefault('pdf_upload_history',[]).append(previous)
        q['pdf_upload']={'state':'in_flight','upload_ref':upload_ref,'filename':filename,
            'pdf_sha256':sealed['pdf_sha256'],'accepted_account_effects':True,'started_at':agent_state.utcnow_iso()}
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],'upload_ref':upload_ref,'filename':filename,
                'pdf_sha256':sealed['pdf_sha256'],'pdf_bytes':list(Path(sealed['resume_path']).read_bytes()),**permit}


def handle_finish_upload(params):
    run_id=_id(params.get('run_id'))
    path=agent_state.get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_upload_observation')
    with locked_review_queue(path):
        q=agent_state.load_queue(path); upload=q.get('pdf_upload',{})
        if upload.get('state')!='in_flight' or upload.get('upload_ref')!=params.get('upload_ref'):
            raise ValueError('pdf_upload_not_pending')
        if observation.get('filename')!=upload['filename']:raise ValueError('pdf_upload_identity_mismatch')
        # 只有“未派发且观察自证 not_submitted”才是确定性未提交；有写请求或状态未知/超时一律按 unknown 禁止重传。
        status=observation.get('status')
        if status=='uploaded':state='uploaded_unverified'
        elif status=='not_submitted' and not _upload_dispatched(observation):state='not_submitted'
        else:state='unknown'
        # 即使页面宣称成功，仍须另行验证平台附件身份/内容，不能直接进入发送。
        upload.update(state=state,observation=_sanitize_observation(observation),finished_at=agent_state.utcnow_iso())
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_inspect_pdf_packet(params):
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path);u=q.get('pdf_upload',{})
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
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_upload_observation')
    with locked_review_queue(path):
        q=agent_state.load_queue(path);u=q.get('pdf_upload',{})
        if not u or observation.get('filename')!=u['filename']:raise ValueError('pdf_upload_identity_mismatch')
        q['pdf_inspection']={'observed_at':agent_state.utcnow_iso(),'observation':_sanitize_observation(observation)}
        state=_platform_attachment_state(q,observation)
        if state:q['platform_attachment']={'state':state,'observed_at':q['pdf_inspection']['observed_at']}
        from tools.infra.liepin_attachment_contract import verify_legacy_filename_rejection
        reconciliation=verify_legacy_filename_rejection(u,observation)
        if reconciliation:u.update(state='not_submitted',reconciliation=reconciliation)
        # 从最终发送开始，绑定属于不可变发送历史；当前平台附件的后续变化另作观测。
        if u.get('state')=='uploaded_unverified' and not q.get('pdf_delivery',{}).get('final_send_started'):
            from tools.infra.liepin_attachment_contract import verify_uploaded_attachment
            sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,q['candidates'][0])
            try:
                binding=verify_uploaded_attachment(u,observation,sealed['pdf_sha256'],Path(sealed['resume_path']).stat().st_size)
                q['attachment_binding']={**binding,'verified_at':agent_state.utcnow_iso()}
                q.pop('attachment_binding_error',None)
            except ValueError as error:
                q['attachment_binding_error']=str(error)
                q.pop('attachment_binding',None)
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_pdf_target_packet(params):
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path);c=q['candidates'][0]
        sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,c)
        binding=q.get('attachment_binding',{})
        if not binding or binding.get('pdf_sha256')!=sealed['pdf_sha256']:raise ValueError('attachment_verification_required')
        from tools.sidecar.handlers.daily_delivery import require_current_pdf_queue_target
        require_current_pdf_queue_target(q)
        return {'meta':params['meta'],'filename':binding['filename'],'job_url':c['job_url'],
                'company':c['company'],'position':c['position'],'attachment_id':binding['attachment_id']}


def handle_record_pdf_target(params):
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_target_observation')
    with locked_review_queue(path):
        q=agent_state.load_queue(path)
        if not q.get('attachment_binding'):raise ValueError('attachment_verification_required')
        q['pdf_target_view']={'observed_at':agent_state.utcnow_iso(),'observation':_sanitize_observation(observation)}
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}


def handle_authorize_single_pdf_delivery(params):
    if params.get('confirmed') is not True:raise ValueError('single_pdf_confirmation_required')
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path)
        if q.get('daily_cycle') or q.get('pdf_delivery') or len(q.get('candidates',[]))!=1:
            raise ValueError('single_pdf_scope_invalid')
        c=q['candidates'][0];sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,c)
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
        attempts=DeliveryAttemptStore(agent_state.project_root()/'outputs/submissions/delivery_attempts.sqlite3')
        batch=attempts.active_batch();batch_id='single_pdf_'+run_id
        if not batch:raise ValueError('pdf_batch_authorization_required')
        if batch.get('authorization_ref')!=ref:
            attempts.authorize_supplementary_batch(batch_id,batch['batch_id'],1,'generated_pdf',ref)
        elif batch['batch_id']!=batch_id:raise ValueError('delivery_scope_mismatch')
        q['single_delivery_authorization']={'batch_id':batch_id,'authorization_ref':ref,
            'pdf_sha256':sealed['pdf_sha256'],'job_key':job_key,'maximum':1,'confirmed_at':agent_state.utcnow_iso()}
        agent_state.save_queue(path,q)
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

def handle_record_pdf_interaction(params):
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id);observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_chat_observation')
    with locked_review_queue(path):
        q=agent_state.load_queue(path);d=q.get('pdf_delivery',{})
        if d.get('attempt_id')!=params.get('delivery_ref'):raise ValueError('pdf_delivery_not_pending')
        sanitized=_sanitize_observation(observation)
        d.setdefault('interaction_history',[]).append({'action':params.get('action'),'observed_at':agent_state.utcnow_iso(),'observation':sanitized})
        if params.get('action')=='ai_disclosure':
            detail={}
            try:
                for response in sanitized.get('responses',[]):
                    if response.get('method')=='OBSERVE':detail=json.loads(response['payload'])
            except (ValueError,TypeError):detail={}
            if _disclosure_observation_matches(detail,q['candidates'][0]):
                d['ai_disclosure']={'text':AI_DISCLOSURE_TEXT,'text_sha256':disclosure_sha256(),
                    'observed_at':agent_state.utcnow_iso()}
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_public(q)}

def handle_verify_pdf_receipt(params):
    """仅核验已保存的 App 业务响应，不联网、不补发。"""
    from tools.infra.liepin_native_receipt import classify_native_resume_receipt
    from tools.submission.storage import SubmissionRecorder,SubmissionRecord,SubmissionStep
    run_id=_id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path);c=q['candidates'][0];d=q.get('pdf_delivery',{});binding=q.get('attachment_binding',{})
        sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,c)
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
        submission_id=_id(d['submission_id']);directory=agent_state.project_root()/'outputs/submissions/liepin'/submission_id
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
        # 回执已证明实际发送的附件身份；同步进提交日志，避免发送前重传后日志身份过期。
        identity_changed=_record_verified_attachment_identity(saved,binding)
        if saved.get('status')!='success':
            recorder=SubmissionRecorder(agent_state.project_root()/'outputs/submissions','liepin','submit',run_id=submission_id,transport='browser')
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
        elif identity_changed:
            # 幂等重复核验：只原子校正日志中的附件身份，不重复 consume 配额、不改已归档回执与步骤。
            atomic_write_json(directory/'submission_log.json',saved)
            (directory/'submission_log.json').chmod(0o600)
        attempts=DeliveryAttemptStore(agent_state.project_root()/'outputs/submissions/delivery_attempts.sqlite3')
        try:attempts.finish(d['attempt_id'],'success')
        except ValueError as error:
            if str(error)!='delivery_attempt_already_finished':raise
            attempts.resolve_unknown(d['attempt_id'],run_id,sealed['pdf_sha256'],'success')
        d.update(state='success',native_receipt_sha256=archive_sha,verified_at=d.get('verified_at') or agent_state.utcnow_iso())
        c['delivery']={'job_lead_id':c['job_lead_id'],'success':True,'submission_id':submission_id,
            'receipt_source':'app_browser','app_verified':True,'status':'success','code':'submitted',
            'resume_pdf_sha256':sealed['pdf_sha256'],'attachment_id':binding['attachment_id'],'native_receipt_sha256':archive_sha}
        agent_state.save_queue(path,q)
        run_file=agent_state.get_agent_run_file(run_id)
        if run_file.exists():
            run=agent_state.load_agent_run(run_id);run['run'].setdefault('started_at',q.get('created_at',''));run['run'].setdefault('round',0)
            atomic_write_json(run_file,run)
        agent_state.sync_review_run(run_id,q,[c['delivery']])
        return {'meta':params['meta'],**_public(q),'submission_id':submission_id}

# 拆分子模块继续以 native_pdf 作为公开入口 re-export。
from tools.sidecar.handlers.native_pdf_delivery import (  # noqa: E402
    handle_begin_pdf_delivery,
    handle_pdf_interaction_packet,
    handle_record_pdf_communication,
)
from tools.sidecar.handlers.native_pdf_removal import (  # noqa: E402
    handle_begin_pdf_removal,
    handle_finish_pdf_removal,
    handle_recheck_pdf_removal,
)

