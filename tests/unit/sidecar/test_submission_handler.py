import json
import unittest
from unittest.mock import Mock
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.submission import (
    handle_channel_session_check,
    handle_channel_session_clear,
    handle_channel_session_get,
    handle_channel_session_start,
    handle_feedback_create_iteration,
    handle_feedback_list,
    handle_submission_check_mode,
    handle_submission_detail,
    handle_submission_list,
    handle_submission_retry,
)


class RealSessionBoundaryTests(unittest.TestCase):
    def test_start_rechecks_existing_authenticated_page(self):
        from tools.sidecar.handlers import submission
        with TemporaryDirectory() as tmp, patch.object(submission, "_CHANNEL_SESSIONS_DIR", Path(tmp)), patch.object(submission, "_session_browser") as browser:
            browser.start.return_value = True
            browser.check.return_value = {"login_signals": {"authenticated_user_visible": True}}
            result = handle_channel_session_start({"meta": {"correlation_id": "existing"}, "channel": "liepin"})
            self.assertEqual(result["session"]["login_status"], "session_valid")
            self.assertFalse(result["manual_login_required"])
    def test_legacy_unobserved_valid_session_is_not_trusted(self):
        from tools.sidecar.handlers import submission
        with TemporaryDirectory() as tmp, patch.object(submission, "_CHANNEL_SESSIONS_DIR", Path(tmp)):
            submission._write_session("liepin", {"channel": "liepin", "login_status": "session_valid"})
            self.assertEqual(submission._read_session("liepin")["login_status"], "session_unknown")

    def test_failed_recheck_invalidates_previous_valid_session(self):
        from tools.sidecar.handlers import submission
        with TemporaryDirectory() as tmp, patch.object(submission, "_CHANNEL_SESSIONS_DIR", Path(tmp)), patch.object(submission, "_session_browser") as browser:
            submission._write_session("liepin", {"login_status": "session_valid", "verification_source": "owned_playwright"})
            browser.check.side_effect = RuntimeError("browser closed")
            with self.assertRaises(RuntimeError):
                handle_channel_session_check({"meta": {"correlation_id": "recheck"}, "channel": "liepin"})
            self.assertEqual(submission._read_session("liepin")["login_status"], "session_unknown")

    def test_start_opens_owned_browser_before_reporting_success(self):
        from tools.sidecar.handlers import submission
        with TemporaryDirectory() as tmp, patch.object(submission, "_CHANNEL_SESSIONS_DIR", Path(tmp)), patch.object(submission, "_session_browser", create=True) as browser:
            result = handle_channel_session_start({"meta": {"correlation_id": "start"}, "channel": "liepin"})
            browser.start.assert_called_once_with(Path(tmp) / "liepin/browser_profile", "https://www.liepin.com/")
            self.assertTrue(result["browser_automation"]["opened_login_page"])

    def test_browser_failure_cannot_report_opened_login_page(self):
        from tools.sidecar.handlers import submission
        with TemporaryDirectory() as tmp, patch.object(submission, "_CHANNEL_SESSIONS_DIR", Path(tmp)), patch.object(submission, "_session_browser", create=True) as browser:
            browser.start.side_effect = RuntimeError("PLAYWRIGHT_UNAVAILABLE")
            with self.assertRaisesRegex(RuntimeError, "PLAYWRIGHT_UNAVAILABLE"):
                handle_channel_session_start({"meta": {"correlation_id": "failed"}, "channel": "liepin"})

    def test_frontend_cannot_forge_valid_session_or_account_identity(self):
        from tools.sidecar.handlers import submission
        with TemporaryDirectory() as tmp, patch.object(submission, "_CHANNEL_SESSIONS_DIR", Path(tmp)), patch.object(submission, "_session_browser", create=True) as browser:
            browser.check.return_value = {"login_signals": {"login_required": True}}
            result = handle_channel_session_check({"meta": {"correlation_id": "check"}, "channel": "liepin", "login_signals": {"authenticated_user_visible": True}, "account_identity": {"nickname": "forged"}})
            self.assertEqual(result["session"]["login_status"], "login_required")
            self.assertNotEqual(result["session"]["account_identity"]["display_name_or_nickname"], "forged")
            browser.check.assert_called_once_with(Path(tmp) / "liepin/browser_profile")


