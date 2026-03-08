import unittest
from typing import Any, Sequence

from tools.domain.models import (
    EvidenceCard,
    JobProfile,
    MatchingReport,
    ResumeOutput,
    Scorecard,
)
from tools.domain.protocols import (
    DeliveryChannel,
    EvidenceExtractor,
    EvaluationEngine,
    GateEngine,
    GenerationEngine,
    MatchingEngine,
    RunStore,
    Stage,
    StageResult,
)
from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import (
    Candidate,
    ChannelFailure,
    DeliveryResult,
    GateDecision,
    GateFailure,
)


# --- Fake implementations to verify Protocol satisfaction ---


class FakeExtractor:
    def extract(self, raw_material: Any) -> EvidenceCard:
        return EvidenceCard(
            id="ec-test-001",
            title="Test",
            raw_source="test.md",
            results=("result",),
            artifacts=("artifact",),
        )


class FakeMatcher:
    def score(
        self, evidence_cards: Sequence[EvidenceCard], profile: JobProfile
    ) -> MatchingReport:
        return MatchingReport(
            job_profile_id=profile.id,
            evidence_card_ids=tuple(c.id for c in evidence_cards),
            score_breakdown={"keyword": 80.0},
            gap_tasks=(),
        )


class FakeGenerator:
    def generate(
        self,
        report: MatchingReport,
        cards: Sequence[EvidenceCard],
        version: str,
        config: Any,
    ) -> ResumeOutput:
        return ResumeOutput(
            version=version,
            job_profile_id=report.job_profile_id,
            content="generated",
            format="markdown",
        )


class FakeEvaluator:
    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard:
        return Scorecard(
            resume_version=resume.version,
            job_profile_id=profile.id,
            total_score=85.0,
            dimension_scores={"coverage": 85.0},
        )


class FakeGate:
    def evaluate(self, request: Any) -> Result[GateDecision, GateFailure]:
        return Ok(GateDecision(passed=True, pass_count=1, details="passed"))


class FakeChannel:
    channel_id: str = "fake"

    def deliver(self, request: Any) -> Result[DeliveryResult, ChannelFailure]:
        return Ok(
            DeliveryResult(
                channel_id="fake", success=True, submission_id="s-1", message="ok"
            )
        )


class FakeRunStore:
    def __init__(self) -> None:
        self._events: list[Any] = []

    def append_event(self, event: Any) -> None:
        self._events.append(event)

    def load_events(self, run_id: str) -> Sequence[Any]:
        return self._events


class FakeStage:
    name: str = "fake_stage"

    def execute(self, context: Any) -> StageResult:
        return StageResult(success=True, data={"key": "value"})


# --- Tests ---


class EvidenceExtractorProtocolTests(unittest.TestCase):
    def test_fake_extractor_satisfies_protocol(self) -> None:
        extractor: EvidenceExtractor = FakeExtractor()
        card = extractor.extract("raw input")
        self.assertEqual(card.id, "ec-test-001")


class MatchingEngineProtocolTests(unittest.TestCase):
    def test_fake_matcher_satisfies_protocol(self) -> None:
        matcher: MatchingEngine = FakeMatcher()
        card = EvidenceCard(
            id="ec-001", title="T", raw_source="s", results=("r",), artifacts=("a",)
        )
        profile = JobProfile(id="jp-001", title="Dev", keywords=("py",), level="mid")
        report = matcher.score([card], profile)
        self.assertEqual(report.job_profile_id, "jp-001")


class GenerationEngineProtocolTests(unittest.TestCase):
    def test_fake_generator_satisfies_protocol(self) -> None:
        gen: GenerationEngine = FakeGenerator()
        report = MatchingReport(
            job_profile_id="jp-001",
            evidence_card_ids=("ec-001",),
            score_breakdown={},
            gap_tasks=(),
        )
        resume = gen.generate(report, [], "v1", {})
        self.assertEqual(resume.version, "v1")


class EvaluationEngineProtocolTests(unittest.TestCase):
    def test_fake_evaluator_satisfies_protocol(self) -> None:
        evaluator: EvaluationEngine = FakeEvaluator()
        resume = ResumeOutput(version="v1", job_profile_id="jp-001", content="c", format="md")
        profile = JobProfile(id="jp-001", title="Dev", keywords=(), level="mid")
        sc = evaluator.evaluate(resume, profile)
        self.assertAlmostEqual(sc.total_score, 85.0)


class GateEngineProtocolTests(unittest.TestCase):
    def test_gate_returns_result_type(self) -> None:
        gate: GateEngine = FakeGate()
        result = gate.evaluate({})
        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertTrue(result.value.passed)

    def test_gate_can_return_failure(self) -> None:
        class FailingGate:
            def evaluate(self, request: Any) -> Result[GateDecision, GateFailure]:
                return Err(GateFailure(reason="low_score", details="60 < 75"))

        gate: GateEngine = FailingGate()
        result = gate.evaluate({})
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.error.reason, "low_score")


class DeliveryChannelProtocolTests(unittest.TestCase):
    def test_channel_returns_result_type(self) -> None:
        channel: DeliveryChannel = FakeChannel()
        result = channel.deliver({})
        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertTrue(result.value.success)

    def test_channel_can_return_failure(self) -> None:
        class FailingChannel:
            channel_id: str = "broken"

            def deliver(self, request: Any) -> Result[DeliveryResult, ChannelFailure]:
                return Err(
                    ChannelFailure(channel_id="broken", reason="timeout", details="30s")
                )

        channel: DeliveryChannel = FailingChannel()
        result = channel.deliver({})
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.error.channel_id, "broken")


class RunStoreProtocolTests(unittest.TestCase):
    def test_run_store_append_and_load(self) -> None:
        store: RunStore = FakeRunStore()
        store.append_event({"type": "round.started"})
        events = store.load_events("run-001")
        self.assertEqual(len(events), 1)


class StageProtocolTests(unittest.TestCase):
    def test_stage_execute_returns_stage_result(self) -> None:
        stage: Stage = FakeStage()
        result = stage.execute({})
        self.assertIsInstance(result, StageResult)
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"key": "value"})


if __name__ == "__main__":
    unittest.main()
