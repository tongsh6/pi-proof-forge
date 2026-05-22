from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.persistence.yaml_io import parse_simple_yaml

_SUBMISSIONS_DIR = Path("outputs") / "submissions"
_CHANNEL_SESSIONS_DIR = Path("outputs") / "channel_sessions"
_JOB_LEAD_DIR = Path("job_leads")
_FEEDBACK_ITERATIONS_DIR = Path("outputs") / "feedback_iterations"
_ALLOWED_RETRY_STRATEGIES = {"same_channel", "fallback_email"}
_ALLOWED_FEEDBACK_SOURCES = {
    "evaluation_scorecard",
    "matching_gap_tasks",
    "gate_decision",
    "review_decision",
    "submission_check_mode_terminal_status",
    "target_recovery_result",
    "resume_target_mismatch_warning",
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
        "login_url": "https://passport.liepin.com/login/",
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


def _submission_log_paths() -> list[Path]:
    if not _SUBMISSIONS_DIR.exists():
        return []
    return sorted(_SUBMISSIONS_DIR.rglob("submission_log.json"))


def _load_submission_log(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_submission_log_or_raise(source_run_id: str) -> Path:
    if not source_run_id:
        raise ValueError("source_run_id_required")
    path = _find_submission_log(source_run_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {source_run_id}")
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_submission_channel(params: dict[str, Any]) -> str:
    channel = str(params.get("channel") or "").strip().lower()
    if not channel:
        raise ValueError("channel_required")
    if channel not in _SUPPORTED_SUBMISSION_CHANNELS:
        raise ValueError("unsupported_submission_channel")
    return channel


def _reject_forbidden_session_params(value: object, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_SESSION_PARAM_KEYS:
                location = f"{path}.{normalized}" if path else normalized
                raise ValueError(f"credentials_or_challenge_input_forbidden: {location}")
            _reject_forbidden_session_params(
                child, f"{path}.{normalized}" if path else normalized
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_session_params(child, f"{path}[{index}]")


def _channel_root(channel: str) -> Path:
    return _CHANNEL_SESSIONS_DIR / channel


def _channel_profile_path(channel: str) -> Path:
    return _channel_root(channel) / "browser_profile"


def _channel_session_path(channel: str) -> Path:
    return _channel_root(channel) / "session.json"


def _channel_log_path(channel: str) -> Path:
    return _channel_root(channel) / "session_check_log.json"


def _supported_channels_payload() -> list[dict[str, str]]:
    return [
        {
            "channel": channel,
            "label": config["label"],
            "login_url": config["login_url"],
        }
        for channel, config in sorted(_SUPPORTED_SUBMISSION_CHANNELS.items())
    ]


def _adapter_capabilities(channel: str) -> dict[str, Any]:
    if channel == "liepin":
        return {
            "channel": channel,
            "browser_channel": "liepin",
            "supports_check_mode": True,
            "supports_target_recovery": True,
            "supports_attachment_check": False,
            "final_submit_control": "confirm_send_button",
            "send_resume_path": "chat_send_resume",
            "target_safety_fields": ["job_id", "recruiter"],
            "adapter": {
                "liepin": {
                    "main_job_button_only": True,
                    "recommendation_area_requires_recovery": True,
                }
            },
        }
    raise ValueError("unsupported_submission_channel")


def _mask_contact_suffix(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    suffix = raw[-4:]
    return f"***{suffix}"


def _safe_account_identity(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("account_identity")
    if not isinstance(raw, dict):
        return {
            "status": "account_identity_unknown",
            "display_name_or_nickname": "",
            "avatar_presence": None,
            "masked_phone_or_email_suffix": "",
        }

    display_name = str(raw.get("display_name_or_nickname") or raw.get("display_name") or raw.get("nickname") or "").strip()
    masked_suffix = _mask_contact_suffix(
        raw.get("masked_phone_or_email_suffix") or raw.get("masked_contact_suffix")
    )
    avatar_raw = raw.get("avatar_presence")
    avatar_presence = bool(avatar_raw) if avatar_raw is not None else None
    status = (
        "available"
        if display_name or masked_suffix or avatar_presence is not None
        else "account_identity_unknown"
    )
    return {
        "status": status,
        "display_name_or_nickname": display_name,
        "avatar_presence": avatar_presence,
        "masked_phone_or_email_suffix": masked_suffix,
    }


def _session_payload(
    *,
    channel: str,
    login_status: str,
    checked_at: str,
    account_identity: dict[str, Any] | None = None,
    session_id: str | None = None,
    clear_available: bool = False,
    log_path: Path | None = None,
) -> dict[str, Any]:
    config = _SUPPORTED_SUBMISSION_CHANNELS[channel]
    profile_path = _channel_profile_path(channel)
    resolved_session_id = session_id or f"cs_{channel}_{checked_at.replace(':', '').replace('-', '').replace('.', '')}"
    return {
        "channel": channel,
        "session_id": resolved_session_id,
        "session_path": str(profile_path),
        "login_status": login_status,
        "account_identity": account_identity
        or {
            "status": "account_identity_unknown",
            "display_name_or_nickname": "",
            "avatar_presence": None,
            "masked_phone_or_email_suffix": "",
        },
        "checked_at": checked_at,
        "expires_or_unknown": "unknown",
        "clear_available": clear_available,
        "log_path": str(log_path or _channel_log_path(channel)),
        "adapter": {
            channel: {
                "login_url": config["login_url"],
                "storage_policy": "browser_profile_or_equivalent_session_state",
                "positive_login_signal": config["positive_signal"],
            }
        },
    }


def _write_session(channel: str, session: dict[str, Any]) -> None:
    path = _channel_session_path(channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_session(channel: str) -> dict[str, Any] | None:
    path = _channel_session_path(channel)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_session_log(
    *,
    channel: str,
    terminal_status: str,
    steps: list[dict[str, str]],
    checked_at: str,
) -> Path:
    path = _channel_log_path(channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "channel": channel,
        "steps": steps,
        "terminal_status": terminal_status,
        "screenshot_path": "",
        "log_path": str(path),
        "checked_at": checked_at,
        "adapter": {
            channel: {
                "login_url": _SUPPORTED_SUBMISSION_CHANNELS[channel]["login_url"],
                "credential_entry_attempted": False,
                "captcha_sms_bypass_attempted": False,
            }
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _session_result(
    correlation_id: str,
    *,
    channel: str,
    session: dict[str, Any],
    steps: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "meta": {"correlation_id": correlation_id},
        "supported_channels": _supported_channels_payload(),
        "session": session,
        "steps": steps or [],
        "manual_login_required": session["login_status"] == "waiting_for_manual_login",
        "browser_automation": {
            "opened_login_page": session["login_status"] == "waiting_for_manual_login",
            "entered_credentials": False,
            "entered_captcha_or_sms": False,
            "captcha_sms_bypass_attempted": False,
        },
        "artifact_paths": {
            "channel_session": str(_channel_session_path(channel)),
            "session_check_log": session.get("log_path", str(_channel_log_path(channel))),
        },
    }


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
    if terminal_status:
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


def _last_step(payload: dict[str, Any]) -> dict[str, str]:
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return {"name": "", "status": "", "detail": ""}
    raw = steps[-1]
    if not isinstance(raw, dict):
        return {"name": "", "status": "", "detail": ""}
    return {
        "name": str(raw.get("name", "")),
        "status": str(raw.get("status", "")),
        "detail": str(raw.get("detail", "")),
    }


def _step_by_name(payload: dict[str, Any], name: str) -> dict[str, str]:
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        return {"name": "", "status": "", "detail": ""}
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("name", "")) == name:
            return {
                "name": str(raw.get("name", "")),
                "status": str(raw.get("status", "")),
                "detail": str(raw.get("detail", "")),
            }
    return {"name": "", "status": "", "detail": ""}


def _parse_cursor(value: object) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _parse_page_size(value: object) -> int:
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            parsed = 20
    else:
        parsed = 20
    return max(1, min(parsed, 100))


def _parse_sort_field(value: object) -> str:
    field = str(value or "submitted_at")
    if field in {"submitted_at", "status"}:
        return field
    return "submitted_at"


def _parse_sort_order(value: object) -> str:
    order = str(value or "desc")
    if order in {"asc", "desc"}:
        return order
    return "desc"


def _safe_parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date_range(value: object) -> tuple[datetime | None, datetime | None]:
    if isinstance(value, dict):
        start_raw = value.get("start") or value.get("from")
        end_raw = value.get("end") or value.get("to")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        start_raw, end_raw = value
    else:
        return None, None
    start = _safe_parse_iso_datetime(str(start_raw)) if start_raw else None
    end = _safe_parse_iso_datetime(str(end_raw)) if end_raw else None
    return start, end


def _submission_item(path: Path) -> dict[str, Any]:
    payload = _load_submission_log(path)
    submitted_at = str(payload.get("ended_at") or payload.get("started_at") or "")
    rate_limit = _step_by_name(payload, "rate_limit")
    return {
        "submission_id": str(payload.get("run_id", path.parent.name)),
        "company": str(payload.get("company", payload.get("job_company", ""))),
        "position": str(payload.get("position", payload.get("job_title", ""))),
        "channel": str(payload.get("platform", path.parent.parent.name)),
        "mode": str(payload.get("mode", "")),
        "status": str(payload.get("status", "")),
        "error": str(payload.get("error", "")),
        "job_url": str(payload.get("job_url", "")),
        "submitted_at": submitted_at,
        "last_step": _last_step(payload),
        "rate_limit_status": rate_limit["status"],
        "rate_limit_detail": rate_limit["detail"],
    }


def _find_submission_log(submission_id: str) -> Path | None:
    for path in _submission_log_paths():
        payload = _load_submission_log(path)
        if str(payload.get("run_id", path.parent.name)) == submission_id:
            return path
    return None


def _detail_step(raw: object, run_dir: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "name": "",
            "status": "",
            "detail": "",
            "screenshot": "",
            "screenshot_path": "",
            "screenshot_exists": False,
        }
    screenshot = str(raw.get("screenshot", ""))
    screenshot_path = ""
    screenshot_exists = False
    if screenshot:
        candidate_raw_path = run_dir / screenshot
        candidate_path = candidate_raw_path.resolve()
        run_root = run_dir.resolve()
        if candidate_path.is_relative_to(run_root):
            screenshot_path = str(candidate_raw_path)
            screenshot_exists = candidate_path.exists()
    return {
        "name": str(raw.get("name", "")),
        "status": str(raw.get("status", "")),
        "detail": str(raw.get("detail", "")),
        "screenshot": screenshot,
        "screenshot_path": screenshot_path,
        "screenshot_exists": screenshot_exists,
    }


def handle_submission_detail(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    submission_id = str(params["submission_id"])
    log_path = _find_submission_log(submission_id)
    if log_path is None:
        raise KeyError(f"NOT_FOUND: {submission_id}")

    payload = _load_submission_log(log_path)
    run_dir = log_path.parent
    steps_raw = payload.get("steps", [])
    steps = (
        [_detail_step(step, run_dir) for step in steps_raw]
        if isinstance(steps_raw, list)
        else []
    )
    yaml_path = run_dir / "submission_log.yaml"
    return {
        "meta": {"correlation_id": correlation_id},
        "submission": {
            **_submission_item(log_path),
            "started_at": str(payload.get("started_at", "")),
            "ended_at": str(payload.get("ended_at", "")),
            "resume_path": str(payload.get("resume_path", "")),
            "profile_path": str(payload.get("profile_path", "")),
            "headless": bool(payload.get("headless", True)),
            "browser_channel": str(payload.get("browser_channel", "")),
            "steps": steps,
            "terminal_status": str(payload.get("terminal_status", payload.get("status", ""))),
            "resume_version_id": str(payload.get("resume_version_id", "")),
            "adapter_capabilities": payload.get("adapter_capabilities", {}),
            "original_job_lead": payload.get("original_job_lead", {}),
            "final_verified_target": payload.get("final_verified_target", {}),
            "session_metadata": payload.get("session_metadata", {}),
            "target_recovery_attempts": payload.get("target_recovery_attempts", []),
            "recovered_target_confirmation": payload.get("recovered_target_confirmation", {}),
            "resume_target_mismatch_warning": payload.get("resume_target_mismatch_warning", {}),
            "next_action": str(payload.get("next_action", "")),
            "final_submit_attempted": bool(payload.get("final_submit_attempted", False)),
            "external_submission_attempted": bool(payload.get("external_submission_attempted", False)),
            "log_json_path": str(log_path),
            "log_yaml_path": str(yaml_path) if yaml_path.exists() else "",
        },
    }


def handle_submission_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = params.get("sort") or {}
    filters = params.get("filters") or {}

    items = [_submission_item(path) for path in _submission_log_paths()]

    status_filter = str(filters.get("status") or "").strip()
    channel_filter = str(filters.get("channel") or "").strip()
    company_filter = str(filters.get("company") or "").strip()
    date_start, date_end = _parse_date_range(filters.get("date_range"))

    filtered: list[dict[str, Any]] = []
    for item in items:
        if status_filter and item["status"] != status_filter:
            continue
        if channel_filter and item["channel"] != channel_filter:
            continue
        if company_filter and item["company"] != company_filter:
            continue
        if date_start or date_end:
            submitted_at = _safe_parse_iso_datetime(str(item.get("submitted_at", "")))
            if submitted_at is None:
                continue
            if date_start and submitted_at < date_start:
                continue
            if date_end and submitted_at > date_end:
                continue
        filtered.append(item)

    sort_field = _parse_sort_field(sort.get("field"))
    sort_order = _parse_sort_order(sort.get("order"))
    reverse = sort_order != "asc"
    if sort_field == "status":
        filtered.sort(key=lambda item: item.get("status", ""), reverse=reverse)
    else:
        filtered.sort(
            key=lambda item: item.get("submitted_at", ""),
            reverse=reverse,
        )

    page = filtered[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(filtered) else None
    return {
        "meta": {"correlation_id": correlation_id},
        "items": page,
        "next_cursor": next_cursor,
    }


def handle_submission_retry(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    submission_id = str(params["submission_id"])
    strategy = str(params.get("strategy", "same_channel"))
    if strategy not in _ALLOWED_RETRY_STRATEGIES:
        raise ValueError(f"unsupported retry strategy: {strategy}")

    found = False
    retried_at = datetime.now(timezone.utc).isoformat()
    for path in _submission_log_paths():
        payload = _load_submission_log(path)
        if str(payload.get("run_id", path.parent.name)) == submission_id:
            payload["status"] = "queued"
            payload["retry_count"] = _parse_cursor(payload.get("retry_count")) + 1
            payload["retry_strategy"] = strategy
            payload["ended_at"] = retried_at
            payload["retried_at"] = retried_at
            _ = path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            found = True
            break
    if not found:
        raise KeyError(f"NOT_FOUND: {submission_id}")

    return {
        "meta": {"correlation_id": correlation_id},
        "submission_id": submission_id,
        "status": "queued",
    }


def handle_channel_session_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    _reject_forbidden_session_params(params)
    channel = _require_submission_channel(params)
    session = _read_session(channel)
    if session is None:
        checked_at = _now_iso()
        session = _session_payload(
            channel=channel,
            login_status="ready_to_setup",
            checked_at=checked_at,
            clear_available=False,
        )
    return _session_result(correlation_id, channel=channel, session=session)


def handle_channel_session_start(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    _reject_forbidden_session_params(params)
    channel = _require_submission_channel(params)
    checked_at = _now_iso()
    config = _SUPPORTED_SUBMISSION_CHANNELS[channel]
    steps = [
        {
            "name": "select_submission_channel",
            "status": "success",
            "detail": channel,
        },
        {
            "name": "open_channel_login_page",
            "status": "manual_boundary",
            "detail": config["login_url"],
        },
        {
            "name": "manual_login_required",
            "status": "waiting",
            "detail": "user_must_complete_sensitive_login_steps_manually",
        },
        {
            "name": "credential_entry",
            "status": "skipped",
            "detail": "browser_automation_must_not_enter_credentials",
        },
        {
            "name": "captcha_sms",
            "status": "skipped",
            "detail": "captcha_and_sms_bypass_forbidden",
        },
    ]
    log_path = _write_session_log(
        channel=channel,
        terminal_status="waiting_for_manual_login",
        steps=steps,
        checked_at=checked_at,
    )
    session = _session_payload(
        channel=channel,
        login_status="waiting_for_manual_login",
        checked_at=checked_at,
        clear_available=False,
        log_path=log_path,
    )
    _write_session(channel, session)
    return _session_result(
        correlation_id,
        channel=channel,
        session=session,
        steps=steps,
    )


def handle_channel_session_check(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    _reject_forbidden_session_params(params)
    channel = _require_submission_channel(params)
    checked_at = _now_iso()
    signals = params.get("login_signals")
    signals = signals if isinstance(signals, dict) else {}
    positive_key = _SUPPORTED_SUBMISSION_CHANNELS[channel]["positive_signal"]
    positive_signal = bool(signals.get(positive_key) or signals.get("authenticated_user_visible"))
    login_required = bool(signals.get("login_required") or signals.get("not_authenticated"))
    login_modal_absent = bool(signals.get("login_modal_absent"))

    steps = [
        {
            "name": "select_submission_channel",
            "status": "success",
            "detail": channel,
        },
        {
            "name": "login_state_check",
            "status": "running",
            "detail": "requires_positive_authenticated_signal",
        },
    ]
    if positive_signal:
        login_status = "session_valid"
        steps.append(
            {
                "name": "positive_login_signal",
                "status": "success",
                "detail": positive_key,
            }
        )
    elif login_required:
        login_status = "login_required"
        steps.append(
            {
                "name": "login_required",
                "status": "blocked",
                "detail": "authenticated_signal_absent",
            }
        )
    else:
        login_status = "session_unknown"
        detail = (
            "login_modal_absence_alone_not_sufficient"
            if login_modal_absent
            else "authenticated_signal_uncertain"
        )
        steps.append(
            {
                "name": "positive_login_signal",
                "status": "missing",
                "detail": detail,
            }
        )

    steps.extend(
        [
            {
                "name": "credential_entry",
                "status": "skipped",
                "detail": "browser_automation_did_not_enter_credentials",
            },
            {
                "name": "captcha_sms",
                "status": "skipped",
                "detail": "browser_automation_did_not_enter_captcha_or_sms",
            },
        ]
    )

    if login_status == "session_valid":
        _channel_profile_path(channel).mkdir(parents=True, exist_ok=True)
    log_path = _write_session_log(
        channel=channel,
        terminal_status=login_status,
        steps=steps,
        checked_at=checked_at,
    )
    previous = _read_session(channel) or {}
    session = _session_payload(
        channel=channel,
        login_status=login_status,
        checked_at=checked_at,
        account_identity=_safe_account_identity(params),
        session_id=str(previous.get("session_id") or ""),
        clear_available=login_status == "session_valid",
        log_path=log_path,
    )
    _write_session(channel, session)
    return _session_result(
        correlation_id,
        channel=channel,
        session=session,
        steps=steps,
    )


def handle_channel_session_clear(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    _reject_forbidden_session_params(params)
    channel = _require_submission_channel(params)
    checked_at = _now_iso()
    profile_path = _channel_profile_path(channel)
    if profile_path.exists():
        shutil.rmtree(profile_path)
    steps = [
        {
            "name": "select_submission_channel",
            "status": "success",
            "detail": channel,
        },
        {
            "name": "clear_selected_channel_session",
            "status": "success",
            "detail": "selected_channel_only",
        },
    ]
    log_path = _write_session_log(
        channel=channel,
        terminal_status="session_cleared",
        steps=steps,
        checked_at=checked_at,
    )
    previous = _read_session(channel) or {}
    session = _session_payload(
        channel=channel,
        login_status="session_cleared",
        checked_at=checked_at,
        account_identity=previous.get("account_identity"),
        session_id=str(previous.get("session_id") or ""),
        clear_available=False,
        log_path=log_path,
    )
    _write_session(channel, session)
    return _session_result(
        correlation_id,
        channel=channel,
        session=session,
        steps=steps,
    )


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
        "supported_actions": sorted(_ALLOWED_ITERATION_ACTIONS),
    }


def handle_feedback_create_iteration(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    source_run_id = str(params.get("source_run_id") or "").strip()
    log_path = _resolve_submission_log_or_raise(source_run_id)
    source_payload = _load_submission_log(log_path)
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
