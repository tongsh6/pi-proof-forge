import unittest
from pathlib import Path

from tools.submission.liepin import LiepinSubmissionConfig, _browser_context_options


def _config(browser_channel: str) -> LiepinSubmissionConfig:
    return LiepinSubmissionConfig(
        job_url="https://www.liepin.com/job/1",
        resume_path="outputs/resume.pdf",
        profile_path="profiles/candidate_profile.yaml",
        headless=True,
        dry_run=False,
        submit=False,
        output_dir="outputs/submissions",
        session_dir=".sessions",
        timeout_ms=45_000,
        browser_channel=browser_channel,
    )


class LiepinSubmissionBrowserChannelTests(unittest.TestCase):
    def test_context_options_default_to_chrome_channel(self) -> None:
        options = _browser_context_options(_config("chrome"), Path(".sessions/liepin"))

        self.assertEqual(
            options,
            {
                "user_data_dir": ".sessions/liepin",
                "headless": True,
                "channel": "chrome",
            },
        )

    def test_context_options_allow_bundled_chromium(self) -> None:
        options = _browser_context_options(_config(""), Path(".sessions/liepin"))

        self.assertEqual(
            options,
            {
                "user_data_dir": ".sessions/liepin",
                "headless": True,
            },
        )


if __name__ == "__main__":
    _ = unittest.main()
