"""原生 WebView PDF 附件移除 handler。

从 ``native_pdf.py`` 拆出：只处理“已成功投递的附件在 App 外被移除”的
确认、观测与复核，队列读写与公开视图仍由原模块提供。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from tools.sidecar.handlers._shared import agent_state
from tools.sidecar.handlers import native_pdf as _origin
from tools.sidecar.handlers._shared.pdf_attachment import (
    record_verified_attachment_identity,
)
from tools.infra.persistence.review_queue import locked_review_queue, atomic_write_json
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore


class _AttachmentMissing(Exception):
    pass


def _reconcile_removal_evidence(q,run_id,log_path):
    """发送前重传使日志附件身份过期时，仅在校验本地归档回执完整自证后校正日志；前提不成立返回 False。"""
    from tools.infra.liepin_native_receipt import SEND_RESUME_URL,classify_native_resume_receipt
    try:
        c=q['candidates'][0];d=q.get('pdf_delivery',{});binding=q.get('attachment_binding',{})
        raw=log_path.read_bytes();saved=json.loads(raw)
        archive_raw=(log_path.parent/'native_receipt.json').read_bytes();archive=json.loads(archive_raw)
        inputs=saved['input_artifacts'];receipt=archive['receipt']
        parsed=classify_native_resume_receipt({'url':SEND_RESUME_URL,'method':'POST','http_status':receipt.get('http_status'),
            'request':json.dumps(receipt['request']),'response':json.dumps(receipt['response'])},binding.get('attachment_id'))
        # 逐项确认：只有“日志是同一成功投递、归档回执字节与摘要一致、队列/快照绑定一致、按当前绑定重算回执完全相等”才允许校正。
        if not (saved.get('status')=='success' and saved.get('run_id')==d.get('submission_id')
                and hashlib.sha256(archive_raw).hexdigest()==inputs.get('native_receipt_sha256')==d.get('native_receipt_sha256')
                and archive.get('parent_run_id')==run_id and archive.get('candidate_id')==c.get('job_lead_id')
                and archive.get('pdf_sha256')==inputs.get('resume_pdf_sha256')==binding.get('pdf_sha256')
                and archive.get('file_id')==binding.get('file_id') and d.get('final_send_started') is True
                and inputs.get('delivery_attempt_id')==d.get('attempt_id')
                and inputs.get('attachment_id') not in (None,'',binding.get('attachment_id'))
                and parsed.get('status')=='success' and parsed==receipt):
            return False
        previous=inputs.get('attachment_id')
        if not record_verified_attachment_identity(saved,binding):return False
        atomic_write_json(log_path,saved);log_path.chmod(0o600)
        d.setdefault('evidence_reconciliations',[]).append({'reason':'receipt_binding_mismatch',
            'previous_attachment_id':previous,'attachment_id':binding['attachment_id'],'source':'native_receipt',
            'log_sha256_before':hashlib.sha256(raw).hexdigest(),'log_sha256_after':hashlib.sha256(log_path.read_bytes()).hexdigest(),
            'reconciled_at':agent_state.utcnow_iso()})
        return True
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return False


def _checked_removal_target(q,run_id):
    from tools.infra.liepin_attachment_contract import attachment_filename_matches
    c=q['candidates'][0];d=q.get('pdf_delivery',{});b=q.get('attachment_binding',{})
    if d.get('state')!='success':raise ValueError('attachment_removal_success_required')
    from tools.infra.submission_evidence import inspect_submission_evidence
    log_path=agent_state.project_root()/'outputs/submissions/liepin'/_origin._id(d['submission_id'])/'submission_log.json'
    proof=inspect_submission_evidence(agent_state.project_root(),log_path)
    if proof['status']!='verified' and proof.get('reason')=='receipt_binding_mismatch':
        # 唯一可自动修复的证据缺口：发送前重传后日志仍记旧附件身份。校正后必须重新复核，不自报成功。
        _reconcile_removal_evidence(q,run_id,log_path)
        proof=inspect_submission_evidence(agent_state.project_root(),log_path)
    if proof['status']!='verified':
        raise ValueError('attachment_removal_evidence_unverified'+(':'+proof['reason'] if proof.get('reason') else ''))
    sealed=ReviewSnapshotStore(agent_state.agent_run_dir()).load(run_id,c)
    try:
        current=q['pdf_inspection'];age=(datetime.now(timezone.utc)-datetime.fromisoformat(current['observed_at'].replace('Z','+00:00'))).total_seconds()
        rows=[];counts=[]
        for response in current['observation']['responses']:
            if response.get('method')=='OBSERVE' and response.get('url')=='https://c.liepin.com/resume/edit':
                value=json.loads(response['payload']);rows+=value.get('attachments',[]);counts.append(value.get('attachment_count'))
        if not -5<=age<=120 or len(counts)!=1 or type(counts[0]) is not int or not 0<=counts[0]<=50:raise ValueError()
        if not rows:raise _AttachmentMissing()
        # 页面可能保留同字节遗留卡：只要求观察完整（行数与计数一致）、fileId 非空唯一，目标卡片恰好一张。
        if (counts[0]<1 or len(rows)!=counts[0]
            or any(not isinstance(r,dict) or not isinstance(r.get('fileId'),str) or not r['fileId'] for r in rows)
            or len({r['fileId'] for r in rows})!=len(rows)):raise ValueError()
        matching=[r for r in rows if r.get('fileId')==b.get('file_id') and r.get('encryAttachmentId')==b.get('attachment_id')
                  and attachment_filename_matches(r,b.get('filename',''))]
        if len(matching)!=1:raise ValueError()
        record=matching[0];download=record.get('download',{});size=Path(sealed['resume_path']).stat().st_size
        if (record.get('fileSize')!=size or download.get('http_status')!=200 or download.get('byte_length')!=size
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
    run_id=_origin._id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path);c=q['candidates'][0];d=q.get('pdf_delivery',{});b=q.get('attachment_binding',{})
        prior=q.get('pdf_attachment_removal',{})
        if prior and prior.get('state')!='not_submitted':raise ValueError('attachment_removal_already_attempted')
        if d.get('state')!='success':raise ValueError('attachment_removal_success_required')
        b,sealed,count=_checked_removal_target(q,run_id)
        removal={'state':'in_flight','removal_ref':uuid4().hex,'confirmed_by_user':True,'started_at':agent_state.utcnow_iso(),
            'filename':b['filename'],'file_id':b['file_id'],'attachment_id':b['attachment_id'],
            'pdf_sha256':sealed['pdf_sha256'],'attachment_count':count}
        if prior:q.setdefault('pdf_attachment_removal_history',[]).append(prior)
        q['pdf_attachment_removal']=removal;agent_state.save_queue(path,q)
        return {'meta':params['meta'],'run_id':run_id,**removal}


def handle_finish_pdf_removal(params):
    run_id=_origin._id(params.get('run_id'));path=agent_state.get_queue_file(run_id);observation=params.get('observation')
    if not isinstance(observation,dict) or len(json.dumps(observation))>65536:raise ValueError('invalid_upload_observation')
    with locked_review_queue(path):
        q=agent_state.load_queue(path);r=q.get('pdf_attachment_removal',{})
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
        r.update(state=state,finished_at=agent_state.utcnow_iso(),observation=_origin._sanitize_observation(observation))
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_origin._public(q)}


def handle_recheck_pdf_removal(params):
    """只核验原请求前拦截证据和当前同一文件，绝不调用移除脚本。"""
    run_id=_origin._id(params.get('run_id'));path=agent_state.get_queue_file(run_id)
    with locked_review_queue(path):
        q=agent_state.load_queue(path);r=q.get('pdf_attachment_removal',{})
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
        r.update(state='not_submitted',reconciliation={'reason':'request_guard_blocked_before_send','checked_at':agent_state.utcnow_iso(),
            'current_attachment_original_bytes_verified':True,'source_observation_sha256':hashlib.sha256(json.dumps(r['observation'],sort_keys=True).encode()).hexdigest()})
        agent_state.save_queue(path,q)
        return {'meta':params['meta'],**_origin._public(q)}
