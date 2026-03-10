import unittest
from unittest.mock import patch
from typing import Any

from tools.sidecar.handlers.overview import handle_overview_get, _score_from_doc


class OverviewGetTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.overview._list_recent_activity")
    @patch("tools.sidecar.handlers.overview._build_match_trend")
    @patch("tools.sidecar.handlers.overview._build_gaps")
    @patch("tools.sidecar.handlers.overview._count_submission_runs")
    @patch("tools.sidecar.handlers.overview._count_resume_versions")
    @patch("tools.sidecar.handlers.overview._count_matching_reports")
    @patch("tools.sidecar.handlers.overview._count_evidence_cards")
    def test_returns_dashboard_sections(
        self,
        mock_evidence: Any,
        mock_matching: Any,
        mock_resumes: Any,
        mock_submissions: Any,
        mock_gaps: Any,
        mock_trend: Any,
        mock_activity: Any,
    ) -> None:
        mock_evidence.return_value = 12
        mock_matching.return_value = 8
        mock_resumes.return_value = 5
        mock_submissions.return_value = 23
        mock_gaps.return_value = [
            {
                "gap_id": "gap_1",
                "severity": "high",
                "description": "Need more quantified evidence",
                "suggested_action": "Add evidence with measurable outcomes",
            }
        ]
        mock_trend.return_value = [
            {"date": "2026-02-28", "score": 81},
            {"date": "2026-03-07", "score": 87},
        ]
        mock_activity.return_value = [
            {
                "activity_id": "act_1",
                "type": "resume_generated",
                "timestamp": "2026-03-07T10:00:00Z",
                "description": "Created resume_mr-2026-005_A.md",
            }
        ]

        result = handle_overview_get({"meta": {"correlation_id": "corr_001"}})

        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertEqual(result["metrics"]["evidence_count"], 12)
        self.assertEqual(result["metrics"]["matched_jobs_count"], 8)
        self.assertEqual(result["metrics"]["resume_count"], 5)
        self.assertEqual(result["metrics"]["submission_count"], 23)
        self.assertEqual(len(result["recent_activities"]), 1)
        self.assertEqual(len(result["match_trend"]), 2)
        self.assertEqual(len(result["gaps"]), 1)


class ScoreFromDocTests(unittest.TestCase):
    def test_uses_score_total_when_present(self) -> None:
        doc = {"scalars": {"score_total": "85"}, "lists": {}}
        self.assertEqual(_score_from_doc(doc), 85)

    def test_falls_back_to_score_breakdown_sum(self) -> None:
        doc = {
            "scalars": {},
            "lists": {
                "score_breakdown": {"keywords": "30", "depth": "25", "stack": "20"}
            },
        }
        self.assertEqual(_score_from_doc(doc), 75)

    def test_returns_zero_when_no_score_data(self) -> None:
        doc = {"scalars": {}, "lists": {}}
        self.assertEqual(_score_from_doc(doc), 0)

    def test_caps_score_at_100(self) -> None:
        doc = {"scalars": {}, "lists": {"score_breakdown": {"a": "60", "b": "60"}}}
        self.assertEqual(_score_from_doc(doc), 100)


if __name__ == "__main__":
    unittest.main()
