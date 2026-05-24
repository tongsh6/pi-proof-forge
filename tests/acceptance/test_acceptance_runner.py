from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from tools.acceptance.acceptance_runner import (
    build_run_id,
    run_acceptance,
    write_acceptance_report,
)
from tools.acceptance.external_l3 import submission_log_error_blocker_reason


def _external_l3_session_dir(root: Path) -> Path:
    session_dir = root / ".sessions"
    channel_session_dir = session_dir / "liepin" / "session" / "liepin"
    channel_session_dir.mkdir(parents=True, exist_ok=True)
    (channel_session_dir / "storage-state.json").write_text("{}", encoding="utf-8")
    return session_dir


def test_acceptance_runner_defaults_to_l1(tmp_path: Path) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="l1 ok", stderr="")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert report.levels == ("L1",)
    assert [step.level for step in report.steps] == [
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
    ]
    assert [step.name for step in report.steps] == [
        "first_launch_configure_lm_studio",
        "setup_profile_and_material_library",
        "generate_review_and_complete_evidence_card",
        "setup_job_target",
        "quick_run_generate_and_evaluate_resume",
        "agent_run_guided_batch",
        "channel_session_setup",
        "submission_check_mode",
        "feedback_iteration_after_check_mode",
        "closed_loop_e2e_audit",
    ]
    assert run_mock.call_count == 9
    assert run_mock.call_args_list[0].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_first_launch_configure_lm_studio.py",
        "-q",
    ]
    assert run_mock.call_args_list[1].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_setup_profile_and_material_library.py",
        "-q",
    ]
    assert run_mock.call_args_list[2].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_generate_review_and_complete_evidence_card.py",
        "-q",
    ]
    assert run_mock.call_args_list[3].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_setup_job_target.py",
        "-q",
    ]
    assert run_mock.call_args_list[4].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py",
        "-q",
    ]
    assert run_mock.call_args_list[5].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_agent_run_guided_batch.py",
        "-q",
    ]
    assert run_mock.call_args_list[6].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_channel_session_setup.py",
        "-q",
    ]
    assert run_mock.call_args_list[7].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_submission_check_mode.py",
        "-q",
    ]
    assert run_mock.call_args_list[8].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_feedback_iteration_after_check_mode.py",
        "-q",
    ]


def test_acceptance_runner_all_includes_l2_gate_and_l3_blocker_record(
    tmp_path: Path,
) -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(returncode=0, stdout="l1 ok", stderr="")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1", "L2", "L3"),
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert [step.level for step in report.steps] == [
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L2",
        "L3",
    ]
    assert [step.status for step in report.steps] == [
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "not_started",
        "not_started",
        "pass",
    ]
    assert run_mock.call_count == 9


