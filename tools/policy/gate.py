from __future__ import annotations

from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import Candidate, GateDecision, GateFailure
from tools.policy.exclusions import is_company_excluded


def evaluate_candidate_exclusion(
    candidate: Candidate, exclusions: list[str]
) -> Result[GateDecision, GateFailure]:
    if is_company_excluded(candidate.company, exclusions):
        return Err(
            GateFailure(
                reason="excluded_company",
                details=f"company excluded by policy: {candidate.company}",
            )
        )
    return Ok(GateDecision(passed=True, pass_count=1, details="company allowed"))
