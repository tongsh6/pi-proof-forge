import unittest
from importlib import import_module

from tools.domain.models import EvidenceCard, JobProfile, MatchingReport


def _rule_matching_engine_class():
    module = import_module("tools.engines.matching.rule_scorer")
    return module.RuleMatchingEngine


def _report_builder_class():
    module = import_module("tools.engines.matching.report_builder")
    return module.ReportBuilder


class MatchingEngineTests(unittest.TestCase):
    def _card(self) -> EvidenceCard:
        return EvidenceCard(
            id="ec-1",
            title="Python perf optimization",
            raw_source="raw",
            results=("Latency -30%",),
            artifacts=("pr-123",),
            tags=("Python", "Performance"),
        )

    def _profile(self) -> JobProfile:
        return JobProfile(
            id="jp-1",
            title="Senior Backend Engineer",
            keywords=("Python", "Performance"),
            level="senior",
            must_have=("Python", "Kafka"),
        )

    def test_rule_matching_engine_returns_report(self) -> None:
        engine = _rule_matching_engine_class()()
        report = engine.score([self._card()], self._profile())
        self.assertIsInstance(report, MatchingReport)
        self.assertEqual(report.job_profile_id, "jp-1")
        self.assertIn("K", report.score_breakdown)

    def test_rule_matching_engine_generates_gap_tasks(self) -> None:
        engine = _rule_matching_engine_class()()
        report = engine.score([self._card()], self._profile())
        self.assertTrue(any("Kafka" in task for task in report.gap_tasks))

    def test_report_builder_constructs_report(self) -> None:
        builder = _report_builder_class()()
        report = builder.build(
            job_profile_id="jp-1",
            card_ids=("ec-1",),
            score_breakdown={"K": 0.8},
            gap_tasks=("补充 Kafka 相关证据",),
        )
        self.assertEqual(report.job_profile_id, "jp-1")
        self.assertEqual(report.evidence_card_ids, ("ec-1",))


if __name__ == "__main__":
    _ = unittest.main()
