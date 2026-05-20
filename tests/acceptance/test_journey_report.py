from __future__ import annotations

import json
from pathlib import Path

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_artifact_check_step,
    build_journey_report,
    main,
    render_markdown,
    write_journey_report,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def test_journey_report_serializes_json_deterministically() -> None:
    contract = load_journey_contract(CONTRACT_PATH)

    report = build_journey_report(
        contract,
        run_id="acceptance-test",
        generated_at="2026-05-20T00:00:00Z",
        results={
            "lm_studio_config_persisted": JourneyStepResult(
                status="blocked",
                evidence="outputs/acceptance/lm-studio.json",
                message="LM Studio is not running on 127.0.0.1:1234.",
            )
        },
    )

    payload = report.to_json()

    assert payload["run_id"] == "acceptance-test"
    assert payload["status"] == "blocked"
    assert payload["summary"]["blocked"] == 1
    assert payload["summary"]["not_started"] == len(payload["steps"]) - 1
    assert payload["steps"][0] == {
        "case_id": "first_launch_configure_lm_studio",
        "rule_id": "lm_studio_config_persisted",
        "level": "L1",
        "stage": "system_settings",
        "phase": "",
        "status": "blocked",
        "evidence": "outputs/acceptance/lm-studio.json",
        "message": "LM Studio is not running on 127.0.0.1:1234.",
    }


def test_journey_report_markdown_contains_status_rows() -> None:
    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="acceptance-test",
        generated_at="2026-05-20T00:00:00Z",
        results={
            "quick_run_outputs_are_traceable": JourneyStepResult(
                status="pass",
                evidence="outputs/demo/demo-report.json",
                message="Quick Run artifacts are present.",
            )
        },
    )

    markdown = render_markdown(report)

    assert "# PiProofForge Journey Acceptance" in markdown
    assert "| Case | Rule | Level | Stage | Status | Evidence | Message |" in markdown
    assert "quick_run_outputs_are_traceable" in markdown
    assert "`pass`" in markdown


def test_artifact_check_failure_names_phase_and_missing_artifact(tmp_path: Path) -> None:
    missing = tmp_path / "scorecards" / "scorecard.md"

    step = build_artifact_check_step(
        case_id="quick_run_generate_and_evaluate_resume",
        rule_id="scorecard_exists",
        level="L1",
        stage="quick_run",
        phase="evaluation",
        artifact_path=missing,
        artifact_label="scorecard",
    )

    assert step.status == "fail"
    assert step.phase == "evaluation"
    assert "evaluation" in step.message
    assert "scorecard" in step.message
    assert str(missing) in step.message


def test_write_journey_report_outputs_json_and_markdown(tmp_path: Path) -> None:
    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="acceptance-test",
        generated_at="2026-05-20T00:00:00Z",
    )

    json_path, markdown_path = write_journey_report(tmp_path, report)

    assert json_path == tmp_path / "outputs" / "acceptance" / "acceptance-test" / "journey-report.json"
    assert markdown_path == tmp_path / "outputs" / "acceptance" / "acceptance-test" / "journey-report.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "not_started"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "PiProofForge Journey Acceptance" in markdown


def test_journey_report_cli_writes_baseline_report(tmp_path: Path) -> None:
    contract_dir = tmp_path / "acceptance"
    contract_dir.mkdir()
    contract_path = contract_dir / "journey_contract.yaml"
    contract_path.write_text(CONTRACT_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "--contract",
            "acceptance/journey_contract.yaml",
            "--run-id",
            "journey-cli-test",
        ]
    )

    assert exit_code == 0
    payload = json.loads(
        (
            tmp_path
            / "outputs"
            / "acceptance"
            / "journey-cli-test"
            / "journey-report.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["run_id"] == "journey-cli-test"
    assert payload["status"] == "not_started"
