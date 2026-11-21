"""Agent Review：审批队列读写、待审查询、提交审批与投递同步。

从原 handlers/agent.py 拆出；对 agent_run 的运行记录读取使用延迟导入薄包装。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ._shared.agent_runtime import (
    _find_project_root,
    _utcnow_iso,
)


def _facade():
    """门面模块：路径常量、Popen 与 Quick Run 运行态由 handlers/agent.py 持有。

    这些符号会被测试 patch；子模块统一在运行时从门面读取，避免拆分后 patch
    失效。门面在 handlers/agent.py 中定义它们并 re-export 本模块函数。
    """
    from tools.sidecar.handlers import agent

    return agent





def _load_agent_run(run_id: str) -> dict[str, Any]:
    from tools.sidecar.handlers.agent_run import _load_agent_run as impl

    return impl(run_id)


def _agent_run_dir() -> Path:
    return _facade()._AGENT_RUN_DIR


def _ensure_queue_dir() -> None:
    _facade()._REVIEW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

def _get_queue_file(run_id: str | None = None) -> Path:
    _ensure_queue_dir()
    if run_id is None:
        # Use the most recent queue file or create a default
        files = sorted(_facade()._REVIEW_QUEUE_DIR.glob("*.json"), key=lambda path: (path.stat().st_mtime_ns, path.name))
        if files:
            return files[-1]
        return _facade()._REVIEW_QUEUE_DIR / "default.json"
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', run_id):
        raise ValueError('invalid_review_run_id')
    return _facade()._REVIEW_QUEUE_DIR / f"{run_id}.json"

def _load_queue(queue_file: Path) -> dict[str, Any]:
    if not queue_file.exists():
        return {
            "run_id": queue_file.stem,
            "candidates": [],
            "created_at": _utcnow_iso(),
        }
    return json.loads(queue_file.read_text(encoding="utf-8"))

def _save_queue(queue_file: Path, queue: dict[str, Any]) -> None:
    from tools.infra.persistence.review_queue import atomic_write_json
    atomic_write_json(queue_file, queue)

def _delivery_confirmation(result: dict) -> dict:
    """保留实际投递事实，单独标记其确认来源；历史记录不自动升级。"""
    result = {**result, 'app_verified': False}
    if result.get('success'):
        if result.get('receipt_source') == 'website_history':
            result.update(status='externally_confirmed', code='external_observation_confirmed')
        elif result.get('receipt_source') in {'app_api', 'app_browser'} and result.get('submission_id'):
            result['app_verified'] = True
        else:
            result.update(status='unknown', code='receipt_source_unverified')
    return result

def _delivery_summary(run: dict) -> dict:
    run = dict(run)
    if 'delivery_results' not in run:
        return run
    results = [_delivery_confirmation(r) for r in run['delivery_results']]
    run.update(delivery_results=results, deliveries_completed=sum(bool(r.get('success')) for r in results),
               app_verified_deliveries=sum(r['app_verified'] for r in results),
               externally_confirmed_deliveries=sum(r.get('status') == 'externally_confirmed' for r in results))
    if run.get('status') not in {'REVIEW_PENDING', 'stopped'}:
        if any(r.get('status') in {'blocked', 'unknown'} for r in results):
            run['status'] = 'DELIVERY_BLOCKED'
        elif run['externally_confirmed_deliveries']:
            run['status'] = 'EXTERNAL_CONFIRMATION_ONLY'
    return run

def _sync_review_run(run_id: str, queue: dict, results: list[dict]) -> None:
    """审批队列为恢复来源，同步 App 已有运行记录与事件流。"""
    from tools.infra.persistence.review_queue import atomic_write_json
    run_file = _agent_run_dir() / f'{run_id}.json'
    if not run_file.exists():
        return
    payload = _load_agent_run(run_id)
    run = payload.setdefault('run', {})
    run['review_queue'] = queue
    run['delivery_results'] = results
    run['deliveries_completed'] = sum(bool(r['success']) for r in results)
    if any(c.get('status') == 'pending' for c in queue['candidates']):
        run['status'] = 'REVIEW_PENDING'
    elif any(r['status'] in {'blocked', 'unknown'} for r in results):
        run['status'] = 'DELIVERY_BLOCKED'
    elif results and all(r['status'] == 'checked' for r in results):
        run['status'] = 'REVIEWED_CHECK_ONLY'
    else:
        run['status'] = 'DONE'
    run.update(_delivery_summary(run))
    events = payload.setdefault('events', [])
    for result in results:
        event_key = 'review-delivery:' + result['job_lead_id']
        if not any(e.get('payload', {}).get('event_key') == event_key for e in events):
            round_index = next((c.get('round_index', 0) for c in queue['candidates'] if c['job_lead_id'] == result['job_lead_id']), 0)
            events.append({'event_type': 'DELIVER', 'round_index': round_index, 'timestamp': _utcnow_iso(),
                           'payload': {**result, 'dry_run': result['status'] == 'checked', 'event_key': event_key}})
    atomic_write_json(run_file, payload)

def _snapshot_candidate(run_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore

    projected = dict(candidate)
    try:
        snapshot = ReviewSnapshotStore(_agent_run_dir()).load(run_id, candidate)
        projected.update(snapshot_status='ready', resume_preview=snapshot['resume_markdown'])
        if snapshot['quality_snapshot'] is not None:
            projected['quality_snapshot'] = snapshot['quality_snapshot']
        else:
            projected.pop('quality_snapshot', None)
    except ValueError:
        projected.update(snapshot_status='invalid', resume_preview='')
        projected.pop('quality_snapshot', None)
    return projected


def handle_get_pending_review(params: dict[str, Any]) -> dict[str, Any]:
    """Return pending REVIEW candidates for the active run."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    queue_file = _get_queue_file(run_id)
    queue = _load_queue(queue_file)

    # Filter only pending candidates
    pending = [_snapshot_candidate(queue_file.stem, c) for c in queue.get("candidates", [])
               if c.get("status") == "pending" or (c.get('status') == 'approved' and 'delivery' not in c)]

    # 一次准备多个岗位时会有多个队列；只返回最新一个会让更早的待审任务在界面上
    # 消失（用户以为没准备成功）。这里额外聚合全部待审队列，保持既有字段不变。
    all_pending: list[dict[str, Any]] = []
    queue_dir = _facade()._REVIEW_QUEUE_DIR
    for path in sorted(queue_dir.glob('*.json')):
        if path == queue_file:
            continue
        try:
            other = _load_queue(path)
        except (ValueError, OSError):
            continue
        for candidate in other.get('candidates', []):
            # 只列真正待审的：approved 但无 delivery 的是历史遗留决定，
            # 混进来会让待审列表变噪音（实测聚合出 21 条）。
            if candidate.get('status') == 'pending' and 'delivery' not in candidate:
                all_pending.append({**_snapshot_candidate(path.stem, candidate), 'run_id': path.stem})
    for candidate in pending:
        all_pending.append({**candidate, 'run_id': queue_file.stem})
    # 最新的排前面：run_id 以时间戳开头，字典序即时间序。
    all_pending.sort(key=lambda item: str(item.get('run_id') or ''), reverse=True)
    return {
        "meta": {"correlation_id": correlation_id},
        "candidates": pending,
        "run_id": queue_file.stem,
        "native_pdf_quick_run_id": queue.get("quick_run_id"),
        "delivery_results": [_delivery_confirmation(c['delivery']) for c in queue.get('candidates', []) if 'delivery' in c],
        "all_pending": all_pending,
    }

