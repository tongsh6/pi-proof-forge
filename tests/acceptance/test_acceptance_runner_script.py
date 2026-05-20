from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "acceptance" / "run-acceptance.sh"
PLAN = ROOT / "AIEF" / "docs" / "plans" / "2026-05-13-user-journey-closed-loop-validation.md"


def test_acceptance_runner_script_exists_and_delegates_to_module() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert source.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in source
    assert "python3 -m tools.acceptance.acceptance_runner" in source


def test_acceptance_runner_is_documented_in_plan() -> None:
    text = PLAN.read_text(encoding="utf-8")

    assert "scripts/acceptance/run-acceptance.sh" in text
    assert "--level L1" in text
    assert "outputs/acceptance/<run_id>/acceptance-report.json" in text
