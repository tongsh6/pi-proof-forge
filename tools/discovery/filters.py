from __future__ import annotations

from tools.domain.value_objects import Candidate
from tools.policy.exclusions import PolicyExclusions, match_exclusion


def filter_candidates_by_policy(
    candidates: list[Candidate],
    exclusions: list[str],
    legal_entity_exclusions: list[str] | None = None,
) -> tuple[list[Candidate], list[Candidate]]:
    policy = PolicyExclusions(
        company_rules=tuple(exclusions),
        legal_entities=tuple(legal_entity_exclusions or []),
    )
    kept: list[Candidate] = []
    excluded: list[Candidate] = []
    for candidate in candidates:
        if match_exclusion(candidate.company, candidate.legal_entity, policy):
            excluded.append(candidate)
        else:
            kept.append(candidate)
    return kept, excluded