def test_acceptance_runner_level_without_implementation_is_not_started(
    tmp_path: Path,
) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L2",),
            timeout_seconds=10,
        )

    assert report.status == "not_started"
    assert report.steps[0].level == "L2"
    assert report.steps[0].status == "not_started"
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_records_authorization_blocker(tmp_path: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert report.steps[0].level == "L3"
    assert report.steps[0].name == "external_l3_submission_validation"
    assert report.steps[0].status == "pass"
    assert "explicit_user_authorization_required" in report.steps[0].message

    evidence_path = Path(report.steps[0].evidence)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "explicit_user_authorization_required"
    assert "user_authorization" in payload["live_blocker"]["failed_checks"]
    assert (
        payload["live_blocker"]["diagnostics"]["submit_command_allowed"]
        is False
    )
    assert "job_url_present" in payload["live_blocker"]["diagnostics"]["missing_gates"]
    assert isinstance(
        payload["live_blocker"]["diagnostics"]["readiness_gates"],
        list,
    )
    assert (
        payload["live_blocker"]["diagnostics"]["live_input_artifacts"]["job_url"][
            "raw_value_persisted"
        ]
        is False
    )
    assert payload["coverage"]["user_authorized_external_session"] == "blocked_recorded"
    assert payload["coverage"]["post_submit_feedback_traceability"] == "pass"
    assert payload["coverage"]["no_secret_or_captcha_bypass"] == "pass"
    assert payload["rate_limit_policy"]["enabled"] is True
    assert payload["rate_limit_policy"]["max_per_batch"] == 5
    assert payload["rate_limit_policy"]["cooldown_seconds"] == 900
    assert payload["rate_limit_policy"]["daily_limit"] == 30
    assert payload["rate_limit_policy"]["state_path"].endswith(
        "outputs/submissions/liepin_rate_limit.json"
    )
    forbidden_audit = payload["forbidden_input_audit"]
    assert forbidden_audit["forbidden_inputs_present"] is False
    assert forbidden_audit["raw_values_persisted"] is False
    assert {
        item["name"] for item in forbidden_audit["inputs"]
    } == {"password", "captcha_code", "sms_code", "raw_api_key"}
    assert all(item["raw_value_persisted"] is False for item in forbidden_audit["inputs"])
    target_audit = payload["target_confirmation_audit"]
    assert target_audit["job_url_has_parseable_job_id"] is False
    assert target_audit["confirm_submit_job_id_present"] is False
    assert target_audit["confirm_submit_recruiter_present"] is False
    assert target_audit["job_id_matches_confirmation"] is False
    assert target_audit["recruiter_page_match_requires_target_verify"] is True
    assert target_audit["raw_values_persisted"] is False
    assert target_audit["raw_recruiter_value_persisted"] is False
    input_artifacts = payload["live_input_artifacts"]
    assert input_artifacts["job_url"]["present"] is False
    assert input_artifacts["job_url"]["raw_value_persisted"] is False
    assert input_artifacts["confirmations"]["raw_values_persisted"] is False
    assert all(
        item["raw_content_persisted"] is False
        for item in input_artifacts["files"]
    )
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "blocked_before_command"
    assert submit_decision["submit_command_allowed"] is False
    assert submit_decision["external_submission_attempted"] is False
    assert submit_decision["authorization_confirmed"] is False
    assert submit_decision["final_submit_confirmed"] is False
    assert submit_decision["requires_explicit_user_authorization"] is True
    assert submit_decision["requires_separate_final_submit_confirmation"] is True
    assert submit_decision["credentials_or_challenge_inputs_accepted"] is False
    assert submit_decision["forbidden_inputs_present"] is False
    assert submit_decision["blocking_reason"] == "explicit_user_authorization_required"
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["traceable"] is True
    assert feedback_trace["source_type"] == "live_blocker"
    assert feedback_trace["source_status"] == "pre_submit_blocked"
    assert feedback_trace["source_reason"] == "explicit_user_authorization_required"
    assert (
        feedback_trace["feedback_iteration_route"]
        == "resolve_live_blocker_before_feedback_iteration"
    )
    outcome_summary = payload["outcome_summary"]
    assert outcome_summary["outcome"] == "pre_submit_blocker_recorded"
    assert (
        outcome_summary["acceptance_status_meaning"]
        == "pre_submit_blocker_evidence_recorded"
    )
    assert outcome_summary["external_l3_success"] is False
    assert outcome_summary["external_submission_attempted"] is False
    assert outcome_summary["blocker_resolution_required"] is True
    assert outcome_summary["blocker_reason"] == "explicit_user_authorization_required"
    assert outcome_summary["p0_017_complete"] is False
    completion_gate = payload["p0_017_completion_gate"]
    assert completion_gate["status"] == "incomplete_pre_submit_blocker"
    assert completion_gate["p0_017_complete"] is False
    assert completion_gate["acceptance_pass_is_completion"] is False
    assert completion_gate["external_l3_success"] is False
    assert completion_gate["external_submission_attempted"] is False
    assert "explicit_user_authorization" in completion_gate["completion_blockers"]
    assert "external_submission_attempted" in completion_gate["completion_blockers"]
    assert "outcome_external_validated" in completion_gate["completion_blockers"]
    assert completion_gate["raw_live_inputs_persisted"] is False
    completion_items = {
        item["id"]: item for item in completion_gate["required_evidence"]
    }
    assert completion_items["explicit_user_authorization"]["status"] == "missing"
    assert (
        completion_items["explicit_user_authorization"]["source_path"]
        == "live_run_readiness.gates.user_authorization"
    )
    assert (
        completion_items["post_submit_feedback_traceability"]["status"]
        == "satisfied"
    )
    assert completion_items["outcome_external_validated"]["status"] == "missing"
    assert all(
        item["required"] is True and item["raw_live_inputs_persisted"] is False
        for item in completion_gate["required_evidence"]
    )
    evidence_manifest = payload["evidence_manifest"]
    assert evidence_manifest["status"] == "complete"
    assert evidence_manifest["raw_live_inputs_persisted"] is False
    evidence_entries = {
        item["id"]: item for item in evidence_manifest["entries"]
    }
    assert evidence_entries["external_l3_validation_json"]["present"] is True
    assert evidence_entries["external_l3_validation_markdown"]["present"] is True
    assert evidence_entries["live_run_readiness"]["present"] is True
    assert evidence_entries["operator_handoff"]["present"] is True
    assert evidence_entries["p0_017_completion_gate"]["required"] is True
    assert evidence_entries["p0_017_completion_gate"]["present"] is True
    assert (
        evidence_entries["p0_017_completion_gate"]["status"]
        == "incomplete_pre_submit_blocker"
    )
    assert evidence_entries["external_l3_live_run_runbook"]["required"] is True
    assert evidence_entries["external_l3_live_run_runbook"]["present"] is True
    assert (
        evidence_entries["external_l3_live_run_runbook"]["status"]
        == "fingerprinted_and_sections_complete"
    )
    assert (
        evidence_entries["external_l3_live_run_runbook"]["location"]
        == "docs/runbooks/external-l3-live-run.md"
    )
    assert evidence_entries["preflight_review_checklist"]["required"] is True
    assert evidence_entries["preflight_review_checklist"]["present"] is True
    assert (
        evidence_entries["preflight_review_checklist"]["status"]
        == "operator_review_required_before_authorized_template"
    )
    assert evidence_entries["preflight_review_result"]["required"] is True
    assert evidence_entries["preflight_review_result"]["present"] is True
    assert (
        evidence_entries["preflight_review_result"]["status"]
        == "preflight_evidence_review_passed_with_live_readiness_blockers"
    )
    assert evidence_entries["authorization_readiness_action_plan"]["required"] is True
    assert evidence_entries["authorization_readiness_action_plan"]["present"] is True
    assert (
        evidence_entries["authorization_readiness_action_plan"]["status"]
        == "blocked_until_live_inputs_and_session_ready"
    )
    assert evidence_entries["authorization_intake_checklist"]["required"] is True
    assert evidence_entries["authorization_intake_checklist"]["present"] is True
    assert (
        evidence_entries["authorization_intake_checklist"]["status"]
        == "blocked_until_authorization_intake_complete"
    )
    assert evidence_entries["authorized_template_release_decision"]["required"] is True
    assert evidence_entries["authorized_template_release_decision"]["present"] is True
    assert (
        evidence_entries["authorized_template_release_decision"]["status"]
        == "withheld_until_authorization_readiness"
    )
    assert evidence_entries["live_run_go_no_go_decision"]["required"] is True
    assert evidence_entries["live_run_go_no_go_decision"]["present"] is True
    assert (
        evidence_entries["live_run_go_no_go_decision"]["status"]
        == "no_go_until_authorized_template_released"
    )
    assert evidence_entries["live_run_execution_sequence"]["required"] is True
    assert evidence_entries["live_run_execution_sequence"]["present"] is True
    assert (
        evidence_entries["live_run_execution_sequence"]["status"]
        == "blocked_before_authorized_template_execution"
    )
    assert evidence_entries["post_submit_feedback_traceability"]["present"] is True
    assert evidence_entries["live_blocker"]["required"] is True
    assert evidence_entries["live_blocker"]["present"] is True
    assert evidence_entries["submission_log_yaml"]["required"] is False
    assert evidence_entries["submission_log_yaml"]["present"] is False
    assert evidence_entries["feedback_source_artifact"]["present"] is True
    assert all(
        item["raw_live_inputs_persisted"] is False
        for item in evidence_manifest["entries"]
    )
    readiness = payload["live_run_readiness"]
    assert readiness["ready"] is False
    assert readiness["submit_command_allowed"] is False
    assert readiness["blocking_reason"] == "explicit_user_authorization_required"
    assert "user_authorization" in readiness["missing_gates"]
    assert "manual_session_ready_confirmed" in readiness["missing_gates"]
    assert "job_url_present" in readiness["missing_gates"]
    assert "job_url_valid" in readiness["missing_gates"]
    assert "resume_pdf_file_ready" in readiness["missing_gates"]
    assert "profile_yaml_file_ready" in readiness["missing_gates"]
    handoff = payload["operator_handoff"]
    assert handoff["status"] == "blocked_until_operator_action"
    assert "显式授权" in handoff["next_action"]
    assert "password" in handoff["forbidden_inputs"]
    assert "captcha_code" in handoff["forbidden_inputs"]
    assert handoff["session_readiness"]["session_ready_confirmed"] is False
    assert handoff["session_readiness"]["manual_login_required"] is True
    assert handoff["session_readiness"]["browser_automation_enters_credentials"] is False
    assert handoff["runtime_options"] == {
        "channel": "liepin",
        "session_dir": ".sessions",
        "output_dir": "outputs/submissions",
        "timeout_seconds": 10,
        "timeout_ms": 45000,
        "headless": False,
    }
    assert "PIPF_EXTERNAL_L3_CHANNEL=liepin" in handoff["command_template"]
    assert (
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true"
        in handoff["command_template"]
    )
    assert "PIPF_EXTERNAL_L3_JOB_URL='<https-url>'" in handoff["command_template"]
    assert "PIPF_EXTERNAL_L3_RESUME_PDF='<resume.pdf>'" in handoff["command_template"]
    assert "PIPF_EXTERNAL_L3_PROFILE='<profile.yaml>'" in handoff["command_template"]
    assert "PIPF_EXTERNAL_L3_SESSION_DIR=.sessions" in handoff["command_template"]
    assert (
        "PIPF_EXTERNAL_L3_OUTPUT_DIR=outputs/submissions"
        in handoff["command_template"]
    )
    assert "PIPF_EXTERNAL_L3_TIMEOUT_SECONDS=10" in handoff["command_template"]
    assert "PIPF_EXTERNAL_L3_TIMEOUT_MS=45000" in handoff["command_template"]
    assert "PIPF_EXTERNAL_L3_HEADLESS=false" in handoff["command_template"]
    assert "PIPF_EXTERNAL_L3_RATE_LIMIT_MAX_PER_BATCH=5" in handoff["command_template"]
    assert (
        "PIPF_EXTERNAL_L3_RATE_LIMIT_COOLDOWN_SECONDS=900"
        in handoff["command_template"]
    )
    assert (
        "PIPF_EXTERNAL_L3_RATE_LIMIT_DAILY_LIMIT=30"
        in handoff["command_template"]
    )
    preflight_template = handoff["preflight_command_template"]
    assert "PIPF_EXTERNAL_L3_AUTHORIZED=false" in preflight_template
    assert "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false" in preflight_template
    assert "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=false" in preflight_template
    assert "PIPF_EXTERNAL_L3_AUTHORIZED=true" not in preflight_template
    assert "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true" not in preflight_template
    assert "PIPF_EXTERNAL_L3_JOB_URL='<https-url>'" in preflight_template
    assert "bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3" in preflight_template
    preflight_expectation = handoff["preflight_result_expectation"]
    assert preflight_expectation["template"] == "preflight_command_template"
    assert preflight_expectation["expected_status"] == "live_blocker_recorded"
    assert preflight_expectation["expected_outcome"] == "pre_submit_blocker_recorded"
    assert (
        preflight_expectation["expected_blocker_reason"]
        == "explicit_user_authorization_required"
    )
    assert preflight_expectation["expected_external_submission_attempted"] is False
    assert preflight_expectation["expected_submit_command_allowed"] is False
    assert preflight_expectation["expected_p0_017_complete"] is False
    assert (
        preflight_expectation["operator_should_treat_as_successful_preflight"]
        is True
    )
    assert preflight_expectation["must_not_start_external_channel"] is True
    assert "evidence_manifest" in preflight_expectation["required_evidence_sections"]
    preflight_review_checklist = handoff["preflight_review_checklist"]
    assert (
        preflight_review_checklist["status"]
        == "operator_review_required_before_authorized_template"
    )
    assert (
        preflight_review_checklist["required_before_authorized_template"] is True
    )
    assert preflight_review_checklist["raw_live_inputs_persisted"] is False
    preflight_review_items = {
        item["id"]: item for item in preflight_review_checklist["items"]
    }
    assert (
        preflight_review_items["validation_status_is_live_blocker_recorded"][
            "source_path"
        ]
        == "status"
    )
    assert (
        preflight_review_items["validation_status_is_live_blocker_recorded"][
            "expected"
        ]
        == "live_blocker_recorded"
    )
    assert (
        preflight_review_items[
            "blocker_reason_is_explicit_user_authorization_required"
        ]["expected"]
        == "explicit_user_authorization_required"
    )
    assert (
        preflight_review_items["external_submission_attempted_false"]["expected"]
        is False
    )
    assert (
        preflight_review_items["submit_command_allowed_false"]["source_path"]
        == "live_run_readiness.submit_command_allowed"
    )
    assert preflight_review_items["p0_017_complete_false"]["expected"] is False
    assert (
        preflight_review_items["live_input_artifacts_present_and_redacted"][
            "expected"
        ]
        == "present_with_raw_live_inputs_persisted_false"
    )
    assert (
        preflight_review_items["session_readiness_reviewed"]["expected"]
        == "present_with_manual_login_boundary"
    )
    assert preflight_review_items["rate_limit_policy_enabled"]["expected"] is True
    assert (
        preflight_review_items["evidence_manifest_complete"]["source_path"]
        == "evidence_manifest.status"
    )
    assert (
        preflight_review_items["runbook_fingerprinted"]["expected"]
        == "fingerprinted_and_sections_complete"
    )
    assert (
        preflight_review_items[
            "post_submit_feedback_traceability_points_to_live_blocker"
        ]["source_path"]
        == "post_submit_feedback_traceability.source_type"
    )
    assert all(
        item["required"] is True and item["raw_live_inputs_persisted"] is False
        for item in preflight_review_checklist["items"]
    )
    preflight_review_result = handoff["preflight_review_result"]
    assert (
        preflight_review_result["status"]
        == "preflight_evidence_review_passed_with_live_readiness_blockers"
    )
    assert preflight_review_result["applies_to_current_run"] is True
    assert preflight_review_result["all_required_items_passed"] is True
    assert preflight_review_result["live_readiness_for_authorization"] is False
    assert "manual_session_ready_confirmed" in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert "job_url_present" in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert "resume_pdf_file_ready" in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert "profile_yaml_file_ready" in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert "confirm_job_id_present" in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert "user_authorization" not in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert "final_submit_confirmation" not in preflight_review_result[
        "authorization_decision_blockers"
    ]
    assert preflight_review_result["ready_for_authorization_decision"] is False
    assert preflight_review_result["authorized_template_execution_allowed"] is False
    assert preflight_review_result["authorization_decision_required"] is False
    assert preflight_review_result["raw_live_inputs_persisted"] is False
    preflight_result_items = {
        item["id"]: item for item in preflight_review_result["items"]
    }
    assert (
        preflight_result_items["validation_status_is_live_blocker_recorded"][
            "observed"
        ]
        == "live_blocker_recorded"
    )
    assert (
        preflight_result_items[
            "blocker_reason_is_explicit_user_authorization_required"
        ]["observed"]
        == "explicit_user_authorization_required"
    )
    assert (
        preflight_result_items["external_submission_attempted_false"]["observed"]
        is False
    )
    assert (
        preflight_result_items["submit_command_allowed_false"]["observed"] is False
    )
    assert preflight_result_items["p0_017_complete_false"]["observed"] is False
    assert (
        preflight_result_items["live_input_artifacts_present_and_redacted"][
            "observed"
        ]
        == "present_with_raw_live_inputs_persisted_false"
    )
    assert (
        preflight_result_items["session_readiness_reviewed"]["observed"]
        == "present_with_manual_login_boundary"
    )
    assert preflight_result_items["rate_limit_policy_enabled"]["observed"] is True
    assert (
        preflight_result_items["evidence_manifest_complete"]["observed"]
        == "complete"
    )
    assert (
        preflight_result_items["runbook_fingerprinted"]["observed"]
        == "fingerprinted_and_sections_complete"
    )
    assert (
        preflight_result_items[
            "post_submit_feedback_traceability_points_to_live_blocker"
        ]["observed"]
        == "live_blocker"
    )
    assert all(
        item["status"] == "pass"
        and item["required"] is True
        and item["raw_live_inputs_persisted"] is False
        for item in preflight_review_result["items"]
    )
    action_plan = handoff["authorization_readiness_action_plan"]
    assert action_plan["status"] == "blocked_until_live_inputs_and_session_ready"
    assert action_plan["ready_for_authorization_decision"] is False
    assert action_plan["authorized_template_execution_allowed"] is False
    assert action_plan["pending_action_count"] == 5
    assert action_plan["raw_live_inputs_persisted"] is False
    action_items = {item["id"]: item for item in action_plan["actions"]}
    assert "manual_session_ready_confirmed" in action_items[
        "prepare_manual_session"
    ]["blocks_gates"]
    assert "job_url_present" in action_items["provide_job_url"]["blocks_gates"]
    assert "resume_pdf_file_ready" in action_items[
        "provide_reviewed_resume_pdf"
    ]["blocks_gates"]
    assert "profile_yaml_file_ready" in action_items[
        "provide_reviewed_profile_yaml"
    ]["blocks_gates"]
    assert "confirm_job_id_present" in action_items[
        "confirm_target_identity"
    ]["blocks_gates"]
    assert any(
        "session_readiness.session_storage_ready=true" in item
        for item in action_items["prepare_manual_session"]["required_evidence"]
    )
    assert all(
        item["required"] is True
        and item["raw_live_inputs_persisted"] is False
        and item["blocks_authorization_decision"] is True
        for item in action_plan["actions"]
    )
    intake_checklist = handoff["authorization_intake_checklist"]
    assert (
        intake_checklist["status"]
        == "blocked_until_authorization_intake_complete"
    )
    assert intake_checklist["required_before_template_release"] is True
    assert intake_checklist["required_before_authorized_template"] is True
    assert intake_checklist["pending_item_count"] == 9
    assert intake_checklist["satisfied_item_count"] == 0
    assert intake_checklist["raw_live_inputs_persisted"] is False
    intake_items = {item["id"]: item for item in intake_checklist["items"]}
    assert (
        intake_items["confirm_user_authorization"]["env_var"]
        == "PIPF_EXTERNAL_L3_AUTHORIZED"
    )
    assert "user_authorization" in intake_items[
        "confirm_user_authorization"
    ]["gates"]
    assert (
        intake_items["confirm_final_submit"]["env_var"]
        == "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED"
    )
    assert (
        intake_items["confirm_manual_session_ready"]["env_var"]
        == "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED"
    )
    assert (
        intake_items["prepare_session_storage"]["env_var"]
        == "PIPF_EXTERNAL_L3_SESSION_DIR"
    )
    assert intake_items["provide_job_url"]["env_var"] == "PIPF_EXTERNAL_L3_JOB_URL"
    assert "target_job_id_extractable" in intake_items["provide_job_url"]["gates"]
    assert (
        intake_items["provide_resume_pdf"]["env_var"]
        == "PIPF_EXTERNAL_L3_RESUME_PDF"
    )
    assert (
        intake_items["provide_profile_yaml"]["env_var"]
        == "PIPF_EXTERNAL_L3_PROFILE"
    )
    assert (
        intake_items["confirm_target_job_id"]["env_var"]
        == "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID"
    )
    assert (
        intake_items["confirm_recruiter"]["env_var"]
        == "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER"
    )
    assert all(
        item["status"] == "pending"
        and item["required"] is True
        and item["blocks_template_release"] is True
        and item["raw_live_inputs_persisted"] is False
        for item in intake_checklist["items"]
    )
    release_decision = handoff["authorized_template_release_decision"]
    assert release_decision["status"] == "withheld_until_authorization_readiness"
    assert release_decision["template_released"] is False
    assert release_decision["template_released_to_operator"] is False
    assert release_decision["copy_execution_allowed"] is False
    assert release_decision["authorized_template_rendered_for_review"] is True
    assert release_decision["template_rendered_for_audit"] is True
    assert (
        release_decision["withheld_reason"]
        == "authorization_readiness_action_plan_pending"
    )
    assert release_decision["pending_action_count"] == 5
    assert "prepare_manual_session" in release_decision["pending_action_ids"]
    assert "provide_job_url" in release_decision["pending_action_ids"]
    assert "confirm_target_identity" in release_decision["pending_action_ids"]
    assert (
        "authorization_readiness_action_plan_pending"
        in release_decision["release_blockers"]
    )
    assert (
        "authorization_intake_checklist_pending"
        in release_decision["release_blockers"]
    )
    assert (
        "ready_for_authorization_decision_false"
        in release_decision["release_blockers"]
    )
    assert (
        "explicit_user_authorization_missing"
        in release_decision["release_blockers"]
    )
    assert (
        "final_submit_confirmation_missing"
        in release_decision["release_blockers"]
    )
    assert (
        "authorization_readiness_action_plan.pending_action_count=0"
        in release_decision["required_before_release"]
    )
    assert (
        "authorization_intake_checklist.pending_item_count=0"
        in release_decision["required_before_release"]
    )
    assert (
        "preflight_review_result.ready_for_authorization_decision=true"
        in release_decision["required_before_release"]
    )
    assert (
        "PIPF_EXTERNAL_L3_AUTHORIZED=true"
        in release_decision["required_before_release"]
    )
    assert release_decision["raw_live_inputs_persisted"] is False
    go_no_go_decision = handoff["live_run_go_no_go_decision"]
    assert (
        go_no_go_decision["status"]
        == "no_go_until_authorized_template_released"
    )
    assert go_no_go_decision["go_for_live_run"] is False
    assert go_no_go_decision["submit_command_may_start"] is False
    assert go_no_go_decision["copy_authorized_template_allowed"] is False
    assert go_no_go_decision["reason"] == "live_run_readiness_not_ready"
    assert go_no_go_decision["raw_live_inputs_persisted"] is False
    assert (
        go_no_go_decision["decision_inputs"][
            "live_run_readiness_submit_command_allowed"
        ]
        is False
    )
    assert (
        go_no_go_decision["decision_inputs"]["submit_safety_decision"]
        == "blocked_before_command"
    )
    assert (
        go_no_go_decision["decision_inputs"][
            "authorization_readiness_action_plan_pending_action_count"
        ]
        == 5
    )
    assert (
        go_no_go_decision["decision_inputs"][
            "authorization_intake_pending_item_count"
        ]
        == 9
    )
    assert (
        go_no_go_decision["decision_inputs"][
            "authorized_template_copy_execution_allowed"
        ]
        is False
    )
    assert "submit_command_not_allowed" in go_no_go_decision["blocking_evidence"]
    assert (
        "authorization_readiness_action_plan_pending"
        in go_no_go_decision["blocking_evidence"]
    )
    assert (
        "authorization_intake_checklist_pending"
        in go_no_go_decision["blocking_evidence"]
    )
    assert (
        "authorized_template_not_released"
        in go_no_go_decision["blocking_evidence"]
    )
    resolution_routes = {
        item["blocker"]: item for item in go_no_go_decision["resolution_routes"]
    }
    assert (
        resolution_routes["live_run_readiness_not_ready"]["source_path"]
        == "live_run_readiness.missing_gates"
    )
    assert (
        "live_run_readiness.ready=true"
        in resolution_routes["live_run_readiness_not_ready"]["required_evidence"]
    )
    assert (
        resolution_routes["submit_safety_decision_blocked_before_command"][
            "source_path"
        ]
        == "submit_safety_decision.blocking_reason"
    )
    assert (
        "submit_safety_decision.decision=allowed_pending_execution"
        in resolution_routes["submit_safety_decision_blocked_before_command"][
            "required_evidence"
        ]
    )
    assert (
        resolution_routes["authorization_readiness_action_plan_pending"][
            "source_path"
        ]
        == "operator_handoff.authorization_readiness_action_plan.actions"
    )
    assert (
        resolution_routes["authorization_intake_checklist_pending"]["source_path"]
        == "operator_handoff.authorization_intake_checklist.items"
    )
    assert (
        resolution_routes["authorized_template_not_released"]["source_path"]
        == "operator_handoff.authorized_template_release_decision.release_blockers"
    )
    assert all(
        item["operator_action"]
        and item["required_evidence"]
        and item["raw_live_inputs_persisted"] is False
        for item in go_no_go_decision["resolution_routes"]
    )
    assert (
        "submit_safety_decision.decision=allowed_pending_execution"
        in go_no_go_decision["required_before_go"]
    )
    assert (
        "operator_handoff.authorized_template_release_decision.copy_execution_allowed=true"
        in go_no_go_decision["required_before_go"]
    )
    assert "真实渠道验证成功后完成" in go_no_go_decision["p0_017_completion_note"]
    execution_sequence = handoff["live_run_execution_sequence"]
    assert (
        execution_sequence["status"]
        == "blocked_before_authorized_template_execution"
    )
    assert execution_sequence["next_executable_step"] == "resolve_no_go_routes"
    assert execution_sequence["authorized_template_execution_allowed"] is False
    assert execution_sequence["raw_live_inputs_persisted"] is False
    sequence_steps = {
        item["id"]: item for item in execution_sequence["steps"]
    }
    assert sequence_steps["run_preflight_template"]["order"] == 1
    assert sequence_steps["run_preflight_template"]["status"] == "satisfied"
    assert (
        sequence_steps["run_preflight_template"]["source_path"]
        == "operator_handoff.preflight_command_template"
    )
    assert sequence_steps["run_preflight_template"]["blocks_next_step"] is False
    assert sequence_steps["review_preflight_evidence"]["status"] == "satisfied"
    assert (
        sequence_steps["resolve_no_go_routes"]["source_path"]
        == "operator_handoff.live_run_go_no_go_decision.resolution_routes"
    )
    assert sequence_steps["resolve_no_go_routes"]["status"] == "blocked"
    assert sequence_steps["resolve_no_go_routes"]["blocks_next_step"] is True
    assert (
        "operator_handoff.live_run_go_no_go_decision.resolution_routes=[]"
        in sequence_steps["resolve_no_go_routes"]["required_before_next"]
    )
    assert (
        sequence_steps["complete_authorization_readiness_actions"]["source_path"]
        == "operator_handoff.authorization_readiness_action_plan.pending_action_count"
    )
    assert sequence_steps["complete_authorization_intake"]["status"] == "blocked"
    assert sequence_steps["release_authorized_template"]["status"] == "blocked"
    assert sequence_steps["pass_live_run_go_no_go"]["status"] == "blocked"
    assert sequence_steps["execute_authorized_template"]["status"] == "blocked"
    assert sequence_steps["verify_p0_017_completion"]["status"] == "blocked"
    assert all(
        item["required_before_next"]
        and item["raw_live_inputs_persisted"] is False
        for item in execution_sequence["steps"]
    )
    command_template_review = handoff["command_template_review"]
    assert command_template_review["copy_paste_ready"] is False
    assert command_template_review["requires_placeholder_replacement"] is True
    assert command_template_review["requires_separate_authorization"] is True
    assert (
        command_template_review["requires_separate_final_submit_confirmation"]
        is True
    )
    assert (
        command_template_review["requires_manual_session_ready_confirmation"] is True
    )
    assert command_template_review["requires_prepared_session_storage"] is True
    assert command_template_review["shell_safe_env_assignments"] is True
    assert command_template_review["live_input_placeholders_present"] is True
    assert command_template_review["raw_live_inputs_persisted"] is False
    assert command_template_review["execution_order"] == [
        "preflight_command_template",
        "authorized_command_template",
    ]
    assert (
        command_template_review["preflight_must_run_before_authorized_template"]
        is True
    )
    assert command_template_review["preflight_template_authorization_enabled"] is False
    assert command_template_review["preflight_template_final_submit_enabled"] is False
    assert (
        command_template_review[
            "authorized_template_requires_preflight_evidence_review"
        ]
        is True
    )
    assert "<https-url>" in command_template_review["placeholders"]
    assert any("占位符" in item for item in command_template_review["review_items"])
    assert any(
        "Liepin 持久化会话目录" in item
        for item in command_template_review["review_items"]
    )
    required_env = {item["name"]: item for item in handoff["required_env"]}
    assert required_env["PIPF_EXTERNAL_L3_AUTHORIZED"]["present"] is False
    assert (
        required_env["PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED"]["present"] is False
    )
    assert required_env["PIPF_EXTERNAL_L3_JOB_URL"]["present"] is False
    assert handoff["forbidden_input_audit"]["forbidden_inputs_present"] is False
    assert all("value" not in item for item in handoff["required_env"])
    runbook = handoff["runbook"]
    runbook_path = Path("docs/runbooks/external-l3-live-run.md")
    assert runbook["path"] == "docs/runbooks/external-l3-live-run.md"
    assert runbook["language"] == "zh-CN"
    assert runbook["exists"] is True
    assert runbook["sha256"] == hashlib.sha256(runbook_path.read_bytes()).hexdigest()
    assert all(
        runbook["required_sections_present"][section] is True
        for section in runbook["required_sections"]
    )
    assert runbook["operator_review_required"] is True
    assert runbook["copy_paste_requires_live_value_replacement"] is True
    assert runbook["raw_live_inputs_persisted"] is False
    assert "authorization_boundary" in runbook["covers"]
    assert "post_run_evidence_review" in runbook["covers"]
    authorization_packet = handoff["authorization_packet"]
    assert authorization_packet["status"] == "blocked_until_missing_gates_resolved"
    assert authorization_packet["raw_confirmation_values_persisted"] is False
    assert len(authorization_packet["required_confirmation_statements"]) >= 3
    assert any(
        "Liepin 持久化会话目录" in item
        for item in authorization_packet["required_confirmation_statements"]
    )
    assert "live_run_readiness" in authorization_packet["required_evidence"]
    assert "submit_safety_decision" in authorization_packet["required_evidence"]
    assert "session_readiness" in authorization_packet["required_evidence"]
    assert "password" in authorization_packet["operator_must_not_provide"]
    assert "captcha_code" in authorization_packet["operator_must_not_provide"]
    acknowledgement_items = {
        item["id"]: item
        for item in authorization_packet["acknowledgement_checklist"]
    }
    assert (
        acknowledgement_items["acknowledge_external_channel_authorization"][
            "status"
        ]
        == "pending"
    )
    assert (
        "PIPF_EXTERNAL_L3_AUTHORIZED"
        in acknowledgement_items["acknowledge_external_channel_authorization"][
            "env_vars"
        ]
    )
    assert (
        "user_authorization"
        in acknowledgement_items["acknowledge_external_channel_authorization"][
            "gates"
        ]
    )
    assert (
        acknowledgement_items["acknowledge_final_submit_confirmation"][
            "source_path"
        ]
        == "live_run_readiness.gates.final_submit_confirmation"
    )
    assert (
        acknowledgement_items["acknowledge_manual_session_ready"]["source_path"]
        == "session_readiness"
    )
    assert (
        "PIPF_EXTERNAL_L3_JOB_URL"
        in acknowledgement_items["acknowledge_live_input_artifacts"]["env_vars"]
    )
    assert (
        acknowledgement_items["acknowledge_target_identity"]["source_path"]
        == "target_confirmation_audit"
    )
    assert (
        acknowledgement_items["acknowledge_forbidden_inputs_absent"]["status"]
        == "satisfied"
    )
    assert all(
        item["required_before_template_release"] is True
        and item["required_before_authorized_template"] is True
        and item["raw_live_inputs_persisted"] is False
        and item["statement"]
        for item in authorization_packet["acknowledgement_checklist"]
    )
    assert any(
        "当前缺失 gate" in item
        for item in authorization_packet["abort_conditions"]
    )
    assert all(
        "https://www.liepin.com/job/123.shtml" not in item
        for item in authorization_packet["required_confirmation_statements"]
    )
    markdown_path = evidence_path.parent / "external-l3-validation.md"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# External L3 投递验证" in markdown
    assert "## 结果分级" in markdown
    assert "- Outcome: `pre_submit_blocker_recorded`" in markdown
    assert (
        "- Acceptance pass 含义: `pre_submit_blocker_evidence_recorded`"
        in markdown
    )
    assert "- 是否已真实验证成功: `False`" in markdown
    assert "- P0-017 是否完成: `False`" in markdown
    assert "## P0-017 完成门禁" in markdown
    assert "- 状态: `incomplete_pre_submit_blocker`" in markdown
    assert "- Acceptance pass 是否等于完成: `False`" in markdown
    assert "- 完成阻断项: `explicit_user_authorization" in markdown
    assert "| 完成证据 | 状态 | 来源 | 必需 | 原值落盘 |" in markdown
    assert (
        "| `explicit_user_authorization` | `missing` | "
        "`live_run_readiness.gates.user_authorization` | `True` | `False` |"
    ) in markdown
    assert (
        "| `post_submit_feedback_traceability` | `satisfied` | "
        "`post_submit_feedback_traceability.traceable` | `True` | `False` |"
    ) in markdown
    assert "## Live Run Readiness" in markdown
    assert "- 是否允许启动 submit 命令: `False`" in markdown
    assert "## 最终提交安全决策" in markdown
    assert "- 决策: `blocked_before_command`" in markdown
    assert "## 真实输入产物审计" in markdown
    assert "- Job URL 原值是否持久化: `False`" in markdown
    assert "| 产物 | 已提供 | 存在文件 | 文件名是否持久化 | 原内容是否持久化 | 扩展名 | 大小 | SHA256 |" in markdown
    assert "| `resume_pdf` | `False` | `False` | `False` | `False` | `` | 0 | `` |" in markdown
    assert "## 频控策略" in markdown
    assert "- 是否启用: `True`" in markdown
    assert "## 人工会话准备" in markdown
    assert "- 已确认共享登录会话可用: `False`" in markdown
    assert "- 自动化是否输入凭据: `False`" in markdown
    assert "## 禁止输入审计" in markdown
    assert "- 禁止输入是否出现: `False`" in markdown
    assert "## 目标确认审计" in markdown
    assert "- 确认 recruiter 是否已提供: `False`" in markdown
    assert "- URL 岗位 ID 与确认值是否一致: `False`" in markdown
    assert (
        "- recruiter 页面匹配是否必须由 target_verify 证明: `True`"
        in markdown
    )
    assert "- recruiter 原始确认值是否持久化: `False`" in markdown
    assert "| Gate | 状态 | 说明 |" in markdown
    assert "## 授权交接包" in markdown
    assert "### 运行配置" in markdown
    assert "| `timeout_seconds` | `10` |" in markdown
    assert "### 真实运行 Runbook" in markdown
    assert "- 路径: `docs/runbooks/external-l3-live-run.md`" in markdown
    assert f"- SHA256: `{runbook['sha256']}`" in markdown
    assert "- 运行前必须复核: `True`" in markdown
    assert "#### Runbook 必需章节" in markdown
    assert "#### Runbook 覆盖边界" in markdown
    assert "### 本地预检命令模板" in markdown
    assert "PIPF_EXTERNAL_L3_AUTHORIZED=false" in markdown
    assert "### 本地预检预期结果" in markdown
    assert "- 预期状态: `live_blocker_recorded`" in markdown
    assert "- 预期 blocker reason: `explicit_user_authorization_required`" in markdown
    assert "- 操作者是否应视为预检正常: `True`" in markdown
    assert "#### 预检必需证据段" in markdown
    assert "### 本地预检复核清单" in markdown
    assert (
        "- 状态: `operator_review_required_before_authorized_template`"
        in markdown
    )
    assert "- 授权模板前必需: `True`" in markdown
    assert "- 原始 live 输入是否持久化: `False`" in markdown
    assert "| 复核项 | 来源 | 预期 | 必需 |" in markdown
    assert "`validation_status_is_live_blocker_recorded`" in markdown
    assert "`blocker_reason_is_explicit_user_authorization_required`" in markdown
    assert "`external_submission_attempted_false`" in markdown
    assert "`submit_command_allowed_false`" in markdown
    assert "`p0_017_complete_false`" in markdown
    assert "`runbook_fingerprinted`" in markdown
    assert "### 本地预检复核结果" in markdown
    assert (
        "- 状态: `preflight_evidence_review_passed_with_live_readiness_blockers`"
        in markdown
    )
    assert "- 适用于当前运行: `True`" in markdown
    assert "- 必需项全部通过: `True`" in markdown
    assert "- 授权决策前真实运行就绪: `False`" in markdown
    assert "- 授权决策阻断项: `manual_session_ready_confirmed" in markdown
    assert "- 可进入授权决策: `False`" in markdown
    assert "- 是否允许执行授权模板: `False`" in markdown
    assert "- 仍需用户授权: `False`" in markdown
    assert "| 复核项 | 状态 | 来源 | 预期 | 观测 |" in markdown
    assert (
        "| `validation_status_is_live_blocker_recorded` | `pass` | `status` | "
        "`live_blocker_recorded` | `live_blocker_recorded` |"
    ) in markdown
    assert "### 授权就绪行动计划" in markdown
    assert "- 状态: `blocked_until_live_inputs_and_session_ready`" in markdown
    assert "- 待补行动数: `5`" in markdown
    assert "| 行动 | 类别 | 阻断 Gate | 需要补齐 | 必需证据 | 原值落盘 |" in markdown
    assert "`prepare_manual_session`" in markdown
    assert "`provide_job_url`" in markdown
    assert "`provide_reviewed_resume_pdf`" in markdown
    assert "`provide_reviewed_profile_yaml`" in markdown
    assert "`confirm_target_identity`" in markdown
    assert "### 授权输入接收清单" in markdown
    assert (
        "- 状态: `blocked_until_authorization_intake_complete`"
        in markdown
    )
    assert "- 授权模板发布前必需: `True`" in markdown
    assert "- 待补输入/确认数: `9`" in markdown
    assert "| 输入/确认 | Env | 占位符 | Gate | 状态 | 需要补齐 | 原值落盘 |" in markdown
    assert "`confirm_user_authorization`" in markdown
    assert "`PIPF_EXTERNAL_L3_AUTHORIZED`" in markdown
    assert "`confirm_final_submit`" in markdown
    assert "`PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED`" in markdown
    assert "`provide_job_url`" in markdown
    assert "`PIPF_EXTERNAL_L3_JOB_URL`" in markdown
    assert "### 授权模板发布决策" in markdown
    assert (
        "- 状态: `withheld_until_authorization_readiness`"
        in markdown
    )
    assert "- 模板是否发布给操作者执行: `False`" in markdown
    assert "- 是否允许复制执行: `False`" in markdown
    assert "- 模板是否仅供复核展示: `True`" in markdown
    assert (
        "- 发布阻断原因: `authorization_readiness_action_plan_pending`"
        in markdown
    )
    assert "#### 发布阻断项" in markdown
    assert "`authorization_readiness_action_plan_pending`" in markdown
    assert "`authorization_intake_checklist_pending`" in markdown
    assert "`explicit_user_authorization_missing`" in markdown
    assert "`final_submit_confirmation_missing`" in markdown
    assert "#### 发布前必需条件" in markdown
    assert "`authorization_readiness_action_plan.pending_action_count=0`" in markdown
    assert "`authorization_intake_checklist.pending_item_count=0`" in markdown
    assert "`preflight_review_result.ready_for_authorization_decision=true`" in markdown
    assert "### 真实运行 Go/No-Go 决策" in markdown
    assert "- 状态: `no_go_until_authorized_template_released`" in markdown
    assert "- 是否允许启动真实运行: `False`" in markdown
    assert "- submit 命令是否可启动: `False`" in markdown
    assert "- 是否允许复制授权模板: `False`" in markdown
    assert "- 决策原因: `live_run_readiness_not_ready`" in markdown
    assert "#### 决策输入" in markdown
    assert "`live_run_readiness_submit_command_allowed`: `False`" in markdown
    assert "`submit_safety_decision`: `blocked_before_command`" in markdown
    assert "`authorized_template_copy_execution_allowed`: `False`" in markdown
    assert "#### Go/No-Go 阻断证据" in markdown
    assert "`submit_command_not_allowed`" in markdown
    assert "`authorized_template_not_released`" in markdown
    assert "#### No-Go 处理路线" in markdown
    assert "| 阻断项 | 来源 | 处理动作 | 必需证据 | 原值落盘 |" in markdown
    assert (
        "`live_run_readiness_not_ready` | `live_run_readiness.missing_gates`"
        in markdown
    )
    assert (
        "`submit_safety_decision_blocked_before_command` | `submit_safety_decision.blocking_reason`"
        in markdown
    )
    assert (
        "`authorization_readiness_action_plan_pending` | `operator_handoff.authorization_readiness_action_plan.actions`"
        in markdown
    )
    assert (
        "`authorization_intake_checklist_pending` | `operator_handoff.authorization_intake_checklist.items`"
        in markdown
    )
    assert (
        "`authorized_template_not_released` | `operator_handoff.authorized_template_release_decision.release_blockers`"
        in markdown
    )
    assert "#### Go 前必需条件" in markdown
    assert "`live_run_readiness.submit_command_allowed=true`" in markdown
    assert (
        "`submit_safety_decision.decision=allowed_pending_execution`"
        in markdown
    )
    assert (
        "`operator_handoff.authorized_template_release_decision.copy_execution_allowed=true`"
        in markdown
    )
    assert "### 真实运行执行顺序门禁" in markdown
    assert (
        "- 状态: `blocked_before_authorized_template_execution`"
        in markdown
    )
    assert "- 下一可执行步骤: `resolve_no_go_routes`" in markdown
    assert "- 是否允许执行授权模板: `False`" in markdown
    assert (
        "| 顺序 | 步骤 | 状态 | 来源 | 阻断后续 | 必需条件 | 原值落盘 |"
        in markdown
    )
    assert "`1` | `run_preflight_template` | `satisfied`" in markdown
    assert "`3` | `resolve_no_go_routes` | `blocked`" in markdown
    assert "`6` | `release_authorized_template` | `blocked`" in markdown
    assert "`9` | `verify_p0_017_completion` | `blocked`" in markdown
    assert "### 授权真实运行命令模板" in markdown
    assert "PIPF_EXTERNAL_L3_AUTHORIZED=true" in markdown
    assert "```bash" in markdown
    assert "PIPF_EXTERNAL_L3_JOB_URL='<https-url>'" in markdown
    assert "bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3" in markdown
    assert "### 命令模板复核" in markdown
    assert "- 是否可直接复制运行: `False`" in markdown
    assert "- 必须替换占位符: `True`" in markdown
    assert "- 必须独立确认最终提交: `True`" in markdown
    assert "- 必须确认人工会话可用: `True`" in markdown
    assert "- 必须确认 session 存储就绪: `True`" in markdown
    assert "- 必须先跑本地预检: `True`" in markdown
    assert "- 预检模板是否启用授权: `False`" in markdown
    assert "- 预检模板是否启用最终提交: `False`" in markdown
    assert "- 授权模板是否要求先复核预检证据: `True`" in markdown
    assert "#### 执行顺序" in markdown
    assert "#### 需替换占位符" in markdown
    assert "#### 复核项" in markdown
    assert "### 授权确认包" in markdown
    assert "#### 必需确认声明" in markdown
    assert "#### 授权签核清单" in markdown
    assert "| 签核项 | 状态 | Env | Gate | 来源 | 原值落盘 |" in markdown
    assert "`acknowledge_external_channel_authorization`" in markdown
    assert "`acknowledge_final_submit_confirmation`" in markdown
    assert "`acknowledge_manual_session_ready`" in markdown
    assert "`acknowledge_forbidden_inputs_absent`" in markdown
    assert "#### 中止条件" in markdown
    assert "| 必需环境变量 | 是否存在 | 是否敏感 |" in markdown
    assert "## 提交后反馈追溯" in markdown
    assert "- 来源类型: `live_blocker`" in markdown
    assert "- 来源状态: `pre_submit_blocked`" in markdown
    assert "- 来源原因: `explicit_user_authorization_required`" in markdown
    assert "- Submit 命令允许启动: `False`" in markdown
    assert "- Missing Gates: `user_authorization" in markdown
    assert "- 诊断 Job URL 已提供: `False`" in markdown
    assert "- 诊断 Job URL 原值是否持久化: `False`" in markdown
    assert "## 证据清单" in markdown
    assert "| 证据 | 类型 | 必需 | 存在 | 状态 | 位置 |" in markdown
    assert "`external_l3_validation_json`" in markdown
    assert "`feedback_source_artifact`" in markdown

    markdown_path.write_text(
        markdown.replace(
            "- Missing Gates: `user_authorization",
            "- Missing Gates: `stale_user_authorization",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    pre_submit_diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_pre_submit_blocker_diagnostics_recorded"
        )
    )
    assert pre_submit_diagnostics_rule["status"] == "fail"
    assert "Missing Gates" in pre_submit_diagnostics_rule["message"]


def test_acceptance_runner_l3_journey_report_records_live_blocker_rule(
    tmp_path: Path,
) -> None:
    with patch.dict(os.environ, {}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    assert journey_payload["status"] == "pass"
    external_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_result_or_blocker_recorded"
    )
    assert external_rule["level"] == "L3"
    assert external_rule["stage"] == "submissions"
    assert external_rule["status"] == "pass"
    assert "external-l3-validation.json" in external_rule["evidence"]
    assert "explicit_user_authorization_required" in external_rule["message"]
    safety_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submit_safety_decision_recorded"
    )
    assert safety_rule["level"] == "L3"
    assert safety_rule["stage"] == "submissions"
    assert safety_rule["status"] == "pass"
    assert "blocked_before_command" in safety_rule["message"]
    input_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_live_input_artifacts_fingerprinted"
    )
    assert input_rule["level"] == "L3"
    assert input_rule["stage"] == "submissions"
    assert input_rule["status"] == "pass"
    assert "真实输入产物审计" in input_rule["message"]
    rate_limit_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_rate_limit_policy_recorded"
    )
    assert rate_limit_rule["level"] == "L3"
    assert rate_limit_rule["stage"] == "submissions"
    assert rate_limit_rule["status"] == "pass"
    assert "频控策略" in rate_limit_rule["message"]
    forbidden_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_forbidden_inputs_rejected"
    )
    assert forbidden_rule["level"] == "L3"
    assert forbidden_rule["stage"] == "submissions"
    assert forbidden_rule["status"] == "pass"
    assert "禁止输入审计" in forbidden_rule["message"]
    target_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_target_confirmation_matches_url"
    )
    assert target_rule["level"] == "L3"
    assert target_rule["stage"] == "submissions"
    assert target_rule["status"] == "pass"
    assert "目标确认审计" in target_rule["message"]
    command_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_live_command_redacted"
    )
    assert command_rule["level"] == "L3"
    assert command_rule["stage"] == "submissions"
    assert command_rule["status"] == "pass"
    assert "命令" in command_rule["message"]
    output_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_live_output_redacted"
    )
    assert output_rule["level"] == "L3"
    assert output_rule["stage"] == "submissions"
    assert output_rule["status"] == "pass"
    assert "output" in output_rule["message"]
    feedback_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_submit_feedback_traceable"
    )
    assert feedback_rule["level"] == "L3"
    assert feedback_rule["stage"] == "submissions"
    assert feedback_rule["status"] == "pass"
    assert "live_blocker" in feedback_rule["message"]
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_post_command_blocker_diagnostics_recorded"
        )
    )
    assert diagnostics_rule["level"] == "L3"
    assert diagnostics_rule["stage"] == "submissions"
    assert diagnostics_rule["status"] == "pass"
    assert "post-command blocker" in diagnostics_rule["message"]
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["level"] == "L3"
    assert summary_rule["stage"] == "submissions"
    assert summary_rule["status"] == "pass"
    assert "submission log" in summary_rule["message"]
    path_guard_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_path_guarded"
    )
    assert path_guard_rule["level"] == "L3"
    assert path_guard_rule["stage"] == "submissions"
    assert path_guard_rule["status"] == "pass"
    assert "未执行真实渠道命令" in path_guard_rule["message"]
    required_steps_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_required_steps_recorded"
    )
    assert required_steps_rule["level"] == "L3"
    assert required_steps_rule["stage"] == "submissions"
    assert required_steps_rule["status"] == "pass"
    assert "未执行真实渠道命令" in required_steps_rule["message"]
    basename_redaction_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_input_artifact_basenames_redacted"
    )
    assert basename_redaction_rule["level"] == "L3"
    assert basename_redaction_rule["stage"] == "submissions"
    assert basename_redaction_rule["status"] == "pass"
    assert "文件名" in basename_redaction_rule["message"]
    markdown_redaction_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_human_readable_redaction_evidence_recorded"
        )
    )
    assert markdown_redaction_rule["level"] == "L3"
    assert markdown_redaction_rule["stage"] == "submissions"
    assert markdown_redaction_rule["status"] == "pass"
    assert "Markdown" in markdown_redaction_rule["message"]
    log_redaction_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_raw_inputs_redacted"
    )
    assert log_redaction_rule["level"] == "L3"
    assert log_redaction_rule["stage"] == "submissions"
    assert log_redaction_rule["status"] == "pass"
    assert "未执行真实渠道命令" in log_redaction_rule["message"]
    step_detail_redaction_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_step_details_redacted"
    )
    assert step_detail_redaction_rule["level"] == "L3"
    assert step_detail_redaction_rule["stage"] == "submissions"
    assert step_detail_redaction_rule["status"] == "pass"
    assert "未执行真实渠道命令" in step_detail_redaction_rule["message"]
    browser_artifacts_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_submission_log_browser_artifacts_redacted"
        )
    )
    assert browser_artifacts_rule["level"] == "L3"
    assert browser_artifacts_rule["stage"] == "submissions"
    assert browser_artifacts_rule["status"] == "pass"
    assert "未执行真实渠道命令" in browser_artifacts_rule["message"]
    authorization_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_authorization_packet_recorded"
    )
    assert authorization_rule["level"] == "L3"
    assert authorization_rule["stage"] == "submissions"
    assert authorization_rule["status"] == "pass"
    assert "授权确认包" in authorization_rule["message"]
    assert "授权签核清单" in authorization_rule["message"]
    handoff_template_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_handoff_command_template_matches_effective_policy"
        )
    )
    assert handoff_template_rule["level"] == "L3"
    assert handoff_template_rule["stage"] == "submissions"
    assert handoff_template_rule["status"] == "pass"
    assert "两阶段模板" in handoff_template_rule["message"]
    handoff_template_review_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_handoff_command_template_review_recorded"
        )
    )
    assert handoff_template_review_rule["level"] == "L3"
    assert handoff_template_review_rule["stage"] == "submissions"
    assert handoff_template_review_rule["status"] == "pass"
    assert "必须先跑本地预检" in handoff_template_review_rule["message"]
    assert "授权 blocker" in handoff_template_review_rule["message"]
    assert "预检复核清单" in handoff_template_review_rule["message"]
    assert "预检复核结果已逐项通过" in handoff_template_review_rule["message"]
    assert "不能进入授权决策" in handoff_template_review_rule["message"]
    assert "授权就绪行动计划" in handoff_template_review_rule["message"]
    assert "授权输入接收清单" in handoff_template_review_rule["message"]
    assert "授权模板发布决策" in handoff_template_review_rule["message"]
    assert "真实运行 Go/No-Go 决策" in handoff_template_review_rule["message"]
    assert "no-go" in handoff_template_review_rule["message"]
    assert "真实运行执行顺序门禁" in handoff_template_review_rule["message"]
    assert "resolve_no_go_routes" in handoff_template_review_rule["message"]
    evidence_manifest_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_evidence_manifest_recorded"
    )
    assert evidence_manifest_rule["level"] == "L3"
    assert evidence_manifest_rule["stage"] == "submissions"
    assert evidence_manifest_rule["status"] == "pass"
    assert "证据清单" in evidence_manifest_rule["message"]
    assert "runbook" in evidence_manifest_rule["message"]
    outcome_summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_outcome_summary_recorded"
    )
    assert outcome_summary_rule["level"] == "L3"
    assert outcome_summary_rule["stage"] == "submissions"
    assert outcome_summary_rule["status"] == "pass"
    assert "结果分级" in outcome_summary_rule["message"]
    session_ready_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_manual_session_ready_confirmed_before_command"
        )
    )
    assert session_ready_rule["level"] == "L3"
    assert session_ready_rule["stage"] == "submissions"
    assert session_ready_rule["status"] == "pass"
    assert "人工会话准备" in session_ready_rule["message"]
    pre_submit_diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_pre_submit_blocker_diagnostics_recorded"
        )
    )
    assert pre_submit_diagnostics_rule["level"] == "L3"
    assert pre_submit_diagnostics_rule["stage"] == "submissions"
    assert pre_submit_diagnostics_rule["status"] == "pass"
    assert "pre-submit blocker" in pre_submit_diagnostics_rule["message"]
    timeout_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_timeout_recorded_as_live_blocker"
    )
    assert timeout_rule["level"] == "L3"
    assert timeout_rule["stage"] == "submissions"
    assert timeout_rule["status"] == "pass"
    assert "超时" in timeout_rule["message"]
    command_error_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_command_error_recorded_as_live_blocker"
        )
    )
    assert command_error_rule["level"] == "L3"
    assert command_error_rule["stage"] == "submissions"
    assert command_error_rule["status"] == "pass"
    assert "启动错误" in command_error_rule["message"]


