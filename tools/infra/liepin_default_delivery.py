"""经用户选择的平台默认简历路线；固定端点、单次请求、保守回执。"""
from __future__ import annotations

import hashlib
import json
import re
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from uuid import uuid4

from tools.domain.result import Err, Ok
from tools.domain.value_objects import ChannelFailure, DeliveryResult
from tools.infra.liepin_api import LiepinApiError, LiepinReadOnlyClient, _NoRedirect
from tools.infra.liepin_job_detail import LiepinJobDetailError, fetch_liepin_job_detail
from tools.submission.storage import SubmissionRecorder


# “应聘成功”由 2026-09-29 App 单次请求的受保护回执核实。
_POSITIVE_MESSAGES = {'应聘成功', '投递成功', '申请成功', '简历投递成功', '简历已成功投递'}
_SAFE_FIELDS = {'code','errCode','data','result','success','ok','message','msg','jobId','applyId','receiptId'}


def _schema(value, depth=0):
    if isinstance(value, dict) and depth < 3:
        return {k: _schema(v, depth+1) for k,v in value.items() if k in _SAFE_FIELDS}
    return type(value).__name__


def _decode_result(value):
    if isinstance(value, str) and len(value) <= 65536 and value.strip().startswith('{'):
        try:
            return json.loads(value)
        except (ValueError, RecursionError):
            pass
    return value


def _replay_payload(value, token: str, depth=0):
    """只保留回执字段，凭据回显替换；未知字段永不进入证据文件。"""
    if depth > 5:
        return None
    value = _decode_result(value)
    if isinstance(value, dict):
        return {k: _replay_payload(v, token, depth+1) for k, v in value.items() if k in _SAFE_FIELDS}
    if isinstance(value, str):
        if len(value) > 65536:
            return None
        return value.replace(token, '<redacted>')
    return value if value is None or type(value) in {bool, int, float} else None


def classify_apply_response(payload: object, expected_job_id: int) -> dict:
    result = {'status':'unknown', 'business_code':None, 'schema':_schema(payload),
              'parser_version':3, 'reason':'unrecognized_response'}
    objects, messages = [], []
    def visit(value, depth=0):
        if depth > 5:
            return
        value = _decode_result(value)
        if isinstance(value, dict):
            objects.append(value)
            for key in ('data', 'result'):
                visit(value.get(key), depth+1)
            messages.extend(value[k] for k in ('message', 'msg') if isinstance(value.get(k), str))
        elif isinstance(value, str):
            messages.append(value)
    visit(payload)
    if not isinstance(payload, dict):
        return result
    codes = [obj[key] for obj in objects for key in ('code','errCode') if key in obj]
    if not codes or any(type(code) is not int for code in codes):
        return {**result, 'reason':'invalid_business_code'}
    result['business_code'] = next((code for code in codes if code != 0), 0)
    if any(code != 0 for code in codes):
        return {**result, 'status':'failed', 'reason':'business_rejected'}
    if any(str(obj['jobId']) != str(expected_job_id) for obj in objects if 'jobId' in obj):
        return {**result, 'reason':'job_identity_mismatch'}
    if any(obj.get('success') is False or obj.get('ok') is False for obj in objects):
        return {**result, 'reason':'conflicting_business_signal'}
    if any(re.search(r'未投递|没有投递|投递失败|申请失败|应聘失败|未应聘|已投递过|重复|已申请过|之前已', message) for message in messages):
        return {**result, 'reason':'negative_or_duplicate_message'}
    positive = payload.get('data') is True or any(obj.get('success') is True for obj in objects)
    positive = positive or any(message.strip().rstrip('。！!.') in _POSITIVE_MESSAGES for message in messages)
    return {**result, 'status':'success' if positive else 'unknown',
            'reason':'explicit_business_success' if positive else 'unrecognized_business_result'}


