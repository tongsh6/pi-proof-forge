from __future__ import annotations

import json
from uuid import uuid4
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.browser.liepin_session import session_browser as _session_browser

_SUBMISSIONS_DIR = Path("outputs") / "submissions"
_CHANNEL_SESSIONS_DIR = Path("outputs") / "channel_sessions"
_JOB_LEAD_DIR = Path("job_leads")
_FEEDBACK_ITERATIONS_DIR = Path("outputs") / "feedback_iterations"
_ALLOWED_RETRY_STRATEGIES = {"same_channel", "fallback_email"}
_ALLOWED_FEEDBACK_SOURCES = {
    "submission_receipt",
    "evaluation_scorecard",
    "matching_gap_tasks",
    "gate_decision",
    "review_decision",
    "submission_check_mode_terminal_status",
    "target_recovery_result",
    "resume_target_mismatch_warning",
    "platform_delivery_status",
}
_ALLOWED_ITERATION_ACTIONS = {
    "add_or_edit_evidence_card",
    "update_job_target",
    "regenerate_resume_from_existing_evidence",
    "acknowledge_and_skip",
    "prepare_next_check_mode",
}
_SUPPORTED_SUBMISSION_CHANNELS: dict[str, dict[str, str]] = {
    "liepin": {
        "label": "Liepin",
        "login_url": "https://www.liepin.com/",
        "positive_signal": "logged_in_user_ui_or_equivalent_authenticated_signal",
    }
}
_FORBIDDEN_SESSION_PARAM_KEYS = {
    "password",
    "credential",
    "credentials",
    "captcha",
    "captcha_code",
    "sms",
    "sms_code",
    "otp",
    "verification_code",
}
_CHECK_MODE_REQUIRED_CONFIRMATIONS = {
    "check_mode_no_real_submit",
    "selected_submission_channel",
    "selected_channel_job_lead",
    "selected_resume_pdf",
    "selected_channel_session_metadata",
    "may_use_channel_shared_session",
    "final_confirm_disabled_and_forbidden",
    "must_stop_before_final_confirm",
}


def _build_submission_check_id() -> str:
    now = datetime.now(timezone.utc)
    return f"sc_{now.strftime('%Y%m%d%H%M%S%f')}"


def _build_feedback_iteration_id() -> str:
    now = datetime.now(timezone.utc)
    return f"fi_{now.strftime('%Y%m%d%H%M%S%f')}"


def _platform_feedback_summary(submission_dir: Path) -> dict[str, str]:
    # 延迟导入避免循环；平台进展只读，不参与回执核验。
    from tools.sidecar.handlers.platform_feedback import platform_feedback_summary
    return platform_feedback_summary(submission_dir)


def _submission_log_paths() -> list[Path]:
    if not _SUBMISSIONS_DIR.exists():
        return []
    return sorted(_SUBMISSIONS_DIR.rglob("submission_log.json"))


