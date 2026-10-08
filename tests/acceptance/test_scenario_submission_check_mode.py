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
    handle_submission_check_mode,
    handle_submission_detail,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def _write_job_lead(project_root: Path) -> Path:
    leads_dir = project_root / "job_leads"
    leads_dir.mkdir(parents=True)
    (leads_dir / "jl_submission_acceptance.yaml").write_text(
        "\n".join(
            [
                'id: "jl_submission_acceptance"',
                'channel: "liepin"',
                'company: "Submission Acceptance"',
                'position: "Backend Engineer"',
                'job_url: "https://www.liepin.com/job/456.shtml"',
                'job_id: "456"',
                'recruiter: "Acceptance Recruiter"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return leads_dir


def _write_resume_pdf(project_root: Path) -> Path:
    path = project_root / "outputs" / "quick_runs" / "acceptance" / "exports" / "resume.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-1.4\nacceptance\n")
    return path


def _confirmation_items() -> list[str]:
    return [
        "check_mode_no_real_submit",
        "selected_submission_channel",
        "selected_channel_job_lead",
        "selected_resume_pdf",
        "selected_channel_session_metadata",
        "may_use_channel_shared_session",
        "final_confirm_disabled_and_forbidden",
        "must_stop_before_final_confirm",
    ]


def test_submission_check_mode_l1_acceptance_writes_report(tmp_path: Path) -> None:
    leads_dir = _write_job_lead(tmp_path)
    resume_path = _write_resume_pdf(tmp_path)
    submissions_dir = tmp_path / "outputs" / "submissions"
    sessions_dir = tmp_path / "outputs" / "channel_sessions"
    with (
        patch("tools.sidecar.handlers.submission._session_browser.check", return_value={"login_signals": {"authenticated_user_visible": True}}),
        patch("tools.sidecar.handlers.submission._JOB_LEAD_DIR", leads_dir),
        patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
        patch("tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR", sessions_dir),
        patch(
            "tools.sidecar.handlers.submission._build_submission_check_id",
            return_value="sc_submission_acceptance",
        ),
    ):
        missing_preflight_rejected = False
        try:
            handle_submission_check_mode(
                {
                    "meta": {"correlation_id": "corr_missing_preflight"},
                    "channel": "liepin",
                    "job_lead_id": "jl_submission_acceptance",
                    "resume_version_id": "rv_submission_acceptance",
                    "resume_pdf_path": str(resume_path),
                }
            )
        except ValueError as exc:
            missing_preflight_rejected = "preflight_confirmation_required" in str(exc)

        missing_session = handle_submission_check_mode(
            {
                "meta": {"correlation_id": "corr_missing_session"},
                "channel": "liepin",
                "job_lead_id": "jl_submission_acceptance",
                "resume_version_id": "rv_submission_acceptance",
                "resume_pdf_path": str(resume_path),
                "preflight_confirmed": True,
                "confirmed_no_real_submit": True,
                "options": {"confirmation_items": _confirmation_items()},
            }
        )

        handle_channel_session_check(
            {
                "meta": {"correlation_id": "corr_session"},
                "channel": "liepin",
                "login_signals": {
                    "logged_in_user_ui_or_equivalent_authenticated_signal": True
                },
                "account_identity": {
                    "display_name_or_nickname": "Acceptance Account",
                    "masked_phone_or_email_suffix": "13800123456",
                },
            }
        )
        identity_rejected = handle_submission_check_mode(
            {
                "meta": {"correlation_id": "corr_identity"},
                "channel": "liepin",
                "job_lead_id": "jl_submission_acceptance",
                "resume_version_id": "rv_submission_acceptance",
                "resume_pdf_path": str(resume_path),
                "preflight_confirmed": True,
                "confirmed_no_real_submit": True,
                "options": {
                    "confirmation_items": _confirmation_items(),
                    "session_identity_accepted": False,
                },
            }
        )
        result = handle_submission_check_mode(
            {
                "meta": {"correlation_id": "corr_check"},
                "channel": "liepin",
                "job_lead_id": "jl_submission_acceptance",
                "resume_version_id": "rv_submission_acceptance",
                "resume_pdf_path": str(resume_path),
                "preflight_confirmed": True,
                "confirmed_no_real_submit": True,
                "options": {
                    "confirmation_items": _confirmation_items(),
                    "target_recovery_limit": 2,
                    "session_identity_accepted": True,
                },
            }
        )
        detail = handle_submission_detail(
            {
                "meta": {"correlation_id": "corr_detail"},
                "submission_id": "sc_submission_acceptance",
            }
        )

    assert missing_preflight_rejected is True
    assert missing_session["status"] == "login_required"
    assert identity_rejected["status"] == "account_identity_mismatch"
    assert identity_rejected["next_action"] == "go_to_channel_session_setup_to_clear_or_refresh"
    assert result["status"] == "check_mode_success_submit_skipped"
    assert result["mode"] == "check"
    assert result["channel"] == "liepin"
    assert result["session_metadata"]["login_status"] == "session_valid"
    assert result["original_job_lead"]["job_lead_id"] == "jl_submission_acceptance"
    assert result["final_verified_target"]["job_url"] == "https://www.liepin.com/job/456.shtml"
    assert result["submit_enabled"] is False
    assert result["final_submit_attempted"] is False
    assert result["external_submission_attempted"] is False
    assert "liepin" in result["adapter_capabilities"]["adapter"]
    step_names = [step["name"] for step in result["steps"]]
    for required in [
        "rate_limit",
        "open_target",
        "login_check",
        "target_verify",
        "send_resume_path_check",
        "attachment_check",
        "submit_skipped",
    ]:
        assert required in step_names
    assert Path(result["log_json_path"]).exists()
    assert Path(result["log_yaml_path"]).exists()
    log_payload = json.loads(Path(result["log_json_path"]).read_text(encoding="utf-8"))
    assert log_payload["preflight_confirmation"]["confirmed_no_real_submit"] is True
    assert log_payload["terminal_status"] == "check_mode_success_submit_skipped"
    assert log_payload["final_submit_attempted"] is False
    assert detail["submission"]["terminal_status"] == "check_mode_success_submit_skipped"
    assert detail["submission"]["original_job_lead"]["job_lead_id"] == "jl_submission_acceptance"

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="submission_check_mode_l1",
        generated_at="2026-05-22T00:00:00Z",
        results={
            "check_mode_never_final_submits": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Submission check mode requires preflight confirmation, channel "
                    "job lead, resume PDF, usable shared session, and records rate "
                    "limit, login, target verification, attachment status, and "
                    "submit_skipped without attempting final submit."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "check_mode_never_final_submits" in markdown_path.read_text(encoding="utf-8")
