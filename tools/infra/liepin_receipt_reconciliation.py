"""保留人工外部观察的历史事实；不作为 App 自动回执或闭环验收。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.infra.persistence.job_lead_binding import same_official_source_url
from tools.infra.persistence.review_queue import atomic_write_json, locked_review_queue
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.submission.storage import SubmissionRecorder


def confirm_from_external_receipt(root: Path, run_id: str, lead_id: str, evidence_path: Path) -> dict:
    """历史人工核验工具，不暴露产品 RPC，不调用发送渠道。"""
    if not all(isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}',v) for v in (run_id,lead_id)):
        raise ValueError('invalid_receipt_identity')
    evidence_bytes=evidence_path.read_bytes()
    proof=json.loads(evidence_bytes)
    proof_hash=hashlib.sha256(evidence_bytes).hexdigest()
    queue_path=root/'outputs/review_queue'/f'{run_id}.json'
    with locked_review_queue(queue_path):
        queue=json.loads(queue_path.read_text())
        row=next(c for c in queue['candidates'] if c['job_lead_id']==lead_id)
        snapshot=ReviewSnapshotStore(root/'outputs/agent_runs').load(run_id,row)
        if (proof.get('origin')!='external_native_browser' or proof.get('record_page')!='https://c.liepin.com/job/record/apply'
                or proof.get('status')!='已投递' or not same_official_source_url(proof.get('job_url',''),row['job_url'])
                or row.get('delivery_kind')!='platform_default' or row.get('status')!='approved'):
            raise ValueError('external_receipt_mismatch')
        if row.get('delivery',{}).get('success'):
            if row['delivery'].get('external_receipt_sha256')!=proof_hash:
                raise ValueError('external_receipt_already_resolved')
            return row['delivery']
        if row.get('delivery',{}).get('status')!='unknown':
            raise ValueError('external_receipt_requires_unknown_attempt')
        matches=[]
        for path in (root/'outputs/submissions/liepin').glob('api-*/submission_log.json'):
            record=json.loads(path.read_text())
            inputs=record.get('input_artifacts',{})
            if inputs.get('parent_run_id')==run_id and inputs.get('candidate_id')==lead_id:
                matches.append(path)
        if len(matches)!=1:
            raise ValueError('external_receipt_ambiguous_attempt')
        recorder=SubmissionRecorder.load_existing(matches[0])
        inputs=recorder.record.input_artifacts
        started=datetime.fromisoformat(recorder.record.started_at.replace('Z','+00:00'))
        applied=datetime.fromisoformat(proof['platform_applied_at'].replace('Z','+00:00'))
        recorded=datetime.fromisoformat(proof['recorded_at'].replace('Z','+00:00'))
        receipt_steps=[s for s in recorder.record.steps if s.name=='receipt']
        original=json.loads(receipt_steps[0].detail) if receipt_steps else {}
        if (recorder.record.transport!='liepin_api' or recorder.record.mode!='submit'
                or original.get('http_status')!=200 or original.get('business_code')!=0
                or not -60 <= (applied-started).total_seconds() <= 120
                or recorded < applied
                or inputs.get('platform_resume_observed_sha256')!=snapshot['markdown_sha256']):
            raise ValueError('external_receipt_correlation_failed')
        inputs.setdefault('api_response_received_at',recorder.record.ended_at)
        inputs.update(external_receipt_sha256=proof_hash,receipt_source='website_history',app_verified=False)
        for artifact in inputs.get('files',[]):
            if artifact.get('id')=='resume_pdf' and artifact.get('suffix')=='.md':
                artifact.update(id='platform_resume_observation',expected_suffixes=['.md'],suffix_valid=True)
        if not any(s.name=='receipt' and s.status=='success' for s in recorder.record.steps):
            recorder.add_step('receipt','success','authenticated website history verified; evidence_sha256='+proof_hash)
        recorder.finish('success')
        # 外部事实已在上方关联核验；不可借用 App 自动回执的 confirmed_submission 门禁。
        DeliveryAttemptStore(root/'outputs/submissions/delivery_attempts.sqlite3').confirm_unknown(
            inputs['delivery_attempt_id'],run_id,snapshot['markdown_sha256'])
        result={'job_lead_id':lead_id,'success':True,'submission_id':recorder.record.run_id,
                'status':'externally_confirmed','code':'external_observation_confirmed','app_verified':False,
                'receipt_source':'website_history','external_receipt_sha256':proof_hash}
        row['delivery']=result
        atomic_write_json(queue_path,queue)
        run_file=root/'outputs/agent_runs'/f'{run_id}.json'
        if run_file.exists():
            payload=json.loads(run_file.read_text()); run=payload['run']
            run.update(review_queue=queue,delivery_results=[c['delivery'] for c in queue['candidates'] if 'delivery' in c],
                       deliveries_completed=sum(bool(c.get('delivery',{}).get('success')) for c in queue['candidates']))
            results = run['delivery_results']
            run['app_verified_deliveries'] = sum(bool(r.get('success')) and r.get('receipt_source') in {'app_api','app_browser'} for r in results)
            run['externally_confirmed_deliveries'] = sum(bool(r.get('success')) and r.get('receipt_source') == 'website_history' for r in results)
            run['status'] = ('REVIEW_PENDING' if any(c.get('status')=='pending' or (c.get('status')=='approved' and 'delivery' not in c) for c in queue['candidates'])
                             else 'DELIVERY_BLOCKED' if any(r.get('status') in {'blocked','unknown'} for r in results)
                             else 'EXTERNAL_CONFIRMATION_ONLY')
            payload.setdefault('events',[]).append({'event_type':'DELIVER','round_index':row.get('round_index',0),
                'timestamp':proof['recorded_at'],'payload':{**result,'event_key':'external-receipt:'+proof_hash}})
            atomic_write_json(run_file,payload)
        return result
