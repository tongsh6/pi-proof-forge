from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from tools.acceptance.acceptance_runner import (
    build_run_id,
    run_acceptance,
    write_acceptance_report,
)


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


def test_acceptance_runner_all_includes_gated_unimplemented_levels(
    tmp_path: Path,
) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
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
        "not_started",
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
