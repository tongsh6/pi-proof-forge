"""Agent Run：10 状态机执行、本地 dry-run 与引导批次。"""

from __future__ import annotations

import json
import os
import re
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from ._shared.agent_runtime import _coerce_positive_int, _utcnow_iso
from .agent_delivery import (
    _domain_evidence_cards,
    _job_lead_candidates,
    _read_domain_job_profile,
)


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

def _ensure_agent_run_dir() -> None:
    _facade()._AGENT_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _build_agent_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"ar_{timestamp}"


def _get_agent_run_file(run_id: str) -> Path:
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', run_id):
        raise ValueError('invalid_review_run_id')
    _ensure_agent_run_dir()
    return _facade()._AGENT_RUN_DIR / f"{run_id}.json"


def _load_agent_run(run_id: str) -> dict[str, Any]:
    run_file = _get_agent_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: agent run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_agent_run(run_file: Path, payload: dict[str, Any]) -> None:
    run_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _event_to_payload(event: Any) -> dict[str, Any]:
    return {
        "run_id": getattr(event, "run_id", ""),
        "event_type": getattr(event, "event_type", ""),
        "round_index": getattr(event, "round_index", 0),
        "payload": getattr(event, "payload", {}),
        "timestamp": getattr(event, "timestamp", ""),
    }


def _execute_local_dry_run(run_id: str, options: dict[str, Any]) -> dict[str, Any]:
    from tools.config.fragments import PolicyConfig
    from tools.infra.persistence.file_run_store import FileRunStore
    from tools.orchestration.agent_loop import AgentLoop

    max_rounds = _coerce_positive_int(options.get("max_rounds"), 1)
    store = FileRunStore(base_dir=str(_facade()._AGENT_RUN_DIR))
    policy = PolicyConfig(
        n_pass_required=1,
        matching_threshold=0.6,
        evaluation_threshold=0.6,
        max_rounds=max_rounds,
        gate_mode="simulate",
        delivery_mode="auto",
        batch_review=False,
        excluded_companies=(),
        excluded_legal_entities=(),
        max_deliveries=0,
    )
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        result = AgentLoop(
            policy=policy,
            run_id=run_id,
            dry_run=True,
            run_store=store,
        ).run()
    events = [_event_to_payload(event) for event in store.load_events(run_id)]

    return {
        "status": result.status,
        "round": result.rounds_completed,
        "events": events,
        "stdout": stdout_buffer.getvalue()[-4000:],
        "stderr": stderr_buffer.getvalue()[-4000:],
    }


