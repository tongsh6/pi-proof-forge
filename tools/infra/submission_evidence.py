"""两条受控投递路线的本地只读证据检查；不联网、不修改投递结果。"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from tools.infra.liepin_default_delivery import _load_saved_receipt, classify_apply_response
from tools.infra.liepin_native_receipt import SEND_RESUME_URL, classify_native_resume_receipt
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.submission.storage import submission_required_steps_evidence


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _id(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value), 'invalid_identity')
    return value


def _read(path, root, maximum=4_000_000):
    path=Path(path);root=Path(root).resolve()
    _require(path.resolve().is_relative_to(root), 'artifact_outside_root')
    current=path.absolute()
    while current != root and current != current.parent:
        _require(not current.is_symlink(), 'artifact_symlink')
        current=current.parent
    _require(path.is_file() and path.stat().st_size <= maximum, 'artifact_unavailable')
    data=path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def inspect_submission_evidence(root: Path, log_path: Path) -> dict:
    """成功仅表示已有业务证据完整；不会把失败/未知投递提升为成功。"""
    root=root.resolve(); result={'status':'incomplete','reason':'evidence_unavailable'}
    try:
        log,log_sha=_read(log_path,root/'outputs/submissions')
        inputs=log.get('input_artifacts',{});sid=_id(log['run_id']);rid=_id(inputs['parent_run_id']);lead=_id(inputs['candidate_id'])
        _require(Path(log_path).parent.name==sid and log.get('platform')=='liepin' and log.get('mode')=='submit','submission_identity_mismatch')
        result.update(submission_id=sid,parent_run_id=rid,job_lead_id=lead,submission_log_sha256=log_sha,
                      receipt_source=inputs.get('receipt_source',''),delivery_kind=inputs.get('delivery_kind',''))
        queue,_=_read(root/'outputs/review_queue'/f'{rid}.json',root/'outputs/review_queue')
        candidates=[c for c in queue['candidates'] if c.get('job_lead_id')==lead]
        _require(queue.get('run_id')==rid and len(candidates)==1,'approval_identity_mismatch')
        c=candidates[0];sealed=ReviewSnapshotStore(root/'outputs/agent_runs').load(rid,c)
        kind=c.get('delivery_kind');source='app_api' if kind=='platform_default' else 'app_browser'
        digest=sealed['markdown_sha256'] if kind=='platform_default' else sealed['pdf_sha256']
        result.update(company=c['company'],position=c['position'],resume_version_id=c['resume_version'],
                      job_profile_id=c.get('job_profile_id',''),resume_sha256=digest,snapshot_sha256=c['snapshot']['sha256'])
        _require(kind in {'platform_default','generated_pdf'} and inputs.get('delivery_kind')==kind,'delivery_kind_mismatch')
        _require(c.get('status')=='approved' and c.get('jd_status')=='complete_reviewed' and sealed['dry_run'] is False,'approval_required')
        for key in ['company','position','resume_version','job_profile_id','source_jd_sha256']:
            _require(key not in inputs or inputs[key]==c.get(key),'submission_identity_mismatch')
        _require(log.get('status')=='success' and inputs.get('receipt_source')==source,'business_success_unconfirmed')
        delivery=c.get('delivery',{})
        _require(delivery.get('success') is True and delivery.get('submission_id')==sid and delivery.get('receipt_source')==source,'approval_result_mismatch')
        _require(submission_required_steps_evidence(log)['passed'],'required_steps_missing')
        sha_field='platform_resume_observed_sha256' if kind=='platform_default' else 'resume_pdf_sha256'
        _require(inputs.get(sha_field)==digest,'resume_binding_mismatch')
        directory=Path(log_path).parent
        if kind=='platform_default':
            reference=inputs.get('api_receipt_reference')
            archive=directory/'api_receipt.json'
            if archive.exists():
                _read(archive,root/'outputs/submissions')
                proof,receipt_sha=_load_saved_receipt(directory)
                _require(str(proof['job_id'])==str(c['platform_job_id']) and proof['job_kind']==c['platform_job_type'],'receipt_target_mismatch')
            else:
                _require(isinstance(reference,dict) and reference.get('source')=='matching_response_sha256','receipt_unavailable')
                archive=directory.parent/_id(reference['submission_id'])/'api_receipt.json'
                _read(archive,root/'outputs/submissions')
                proof,receipt_sha=_load_saved_receipt(archive.parent)
                original=next(json.loads(s['detail']) for s in log['steps'] if s['name']=='receipt')
                _require(receipt_sha==reference['evidence_sha256'] and proof['response_sha256']==reference['response_sha256']==original.get('response_sha256')
                    and type(original.get('http_status')) is int and 200<=original['http_status']<300,'receipt_reference_mismatch')
            _require(classify_apply_response(proof['payload'],int(c['platform_job_id']))['status']=='success','business_success_unconfirmed')
        else:
            archive=directory/'native_receipt.json';proof,receipt_sha=_read(archive,root/'outputs/submissions')
            binding=queue['attachment_binding'];native=queue['pdf_delivery'];receipt=proof['receipt']
            _require(receipt_sha==inputs.get('native_receipt_sha256')==native.get('native_receipt_sha256'),'receipt_hash_mismatch')
            _require(proof.get('parent_run_id')==rid and proof.get('candidate_id')==lead and proof.get('pdf_sha256')==digest==binding.get('pdf_sha256')
                and proof.get('file_id')==binding.get('file_id') and inputs.get('attachment_id')==binding.get('attachment_id')
                and native.get('final_send_started') is True and native.get('submission_id')==sid and native.get('attempt_id')==inputs.get('delivery_attempt_id'),'receipt_binding_mismatch')
            parsed=classify_native_resume_receipt({'url':SEND_RESUME_URL,'method':'POST','http_status':receipt.get('http_status'),
                'request':json.dumps(receipt['request']),'response':json.dumps(receipt['response'])},binding['attachment_id'])
            _require(parsed.get('status')=='success' and parsed==receipt,'business_success_unconfirmed')
        db=root/'outputs/submissions/delivery_attempts.sqlite3'
        _require(db.is_file() and not db.is_symlink(),'attempt_database_unavailable')
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as connection:
            attempt=connection.execute('SELECT run_id,pdf_sha256,state,batch_id FROM attempts WHERE attempt_id=?',(inputs['delivery_attempt_id'],)).fetchone()
            _require(attempt is not None and attempt[:3]==(rid,digest,'success'),'attempt_binding_mismatch')
            batch=connection.execute('SELECT authorized_max,allowed_delivery_kind FROM delivery_batches WHERE batch_id=?',(attempt[3],)).fetchone()
            _require(batch is not None and batch[0]>0 and batch[1] in {None,kind},'batch_authorization_missing')
            count=connection.execute('SELECT COUNT(*) FROM attempts WHERE batch_id=?',(attempt[3],)).fetchone()[0]
            _require(count<=batch[0],'batch_limit_exceeded')
        result.update(status='verified',reason='',receipt_sha256=receipt_sha,receipt_path=str(archive.relative_to(root)),
                      batch_id=attempt[3],delivery_attempt_id=inputs['delivery_attempt_id'],required_steps_passed=True)
    except ValueError as error:
        result['reason']=str(error) if str(error) in {
            'invalid_identity','artifact_outside_root','artifact_symlink','artifact_unavailable','submission_identity_mismatch',
            'approval_identity_mismatch','delivery_kind_mismatch','approval_required','business_success_unconfirmed','approval_result_mismatch',
            'required_steps_missing','resume_binding_mismatch','receipt_target_mismatch','receipt_unavailable','receipt_reference_mismatch',
            'receipt_hash_mismatch','receipt_binding_mismatch','attempt_database_unavailable','attempt_binding_mismatch','batch_authorization_missing',
            'batch_limit_exceeded','review_snapshot_invalid','receipt_evidence_unavailable'} else 'evidence_unavailable'
    except (OSError,KeyError,TypeError,AttributeError,StopIteration,sqlite3.Error):
        result['reason']='evidence_unavailable'
    return result
