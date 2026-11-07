import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.cli.entrypoints import main


class CliEntrypointsTests(unittest.TestCase):
    def test_unknown_command_returns_2(self) -> None:
        code = main(["unknown"])
        self.assertEqual(code, 2)

    def test_agent_command_runs_and_writes_run_log(self) -> None:
        with TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            policy.write_text(
                """n_pass_required: 1
matching_threshold: 0.6
evaluation_threshold: 0.6
max_rounds: 2
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies: []
excluded_legal_entities: []
""",
                encoding="utf-8",
            )
            output_dir = Path(tmp) / "agent_runs"
            code = main(
                [
                    "agent",
                    "--policy",
                    str(policy),
                    "--dry-run",
                    "--run-id",
                    "run-cli-1",
                    "--output-dir",
                    str(output_dir),
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "run-cli-1" / "run_log.json").exists())


if __name__ == "__main__":
    _ = unittest.main()
