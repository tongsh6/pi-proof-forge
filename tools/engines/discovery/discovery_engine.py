from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate


class ExcludedCandidate(NamedTuple):
    candidate: Candidate
    reason: str


@dataclass(frozen=True)
class DiscoveryResult:
    accepted: tuple[Candidate, ...]
    excluded: tuple[ExcludedCandidate, ...]


class DiscoveryEngine:
    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy

    def filter_candidates(self, candidates: list[Candidate]) -> DiscoveryResult:
        accepted: list[Candidate] = []
        excluded: list[ExcludedCandidate] = []

        for candidate in candidates:
            reason = self._exclude_reason(candidate)
            if reason is None:
                accepted.append(candidate)
            else:
                excluded.append(ExcludedCandidate(candidate=candidate, reason=reason))

        return DiscoveryResult(accepted=tuple(accepted), excluded=tuple(excluded))

    def _exclude_reason(self, candidate: Candidate) -> str | None:
        normalized_company = candidate.company.casefold()
        normalized_legal_entity = candidate.legal_entity.casefold()

        for entity in self._policy.excluded_legal_entities:
            if normalized_legal_entity and normalized_legal_entity == entity.casefold():
                return "excluded_by_policy"

        for rule in self._policy.excluded_companies:
            normalized_rule = rule.casefold()
            if normalized_rule.startswith("contains:"):
                needle = normalized_rule.split(":", 1)[1]
                if needle and needle in normalized_company:
                    return "excluded_by_policy"
                continue
            if normalized_rule.startswith("exact:"):
                exact = normalized_rule.split(":", 1)[1]
                if exact and exact == normalized_company:
                    return "excluded_by_policy"
                continue
            if normalized_rule and normalized_rule == normalized_company:
                return "excluded_by_policy"

        return None
