from __future__ import annotations

from tools.domain.value_objects import Candidate
from tools.policy.exclusions import is_company_excluded


def filter_candidates_by_policy(
    candidates: list[Candidate], exclusions: list[str]
) -> tuple[list[Candidate], list[Candidate]]:
    kept: list[Candidate] = []
    excluded: list[Candidate] = []
    for candidate in candidates:
        if is_company_excluded(candidate.company, exclusions):
            excluded.append(candidate)
        else:
            kept.append(candidate)
    return kept, excluded