def handle_submit_review(params: dict[str, Any]) -> dict[str, Any]:
    """持久化审批决定，从对应快照恢复执行，不重新生成简历。"""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")
    decisions = params.get("decisions", [])

    if not isinstance(decisions, list) or not decisions or not isinstance(run_id, str) or not run_id:
        raise ValueError("decisions must be a list")

    queue_file = _get_queue_file(run_id)
    from tools.infra.persistence.review_queue import locked_review_queue
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    from tools.orchestration.approved_delivery import resume_approved_candidate
    actions = {'approve': 'approved', 'reject': 'rejected', 'skip': 'skipped', 'skip_all': 'skipped'}
    with locked_review_queue(queue_file):
        queue = _load_queue(queue_file)
        if queue.get('run_id') != run_id:
            raise ValueError('review_run_mismatch')
        # 原生 PDF 的批准依据与平台副作用由原上传/每日流程管理，不能混用通用投递。
        if queue.get('quick_run_id'):
            raise ValueError('native_pdf_review_required')
        candidates = queue.get('candidates', [])
        unresolved = any(c.get('delivery', {}).get('status') == 'unknown' for c in candidates)
        if unresolved and any(isinstance(d, dict) and d.get('action') == 'approve' for d in decisions):
            raise ValueError('review_batch_has_unresolved_delivery')
        lookup = {c['job_lead_id']: c for c in candidates}
        if len(lookup) != len(candidates):
            raise ValueError('duplicate_review_candidate')
        selected = set()
        snapshots = ReviewSnapshotStore(_agent_run_dir())
        for decision in decisions:
            if not isinstance(decision, dict):
                raise ValueError('invalid_review_decision')
            lead_id, action = decision.get('job_lead_id'), decision.get('action')
            if (not isinstance(lead_id, str) or lead_id not in lookup or lead_id in selected
                    or not isinstance(action, str) or action not in actions):
                raise ValueError('invalid_review_decision')
            selected.add(lead_id)
            candidate = lookup[lead_id]
            if candidate.get('status') not in {'pending', actions[action]}:
                raise ValueError('review_decision_already_final')
            if action == 'approve':
                snapshots.load(run_id, candidate)
                run_file = _agent_run_dir() / f'{run_id}.json'
                if run_file.exists() and _load_agent_run(run_id).get('run', {}).get('status') == 'stopped':
                    raise ValueError('review_run_stopped')
        accepted_count = 0
        for decision in decisions:
            candidate = lookup[decision['job_lead_id']]
            if candidate['status'] != 'pending':
                continue
            candidate.update(status=actions[decision['action']],
                             decided_by=decision.get('decided_by', 'user'), decided_at=_utcnow_iso())
            if 'note' in decision:
                candidate['note'] = decision['note']
            accepted_count += int(decision['action'] == 'approve')
        # 批准先落盘；中断后同一批准可恢复，真实调用由持久化占位防重。
        _save_queue(queue_file, queue)
        for decision in decisions:
            candidate = lookup[decision['job_lead_id']]
            if candidate['status'] == 'approved' and 'delivery' not in candidate:
                try:
                    candidate['delivery'] = resume_approved_candidate(run_id, candidate, _agent_run_dir())
                except Exception:
                    candidate['delivery'] = {'job_lead_id': candidate['job_lead_id'], 'success': False,
                                             'submission_id': '', 'status': 'blocked', 'code': 'review_execution_failed'}
                _save_queue(queue_file, queue)
                if candidate['delivery']['status'] == 'unknown':
                    break
        results = [c['delivery'] for c in candidates if 'delivery' in c]
        _sync_review_run(run_id, queue, results)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": accepted_count,
        "delivery_results": [_delivery_confirmation(result) for result in results],
    }

