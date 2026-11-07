import datetime
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.submission.rate_limit import RateLimitConfig, SubmissionRateLimiter
from tools.submission.liepin import LiepinSubmissionConfig, run_liepin_submission


class Clock:
    def __init__(self, current: datetime.datetime) -> None:
        self.current = current

    def now(self) -> datetime.datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += datetime.timedelta(seconds=seconds)


class SubmissionRateLimitTests(unittest.TestCase):
    def test_allows_until_batch_limit_then_requires_cooldown(self) -> None:
        with TemporaryDirectory() as tmp:
            clock = Clock(datetime.datetime(2026, 5, 12, 10, 0, tzinfo=datetime.timezone.utc))
            limiter = SubmissionRateLimiter(Path(tmp) / "rate.json", now=clock.now)
            config = RateLimitConfig(max_per_batch=2, cooldown_seconds=900, daily_limit=10)

            first = limiter.check_and_record(config)
            second = limiter.check_and_record(config)
            third = limiter.check_and_record(config)

            self.assertTrue(first.allowed)
            self.assertTrue(second.allowed)
            self.assertFalse(third.allowed)
            self.assertEqual(third.reason, "batch_cooldown")
            self.assertEqual(third.wait_seconds, 900)

    def test_resets_batch_after_cooldown(self) -> None:
        with TemporaryDirectory() as tmp:
            clock = Clock(datetime.datetime(2026, 5, 12, 10, 0, tzinfo=datetime.timezone.utc))
            limiter = SubmissionRateLimiter(Path(tmp) / "rate.json", now=clock.now)
            config = RateLimitConfig(max_per_batch=1, cooldown_seconds=900, daily_limit=10)

            self.assertTrue(limiter.check_and_record(config).allowed)
            self.assertFalse(limiter.check_and_record(config).allowed)

            clock.advance(901)
            decision = limiter.check_and_record(config)

            self.assertTrue(decision.allowed)
            self.assertEqual(decision.batch_count, 1)
            self.assertEqual(decision.daily_count, 2)

    def test_blocks_after_daily_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            clock = Clock(datetime.datetime(2026, 5, 12, 10, 0, tzinfo=datetime.timezone.utc))
            limiter = SubmissionRateLimiter(Path(tmp) / "rate.json", now=clock.now)
            config = RateLimitConfig(max_per_batch=10, cooldown_seconds=900, daily_limit=2)

            self.assertTrue(limiter.check_and_record(config).allowed)
            self.assertTrue(limiter.check_and_record(config).allowed)
            third = limiter.check_and_record(config)

            self.assertFalse(third.allowed)
            self.assertEqual(third.reason, "daily_limit_exceeded")

    def test_disabled_when_limits_are_zero(self) -> None:
        with TemporaryDirectory() as tmp:
            limiter = SubmissionRateLimiter(Path(tmp) / "rate.json")
            config = RateLimitConfig(max_per_batch=0, cooldown_seconds=0, daily_limit=0)

            for _ in range(10):
                self.assertTrue(limiter.check_and_record(config).allowed)

    def test_liepin_submission_blocks_before_browser_when_rate_limited(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "submissions"
            state_path = output_dir / "liepin_rate_limit.json"
            state_path.parent.mkdir(parents=True)
            fixed_now = datetime.datetime(2026, 5, 12, 10, 5, tzinfo=datetime.timezone.utc)
            state_path.write_text(
                "{"
                '"day":"2026-05-12",'
                '"daily_count":1,'
                '"batch_count":1,'
                f'"last_at":{fixed_now.timestamp() - 300}'
                "}",
                encoding="utf-8",
            )
            config = LiepinSubmissionConfig(
                job_url="https://www.liepin.com/job/123456.shtml",
                resume_path="outputs/resume.md",
                profile_path="profiles/candidate_profile.yaml",
                headless=True,
                dry_run=False,
                submit=False,
                output_dir=str(output_dir),
                session_dir=str(Path(tmp) / "sessions"),
                timeout_ms=45_000,
                rate_limit_max_per_batch=1,
                rate_limit_cooldown_seconds=900,
                rate_limit_daily_limit=10,
            )

            with patch("tools.submission.rate_limit.datetime") as datetime_mod:
                datetime_mod.datetime.now.return_value = fixed_now
                datetime_mod.datetime.fromtimestamp = datetime.datetime.fromtimestamp
                datetime_mod.timezone = datetime.timezone
                code = run_liepin_submission(config)

            self.assertEqual(code, 14)
            logs = sorted(output_dir.glob("liepin/*/submission_log.yaml"))
            self.assertEqual(len(logs), 1)
            content = logs[0].read_text(encoding="utf-8")
            self.assertIn('name: "rate_limit"', content)
            self.assertIn('status: "blocked"', content)
            self.assertIn("batch_cooldown", content)


if __name__ == "__main__":
    unittest.main()
