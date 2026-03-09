import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.errors.exceptions import FabricationGuardError


def _template_assembler_class():
    module = import_module("tools.engines.generation.template_assembler")
    return module.TemplateAssembler


def _exporter_class():
    module = import_module("tools.engines.generation.exporter")
    return module.ResumeExporter


def _llm_rewriter_class():
    module = import_module("tools.engines.generation.llm_rewriter")
    return module.LLMRewriter


class GenerationEngineTests(unittest.TestCase):
    def _card(self) -> EvidenceCard:
        return EvidenceCard(
            id="ec-1",
            title="Perf campaign",
            raw_source="raw",
            results=("Latency reduced by 30%",),
            artifacts=("pr-1",),
        )

    def _report(self) -> MatchingReport:
        return MatchingReport(
            job_profile_id="jp-1",
            evidence_card_ids=("ec-1",),
            score_breakdown={"K": 0.8},
            gap_tasks=(),
        )

    def test_template_assembler_generates_resume(self) -> None:
        assembler = _template_assembler_class()()
        resume = assembler.assemble(self._report(), [self._card()], "v1")
        self.assertIsInstance(resume, ResumeOutput)
        self.assertIn("Latency reduced by 30%", resume.content)

    def test_template_assembler_raises_without_cards(self) -> None:
        assembler = _template_assembler_class()()
        with self.assertRaises(FabricationGuardError):
            assembler.assemble(self._report(), [], "v1")

    def test_markdown_exporter_writes_file(self) -> None:
        exporter = _exporter_class()()
        with TemporaryDirectory() as tmp:
            resume = ResumeOutput(
                version="v2",
                job_profile_id="jp-1",
                content="# Resume\n",
                format="markdown",
            )
            path = exporter.export_markdown(resume, tmp)
            self.assertTrue(Path(path).exists())

    def test_llm_rewriter_returns_rewritten_content(self) -> None:
        class FakeClient:
            chat_completions_url = "https://example.com"

            def __init__(self) -> None:
                self.last_payload: object = None

            def post_json(self, url: str, payload: object) -> dict[str, object]:
                _ = url
                self.last_payload = payload
                return {"choices": [{"message": {"content": "rewritten"}}]}

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

        fake_client = FakeClient()
        rewriter = _llm_rewriter_class()(client=fake_client, model="gpt-test")
        resume = ResumeOutput(
            version="v1",
            job_profile_id="jp-1",
            content="original",
            format="markdown",
        )
        rewritten = rewriter.rewrite(
            resume, jd_context="backend", company_context="B2B"
        )
        self.assertEqual(rewritten.content, "rewritten")
        payload = fake_client.last_payload
        self.assertIsInstance(payload, dict)
        if isinstance(payload, dict):
            messages = payload.get("messages", [])
            self.assertIsInstance(messages, list)
            if isinstance(messages, list) and messages:
                first = messages[0]
                self.assertIsInstance(first, dict)
                if isinstance(first, dict):
                    content = str(first.get("content", ""))
                    self.assertIn("JD Context: backend", content)
                    self.assertIn("Company Context: B2B", content)


if __name__ == "__main__":
    _ = unittest.main()