def handle_create_review_candidates(params: dict[str, Any]) -> dict[str, Any]:
    """Internal API to create review candidates from a run (called by run_agent)."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id", "default")
    candidates_data = params.get("candidates", [])

    if not isinstance(candidates_data, list):
        raise ValueError("candidates must be a list")

    queue_file = _get_queue_file(run_id)

    candidates = []
    for data in candidates_data:
        candidate = {
            "job_lead_id": data.get("job_lead_id", ""),
            "company": data.get("company", ""),
            "position": data.get("position", ""),
            "matching_score": data.get("matching_score", 0),
            "evaluation_score": data.get("evaluation_score", 0),
            "round_index": data.get("round_index", 0),
            "resume_version": data.get("resume_version", ""),
            "status": "pending",
            "created_at": _utcnow_iso(),
        }
        if "job_url" in data:
            candidate["job_url"] = data["job_url"]
        candidates.append(candidate)

    queue = {
        "run_id": run_id,
        "candidates": candidates,
        "created_at": _utcnow_iso(),
    }
    from tools.infra.persistence.review_queue import locked_review_queue
    with locked_review_queue(queue_file):
        if queue_file.exists():
            raise ValueError('review_queue_already_exists')
        _save_queue(queue_file, queue)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "created": len(candidates),
    }
