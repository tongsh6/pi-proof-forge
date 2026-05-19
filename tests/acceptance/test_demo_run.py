from __future__ import annotations

import json
from pathlib import Path

from tools.acceptance.demo_run import build_demo_report, write_demo_report


def test_demo_report_passes_when_pipeline_artifacts_are_traceable(tmp_path: Path) -> None:
    run_id = "demo_test"
    artifacts = _write_demo_artifacts(tmp_path, run_id)

    report = build_demo_report(
        root=tmp_path,
        run_id=run_id,
        command=("python3", "tools/run_pipeline.py"),
        exit_code=0,
        stdout="[pipeline] done",
        stderr="",
    )

    assert report.status == "pass"
    assert report.artifacts["matching"] == artifacts["matching"]
    assert {check.status for check in report.checks} == {"pass"}


def test_demo_report_fails_when_required_artifact_is_missing(tmp_path: Path) -> None:
    run_id = "demo_test"
    _ = _write_demo_artifacts(tmp_path, run_id)
    (tmp_path / "outputs" / "scorecards" / f"scorecard_mr-{run_id}_A.md").unlink()

    report = build_demo_report(
        root=tmp_path,
        run_id=run_id,
        command=("python3", "tools/run_pipeline.py"),
        exit_code=0,
        stdout="[pipeline] done",
        stderr="",
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert report.status == "fail"
    assert any(check.name == "artifact:scorecard" for check in failed)


def test_write_demo_report_outputs_json_and_markdown(tmp_path: Path) -> None:
    run_id = "demo_test"
    _ = _write_demo_artifacts(tmp_path, run_id)
    report = build_demo_report(
        root=tmp_path,
        run_id=run_id,
        command=("python3", "tools/run_pipeline.py"),
        exit_code=0,
        stdout="[pipeline] done",
        stderr="",
    )

    json_path, markdown_path = write_demo_report(tmp_path, report)

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "pass"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# PiProofForge Demo Report" in markdown
    assert "artifact:matching" in markdown


def _write_demo_artifacts(root: Path, run_id: str) -> dict[str, str]:
    evidence = root / "evidence_cards" / f"ec-{run_id}.yaml"
    matching = root / "matching_reports" / f"mr-{run_id}.yaml"
    resume_dir = root / "outputs" / run_id
    scorecard = root / "outputs" / "scorecards" / f"scorecard_mr-{run_id}_A.md"
    run_record = root / "outputs" / "agent_runs" / run_id / "run_log.json"
    summary = root / "outputs" / "agent_runs" / run_id / "summary.json"

    for path in (evidence, matching, scorecard, run_record, summary):
        path.parent.mkdir(parents=True, exist_ok=True)
    resume_dir.mkdir(parents=True, exist_ok=True)

    evidence.write_text("id: ec-demo\n", encoding="utf-8")
    matching.write_text("score_total: 95\n", encoding="utf-8")
    (resume_dir / f"resume_mr-{run_id}_A.md").write_text(
        "# Resume A\n", encoding="utf-8"
    )
    (resume_dir / f"resume_mr-{run_id}_B.md").write_text(
        "# Resume B\n", encoding="utf-8"
    )
    scorecard.write_text("# Scorecard\n", encoding="utf-8")
    run_record.write_text(
        json.dumps(
            [
                {"event_type": "PIPELINE_START"},
                {"event_type": "PIPELINE_STEP_SUCCESS"},
                {"event_type": "PIPELINE_DONE"},
            ]
        ),
        encoding="utf-8",
    )

    artifacts = {
        "evidence": f"evidence_cards/ec-{run_id}.yaml",
        "matching": f"matching_reports/mr-{run_id}.yaml",
        "resume_dir": f"outputs/{run_id}",
        "scorecard": f"outputs/scorecards/scorecard_mr-{run_id}_A.md",
        "run_record": f"outputs/agent_runs/{run_id}/run_log.json",
    }
    summary.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "DONE",
                "exit_code": 0,
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return artifacts