def _load_submission_log(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel_root(channel: str) -> Path:
    return _CHANNEL_SESSIONS_DIR / channel


def _channel_profile_path(channel: str) -> Path:
    return _channel_root(channel) / "browser_profile"


def _channel_session_path(channel: str) -> Path:
    return _channel_root(channel) / "session.json"


def _channel_log_path(channel: str) -> Path:
    return _channel_root(channel) / "session_check_log.json"


def _load_channel_job_lead(job_lead_id: str, channel: str) -> dict[str, Any]:
    if not job_lead_id:
        raise ValueError("missing_channel_job_lead")
    path = _JOB_LEAD_DIR / f"{job_lead_id}.yaml"
    if not path.exists():
        raise ValueError("missing_channel_job_lead")
    doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
    scalars = doc["scalars"]
    lead_channel = str(scalars.get("channel") or channel).strip().lower()
    if lead_channel != channel:
        raise ValueError("channel_job_lead_mismatch")
    job_url = str(scalars.get("job_url") or scalars.get("url") or "").strip()
    if not job_url:
        raise ValueError("missing_channel_job_lead")
    return {
        "job_lead_id": str(scalars.get("id") or job_lead_id),
        "channel": channel,
        "company": str(scalars.get("company") or ""),
        "position": str(scalars.get("position") or scalars.get("title") or ""),
        "job_url": job_url,
        "job_id": str(scalars.get("job_id") or ""),
        "recruiter": str(scalars.get("recruiter") or ""),
        "source": str(scalars.get("source") or "job_leads"),
        "path": str(path),
    }


def _write_submission_check_log(
    *,
    channel: str,
    status: str,
    started_at: str,
    ended_at: str,
    original_job_lead: dict[str, Any],
    final_verified_target: dict[str, Any],
    resume: dict[str, str],
    session_metadata: dict[str, Any],
    preflight_confirmation: dict[str, Any],
    target_recovery_limit: int,
    target_recovery_attempts: list[dict[str, Any]],
    recovered_target_confirmation: dict[str, Any],
    resume_target_mismatch_warning: dict[str, Any],
    next_action: str,
    steps: list[dict[str, str]],
    adapter_capabilities: dict[str, Any],
) -> dict[str, Any]:
    submission_id = _build_submission_check_id()
    run_dir = _SUBMISSIONS_DIR / channel / submission_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_json = run_dir / "submission_log.json"
    log_yaml = run_dir / "submission_log.yaml"
    payload = {
        "run_id": submission_id,
        "submission_id": submission_id,
        "platform": channel,
        "channel": channel,
        "mode": "check",
        "status": status,
        "terminal_status": status,
        "error": "" if status == "check_mode_success_submit_skipped" else status,
        "started_at": started_at,
        "ended_at": ended_at,
        "job_url": str(final_verified_target.get("job_url") or original_job_lead.get("job_url") or ""),
        "company": str(final_verified_target.get("company") or original_job_lead.get("company") or ""),
        "position": str(final_verified_target.get("position") or original_job_lead.get("position") or ""),
        "resume_version_id": resume["resume_version_id"],
        "resume_path": resume["resume_path"],
        "profile_path": "",
        "headless": True,
        "browser_channel": str(adapter_capabilities.get("browser_channel") or channel),
        "adapter_capabilities": adapter_capabilities,
        "original_job_lead": original_job_lead,
        "final_verified_target": final_verified_target,
        "session_metadata": session_metadata,
        "preflight_confirmation": preflight_confirmation,
        "target_recovery_limit": target_recovery_limit,
        "target_recovery_attempts": target_recovery_attempts,
        "recovered_target_confirmation": recovered_target_confirmation,
        "resume_target_mismatch_warning": resume_target_mismatch_warning,
        "next_action": next_action,
        "attachment_check": "attachment_check_not_supported",
        "submit_enabled": False,
        "final_submit_attempted": False,
        "external_submission_attempted": False,
        "steps": steps,
    }
    log_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log_yaml.write_text(
        "\n".join(
            [
                f'run_id: "{submission_id}"',
                f'channel: "{channel}"',
                'mode: "check"',
                f'status: "{status}"',
                f'terminal_status: "{status}"',
                f'resume_version_id: "{resume["resume_version_id"]}"',
                f'resume_path: "{resume["resume_path"]}"',
                f'job_url: "{payload["job_url"]}"',
                "final_submit_attempted: false",
                "steps:",
                *[
                    f'  - name: "{step["name"]}"\n    status: "{step["status"]}"\n    detail: "{step["detail"]}"\n    screenshot: "{step.get("screenshot", "")}"'
                    for step in steps
                ],
                "",
            ]
        ),
        encoding="utf-8",
    )
    payload["log_json_path"] = str(log_json)
    payload["log_yaml_path"] = str(log_yaml)
    return payload


def _managed_evidence(log_path: Path, payload: dict) -> dict:
    if not _managed_delivery(payload):
        return {}
    from tools.infra.submission_evidence import inspect_submission_evidence
    return inspect_submission_evidence(_SUBMISSIONS_DIR.resolve().parents[1], log_path.resolve())


def _saved_feedback_iterations(source_run_id: str) -> list[dict]:
    records=[]
    for path in sorted(_FEEDBACK_ITERATIONS_DIR.glob("fi_*/iteration_record.json"), reverse=True):
        if path.is_symlink() or not path.resolve().is_relative_to(_FEEDBACK_ITERATIONS_DIR.resolve()):
            continue
        try:
            record=json.loads(path.read_text())
            if record.get("source_run_id")==source_run_id:
                records.append(record)
        except (OSError, ValueError, AttributeError):
            continue
    return records


def _create_managed_feedback(params: dict, log_path: Path, payload: dict) -> dict:
    # 反馈是用户记录及下一步计划，不改业务回执，不调用生成或投递。
    from tools.infra.persistence.review_queue import atomic_write_json
    source_run_id=payload["run_id"]
    items=_feedback_items_from_submission_log(payload, log_path)
    supplied=_validate_feedback_items(params.get("source_feedback_items"))
    if supplied and any(item not in items for item in supplied):
        raise ValueError("feedback_source_mismatch")
    actions=_selected_iteration_actions(params.get("selected_actions"))
    if "prepare_next_check_mode" in actions:
        raise ValueError("managed_feedback_use_quick_run")
    note=str(params.get("user_notes") or "").strip()
    if not note:
        raise ValueError("feedback_note_required")
    if len(note)>4000:
        raise ValueError("feedback_note_too_long")
    source=params.get("feedback_source", "user_note")
    if source not in {"user_note", "manual_recruiter"}:
        raise ValueError("unsupported_feedback_source")
    if params.get("new_or_updated_claims"):
        raise ValueError("feedback_claims_require_generation")
    binding=_managed_evidence(log_path,payload)
    inputs=payload.get("input_artifacts",{})
    version=binding.get("resume_version_id") or inputs.get("resume_version", "")
    profile=binding.get("job_profile_id") or inputs.get("job_profile_id", "")
    if "regenerate_resume_from_existing_evidence" in actions and not profile:
        raise ValueError("feedback_job_profile_missing")
    iid=_build_feedback_iteration_id();directory=_FEEDBACK_ITERATIONS_DIR/iid
    directory.mkdir(parents=True, mode=0o700);directory.chmod(0o700)
    snapshot=directory/"source_snapshot.json";record_path=directory/"iteration_record.json"
    snapshot.write_bytes(log_path.read_bytes());snapshot.chmod(0o444)
    quick_run={"job_profile_id":profile,"source_submission_id":source_run_id,"requires_review":True} if "regenerate_resume_from_existing_evidence" in actions else {}
    next_step=("quick_run" if quick_run else "evidence" if "add_or_edit_evidence_card" in actions else "jobs" if "update_job_target" in actions else "review_iteration_record")
    record={"iteration_id":iid,"status":"iteration_recorded","created_at":_now_iso(),"source_run_id":source_run_id,
        "source_binding":binding,"feedback_source":source,"source_feedback_items":items,"selected_actions":actions,"user_notes":note,
        "previous_resume_version_id":version,"new_resume_version_id_or_none":"","evidence_card_ids_added_or_updated":[],
        "job_target_id_or_none":binding.get("job_lead_id", ""),"comparison_summary":{"status":"comparison_unavailable","reason":"no_new_resume_version_created"},
        "remaining_gap_tasks":[],"next_recommended_step":next_step,"next_quick_run_candidate":quick_run,"next_check_mode_candidate":{},
        "source_snapshot_path":str(snapshot),"source_snapshot_sha256":hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "record_path":str(record_path),"affected_artifacts":{"source_submission_log":str(log_path),"source_snapshot":str(snapshot)},
        "immutable_source_snapshot":True,"previous_artifacts_preserved":True,"real_submit_disabled":True}
    atomic_write_json(record_path,record);record_path.chmod(0o600)
    return _feedback_iteration_result(params["meta"]["correlation_id"],record)


def handle_submission_record_manual(params: dict[str, Any]) -> dict[str, Any]:
    """手动投递记录：用户在 App 外完成投递后回填一条记录。

    规范：openspec/specs/pi-proof-forge-core.md「人工导入来源契约」。写入与自动投递相同的
    submission_log.json 位置，transport/mode 为 manual，status 为 manual_recorded，不计入自动确认数、不可重试。
    """
    from tools.sidecar.handlers._shared import job_repository

    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = str(params.get("job_profile_id") or "").strip()
    if not job_profile_id:
        raise ValueError("job_profile_id_required")
    profile_path = job_repository.profile_path(job_profile_id)
    if not profile_path.exists():
        raise KeyError(f"NOT_FOUND: {job_profile_id}")
    scalars = job_repository.read_yaml_doc(profile_path)["scalars"]
    source_url = str(scalars.get("source_url", "")).strip()
    platform = str(scalars.get("platform") or job_repository.platform_from_url(source_url) or "other")
    delivered_at = str(params.get("delivered_at") or "").strip() or _now_iso()
    if _safe_parse_iso_datetime(delivered_at) is None:
        raise ValueError("delivered_at_invalid")
    note = str(params.get("note") or "").strip()[:2000]
    quick_run_id = str(params.get("quick_run_id") or "").strip()
    run_id = f"manual-{uuid4().hex[:12]}"
    recorded_at = _now_iso()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "platform": platform,
        "transport": "manual",
        "mode": "manual",
        "status": "manual_recorded",
        "terminal_status": "manual_recorded",
        "receipt_source": "manual_tracking",
        "company": str(scalars.get("company", "")),
        "position": str(scalars.get("target_role", "")),
        "job_url": source_url,
        "job_profile_id": job_profile_id,
        "job_lead_id": str(scalars.get("job_lead_id", "")),
        "quick_run_id": quick_run_id,
        "resume_version_id": quick_run_id,
        "note": note,
        "started_at": delivered_at,
        "ended_at": delivered_at,
        "recorded_at": recorded_at,
        "final_submit_attempted": False,
        "external_submission_attempted": True,
        "steps": [{"name": "manual_record", "status": "recorded", "detail": note}],
    }
    run_dir = _SUBMISSIONS_DIR / platform / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "submission_log.json"
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "meta": {"correlation_id": correlation_id},
        "submission_id": run_id,
        "status": "manual_recorded",
        "platform": platform,
        "delivered_at": delivered_at,
        "log_json_path": str(log_path),
    }


