import unittest
from importlib import import_module

from tools.config.fragments import PolicyConfig
from tools.domain.result import Err, Ok
from tools.domain.value_objects import Candidate


def _gate_engine_class():
    module = import_module("tools.orchestration.gate_engine")
    return module.GateEngine


def _review_stage_class():
    module = import_module("tools.orchestration.review_stage")
    return module.ReviewStage


def _policy(
    delivery_mode: str = "auto",
    batch_review: bool = False,
    excluded_companies: tuple[str, ...] = (),
    gate_mode: str = "strict",
) -> PolicyConfig:
    return PolicyConfig(
        n_pass_required=1,
        matching_threshold=0.6,
        evaluation_threshold=0.6,
        max_rounds=3,
        gate_mode=gate_mode,
        delivery_mode=delivery_mode,
        batch_review=batch_review,
        excluded_companies=excluded_companies,
        excluded_legal_entities=(),
    )


def _candidate(company: str = "Acme") -> Candidate:
    return Candidate(
        candidate_id="cand-1",
        direction="backend",
        company=company,
        job_url="https://example.com",
        confidence=0.8,
        source="job_leads",
        merged_sources=("job_leads",),
    )


class GateEngineTests(unittest.TestCase):
    def test_gate_passes_above_threshold(self) -> None:
        gate = _gate_engine_class()(_policy(), run_id="run-1", round_index=0)
        result = gate.evaluate(_candidate(), matching_score=0.8, evaluation_score=0.9)
        self.assertIsInstance(result, Ok)

    def test_gate_fails_for_excluded_company(self) -> None:
        gate = _gate_engine_class()(
            _policy(excluded_companies=("exact:Acme",)),
            run_id="run-1",
            round_index=0,
        )
        result = gate.evaluate(_candidate(), matching_score=0.8, evaluation_score=0.9)
        self.assertIsInstance(result, Err)

    def test_gate_strict_fails_below_threshold(self) -> None:
        policy = PolicyConfig(
            n_pass_required=2,
            matching_threshold=0.6,
            evaluation_threshold=0.6,
            max_rounds=3,
            gate_mode="strict",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
        )
        gate = _gate_engine_class()(
            policy,
            run_id="run-1",
            round_index=0,
        )
        result = gate.evaluate(_candidate(), matching_score=0.1, evaluation_score=0.9)
        self.assertIsInstance(result, Err)

    def test_gate_simulate_allows_below_threshold(self) -> None:
        policy = PolicyConfig(
            n_pass_required=2,
            matching_threshold=0.6,
            evaluation_threshold=0.6,
            max_rounds=3,
            gate_mode="simulate",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
        )
        gate = _gate_engine_class()(
            policy,
            run_id="run-1",
            round_index=0,
        )
        result = gate.evaluate(_candidate(), matching_score=0.1, evaluation_score=0.9)
        self.assertIsInstance(result, Ok)
        self.assertIn("simulate:", result.value.details)

    def test_gate_n_pass_required_blocks_when_not_met(self) -> None:
        policy = PolicyConfig(
            n_pass_required=2,
            matching_threshold=0.7,
            evaluation_threshold=0.7,
            max_rounds=3,
            gate_mode="strict",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
        )
        gate = _gate_engine_class()(policy, run_id="run-1", round_index=0)
        result = gate.evaluate(_candidate(), matching_score=0.8, evaluation_score=0.6)
        self.assertIsInstance(result, Err)

    def test_gate_n_pass_required_allows_when_met(self) -> None:
        policy = PolicyConfig(
            n_pass_required=2,
            matching_threshold=0.7,
            evaluation_threshold=0.7,
            max_rounds=3,
            gate_mode="strict",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
        )
        gate = _gate_engine_class()(policy, run_id="run-1", round_index=0)
        result = gate.evaluate(_candidate(), matching_score=0.8, evaluation_score=0.8)
        self.assertIsInstance(result, Ok)


class ReviewStageTests(unittest.TestCase):
    def test_auto_mode_pass_through(self) -> None:
        stage = _review_stage_class()(_policy(delivery_mode="auto"))
        result = stage.execute({"events": []})
        self.assertTrue(result.success)
        self.assertEqual(result.data["pass_through"], True)

    def test_manual_non_batch_waits_for_review(self) -> None:
        stage = _review_stage_class()(
            _policy(delivery_mode="manual", batch_review=False)
        )
        context = {"events": []}
        result = stage.execute(context)
        self.assertTrue(result.success)
        self.assertEqual(result.data["waiting_for_review"], True)
        self.assertIn("agent.review.pending", context["events"])

    def test_manual_batch_collecting_before_all_rounds_done(self) -> None:
        stage = _review_stage_class()(
            _policy(delivery_mode="manual", batch_review=True)
        )
        result = stage.execute({"all_rounds_done": False, "events": []})
        self.assertTrue(result.success)
        self.assertEqual(result.data["collecting"], True)

    def test_manual_batch_waits_when_all_rounds_done(self) -> None:
        stage = _review_stage_class()(
            _policy(delivery_mode="manual", batch_review=True)
        )
        result = stage.execute({"all_rounds_done": True, "events": []})
        self.assertTrue(result.success)
        self.assertEqual(result.data["waiting_for_review"], True)


if __name__ == "__main__":
    _ = unittest.main()
