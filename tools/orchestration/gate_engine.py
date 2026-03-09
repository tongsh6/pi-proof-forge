from __future__ import annotations

from tools.config.fragments import PolicyConfig
from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import Candidate, GateDecision, GateFailure


class GateEngine:
    def __init__(self, policy: PolicyConfig, run_id: str, round_index: int) -> None:
        self._policy = policy
        self._run_id = run_id
        self._round_index = round_index

    def evaluate(
        self,
        candidate: Candidate,
        matching_score: float,
        evaluation_score: float,
    ) -> Result[GateDecision, GateFailure]:
        exclusion = _match_exclusion(candidate, self._policy)
        if exclusion is not None:
            return Err(
                GateFailure(
                    reason="excluded_company",
                    details=f"{candidate.company} matched exclusion rule: {exclusion}",
                )
            )

        pass_count = 0
        if matching_score >= self._policy.matching_threshold:
            pass_count += 1
        if evaluation_score >= self._policy.evaluation_threshold:
            pass_count += 1

        if pass_count < self._policy.n_pass_required:
            return self._threshold_result(
                reason="n_pass_not_met",
                details=(
                    f"pass_count={pass_count} < n_pass_required={self._policy.n_pass_required}; "
                    f"matching={matching_score:.4f}/{self._policy.matching_threshold:.4f}, "
                    f"evaluation={evaluation_score:.4f}/{self._policy.evaluation_threshold:.4f}"
                ),
            )

        return Ok(
            GateDecision(
                passed=True,
                pass_count=pass_count,
                details=(
                    f"run_id={self._run_id}, round_index={self._round_index}, "
                    f"matching={matching_score:.4f}, evaluation={evaluation_score:.4f}"
                ),
            )
        )

    def _threshold_result(
        self, reason: str, details: str
    ) -> Result[GateDecision, GateFailure]:
        if self._policy.gate_mode == "simulate":
            return Ok(
                GateDecision(
                    passed=False,
                    pass_count=0,
                    details=f"simulate:{reason}:{details}",
                )
            )

        return Err(GateFailure(reason=reason, details=details))


def _match_exclusion(candidate: Candidate, policy: PolicyConfig) -> str | None:
    legal_entity = candidate.legal_entity.casefold()
    for blocked_entity in policy.excluded_legal_entities:
        if legal_entity and legal_entity == blocked_entity.casefold():
            return blocked_entity

    company = candidate.company.casefold()
    for rule in policy.excluded_companies:
        lowered = rule.casefold()
        if lowered.startswith("contains:"):
            needle = lowered.split(":", 1)[1]
            if needle and needle in company:
                return rule
        elif lowered.startswith("exact:"):
            expected = lowered.split(":", 1)[1]
            if expected and expected == company:
                return rule
        elif lowered and lowered == company:
            return rule
    return None
