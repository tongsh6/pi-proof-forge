import unittest

from tools.domain.models import (
    ActivityLog,
    EvidenceCard,
    JobLead,
    JobProfile,
    MatchingReport,
    PersonalProfile,
    ResumeOutput,
    Scorecard,
    UploadedResume,
)


class EvidenceCardEligibilityTests(unittest.TestCase):
    def test_eligible_when_results_and_artifacts_present(self) -> None:
        card = EvidenceCard(
            id="ec-2026-001",
            title="Built CI pipeline",
            raw_source="logs/ci.md",
            results=("Reduced build time by 40%",),
            artifacts=("pipeline.yaml",),
        )
        self.assertTrue(card.is_eligible())

    def test_not_eligible_when_results_empty(self) -> None:
        card = EvidenceCard(
            id="ec-2026-002",
            title="Some work",
            raw_source="logs/work.md",
            results=(),
            artifacts=("doc.pdf",),
        )
        self.assertFalse(card.is_eligible())

    def test_not_eligible_when_artifacts_empty(self) -> None:
        card = EvidenceCard(
            id="ec-2026-003",
            title="Some work",
            raw_source="logs/work.md",
            results=("Result A",),
            artifacts=(),
        )
        self.assertFalse(card.is_eligible())

    def test_evidence_card_is_frozen(self) -> None:
        card = EvidenceCard(
            id="ec-2026-001",
            title="X",
            raw_source="x",
            results=("r",),
            artifacts=("a",),
        )
        with self.assertRaises(AttributeError):
            card.title = "Y"  # type: ignore[misc]


class JobProfileTests(unittest.TestCase):
    def test_job_profile_minimal_fields(self) -> None:
        jp = JobProfile(
            id="jp-2026-001",
            title="Senior Backend Engineer",
            keywords=("Python", "Kubernetes", "PostgreSQL"),
            level="senior",
        )
        self.assertEqual(jp.id, "jp-2026-001")
        self.assertEqual(jp.title, "Senior Backend Engineer")
        self.assertEqual(jp.level, "senior")
        self.assertIn("Python", jp.keywords)

    def test_job_profile_is_frozen(self) -> None:
        jp = JobProfile(id="jp-001", title="X", keywords=(), level="mid")
        with self.assertRaises(AttributeError):
            jp.title = "Y"  # type: ignore[misc]


class MatchingReportTests(unittest.TestCase):
    def test_matching_report_fields(self) -> None:
        mr = MatchingReport(
            job_profile_id="jp-2026-001",
            evidence_card_ids=("ec-2026-001", "ec-2026-002"),
            score_breakdown={"keyword": 80.0, "domain": 75.0},
            gap_tasks=("Need K8s cert",),
        )
        self.assertEqual(mr.job_profile_id, "jp-2026-001")
        self.assertEqual(len(mr.evidence_card_ids), 2)
        self.assertIn("keyword", mr.score_breakdown)
        self.assertEqual(len(mr.gap_tasks), 1)


class ResumeOutputTests(unittest.TestCase):
    def test_resume_output_minimal_fields(self) -> None:
        ro = ResumeOutput(
            version="v1",
            job_profile_id="jp-2026-001",
            content="Resume content here",
            format="markdown",
        )
        self.assertEqual(ro.version, "v1")
        self.assertEqual(ro.format, "markdown")


class ScorecardTests(unittest.TestCase):
    def test_scorecard_minimal_fields(self) -> None:
        sc = Scorecard(
            resume_version="v1",
            job_profile_id="jp-2026-001",
            total_score=82.5,
            dimension_scores={"coverage": 85.0, "clarity": 80.0},
        )
        self.assertAlmostEqual(sc.total_score, 82.5)
        self.assertIn("coverage", sc.dimension_scores)


class PersonalProfileTests(unittest.TestCase):
    def test_personal_profile_fields(self) -> None:
        pp = PersonalProfile(
            name="Zhang San",
            phone="13800000000",
            email="zhangsan@example.com",
            city="Shanghai",
            current_title="Senior Engineer",
        )
        self.assertEqual(pp.name, "Zhang San")
        self.assertEqual(pp.city, "Shanghai")

    def test_personal_profile_is_frozen(self) -> None:
        pp = PersonalProfile(name="X", phone="1", email="e", city="c", current_title="t")
        with self.assertRaises(AttributeError):
            pp.name = "Y"  # type: ignore[misc]


class JobLeadTests(unittest.TestCase):
    def test_job_lead_fields(self) -> None:
        jl = JobLead(
            id="jl-001",
            source="liepin",
            url="https://liepin.com/job/123",
            company="Acme Inc",
            title="Backend Dev",
            status="new",
            favorited=False,
        )
        self.assertEqual(jl.source, "liepin")
        self.assertFalse(jl.favorited)


class UploadedResumeTests(unittest.TestCase):
    def test_uploaded_resume_fields(self) -> None:
        ur = UploadedResume(
            id="ur-001",
            filename="resume_v3.pdf",
            language="zh",
            uploaded_at="2026-03-01T10:00:00Z",
            source_channel="manual",
        )
        self.assertEqual(ur.filename, "resume_v3.pdf")
        self.assertEqual(ur.language, "zh")


class ActivityLogTests(unittest.TestCase):
    def test_activity_log_fields(self) -> None:
        al = ActivityLog(
            type="submission",
            timestamp="2026-03-01T10:00:00Z",
            description="Submitted to Acme Inc",
            resource_id="sub-001",
        )
        self.assertEqual(al.type, "submission")
        self.assertEqual(al.resource_id, "sub-001")


if __name__ == "__main__":
    unittest.main()