class LiepinDefaultResumeClient:
    def apply(self, token: str, job_id: int, job_kind: str) -> dict:
        if type(job_id) is not int or job_id <= 0 or job_kind not in {'1','2'}:
            raise LiepinApiError('INVALID_INPUT')
        token = LiepinReadOnlyClient._token(token)
        request = Request('https://open-agent.liepin.com/mcp/apply-job',
            data=json.dumps({'jobId':job_id,'jobKind':job_kind}).encode(), method='POST',
            headers={'x-user-token':token,'Content-Type':'application/json','Accept':'application/json'})
        try:
            with build_opener(_NoRedirect()).open(request,timeout=20) as response:
                status = response.status
                body = response.read(2_000_001)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            return {'status':'unknown','http_status':status,'business_code':None,'schema':{}}
        except (OSError, URLError, TimeoutError, HTTPException):
            return {'status':'unknown','http_status':None,'business_code':None,'schema':{}}
        summary = {'status':'unknown','http_status':status,'business_code':None,
                   'response_sha256':hashlib.sha256(body).hexdigest(),'schema':{}}
        if not 200 <= status < 300 or len(body) > 2_000_000:
            return summary
        try:
            payload=json.loads(body)
        except (ValueError,UnicodeError,RecursionError):
            return summary
        # 仅返回受限字段形状/业务码/指纹；不返回原文或请求头。
        safe_payload = _replay_payload(payload, token)
        return {**summary, **classify_apply_response(safe_payload, job_id), '_replay_payload': safe_payload}