def _execute_guided_batch_run(
    run_id: str,
    job_profile_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    from tools.config.composer import Composer
    from tools.config.fragments import PolicyConfig
    from tools.infra.persistence.file_run_store import FileRunStore

    max_rounds = _coerce_positive_int(options.get("max_rounds"), 2)
    from tools.policy.exclusions import load_exclusion_policy, resolve_policy_path
    exclusions = load_exclusion_policy(resolve_policy_path(_facade()._PROJECT_ROOT))
    policy = PolicyConfig(
        n_pass_required=1,
        matching_threshold=float(options.get("matching_threshold") or 0.3),
        evaluation_threshold=float(options.get("evaluation_threshold") or 0.3),
        max_rounds=max_rounds,
        gate_mode="strict",
        delivery_mode="manual",
        batch_review=True,
        excluded_companies=exclusions.company_rules,
        excluded_legal_entities=exclusions.legal_entities,
        max_deliveries=0,
    )
    job_profile = _read_domain_job_profile(job_profile_id)
    evidence_cards = _domain_evidence_cards(options)
    candidates = _job_lead_candidates({**options, "job_profile_id": job_profile_id})
    store = FileRunStore(base_dir=str(_facade()._AGENT_RUN_DIR))
    composer = Composer(policy=policy)
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    cwd = Path.cwd()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            os.chdir(_facade()._PROJECT_ROOT)
            result = composer.build_agent_loop(
                run_id=run_id,
                dry_run=True,
                run_store=store,
                evidence_cards=evidence_cards,
                job_profile=job_profile,
                candidates=candidates,
            ).run()
        finally:
            os.chdir(cwd)

    events = [_event_to_payload(event) for event in store.load_events(run_id)]
    gate_checks = [
        event
        for event in events
        if event.get("event_type") == "GATE"
    ]
    queue_path = _facade()._PROJECT_ROOT / "outputs" / "review_queue" / f"{run_id}.json"
    review_queue: dict[str, Any] = {}
    if queue_path.exists():
        review_queue = json.loads(queue_path.read_text(encoding="utf-8"))
    delivery_events = [
        event for event in events if event.get("event_type") == "DELIVER"
    ]
    policy_limits = {
        "max_candidates": _coerce_positive_int(options.get("max_candidates"), 5),
        "max_passed_candidates": _coerce_positive_int(
            options.get("max_passed_candidates"), 3
        ),
        "max_generated_resumes": _coerce_positive_int(
            options.get("max_generated_resumes"), 3
        ),
        "submit_enabled": False,
    }
    preflight_confirmation = {
        "confirmed_by_user": bool(options.get("preflight_confirmed")),
        "confirmed_no_real_submit": bool(options.get("confirmed_no_real_submit")),
        "confirmed_at": _utcnow_iso() if options.get("preflight_confirmed") else "",
        "confirmed_policy_limits": policy_limits,
    }
    selected_candidate_ids = [candidate.candidate_id for candidate in candidates]
    return {
        "status": result.status,
        "round": result.rounds_completed,
        "events": events,
        "gate_checks": gate_checks,
        "review_queue": {
            "path": str(queue_path.relative_to(_facade()._PROJECT_ROOT)),
            "candidate_count": len(review_queue.get("candidates", [])),
            "pending_count": len(
                [
                    candidate
                    for candidate in review_queue.get("candidates", [])
                    if candidate.get("status") == "pending"
                ]
            ),
        },
        "selected_candidate_ids": selected_candidate_ids,
        "policy_limits": policy_limits,
        "preflight_confirmation": preflight_confirmation,
        "delivery_plan": {
            "submit_enabled": False,
            "submit_status": "blocked_pending_manual_review",
            "external_submission_attempted": False,
            "delivery_events": len(delivery_events),
        },
        "run_log": str(
            Path("outputs") / "agent_runs" / run_id / "run_log.json"
        ),
        "stdout": stdout_buffer.getvalue()[-4000:],
        "stderr": stderr_buffer.getvalue()[-4000:],
    }


def handle_agent_start(params: dict[str, Any]) -> dict[str, Any]:
    """Create a desktop-visible Agent Run control record."""
    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = params.get("job_profile_id")
    options = params.get("options", {})

    if not isinstance(job_profile_id, str) or not job_profile_id:
        raise ValueError("job_profile_id is required")
    if not isinstance(options, dict):
        raise ValueError("options must be an object")

    llm_config_summary, _llm_env = _facade()._persisted_llm_runtime_context()
    if options.get("submit_enabled") is True:
        raise ValueError("submit_enable_blocked_for_case")
    if options.get("execute_guided_batch") is True:
        if not llm_config_summary.get("provider") or not llm_config_summary.get("model"):
            raise ValueError("missing_provider_config")
        if not options.get("preflight_confirmed"):
            raise ValueError("preflight_confirmation_required")
        if not options.get("confirmed_no_real_submit"):
            raise ValueError("no_real_submit_confirmation_required")
    run_id = _facade()._build_agent_run_id()
    started_at = _utcnow_iso()
    run_payload = {
        "run": {
            "run_id": run_id,
            "status": "queued",
            "round": 0,
            "started_at": started_at,
            "job_profile_id": job_profile_id,
            "options": options,
            "llm_config_summary": llm_config_summary,
        },
        "gate_checks": [],
        "events": [],
        "next_event_cursor": None,
    }

    if options.get("execute_guided_batch") is True:
        execution = _execute_guided_batch_run(run_id, job_profile_id, options)
        run_payload["run"]["status"] = execution["status"]
        run_payload["run"]["round"] = execution["round"]
        run_payload["run"]["completed_at"] = _utcnow_iso()
        run_payload["run"]["guided_batch"] = True
        run_payload["run"]["selected_candidate_ids"] = execution[
            "selected_candidate_ids"
        ]
        run_payload["run"]["policy_limits"] = execution["policy_limits"]
        run_payload["run"]["preflight_confirmation"] = execution[
            "preflight_confirmation"
        ]
        run_payload["run"]["delivery_plan"] = execution["delivery_plan"]
        run_payload["run"]["review_queue"] = execution["review_queue"]
        run_payload["run"]["run_log"] = execution["run_log"]
        run_payload["events"] = execution["events"]
        run_payload["gate_checks"] = execution["gate_checks"]
        run_payload["stdout"] = execution.get("stdout", "")
        run_payload["stderr"] = execution.get("stderr", "")
    elif options.get("execute_dry_run") is True:
        execution = _execute_local_dry_run(run_id, options)
        run_payload["run"]["status"] = execution["status"]
        run_payload["run"]["round"] = execution["round"]
        run_payload["run"]["completed_at"] = _utcnow_iso()
        run_payload["events"] = execution["events"]
        run_payload["stdout"] = execution.get("stdout", "")
        run_payload["stderr"] = execution.get("stderr", "")

    _save_agent_run(_get_agent_run_file(run_id), run_payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "status": run_payload["run"]["status"],
        "llm_config_summary": llm_config_summary,
        "guided_batch": bool(run_payload["run"].get("guided_batch")),
        "review_queue": run_payload["run"].get("review_queue"),
        "delivery_plan": run_payload["run"].get("delivery_plan"),
    }


def handle_agent_get(params: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted Agent Run control record."""
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")

    payload = _load_agent_run(run_id)
    events = list(payload.get("events", []))
    event_cursor = _coerce_positive_int(params.get("event_cursor"), 0)
    event_limit = _coerce_positive_int(params.get("event_limit"), 50)
    visible_events = events[event_cursor : event_cursor + event_limit]
    next_cursor_index = event_cursor + len(visible_events)
    next_event_cursor = (
        str(next_cursor_index) if next_cursor_index < len(events) else None
    )
    queue = _load_queue(_get_queue_file(run_id))
    # 每日项在原 daily 历史展示所属批次；不能借用当前手动验证批次的成功计数。
    delivery_batch = None if queue.get('daily_cycle') else DeliveryAttemptStore(
        _facade()._AGENT_RUN_DIR.parent / 'submissions/delivery_attempts.sqlite3').active_batch()

    return {
        "meta": {"correlation_id": correlation_id},
        "run": _delivery_summary(payload.get("run", {})),
        "delivery_batch": delivery_batch,
        "gate_checks": payload.get("gate_checks", []),
        "events": visible_events,
        "next_event_cursor": next_event_cursor,
    }


def handle_agent_stop(params: dict[str, Any]) -> dict[str, Any]:
    """Mark a desktop-visible Agent Run as stopped."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")

    run_file = _get_agent_run_file(run_id)
    payload = _load_agent_run(run_id)
    run_payload = payload.setdefault("run", {})
    run_payload["status"] = "stopped"
    run_payload["stopped_at"] = _utcnow_iso()
    _save_agent_run(run_file, payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": True,
    }
