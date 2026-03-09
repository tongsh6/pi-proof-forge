import unittest
from importlib import import_module

from tools.domain.models import JobProfile, ResumeOutput, Scorecard


def _rule_evaluator_class():
    module = import_module("tools.engines.evaluation.rule_evaluator")
    return module.RuleEvaluationEngine


def _scorecard_builder_class():
    module = import_module("tools.engines.evaluation.scorecard_builder")
    return module.ScorecardBuilder


def _llm_evaluator_class():
    module = import_module("tools.engines.evaluation.llm_evaluator")
    return module.LLMEvaluationEngine


class EvaluationEngineTests(unittest.TestCase):
    def _resume(self) -> ResumeOutput:
        return ResumeOutput(
            version="v1",
            job_profile_id="jp-1",
            content="## Highlights\n- Reduced latency by 30%\n- Improved throughput 2x\n",
            format="markdown",
        )

    def _profile(self) -> JobProfile:
        return JobProfile(
            id="jp-1",
            title="Backend",
            keywords=("latency", "throughput"),
            level="senior",
            must_have=("latency",),
        )

    def test_rule_evaluator_returns_scorecard(self) -> None:
        evaluator = _rule_evaluator_class()()
        scorecard = evaluator.evaluate(self._resume(), self._profile())
        self.assertIsInstance(scorecard, Scorecard)
        self.assertIn("coverage", scorecard.dimension_scores)

    def test_scorecard_builder_builds_total(self) -> None:
        builder = _scorecard_builder_class()()
        card = builder.build("v1", "jp-1", {"coverage": 0.8, "quant": 0.6})
        self.assertAlmostEqual(card.total_score, 0.7)

    def test_llm_evaluator_keeps_rule_total_and_adds_note_count(self) -> None:
        class FakeClient:
            chat_completions_url = "https://example.com"

            def post_json(self, url: str, payload: object) -> dict[str, object]:
                _ = (url, payload)
                return {
                    "choices": [{"message": {"content": '{"notes": ["n1", "n2"]}'}}]
                }

            @staticmethod
            def extract_content(response: dict[str, object]) -> str:
                choices = response.get("choices", [])
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        message = first.get("message", {})
                        if isinstance(message, dict):
                            content = message.get("content", "")
                            if isinstance(content, str):
                                return content
                return ""

        evaluator = _llm_evaluator_class()(client=FakeClient(), model="gpt-test")
        result = evaluator.evaluate(self._resume(), self._profile())
        self.assertIn("llm_notes_count", result.dimension_scores)
        self.assertEqual(result.dimension_scores["llm_notes_count"], 2.0)


if __name__ == "__main__":
    _ = unittest.main()
