"""Agent run / REVIEW RPC handlers with real implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AGENT_RUN_DIR = Path("outputs") / "agent_runs"
_REVIEW_QUEUE_DIR = Path("outputs") / "review_queue"


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _ensure_queue_dir() -> None:
    _REVIEW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_agent_run_dir() -> None:
    _AGENT_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _build_agent_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"ar_{timestamp}"


def _get_agent_run_file(run_id: str) -> Path:
    _ensure_agent_run_dir()
    return _AGENT_RUN_DIR / f"{run_id}.json"


def _load_agent_run(run_id: str) -> dict[str, Any]:
    run_file = _get_agent_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: agent run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_agent_run(run_file: Path, payload: dict[str, Any]) -> None:
    run_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _coerce_positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default


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
    store = FileRunStore(base_dir=str(_AGENT_RUN_DIR))
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
    }


def _get_queue_file(run_id: str | None = None) -> Path:
    _ensure_queue_dir()
    if run_id is None:
        # Use the most recent queue file or create a default
        files = sorted(_REVIEW_QUEUE_DIR.glob("*.json"))
        if files:
            return files[-1]
        return _REVIEW_QUEUE_DIR / "default.json"
    return _REVIEW_QUEUE_DIR / f"{run_id}.json"


def _load_queue(queue_file: Path) -> dict[str, Any]:
    if not queue_file.exists():
        return {
            "run_id": queue_file.stem,
            "candidates": [],
            "created_at": _utcnow_iso(),
        }
    return json.loads(queue_file.read_text(encoding="utf-8"))


def _save_queue(queue_file: Path, queue: dict[str, Any]) -> None:
    queue_file.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def handle_agent_start(params: dict[str, Any]) -> dict[str, Any]:
    """Create a desktop-visible Agent Run control record."""
    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = params.get("job_profile_id")
    options = params.get("options", {})

    if not isinstance(job_profile_id, str) or not job_profile_id:
        raise ValueError("job_profile_id is required")
    if not isinstance(options, dict):
        raise ValueError("options must be an object")

    run_id = _build_agent_run_id()
    started_at = _utcnow_iso()
    run_payload = {
        "run": {
            "run_id": run_id,
            "status": "queued",
            "round": 0,
            "started_at": started_at,
            "job_profile_id": job_profile_id,
            "options": options,
        },
        "gate_checks": [],
        "events": [],
        "next_event_cursor": None,
    }

    if options.get("execute_dry_run") is True:
        execution = _execute_local_dry_run(run_id, options)
        run_payload["run"]["status"] = execution["status"]
        run_payload["run"]["round"] = execution["round"]
        run_payload["run"]["completed_at"] = _utcnow_iso()
        run_payload["events"] = execution["events"]

    _save_agent_run(_get_agent_run_file(run_id), run_payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "status": run_payload["run"]["status"],
    }


def handle_agent_get(params: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted Agent Run control record."""
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

    return {
        "meta": {"correlation_id": correlation_id},
        "run": payload.get("run", {}),
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


def handle_get_pending_review(params: dict[str, Any]) -> dict[str, Any]:
    """Return pending REVIEW candidates for the active run."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    queue_file = _get_queue_file(run_id)
    queue = _load_queue(queue_file)

    # Filter only pending candidates
    pending = [c for c in queue.get("candidates", []) if c.get("status") == "pending"]

    return {
        "meta": {"correlation_id": correlation_id},
        "candidates": pending,
    }


def handle_submit_review(params: dict[str, Any]) -> dict[str, Any]:
    """Accept review decisions and update candidate statuses."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")
    decisions = params.get("decisions", [])

    if not isinstance(decisions, list):
        raise ValueError("decisions must be a list")

    queue_file = _get_queue_file(run_id)
    queue = _load_queue(queue_file)
    candidates = queue.get("candidates", [])

    accepted_count = 0

    for decision in decisions:
        job_lead_id = decision.get("job_lead_id")
        action = decision.get("action")

        # Find and update the candidate
        for candidate in candidates:
            if candidate.get("job_lead_id") == job_lead_id:
                if action == "approve":
                    candidate["status"] = "approved"
                    accepted_count += 1
                elif action == "reject":
                    candidate["status"] = "rejected"
                elif action in ("skip", "skip_all"):
                    candidate["status"] = "skipped"

                candidate["decided_by"] = decision.get("decided_by", "user")
                candidate["decided_at"] = decision.get("decided_at", _utcnow_iso())
                if "note" in decision:
                    candidate["note"] = decision["note"]
                break

    _save_queue(queue_file, queue)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": accepted_count,
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
    _save_queue(queue_file, queue)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "created": len(candidates),
    }
