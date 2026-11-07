"""渠道登录会话 handler。

从 ``submission.py`` 拆出；渠道目录、会话日志路径等仍由原模块提供，
浏览器会话对象经原模块运行时读取，保证测试 patch ``submission._session_browser`` 生效。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from tools.sidecar.handlers import submission as _origin
from tools.sidecar.handlers.submission import (
    _FORBIDDEN_SESSION_PARAM_KEYS,
    _SUPPORTED_SUBMISSION_CHANNELS,
    _now_iso,
    _channel_log_path,
    _channel_profile_path,
    _channel_session_path,
)


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
    session = json.loads(path.read_text(encoding="utf-8"))
    if session.get("login_status") == "session_valid" and session.get("verification_source") != "owned_playwright":
        session["login_status"] = "session_unknown"
    return session


def _record_browser_failure(channel: str, checked_at: str, error: Exception) -> None:
    log_path = _write_session_log(channel=channel, terminal_status="session_unknown", checked_at=checked_at,
        steps=[{"name": "browser_operation", "status": "failed", "detail": str(error)}])
    _write_session(channel, _session_payload(channel=channel, login_status="session_unknown", checked_at=checked_at,
        clear_available=_channel_profile_path(channel).is_dir(), log_path=log_path))


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
            "opened_login_page": any(step.get("name") == "open_channel_login_page" and step.get("status") == "success" for step in (steps or [])),
            "entered_credentials": False,
            "entered_captcha_or_sms": False,
            "captcha_sms_bypass_attempted": False,
        },
        "artifact_paths": {
            "channel_session": str(_channel_session_path(channel)),
            "session_check_log": session.get("log_path", str(_channel_log_path(channel))),
        },
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
    try:
        already_logged_in = _origin._session_browser.start(_channel_profile_path(channel), config["login_url"])
    except (RuntimeError, OSError) as exc:
        _record_browser_failure(channel, checked_at, exc)
        raise
    if already_logged_in is True:
        return handle_channel_session_check(params)
    steps = [
        {
            "name": "select_submission_channel",
            "status": "success",
            "detail": channel,
        },
        {
            "name": "open_channel_login_page",
            "status": "success",
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
    try:
        observation = _origin._session_browser.check(_channel_profile_path(channel))
    except (RuntimeError, OSError) as exc:
        _record_browser_failure(channel, checked_at, exc)
        raise
    signals = observation.get("login_signals")
    signals = signals if isinstance(signals, dict) else {}
    positive_key = _SUPPORTED_SUBMISSION_CHANNELS[channel]["positive_signal"]
    login_required = bool(signals.get("login_required") or signals.get("not_authenticated"))
    positive_signal = not login_required and bool(signals.get(positive_key) or signals.get("authenticated_user_visible"))
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
        account_identity=_safe_account_identity(observation),
        session_id=str(previous.get("session_id") or ""),
        clear_available=login_status == "session_valid",
        log_path=log_path,
    )
    session["verification_source"] = "owned_playwright"
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
    _origin._session_browser.close()
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
