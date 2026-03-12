"""Agent run / REVIEW RPC handlers with real implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
