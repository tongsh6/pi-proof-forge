from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


EXPECTED_JOURNEY_STAGES: tuple[str, ...] = (
    "overview",
    "resumes",
    "evidence",
    "jobs",
    "quick_run",
    "agent_run",
    "submissions",
    "policy",
    "system_settings",
)

ALLOWED_RULE_STATUSES = {"not_started", "pass", "fail", "blocked"}
IMPLEMENTABLE_CASE_STATUSES = {"ready_for_implementation", "implemented"}


class JourneyContractError(ValueError):
    pass


@dataclass(frozen=True)
class AcceptanceRule:
    rule_id: str
    case_id: str
    level: str
    stage: str
    status: str
    evidence: str
    message: str


@dataclass(frozen=True)
class CaseContract:
    case_id: str
    primary_stage: str
    supporting_stages: tuple[str, ...]
    required_outputs: tuple[str, ...]
    acceptance_rules: tuple[AcceptanceRule, ...]


@dataclass(frozen=True)
class JourneyContract:
    version: str
    source_scenario_cases: str
    status: str
    stages: tuple[str, ...]
    levels: tuple[str, ...]
    selected_cases: tuple[str, ...]
    case_contracts: tuple[CaseContract, ...]

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.case_contracts)


def load_journey_contract(
    path: str | Path,
    *,
    scenario_cases_path: str | Path | None = None,
) -> JourneyContract:
    contract_path = Path(path)
    raw = _load_yaml_mapping(contract_path)

    version = _require_str(raw, "version")
    source_scenario_cases = _require_str(raw, "source_scenario_cases")
    status = _require_str(raw, "status")

    journey = _require_mapping(raw, "journey")
    stages = tuple(_require_str_list(journey, "stages"))
    if stages != EXPECTED_JOURNEY_STAGES:
        raise JourneyContractError(
            "journey.stages must match the required scenario stage order"
        )

    levels_raw = _require_mapping(raw, "levels")
    levels = tuple(levels_raw.keys())
    if not {"L1", "L2", "L3"}.issubset(levels):
        raise JourneyContractError("levels must include L1, L2, and L3")

    selected_cases = tuple(_require_str_list(raw, "selected_cases"))
    if not selected_cases:
        raise JourneyContractError("selected_cases must not be empty")

    case_contracts_raw = _require_mapping(raw, "case_contracts")
    case_contracts = tuple(
        _parse_case_contract(
            case_id=case_id,
            raw=_require_mapping(case_contracts_raw, case_id),
            levels=set(levels),
            selected_cases=set(selected_cases),
            stages=set(stages),
        )
        for case_id in selected_cases
    )

    extra_contracts = set(case_contracts_raw) - set(selected_cases)
    if extra_contracts:
        raise JourneyContractError(
            "case_contracts contains non-selected cases: "
            + ", ".join(sorted(extra_contracts))
        )

    if scenario_cases_path is not None:
        _validate_against_scenario_cases(
            selected_cases=selected_cases,
            scenario_cases_path=Path(scenario_cases_path),
        )

    return JourneyContract(
        version=version,
        source_scenario_cases=source_scenario_cases,
        status=status,
        stages=stages,
        levels=levels,
        selected_cases=selected_cases,
        case_contracts=case_contracts,
    )


def _parse_case_contract(
    *,
    case_id: str,
    raw: dict[str, Any],
    levels: set[str],
    selected_cases: set[str],
    stages: set[str],
) -> CaseContract:
    primary_stage = _require_str(raw, "primary_stage")
    if primary_stage not in stages:
        raise JourneyContractError(f"{case_id}.primary_stage is not a valid stage")

    supporting_stages = tuple(_require_str_list(raw, "supporting_stages"))
    unknown_supporting = set(supporting_stages) - stages
    if unknown_supporting:
        raise JourneyContractError(
            f"{case_id}.supporting_stages contains invalid stages: "
            + ", ".join(sorted(unknown_supporting))
        )

    required_outputs = tuple(_require_str_list(raw, "required_outputs"))
    if not required_outputs:
        raise JourneyContractError(f"{case_id}.required_outputs must not be empty")

    rules_raw = _require_list(raw, "acceptance_rules")
    rules = tuple(
        _parse_rule(
            case_id=case_id,
            raw_rule=rule,
            levels=levels,
            selected_cases=selected_cases,
            stages=stages,
        )
        for rule in rules_raw
    )
    if not rules:
        raise JourneyContractError(f"{case_id}.acceptance_rules must not be empty")

    return CaseContract(
        case_id=case_id,
        primary_stage=primary_stage,
        supporting_stages=supporting_stages,
        required_outputs=required_outputs,
        acceptance_rules=rules,
    )


def _parse_rule(
    *,
    case_id: str,
    raw_rule: object,
    levels: set[str],
    selected_cases: set[str],
    stages: set[str],
) -> AcceptanceRule:
    if not isinstance(raw_rule, dict):
        raise JourneyContractError(f"{case_id}.acceptance_rules entries must be maps")

    rule_case_id = str(raw_rule.get("case_id") or case_id)
    if rule_case_id not in selected_cases:
        raise JourneyContractError(
            f"{case_id}.acceptance_rules references non-selected case {rule_case_id}"
        )

    level = _require_str(raw_rule, "level")
    if level not in levels:
        raise JourneyContractError(f"{case_id}.acceptance_rules has invalid level")

    stage = _require_str(raw_rule, "stage")
    if stage not in stages:
        raise JourneyContractError(f"{case_id}.acceptance_rules has invalid stage")

    status = _require_str(raw_rule, "status")
    if status not in ALLOWED_RULE_STATUSES:
        raise JourneyContractError(f"{case_id}.acceptance_rules has invalid status")

    return AcceptanceRule(
        rule_id=_require_str(raw_rule, "rule_id"),
        case_id=rule_case_id,
        level=level,
        stage=stage,
        status=status,
        evidence=_require_str(raw_rule, "evidence"),
        message=_require_str(raw_rule, "message"),
    )


def _validate_against_scenario_cases(
    *,
    selected_cases: tuple[str, ...],
    scenario_cases_path: Path,
) -> None:
    raw = _load_yaml_mapping(scenario_cases_path)
    cases = _require_list(raw, "cases")
    statuses: dict[str, str] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise JourneyContractError("scenario cases entries must be maps")
        case_id = str(case.get("case_id") or "")
        status = str(case.get("status") or "")
        if case_id:
            statuses[case_id] = status

    missing = [case_id for case_id in selected_cases if case_id not in statuses]
    if missing:
        raise JourneyContractError(
            "selected_cases missing from scenario catalog: " + ", ".join(missing)
        )

    not_ready = [
        case_id
        for case_id in selected_cases
        if statuses[case_id] not in IMPLEMENTABLE_CASE_STATUSES
    ]
    if not_ready:
        raise JourneyContractError(
            "selected_cases are not ready for implementation: "
            + ", ".join(not_ready)
        )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise JourneyContractError(f"{path} must contain a YAML mapping")
    return loaded


def _require_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise JourneyContractError(f"{key} must be a mapping")
    return value


def _require_list(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise JourneyContractError(f"{key} must be a list")
    return value


def _require_str_list(raw: dict[str, Any], key: str) -> list[str]:
    values = _require_list(raw, key)
    if not all(isinstance(value, str) and value for value in values):
        raise JourneyContractError(f"{key} must be a list of non-empty strings")
    return values


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise JourneyContractError(f"{key} must be a string")
    return value
