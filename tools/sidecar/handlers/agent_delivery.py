"""Agent 投递前置：岗位线索、完整 JD 读取、默认简历准备与回执复核。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.persistence.review_queue import locked_review_queue

from ._shared.agent_runtime import _coerce_positive_int, _utcnow_iso


def _facade():
    """门面模块：路径常量、运行态与跨域流程由 handlers/agent.py 持有（可被测试 patch）。"""
    from tools.sidecar.handlers import agent

    return agent



# 跨域薄包装：统一经门面调用，保证测试 patch handlers/agent.py 的符号语义不变。
def _get_queue_file(run_id: str | None = None) -> Path:
    return _facade()._get_queue_file(run_id)


def _load_queue(queue_file: Path) -> dict[str, Any]:
    return _facade()._load_queue(queue_file)


def _save_queue(queue_file: Path, queue: dict[str, Any]) -> None:
    _facade()._save_queue(queue_file, queue)


def _delivery_summary(run: dict[str, Any]) -> dict:
    return _facade()._delivery_summary(run)


def _delivery_confirmation(result: dict) -> dict:
    return _facade()._delivery_confirmation(result)


def _sync_review_run(run_id: str, queue: dict, deliveries: list[dict]) -> None:
    _facade()._sync_review_run(run_id, queue, deliveries)


def _persisted_llm_runtime_context() -> tuple[dict[str, Any], dict[str, str]]:
    return _facade()._persisted_llm_runtime_context()


def _load_agent_run(run_id: str) -> dict[str, Any]:
    return _facade()._load_agent_run(run_id)


def _save_agent_run(run_file: Path, payload: dict[str, Any]) -> None:
    _facade()._save_agent_run(run_file, payload)


def _get_agent_run_file(run_id: str) -> Path:
    return _facade()._get_agent_run_file(run_id)


def _review_queue_dir() -> Path:
    return _facade()._REVIEW_QUEUE_DIR


def _evidence_card_dir() -> Path:
    return _facade()._PROJECT_ROOT / "evidence_cards"


def _is_saved_eligible_evidence(doc: dict[str, dict[str, Any]]) -> bool:
    return _facade()._is_saved_eligible_evidence(doc)

def _read_domain_job_profile(job_profile_id: str) -> Any:
    from tools.domain.models import JobProfile
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile

    profile_path = _facade()._PROJECT_ROOT / "job_profiles" / f"{job_profile_id}.yaml"
    if not profile_path.exists():
        raise ValueError(f"job_profile_not_found: {job_profile_id}")
    doc = parse_simple_yaml(profile_path.read_text(encoding="utf-8"))
    status = doc["scalars"].get("status", "").strip()
    if status and status != "active":
        raise ValueError(f"job_profile_not_active: {job_profile_id}")
    if doc["scalars"].get("source") == "liepin_official":
        lead_id = doc["scalars"].get("job_lead_id", "")
        if not lead_id or "/" in lead_id or "\\" in lead_id:
            raise ValueError("job_profile_review_required")
        lead_path = _facade()._PROJECT_ROOT / "job_leads" / f"{lead_id}.yaml"
        if not lead_path.is_file():
            raise ValueError("job_profile_review_required")
        lead = parse_simple_yaml(lead_path.read_text())["scalars"]
        if lead.get("job_profile_id") != job_profile_id or not reviewed_official_profile(lead, _facade()._PROJECT_ROOT / "job_profiles"):
            raise ValueError("job_profile_review_required")
    return JobProfile(
        id=job_profile_id,
        title=doc["scalars"].get("target_role", job_profile_id),
        keywords=tuple(doc["lists"].get("keywords", [])),
        level=doc["scalars"].get("seniority", ""),
        tone=doc["scalars"].get("tone", ""),
        must_have=tuple(doc["lists"].get("must_have", [])),
        nice_to_have=tuple(doc["lists"].get("nice_to_have", [])),
        company=doc["scalars"].get("company", ""),
        business_domain=doc["scalars"].get("business_domain", ""),
        seniority_signal=tuple(doc["lists"].get("seniority_signal", [])),
        jd_text=doc["scalars"].get("source_jd", ""),
    )


def _generation_context(job_profile_id: str) -> tuple[dict, dict]:
    """加载个人资料与岗位上下文供真实生成/评测引擎使用；缺失时返回空上下文。"""
    from tools.engines.generation.resume_renderer import load_generation_context

    root = _facade()._PROJECT_ROOT
    profile_path = root / "personal_profile.yaml"
    job_path = root / "job_profiles" / f"{job_profile_id}.yaml"
    if not profile_path.is_file() or not job_path.is_file():
        return {}, {}
    try:
        return load_generation_context(profile_path, job_path)
    except (OSError, ValueError):
        return {}, {}


def _domain_evidence_cards(options: dict[str, Any]) -> tuple[Any, ...]:
    from tools.domain.models import EvidenceCard

    requested_ids = options.get("evidence_ids")
    allowed_ids = {
        str(item).strip()
        for item in requested_ids
        if str(item).strip()
    } if isinstance(requested_ids, list) else set()
    cards: list[Any] = []
    evidence_dir = _evidence_card_dir()
    if not evidence_dir.exists():
        raise ValueError("missing_eligible_evidence_cards")
    for path in sorted(evidence_dir.glob("*.yaml")):
        if allowed_ids and path.stem not in allowed_ids:
            continue
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not _is_saved_eligible_evidence(doc):
            continue
        cards.append(
            EvidenceCard(
                id=doc["scalars"].get("id", path.stem),
                title=doc["scalars"].get("title", path.stem),
                raw_source=doc["scalars"].get("raw_source", ""),
                results=tuple(doc["lists"].get("results", [])),
                artifacts=tuple(doc["lists"].get("artifacts", [])),
                tags=tuple(doc["lists"].get("tags", [])),
                stack=tuple(doc["lists"].get("stack", [])),
                period=doc["scalars"].get("time_range", ""),
                context=doc["scalars"].get("context", ""),
            )
        )
    if not cards:
        raise ValueError("missing_eligible_evidence_cards")
    return tuple(cards)


def _job_lead_candidates(options: dict[str, Any]) -> tuple[Any, ...]:
    from tools.domain.value_objects import Candidate
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile

    selected_ids_raw = options.get("candidate_ids")
    selected_ids = [
        str(item).strip()
        for item in selected_ids_raw
        if str(item).strip()
    ] if isinstance(selected_ids_raw, list) else []
    excluded_ids_raw = options.get("excluded_candidate_ids")
    excluded_ids = {
        str(item).strip()
        for item in excluded_ids_raw
        if str(item).strip()
    } if isinstance(excluded_ids_raw, list) else set()
    pinned_ids_raw = options.get("pinned_candidate_ids")
    pinned_ids = [
        str(item).strip()
        for item in pinned_ids_raw
        if str(item).strip()
    ] if isinstance(pinned_ids_raw, list) else []

    lead_dir = _facade()._PROJECT_ROOT / "job_leads"
    lead_map: dict[str, Any] = {}
    if lead_dir.exists():
        for path in sorted(lead_dir.glob("*.yaml")):
            try:
                doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            lead_id = doc["scalars"].get("id", path.stem)
            url = doc["scalars"].get("url", doc["scalars"].get("job_url", ""))
            if not url:
                continue
            source_fields = doc["scalars"]
            if source_fields.get("source") == "liepin_official":
                if not reviewed_official_profile(source_fields, _facade()._PROJECT_ROOT / "job_profiles"):
                    continue
            profile_id = source_fields.get("job_profile_id", "")
            if profile_id and options.get("job_profile_id") and profile_id != options["job_profile_id"]:
                continue
            lead_map[lead_id] = Candidate(
                candidate_id=lead_id,
                direction=doc["scalars"].get("position", doc["scalars"].get("title", "")),
                company=doc["scalars"].get("company", ""),
                job_url=url,
                confidence=float(doc["scalars"].get("confidence", "0.75") or 0.75),
                source=doc["scalars"].get("source", "job_leads"),
                merged_sources=("job_leads",),
                legal_entity=doc["scalars"].get("legal_entity", ""),
                platform=source_fields.get("platform", ""),
                platform_job_id=source_fields.get("platform_job_id", ""),
                platform_job_type=source_fields.get("platform_job_type", ""),
                job_profile_id=profile_id,
                jd_status=source_fields.get("jd_status", ""),
                source_jd_sha256=source_fields.get("source_jd_sha256", ""),
            )

    ordered_ids = [lead_id for lead_id in pinned_ids + selected_ids if lead_id in lead_map]
    if not ordered_ids and not selected_ids:
        ordered_ids = sorted(lead_map)
    candidates = [
        lead_map[lead_id]
        for lead_id in dict.fromkeys(ordered_ids)
        if lead_id not in excluded_ids
    ]
    max_candidates = _coerce_positive_int(options.get("max_candidates"), 5)
    candidates = candidates[:max_candidates]
    if not candidates:
        raise ValueError("missing_candidate_job_leads")
    return tuple(candidates)


def handle_prepare_liepin_default(params: dict[str, Any]) -> dict[str, Any]:
    """从已审核岗位准备默认简历审批；此入口只有读取操作，绝不发送。"""
    from tools.sidecar.handlers import jobs
    from tools.channels.base import DeliveryRequest
    from tools.infra.liepin_job_detail import fetch_liepin_job_detail, LiepinJobDetailError
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile
    from tools.infra.persistence.review_queue import atomic_write_json, locked_review_queue
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    from tools.orchestration.approved_delivery import _job_key
    from tools.policy.exclusions import load_exclusion_policy, match_exclusion, resolve_policy_path

    base = {'meta': {'correlation_id': params['meta']['correlation_id']}, 'status': 'blocked'}
    lead_id = params.get('job_lead_id')
    if (set(params) - {'meta', 'job_lead_id'} or not isinstance(lead_id, str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', lead_id)):
        return {**base, 'code': 'INVALID_INPUT'}
    try:
        binding = jobs._bound_lead(lead_id)
        if not binding:
            return {**base, 'code': 'JOB_REVIEW_REQUIRED'}
        lead = binding[1]
        if (lead.get('source') != 'liepin_official' or lead.get('platform') != 'liepin'
                or not reviewed_official_profile(lead, jobs._JOB_PROFILE_DIR)):
            return {**base, 'code': 'JOB_REVIEW_REQUIRED'}
        if match_exclusion(lead.get('company', ''), lead.get('legal_entity', ''),
                           load_exclusion_policy(resolve_policy_path(_facade()._PROJECT_ROOT))):
            return {**base, 'code': 'EXCLUDED_TARGET'}
        request = DeliveryRequest('', lead_id, 'liepin', '', lead['url'], False, lead)
        store = DeliveryAttemptStore(_facade()._PROJECT_ROOT / 'outputs/submissions/delivery_attempts.sqlite3')
        if store.has_attempt(_job_key(request)):
            return {**base, 'code': 'ALREADY_ATTEMPTED'}
        # platform_default 的授权是 attempt 级（delivery_attempt_id + 用户确认），
        # 与 generated_pdf 的批次额度无关：遗留的 generated_pdf 批次不该挡住
        # 平台默认简历投递。只有批次本身就是 platform_default 时才校验额度。
        batch = store.active_batch()
        if batch and batch.get('allowed_delivery_kind') not in (None, 'platform_default'):
            # 其他类型（如 generated_pdf）的批次不适用于平台默认简历投递。
            # 已用尽且无未决时可以关闭它；否则如实报授权不匹配。
            if not store.close_spent_batch(batch['batch_id'], delivery_kind='platform_default'):
                return {**base, 'code': 'BATCH_ROUTE_NOT_AUTHORIZED'}
            batch = store.active_batch()
        if batch and batch.get('allowed_delivery_kind') in (None, 'platform_default'):
            if batch['remaining'] == 0:
                return {**base, 'code': 'BATCH_LIMIT_REACHED'}
            if batch['unresolved']:
                return {**base, 'code': 'BATCH_UNRESOLVED'}
        from tools.infra.resume_content import current_career,content_body_issues
        career=current_career(_facade()._PROJECT_ROOT)
        detail = fetch_liepin_job_detail(lead['url'], lead['platform_job_id'])
        if detail['source_jd_sha256'] != lead['source_jd_sha256']:
            return {**base, 'code': 'JOB_REVIEW_REQUIRED'}
        resume = jobs.liepin_readonly.read_resume()
        if resume['status'] != 'pass':
            return {**base, 'code': 'RESUME_UNAVAILABLE'}
        content = resume.get('resume_text', '')
        if not isinstance(content, str) or not content.strip():
            return {**base, 'code': 'RESUME_UNAVAILABLE'}
        # 平台默认简历由用户自行维护：只校验核心事实（公司/职位/起止时间/
        # 学校/学历），豁免平台脱敏字段与人工省略；系统生成简历仍走严格策略。
        if content_body_issues(career,content,policy='user_maintained'):
            return {**base,'code':'RESUME_CONTENT_INCOMPLETE'}
        digest = hashlib.sha256(content.encode()).hexdigest()
        candidate = {key: lead.get(key, '') for key in (
            'company', 'position', 'platform', 'platform_job_id', 'platform_job_type',
            'job_profile_id', 'jd_status', 'source_jd_sha256', 'source', 'legal_entity')}
        candidate.update(job_lead_id=lead_id, job_url=lead['url'], delivery_kind='platform_default',
                         career_revision=career['revision'],content_schema_version=1,
                         platform_resume_sha256=digest, resume_version='platform-default-' + digest[:12],
                         matching_score=None, evaluation_score=None, round_index=0, status='pending',
                         created_at=_utcnow_iso())
        snapshots = ReviewSnapshotStore(_facade()._AGENT_RUN_DIR)
        # 多窗口同时准备时只创建一个任务；审批与真实发送仍使用各自原有锁和占位。
        with locked_review_queue(_review_queue_dir() / '.prepare-liepin'):
            if store.has_attempt(_job_key(request)):
                return {**base, 'code': 'ALREADY_ATTEMPTED'}
            for path in _review_queue_dir().glob('*.json'):
                with locked_review_queue(path):
                    queue = _load_queue(path)
                    for existing in queue.get('candidates', []):
                        if (existing.get('status') != 'pending' or existing.get('delivery')
                                or any(existing.get(key) != candidate.get(key) for key in candidate
                                       if key not in {'created_at', 'matching_score', 'evaluation_score', 'round_index'})):
                            continue
                        try:
                            sealed = snapshots.load(path.stem, existing)
                            run = _load_agent_run(path.stem)['run']
                        except (ValueError, KeyError, OSError):
                            continue
                        if not sealed['dry_run'] and run.get('status') == 'REVIEW_PENDING':
                            return {**base, 'status': 'ready', 'code': 'OK', 'run_id': path.stem,
                                    'job_profile_id': lead['job_profile_id'], 'reused': True}
            run_id = _facade()._build_agent_run_id()
            candidate['snapshot'] = snapshots.create(run_id, candidate, content, dry_run=False)
            queue = {'run_id': run_id, 'candidates': [candidate], 'created_at': _utcnow_iso()}
            payload = {'run': {'run_id': run_id, 'status': 'REVIEW_PENDING', 'round': 0,
                       'started_at': _utcnow_iso(), 'job_profile_id': lead['job_profile_id'],
                       'options': {'delivery_kind': 'platform_default'}, 'review_queue': queue,
                       'deliveries_completed': 0, 'app_verified_deliveries': 0, 'externally_confirmed_deliveries': 0},
                       'events': [], 'gate_checks': [], 'next_event_cursor': None}
            atomic_write_json(_get_agent_run_file(run_id), payload)
            _save_queue(_get_queue_file(run_id), queue)
        return {**base, 'status': 'ready', 'code': 'OK', 'run_id': run_id,
                'job_profile_id': lead['job_profile_id'], 'reused': False}
    except LiepinJobDetailError:
        return {**base, 'code': 'JOB_DETAIL_UNAVAILABLE'}
    except ValueError as error:
        return {**base,'code':'CAREER_PROFILE_UNCONFIRMED' if str(error)=='career_profile_unconfirmed' else 'PREPARATION_UNAVAILABLE'}
    except (OSError, KeyError):
        return {**base, 'code': 'PREPARATION_UNAVAILABLE'}


def handle_recheck_receipt(params: dict[str, Any]) -> dict[str, Any]:
    """App 重新核验已有 API 回执；没有发送或网络操作。"""
    from tools.infra.liepin_default_delivery import recheck_api_receipt
    from tools.infra.persistence.review_queue import locked_review_queue, atomic_write_json
    base = {'meta': {'correlation_id': params['meta']['correlation_id']}, 'status':'blocked'}
    run_id, lead_id = params.get('run_id'), params.get('job_lead_id')
    if (set(params) - {'meta','run_id','job_lead_id'} or
            not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', v) for v in (run_id, lead_id))):
        return {**base, 'code':'INVALID_INPUT'}
    with locked_review_queue(_get_queue_file(run_id)):
        queue = _load_queue(_get_queue_file(run_id))
        candidate = next((c for c in queue['candidates'] if c['job_lead_id'] == lead_id), None)
        if not candidate or queue.get('run_id') != run_id:
            return {**base, 'code':'RECEIPT_EVIDENCE_UNAVAILABLE'}
        if (candidate.get('delivery', {}).get('status') == 'unknown'
                or candidate.get('delivery', {}).get('receipt_source') == 'website_history'):
            try:
                result = recheck_api_receipt(_facade()._PROJECT_ROOT, run_id, candidate)
            except (OSError, ValueError, KeyError, TypeError):
                return {**base, 'code':'RECEIPT_EVIDENCE_UNAVAILABLE'}
            changed = result != candidate['delivery']
            candidate['delivery'] = result
            _save_queue(_get_queue_file(run_id), queue)
            if changed:
                payload = _load_agent_run(run_id)
                payload.setdefault('events', []).append({'event_type':'DELIVER', 'round_index':candidate.get('round_index', 0),
                    'timestamp':_utcnow_iso(), 'payload':{**result, 'source':'api_receipt_recheck'}})
                atomic_write_json(_get_agent_run_file(run_id), payload)
        results = [c['delivery'] for c in queue['candidates'] if 'delivery' in c]
        _sync_review_run(run_id, queue, results)
    return {**base, 'status':'ready', 'code':'RECEIPT_RECHECKED',
            'delivery_results':[_delivery_confirmation(r) for r in results]}
