from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_journey_report,
    write_journey_report,
)
from tools.sidecar.handlers.submission import (
    handle_channel_session_check,
    handle_channel_session_clear,
    handle_channel_session_get,
    handle_channel_session_start,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def test_channel_session_setup_l1_acceptance_writes_report(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "outputs" / "channel_sessions"
    with patch(
        "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
        sessions_dir,
    ):
        missing_channel_rejected = False
        try:
            handle_channel_session_get({"meta": {"correlation_id": "corr_missing"}})
        except ValueError as exc:
            missing_channel_rejected = "channel_required" in str(exc)

        unsupported_channel_rejected = False
        try:
            handle_channel_session_get(
                {"meta": {"correlation_id": "corr_unsupported"}, "channel": "boss"}
            )
        except ValueError as exc:
            unsupported_channel_rejected = "unsupported_submission_channel" in str(exc)

        credentials_rejected = False
        try:
            handle_channel_session_start(
                {
                    "meta": {"correlation_id": "corr_credentials"},
                    "channel": "liepin",
                    "credentials": {"password": "secret"},
                }
            )
        except ValueError as exc:
            credentials_rejected = "credentials_or_challenge_input_forbidden" in str(
                exc
            )

        captcha_rejected = False
        try:
            handle_channel_session_check(
                {
                    "meta": {"correlation_id": "corr_captcha"},
                    "channel": "liepin",
                    "captcha_code": "123456",
                }
            )
        except ValueError as exc:
            captcha_rejected = "credentials_or_challenge_input_forbidden" in str(exc)

        start = handle_channel_session_start(
            {"meta": {"correlation_id": "corr_start"}, "channel": "liepin"}
        )
        unknown = handle_channel_session_check(
            {
                "meta": {"correlation_id": "corr_unknown"},
                "channel": "liepin",
                "login_signals": {"login_modal_absent": True},
            }
        )
        login_required = handle_channel_session_check(
            {
                "meta": {"correlation_id": "corr_login_required"},
                "channel": "liepin",
                "login_signals": {"login_required": True},
            }
        )
        valid = handle_channel_session_check(
            {
                "meta": {"correlation_id": "corr_valid"},
                "channel": "liepin",
                "login_signals": {
                    "logged_in_user_ui_or_equivalent_authenticated_signal": True
                },
                "account_identity": {
                    "display_name_or_nickname": "Verifier",
                    "masked_phone_or_email_suffix": "13800123456",
                    "avatar_presence": True,
                },
            }
        )
        other_channel_profile = sessions_dir / "future_channel" / "browser_profile"
        other_channel_profile.mkdir(parents=True)
        cleared = handle_channel_session_clear(
            {"meta": {"correlation_id": "corr_clear"}, "channel": "liepin"}
        )
        fetched_after_clear = handle_channel_session_get(
            {"meta": {"correlation_id": "corr_fetch"}, "channel": "liepin"}
        )

    assert missing_channel_rejected is True
    assert unsupported_channel_rejected is True
    assert credentials_rejected is True
    assert captcha_rejected is True
    assert [channel["channel"] for channel in start["supported_channels"]] == ["liepin"]
    assert start["session"]["login_status"] == "waiting_for_manual_login"
    assert start["manual_login_required"] is True
    assert start["browser_automation"]["entered_credentials"] is False
    assert start["browser_automation"]["entered_captcha_or_sms"] is False
    assert start["browser_automation"]["captcha_sms_bypass_attempted"] is False
    assert "liepin" in start["session"]["adapter"]
    assert unknown["session"]["login_status"] == "session_unknown"
    assert unknown["session"]["clear_available"] is False
    assert login_required["session"]["login_status"] == "login_required"
    assert valid["session"]["login_status"] == "session_valid"
    assert valid["session"]["clear_available"] is True
    assert valid["session"]["session_path"]
    assert valid["session"]["account_identity"]["display_name_or_nickname"] == "Verifier"
    assert valid["session"]["account_identity"]["masked_phone_or_email_suffix"] == "***3456"
    assert cleared["session"]["login_status"] == "session_cleared"
    assert fetched_after_clear["session"]["login_status"] == "session_cleared"
    assert fetched_after_clear["session"]["clear_available"] is False
    assert other_channel_profile.exists()

    session_path = Path(cleared["artifact_paths"]["channel_session"])
    log_path = Path(cleared["artifact_paths"]["session_check_log"])
    assert session_path.exists()
    assert log_path.exists()
    session_payload = json.loads(session_path.read_text(encoding="utf-8"))
    log_payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert session_payload["channel"] == "liepin"
    assert session_payload["login_status"] == "session_cleared"
    assert "liepin" in session_payload["adapter"]
    assert log_payload["channel"] == "liepin"
    assert log_payload["terminal_status"] == "session_cleared"
    assert log_payload["adapter"]["liepin"]["credential_entry_attempted"] is False
    assert log_payload["adapter"]["liepin"]["captcha_sms_bypass_attempted"] is False

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="channel_session_setup_l1",
        generated_at="2026-05-22T00:00:00Z",
        results={
            "channel_session_validity_is_positive_signal_based": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Channel session setup requires channel selection, rejects "
                    "unsupported channels and credential/challenge inputs, records "
                    "manual-login boundary steps, requires a positive login signal "
                    "for session_valid, masks safe account identity, and clears only "
                    "the selected channel session."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "channel_session_validity_is_positive_signal_based" in markdown_path.read_text(
        encoding="utf-8"
    )