def test_acceptance_runner_l3_journey_report_rejects_stale_evidence_manifest_markdown(
    tmp_path: Path,
) -> None:
    with patch.dict(os.environ, {}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    external_step = next(
        step
        for step in report.steps
        if step.name == "external_l3_submission_validation"
    )
    evidence_path = Path(external_step.evidence)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    manifest_entry = next(
        item
        for item in payload["evidence_manifest"]["entries"]
        if item["id"] == "feedback_source_artifact"
    )
    expected_row = (
        "| "
        + " | ".join(
            [
                f"`{manifest_entry.get('id', '')}`",
                f"`{manifest_entry.get('artifact_type', '')}`",
                f"`{manifest_entry.get('required', False)}`",
                f"`{manifest_entry.get('present', False)}`",
                f"`{manifest_entry.get('status', '')}`",
                f"`{manifest_entry.get('location', '')}`",
            ]
        )
        + " |"
    )
    stale_row = expected_row.replace("`declared_source`", "`stale_source`")
    assert stale_row != expected_row
    markdown_path = evidence_path.with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert expected_row in markdown
    markdown_path.write_text(
        markdown.replace(expected_row, stale_row),
        encoding="utf-8",
    )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    evidence_manifest_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_evidence_manifest_recorded"
    )
    assert evidence_manifest_rule["status"] == "fail"
    assert (
        "feedback_source_artifact.markdown_row"
        in evidence_manifest_rule["message"]
    )


