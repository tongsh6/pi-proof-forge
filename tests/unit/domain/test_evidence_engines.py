import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.domain.models import EvidenceCard
from tools.errors.exceptions import EvidenceValidationError


def _validator_class():
    module = import_module("tools.engines.evidence.validator")
    return module.EvidenceValidator


def _rule_extractor_class():
    module = import_module("tools.engines.evidence.rule_extractor")
    return module.RuleEvidenceExtractor


def _store_class():
    module = import_module("tools.engines.evidence.store")
    return module.EvidenceStore


def _llm_extractor_class():
    module = import_module("tools.engines.evidence.llm_extractor")
    return module.LLMEvidenceExtractor


class EvidenceValidatorTests(unittest.TestCase):
    def test_validator_accepts_valid_card(self) -> None:
        card = EvidenceCard(
            id="ec-1",
            title="OK",
            raw_source="raw",
            results=("result",),
            artifacts=("artifact",),
        )
        _validator_class()().validate(card)

    def test_validator_rejects_missing_results(self) -> None:
        card = EvidenceCard(
            id="ec-1",
            title="BAD",
            raw_source="raw",
            results=(),
            artifacts=("artifact",),
        )
        with self.assertRaises(EvidenceValidationError):
            _validator_class()().validate(card)

    def test_validator_rejects_missing_artifacts(self) -> None:
        card = EvidenceCard(
            id="ec-1",
            title="BAD",
            raw_source="raw",
            results=("result",),
            artifacts=(),
        )
        with self.assertRaises(EvidenceValidationError):
            _validator_class()().validate(card)


class RuleExtractorTests(unittest.TestCase):
    def test_extract_rule_card(self) -> None:
        extractor = _rule_extractor_class()()
        card = extractor.extract(
            "Performance optimization\nresult: latency -30%\nartifact: pr-100\ntag: python"
        )
        self.assertIn("latency -30%", card.results)
        self.assertIn("pr-100", card.artifacts)
        self.assertIn("python", card.tags)


class EvidenceStoreTests(unittest.TestCase):
    def test_save_and_get(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _store_class()(base_dir=tmp)
            card = EvidenceCard(
                id="ec-2",
                title="Card",
                raw_source="source",
                results=("R",),
                artifacts=("A",),
                tags=("T",),
            )
            path = store.save(card)
            self.assertTrue(Path(path).exists())
            loaded = store.get("ec-2")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.results, ("R",))


class LLMExtractorTests(unittest.TestCase):
    def test_extract_from_llm_json(self) -> None:
        class FakeClient:
            chat_completions_url = "https://example.com/chat/completions"

            def __init__(self) -> None:
                self.called_url = ""
                self.called_payload: object = {}

            def post_json(self, url: str, payload: object) -> dict[str, object]:
                self.called_url = url
                self.called_payload = payload
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"id":"ec-llm-1","title":"LLM","raw_source":"raw",'
                                    '"results":["r1"],"artifacts":["a1"],"tags":["t1"]}'
                                )
                            }
                        }
                    ]
                }

            @staticmethod
            def extract_content(response: dict[str, object]) -> str:
                choices = response["choices"]
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        message = first.get("message")
                        if isinstance(message, dict):
                            content = message.get("content")
                            if isinstance(content, str):
                                return content
                return ""

        fake_client = FakeClient()
        extractor = _llm_extractor_class()(client=fake_client, model="gpt-test")
        card = extractor.extract("raw")
        self.assertEqual(card.id, "ec-llm-1")
        self.assertEqual(card.results, ("r1",))
        self.assertEqual(card.artifacts, ("a1",))


if __name__ == "__main__":
    _ = unittest.main()
