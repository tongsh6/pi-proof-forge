from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from tools.acceptance.demo_readiness import run_readiness, write_readiness_report


def test_readiness_runs_core_demo_by_default(tmp_path: Path) -> None:
    with patch("tools.acceptance.demo_readiness.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="core ok", stderr="")

        report = run_readiness(
            root=tmp_path,
            run_id="ready_test",
            include_gui=False,
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert [step.name for step in report.steps] == ["core demo"]
    assert run_mock.call_count == 1
    assert "tools.acceptance.demo_run" in run_mock.call_args.args[0]


def test_readiness_can_include_quick_run_native_verifier(tmp_path: Path) -> None:
    with patch("tools.acceptance.demo_readiness.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="ok", stderr="")

        report = run_readiness(
            root=tmp_path,
            run_id="ready_test",
            include_gui=True,
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert [step.name for step in report.steps] == [
        "core demo",
        "quick run native verifier",
    ]
    assert run_mock.call_count == 2
    assert run_mock.call_args_list[1].args[0] == [
        "pnpm",
        "--dir",
        "ui",
        "run",
        "e2e:quick-run",
    ]


def test_readiness_fails_when_a_step_fails(tmp_path: Path) -> None:
    with patch("tools.acceptance.demo_readiness.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=1, stdout="", stderr="boom")

        report = run_readiness(
            root=tmp_path,
            run_id="ready_test",
            include_gui=False,
            timeout_seconds=10,
        )

    assert report.status == "fail"
    assert report.steps[0].status == "fail"
    assert "inspect the demo report" in report.steps[0].message


def test_readiness_reports_timeout_as_failure(tmp_path: Path) -> None:
    with patch("tools.acceptance.demo_readiness.subprocess.run") as run_mock:
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["python3"],
            timeout=10,
            output="partial",
            stderr="slow",
        )

        report = run_readiness(
            root=tmp_path,
            run_id="ready_test",
            include_gui=False,
            timeout_seconds=10,
        )

    assert report.status == "fail"
    assert report.steps[0].status == "fail"
    assert "timed out" in report.steps[0].message
    assert report.steps[0].stdout_tail == "partial"


def test_write_readiness_report_outputs_json_and_markdown(tmp_path: Path) -> None:
    with patch("tools.acceptance.demo_readiness.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="core ok", stderr="")
        report = run_readiness(
            root=tmp_path,
            run_id="ready_test",
            include_gui=False,
            timeout_seconds=10,
        )

    json_path, markdown_path = write_readiness_report(tmp_path, report)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["steps"][0]["name"] == "core demo"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# PiProofForge Demo Readiness" in markdown
    assert "core demo" in markdown
