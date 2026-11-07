"""投递反馈条目与迭代记录列表 handler。

从 ``submission.py`` 拆出；反馈迭代目录与托管证据仍由原模块提供。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from tools.sidecar.handlers.submission import (
    _ALLOWED_FEEDBACK_SOURCES,
    _ALLOWED_ITERATION_ACTIONS,
    _load_submission_log,
    _managed_evidence,
    _platform_feedback_summary,
    _saved_feedback_iterations,
)
from tools.sidecar.handlers.submission_listing import (
    _find_submission_log,
    _managed_delivery,
)


def _feedback_item(
    *,
    source_type: str,
    source_run_id: str,
    source_artifact_path_or_id: str,
    summary: str,
    severity_or_priority: str,
    recommended_next_action: str,
) -> dict[str, str]:
    if source_type not in _ALLOWED_FEEDBACK_SOURCES:
        raise ValueError("unsupported_feedback_source")
    return {
        "source_type": source_type,
        "source_run_id": source_run_id,
        "source_artifact_path_or_id": source_artifact_path_or_id,
        "summary": summary,
        "severity_or_priority": severity_or_priority,
        "recommended_next_action": recommended_next_action,
    }


def _feedback_items_from_submission_log(
    payload: dict[str, Any], log_path: Path
) -> list[dict[str, str]]:
    source_run_id = str(payload.get("submission_id") or payload.get("run_id") or "")
    artifact = str(log_path)
    items: list[dict[str, str]] = []
    terminal_status = str(payload.get("terminal_status") or payload.get("status") or "")
    if terminal_status and _managed_delivery(payload):
        items.append(_feedback_item(source_type="submission_receipt", source_run_id=source_run_id,
            source_artifact_path_or_id=artifact, summary=terminal_status,
            severity_or_priority="info" if terminal_status=="success" else "high",
            recommended_next_action="acknowledge_and_skip"))
    elif terminal_status:
        action = (
            "prepare_next_check_mode"
            if terminal_status == "check_mode_success_submit_skipped"
            else "update_job_target"
        )
        items.append(
            _feedback_item(
                source_type="submission_check_mode_terminal_status",
                source_run_id=source_run_id,
                source_artifact_path_or_id=artifact,
                summary=terminal_status,
                severity_or_priority=(
                    "info"
                    if terminal_status == "check_mode_success_submit_skipped"
                    else "high"
                ),
                recommended_next_action=action,
            )
        )
    platform_feedback = _platform_feedback_summary(log_path.parent) if _managed_delivery(payload) else {}
    if platform_feedback:
        from tools.sidecar.handlers.platform_feedback import recommended_action
        action, severity = recommended_action(platform_feedback)
        items.append(_feedback_item(source_type="platform_delivery_status", source_run_id=source_run_id,
            source_artifact_path_or_id=str(log_path.parent / "platform_feedback.json"),
            summary=f"{platform_feedback['label'] or platform_feedback['status']} ({platform_feedback['status']})",
            severity_or_priority=severity, recommended_next_action=action))
    recovery_attempts = payload.get("target_recovery_attempts")
    if isinstance(recovery_attempts, list) and recovery_attempts:
        items.append(
            _feedback_item(
                source_type="target_recovery_result",
                source_run_id=source_run_id,
                source_artifact_path_or_id=artifact,
                summary=f"{len(recovery_attempts)} target recovery attempt(s)",
                severity_or_priority="medium",
                recommended_next_action="update_job_target",
            )
        )
    warning = payload.get("resume_target_mismatch_warning")
    if isinstance(warning, dict) and warning:
        items.append(
            _feedback_item(
                source_type="resume_target_mismatch_warning",
                source_run_id=source_run_id,
                source_artifact_path_or_id=artifact,
                summary=str(warning.get("status") or "resume_target_mismatch_warning"),
                severity_or_priority="medium",
                recommended_next_action="regenerate_resume_from_existing_evidence",
            )
        )
    steps = payload.get("steps")
    if isinstance(steps, list):
        blocked = [
            step
            for step in steps
            if isinstance(step, dict)
            and str(step.get("status", "")) in {"failed", "blocked"}
        ]
        for step in blocked[:3]:
            items.append(
                _feedback_item(
                    source_type="submission_check_mode_terminal_status",
                    source_run_id=source_run_id,
                    source_artifact_path_or_id=artifact,
                    summary=f"{step.get('name', '')}: {step.get('detail', '')}",
                    severity_or_priority="high",
                    recommended_next_action="update_job_target",
                )
            )
    return items


def _validate_feedback_items(items: object) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    validated: list[dict[str, str]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        source_type = str(raw.get("source_type") or "")
        if source_type not in _ALLOWED_FEEDBACK_SOURCES:
            raise ValueError("unsupported_feedback_source")
        validated.append(
            _feedback_item(
                source_type=source_type,
                source_run_id=str(raw.get("source_run_id") or ""),
                source_artifact_path_or_id=str(
                    raw.get("source_artifact_path_or_id") or ""
                ),
                summary=str(raw.get("summary") or ""),
                severity_or_priority=str(raw.get("severity_or_priority") or ""),
                recommended_next_action=str(raw.get("recommended_next_action") or ""),
            )
        )
    return validated


def _selected_iteration_actions(value: object) -> list[str]:
    actions = [
        str(item).strip()
        for item in value
        if str(item).strip()
    ] if isinstance(value, list) else []
    if not actions:
        raise ValueError("feedback_action_required")
    unsupported = [action for action in actions if action not in _ALLOWED_ITERATION_ACTIONS]
    if unsupported:
        raise ValueError("unsupported_feedback_action")
    return list(dict.fromkeys(actions))


def _copy_resume_for_new_version(
    source_payload: dict[str, Any],
    iteration_dir: Path,
    iteration_id: str,
) -> tuple[str, str]:
    previous_version = str(source_payload.get("resume_version_id") or "")
    previous_path_raw = str(source_payload.get("resume_path") or "")
    previous_path = Path(previous_path_raw)
    if not previous_version or not previous_path.exists():
        raise ValueError("missing_resume_pdf")
    new_version = f"{previous_version}_iter_{iteration_id[-8:]}"
    target = iteration_dir / "resume_versions" / f"{new_version}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(previous_path, target)
    return new_version, str(target)


def _iteration_comparison(
    *,
    previous_version: str,
    new_version: str,
    evidence_ids: list[str],
    remaining_gap_tasks: list[str],
) -> dict[str, Any]:
    return {
        "previous_version_id": previous_version,
        "new_version_id": new_version,
        "changed_sections": ["submission_feedback_notes"],
        "evidence_ids_used": evidence_ids,
        "new_or_updated_claims": [],
        "removed_claims": [],
        "score_delta_when_available": None,
        "remaining_gap_tasks": remaining_gap_tasks,
    }


def _feedback_iteration_result(
    correlation_id: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "meta": {"correlation_id": correlation_id},
        "iteration": record,
        "iteration_id": record["iteration_id"],
        "status": record["status"],
        "record_path": record["record_path"],
        "next_check_mode_candidate": record["next_check_mode_candidate"],
    }


def _resolve_submission_log_or_raise(source_run_id: str) -> Path:
    if not source_run_id:
        raise ValueError("source_run_id_required")
    path = _find_submission_log(source_run_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {source_run_id}")
    return path


def handle_feedback_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    source_run_id = str(params.get("source_run_id") or "").strip()
    log_path = _resolve_submission_log_or_raise(source_run_id)
    payload = _load_submission_log(log_path)
    items = _feedback_items_from_submission_log(payload, log_path)
    return {
        "meta": {"correlation_id": correlation_id},
        "source_run_id": source_run_id,
        "source_artifact_path": str(log_path),
        "items": items,
        "supported_actions": sorted(_ALLOWED_ITERATION_ACTIONS - ({"prepare_next_check_mode"} if _managed_delivery(payload) else set())),
        "source_binding": _managed_evidence(log_path, payload),
        "iterations": _saved_feedback_iterations(source_run_id),
    }