def test_acceptance_runner_l3_requires_separate_final_submit_confirmation(
    tmp_path: Path,
) -> None:
    with patch.dict(os.environ, {"PIPF_EXTERNAL_L3_AUTHORIZED": "true"}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["authorized"] is True
    assert payload["final_submit_confirmed"] is False
    assert (
        payload["live_blocker"]["reason"]
        == "explicit_final_submit_confirmation_required"
    )
    assert "final_submit_confirmation" in payload["live_blocker"]["failed_checks"]
    assert payload["coverage"]["user_authorized_external_session"] == "pass"
    assert payload["coverage"]["explicit_final_submit_gate"] == "blocked_recorded"
    readiness = payload["live_run_readiness"]
    assert readiness["ready"] is False
    assert "user_authorization" not in readiness["missing_gates"]
    assert "final_submit_confirmation" in readiness["missing_gates"]
    required_env = {
        item["name"]: item for item in payload["operator_handoff"]["required_env"]
    }
    assert required_env["PIPF_EXTERNAL_L3_AUTHORIZED"]["present"] is True
    assert (
        required_env["PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED"]["present"] is False
    )
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "blocked_before_command"
    assert submit_decision["authorization_confirmed"] is True
    assert submit_decision["final_submit_confirmed"] is False
    assert (
        submit_decision["blocking_reason"]
        == "explicit_final_submit_confirmation_required"
    )


def test_acceptance_runner_l3_rejects_forbidden_secret_or_challenge_inputs(
    tmp_path: Path,
) -> None:
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_PASSWORD": "do-not-store",
        "PIPF_EXTERNAL_L3_CAPTCHA_CODE": "123456",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "forbidden_external_l3_sensitive_inputs"
    assert payload["live_blocker"]["category"] == "safety"
    assert "forbidden_sensitive_inputs_absent" in payload["live_blocker"]["failed_checks"]
    assert "do-not-store" not in json.dumps(payload, ensure_ascii=False)
    assert "123456" not in json.dumps(payload, ensure_ascii=False)
    forbidden_audit = payload["forbidden_input_audit"]
    assert forbidden_audit["forbidden_inputs_present"] is True
    assert forbidden_audit["raw_values_persisted"] is False
    inputs = {item["name"]: item for item in forbidden_audit["inputs"]}
    assert inputs["password"]["present"] is True
    assert inputs["captcha_code"]["present"] is True
    assert inputs["sms_code"]["present"] is False
    assert all(item["raw_value_persisted"] is False for item in inputs.values())
    assert payload["submit_safety_decision"]["forbidden_inputs_present"] is True
    assert (
        payload["submit_safety_decision"]["credentials_or_challenge_inputs_accepted"]
        is False
    )
    readiness = payload["live_run_readiness"]
    assert "forbidden_sensitive_inputs_absent" in readiness["missing_gates"]
    diagnostics = payload["live_blocker"]["diagnostics"]["forbidden_input_audit"]
    assert diagnostics["forbidden_inputs_present"] is True
    assert run_mock.call_count == 0

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    forbidden_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_forbidden_inputs_rejected"
    )
    assert forbidden_rule["status"] == "pass"
    assert "阻断在 submit 命令前" in forbidden_rule["message"]