class LiepinOfficialChannel:
    channel_id = 'liepin'
    supports_platform_default = True

    def __init__(self, *, token_store=None, read_client=None, write_client=None):
        if token_store is None:
            from tools.infra.liepin_readonly import liepin_readonly
            token_store = liepin_readonly._store
        self._store = token_store
        self._reader = read_client or LiepinReadOnlyClient()
        self._writer = write_client or LiepinDefaultResumeClient()

    def deliver(self, request):
        metadata = request.metadata or {}
        def blocked(code):
            return Err(ChannelFailure('liepin',code,'官方默认简历前置检查未通过，未发送。',not_submitted=True))
        if request.dry_run or metadata.get('delivery_kind') != 'platform_default' or not metadata.get('delivery_attempt_id'):
            return blocked('platform_default_authorization_required')
        from tools.infra.resume_content import require_default_content
        try:require_default_content(Path.cwd(),metadata)
        except ValueError as error:return blocked(str(error))
        try:
            raw_id = metadata.get('platform_job_id','')
            if (type(raw_id) is not int and not (isinstance(raw_id,str) and re.fullmatch(r'[1-9][0-9]*',raw_id))):
                return blocked('INVALID_INPUT')
            job_id = int(raw_id)
            kind = metadata.get('platform_job_type')
            if job_id <= 0 or kind not in {'1','2'}:
                return blocked('INVALID_INPUT')
            token = self._store.load()
            if not token:
                return blocked('AUTH_REQUIRED')
            observed = self._reader.get_resume(token)
            digest = hashlib.sha256(observed.encode()).hexdigest()
            if digest != metadata.get('platform_resume_sha256'):
                return blocked('platform_resume_changed')
            detail = fetch_liepin_job_detail(request.job_url, expected_job_id=str(job_id))
            if detail['source_jd_sha256'] != metadata.get('source_jd_sha256'):
                return blocked('job_detail_changed')
        except (LiepinApiError, LiepinJobDetailError) as exc:
            return blocked(exc.code)
        except Exception:
            return blocked('official_preflight_failed')

        recorder = SubmissionRecorder(Path('outputs/submissions'), 'liepin', 'submit',
            run_id='api-'+uuid4().hex, transport='liepin_api')
        recorder.run_dir.chmod(0o700)
        recorder.set_meta(request.job_url, str(metadata.get('resume_markdown_path','')), '', True,
            browser_channel='official_api', redact_inputs=True, redaction_values=(token,))
        observations = [f for f in recorder.record.input_artifacts['files'] if f['id']=='resume_pdf']
        for artifact in observations:
            artifact.update(id='platform_resume_observation', expected_suffixes=['.md'], suffix_valid=artifact.get('suffix')=='.md')
        recorder.record.input_artifacts['files'] = observations
        recorder.record.input_artifacts.update({
            'delivery_kind':'platform_default','platform_resume_observed_sha256':digest,
            'resume_binding':'observed_before_submission_not_server_locked',
            'source_jd_sha256':metadata['source_jd_sha256'],
            'delivery_attempt_id':metadata['delivery_attempt_id'],
            'parent_run_id':request.run_id,'candidate_id':request.candidate_id,
            'company': metadata.get('company', ''), 'position': metadata.get('position', ''),
            'resume_version': metadata.get('resume_version', ''), 'job_profile_id': metadata.get('job_profile_id', ''),
        })
        for name, description in (
            ('idempotency','本次发送已取得持久化占位'),
            ('credential_check','官方只读认证通过'),
            ('target_check','原始岗位 ID 与当前完整 JD 指纹一致'),
            ('resume_observed','当前平台简历文本与已批准观测快照一致；非服务端版本锁'),
            ('authorization','已批准 platform_default 路线；不发送生成 PDF'),
        ):
            recorder.add_step(name,'success',description)
        recorder.finish('running')
        from tools.infra.persistence.daily_delivery import DailyDeliveryStore
        try:
            require_default_content(Path.cwd(),metadata,observed)
            DailyDeliveryStore().write_permit(None,request.run_id,digest,attempt_id=metadata['delivery_attempt_id'])
        except ValueError as error:
            recorder.add_step('submit_safety','blocked',str(error))
            recorder.finish('blocked',str(error))
            return blocked(str(error))
        try:
            receipt = self._writer.apply(token,job_id,kind)
        except Exception:
            receipt = {'status':'unknown','http_status':None,'business_code':None,'schema':{}}
        # 原业务证据独立保护，普通步骤日志只保存指纹及解析摘要。
        replay = receipt.pop('_replay_payload', None)
        if replay is not None:
            from tools.infra.persistence.review_queue import atomic_write_json
            archive = recorder.run_dir / 'api_receipt.json'
            try:
                atomic_write_json(archive, {
                    'parent_run_id': request.run_id, 'candidate_id': request.candidate_id,
                    'job_id': job_id, 'job_kind': kind, 'resume_sha256': digest,
                    'response_sha256': receipt.get('response_sha256'),
                    'http_status': receipt.get('http_status'), 'payload': replay,
                })
                archive.chmod(0o600)
                recorder.record.input_artifacts['api_receipt_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
            except OSError:
                receipt.update(status='unknown', reason='receipt_evidence_unavailable')
        recorder.record.input_artifacts['receipt_source'] = 'app_api'
        status = receipt.get('status','unknown')
        if status not in {'success','failed','unknown'}:
            status = 'unknown'
        http_status = receipt.get('http_status')
        recorder.add_step('api_submit','success' if type(http_status) is int and 200 <= http_status < 300 else 'unknown',
            '单次官方 apply-job 请求；无自动重试')
        recorder.add_step('receipt',status,json.dumps(receipt,ensure_ascii=False))
        recorder.finish(status, '' if status=='success' else 'official_apply_failed' if status=='failed' else 'delivery_result_unknown')
        confirmed = status=='success' and recorder.confirmed_submission()
        return Ok(DeliveryResult('liepin',confirmed,recorder.record.run_id,
            str(recorder.log_json),outcome='submitted' if confirmed else 'failed' if status=='failed' else 'unknown'))


def _load_saved_receipt(directory: Path) -> tuple[dict, str]:
    import os
    import stat
    archive, log = directory / 'api_receipt.json', directory / 'submission_log.json'
    if directory.is_symlink() or archive.is_symlink() or log.is_symlink():
        raise ValueError('receipt_evidence_unavailable')
    info = archive.stat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_size > 2_000_000):
        raise ValueError('receipt_evidence_unavailable')
    encoded = archive.read_bytes()
    digest = hashlib.sha256(encoded).hexdigest()
    record = SubmissionRecorder.load_existing(log).record
    inputs, proof = record.input_artifacts, json.loads(encoded)
    original = next((json.loads(step.detail) for step in record.steps if step.name == 'receipt'), {})
    if (record.transport != 'liepin_api' or record.mode != 'submit' or record.run_id != directory.name
            or digest != inputs.get('api_receipt_sha256')
            or proof.get('parent_run_id') != inputs.get('parent_run_id')
            or proof.get('candidate_id') != inputs.get('candidate_id')
            or proof.get('resume_sha256') != inputs.get('platform_resume_observed_sha256')
            or not proof.get('response_sha256') or proof['response_sha256'] != original.get('response_sha256')
            or type(proof.get('http_status')) is not int or not 200 <= proof['http_status'] < 300):
        raise ValueError('receipt_evidence_unavailable')
    return proof, digest


