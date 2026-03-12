import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch
from typing import Any

from tools.infra.persistence.yaml_io import ParsedDoc
from tools.sidecar.handlers.overview import (
    _count_matched_job_profiles,
    _build_match_trend,
    _score_from_doc,
    handle_overview_get,
)


class OverviewGetTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.overview._list_recent_activity")
    @patch("tools.sidecar.handlers.overview._build_match_trend")
    @patch("tools.sidecar.handlers.overview._build_gaps")
    @patch("tools.sidecar.handlers.overview._count_submission_runs")
    @patch("tools.sidecar.handlers.overview._count_resume_versions")
    @patch("tools.sidecar.handlers.overview._count_matched_job_profiles")
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

        result = cast(
            dict[str, Any],
            handle_overview_get({"meta": {"correlation_id": "corr_001"}}),
        )

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
        doc = cast(object, {"scalars": {"score_total": "85"}, "lists": {}})
        parsed = cast(ParsedDoc, doc)
        self.assertEqual(_score_from_doc(parsed), 85)

    def test_falls_back_to_score_breakdown_sum(self) -> None:
        doc = cast(
            object,
            {
                "scalars": {},
                "lists": {
                    "score_breakdown": {
                        "keywords": "30",
                        "depth": "25",
                        "stack": "20",
                    }
                },
            },
        )
        parsed = cast(ParsedDoc, doc)
        self.assertEqual(_score_from_doc(parsed), 75)

    def test_reads_nested_score_breakdown_scores(self) -> None:
        doc = cast(
            object,
            {
                "scalars": {},
                "lists": {
                    "score_breakdown": {
                        "K": {"score": "30", "reason": "keywords"},
                        "D": {"score": "25", "reason": "depth"},
                        "S": {"score": "20", "reason": "stack"},
                    }
                },
            },
        )
        parsed = cast(ParsedDoc, doc)
        self.assertEqual(_score_from_doc(parsed), 75)

    def test_returns_zero_when_no_score_data(self) -> None:
        doc = cast(object, {"scalars": {}, "lists": {}})
        parsed = cast(ParsedDoc, doc)
        self.assertEqual(_score_from_doc(parsed), 0)

    def test_caps_score_at_100(self) -> None:
        doc = cast(
            object,
            {"scalars": {}, "lists": {"score_breakdown": {"a": "60", "b": "60"}}},
        )
        parsed = cast(ParsedDoc, doc)
        self.assertEqual(_score_from_doc(parsed), 100)


class CountMatchedJobProfilesTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.overview._read_yaml_doc")
    @patch("tools.sidecar.handlers.overview._glob_files")
    def test_counts_distinct_job_profile_ids(
        self, mock_glob_files: Any, mock_read_yaml_doc: Any
    ) -> None:
        mock_glob_files.return_value = [Path("a.yaml"), Path("b.yaml"), Path("c.yaml")]
        mock_read_yaml_doc.side_effect = [
            cast(
                ParsedDoc,
                cast(object, {"scalars": {"job_profile_id": "jp-1"}, "lists": {}}),
            ),
            cast(
                ParsedDoc,
                cast(object, {"scalars": {"job_profile_id": "jp-1"}, "lists": {}}),
            ),
            cast(
                ParsedDoc,
                cast(object, {"scalars": {"job_profile_id": "jp-2"}, "lists": {}}),
            ),
        ]

        self.assertEqual(_count_matched_job_profiles(), 2)


class BuildMatchTrendTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.overview._glob_files")
    def test_reads_score_breakdown_from_real_yaml_text_when_score_total_missing(
        self, mock_glob_files: Any
    ) -> None:
        with TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "mr.yaml"
            report_path.write_text(
                "\n".join(
                    [
                        'job_profile_id: "jp-1"',
                        "score_breakdown:",
                        '  K: { score: 19, reason: "kw" }',
                        '  D: { score: 12, reason: "domain" }',
                        '  S: { score: 14, reason: "scope" }',
                        'generated_at: "2026-03-10T10:00:00+08:00"',
                    ]
                ),
                encoding="utf-8",
            )
            mock_glob_files.return_value = [report_path]

            trend = _build_match_trend()

        self.assertEqual(len(trend), 1)
        self.assertEqual(trend[0]["score"], 45)


if __name__ == "__main__":
    unittest.main()
