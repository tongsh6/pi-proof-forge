import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.submission import (
    handle_submission_detail,
    handle_submission_list,
    handle_submission_retry,
)


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


if __name__ == "__main__":
    unittest.main()
