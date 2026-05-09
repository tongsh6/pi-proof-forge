import unittest
from pathlib import Path
from unittest.mock import Mock

from tools.submission.liepin import (
    LiepinSubmissionConfig,
    _browser_context_options,
    _is_error_page,
)


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
                "viewport": {"width": 1440, "height": 900},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                "ignore_default_args": ["--enable-automation"],
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
                "viewport": {"width": 1440, "height": 900},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                "ignore_default_args": ["--enable-automation"],
            },
        )

    def test_job_page_health_rejects_offline_liepin_jobs(self) -> None:
        page = Mock(url="https://www.liepin.com/job/1964642633.shtml")

        def locator(selector: str) -> Mock:
            result = Mock()
            result.count.return_value = 1 if selector == "text=已下线" else 0
            return result

        page.locator.side_effect = locator
        page.frames = []

        self.assertTrue(_is_error_page(page))


if __name__ == "__main__":
    _ = unittest.main()
