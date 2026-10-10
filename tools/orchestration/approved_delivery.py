"""从已批准快照恢复发送；真实未知结果保留占位，不自动重试。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tools.channels.base import DeliveryRequest, deliver_with_fallback
from tools.domain.result import Err, Ok
from tools.domain.value_objects import Candidate, ChannelFailure
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore


def _job_key(request: DeliveryRequest) -> str:
    metadata = request.metadata or {}
    if metadata.get('platform_job_id') and metadata.get('platform_job_type'):
        identity = [request.channel, str(metadata['platform_job_type']), str(metadata['platform_job_id'])]
    else:
        url = urlsplit(request.job_url)
        query = [(k, v) for k, v in parse_qsl(url.query) if not k.startswith('utm_') and k != 'mscid']
        identity = [request.channel, urlunsplit((url.scheme, url.netloc.lower(), url.path, urlencode(sorted(query)), ''))]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def deliver_once(request: DeliveryRequest, channels: list, *, source: str):
    def failure(code, submission_id=''):
        return Err(ChannelFailure(request.channel, code, '投递未获得可确认的成功结果。', submission_id=submission_id))
    metadata = request.metadata or {}
    selected = next((c for c in channels if c.channel_id == request.channel), None)
    platform_default = metadata.get('delivery_kind') == 'platform_default'
    if source == 'liepin_official' and not (platform_default and getattr(selected, 'supports_platform_default', False) is True):
        return failure('official_delivery_contract_unverified')
    if request.dry_run:
        return failure('check_mode_no_real_submit')
    if not any(channel.channel_id == request.channel for channel in channels):
        return failure('no_channel')
    digest = metadata.get('platform_resume_sha256') if platform_default else metadata.get('resume_pdf_sha256')
    if not isinstance(digest, str) or not digest:
        return failure('resume_snapshot_missing')
    store = DeliveryAttemptStore()
    try:
        attempt_id = store.reserve(_job_key(request), request.run_id, digest, delivery_kind=metadata.get('delivery_kind'))
    except ValueError as exc:
        return failure(str(exc) if str(exc) in {'delivery_batch_limit_reached', 'delivery_batch_unresolved', 'delivery_batch_route_not_authorized','daily_limit_reached','daily_unresolved','daily_busy'} else 'delivery_state_unavailable')
    if attempt_id is None:
        return failure('delivery_already_attempted')
    try:
        prepared = replace(request, metadata={**metadata, 'delivery_attempt_id': attempt_id})
        result = deliver_with_fallback(prepared, channels)
    except Exception:
        result = failure('delivery_result_unknown')
    confirmed = (isinstance(result, Ok) and result.value.success and bool(result.value.submission_id)
                 and result.value.outcome in {'', 'submitted'})
    not_sent = ((isinstance(result, Ok) and not result.value.success and result.value.outcome == 'not_submitted')
                or (isinstance(result, Err) and result.error.not_submitted))
    failed = isinstance(result, Ok) and not result.value.success and result.value.outcome == 'failed'
    try:
        store.finish(attempt_id, 'success' if confirmed else 'not_submitted' if not_sent else 'failed' if failed else 'unknown')
    except ValueError:
        return failure('delivery_result_unknown')
    if isinstance(result, Ok) and result.value.success and not confirmed:
        return failure('delivery_receipt_missing')
    if not (confirmed or not_sent or failed):
        return failure('delivery_result_unknown', result.value.submission_id if isinstance(result, Ok) else result.error.submission_id)
    return result


def resume_approved_candidate(run_id: str, candidate: dict, snapshot_root: Path) -> dict:
    from tools.orchestration.agent_loop import _delivery_platform
    data = ReviewSnapshotStore(snapshot_root).load(run_id, candidate)
    output = {'job_lead_id': candidate['job_lead_id'], 'success': False, 'submission_id': ''}
    if candidate.get('status') != 'approved':
        raise ValueError('review_approval_required')
    from tools.policy.exclusions import load_exclusion_policy, match_exclusion, resolve_policy_path
    exclusions = load_exclusion_policy(resolve_policy_path(snapshot_root.parent.parent))
    excluded = match_exclusion(candidate.get('company', ''), candidate.get('legal_entity', ''), exclusions)
    if excluded:
        return {**output, 'code': excluded, 'status': 'blocked'}
    target = Candidate(
        candidate_id=candidate['job_lead_id'], direction=candidate.get('position', ''),
        company=candidate.get('company', ''), job_url=candidate.get('job_url', ''),
        confidence=0, source=candidate.get('source', ''), merged_sources=(),
        platform=candidate.get('platform', ''),
    )
    route = _delivery_platform(target)
    if isinstance(route, Err):
        return {**output, 'code': route.error.reason, 'status': 'blocked'}
    if data['dry_run']:
        return {**output, 'code': 'checked_not_submitted', 'status': 'checked'}
    if route.value != 'liepin':
        return {**output, 'code': 'reviewed_channel_unavailable', 'status': 'blocked'}
    if data['candidate'].get('delivery_kind') == 'platform_default':
        from tools.infra.liepin_default_delivery import LiepinOfficialChannel
        channel = LiepinOfficialChannel()
    else:
        from tools.channels.liepin import LiepinChannel
        channel = LiepinChannel()
    request = DeliveryRequest(
        run_id=run_id, candidate_id=target.candidate_id, channel=route.value,
        job_url=target.job_url, resume_path=data['resume_path'], dry_run=False,
        metadata={**data['candidate'], 'resume_markdown_path': data['resume_markdown_path'],
                  'resume_markdown_sha256': data['markdown_sha256'], 'resume_pdf_sha256': data['pdf_sha256']},
    )
    result = deliver_once(request, [channel], source=target.source)
    if isinstance(result, Err):
        uncertain = result.error.reason in {'delivery_result_unknown', 'delivery_receipt_missing', 'delivery_already_attempted'}
        return {**output, 'code': result.error.reason, 'status': 'unknown' if uncertain else 'blocked',
                'submission_id': result.error.submission_id}
    return {**output, 'success': result.value.success, 'submission_id': result.value.submission_id,
            'receipt_source': 'app_api' if data['candidate'].get('delivery_kind') == 'platform_default' else 'app_browser',
            'app_verified': result.value.success,
            'code': 'submitted' if result.value.success else 'checked_not_submitted' if result.value.outcome == 'not_submitted' else 'delivery_failed',
            'status': 'success' if result.value.success else 'checked' if result.value.outcome == 'not_submitted' else 'blocked'}
