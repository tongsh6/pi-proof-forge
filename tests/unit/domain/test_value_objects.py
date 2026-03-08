import unittest

from tools.domain.result import Err
from tools.domain.value_objects import (
    Candidate,
    ChannelFailure,
    DeliveryResult,
    GapItem,
    GapTask,
    GateDecision,
    GateFailure,
    MatchTrendPoint,
    Score,
    ScreenshotRef,
    SubmissionStep,
)


class ScoreTests(unittest.TestCase):
    def test_score_is_comparable(self) -> None:
        self.assertGreater(Score(value=85.0), Score(value=70.0))
        self.assertEqual(Score(value=80.0), Score(value=80.0))

    def test_score_is_frozen(self) -> None:
        s = Score(value=90.0)
        with self.assertRaises(AttributeError):
            s.value = 50.0  # type: ignore[misc]


class GapTaskTests(unittest.TestCase):
    def test_gap_task_fields(self) -> None:
        gt = GapTask(description="Add K8s experience", priority="high", source="matching")
        self.assertEqual(gt.description, "Add K8s experience")
        self.assertEqual(gt.priority, "high")
        self.assertEqual(gt.source, "matching")

    def test_gap_task_is_frozen(self) -> None:
        gt = GapTask(description="x", priority="low", source="eval")
        with self.assertRaises(AttributeError):
            gt.description = "y"  # type: ignore[misc]


class CandidateTests(unittest.TestCase):
    def test_candidate_has_required_fields(self) -> None:
        c = Candidate(
            candidate_id="cand-001",
            direction="backend",
            company="Acme Inc",
            job_url="https://example.com/job/1",
            confidence=0.85,
            source="job_leads",
            merged_sources=("job_leads", "jd_inputs"),
        )
        self.assertEqual(c.candidate_id, "cand-001")
        self.assertEqual(c.direction, "backend")
        self.assertEqual(c.company, "Acme Inc")
        self.assertEqual(c.job_url, "https://example.com/job/1")
        self.assertAlmostEqual(c.confidence, 0.85)
        self.assertEqual(c.source, "job_leads")
        self.assertEqual(c.merged_sources, ("job_leads", "jd_inputs"))

    def test_candidate_is_frozen(self) -> None:
        c = Candidate(
            candidate_id="cand-001",
            direction="backend",
            company="Acme",
            job_url="https://example.com",
            confidence=0.5,
            source="jd_inputs",
            merged_sources=(),
        )
        with self.assertRaises(AttributeError):
            c.company = "Other"  # type: ignore[misc]


class GateFailureTests(unittest.TestCase):
    def test_gate_failure_as_err_type(self) -> None:
        gf = GateFailure(reason="score_below_threshold", details="matching=60 < 75")
        err = Err(error=gf)
        self.assertEqual(err.error.reason, "score_below_threshold")

    def test_gate_failure_is_frozen(self) -> None:
        gf = GateFailure(reason="x", details="y")
        with self.assertRaises(AttributeError):
            gf.reason = "z"  # type: ignore[misc]


class ChannelFailureTests(unittest.TestCase):
    def test_channel_failure_as_err_type(self) -> None:
        cf = ChannelFailure(channel_id="liepin", reason="login_expired", details="session timeout")
        err = Err(error=cf)
        self.assertEqual(err.error.channel_id, "liepin")
        self.assertEqual(err.error.reason, "login_expired")


class GateDecisionTests(unittest.TestCase):
    def test_gate_decision_fields(self) -> None:
        gd = GateDecision(passed=True, pass_count=2, details="all gates passed")
        self.assertTrue(gd.passed)
        self.assertEqual(gd.pass_count, 2)


class DeliveryResultTests(unittest.TestCase):
    def test_delivery_result_is_not_anonymous_dict(self) -> None:
        dr = DeliveryResult(
            channel_id="email",
            success=True,
            submission_id="sub-001",
            message="delivered",
        )
        self.assertEqual(dr.channel_id, "email")
        self.assertTrue(dr.success)
        self.assertEqual(dr.submission_id, "sub-001")

    def test_delivery_result_is_frozen(self) -> None:
        dr = DeliveryResult(channel_id="x", success=True, submission_id="s", message="m")
        with self.assertRaises(AttributeError):
            dr.success = False  # type: ignore[misc]


class MatchTrendPointTests(unittest.TestCase):
    def test_match_trend_point_fields(self) -> None:
        mtp = MatchTrendPoint(date="2026-03-01", score=82.5, job_profile_id="jp-2026-001")
        self.assertEqual(mtp.date, "2026-03-01")
        self.assertAlmostEqual(mtp.score, 82.5)


class GapItemTests(unittest.TestCase):
    def test_gap_item_fields(self) -> None:
        gi = GapItem(description="Missing cloud cert", category="skill", severity="medium")
        self.assertEqual(gi.category, "skill")


class SubmissionStepTests(unittest.TestCase):
    def test_submission_step_fields(self) -> None:
        ss = SubmissionStep(
            step_name="upload_resume",
            status="completed",
            timestamp="2026-03-01T10:00:00Z",
        )
        self.assertEqual(ss.step_name, "upload_resume")
        self.assertEqual(ss.status, "completed")


class ScreenshotRefTests(unittest.TestCase):
    def test_screenshot_ref_fields(self) -> None:
        sr = ScreenshotRef(resource_id="scr-001", step_name="upload_resume", mime_type="image/png")
        self.assertEqual(sr.resource_id, "scr-001")
        self.assertEqual(sr.mime_type, "image/png")


if __name__ == "__main__":
    unittest.main()
