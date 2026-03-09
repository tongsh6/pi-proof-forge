from __future__ import annotations

from pathlib import Path

from tools.config.fragments import PolicyConfig
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.policy.exclusions import load_exclusion_policy


def _to_bool(value: str, default: bool = False) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    return default


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_policy_config(path: str) -> PolicyConfig:
    text = Path(path).read_text(encoding="utf-8")
    parsed = parse_simple_yaml(text)
    scalars = parsed.get("scalars", {})
    lists = parsed.get("lists", {})

    exclusions = load_exclusion_policy(Path(path))
    excluded_companies = tuple(
        exclusions.company_rules
        if exclusions.company_rules
        else lists.get("excluded_companies", [])
    )
    excluded_legal_entities = tuple(
        exclusions.legal_entities
        if exclusions.legal_entities
        else lists.get("excluded_legal_entities", [])
    )

    return PolicyConfig(
        n_pass_required=_to_int(scalars.get("n_pass_required", "1"), 1),
        matching_threshold=_to_float(scalars.get("matching_threshold", "0.0"), 0.0),
        evaluation_threshold=_to_float(
            scalars.get("evaluation_threshold", "0.0"),
            0.0,
        ),
        max_rounds=_to_int(scalars.get("max_rounds", "1"), 1),
        gate_mode=scalars.get("gate_mode", "strict"),
        delivery_mode=scalars.get("delivery_mode", "auto"),
        batch_review=_to_bool(scalars.get("batch_review", "false"), False),
        excluded_companies=excluded_companies,
        excluded_legal_entities=excluded_legal_entities,
        max_deliveries=_to_int(scalars.get("max_deliveries", "0"), 0),
    )
