from __future__ import annotations

from tools.config.fragments import PolicyConfig
from tools.errors.exceptions import PolicyError


def _validate_exclusion_rule(rule: str) -> None:
    trimmed = rule.strip()
    if not trimmed:
        raise PolicyError("excluded_companies contains empty value")

    if ":" not in trimmed:
        return

    prefix = trimmed.split(":", 1)[0].strip().lower()
    value = trimmed.split(":", 1)[1].strip()
    if prefix not in ("exact", "contains"):
        raise PolicyError(f"unsupported exclusion match mode: {prefix}")
    if not value:
        raise PolicyError("excluded_companies has empty rule value")


def validate_policy_config(config: PolicyConfig) -> None:
    if config.delivery_mode not in ("auto", "manual"):
        raise PolicyError("delivery_mode must be auto or manual")

    if config.gate_mode not in ("strict", "simulate"):
        raise PolicyError("gate_mode must be strict or simulate")

    if config.n_pass_required < 1:
        raise PolicyError("n_pass_required must be >= 1")

    if config.max_rounds < 1:
        raise PolicyError("max_rounds must be >= 1")

    if config.max_deliveries < 0:
        raise PolicyError("max_deliveries must be >= 0")

    if not 0.0 <= config.matching_threshold <= 1.0:
        raise PolicyError("matching_threshold must be in [0, 1]")

    if not 0.0 <= config.evaluation_threshold <= 1.0:
        raise PolicyError("evaluation_threshold must be in [0, 1]")

    seen_companies: set[str] = set()
    for rule in config.excluded_companies:
        _validate_exclusion_rule(rule)
        normalized = rule.strip().casefold()
        if normalized in seen_companies:
            raise PolicyError(f"duplicated excluded_companies rule: {rule}")
        seen_companies.add(normalized)

    seen_entities: set[str] = set()
    for entity in config.excluded_legal_entities:
        normalized = entity.strip().casefold()
        if not normalized:
            raise PolicyError("excluded_legal_entities contains empty value")
        if normalized in seen_entities:
            raise PolicyError(f"duplicated excluded_legal_entities value: {entity}")
        seen_entities.add(normalized)
