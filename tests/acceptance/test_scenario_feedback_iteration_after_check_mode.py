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
    handle_feedback_create_iteration,
    handle_feedback_list,
    handle_submission_check_mode,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def _write_inputs(project_root: Path) -> tuple[Path, Path, Path, Path]:
    leads_dir = project_root / "job_leads"
    leads_dir.mkdir(parents=True)
    (leads_dir / "jl_feedback_acceptance.yaml").write_text(
        "\n".join(
            [
                'id: "jl_feedback_acceptance"',
                'channel: "liepin"',
                'company: "Feedback Acceptance"',
                'position: "Backend Engineer"',
                'job_url: "https://www.liepin.com/job/feedback.shtml"',
                'job_id: "feedback"',
                'recruiter: "Feedback Recruiter"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    resume_path = project_root / "outputs" / "quick_runs" / "feedback" / "exports" / "resume.pdf"
    resume_path.parent.mkdir(parents=True)
    resume_path.write_bytes(b"%PDF-1.4\nfeedback\n")
    return (
        leads_dir,
        resume_path,
        project_root / "outputs" / "submissions",
        project_root / "outputs" / "feedback_iterations",
    )


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


def test_feedback_iteration_after_check_mode_l1_acceptance_writes_report(
    tmp_path: Path,
) -> None:
    leads_dir, resume_path, submissions_dir, iterations_dir = _write_inputs(tmp_path)
    sessions_dir = tmp_path / "outputs" / "channel_sessions"
    previous_resume_bytes = resume_path.read_bytes()
    with (
        patch("tools.sidecar.handlers.submission._JOB_LEAD_DIR", leads_dir),
        patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
        patch("tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR", sessions_dir),
        patch("tools.sidecar.handlers.submission._FEEDBACK_ITERATIONS_DIR", iterations_dir),
        patch(
            "tools.sidecar.handlers.submission._build_submission_check_id",
            return_value="sc_feedback_acceptance",
        ),
        patch(
            "tools.sidecar.handlers.submission._build_feedback_iteration_id",
            return_value="fi_feedback_acceptance",
        ),
    ):
        handle_channel_session_check(
            {
                "meta": {"correlation_id": "corr_session"},
                "channel": "liepin",
                "login_signals": {
                    "logged_in_user_ui_or_equivalent_authenticated_signal": True
                },
            }
        )
        check_mode = handle_submission_check_mode(
            {
                "meta": {"correlation_id": "corr_check"},
                "channel": "liepin",
                "job_lead_id": "jl_feedback_acceptance",
                "resume_version_id": "rv_feedback_acceptance",
                "resume_pdf_path": str(resume_path),
                "preflight_confirmed": True,
                "confirmed_no_real_submit": True,
                "options": {
                    "confirmation_items": _confirmation_items(),
                    "session_identity_accepted": True,
                },
            }
        )
        feedback = handle_feedback_list(
            {
                "meta": {"correlation_id": "corr_feedback"},
                "source_run_id": "sc_feedback_acceptance",
            }
        )
        missing_action_rejected = False
        try:
            handle_feedback_create_iteration(
                {
                    "meta": {"correlation_id": "corr_missing_action"},
                    "source_run_id": "sc_feedback_acceptance",
                    "source_feedback_items": feedback["items"],
                    "selected_actions": [],
                }
            )
        except ValueError as exc:
            missing_action_rejected = "feedback_action_required" in str(exc)
        unsupported_source_rejected = False
        try:
            handle_feedback_create_iteration(
                {
                    "meta": {"correlation_id": "corr_bad_source"},
                    "source_run_id": "sc_feedback_acceptance",
                    "source_feedback_items": [
                        {
                            "source_type": "unsupported_feedback",
                            "source_run_id": "sc_feedback_acceptance",
                            "source_artifact_path_or_id": "x",
                            "summary": "x",
                            "severity_or_priority": "high",
                            "recommended_next_action": "x",
                        }
                    ],
                    "selected_actions": ["acknowledge_and_skip"],
                    "user_notes": "skip",
                }
            )
        except ValueError as exc:
            unsupported_source_rejected = "unsupported_feedback_source" in str(exc)
        iteration = handle_feedback_create_iteration(
            {
                "meta": {"correlation_id": "corr_iteration"},
                "source_run_id": "sc_feedback_acceptance",
                "source_feedback_items": feedback["items"],
                "selected_actions": [
                    "regenerate_resume_from_existing_evidence",
                    "prepare_next_check_mode",
                ],
                "user_notes": "Regenerate from reviewed feedback.",
                "evidence_card_ids_added_or_updated": ["ec_feedback_acceptance"],
                "new_or_updated_claims": ["Evidence-linked retained claim"],
                "remaining_gap_tasks": ["Confirm channel messaging fit"],
            }
        )
        record = json.loads(Path(iteration["record_path"]).read_text(encoding="utf-8"))
        source_snapshot_exists = Path(record["source_snapshot_path"]).exists()
        new_resume_exists = Path(record["affected_artifacts"]["new_resume_path"]).exists()
        previous_resume_after = resume_path.read_bytes()

    assert check_mode["status"] == "check_mode_success_submit_skipped"
    assert len(feedback["items"]) >= 1
    assert missing_action_rejected is True
    assert unsupported_source_rejected is True
    assert iteration["status"] == "iteration_recorded"
    assert record["source_run_id"] == "sc_feedback_acceptance"
    assert record["source_feedback_items"][0]["source_run_id"] == "sc_feedback_acceptance"
    assert "regenerate_resume_from_existing_evidence" in record["selected_actions"]
    assert record["previous_resume_version_id"] == "rv_feedback_acceptance"
    assert record["new_resume_version_id_or_none"]
    assert previous_resume_after == previous_resume_bytes
    assert source_snapshot_exists is True
    assert new_resume_exists is True
    assert record["previous_artifacts_preserved"] is True
    assert record["immutable_source_snapshot"] is True
    assert record["comparison_summary"]["evidence_ids_used"] == ["ec_feedback_acceptance"]
    assert record["comparison_summary"]["new_or_updated_claims"][0]["evidence_ids"] == [
        "ec_feedback_acceptance"
    ]
    assert record["remaining_gap_tasks"] == ["Confirm channel messaging fit"]
    assert record["next_check_mode_candidate"]["resume_version_id"] == record[
        "new_resume_version_id_or_none"
    ]
    assert record["next_check_mode_candidate"]["real_submit_disabled"] is True

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="feedback_iteration_after_check_mode_l1",
        generated_at="2026-05-22T00:00:00Z",
        results={
            "feedback_iteration_preserves_traceability": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Feedback iteration lists check-mode feedback, requires a user "
                    "action, preserves source snapshots and previous resume artifacts, "
                    "creates a new resume version with evidence-linked comparison, "
                    "and prepares a no-submit next check-mode candidate."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "feedback_iteration_preserves_traceability" in markdown_path.read_text(
        encoding="utf-8"
    )
