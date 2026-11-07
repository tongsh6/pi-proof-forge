"""原生 WebView PDF 投递开始/沟通/确认交互 handler。

从 ``native_pdf.py`` 拆出；共享的队列、公开视图与 AI 声明判定仍由原模块
（经 ``_origin`` 运行时访问）提供，保证既有测试 patch 语义不变。
"""
from __future__ import annotations

import json

from tools.sidecar.handlers._shared import agent_state
from tools.sidecar.handlers import native_pdf as _origin
from tools.infra.persistence.review_queue import locked_review_queue
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.channels.base import DeliveryRequest
from tools.orchestration.approved_delivery import _job_key


def handle_begin_pdf_delivery(params):
    run_id=_origin._id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path);c=q['candidates'][0]
        if q.get('pdf_delivery'):raise ValueError('pdf_delivery_already_started')
        sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,c)
        binding=q.get('attachment_binding',{})
        if c.get('status')!='approved' or not binding or binding.get('pdf_sha256')!=sealed['pdf_sha256']:
            raise ValueError('attachment_verification_required')
        target={}
        for response in q.get('pdf_target_view',{}).get('observation',{}).get('responses',[]):
            if response.get('method')=='OBSERVE':target=json.loads(response['payload'])
        if not all(target.get(k) is True for k in ('url_match','company_present','position_present')) or target.get('challenge') or target.get('unavailable'):
            raise ValueError('pdf_target_verification_required')
        from tools.policy.exclusions import load_exclusion_policy,match_exclusion,resolve_policy_path
        if match_exclusion(c.get('company',''),c.get('legal_entity',''),load_exclusion_policy(resolve_policy_path(agent_state.project_root()))):
            raise ValueError('pdf_target_excluded')
        from tools.infra.liepin_job_detail import fetch_liepin_job_detail
        current=fetch_liepin_job_detail(c['job_url'],expected_job_id=str(c['platform_job_id']))
        if current['source_jd_sha256']!=c['source_jd_sha256']:raise ValueError('job_detail_changed')
        attempts=DeliveryAttemptStore(agent_state.project_root()/'outputs/submissions/delivery_attempts.sqlite3')
        from tools.sidecar.handlers.daily_delivery import check_queue_write,store as daily_store
        check_queue_write(q,sealed['pdf_sha256'])
        request=DeliveryRequest(run_id,c['job_lead_id'],'liepin',sealed['resume_path'],c['job_url'],False,c)
        if q.get('daily_cycle'):
            ref=daily_store().reserve_daily(q['daily_cycle'],run_id,_job_key(request),sealed['pdf_sha256'])
        else:
            batch=attempts.active_batch()
            if not batch or batch.get('allowed_delivery_kind')!='generated_pdf':raise ValueError('pdf_batch_authorization_required')
            ref=attempts.reserve(_job_key(request),run_id,sealed['pdf_sha256'],delivery_kind='generated_pdf')
        if not ref:raise ValueError('delivery_already_attempted'+_origin._existing_attempt_hint(job_key=_job_key(request)))
        from tools.submission.storage import SubmissionRecorder
        recorder=SubmissionRecorder(agent_state.project_root()/'outputs/submissions','liepin','submit',run_id='native-'+ref,transport='browser')
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
        q['pdf_delivery']={'state':'delivery_in_flight','attempt_id':ref,'submission_id':'native-'+ref,'started_at':agent_state.utcnow_iso()}
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],'run_id':run_id,'delivery_ref':ref,'filename':binding['filename'],
                'attachment_id':binding['attachment_id'],'job_url':c['job_url'],'company':c['company'],'position':c['position'],
                **check_queue_write(q,sealed['pdf_sha256'])}


def handle_record_pdf_communication(params):
    run_id=_origin._id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_chat_observation')
    with locked_review_queue(path):
        q=agent_state.load_queue(path);delivery=q.get('pdf_delivery',{})
        if delivery.get('state')!='delivery_in_flight' or delivery.get('attempt_id')!=params.get('delivery_ref'):
            raise ValueError('pdf_delivery_not_pending')
        delivery.update(state='communication_started',observation=_origin._sanitize_observation(observation))
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_origin._public(q)}


def handle_pdf_interaction_packet(params):
    run_id=_origin._id(params.get('run_id'));action=params.get('action');path=agent_state.get_queue_file(run_id)
    if action not in {'inspect','prepare','send'}:raise ValueError('unsupported_pdf_interaction')
    with locked_review_queue(path):
        q=agent_state.load_queue(path);d=q.get('pdf_delivery',{});c=q['candidates'][0]
        sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,c)
        binding=q.get('attachment_binding',{})
        if d.get('state') not in {'communication_started','resume_interaction_pending','final_send_pending'}:
            raise ValueError('pdf_delivery_not_pending')
        if binding.get('pdf_sha256')!=sealed['pdf_sha256']:
            # 状态在投递中但附件绑定缺失/失效：提示先重新核验附件，避免误报“投递流程未开始”。
            raise ValueError('attachment_verification_required')
        if action=='prepare':
            if q.get('daily_interruption'):raise ValueError('daily_recovery_required')
            # 开关开启时，准备前必须先发出 AI 声明；声明本身是独立、可核对的一次聊天写入。
            if (not d.get('final_send_started') and _origin._ai_disclosure_enabled() and _origin._disclosure_recorded(q) is None):
                return _origin._ai_disclosure_requirement(params,action,d,binding,c)
            # 首次 prepare 的点击可能未生效（入口未打开/目标未核验）；确认框抓取成功前允许重试，避免一次失败锁死投递。
            if d.get('resume_interaction_started') and _origin._dialog_captured(q):raise ValueError('resume_interaction_already_started')
            d.update(state='resume_interaction_pending',resume_interaction_started=True)
            agent_state.save_queue(path,q)
        if action=='send':
            from tools.sidecar.handlers.daily_delivery import check_queue_write
            # 每日中断/恢复、内容与额度门禁先于声明写入，避免恢复态借助声明步骤产生新的平台写入。
            check_queue_write(q,sealed['pdf_sha256'])
            if d.get('final_send_started'):raise ValueError('pdf_final_send_already_started')
            if _origin._ai_disclosure_enabled() and _origin._disclosure_recorded(q) is None:
                return _origin._ai_disclosure_requirement(params,action,d,binding,c)
            if not _origin._confirmation_matches(q):raise ValueError('pdf_confirmation_not_verified')
            d.update(state='final_send_pending',final_send_started=True,final_send_started_at=agent_state.utcnow_iso())
            agent_state.save_queue(path,q)
        return {'meta':params['meta'],'action':action,'delivery_ref':d['attempt_id'],'filename':binding['filename'],
                'attachment_id':binding['attachment_id'],'file_id':binding.get('file_id',''),'job_url':c['job_url'],'company':c['company'],'position':c['position']}
