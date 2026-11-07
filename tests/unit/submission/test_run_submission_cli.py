import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from tools.submission.run_submission import validate_args


def _args(tmp_dir: str, **overrides):
    resume = Path(tmp_dir) / "resume.pdf"
    profile = Path(tmp_dir) / "profile.yaml"
    resume.write_bytes(b"%PDF-1.7\n")
    profile.write_text("name: test\n", encoding="utf-8")
    values = {
        "job_url": "https://www.liepin.com/job/123456.shtml",
        "resume": str(resume),
        "profile": str(profile),
        "submit": False,
        "dry_run": False,
        "timeout_ms": 45_000,
        "rate_limit_max_per_batch": 5,
        "rate_limit_cooldown_seconds": 900,
        "rate_limit_daily_limit": 30,
        "confirm_submit_job_id": "",
        "confirm_submit_recruiter": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class RunSubmissionCliTests(unittest.TestCase):
    def test_submit_requires_explicit_job_id_confirmation(self) -> None:
        with TemporaryDirectory() as tmp:
            args = _args(tmp, submit=True, confirm_submit_recruiter="Sun")

            with self.assertRaisesRegex(RuntimeError, "--confirm-submit-job-id"):
                validate_args(args)

    def test_submit_requires_explicit_recruiter_confirmation(self) -> None:
        with TemporaryDirectory() as tmp:
            args = _args(tmp, submit=True, confirm_submit_job_id="123456")

            with self.assertRaisesRegex(RuntimeError, "--confirm-submit-recruiter"):
                validate_args(args)

    def test_submit_accepts_full_confirmation(self) -> None:
        with TemporaryDirectory() as tmp:
            args = _args(
                tmp,
                submit=True,
                confirm_submit_job_id="123456",
                confirm_submit_recruiter="Sun",
            )

            validate_args(args)


if __name__ == "__main__":
    unittest.main()