class SubmissionListTests(unittest.TestCase):
    def test_list_returns_empty_when_no_logs_exist(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_list(
                    {"meta": {"correlation_id": "corr_001"}}
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertEqual(result["items"], [])
        self.assertIsNone(result["next_cursor"])

    def test_list_reads_submission_logs(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            run_dir.mkdir(parents=True)
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "status": "failed",
                        "started_at": "2026-03-04T12:46:34+00:00",
                        "ended_at": "2026-03-04T12:46:37+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_list(
                    {"meta": {"correlation_id": "corr_002"}}
                )

        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["submission_id"], "20260304-124634")
        self.assertEqual(item["channel"], "liepin")
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["submitted_at"], "2026-03-04T12:46:37+00:00")

    def test_list_returns_operational_status_details(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            run_dir.mkdir(parents=True)
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "mode": "check",
                        "status": "blocked",
                        "error": "batch_cooldown",
                        "job_url": "https://www.liepin.com/job/123.shtml",
                        "ended_at": "2026-03-04T12:46:37+00:00",
                        "steps": [
                            {
                                "name": "rate_limit",
                                "status": "blocked",
                                "detail": "batch_cooldown; wait_seconds=385",
                                "screenshot": "",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_list(
                    {"meta": {"correlation_id": "corr_014"}}
                )

        item = result["items"][0]
        self.assertEqual(item["mode"], "check")
        self.assertEqual(item["job_url"], "https://www.liepin.com/job/123.shtml")
        self.assertEqual(item["error"], "batch_cooldown")
        self.assertEqual(item["last_step"]["name"], "rate_limit")
        self.assertEqual(item["last_step"]["status"], "blocked")
        self.assertEqual(item["last_step"]["detail"], "batch_cooldown; wait_seconds=385")
        self.assertEqual(item["rate_limit_status"], "blocked")
        self.assertEqual(item["rate_limit_detail"], "batch_cooldown; wait_seconds=385")

    def test_list_filters_by_status_and_channel(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            run_dir.mkdir(parents=True)
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "status": "failed",
                        "ended_at": "2026-03-04T12:46:37+00:00",
                    }
                ),
                encoding="utf-8",
            )
            other_dir = submissions_dir / "liepin" / "20260305-124634"
            other_dir.mkdir(parents=True)
            (other_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260305-124634",
                        "platform": "liepin",
                        "status": "done",
                        "ended_at": "2026-03-05T12:46:37+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_list(
                    {
                        "meta": {"correlation_id": "corr_010"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "submitted_at", "order": "desc"},
                        "filters": {
                            "status": "failed",
                            "channel": "liepin",
                        },
                    }
                )

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["submission_id"], "20260304-124634")

    def test_list_filters_by_date_range(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            run_dir.mkdir(parents=True)
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "status": "failed",
                        "ended_at": "2026-03-04T12:46:37+00:00",
                    }
                ),
                encoding="utf-8",
            )
            later_dir = submissions_dir / "liepin" / "20260306-124634"
            later_dir.mkdir(parents=True)
            (later_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260306-124634",
                        "platform": "liepin",
                        "status": "done",
                        "ended_at": "2026-03-06T12:46:37+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_list(
                    {
                        "meta": {"correlation_id": "corr_011"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "submitted_at", "order": "desc"},
                        "filters": {
                            "date_range": {
                                "start": "2026-03-04T00:00:00Z",
                                "end": "2026-03-05T23:59:59Z",
                            }
                        },
                    }
                )

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["submission_id"], "20260304-124634")

    def test_list_sorts_by_status_ascending(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"

            # 创建多个提交记录，状态顺序是混乱的
            run1_dir = submissions_dir / "liepin" / "20260301-100000"
            run1_dir.mkdir(parents=True)
            (run1_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260301-100000",
                        "platform": "liepin",
                        "status": "failed",
                        "ended_at": "2026-03-01T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            run2_dir = submissions_dir / "liepin" / "20260302-110000"
            run2_dir.mkdir(parents=True)
            (run2_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260302-110000",
                        "platform": "liepin",
                        "status": "done",
                        "ended_at": "2026-03-02T11:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            run3_dir = submissions_dir / "boss" / "20260303-120000"
            run3_dir.mkdir(parents=True)
            (run3_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260303-120000",
                        "platform": "boss",
                        "status": "queued",
                        "ended_at": "2026-03-03T12:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                # 测试按status升序排序
                result = handle_submission_list(
                    {
                        "meta": {"correlation_id": "corr_012"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "status", "order": "asc"},
                        "filters": {},
                    }
                )

        # 按status升序排序：done, failed, queued (字母顺序)
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["items"][0]["status"], "done")
        self.assertEqual(result["items"][0]["submission_id"], "20260302-110000")
        self.assertEqual(result["items"][1]["status"], "failed")
        self.assertEqual(result["items"][1]["submission_id"], "20260301-100000")
        self.assertEqual(result["items"][2]["status"], "queued")
        self.assertEqual(result["items"][2]["submission_id"], "20260303-120000")

    def test_list_sorts_by_status_descending(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"

            # 创建多个提交记录
            run1_dir = submissions_dir / "liepin" / "20260301-100000"
            run1_dir.mkdir(parents=True)
            (run1_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260301-100000",
                        "platform": "liepin",
                        "status": "failed",
                        "ended_at": "2026-03-01T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            run2_dir = submissions_dir / "liepin" / "20260302-110000"
            run2_dir.mkdir(parents=True)
            (run2_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260302-110000",
                        "platform": "liepin",
                        "status": "done",
                        "ended_at": "2026-03-02T11:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            run3_dir = submissions_dir / "boss" / "20260303-120000"
            run3_dir.mkdir(parents=True)
            (run3_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260303-120000",
                        "platform": "boss",
                        "status": "queued",
                        "ended_at": "2026-03-03T12:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                # 测试按status降序排序
                result = handle_submission_list(
                    {
                        "meta": {"correlation_id": "corr_013"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "status", "order": "desc"},
                        "filters": {},
                    }
                )

        # 按status降序排序：queued, failed, done (字母顺序反向)
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["items"][0]["status"], "queued")
        self.assertEqual(result["items"][0]["submission_id"], "20260303-120000")
        self.assertEqual(result["items"][1]["status"], "failed")
        self.assertEqual(result["items"][1]["submission_id"], "20260301-100000")
        self.assertEqual(result["items"][2]["status"], "done")
        self.assertEqual(result["items"][2]["submission_id"], "20260302-110000")


class SubmissionDetailTests(unittest.TestCase):
    def test_detail_returns_steps_screenshots_and_log_paths(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            screenshot_dir = run_dir / "screenshots"
            screenshot_dir.mkdir(parents=True)
            screenshot_path = screenshot_dir / "02_open_job_page.png"
            screenshot_path.write_bytes(b"png")
            (run_dir / "submission_log.yaml").write_text(
                'run_id: "20260304-124634"\n',
                encoding="utf-8",
            )
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "mode": "check",
                        "status": "success",
                        "job_url": "https://www.liepin.com/job/123.shtml",
                        "resume_path": "outputs/v1.md",
                        "profile_path": "profiles/candidate_profile.yaml",
                        "started_at": "2026-03-04T12:46:34+00:00",
                        "ended_at": "2026-03-04T12:46:37+00:00",
                        "steps": [
                            {
                                "name": "open_job_page",
                                "status": "success",
                                "detail": "job page opened",
                                "screenshot": "screenshots/02_open_job_page.png",
                            },
                            {
                                "name": "submit",
                                "status": "skipped",
                                "detail": "submit not enabled",
                                "screenshot": "",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_detail(
                    {
                        "meta": {"correlation_id": "corr_detail"},
                        "submission_id": "20260304-124634",
                    }
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_detail")
        self.assertEqual(result["submission"]["submission_id"], "20260304-124634")
        self.assertEqual(result["submission"]["log_json_path"], str(run_dir / "submission_log.json"))
        self.assertEqual(result["submission"]["log_yaml_path"], str(run_dir / "submission_log.yaml"))
        self.assertEqual(result["submission"]["steps"][0]["name"], "open_job_page")
        self.assertEqual(result["submission"]["steps"][0]["screenshot"], "screenshots/02_open_job_page.png")
        self.assertEqual(result["submission"]["steps"][0]["screenshot_path"], str(screenshot_path))
        self.assertTrue(result["submission"]["steps"][0]["screenshot_exists"])
        self.assertFalse(result["submission"]["steps"][1]["screenshot_exists"])

    def test_detail_not_found_raises(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                with self.assertRaises(KeyError):
                    handle_submission_detail(
                        {
                            "meta": {"correlation_id": "corr_missing"},
                            "submission_id": "missing",
                        }
                    )

    def test_detail_marks_screenshot_outside_run_dir_missing(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            run_dir.mkdir(parents=True)
            outside = submissions_dir / "leaked.png"
            outside.write_bytes(b"png")
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "status": "success",
                        "steps": [
                            {
                                "name": "open_job_page",
                                "status": "success",
                                "detail": "job page opened",
                                "screenshot": "../leaked.png",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_detail(
                    {
                        "meta": {"correlation_id": "corr_detail_unsafe"},
                        "submission_id": "20260304-124634",
                    }
                )

        step = result["submission"]["steps"][0]
        self.assertEqual(step["screenshot"], "../leaked.png")
        self.assertEqual(step["screenshot_path"], "")
        self.assertFalse(step["screenshot_exists"])


class SubmissionRetryTests(unittest.TestCase):
    def test_retry_returns_queued_for_existing_submission(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "20260304-124634"
            original_ended_at = "2026-03-04T12:46:37+00:00"
            run_dir.mkdir(parents=True)
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260304-124634",
                        "platform": "liepin",
                        "status": "failed",
                        "retry_count": 1,
                        "ended_at": original_ended_at,
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                result = handle_submission_retry(
                    {
                        "meta": {"correlation_id": "corr_003"},
                        "submission_id": "20260304-124634",
                        "strategy": "same_channel",
                    }
                )

            updated_log = json.loads(
                (run_dir / "submission_log.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["meta"]["correlation_id"], "corr_003")
        self.assertEqual(result["submission_id"], "20260304-124634")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(updated_log["status"], "queued")
        self.assertEqual(updated_log["retry_count"], 2)
        self.assertNotEqual(updated_log["ended_at"], original_ended_at)
        parsed_ended_at = datetime.fromisoformat(updated_log["ended_at"])
        self.assertIsNotNone(parsed_ended_at.tzinfo)

    def test_retry_not_found_raises(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                with self.assertRaises(KeyError):
                    handle_submission_retry(
                        {
                            "meta": {"correlation_id": "corr_004"},
                            "submission_id": "missing",
                            "strategy": "same_channel",
                        }
                    )


class SessionBrowserStubTests(unittest.TestCase):
    def setUp(self):
        # 合同测试只替代后端浏览器观察；不再由请求参数决定登录结果。
        self.browser = self.enterContext(patch("tools.sidecar.handlers.submission._session_browser"))
        self.browser.check.return_value = {
            "login_signals": {"authenticated_user_visible": True},
            "account_identity": {"display_name_or_nickname": "Verifier", "masked_phone_or_email_suffix": "13800123456", "avatar_presence": True},
        }


class ChannelSessionTests(SessionBrowserStubTests):
    def test_channel_session_requires_and_validates_channel(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            sessions_dir = Path(tmp_dir) / "channel_sessions"
            with patch(
                "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                sessions_dir,
            ):
                with self.assertRaises(ValueError) as missing:
                    handle_channel_session_get({"meta": {"correlation_id": "corr"}})
                with self.assertRaises(ValueError) as unsupported:
                    handle_channel_session_get(
                        {
                            "meta": {"correlation_id": "corr"},
                            "channel": "boss",
                        }
                    )

        self.assertIn("channel_required", str(missing.exception))
        self.assertIn("unsupported_submission_channel", str(unsupported.exception))

    def test_channel_session_rejects_credentials_and_challenge_inputs(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            sessions_dir = Path(tmp_dir) / "channel_sessions"
            with patch(
                "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                sessions_dir,
            ):
                with self.assertRaises(ValueError) as password_error:
                    handle_channel_session_start(
                        {
                            "meta": {"correlation_id": "corr_password"},
                            "channel": "liepin",
                            "credentials": {"password": "secret"},
                        }
                    )
                with self.assertRaises(ValueError) as captcha_error:
                    handle_channel_session_check(
                        {
                            "meta": {"correlation_id": "corr_captcha"},
                            "channel": "liepin",
                            "captcha_code": "1234",
                        }
                    )

        self.assertIn(
            "credentials_or_challenge_input_forbidden", str(password_error.exception)
        )
        self.assertIn(
            "credentials_or_challenge_input_forbidden", str(captcha_error.exception)
        )

    def test_channel_session_start_records_manual_login_boundary(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            sessions_dir = Path(tmp_dir) / "channel_sessions"
            with patch(
                "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                sessions_dir,
            ):
                result = handle_channel_session_start(
                    {
                        "meta": {"correlation_id": "corr_start"},
                        "channel": "liepin",
                    }
                )
                session_artifact_exists = Path(
                    result["artifact_paths"]["channel_session"]
                ).exists()
                log_artifact_exists = Path(
                    result["artifact_paths"]["session_check_log"]
                ).exists()

        self.assertEqual(result["meta"]["correlation_id"], "corr_start")
        self.assertEqual(result["session"]["channel"], "liepin")
        self.assertEqual(result["session"]["login_status"], "waiting_for_manual_login")
        self.assertTrue(result["manual_login_required"])
        self.assertFalse(result["browser_automation"]["entered_credentials"])
        self.assertFalse(result["browser_automation"]["entered_captcha_or_sms"])
        self.assertIn("liepin", result["session"]["adapter"])
        step_names = [step["name"] for step in result["steps"]]
        self.assertIn("manual_login_required", step_names)
        self.assertTrue(session_artifact_exists)
        self.assertTrue(log_artifact_exists)

    def test_channel_session_check_requires_positive_login_signal(self) -> None:
        self.browser.check.side_effect = [
            {"login_signals": {"login_modal_absent": True}},
            {"login_signals": {"login_required": True}},
            self.browser.check.return_value,
        ]
        with TemporaryDirectory() as tmp_dir:
            sessions_dir = Path(tmp_dir) / "channel_sessions"
            with patch(
                "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                sessions_dir,
            ):
                unknown = handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_unknown"},
                        "channel": "liepin",
                        "login_signals": {"login_modal_absent": True},
                    }
                )
                login_required = handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_login_required"},
                        "channel": "liepin",
                        "login_signals": {"login_required": True},
                    }
                )
                valid = handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_valid"},
                        "channel": "liepin",
                        "login_signals": {
                            "logged_in_user_ui_or_equivalent_authenticated_signal": True
                        },
                        "account_identity": {
                            "display_name_or_nickname": "Verifier",
                            "masked_phone_or_email_suffix": "13800123456",
                            "avatar_presence": True,
                        },
                    }
                )
                log_payload = json.loads(
                    Path(valid["artifact_paths"]["session_check_log"]).read_text(
                        encoding="utf-8"
                    )
                )

        self.assertEqual(unknown["session"]["login_status"], "session_unknown")
        self.assertFalse(unknown["session"]["clear_available"])
        self.assertEqual(login_required["session"]["login_status"], "login_required")
        self.assertEqual(valid["session"]["login_status"], "session_valid")
        self.assertTrue(valid["session"]["clear_available"])
        self.assertEqual(
            valid["session"]["account_identity"]["display_name_or_nickname"],
            "Verifier",
        )
        self.assertEqual(
            valid["session"]["account_identity"]["masked_phone_or_email_suffix"],
            "***3456",
        )
        self.assertIn("liepin", valid["session"]["adapter"])
        self.assertEqual(log_payload["terminal_status"], "session_valid")
        self.assertFalse(log_payload["adapter"]["liepin"]["credential_entry_attempted"])

    def test_channel_session_clear_removes_only_selected_channel_profile(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            sessions_dir = Path(tmp_dir) / "channel_sessions"
            with patch(
                "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                sessions_dir,
            ):
                valid = handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_valid"},
                        "channel": "liepin",
                        "login_signals": {
                            "logged_in_user_ui_or_equivalent_authenticated_signal": True
                        },
                    }
                )
                valid_profile_exists = Path(valid["session"]["session_path"]).exists()
                other_channel_profile = sessions_dir / "future_channel" / "browser_profile"
                other_channel_profile.mkdir(parents=True)
                cleared = handle_channel_session_clear(
                    {
                        "meta": {"correlation_id": "corr_clear"},
                        "channel": "liepin",
                    }
                )
                cleared_profile_exists = Path(
                    cleared["session"]["session_path"]
                ).exists()
                other_profile_exists = other_channel_profile.exists()
                fetched = handle_channel_session_get(
                    {
                        "meta": {"correlation_id": "corr_get"},
                        "channel": "liepin",
                    }
                )

        self.assertTrue(valid_profile_exists)
        self.assertEqual(cleared["session"]["login_status"], "session_cleared")
        self.assertFalse(cleared_profile_exists)
        self.assertTrue(other_profile_exists)
        self.assertEqual(fetched["session"]["login_status"], "session_cleared")
        self.assertFalse(fetched["session"]["clear_available"])


def _write_check_mode_inputs(root: Path) -> tuple[Path, Path, Path]:
    leads_dir = root / "job_leads"
    leads_dir.mkdir(parents=True)
    lead_path = leads_dir / "jl_submission_check.yaml"
    lead_path.write_text(
        "\n".join(
            [
                'id: "jl_submission_check"',
                'channel: "liepin"',
                'company: "Check Corp"',
                'position: "Backend Engineer"',
                'job_url: "https://www.liepin.com/job/123.shtml"',
                'job_id: "123"',
                'recruiter: "Recruiter A"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    resume_path = root / "outputs" / "quick_runs" / "check" / "exports" / "resume.pdf"
    resume_path.parent.mkdir(parents=True)
    resume_path.write_bytes(b"%PDF-1.4\nfixture\n")
    return leads_dir, resume_path, root / "outputs" / "submissions"


def _check_mode_confirmation_items() -> list[str]:
    return [
        "check_mode_no_real_submit",
        "selected_submission_channel",
        "selected_channel_job_lead",
        "selected_resume_pdf",
        "selected_channel_session_metadata",
        "may_use_channel_shared_session",
        "final_confirm_disabled_and_forbidden",
        "must_stop_before_final_confirm",
    ]


class SubmissionCheckModeTests(SessionBrowserStubTests):
    def test_check_mode_requires_preflight_channel_lead_resume_and_valid_session(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            leads_dir, resume_path, submissions_dir = _write_check_mode_inputs(root)
            sessions_dir = root / "outputs" / "channel_sessions"
            with (
                patch("tools.sidecar.handlers.submission._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
                patch(
                    "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                    sessions_dir,
                ),
            ):
                with self.assertRaises(ValueError) as preflight_error:
                    handle_submission_check_mode(
                        {
                            "meta": {"correlation_id": "corr_missing_preflight"},
                            "channel": "liepin",
                            "job_lead_id": "jl_submission_check",
                            "resume_version_id": "rv_check",
                            "resume_pdf_path": str(resume_path),
                        }
                    )

                login_required = handle_submission_check_mode(
                    {
                        "meta": {"correlation_id": "corr_no_session"},
                        "channel": "liepin",
                        "job_lead_id": "jl_submission_check",
                        "resume_version_id": "rv_check",
                        "resume_pdf_path": str(resume_path),
                        "preflight_confirmed": True,
                        "confirmed_no_real_submit": True,
                        "options": {
                            "confirmation_items": _check_mode_confirmation_items(),
                        },
                    }
                )

        self.assertIn("preflight_confirmation_required", str(preflight_error.exception))
        self.assertEqual(login_required["status"], "login_required")
        self.assertEqual(login_required["next_action"], "go_to_channel_session_setup")

    def test_check_mode_writes_submit_skipped_log_for_valid_session(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            leads_dir, resume_path, submissions_dir = _write_check_mode_inputs(root)
            sessions_dir = root / "outputs" / "channel_sessions"
            with (
                patch("tools.sidecar.handlers.submission._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
                patch(
                    "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                    sessions_dir,
                ),
                patch(
                    "tools.sidecar.handlers.submission._build_submission_check_id",
                    return_value="sc_submission_check",
                ),
            ):
                handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_session"},
                        "channel": "liepin",
                        "login_signals": {
                            "logged_in_user_ui_or_equivalent_authenticated_signal": True
                        },
                    }
                )
                result = handle_submission_check_mode(
                    {
                        "meta": {"correlation_id": "corr_check"},
                        "channel": "liepin",
                        "job_lead_id": "jl_submission_check",
                        "resume_version_id": "rv_check",
                        "resume_pdf_path": str(resume_path),
                        "preflight_confirmed": True,
                        "confirmed_no_real_submit": True,
                        "options": {
                            "confirmation_items": _check_mode_confirmation_items(),
                            "target_recovery_limit": 2,
                            "session_identity_accepted": True,
                        },
                    }
                )
                detail = handle_submission_detail(
                    {
                        "meta": {"correlation_id": "corr_detail"},
                        "submission_id": "sc_submission_check",
                    }
                )
                payload = json.loads(
                    Path(result["log_json_path"]).read_text(encoding="utf-8")
                )

        self.assertEqual(result["status"], "check_mode_success_submit_skipped")
        self.assertFalse(result["final_submit_attempted"])
        self.assertFalse(result["external_submission_attempted"])
        self.assertEqual(result["session_metadata"]["login_status"], "session_valid")
        self.assertIn("liepin", result["adapter_capabilities"]["adapter"])
        step_names = [step["name"] for step in result["steps"]]
        self.assertEqual(
            step_names,
            [
                "rate_limit",
                "open_target",
                "login_check",
                "target_verify",
                "send_resume_path_check",
                "attachment_check",
                "submit_skipped",
            ],
        )
        self.assertEqual(payload["mode"], "check")
        self.assertEqual(payload["terminal_status"], "check_mode_success_submit_skipped")
        self.assertFalse(payload["final_submit_attempted"])
        self.assertEqual(payload["original_job_lead"]["job_lead_id"], "jl_submission_check")
        self.assertEqual(payload["final_verified_target"]["job_url"], "https://www.liepin.com/job/123.shtml")
        self.assertEqual(detail["submission"]["terminal_status"], "check_mode_success_submit_skipped")
        self.assertEqual(detail["submission"]["original_job_lead"]["job_lead_id"], "jl_submission_check")

    def test_check_mode_blocks_identity_rejection_and_rate_limit(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            leads_dir, resume_path, submissions_dir = _write_check_mode_inputs(root)
            sessions_dir = root / "outputs" / "channel_sessions"
            with (
                patch("tools.sidecar.handlers.submission._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
                patch(
                    "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                    sessions_dir,
                ),
            ):
                handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_session"},
                        "channel": "liepin",
                        "login_signals": {
                            "logged_in_user_ui_or_equivalent_authenticated_signal": True
                        },
                    }
                )
                identity = handle_submission_check_mode(
                    {
                        "meta": {"correlation_id": "corr_identity"},
                        "channel": "liepin",
                        "job_lead_id": "jl_submission_check",
                        "resume_version_id": "rv_check",
                        "resume_pdf_path": str(resume_path),
                        "preflight_confirmed": True,
                        "confirmed_no_real_submit": True,
                        "options": {
                            "confirmation_items": _check_mode_confirmation_items(),
                            "session_identity_accepted": False,
                        },
                    }
                )
                rate_limited = handle_submission_check_mode(
                    {
                        "meta": {"correlation_id": "corr_rate"},
                        "channel": "liepin",
                        "job_lead_id": "jl_submission_check",
                        "resume_version_id": "rv_check",
                        "resume_pdf_path": str(resume_path),
                        "preflight_confirmed": True,
                        "confirmed_no_real_submit": True,
                        "options": {
                            "confirmation_items": _check_mode_confirmation_items(),
                            "simulate_rate_limited": True,
                        },
                    }
                )

        self.assertEqual(identity["status"], "account_identity_mismatch")
        self.assertEqual(
            identity["next_action"],
            "go_to_channel_session_setup_to_clear_or_refresh",
        )
        self.assertEqual(rate_limited["status"], "rate_limited")
        self.assertEqual(rate_limited["steps"][0]["name"], "rate_limit")
        self.assertEqual(rate_limited["steps"][0]["status"], "blocked")


class FeedbackIterationTests(SessionBrowserStubTests):
    def test_feedback_iteration_lists_items_requires_action_and_preserves_artifacts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            leads_dir, resume_path, submissions_dir = _write_check_mode_inputs(root)
            sessions_dir = root / "outputs" / "channel_sessions"
            iterations_dir = root / "outputs" / "feedback_iterations"
            original_resume_bytes = resume_path.read_bytes()
            with (
                patch("tools.sidecar.handlers.submission._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
                patch(
                    "tools.sidecar.handlers.submission._CHANNEL_SESSIONS_DIR",
                    sessions_dir,
                ),
                patch(
                    "tools.sidecar.handlers.submission._FEEDBACK_ITERATIONS_DIR",
                    iterations_dir,
                ),
                patch(
                    "tools.sidecar.handlers.submission._build_submission_check_id",
                    return_value="sc_feedback_source",
                ),
                patch(
                    "tools.sidecar.handlers.submission._build_feedback_iteration_id",
                    return_value="fi_feedback_iteration",
                ),
            ):
                handle_channel_session_check(
                    {
                        "meta": {"correlation_id": "corr_session"},
                        "channel": "liepin",
                        "login_signals": {
                            "logged_in_user_ui_or_equivalent_authenticated_signal": True
                        },
                    }
                )
                check_mode = handle_submission_check_mode(
                    {
                        "meta": {"correlation_id": "corr_check"},
                        "channel": "liepin",
                        "job_lead_id": "jl_submission_check",
                        "resume_version_id": "rv_check",
                        "resume_pdf_path": str(resume_path),
                        "preflight_confirmed": True,
                        "confirmed_no_real_submit": True,
                        "options": {
                            "confirmation_items": _check_mode_confirmation_items(),
                            "session_identity_accepted": True,
                        },
                    }
                )
                feedback = handle_feedback_list(
                    {
                        "meta": {"correlation_id": "corr_feedback"},
                        "source_run_id": "sc_feedback_source",
                    }
                )
                with self.assertRaises(ValueError) as missing_action:
                    handle_feedback_create_iteration(
                        {
                            "meta": {"correlation_id": "corr_missing_action"},
                            "source_run_id": "sc_feedback_source",
                            "source_feedback_items": feedback["items"],
                            "selected_actions": [],
                        }
                    )
                with self.assertRaises(ValueError) as unsupported_source:
                    handle_feedback_create_iteration(
                        {
                            "meta": {"correlation_id": "corr_bad_source"},
                            "source_run_id": "sc_feedback_source",
                            "source_feedback_items": [
                                {
                                    "source_type": "unsupported",
                                    "source_run_id": "sc_feedback_source",
                                    "source_artifact_path_or_id": "x",
                                    "summary": "x",
                                    "severity_or_priority": "high",
                                    "recommended_next_action": "x",
                                }
                            ],
                            "selected_actions": ["acknowledge_and_skip"],
                            "user_notes": "skip",
                        }
                    )
                with self.assertRaises(ValueError) as evidence_required:
                    handle_feedback_create_iteration(
                        {
                            "meta": {"correlation_id": "corr_claim"},
                            "source_run_id": "sc_feedback_source",
                            "source_feedback_items": feedback["items"],
                            "selected_actions": [
                                "regenerate_resume_from_existing_evidence"
                            ],
                            "new_or_updated_claims": ["new claim"],
                        }
                    )
                iteration = handle_feedback_create_iteration(
                    {
                        "meta": {"correlation_id": "corr_iteration"},
                        "source_run_id": "sc_feedback_source",
                        "source_feedback_items": feedback["items"],
                        "selected_actions": [
                            "regenerate_resume_from_existing_evidence",
                            "prepare_next_check_mode",
                        ],
                        "user_notes": "Regenerate from existing evidence.",
                        "evidence_card_ids_added_or_updated": ["ec_feedback"],
                        "new_or_updated_claims": ["Claim linked to evidence"],
                        "remaining_gap_tasks": ["Confirm messaging fit"],
                    }
                )
                record_payload = json.loads(
                    Path(iteration["record_path"]).read_text(encoding="utf-8")
                )
                source_snapshot_exists = Path(
                    iteration["iteration"]["source_snapshot_path"]
                ).exists()
                new_resume_exists = Path(
                    iteration["iteration"]["affected_artifacts"]["new_resume_path"]
                ).exists()
                original_resume_preserved = resume_path.read_bytes()

        self.assertEqual(check_mode["status"], "check_mode_success_submit_skipped")
        self.assertGreaterEqual(len(feedback["items"]), 1)
        self.assertIn("feedback_action_required", str(missing_action.exception))
        self.assertIn("unsupported_feedback_source", str(unsupported_source.exception))
        self.assertIn("new_claims_require_evidence_links", str(evidence_required.exception))
        self.assertEqual(iteration["status"], "iteration_recorded")
        self.assertEqual(iteration["iteration"]["source_run_id"], "sc_feedback_source")
        self.assertEqual(iteration["iteration"]["previous_resume_version_id"], "rv_check")
        self.assertTrue(iteration["iteration"]["new_resume_version_id_or_none"])
        self.assertTrue(source_snapshot_exists)
        self.assertTrue(new_resume_exists)
        self.assertEqual(original_resume_preserved, original_resume_bytes)
        self.assertTrue(iteration["iteration"]["previous_artifacts_preserved"])
        self.assertTrue(iteration["iteration"]["immutable_source_snapshot"])
        self.assertTrue(iteration["iteration"]["real_submit_disabled"])
        self.assertEqual(
            iteration["next_check_mode_candidate"]["resume_version_id"],
            iteration["iteration"]["new_resume_version_id_or_none"],
        )
        self.assertTrue(iteration["next_check_mode_candidate"]["real_submit_disabled"])
        self.assertEqual(record_payload["comparison_summary"]["evidence_ids_used"], ["ec_feedback"])
        self.assertEqual(
            record_payload["comparison_summary"]["new_or_updated_claims"][0]["evidence_ids"],
            ["ec_feedback"],
        )


if __name__ == "__main__":
    unittest.main()
