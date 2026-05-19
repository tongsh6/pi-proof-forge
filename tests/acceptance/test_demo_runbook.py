from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "demo-runbook.md"


def test_demo_runbook_documents_primary_readiness_entrypoint() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "bash scripts/acceptance/run-demo-readiness.sh" in text
    assert "bash scripts/acceptance/run-demo-readiness.sh --include-gui" in text
    assert "pnpm --dir ui run e2e:quick-run" in text


def test_demo_runbook_documents_required_reports_and_artifacts() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    required_paths = [
        "outputs/demo/<run_id>/readiness-report.json",
        "outputs/demo/<run_id>/readiness-report.md",
        "outputs/demo/<run_id>/demo-report.json",
        "outputs/demo/<run_id>/demo-report.md",
        "matching_reports/mr-<run_id>.yaml",
        "outputs/<run_id>/resume_mr-<run_id>_A.md",
        "outputs/<run_id>/resume_mr-<run_id>_B.md",
        "outputs/scorecards/scorecard_mr-<run_id>_A.md",
        "ui/test-results/quick-run-native/",
    ]

    for path in required_paths:
        assert path in text


def test_demo_runbook_keeps_default_demo_scope_safe() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "does not perform real" in text
    assert "submission" in text
    assert "external job discovery" in text