def test_acceptance_runner_l3_blocks_confirm_job_id_mismatch_before_submit(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123456789.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "987654321",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    payload_text = json.dumps(payload, ensure_ascii=False)
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "target_confirmation_mismatch"
    assert "target_job_id_matches_confirmation" in payload["live_blocker"]["failed_checks"]
    assert "123456789" not in payload_text
    assert "987654321" not in payload_text
    target_audit = payload["target_confirmation_audit"]
    assert target_audit["job_url_has_parseable_job_id"] is True
    assert target_audit["confirm_submit_job_id_present"] is True
    assert target_audit["confirm_submit_recruiter_present"] is True
    assert target_audit["job_id_matches_confirmation"] is False
    assert target_audit["recruiter_page_match_requires_target_verify"] is True
    assert target_audit["raw_values_persisted"] is False
    assert target_audit["raw_recruiter_value_persisted"] is False
    assert (
        payload["submit_safety_decision"]["target_confirmation_audit"]
        == target_audit
    )
    readiness = payload["live_run_readiness"]
    assert "target_job_id_extractable" not in readiness["missing_gates"]
    assert "target_job_id_matches_confirmation" in readiness["missing_gates"]
    diagnostics = payload["live_blocker"]["diagnostics"]["target_confirmation_audit"]
    assert diagnostics["job_id_matches_confirmation"] is False
    assert run_mock.call_count == 0

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    target_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_target_confirmation_matches_url"
    )
    assert target_rule["status"] == "pass"
    assert "阻断 URL 岗位 ID 与确认岗位 ID 不一致" in target_rule["message"]
    assert "recruiter 页面匹配由 target_verify 证明" in target_rule["message"]


