"""Agent run / REVIEW RPC handlers with real implementation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _find_project_root(start: Path) -> Path:
    for parent in start.parents:
        if (parent / "tools" / "run_pipeline.py").exists():
            return parent
    return start.parents[3] if len(start.parents) > 3 else start.parent


_PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
_AGENT_RUN_DIR = _PROJECT_ROOT / "outputs" / "agent_runs"
_QUICK_RUN_DIR = _PROJECT_ROOT / "outputs" / "quick_runs"
_REVIEW_QUEUE_DIR = _PROJECT_ROOT / "outputs" / "review_queue"


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


def _ensure_quick_run_dir() -> None:
    _QUICK_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _build_agent_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"ar_{timestamp}"


def _build_quick_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"qr_{timestamp}"


def _validate_run_resource_id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    normalized = value.strip()
    if "/" in normalized or "\\" in normalized or normalized.startswith("."):
        raise ValueError(f"{name} is invalid")
    return normalized


def _get_agent_run_file(run_id: str) -> Path:
    _ensure_agent_run_dir()
    return _AGENT_RUN_DIR / f"{run_id}.json"


def _get_quick_run_file(run_id: str) -> Path:
    _ensure_quick_run_dir()
    return _QUICK_RUN_DIR / f"{run_id}.json"


def _load_agent_run(run_id: str) -> dict[str, Any]:
    run_file = _get_agent_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: agent run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_agent_run(run_file: Path, payload: dict[str, Any]) -> None:
    run_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_quick_run(run_id: str) -> dict[str, Any]:
    run_file = _get_quick_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: quick run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_quick_run(run_file: Path, payload: dict[str, Any]) -> None:
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


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return _PROJECT_ROOT / path


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


def _quick_run_paths(job_profile_id: str, options: dict[str, Any]) -> tuple[Path, Path]:
    raw_path = _resolve_project_path(
        str(options.get("raw_path") or "tools/sample_raw.txt")
    )
    job_profile_path = _resolve_project_path(
        str(options.get("job_profile_path") or f"job_profiles/{job_profile_id}.yaml")
    )
    if not raw_path.exists():
        raise ValueError(f"raw_path does not exist: {raw_path}")
    if not job_profile_path.exists():
        raise ValueError(f"job_profile_path does not exist: {job_profile_path}")
    return raw_path, job_profile_path


def _load_quick_run_summary(run_id: str) -> dict[str, Any]:
    summary_path = _PROJECT_ROOT / "outputs" / "agent_runs" / run_id / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_matching_scores(matching_path: Path) -> tuple[int | None, dict[str, dict[str, Any]]]:
    if not matching_path.exists():
        return None, {}
    text = matching_path.read_text(encoding="utf-8")
    total_match = re.search(r"(?m)^score_total:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text)
    score_total = int(float(total_match.group(1))) if total_match else None
    breakdown: dict[str, dict[str, Any]] = {}
    for key, score, reason in re.findall(
        r'(?m)^\s+([KDSQER]):\s*\{\s*score:\s*([0-9]+(?:\.[0-9]+)?),\s*reason:\s*"([^"]*)"',
        text,
    ):
        breakdown[key] = {
            "score": int(float(score)),
            "reason": reason,
        }
    return score_total, breakdown


def _quick_run_result_details(
    run_id: str,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    summary_payload = _load_quick_run_summary(run_id)
    artifacts = summary_payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    failed_step = summary_payload.get("failed_step", "")
    reason = summary_payload.get("reason", "")
    matching_artifact = artifacts.get("matching")
    score_total: int | None = None
    score_breakdown: dict[str, dict[str, Any]] = {}
    if isinstance(matching_artifact, str) and matching_artifact:
        score_total, score_breakdown = _parse_matching_scores(
            _resolve_project_path(matching_artifact)
        )
    return {
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "artifacts": artifacts,
        "failed_step": failed_step if isinstance(failed_step, str) else "",
        "reason": reason if isinstance(reason, str) else "",
        "score_total": score_total,
        "score_breakdown": score_breakdown,
    }


def handle_quick_start(params: dict[str, Any]) -> dict[str, Any]:
    """Run the single-pass pipeline from the desktop Quick Run page."""
    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = _validate_run_resource_id(
        "job_profile_id", params.get("job_profile_id")
    )
    evidence_id = params.get("evidence_id")
    if evidence_id is not None:
        _validate_run_resource_id("evidence_id", evidence_id)
    options = params.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("options must be an object")

    raw_path, job_profile_path = _quick_run_paths(job_profile_id, options)
    run_id = _build_quick_run_id()
    started_at = _utcnow_iso()
    pipeline_script = _PROJECT_ROOT / "tools" / "run_pipeline.py"
    command = [
        sys.executable,
        str(pipeline_script),
        "--raw",
        str(raw_path),
        "--job-profile",
        str(job_profile_path),
        "--run-id",
        run_id,
    ]
    timeout_seconds = _coerce_positive_int(options.get("timeout_seconds"), 120)
    if options.get("use_llm") is True:
        command.append("--use-llm")
    if options.get("require_llm") is True:
        command.append("--require-llm")

    status = "queued"
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    finished_at = ""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(_PROJECT_ROOT),
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        if completed.returncode == 0:
            status = "DONE"
        elif completed.returncode == 2:
            status = "SKIPPED"
        else:
            status = "FAILED"
        finished_at = _utcnow_iso()
    except subprocess.TimeoutExpired as exc:
        status = "TIMEOUT"
        exit_code = None
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        finished_at = _utcnow_iso()

    payload = {
        "run": {
            "run_id": run_id,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "job_profile_id": job_profile_id,
            "evidence_id": evidence_id or "",
            "raw_path": str(raw_path),
            "job_profile_path": str(job_profile_path),
            "command": command,
            "exit_code": exit_code,
            "options": options,
        },
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }
    _save_quick_run(_get_quick_run_file(run_id), payload)

    details = _quick_run_result_details(run_id, stdout, stderr)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "status": status,
        "exit_code": exit_code,
        "run_record": str(Path("outputs") / "agent_runs" / run_id / "run_log.json"),
        "summary": str(Path("outputs") / "agent_runs" / run_id / "summary.json"),
        **details,
    }


def handle_quick_cancel(params: dict[str, Any]) -> dict[str, Any]:
    """Best-effort cancellation marker for Quick Run records."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = _validate_run_resource_id("run_id", params.get("run_id"))
    run_file = _get_quick_run_file(run_id)
    payload = _load_quick_run(run_id)
    run_payload = payload.setdefault("run", {})
    if run_payload.get("status") not in {"DONE", "FAILED", "SKIPPED", "TIMEOUT"}:
        run_payload["status"] = "stopped"
    run_payload["cancel_requested_at"] = _utcnow_iso()
    _save_quick_run(run_file, payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": True,
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
