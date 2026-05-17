import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools.run_pipeline import main


class RunPipelineExclusionTests(unittest.TestCase):
    def test_success_writes_unified_run_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = os.getcwd()
            policy_path = Path(tmp_dir) / "policy.yaml"
            _ = policy_path.write_text("excluded_companies: []\n", encoding="utf-8")
            job_profile = Path(tmp_dir) / "jp-003.yaml"
            _ = job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Product Labs'",
                        "source_jd: 'https://example.com/jd/3'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            raw_path = Path(tmp_dir) / "raw.txt"
            _ = raw_path.write_text("sample", encoding="utf-8")
            run_id = "test-run-record"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_pipeline.py",
                    "--raw",
                    str(raw_path),
                    "--job-profile",
                    str(job_profile),
                    "--run-id",
                    run_id,
                ]
                with (
                    mock.patch("sys.argv", argv),
                    mock.patch("tools.run_pipeline.subprocess.run") as run_mock,
                ):
                    run_mock.return_value = mock.Mock(returncode=0)
                    os.chdir(tmp_dir)
                    try:
                        code = main()
                    finally:
                        os.chdir(cwd)
            log_path = (
                Path(tmp_dir) / "outputs" / "agent_runs" / run_id / "run_log.json"
            )
            events = json.loads(log_path.read_text(encoding="utf-8"))
            summary_path = (
                Path(tmp_dir) / "outputs" / "agent_runs" / run_id / "summary.json"
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(run_mock.call_count, 4)
        event_types = [event["event_type"] for event in events]
        self.assertEqual(event_types[0], "PIPELINE_START")
        self.assertEqual(event_types[-1], "PIPELINE_DONE")
        self.assertEqual(event_types.count("PIPELINE_STEP_SUCCESS"), 4)
        self.assertEqual(summary["status"], "DONE")
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(
            summary["artifacts"]["run_record"],
            "outputs/agent_runs/test-run-record/run_log.json",
        )

    def test_returns_2_when_company_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = os.getcwd()
            policy_path = Path(tmp_dir) / "policy.yaml"
            _ = policy_path.write_text(
                "\n".join(
                    [
                        "exclusion_list:",
                        "  - 'contains:Outsource'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            job_profile = Path(tmp_dir) / "jp-001.yaml"
            _ = job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Outsource Labs'",
                        "source_jd: 'https://example.com/jd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            raw_path = Path(tmp_dir) / "raw.txt"
            _ = raw_path.write_text("sample", encoding="utf-8")
            run_id = "test-excluded"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_pipeline.py",
                    "--raw",
                    str(raw_path),
                    "--job-profile",
                    str(job_profile),
                    "--run-id",
                    run_id,
                ]
                with mock.patch("sys.argv", argv):
                    os.chdir(tmp_dir)
                    try:
                        code = main()
                    finally:
                        os.chdir(cwd)
            log_path = Path(tmp_dir) / "outputs" / run_id / "run_log.json"
            log_text = log_path.read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertIn("excluded_by_policy", log_text)

    def test_returns_2_when_legal_entity_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = os.getcwd()
            policy_path = Path(tmp_dir) / "policy.yaml"
            _ = policy_path.write_text(
                "\n".join(
                    [
                        "excluded_legal_entities:",
                        "  - 'Acme Holdings Ltd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            job_profile = Path(tmp_dir) / "jp-002.yaml"
            _ = job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Acme Staffing'",
                        "legal_entity: 'Acme Holdings Ltd'",
                        "source_jd: 'https://example.com/jd/2'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            raw_path = Path(tmp_dir) / "raw.txt"
            _ = raw_path.write_text("sample", encoding="utf-8")
            run_id = "test-legal-entity"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_pipeline.py",
                    "--raw",
                    str(raw_path),
                    "--job-profile",
                    str(job_profile),
                    "--run-id",
                    run_id,
                ]
                with mock.patch("sys.argv", argv):
                    os.chdir(tmp_dir)
                    try:
                        code = main()
                    finally:
                        os.chdir(cwd)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    _ = unittest.main()