def recheck_api_receipt(root: Path, run_id: str, candidate: dict) -> dict:
    """解析已有真实响应；允许按完整响应指纹引用同一份已接收内容，不联网。"""
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore

    snapshot = ReviewSnapshotStore(root / 'outputs/agent_runs').load(run_id, candidate)
    submission_id = candidate.get('delivery', {}).get('submission_id', '')
    if (not isinstance(submission_id, str) or not re.fullmatch(r'api-[0-9a-f]{32}', submission_id)
            or candidate.get('delivery_kind') != 'platform_default' or candidate.get('status') != 'approved'):
        raise ValueError('receipt_evidence_unavailable')
    directory = root / 'outputs/submissions/liepin' / submission_id
    if directory.is_symlink() or (directory / 'submission_log.json').is_symlink():
        raise ValueError('receipt_evidence_unavailable')
    recorder = SubmissionRecorder.load_existing(directory / 'submission_log.json')
    inputs = recorder.record.input_artifacts
    original = next((json.loads(step.detail) for step in recorder.record.steps if step.name == 'receipt'), {})
    if (recorder.record.transport != 'liepin_api' or recorder.record.mode != 'submit'
            or recorder.record.run_id != submission_id or inputs.get('parent_run_id') != run_id
            or inputs.get('candidate_id') != candidate['job_lead_id']
            or inputs.get('platform_resume_observed_sha256') != snapshot['markdown_sha256']
            or inputs.get('source_jd_sha256') != candidate.get('source_jd_sha256')
            or type(original.get('http_status')) is not int or not 200 <= original['http_status'] < 300
            or not re.fullmatch(r'[0-9a-f]{64}', str(original.get('response_sha256', '')))):
        raise ValueError('receipt_evidence_unavailable')
    reference = None
    archive = directory / 'api_receipt.json'
    if archive.exists() or archive.is_symlink():
        proof, evidence_sha = _load_saved_receipt(directory)
        if (str(proof.get('job_id')) != str(candidate['platform_job_id'])
                or proof.get('job_kind') != candidate['platform_job_type']):
            raise ValueError('receipt_evidence_unavailable')
    else:
        matches = []
        for path in sorted(directory.parent.glob('api-*/api_receipt.json')):
            try:
                saved, digest = _load_saved_receipt(path.parent)
                if saved['response_sha256'] == original['response_sha256']:
                    matches.append((saved, digest, path.parent.name))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        if not matches or len({json.dumps(p['payload'], sort_keys=True) for p, _, _ in matches}) != 1:
            raise ValueError('receipt_evidence_unavailable')
        proof, evidence_sha, reference_id = matches[0]
        reference = {'source':'matching_response_sha256', 'submission_id':reference_id,
                     'evidence_sha256':evidence_sha, 'response_sha256':original['response_sha256']}
    receipt = classify_apply_response(proof['payload'], int(candidate['platform_job_id']))
    if receipt['status'] == 'unknown':
        return {**candidate['delivery'], 'receipt_reason':receipt['reason'], 'parser_version':receipt['parser_version']}
    status = receipt['status']
    if inputs.get('receipt_source') != 'app_api':
        inputs.setdefault('prior_receipt_source', inputs.get('receipt_source', ''))
    inputs['receipt_source'] = 'app_api'
    if reference:
        inputs['api_receipt_reference'] = reference
    recorder.add_step('receipt', status, json.dumps({**receipt,
        'source':'matching_response_sha256' if reference else 'saved_api_response',
        'evidence_sha256':evidence_sha}, ensure_ascii=False))
    recorder.finish(status, '' if status == 'success' else 'official_apply_failed')
    if status == 'success' and not recorder.confirmed_submission():
        raise ValueError('receipt_evidence_unavailable')
    DeliveryAttemptStore(root / 'outputs/submissions/delivery_attempts.sqlite3').resolve_unknown(
        inputs['delivery_attempt_id'], run_id, snapshot['markdown_sha256'], status)
    return {'job_lead_id':candidate['job_lead_id'], 'success':status == 'success',
            'status':'success' if status == 'success' else 'blocked',
            'code':'submitted' if status == 'success' else 'delivery_failed',
            'submission_id':submission_id, 'receipt_source':'app_api', 'app_verified':status == 'success',
            'receipt_reason':receipt['reason'], 'parser_version':receipt['parser_version']}
