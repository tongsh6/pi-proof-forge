"""渠道 check mode handler（只核验、不真实投递）。

从 ``submission.py`` 拆出；check 日志写入与渠道会话读取仍由原模块/会话子模块提供。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.sidecar.handlers.submission import (
    _CHECK_MODE_REQUIRED_CONFIRMATIONS,
    _load_channel_job_lead,
    _now_iso,
    _write_submission_check_log,
)
from tools.sidecar.handlers.submission_session import (
    _adapter_capabilities,
    _read_session,
    _reject_forbidden_session_params,
    _require_submission_channel,
)


def _resume_pdf_metadata(params: dict[str, Any]) -> dict[str, str]:
    resume_version_id = str(params.get("resume_version_id") or "").strip()
    resume_pdf_path = str(params.get("resume_pdf_path") or params.get("pdf_path") or "").strip()
    if not resume_version_id or not resume_pdf_path:
        raise ValueError("missing_resume_pdf")
    path = Path(resume_pdf_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise ValueError("missing_resume_pdf")
    try:
        if not path.read_bytes().startswith(b"%PDF-"):
            raise ValueError("invalid_resume_pdf")
    except OSError as exc:
        raise ValueError("missing_resume_pdf") from exc
    return {
        "resume_version_id": resume_version_id,
        "resume_path": str(path),
    }


def _check_mode_preflight(params: dict[str, Any], channel: str) -> dict[str, Any]:
    options = params.get("options")
    options = options if isinstance(options, dict) else {}
    if bool(options.get("submit_enabled") or params.get("submit_enabled")):
        raise ValueError("submit_enable_blocked_for_check_mode")
    confirmed = bool(params.get("preflight_confirmed") or options.get("preflight_confirmed"))
    confirmed_no_submit = bool(
        params.get("confirmed_no_real_submit")
        or options.get("confirmed_no_real_submit")
        or options.get("check_mode_no_real_submit")
    )
    items_raw = options.get("confirmation_items")
    items = {
        str(item)
        for item in items_raw
        if str(item).strip()
    } if isinstance(items_raw, list) else set()
    missing_items = sorted(_CHECK_MODE_REQUIRED_CONFIRMATIONS.difference(items))
    if not confirmed or not confirmed_no_submit or missing_items:
        raise ValueError("preflight_confirmation_required")
    return {
        "confirmed": True,
        "confirmed_no_real_submit": True,
        "channel": channel,
        "confirmation_items": sorted(items),
        "missing_items": [],
        "external_access_allowed_after_confirmation": True,
        "submit_enabled": False,
        "final_confirm_disabled_and_forbidden": True,
    }


def _coerce_recovery_limit(value: object) -> int:
    if value is None or value == "":
        return 2
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 2
    return max(0, min(parsed, 5))


def _blocked_check_mode_result(
    correlation_id: str,
    *,
    channel: str,
    status: str,
    next_action: str = "",
) -> dict[str, Any]:
    checked_at = _now_iso()
    session = _read_session(channel)
    payload = _write_submission_check_log(
        channel=channel,
        status=status,
        started_at=checked_at,
        ended_at=checked_at,
        original_job_lead={},
        final_verified_target={},
        resume={"resume_version_id": "", "resume_path": ""},
        session_metadata=session or {},
        preflight_confirmation={},
        target_recovery_limit=0,
        target_recovery_attempts=[],
        recovered_target_confirmation={},
        resume_target_mismatch_warning={},
        next_action=next_action,
        steps=[
            {
                "name": "login_check",
                "status": "blocked",
                "detail": status,
                "screenshot": "",
            }
        ],
        adapter_capabilities=_adapter_capabilities(channel),
    )
    return _check_mode_result(correlation_id, payload)


def _check_mode_result(correlation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {"correlation_id": correlation_id},
        "submission_id": payload["submission_id"],
        "status": payload["status"],
        "terminal_status": payload["terminal_status"],
        "channel": payload["channel"],
        "mode": payload["mode"],
        "steps": payload["steps"],
        "adapter_capabilities": payload["adapter_capabilities"],
        "original_job_lead": payload["original_job_lead"],
        "final_verified_target": payload["final_verified_target"],
        "session_metadata": payload["session_metadata"],
        "target_recovery_attempts": payload["target_recovery_attempts"],
        "recovered_target_confirmation": payload["recovered_target_confirmation"],
        "resume_target_mismatch_warning": payload["resume_target_mismatch_warning"],
        "next_action": payload["next_action"],
        "submit_enabled": payload["submit_enabled"],
        "final_submit_attempted": payload["final_submit_attempted"],
        "external_submission_attempted": payload["external_submission_attempted"],
        "log_json_path": payload["log_json_path"],
        "log_yaml_path": payload["log_yaml_path"],
    }


def handle_submission_check_mode(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    _reject_forbidden_session_params(params)
    channel = _require_submission_channel(params)
    options = params.get("options")
    options = options if isinstance(options, dict) else {}
    preflight_confirmation = _check_mode_preflight(params, channel)
    job_lead_id = str(params.get("job_lead_id") or "").strip()
    original_job_lead = _load_channel_job_lead(job_lead_id, channel)
    resume = _resume_pdf_metadata(params)
    session = _read_session(channel)
    session_status = str((session or {}).get("login_status") or "")
    if session_status != "session_valid":
        blocked_status = (
            "login_required"
            if not session_status or session_status in {"ready_to_setup", "waiting_for_manual_login"}
            else session_status
        )
        return _blocked_check_mode_result(
            correlation_id,
            channel=channel,
            status=blocked_status,
            next_action="go_to_channel_session_setup",
        )
    if options.get("session_identity_accepted") is False:
        return _blocked_check_mode_result(
            correlation_id,
            channel=channel,
            status="account_identity_mismatch",
            next_action="go_to_channel_session_setup_to_clear_or_refresh",
        )

    started_at = _now_iso()
    target_recovery_limit = _coerce_recovery_limit(options.get("target_recovery_limit"))
    adapter_capabilities = _adapter_capabilities(channel)
    rate_limited = bool(options.get("simulate_rate_limited"))
    target_mismatch = bool(options.get("simulate_target_mismatch"))
    recovery_confirmed = bool(options.get("recovered_target_confirmed"))
    resume_warning_ack = bool(options.get("resume_target_mismatch_warning_acknowledged"))
    abort_to_regenerate = bool(options.get("abort_to_regenerate_resume"))

    rate_detail = (
        f"channel={channel}; recovery_limit={target_recovery_limit}; "
        "final_submit_forbidden=true"
    )
    steps: list[dict[str, str]] = [
        {
            "name": "rate_limit",
            "status": "blocked" if rate_limited else "success",
            "detail": "rate_limited" if rate_limited else rate_detail,
            "screenshot": "",
        }
    ]
    target_recovery_attempts: list[dict[str, Any]] = []
    recovered_target_confirmation: dict[str, Any] = {}
    resume_target_mismatch_warning: dict[str, Any] = {}
    next_action = ""
    final_target = dict(original_job_lead)
    terminal_status = "check_mode_success_submit_skipped"

    if rate_limited:
        terminal_status = "rate_limited"
    else:
        steps.extend(
            [
                {
                    "name": "open_target",
                    "status": "success",
                    "detail": original_job_lead["job_url"],
                    "screenshot": "",
                },
                {
                    "name": "login_check",
                    "status": "success",
                    "detail": f"session_id={session.get('session_id', '')}",
                    "screenshot": "",
                },
            ]
        )
        if target_mismatch:
            steps.append(
                {
                    "name": "target_verify",
                    "status": "failed",
                    "detail": "target_mismatch",
                    "screenshot": "",
                }
            )
            for attempt_index in range(1, target_recovery_limit + 1):
                recovered = {
                    **original_job_lead,
                    "job_url": f"{original_job_lead['job_url']}?recovered={attempt_index}",
                    "position": f"{original_job_lead['position']} (Recovered)",
                }
                attempt = {
                    "attempt_index": attempt_index,
                    "candidate_source": "same_channel_similar_jobs",
                    "candidate_url_or_identifier": recovered["job_url"],
                    "reason_selected": "target_mismatch_recovery",
                    "target_verify_result": "success",
                    "rate_limit_status": "success",
                }
                target_recovery_attempts.append(attempt)
                final_target = recovered
                break
            if not target_recovery_attempts:
                terminal_status = "target_recovery_exhausted"
                next_action = "inspect_or_select_new_channel_job_lead"
            elif not recovery_confirmed:
                terminal_status = "recovered_target_pending_confirmation"
                next_action = "confirm_or_reject_recovered_target"
            else:
                recovered_target_confirmation = {
                    "status": "recovered_target_confirmed",
                    "original_company": original_job_lead["company"],
                    "original_role": original_job_lead["position"],
                    "original_url": original_job_lead["job_url"],
                    "original_channel": channel,
                    "recovered_company": final_target["company"],
                    "recovered_role": final_target["position"],
                    "recovered_url": final_target["job_url"],
                    "recovered_channel": channel,
                    "candidate_source": "same_channel_similar_jobs",
                    "reason_selected": "target_mismatch_recovery",
                    "target_verify_result": "success",
                    "difference_summary": "same channel recovered target differs from original URL/role",
                }
                if abort_to_regenerate:
                    terminal_status = "regenerate_resume_for_recovered_target"
                    next_action = "regenerate_resume_for_recovered_target"
                elif not resume_warning_ack:
                    terminal_status = "resume_target_mismatch_warning_pending"
                    next_action = "acknowledge_resume_target_mismatch_warning"
                    resume_target_mismatch_warning = {
                        "status": "pending",
                        "detail": "resume was generated for original target",
                    }
                else:
                    resume_target_mismatch_warning = {
                        "status": "resume_target_mismatch_warning_acknowledged",
                        "detail": "user acknowledged recovered-target resume warning",
                    }
                    steps.append(
                        {
                            "name": "target_recovery_attempt_when_configured",
                            "status": "success",
                            "detail": "recovered_target_confirmed",
                            "screenshot": "",
                        }
                    )
        else:
            steps.append(
                {
                    "name": "target_verify",
                    "status": "success",
                    "detail": (
                        f"job_id={original_job_lead.get('job_id', '')}; "
                        f"recruiter={original_job_lead.get('recruiter', '')}"
                    ),
                    "screenshot": "",
                }
            )

    if terminal_status == "check_mode_success_submit_skipped":
        steps.extend(
            [
                {
                    "name": "send_resume_path_check",
                    "status": "success",
                    "detail": adapter_capabilities["send_resume_path"],
                    "screenshot": "",
                },
                {
                    "name": "attachment_check",
                    "status": "attachment_check_not_supported",
                    "detail": resume["resume_path"],
                    "screenshot": "",
                },
                {
                    "name": "submit_skipped",
                    "status": "success",
                    "detail": "stopped_before_final_confirm; final_submit_attempted=false",
                    "screenshot": "",
                },
            ]
        )
    elif terminal_status not in {"rate_limited", "target_recovery_exhausted"}:
        steps.append(
            {
                "name": "send_resume_path_check",
                "status": "blocked",
                "detail": terminal_status,
                "screenshot": "",
            }
        )

    ended_at = _now_iso()
    payload = _write_submission_check_log(
        channel=channel,
        status=terminal_status,
        started_at=started_at,
        ended_at=ended_at,
        original_job_lead=original_job_lead,
        final_verified_target=final_target if terminal_status != "rate_limited" else {},
        resume=resume,
        session_metadata={
            "channel": session.get("channel", channel),
            "session_id": session.get("session_id", ""),
            "session_path": session.get("session_path", ""),
            "login_status": session.get("login_status", ""),
            "checked_at": session.get("checked_at", ""),
            "account_identity": session.get("account_identity", {}),
        },
        preflight_confirmation=preflight_confirmation,
        target_recovery_limit=target_recovery_limit,
        target_recovery_attempts=target_recovery_attempts,
        recovered_target_confirmation=recovered_target_confirmation,
        resume_target_mismatch_warning=resume_target_mismatch_warning,
        next_action=next_action,
        steps=steps,
        adapter_capabilities=adapter_capabilities,
    )
    return _check_mode_result(correlation_id, payload)