def handle_feedback_create_iteration(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    source_run_id = str(params.get("source_run_id") or "").strip()
    log_path = _resolve_submission_log_or_raise(source_run_id)
    source_payload = _load_submission_log(log_path)
    if _managed_delivery(source_payload):
        return _create_managed_feedback(params, log_path, source_payload)
    source_items = _validate_feedback_items(params.get("source_feedback_items"))
    if not source_items:
        source_items = _feedback_items_from_submission_log(source_payload, log_path)
    selected_actions = _selected_iteration_actions(params.get("selected_actions"))
    user_notes = str(params.get("user_notes") or "").strip()
    if "acknowledge_and_skip" in selected_actions and not user_notes:
        raise ValueError("feedback_note_required")

    evidence_ids = [
        str(item).strip()
        for item in (params.get("evidence_card_ids_added_or_updated") or [])
        if str(item).strip()
    ] if isinstance(params.get("evidence_card_ids_added_or_updated"), list) else []
    new_claims = [
        str(item).strip()
        for item in (params.get("new_or_updated_claims") or [])
        if str(item).strip()
    ] if isinstance(params.get("new_or_updated_claims"), list) else []
    if new_claims and not evidence_ids:
        raise ValueError("new_claims_require_evidence_links")

    iteration_id = _build_feedback_iteration_id()
    iteration_dir = _FEEDBACK_ITERATIONS_DIR / iteration_id
    iteration_dir.mkdir(parents=True, exist_ok=True)
    source_snapshot_path = iteration_dir / "source_snapshot.json"
    source_snapshot_path.write_text(
        json.dumps(source_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    previous_resume_version = str(source_payload.get("resume_version_id") or "")
    new_resume_version = ""
    new_resume_path = ""
    affected_artifacts: dict[str, Any] = {
        "source_submission_log": str(log_path),
        "source_snapshot": str(source_snapshot_path),
        "previous_resume_path": str(source_payload.get("resume_path") or ""),
    }
    remaining_gap_tasks = [
        str(item).strip()
        for item in (params.get("remaining_gap_tasks") or [])
        if str(item).strip()
    ] if isinstance(params.get("remaining_gap_tasks"), list) else []

    if "regenerate_resume_from_existing_evidence" in selected_actions:
        new_resume_version, new_resume_path = _copy_resume_for_new_version(
            source_payload,
            iteration_dir,
            iteration_id,
        )
        affected_artifacts["new_resume_path"] = new_resume_path

    comparison_summary: dict[str, Any] = {}
    if new_resume_version:
        comparison_summary = _iteration_comparison(
            previous_version=previous_resume_version,
            new_version=new_resume_version,
            evidence_ids=evidence_ids,
            remaining_gap_tasks=remaining_gap_tasks,
        )
        comparison_summary["new_or_updated_claims"] = [
            {"claim": claim, "evidence_ids": evidence_ids}
            for claim in new_claims
        ]
    elif "regenerate_resume_from_existing_evidence" not in selected_actions:
        comparison_summary = {
            "status": "comparison_unavailable",
            "reason": "no_new_resume_version_created",
            "remaining_gap_tasks": remaining_gap_tasks,
        }

    next_check_mode_candidate: dict[str, Any] = {}
    if "prepare_next_check_mode" in selected_actions or new_resume_version:
        next_check_mode_candidate = {
            "channel": source_payload.get("channel", source_payload.get("platform", "")),
            "job_lead_id": (source_payload.get("final_verified_target") or {}).get(
                "job_lead_id",
                (source_payload.get("original_job_lead") or {}).get("job_lead_id", ""),
            ),
            "resume_version_id": new_resume_version or previous_resume_version,
            "resume_pdf_path": new_resume_path or str(source_payload.get("resume_path") or ""),
            "real_submit_disabled": True,
            "requires_user_confirmation": True,
        }

    next_step = "prepare_next_check_mode" if next_check_mode_candidate else "review_iteration_record"
    record_path = iteration_dir / "iteration_record.json"
    record = {
        "iteration_id": iteration_id,
        "status": "iteration_recorded",
        "created_at": _now_iso(),
        "source_run_id": source_run_id,
        "source_feedback_items": source_items,
        "selected_actions": selected_actions,
        "user_notes": user_notes,
        "affected_artifacts": affected_artifacts,
        "previous_resume_version_id": previous_resume_version,
        "new_resume_version_id_or_none": new_resume_version,
        "evidence_card_ids_added_or_updated": evidence_ids,
        "job_target_id_or_none": str(params.get("job_target_id_or_none") or ""),
        "comparison_summary": comparison_summary,
        "remaining_gap_tasks": remaining_gap_tasks,
        "next_recommended_step": next_step,
        "next_check_mode_candidate": next_check_mode_candidate,
        "source_snapshot_path": str(source_snapshot_path),
        "record_path": str(record_path),
        "immutable_source_snapshot": True,
        "previous_artifacts_preserved": True,
        "real_submit_disabled": True,
    }
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return _feedback_iteration_result(correlation_id, record)


# 拆分子模块继续以 submission 作为公开入口 re-export。
from tools.sidecar.handlers.submission_session import (  # noqa: E402
    _adapter_capabilities,
    _read_session,
    _require_submission_channel,
    _reject_forbidden_session_params,
    _session_payload,
    _session_result,
    _write_session,
    _write_session_log,
    handle_channel_session_check,
    handle_channel_session_clear,
    handle_channel_session_get,
    handle_channel_session_start,
)
from tools.sidecar.handlers.submission_listing import (  # noqa: E402
    _find_submission_log,
    _managed_delivery,
    _parse_cursor,
    _parse_date_range,
    _parse_page_size,
    _parse_sort_field,
    _parse_sort_order,
    _safe_parse_iso_datetime,
    _submission_item,
    handle_submission_detail,
    handle_submission_list,
    handle_submission_retry,
)
from tools.sidecar.handlers.submission_check import (  # noqa: E402
    _check_mode_result,
    _resume_pdf_metadata,
    handle_submission_check_mode,
)
from tools.sidecar.handlers.submission_feedback import (  # noqa: E402
    _copy_resume_for_new_version,
    _feedback_item,
    _feedback_items_from_submission_log,
    _feedback_iteration_result,
    _iteration_comparison,
    _resolve_submission_log_or_raise,
    _selected_iteration_actions,
    _validate_feedback_items,
    handle_feedback_list,
)
