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
    assert [step.level for step in report.steps] == ["L1"]
    assert run_mock.call_args.args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_first_launch_configure_lm_studio.py",
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
    assert [step.level for step in report.steps] == ["L1", "L2", "L3"]
    assert [step.status for step in report.steps] == ["pass", "not_started", "not_started"]
    assert run_mock.call_count == 1


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
    assert report.steps[0].stderr_tail == "boom"


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
    assert report.steps[0].stdout_tail == "partial"


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

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# PiProofForge Acceptance Runner" in markdown
    assert "first_launch_configure_lm_studio" in markdown

    assert journey_json_path.name == "journey-report.json"
    assert journey_markdown_path.name == "journey-report.md"
    assert journey_json_path.exists()
    assert journey_markdown_path.exists()
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    visible_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "lm_studio_visible_to_run_pages"
    )
    assert visible_rule["level"] == "L2"
    assert visible_rule["status"] == "not_started"


def test_build_run_id_uses_acceptance_prefix() -> None:
    assert build_run_id().startswith("acceptance_")
