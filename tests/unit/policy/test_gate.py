import unittest
from typing import cast

from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import Candidate, GateDecision, GateFailure
from tools.policy.gate import evaluate_candidate_exclusion


class PolicyGateTests(unittest.TestCase):
    def test_returns_err_when_company_excluded(self) -> None:
        candidate = Candidate(
            candidate_id="cand-001",
            direction="backend",
            company="Outsource Labs",
            job_url="https://example.com/job/1",
            confidence=0.75,
            source="job_leads",
            merged_sources=("job_leads",),
        )
        result: Result[GateDecision, GateFailure] = evaluate_candidate_exclusion(
            candidate, ["contains:outsource"]
        )
        self.assertIsInstance(result, Err)
        err = cast(Err[GateFailure], result)
        self.assertEqual(err.error.reason, "excluded_company")
        self.assertIn("Outsource Labs", err.error.details)

    def test_returns_ok_when_company_allowed(self) -> None:
        candidate = Candidate(
            candidate_id="cand-002",
            direction="backend",
            company="Acme Inc",
            job_url="https://example.com/job/2",
            confidence=0.6,
            source="job_profiles",
            merged_sources=("job_profiles",),
        )
        result: Result[GateDecision, GateFailure] = evaluate_candidate_exclusion(
            candidate, ["contains:outsource"]
        )
        self.assertIsInstance(result, Ok)
        ok = cast(Ok[GateDecision], result)
        self.assertTrue(ok.value.passed)

    def test_returns_err_when_legal_entity_excluded(self) -> None:
        candidate = Candidate(
            candidate_id="cand-003",
            direction="backend",
            company="Acme Staffing",
            job_url="https://example.com/job/3",
            confidence=0.7,
            source="job_profiles",
            merged_sources=("job_profiles",),
            legal_entity="Acme Holdings Ltd",
        )
        result: Result[GateDecision, GateFailure] = evaluate_candidate_exclusion(
            candidate,
            ["contains:outsource"],
            ["Acme Holdings Ltd"],
        )
        self.assertIsInstance(result, Err)
        err = cast(Err[GateFailure], result)
        self.assertEqual(err.error.reason, "excluded_legal_entity")


if __name__ == "__main__":
    unittest.main()
