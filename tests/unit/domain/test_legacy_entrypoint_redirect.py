import unittest
from unittest.mock import patch

from tools.run_agent import main as legacy_agent_main
from tools.run_evaluation import main as legacy_evaluate_main
from tools.run_evidence_extraction import main as legacy_main
from tools.run_generation import main as legacy_generate_main
from tools.run_matching_scoring import main as legacy_match_main
from tools.run_pipeline import main as legacy_pipeline_main


class LegacyEntrypointRedirectTests(unittest.TestCase):
    def test_run_evidence_extraction_redirects_to_cli_command(self) -> None:
        with patch("tools.run_evidence_extraction.cli_main", return_value=7) as mocked:
            code = legacy_main()
            self.assertEqual(code, 7)
            mocked.assert_called_once()

    def test_run_agent_redirects_to_cli_command(self) -> None:
        with patch("tools.run_agent.cli_main", return_value=3) as mocked:
            code = legacy_agent_main()
            self.assertEqual(code, 3)
            mocked.assert_called_once()

    def test_run_matching_redirects_to_cli_command(self) -> None:
        with patch("tools.cli.commands.match.main", return_value=9) as mocked:
            code = legacy_match_main()
            self.assertEqual(code, 9)
            mocked.assert_called_once()

    def test_run_generation_redirects_to_cli_command(self) -> None:
        with patch("tools.cli.commands.generate.main", return_value=11) as mocked:
            code = legacy_generate_main()
            self.assertEqual(code, 11)
            mocked.assert_called_once()

    def test_run_evaluation_redirects_to_cli_command(self) -> None:
        with patch("tools.cli.commands.evaluate.main", return_value=13) as mocked:
            code = legacy_evaluate_main()
            self.assertEqual(code, 13)
            mocked.assert_called_once()

    def test_run_pipeline_redirects_to_cli_command(self) -> None:
        with patch("tools.cli.commands.pipeline.main", return_value=15) as mocked:
            code = legacy_pipeline_main()
            self.assertEqual(code, 15)
            mocked.assert_called_once()


if __name__ == "__main__":
    _ = unittest.main()
