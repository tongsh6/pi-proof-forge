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

    def test_rule_matching_engine_searches_stack_field(self) -> None:
        """Keywords in stack field should be detected (regression test for benchmark-001 fix)."""
        engine = _rule_matching_engine_class()()
        card_with_stack = EvidenceCard(
            id="ec-stack",
            title="API Gateway",
            raw_source="raw",
            results=("Done",),
            artifacts=("doc",),
            tags=("api",),
            stack=("Java", "Redis", "Kafka"),
        )
        profile = JobProfile(
            id="jp-stack",
            title="Backend",
            keywords=("Java", "Kafka"),
            level="senior",
        )
        report = engine.score([card_with_stack], profile)
        # K-score should be 1.0 (both Java and Kafka found in stack)
        self.assertEqual(report.score_breakdown["K"], 1.0)
        self.assertEqual(report.score_breakdown["total"], 1.0)

    def test_rule_matching_engine_stack_and_tags_combined(self) -> None:
        """Keywords matched across both tags and stack should be counted once each."""
        engine = _rule_matching_engine_class()()
        card = EvidenceCard(
            id="ec-combined",
            title="Service Mesh",
            raw_source="raw",
            results=("Done",),
            artifacts=("doc",),
            tags=("Java",),
            stack=("Redis", "Kafka"),
        )
        profile = JobProfile(
            id="jp-combined",
            title="Platform",
            keywords=("Java", "Redis", "Kafka", "SLA"),
            level="senior",
        )
        report = engine.score([card], profile)
        # 3 out of 4 keywords matched (Java in tags, Redis+Kafka in stack, SLA missing)
        self.assertEqual(report.score_breakdown["K"], 0.75)

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
