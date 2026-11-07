"""Agent 审批队列写入：候选 payload 与队列文件。

从 orchestration/agent_loop.py 拆出；agent_loop 保留同名符号 re-export。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence

from tools.domain.value_objects import Candidate


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _review_queue_path(run_id: str) -> Path:
    return Path("outputs") / "review_queue" / f"{run_id}.json"

def _build_review_candidate_payload(
    *,
    candidate: Candidate | None,
    matching_score: float,
    evaluation_score: float,
    round_index: int,
    resume_version: str,
) -> dict[str, object]:
    return {
        "job_lead_id": candidate.candidate_id if candidate else "",
        "company": candidate.company if candidate else "",
        "legal_entity": candidate.legal_entity if candidate else "",
        "position": candidate.direction if candidate else "",
        "matching_score": matching_score,
        "evaluation_score": evaluation_score,
        "round_index": round_index,
        "resume_version": resume_version,
        "job_url": candidate.job_url if candidate else "",
        "platform": candidate.platform if candidate else "",
        "platform_job_id": candidate.platform_job_id if candidate else "",
        "platform_job_type": candidate.platform_job_type if candidate else "",
        "job_profile_id": candidate.job_profile_id if candidate else "",
        "jd_status": candidate.jd_status if candidate else "",
        "source_jd_sha256": candidate.source_jd_sha256 if candidate else "",
        "source": candidate.source if candidate else "",
        "status": "pending",
        "created_at": _utcnow_iso(),
    }

def _write_review_queue(run_id: str, candidates: Sequence[dict[str, object]]) -> Path:
    queue_path = _review_queue_path(run_id)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue = {
        "run_id": run_id,
        "candidates": list(candidates),
        "created_at": _utcnow_iso(),
    }
    from tools.infra.persistence.review_queue import atomic_write_json, locked_review_queue
    with locked_review_queue(queue_path):
        if queue_path.exists():
            raise ValueError('review_queue_already_exists')
        atomic_write_json(queue_path, queue)
    return queue_path

