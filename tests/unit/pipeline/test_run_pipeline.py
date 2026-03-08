import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools.run_pipeline import main


class RunPipelineExclusionTests(unittest.TestCase):
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


if __name__ == "__main__":
    _ = unittest.main()