def test_acceptance_runner_l3_records_invalid_live_input_gates(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.txt"
    profile = tmp_path / "profile.json"
    resume.write_text("not a pdf\n", encoding="utf-8")
    profile.write_text("{}\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "invalid_live_resume_pdf"
    assert "resume_pdf_file_ready" in payload["live_blocker"]["failed_checks"]
    assert "profile_yaml_file_ready" in payload["live_blocker"]["failed_checks"]
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0
    readiness = payload["live_run_readiness"]
    assert readiness["ready"] is False
    assert "resume_pdf_file_ready" in readiness["missing_gates"]
    assert "profile_yaml_file_ready" in readiness["missing_gates"]
    input_artifacts = payload["live_input_artifacts"]
    files = {item["id"]: item for item in input_artifacts["files"]}
    assert files["resume_pdf"]["suffix"] == ".txt"
    assert files["resume_pdf"]["suffix_valid"] is False
    assert files["resume_pdf"]["sha256"]
    assert files["profile_yaml"]["suffix"] == ".json"
    assert files["profile_yaml"]["suffix_valid"] is False
    assert files["profile_yaml"]["sha256"]
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "blocked_before_command"
    assert submit_decision["live_inputs_ready"] is False
    assert submit_decision["blocking_reason"] == "invalid_live_resume_pdf"


def test_acceptance_runner_l3_records_invalid_job_url_gate(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "ftp://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["live_blocker"]["reason"] == "invalid_live_job_url"
    assert run_mock.call_count == 0
    readiness = payload["live_run_readiness"]
    assert "job_url_valid" in readiness["missing_gates"]
    assert "resume_pdf_file_ready" not in readiness["missing_gates"]
    assert "profile_yaml_file_ready" not in readiness["missing_gates"]


def test_acceptance_runner_l3_blocks_disabled_rate_limit_policy(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
        "PIPF_EXTERNAL_L3_RATE_LIMIT_MAX_PER_BATCH": "0",
        "PIPF_EXTERNAL_L3_SESSION_DIR": ".sessions live",
        "PIPF_EXTERNAL_L3_OUTPUT_DIR": "outputs/custom submissions",
        "PIPF_EXTERNAL_L3_TIMEOUT_SECONDS": "30",
        "PIPF_EXTERNAL_L3_TIMEOUT_MS": "120000",
        "PIPF_EXTERNAL_L3_HEADLESS": "true",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "invalid_external_l3_rate_limit_policy"
    assert payload["rate_limit_policy"]["enabled"] is False
    assert payload["rate_limit_policy"]["max_per_batch"] == 0
    assert (
        "PIPF_EXTERNAL_L3_RATE_LIMIT_MAX_PER_BATCH=0"
        in payload["operator_handoff"]["command_template"]
    )
    runtime_options = payload["operator_handoff"]["runtime_options"]
    assert runtime_options["session_dir"] == ".sessions live"
    assert runtime_options["output_dir"] == "outputs/custom submissions"
    assert runtime_options["timeout_seconds"] == 30
    assert runtime_options["timeout_ms"] == 120000
    assert runtime_options["headless"] is True
    assert (
        "PIPF_EXTERNAL_L3_SESSION_DIR='.sessions live'"
        in payload["operator_handoff"]["command_template"]
    )
    assert (
        "PIPF_EXTERNAL_L3_OUTPUT_DIR='outputs/custom submissions'"
        in payload["operator_handoff"]["command_template"]
    )
    assert (
        "PIPF_EXTERNAL_L3_TIMEOUT_SECONDS=30"
        in payload["operator_handoff"]["command_template"]
    )
    assert (
        "PIPF_EXTERNAL_L3_TIMEOUT_MS=120000"
        in payload["operator_handoff"]["command_template"]
    )
    assert (
        "PIPF_EXTERNAL_L3_HEADLESS=true"
        in payload["operator_handoff"]["command_template"]
    )
    assert (
        payload["live_blocker"]["diagnostics"]["rate_limit_policy"]["enabled"]
        is False
    )
    assert "rate_limit_policy_enabled" in payload["live_run_readiness"]["missing_gates"]
    assert "rate_limit_policy_enabled" in payload["live_blocker"]["failed_checks"]
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_requires_manual_session_ready_before_command(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert (
        payload["live_blocker"]["reason"]
        == "manual_session_ready_confirmation_required"
    )
    assert payload["live_blocker"]["category"] == "session_readiness"
    assert (
        "manual_session_ready_confirmed"
        in payload["live_run_readiness"]["missing_gates"]
    )
    assert payload["session_readiness"]["session_ready_confirmed"] is False
    assert payload["session_readiness"]["manual_login_required"] is True
    assert payload["session_readiness"]["browser_automation_enters_credentials"] is False
    assert payload["submit_safety_decision"]["session_ready_confirmed"] is False
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_requires_prepared_session_storage_before_command(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    missing_session_dir = tmp_path / "missing-session"
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(missing_session_dir),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "manual_session_storage_not_ready"
    assert payload["live_blocker"]["category"] == "session_readiness"
    assert "manual_session_storage_ready" in payload["live_blocker"]["failed_checks"]
    assert payload["session_readiness"]["session_ready_confirmed"] is True
    assert payload["session_readiness"]["session_dir_exists"] is False
    assert payload["session_readiness"]["channel_session_dir_exists"] is False
    assert payload["session_readiness"]["channel_session_dir_has_state"] is False
    assert payload["session_readiness"]["channel_session_state_markers"] == []
    assert payload["session_readiness"]["session_storage_ready"] is False
    assert payload["live_run_readiness"]["submit_command_allowed"] is False
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    session_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_manual_session_ready_confirmed_before_command"
    )
    assert session_rule["status"] == "pass"
    assert "人工会话准备" in session_rule["message"]


def test_acceptance_runner_l3_requires_session_storage_state_before_command(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    session_dir = tmp_path / ".sessions"
    (session_dir / "liepin" / "session" / "liepin").mkdir(parents=True)
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(session_dir),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "manual_session_storage_not_ready"
    assert payload["live_blocker"]["category"] == "session_readiness"
    assert payload["session_readiness"]["session_dir_exists"] is True
    assert payload["session_readiness"]["channel_session_dir_exists"] is True
    assert payload["session_readiness"]["channel_session_dir_has_state"] is False
    assert payload["session_readiness"]["channel_session_state_markers"] == []
    assert payload["session_readiness"]["session_storage_ready"] is False
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_rejects_unrecognized_session_storage_file(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    session_dir = tmp_path / ".sessions"
    channel_session_dir = session_dir / "liepin" / "session" / "liepin"
    channel_session_dir.mkdir(parents=True)
    (channel_session_dir / ".DS_Store").write_bytes(b"not browser state")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(session_dir),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "manual_session_storage_not_ready"
    assert payload["session_readiness"]["channel_session_dir_exists"] is True
    assert payload["session_readiness"]["channel_session_dir_has_state"] is False
    assert payload["session_readiness"]["channel_session_state_markers"] == []
    assert payload["session_readiness"]["session_storage_ready"] is False
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_rejects_empty_session_state_marker(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    session_dir = tmp_path / ".sessions"
    channel_session_dir = session_dir / "liepin" / "session" / "liepin"
    channel_session_dir.mkdir(parents=True)
    (channel_session_dir / "storage-state.json").write_text("", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(session_dir),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "manual_session_storage_not_ready"
    assert payload["session_readiness"]["channel_session_dir_has_state"] is False
    assert payload["session_readiness"]["channel_session_state_markers"] == []
    assert payload["session_readiness"]["session_storage_ready"] is False
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_executes_live_command_only_after_all_gates(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(b"%PDF-1.4\n"),
                            "sha256": hashlib.sha256(b"%PDF-1.4\n").hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(b"id: profile\n"),
                            "sha256": hashlib.sha256(
                                b"id: profile\n"
                            ).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": ""},
                    {"name": "login_check", "status": "success", "detail": ""},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "url_job_id_present=True; dom_jobid_present=True; "
                            "params_jobid_present=True; recruiter_present=True; "
                            "matched_count=1; raw_values_redacted=true"
                        ),
                    },
                    {
                        "name": "submit_safety",
                        "status": "success",
                        "detail": "submit_confirmed:job_id=<redacted>; recruiter=<redacted>",
                    },
                    {"name": "chat_send_resume", "status": "success", "detail": ""},
                    {"name": "submit", "status": "success", "detail": ""},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
        "PIPF_EXTERNAL_L3_HEADLESS": "true",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=(
                "submitted "
                "https://www.liepin.com/job/123.shtml "
                f"{resume} {profile} 123 Verifier\n"
                f"[DONE] submit log: {log_yaml}\n"
            ),
            stderr=(
                "trace "
                "https://www.liepin.com/job/123.shtml "
                f"{resume} {profile} 123 Verifier\n"
            ),
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "external_validated"
    assert payload["external_submission_attempted"] is True
    assert payload["command_redaction"]["raw_live_inputs_persisted"] is False
    assert "--job-url" in payload["command"]
    assert "https://www.liepin.com/job/123.shtml" not in payload["command"]
    assert str(resume) not in payload["command"]
    assert str(profile) not in payload["command"]
    assert "123" not in payload["command"]
    assert "Verifier" not in payload["command"]
    assert payload["command"].count("<redacted>") == 5
    assert payload["live_output_redaction"]["raw_live_inputs_persisted"] is False
    assert set(payload["live_output_redaction"]["redacted_fields"]) == {
        "job_url",
        "resume_pdf_path",
        "profile_path",
        "confirm_submit_job_id",
        "confirm_submit_recruiter",
    }
    assert "https://www.liepin.com/job/123.shtml" not in payload["stdout_tail"]
    assert str(resume) not in payload["stdout_tail"]
    assert str(profile) not in payload["stdout_tail"]
    assert "Verifier" not in payload["stdout_tail"]
    assert "https://www.liepin.com/job/123.shtml" not in payload["stderr_tail"]
    assert str(resume) not in payload["stderr_tail"]
    assert str(profile) not in payload["stderr_tail"]
    assert "Verifier" not in payload["stderr_tail"]
    assert payload["stdout_tail"].count("<redacted>") >= 5
    assert payload["stderr_tail"].count("<redacted>") >= 5
    assert payload["rate_limit_policy"]["enabled"] is True
    assert payload["rate_limit_policy"]["max_per_batch"] == 5
    assert payload["rate_limit_policy"]["cooldown_seconds"] == 900
    assert payload["rate_limit_policy"]["daily_limit"] == 30
    assert payload["coverage"]["explicit_final_submit_gate"] == "pass"
    target_audit = payload["target_confirmation_audit"]
    assert target_audit["job_url_has_parseable_job_id"] is True
    assert target_audit["confirm_submit_job_id_present"] is True
    assert target_audit["confirm_submit_recruiter_present"] is True
    assert target_audit["job_id_matches_confirmation"] is True
    assert target_audit["recruiter_page_match_requires_target_verify"] is True
    assert target_audit["raw_values_persisted"] is False
    assert target_audit["raw_recruiter_value_persisted"] is False
    assert payload["submission_traceability"]["linked_to_validation"] is True
    assert payload["submission_traceability"]["log_links_back_to_validation"] is True
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is True
    )
    assert (
        payload["submission_traceability"][
            "submission_log_input_artifact_basenames_redacted"
        ]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_step_details_redacted"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_browser_artifacts_redacted"]
        is True
    )
    required_steps = payload["submission_traceability"]["submission_log_required_steps"]
    assert required_steps["passed"] is True
    assert required_steps["missing_steps"] == []
    assert [item["name"] for item in required_steps["recorded_steps"]] == [
        "rate_limit",
        "login_check",
        "target_verify",
        "submit_safety",
        "chat_send_resume",
        "submit",
    ]
    assert (
        payload["submission_traceability"]["logged_external_l3_validation_run_id"]
        == "acceptance_external_l3"
    )
    assert (
        payload["submission_traceability"]["logged_external_l3_validation_path"]
        == validation_path
    )
    assert payload["submission_traceability"]["log_yaml_path"] == str(log_yaml)
    assert payload["submission_traceability"]["log_json_path"] == str(log_json)
    assert (
        payload["submission_traceability"]["submission_log_summary"]["mode"]
        == "submit"
    )
    markdown = Path(report.steps[0].evidence).with_suffix(".md").read_text(
        encoding="utf-8"
    )
    assert "- Submission Mode: `submit`" in markdown
    input_artifacts = payload["live_input_artifacts"]
    assert input_artifacts["job_url"]["scheme"] == "https"
    assert input_artifacts["job_url"]["hostname"] == "www.liepin.com"
    assert input_artifacts["job_url"]["raw_value_persisted"] is False
    assert input_artifacts["confirmations"]["confirm_submit_job_id_present"] is True
    assert input_artifacts["confirmations"]["raw_values_persisted"] is False
    files = {item["id"]: item for item in input_artifacts["files"]}
    assert files["resume_pdf"]["basename"] == "<redacted>"
    assert files["resume_pdf"]["basename_persisted"] is False
    assert files["resume_pdf"]["suffix_valid"] is True
    assert files["resume_pdf"]["sha256"] == hashlib.sha256(
        b"%PDF-1.4\n"
    ).hexdigest()
    assert files["profile_yaml"]["basename"] == "<redacted>"
    assert files["profile_yaml"]["basename_persisted"] is False
    assert files["profile_yaml"]["suffix_valid"] is True
    assert files["profile_yaml"]["sha256"] == hashlib.sha256(
        b"id: profile\n"
    ).hexdigest()
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "allowed_and_executed"
    assert submit_decision["submit_command_allowed"] is True
    assert submit_decision["external_submission_attempted"] is True
    assert submit_decision["authorization_confirmed"] is True
    assert submit_decision["final_submit_confirmed"] is True
    assert submit_decision["live_inputs_ready"] is True
    assert submit_decision["blocking_reason"] == ""
    assert submit_decision["post_run_blocker_reason"] == ""
    assert submit_decision["command_returncode"] == 0
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["traceable"] is True
    assert feedback_trace["source_type"] == "submission_log"
    assert feedback_trace["source_status"] == "external_validated"
    assert feedback_trace["source_artifact_path"] == str(log_json)
    assert feedback_trace["feedback_iteration_route"] == "feedback_iteration_after_check_mode"
    assert payload["live_run_readiness"]["ready"] is True
    assert payload["live_run_readiness"]["submit_command_allowed"] is True
    assert payload["live_run_readiness"]["missing_gates"] == []
    assert payload["operator_handoff"]["status"] == "executed_with_guarded_live_result"
    assert payload["outcome_summary"]["outcome"] == "external_validated"
    assert (
        payload["outcome_summary"]["acceptance_status_meaning"]
        == "real_channel_result_recorded"
    )
    assert payload["outcome_summary"]["external_l3_success"] is True
    assert payload["outcome_summary"]["blocker_resolution_required"] is False
    assert payload["outcome_summary"]["p0_017_complete"] is True
    evidence_entries = {
        item["id"]: item for item in payload["evidence_manifest"]["entries"]
    }
    assert payload["evidence_manifest"]["status"] == "complete"
    assert evidence_entries["submission_log_yaml"]["required"] is True
    assert evidence_entries["submission_log_yaml"]["present"] is True
    assert evidence_entries["submission_log_yaml"]["location"] == str(log_yaml)
    assert evidence_entries["submission_log_json"]["required"] is True
    assert evidence_entries["submission_log_json"]["present"] is True
    assert evidence_entries["submission_log_json"]["location"] == str(log_json)
    assert evidence_entries["live_blocker"]["required"] is False
    assert evidence_entries["external_l3_live_run_runbook"]["required"] is True
    assert evidence_entries["external_l3_live_run_runbook"]["present"] is True
    assert evidence_entries["feedback_source_artifact"]["location"] == str(log_json)
    authorization_packet = payload["operator_handoff"]["authorization_packet"]
    assert authorization_packet["status"] == "executed"
    assert authorization_packet["raw_confirmation_values_persisted"] is False
    assert "live_input_artifacts" in authorization_packet["required_evidence"]
    assert run_mock.call_count == 1
    command = run_mock.call_args.args[0]
    assert "--submit" in command
    assert "--headless" in command
    assert "--confirm-submit-job-id" in command
    assert "--external-l3-validation-run-id" in command
    assert (
        command[command.index("--external-l3-validation-run-id") + 1]
        == "acceptance_external_l3"
    )
    assert "--external-l3-validation-path" in command
    assert (
        command[command.index("--external-l3-validation-path") + 1]
        == validation_path
    )
    assert "--rate-limit-max-per-batch" in command
    assert command[command.index("--rate-limit-max-per-batch") + 1] == "5"
    assert "--rate-limit-cooldown-seconds" in command
    assert command[command.index("--rate-limit-cooldown-seconds") + 1] == "900"
    assert "--rate-limit-daily-limit" in command
    assert command[command.index("--rate-limit-daily-limit") + 1] == "30"


def test_acceptance_runner_l3_blocks_zero_returncode_when_submission_log_failed(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text(
        'status: "failed"\nerror: "target_verify_failed"\n',
        encoding="utf-8",
    )
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "failed",
                "error": "target_verify_failed",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": "ok"},
                    {"name": "login_check", "status": "success", "detail": "ok"},
                    {
                        "name": "target_verify",
                        "status": "failed",
                        "detail": (
                            "job_id_present=true; recruiter_present=true; "
                            "raw_values_redacted=true"
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["returncode"] == 0
    assert (
        payload["live_blocker"]["reason"]
        == "external_channel_target_verify_failed"
    )
    assert (
        "external submit was attempted and blocked after command"
        in report.steps[0].message
    )
    assert payload["submission_traceability"]["linked_to_validation"] is True
    assert payload["submission_traceability"]["submission_log_status_success"] is False
    assert (
        "submission_log_status_success"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert "submission_log_status_success" in payload["live_blocker"]["failed_checks"]
    assert (
        payload["submit_safety_decision"]["post_run_blocker_reason"]
        == "external_channel_target_verify_failed"
    )
    assert (
        payload["post_submit_feedback_traceability"]["source_reason"]
        == "external_channel_target_verify_failed"
    )
    assert payload["outcome_summary"]["external_l3_success"] is False
    assert payload["outcome_summary"]["p0_017_complete"] is False


def test_acceptance_runner_l3_promotes_target_verify_submission_log_error(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "target_verify"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    input_artifacts = {
        "job_url": {
            "present": True,
            "scheme": "https",
            "hostname": "www.liepin.com",
            "supported_scheme": True,
            "raw_value_persisted": False,
        },
        "files": [
            {
                "id": "resume_pdf",
                "basename": "<redacted>",
                "basename_persisted": False,
                "suffix": ".pdf",
                "size_bytes": len(resume_bytes),
                "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
            {
                "id": "profile_yaml",
                "basename": "<redacted>",
                "basename_persisted": False,
                "suffix": ".yaml",
                "size_bytes": len(profile_bytes),
                "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
        ],
    }
    log_yaml.write_text(
        'status: "failed"\nerror: "target_mismatch"\n',
        encoding="utf-8",
    )
    log_json.write_text(
        json.dumps(
            {
                "status": "failed",
                "error": "target_mismatch",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": input_artifacts,
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": "ok"},
                    {"name": "login_check", "status": "success", "detail": "ok"},
                    {
                        "name": "target_verify",
                        "status": "failed",
                        "detail": (
                            "job_id_present=true; recruiter_present=true; "
                            "raw_values_redacted=true"
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=12,
            stdout=f"[INFO] log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["returncode"] == 12
    assert (
        payload["live_blocker"]["reason"]
        == "external_channel_target_verify_failed"
    )
    assert (
        payload["submit_safety_decision"]["post_run_blocker_reason"]
        == "external_channel_target_verify_failed"
    )
    summary = payload["submission_traceability"]["submission_log_summary"]
    assert summary["status"] == "failed"
    assert summary["error"] == "target_mismatch"
    assert summary["mode"] == "submit"
    assert summary["last_step"]["name"] == "target_verify"
    assert (
        payload["live_blocker"]["diagnostics"]["submission_log_summary"]
        == summary
    )
    assert payload["submission_traceability"]["linked_to_validation"] is True
    assert "submission_log_status_success" in payload["live_blocker"]["failed_checks"]
    assert payload["outcome_summary"]["external_l3_success"] is False
    assert payload["outcome_summary"]["p0_017_complete"] is False

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "pass"
    assert "external_channel_target_verify_failed" in diagnostics_rule["message"]

    missing_mode_payload = json.loads(json.dumps(payload))
    del missing_mode_payload["submission_traceability"]["submission_log_summary"][
        "mode"
    ]
    Path(report.steps[0].evidence).write_text(
        json.dumps(missing_mode_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["status"] == "fail"
    assert "mode" in summary_rule["message"]

    payload["live_blocker"]["reason"] = "external_channel_command_returned_nonzero"
    Path(report.steps[0].evidence).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "fail"
    assert "expected=external_channel_target_verify_failed" in diagnostics_rule["message"]


def test_acceptance_runner_l3_promotes_send_resume_prefixed_error(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "send_resume"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    input_artifacts = {
        "job_url": {
            "present": True,
            "scheme": "https",
            "hostname": "www.liepin.com",
            "supported_scheme": True,
            "raw_value_persisted": False,
        },
        "files": [
            {
                "id": "resume_pdf",
                "basename": "<redacted>",
                "basename_persisted": False,
                "suffix": ".pdf",
                "size_bytes": len(resume_bytes),
                "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
            {
                "id": "profile_yaml",
                "basename": "<redacted>",
                "basename_persisted": False,
                "suffix": ".yaml",
                "size_bytes": len(profile_bytes),
                "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
        ],
    }
    log_yaml.write_text(
        'status: "failed"\nerror: "main_chat_click_failed:TimeoutError"\n',
        encoding="utf-8",
    )
    log_json.write_text(
        json.dumps(
            {
                "status": "failed",
                "error": "main_chat_click_failed:TimeoutError",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": input_artifacts,
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": "ok"},
                    {"name": "login_check", "status": "success", "detail": "ok"},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "job_id_present=true; recruiter_present=true; "
                            "raw_values_redacted=true"
                        ),
                    },
                    {"name": "submit_safety", "status": "success", "detail": "ok"},
                    {
                        "name": "chat_send_resume",
                        "status": "failed",
                        "detail": "main_chat_click_failed:<redacted>",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=13,
            stdout=f"[INFO] log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "external_channel_send_resume_failed"
    assert (
        payload["submit_safety_decision"]["post_run_blocker_reason"]
        == "external_channel_send_resume_failed"
    )
    assert (
        payload["post_submit_feedback_traceability"]["source_reason"]
        == "external_channel_send_resume_failed"
    )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "pass"
    assert "external_channel_send_resume_failed" in diagnostics_rule["message"]


def test_external_l3_maps_real_liepin_send_resume_errors() -> None:
    for error in (
        "main_chat_click_failed:TimeoutError",
        "send_resume_click_failed:TimeoutError",
        "confirm_send_button_not_found",
        "upload input not found after phases: direct, upload_trigger, apply_dialog",
        "phase=apply_dialog; chooser=phase=apply_dialog; trigger failed",
    ):
        assert (
            submission_log_error_blocker_reason({"error": error})
            == "external_channel_send_resume_failed"
        )


def test_acceptance_runner_l3_blocks_submission_log_with_raw_live_inputs(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "https://www.liepin.com/job/123.shtml",
                "resume_path": str(resume),
                "profile_path": str(profile),
                "live_inputs_redacted": False,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is False
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert (
        "submission_log_raw_live_inputs_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "submission_log_raw_live_inputs_redacted"
        in payload["live_blocker"]["failed_checks"]
    )


def test_acceptance_runner_l3_requires_submission_log_redaction_flag(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": False,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is False
    )
    assert (
        "submission_log_raw_live_inputs_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )


def test_acceptance_runner_l3_blocks_submission_log_with_raw_step_details(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": ""},
                    {"name": "login_check", "status": "success", "detail": ""},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "url=https://www.liepin.com/job/123.shtml; "
                            f"resume={resume}; profile={profile}; "
                            "job_id=123; recruiter=Verifier"
                        ),
                    },
                    {
                        "name": "submit_safety",
                        "status": "success",
                        "detail": "submit_confirmed:job_id=123; recruiter=Verifier",
                    },
                    {"name": "chat_send_resume", "status": "success", "detail": ""},
                    {
                        "name": "submit",
                        "status": "success",
                        "detail": (
                            "submit completed for "
                            "https://www.liepin.com/job/123.shtml "
                            f"{resume} {profile} 123 Verifier"
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_step_details_redacted"]
        is False
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert (
        "submission_log_step_details_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "submission_log_step_details_redacted"
        in payload["live_blocker"]["failed_checks"]
    )
    summary_detail = payload["submission_traceability"]["submission_log_summary"][
        "last_step"
    ]["detail"]
    assert "https://www.liepin.com/job/123.shtml" not in summary_detail
    assert str(resume) not in summary_detail
    assert str(profile) not in summary_detail
    assert "Verifier" not in summary_detail
    assert "<redacted>" in summary_detail
    validation_text = Path(report.steps[0].evidence).read_text(encoding="utf-8")
    assert "https://www.liepin.com/job/123.shtml" not in validation_text
    assert str(resume) not in validation_text
    assert str(profile) not in validation_text
    assert "Verifier" not in validation_text


def test_acceptance_runner_l3_blocks_legacy_target_verify_detail_shape(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": ""},
                    {"name": "login_check", "status": "success", "detail": ""},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "url_job_id=<redacted>; dom_jobid=987654; "
                            "params_jobid=987654; recruiter=ExternalPerson"
                        ),
                    },
                    {
                        "name": "submit_safety",
                        "status": "success",
                        "detail": "submit_confirmed:job_id=<redacted>; recruiter=<redacted>",
                    },
                    {"name": "chat_send_resume", "status": "success", "detail": ""},
                    {"name": "submit", "status": "success", "detail": ""},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert (
        payload["submission_traceability"]["submission_log_step_details_redacted"]
        is False
    )
    assert (
        "submission_log_step_details_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )


def test_acceptance_runner_l3_redacts_unsafe_submission_summary_detail(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "failed"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "failed",
                "error": "target_verify_failed",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": "ok"},
                    {"name": "login_check", "status": "success", "detail": "ok"},
                    {
                        "name": "target_verify",
                        "status": "failed",
                        "detail": (
                            "url_job_id=<redacted>; dom_jobid=987654; "
                            "params_jobid=987654; recruiter=ExternalPerson"
                        ),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert (
        payload["submission_traceability"]["submission_log_step_details_redacted"]
        is False
    )
    summary_last_step = payload["submission_traceability"]["submission_log_summary"][
        "last_step"
    ]
    assert summary_last_step["name"] == "target_verify"
    assert summary_last_step["detail"] == "<redacted>"
    assert summary_last_step["detail_redacted_due_to_unsafe_content"] is True
    validation_text = Path(report.steps[0].evidence).read_text(encoding="utf-8")
    assert "987654" not in validation_text
    assert "ExternalPerson" not in validation_text

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["status"] == "pass"


def test_acceptance_runner_l3_blocks_submission_log_with_browser_artifacts(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": ""},
                    {"name": "login_check", "status": "success", "detail": ""},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "url_job_id_present=True; dom_jobid_present=True; "
                            "params_jobid_present=True; recruiter_present=True; "
                            "matched_count=1; raw_values_redacted=true"
                        ),
                    },
                    {
                        "name": "dom_snapshot",
                        "status": "success",
                        "detail": (
                            "raw_browser_artifacts_persisted=false; "
                            "reason=external_l3_redaction_policy"
                        ),
                        "diagnostics": {
                            "screenshot_path": "screenshots/03_target_verify.png",
                            "html_snapshot_path": "html/01_main_page.html",
                        },
                    },
                    {
                        "name": "submit_safety",
                        "status": "success",
                        "detail": "submit_confirmed:job_id=<redacted>; recruiter=<redacted>",
                    },
                    {"name": "chat_send_resume", "status": "success", "detail": ""},
                    {"name": "submit", "status": "success", "detail": ""},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert (
        payload["submission_traceability"][
            "submission_log_browser_artifacts_redacted"
        ]
        is False
    )
    assert (
        "submission_log_browser_artifacts_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "submission_log_browser_artifacts_redacted"
        in payload["live_blocker"]["failed_checks"]
    )


def test_acceptance_runner_l3_blocks_success_log_without_required_steps(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": ""},
                    {"name": "login_check", "status": "success", "detail": ""},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    required_steps = payload["submission_traceability"]["submission_log_required_steps"]
    assert required_steps["passed"] is False
    assert required_steps["missing_steps"] == [
        "target_verify",
        "submit_safety",
        "chat_send_resume",
        "submit",
    ]
    assert (
        "successful_submission_required_steps_present"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "successful_submission_required_steps_present"
        in payload["live_blocker"]["failed_checks"]
    )
    diagnostic_steps = payload["live_blocker"]["diagnostics"][
        "submission_log_required_steps"
    ]
    assert diagnostic_steps["missing_steps"] == required_steps["missing_steps"]
    markdown_path = Path(report.steps[0].evidence).with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert (
        "- 成功投递必需步骤: "
        "`rate_limit, login_check, target_verify, submit_safety, chat_send_resume, submit`"
    ) in markdown
    assert "- 已记录投递步骤: `rate_limit:success, login_check:success`" in markdown
    assert (
        "- 缺失投递步骤: `target_verify, submit_safety, chat_send_resume, submit`"
        in markdown
    )
    assert "- 失败投递步骤: ``" in markdown
    assert (
        "- 诊断缺失投递步骤: `target_verify, submit_safety, chat_send_resume, submit`"
        in markdown
    )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    required_steps_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_required_steps_recorded"
    )
    assert required_steps_rule["status"] == "pass"
    assert "关键步骤缺失记录为 traceability blocker" in required_steps_rule["message"]

    markdown_path.write_text(
        markdown.replace(
            "- 诊断缺失投递步骤: `target_verify, submit_safety, chat_send_resume, submit`",
            "- 诊断缺失投递步骤: `submit`",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "fail"
    assert "markdown:- 诊断缺失投递步骤" in diagnostics_rule["message"]
    markdown_path.write_text(markdown, encoding="utf-8")

    markdown_path.write_text(
        markdown.replace(
            "- 缺失投递步骤: `target_verify, submit_safety, chat_send_resume, submit`",
            "- 缺失投递步骤: `submit`",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    required_steps_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_required_steps_recorded"
    )
    assert required_steps_rule["status"] == "fail"
    assert "markdown:- 缺失投递步骤" in required_steps_rule["message"]
    markdown_path.write_text(markdown, encoding="utf-8")


def test_acceptance_runner_l3_blocks_success_without_submission_log(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(returncode=0, stdout="[DONE] submit log: missing\n", stderr="")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert payload["live_run_readiness"]["ready"] is True
    assert payload["live_run_readiness"]["submit_command_allowed"] is True
    assert payload["live_run_readiness"]["blocking_reason"] == ""
    assert payload["live_run_readiness"]["missing_gates"] == []
    assert payload["live_blocker"]["failed_checks"] == [
        "submission_log_hint_found",
        "submission_log_yaml_exists",
        "submission_log_json_exists",
        "submission_log_json_parseable",
        "external_l3_validation_run_id_matches",
        "external_l3_validation_path_matches",
        "input_artifacts_match_validation",
        "submission_log_input_artifact_basenames_redacted",
        "submission_log_raw_live_inputs_redacted",
        "submission_log_step_details_redacted",
        "submission_log_browser_artifacts_redacted",
        "successful_submission_required_steps_present",
    ]
    assert payload["live_blocker"]["diagnostics"]["returncode"] == 0
    assert (
        payload["live_blocker"]["diagnostics"][
            "submission_traceability_failed_checks"
        ]
        == payload["live_blocker"]["failed_checks"]
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert "submission_log_hint_found" in payload["submission_traceability"]["failed_checks"]
    assert "submission_log_json_exists" in payload["submission_traceability"]["failed_checks"]
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "allowed_and_executed"
    assert submit_decision["submit_command_allowed"] is True
    assert submit_decision["post_run_blocker_reason"] == "submission_log_not_linked"
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["traceable"] is True
    assert feedback_trace["source_type"] == "live_blocker"
    assert feedback_trace["source_status"] == "external_submission_attempted_blocked"
    assert feedback_trace["source_reason"] == "submission_log_not_linked"

    markdown_path = Path(report.steps[0].evidence).with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "- Failed Checks: `submission_log_hint_found" in markdown
    expected_row = (
        "| `submission_log_json_exists` | `fail` | "
        "submission_log.json 存在 |"
    )
    assert expected_row in markdown
    markdown_path.write_text(
        markdown.replace(expected_row, expected_row.replace("`fail`", "`pass`")),
        encoding="utf-8",
    )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["status"] == "fail"
    assert "submission_log_json_exists.markdown_check_row" in summary_rule["message"]
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_post_command_blocker_diagnostics_recorded"
        )
    )
    assert diagnostics_rule["status"] == "pass"


def test_acceptance_runner_l3_promotes_rate_limit_submission_log_summary(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "rate_limited"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    validation_path = (
        "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    )
    input_artifacts = {
        "job_url": {
            "scheme": "https",
            "hostname": "www.liepin.com",
            "raw_value_persisted": False,
        },
        "files": [
            {
                "id": "resume_pdf",
                "basename": "<redacted>",
                "basename_persisted": False,
                "suffix": ".pdf",
                "size_bytes": len(resume_bytes),
                "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
            {
                "id": "profile_yaml",
                "basename": "<redacted>",
                "basename_persisted": False,
                "suffix": ".yaml",
                "size_bytes": len(profile_bytes),
                "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
        ],
    }
    log_yaml.write_text('status: "blocked"\nerror: "batch_cooldown"\n', encoding="utf-8")
    log_json.write_text(
        json.dumps(
            {
                "status": "blocked",
                "error": "batch_cooldown",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": input_artifacts,
                "steps": [
                    {
                        "name": "rate_limit",
                        "status": "blocked",
                        "detail": (
                            "batch_cooldown; wait_seconds=385; "
                            "batch_count=5; daily_count=7"
                        ),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=14,
            stdout=f"[INFO] log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["returncode"] == 14
    assert payload["live_blocker"]["reason"] == "external_channel_rate_limited"
    summary = payload["submission_traceability"]["submission_log_summary"]
    assert summary["status"] == "blocked"
    assert summary["error"] == "batch_cooldown"
    assert summary["mode"] == "submit"
    assert summary["last_step"]["name"] == "rate_limit"
    assert summary["last_step"]["status"] == "blocked"
    assert (
        payload["live_blocker"]["diagnostics"]["submission_log_summary"]
        == summary
    )
    assert payload["submission_traceability"]["linked_to_validation"] is True
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is True
    )
    assert payload["submit_safety_decision"]["post_run_blocker_reason"] == (
        "external_channel_rate_limited"
    )
    markdown = (
        Path(report.steps[0].evidence).parent / "external-l3-validation.md"
    ).read_text(encoding="utf-8")
    assert "- Submission Status: `blocked`" in markdown
    assert "- Submission Error: `batch_cooldown`" in markdown
    assert "- Last Step: `rate_limit/blocked`" in markdown
    assert "- 来源状态: `external_submission_attempted_blocked`" in markdown
    assert "- 来源原因: `external_channel_rate_limited`" in markdown
    assert "- Submission log 输入产物文件名是否脱敏: `True`" in markdown
    assert "- Submission log 原始浏览器产物是否脱敏: `True`" in markdown

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    outcome_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_outcome_summary_recorded"
    )
    assert outcome_rule["status"] == "pass"
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "pass"
    assert "external_channel_rate_limited" in diagnostics_rule["message"]
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["status"] == "pass"
    assert "blocked/batch_cooldown" in summary_rule["message"]

    markdown_path = Path(report.steps[0].evidence).with_suffix(".md")
    original_markdown = markdown_path.read_text(encoding="utf-8")
    markdown_path.write_text(
        original_markdown.replace(
            "- Returncode: `14`",
            "- Returncode: `0`",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "fail"
    assert "markdown:- Returncode: `14`" in diagnostics_rule["message"]
    markdown_path.write_text(original_markdown, encoding="utf-8")

    markdown_path.write_text(
        original_markdown.replace(
            "- 下一步: 真实渠道频控已阻断本次 submit；等待 submission log 中记录的 "
            "wait_seconds 或调整下一次验证窗口后再重试。",
            "- 下一步: 处理另一个 blocker",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    outcome_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_outcome_summary_recorded"
    )
    assert outcome_rule["status"] == "fail"
    assert "markdown_next_action" in outcome_rule["message"]
    markdown_path.write_text(original_markdown, encoding="utf-8")

    markdown_path.write_text(
        original_markdown.replace(
            "- 来源原因: `external_channel_rate_limited`",
            "- 来源原因: `external_channel_command_returned_nonzero`",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    feedback_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_submit_feedback_traceable"
    )
    assert feedback_rule["status"] == "fail"
    assert "来源原因" in feedback_rule["message"]
    markdown_path.write_text(original_markdown, encoding="utf-8")

    inconsistent_submit_decision = json.loads(json.dumps(payload))
    inconsistent_submit_decision["submit_safety_decision"][
        "post_run_blocker_reason"
    ] = "external_channel_command_returned_nonzero"
    Path(report.steps[0].evidence).write_text(
        json.dumps(inconsistent_submit_decision, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    submit_safety_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submit_safety_decision_recorded"
    )
    assert submit_safety_rule["status"] == "fail"
    assert "post_run_blocker_reason" in submit_safety_rule["message"]

    inconsistent_feedback_trace = json.loads(json.dumps(payload))
    inconsistent_feedback_trace["post_submit_feedback_traceability"][
        "source_reason"
    ] = "external_channel_command_returned_nonzero"
    Path(report.steps[0].evidence).write_text(
        json.dumps(inconsistent_feedback_trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    feedback_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_submit_feedback_traceable"
    )
    assert feedback_rule["status"] == "fail"
    assert "source_reason" in feedback_rule["message"]

    inconsistent_outcome_summary = json.loads(json.dumps(payload))
    inconsistent_outcome_summary["outcome_summary"][
        "next_action"
    ] = "处理另一个 blocker"
    Path(report.steps[0].evidence).write_text(
        json.dumps(inconsistent_outcome_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    outcome_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_outcome_summary_recorded"
    )
    assert outcome_rule["status"] == "fail"
    assert "next_action_matches_live_blocker" in outcome_rule["message"]

    payload["live_blocker"]["reason"] = "external_channel_command_returned_nonzero"
    Path(report.steps[0].evidence).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_command_blocker_diagnostics_recorded"
    )
    assert diagnostics_rule["status"] == "fail"
    assert "expected=external_channel_rate_limited" in diagnostics_rule["message"]


def test_acceptance_runner_l3_records_timeout_as_live_blocker(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["submit"],
            timeout=10,
            output=f"partial https://www.liepin.com/job/123.shtml {resume}",
            stderr=f"slow {profile} Verifier",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is True
    assert payload["command_timed_out"] is True
    assert payload["timeout_seconds"] == 10
    assert payload["returncode"] is None
    assert payload["live_blocker"]["reason"] == "external_channel_command_timed_out"
    assert payload["live_blocker"]["diagnostics"]["command_timed_out"] is True
    assert payload["live_blocker"]["diagnostics"]["timeout_seconds"] == 10
    assert payload["submit_safety_decision"]["post_run_blocker_reason"] == (
        "external_channel_command_timed_out"
    )
    assert "https://www.liepin.com/job/123.shtml" not in payload["stdout_tail"]
    assert str(resume) not in payload["stdout_tail"]
    assert str(profile) not in payload["stderr_tail"]
    assert "Verifier" not in payload["stderr_tail"]
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["source_type"] == "live_blocker"
    assert feedback_trace["source_status"] == "external_submission_attempted_blocked"
    assert feedback_trace["source_reason"] == "external_channel_command_timed_out"
    markdown_path = Path(report.steps[0].evidence).with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "- Reason: `external_channel_command_timed_out`" in markdown
    assert "- 是否超时: `True`" in markdown
    assert "- Timeout 秒数: `10`" in markdown

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    timeout_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_timeout_recorded_as_live_blocker"
    )
    assert timeout_rule["status"] == "pass"
    assert "超时已记录" in timeout_rule["message"]

    markdown_path.write_text(
        markdown.replace("- Timeout 秒数: `10`", "- Timeout 秒数: ``"),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    timeout_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_timeout_recorded_as_live_blocker"
    )
    assert timeout_rule["status"] == "fail"
    assert "Timeout 秒数" in timeout_rule["message"]


def test_acceptance_runner_l3_records_command_error_as_live_blocker(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.side_effect = OSError(
            f"browser failed for https://www.liepin.com/job/123.shtml {resume}"
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is True
    assert payload["returncode"] is None
    assert payload["live_blocker"]["reason"] == (
        "external_channel_command_launch_failed"
    )
    command_error = payload["live_blocker"]["diagnostics"]["command_error"]
    assert command_error["type"] == "OSError"
    assert "https://www.liepin.com/job/123.shtml" not in command_error["message"]
    assert str(resume) not in command_error["message"]
    assert "<redacted>" in command_error["message"]
    assert payload["command_error"] == command_error
    assert payload["submit_safety_decision"]["post_run_blocker_reason"] == (
        "external_channel_command_launch_failed"
    )
    markdown_path = Path(report.steps[0].evidence).with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "- Reason: `external_channel_command_launch_failed`" in markdown
    assert "- Command Error: `OSError`" in markdown
    assert f"- Command Error Message: `{command_error['message']}`" in markdown
    assert "https://www.liepin.com/job/123.shtml" not in markdown
    assert str(resume) not in markdown

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    command_error_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_command_error_recorded_as_live_blocker"
        )
    )
    assert command_error_rule["status"] == "pass"
    assert "启动错误已记录" in command_error_rule["message"]

    markdown_path.write_text(
        markdown.replace("- Command Error: `OSError`", "- Command Error: ``"),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    command_error_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_command_error_recorded_as_live_blocker"
        )
    )
    assert command_error_rule["status"] == "fail"
    assert "Command Error" in command_error_rule["message"]


def test_acceptance_runner_l3_blocks_submission_log_with_raw_input_artifact_basenames(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": (
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
                "input_artifacts": {
                    "job_url": {
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "resume.pdf",
                            "basename_persisted": True,
                            "suffix": ".pdf",
                            "size_bytes": len(b"%PDF-1.4\n"),
                            "sha256": hashlib.sha256(b"%PDF-1.4\n").hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "profile.yaml",
                            "basename_persisted": True,
                            "suffix": ".yaml",
                            "size_bytes": len(b"id: profile\n"),
                            "sha256": hashlib.sha256(
                                b"id: profile\n"
                            ).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": "ok"},
                    {"name": "login_check", "status": "success", "detail": "ok"},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "job_id_present=true; recruiter_present=true; "
                            "raw_values_redacted=true"
                        ),
                    },
                    {"name": "submit_safety", "status": "success", "detail": "ok"},
                    {
                        "name": "chat_send_resume",
                        "status": "success",
                        "detail": "ok",
                    },
                    {"name": "submit", "status": "success", "detail": "ok"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert payload["live_run_readiness"]["ready"] is True
    assert payload["live_run_readiness"]["submit_command_allowed"] is True
    assert payload["live_run_readiness"]["blocking_reason"] == ""
    assert payload["live_run_readiness"]["missing_gates"] == []
    assert payload["submission_traceability"]["log_links_back_to_validation"] is True
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is False
    )
    assert (
        payload["submission_traceability"][
            "submission_log_input_artifact_basenames_redacted"
        ]
        is False
    )
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_step_details_redacted"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_required_steps"]["passed"]
        is True
    )
    assert (
        "input_artifacts_match_validation"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "submission_log_input_artifact_basenames_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert (
        "input_artifacts_match_validation"
        in payload["live_blocker"]["failed_checks"]
    )
    assert (
        "submission_log_input_artifact_basenames_redacted"
        in payload["live_blocker"]["failed_checks"]
    )
    assert payload["live_blocker"]["diagnostics"]["log_yaml_path"] == str(log_yaml)
    assert payload["live_blocker"]["diagnostics"]["log_json_path"] == str(log_json)


def test_acceptance_runner_l3_blocks_submission_log_with_raw_job_url_artifact_flag(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": (
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
                "input_artifacts": {
                    "job_url": {
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "raw_value_persisted": True,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "<redacted>",
                            "basename_persisted": False,
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
                "steps": [
                    {"name": "rate_limit", "status": "success", "detail": "ok"},
                    {"name": "login_check", "status": "success", "detail": "ok"},
                    {
                        "name": "target_verify",
                        "status": "success",
                        "detail": (
                            "job_id_present=true; recruiter_present=true; "
                            "raw_values_redacted=true"
                        ),
                    },
                    {"name": "submit_safety", "status": "success", "detail": "ok"},
                    {"name": "chat_send_resume", "status": "success", "detail": "ok"},
                    {"name": "submit", "status": "success", "detail": "ok"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is False
    )
    assert (
        "input_artifacts_match_validation"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "input_artifacts_match_validation"
        in payload["live_blocker"]["failed_checks"]
    )


def test_acceptance_runner_l3_rejects_submission_log_outside_allowed_root(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    outside_log_dir = tmp_path / "outside-submissions"
    outside_log_dir.mkdir()
    log_yaml = outside_log_dir / "submission_log.yaml"
    log_json = outside_log_dir / "submission_log.json"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": (
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_SESSION_DIR": str(_external_l3_session_dir(tmp_path)),
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    traceability = payload["submission_traceability"]
    assert traceability["log_path_within_allowed_root"] is False
    assert traceability["log_yaml_path"] == ""
    assert traceability["log_json_path"] == ""
    assert traceability["log_json_exists"] is False
    assert traceability["rejected_log_yaml_path_reason"] == (
        "outside_allowed_submission_root"
    )
    assert (
        "submission_log_path_within_allowed_root"
        in traceability["failed_checks"]
    )
    assert (
        "submission_log_path_within_allowed_root"
        in payload["live_blocker"]["failed_checks"]
    )
    evidence_path = Path(report.steps[0].evidence)
    validation_text = evidence_path.read_text(encoding="utf-8")
    assert str(log_yaml) not in validation_text
    markdown_path = evidence_path.with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "- Submission log 路径在允许根目录内: `False`" in markdown
    allowed_root = tmp_path / "outputs" / "submissions" / "liepin"
    assert f"- 允许 submission log 根目录: `{allowed_root}`" in markdown
    assert "- 拒绝 submission log 路径原因: `outside_allowed_submission_root`" in markdown
    assert str(log_yaml) not in markdown

    markdown_path.write_text(
        markdown.replace(
            "- 拒绝 submission log 路径原因: `outside_allowed_submission_root`",
            "- 拒绝 submission log 路径原因: ``",
        ),
        encoding="utf-8",
    )
    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["status"] == "fail"
    assert "拒绝 submission log 路径原因" in summary_rule["message"]


def test_acceptance_runner_failure_returns_fail(tmp_path: Path) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=1, stdout="", stderr="boom")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    assert report.status == "fail"
    assert report.steps[0].status == "fail"
    assert "L1 scenario validation failed" in report.steps[0].message
    assert report.steps[0].stderr_tail.endswith("boom")


def test_acceptance_runner_timeout_returns_fail(tmp_path: Path) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["pytest"],
            timeout=10,
            output="partial",
            stderr="slow",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    assert report.status == "fail"
    assert report.steps[0].status == "fail"
    assert "timed out" in report.steps[0].message
    assert report.steps[0].stdout_tail.endswith("partial")


def test_write_acceptance_report_outputs_json_markdown_and_journey_report(
    tmp_path: Path,
) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="l1 ok", stderr="")
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    json_path, markdown_path, journey_json_path, journey_markdown_path = (
        write_acceptance_report(tmp_path, report)
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["summary"]["L1"] == "pass"
    assert payload["steps"][0]["name"] == "first_launch_configure_lm_studio"
    assert payload["steps"][1]["name"] == "setup_profile_and_material_library"

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# PiProofForge Acceptance Runner" in markdown
    assert "setup_profile_and_material_library" in markdown

    assert journey_json_path.name == "journey-report.json"
    assert journey_markdown_path.name == "journey-report.md"
    assert journey_json_path.exists()
    assert journey_markdown_path.exists()
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    material_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "profile_and_materials_persisted"
    )
    assert material_rule["status"] == "pass"
    evidence_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "evidence_card_requires_review"
    )
    assert evidence_rule["status"] == "pass"
    job_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "job_target_ready_for_runs"
    )
    assert job_rule["status"] == "pass"
    quick_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "quick_run_outputs_are_traceable"
    )
    assert quick_rule["status"] == "pass"
    agent_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "agent_run_batch_is_guarded"
    )
    assert agent_rule["status"] == "pass"
    channel_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "channel_session_validity_is_positive_signal_based"
    )
    assert channel_rule["status"] == "pass"
    check_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "check_mode_never_final_submits"
    )
    assert check_rule["status"] == "pass"
    feedback_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "feedback_iteration_preserves_traceability"
    )
    assert feedback_rule["status"] == "pass"
    visible_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "lm_studio_visible_to_run_pages"
    )
    assert visible_rule["level"] == "L2"
    assert visible_rule["status"] == "not_started"


def test_build_run_id_uses_acceptance_prefix() -> None:
    assert build_run_id().startswith("acceptance_")
