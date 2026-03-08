from __future__ import annotations

from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import Candidate, GateDecision, GateFailure
from tools.policy.exclusions import PolicyExclusions, match_exclusion


def evaluate_candidate_exclusion(
    candidate: Candidate,
    exclusions: list[str],
    legal_entity_exclusions: list[str] | None = None,
) -> Result[GateDecision, GateFailure]:
    policy = PolicyExclusions(
        company_rules=tuple(exclusions),
        legal_entities=tuple(legal_entity_exclusions or []),
    )
    exclusion_reason = match_exclusion(
        candidate.company, candidate.legal_entity, policy
    )
    if exclusion_reason == "excluded_legal_entity":
        return Err(
            GateFailure(
                reason="excluded_legal_entity",
                details=(
                    "legal entity excluded by policy: "
                    f"{candidate.legal_entity or candidate.company}"
                ),
            )
        )
    if exclusion_reason == "excluded_company":
        return Err(
            GateFailure(
                reason="excluded_company",
                details=f"company excluded by policy: {candidate.company}",
            )
        )
    return Ok(GateDecision(passed=True, pass_count=1, details="company allowed"))
