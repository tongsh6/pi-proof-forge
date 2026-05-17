from __future__ import annotations

from pathlib import Path

import pytest

from tools.acceptance.journey_contract import (
    EXPECTED_JOURNEY_STAGES,
    JourneyContractError,
    load_journey_contract,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"
SCENARIO_CASES_PATH = ROOT / "acceptance" / "scenario_cases.yaml"


def test_journey_contract_loads_and_references_ready_cases() -> None:
    contract = load_journey_contract(
        CONTRACT_PATH,
        scenario_cases_path=SCENARIO_CASES_PATH,
    )

    assert contract.version == "2026-05-17"
    assert contract.stages == EXPECTED_JOURNEY_STAGES
    assert contract.selected_cases == contract.case_ids
    assert "feedback_iteration_after_check_mode" in contract.selected_cases
    assert len(contract.case_contracts) == 9


def test_journey_contract_requires_exact_stage_order(tmp_path: Path) -> None:
    invalid = tmp_path / "journey_contract.yaml"
    text = CONTRACT_PATH.read_text(encoding="utf-8").replace(
        '    - "overview"\n',
        "",
        1,
    )
    invalid.write_text(text, encoding="utf-8")

    with pytest.raises(JourneyContractError, match="journey.stages"):
        load_journey_contract(invalid)


def test_journey_contract_rules_expose_report_status_fields() -> None:
    contract = load_journey_contract(CONTRACT_PATH)
    rules = [
        rule
        for case_contract in contract.case_contracts
        for rule in case_contract.acceptance_rules
    ]

    assert rules
    for rule in rules:
        assert rule.status == "not_started"
        assert rule.evidence == ""
        assert rule.message


def test_journey_contract_rejects_missing_case_contract(tmp_path: Path) -> None:
    invalid = tmp_path / "journey_contract.yaml"
    text = CONTRACT_PATH.read_text(encoding="utf-8").replace(
        '  - "feedback_iteration_after_check_mode"\n',
        '  - "feedback_iteration_after_check_mode"\n  - "missing_case"\n',
        1,
    )
    invalid.write_text(text, encoding="utf-8")

    with pytest.raises(JourneyContractError, match="missing_case must be a mapping"):
        load_journey_contract(invalid)
