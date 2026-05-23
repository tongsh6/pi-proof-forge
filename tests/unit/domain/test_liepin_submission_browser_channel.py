import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from tools.submission.liepin import (
    LiepinSubmissionConfig,
    _capture_browser_screenshot,
    _browser_context_options,
    _record_dom_snapshot_step,
    _is_error_page,
)
from tools.submission.storage import SubmissionRecorder


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

    def test_external_l3_skips_raw_browser_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config("chrome")
            config.external_l3_validation_run_id = "acceptance_external_l3"
            config.external_l3_validation_path = (
                "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
            )
            recorder = SubmissionRecorder(
                output_root=Path(tmp),
                platform="liepin",
                mode="submit",
            )
            page = Mock()

            screenshot = _capture_browser_screenshot(
                page,
                recorder,
                config,
                "target_verify",
            )
            _record_dom_snapshot_step(recorder, config, page)

            self.assertIsNone(screenshot)
            page.screenshot.assert_not_called()
            self.assertFalse((recorder.run_dir / "html").exists())
            self.assertEqual(recorder.record.steps[-1].name, "dom_snapshot")
            self.assertEqual(recorder.record.steps[-1].status, "skipped")
            self.assertIn(
                "raw_browser_artifacts_persisted=false",
                recorder.record.steps[-1].detail,
            )


if __name__ == "__main__":
    _ = unittest.main()
