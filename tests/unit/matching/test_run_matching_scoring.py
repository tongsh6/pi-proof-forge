import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.run_matching_scoring import main


class RunMatchingScoringExclusionTests(unittest.TestCase):
    def test_returns_2_when_company_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
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
            evidence_dir = Path(tmp_dir) / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp_dir) / "mr-001.yaml"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_matching_scoring.py",
                    "--job-profile",
                    str(job_profile),
                    "--evidence-dir",
                    str(evidence_dir),
                    "--output",
                    str(output_path),
                ]
                with mock.patch("sys.argv", argv):
                    code = main()
            log_path = output_path.parent / "run_log.json"
            log_text = log_path.read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertIn("excluded_by_policy", log_text)

    def test_returns_2_when_legal_entity_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
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
            evidence_dir = Path(tmp_dir) / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp_dir) / "mr-002.yaml"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_matching_scoring.py",
                    "--job-profile",
                    str(job_profile),
                    "--evidence-dir",
                    str(evidence_dir),
                    "--output",
                    str(output_path),
                ]
                with mock.patch("sys.argv", argv):
                    code = main()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    _ = unittest.main()
