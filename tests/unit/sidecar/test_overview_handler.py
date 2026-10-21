import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch
from typing import Any

from tools.infra.persistence.yaml_io import ParsedDoc
from tools.sidecar.handlers import overview
from tools.sidecar.handlers.overview import (
    _count_matched_job_profiles,
    _build_match_trend,
    _list_recent_activity,
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


class ListRecentActivityTests(unittest.TestCase):
    """活动流不得回显运行编号/文件名，必须给出可读的目标岗位、公司、平台与状态。"""

    def _workspace(self, tmp_dir: str) -> tuple[Path, Path, Path, Path, Path]:
        root = Path(tmp_dir)
        outputs = root / "outputs"
        evidence = root / "evidence_cards"
        reports = root / "matching_reports"
        profiles = root / "job_profiles"
        submissions = outputs / "submissions"
        for path in (outputs, evidence, reports, profiles, submissions):
            path.mkdir(parents=True, exist_ok=True)
        return outputs, evidence, reports, profiles, submissions

    def _activity(self, outputs: Path, evidence: Path, reports: Path, profiles: Path, submissions: Path) -> list[dict[str, str]]:
        with ExitStack() as stack:
            stack.enter_context(patch.object(overview, "_OUTPUTS_DIR", outputs))
            stack.enter_context(patch.object(overview, "_EVIDENCE_DIR", evidence))
            stack.enter_context(patch.object(overview, "_MATCHING_REPORT_DIR", reports))
            stack.enter_context(patch.object(overview, "_JOB_PROFILE_DIR", profiles))
            stack.enter_context(patch.object(overview, "_SUBMISSIONS_DIR", submissions))
            return _list_recent_activity()

    def test_resume_activity_carries_job_target_and_variant_without_run_id(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs, evidence, reports, profiles, submissions = self._workspace(tmp_dir)
            run_dir = outputs / "qr_20261021133955495233"
            run_dir.mkdir()
            (run_dir / "resume_mr-qr_20261021133955495233_B.md").write_text("# 简历\n", encoding="utf-8")
            (reports / "mr-qr_20261021133955495233.yaml").write_text(
                'job_profile_id: "jp_1"\n', encoding="utf-8"
            )
            (profiles / "jp_1.yaml").write_text(
                'target_role: "高级全栈工程师"\ncompany: "某上海专业技术服务公司"\n',
                encoding="utf-8",
            )

            items = self._activity(outputs, evidence, reports, profiles, submissions)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["type"], "resume_generated")
        self.assertEqual(item["target_role"], "高级全栈工程师")
        self.assertEqual(item["company"], "某上海专业技术服务公司")
        self.assertEqual(item["variant"], "B")
        self.assertNotIn("resume_mr", item["description"])
        self.assertNotIn("qr_2026", item["description"])

    def test_resume_activity_without_report_does_not_fall_back_to_file_name(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs, evidence, reports, profiles, submissions = self._workspace(tmp_dir)
            (outputs / "resume_mr-2026-005_A.md").write_text("# 简历\n", encoding="utf-8")

            items = self._activity(outputs, evidence, reports, profiles, submissions)

        self.assertEqual(len(items), 1)
        description = items[0]["description"]
        self.assertNotIn("resume_mr", description)
        self.assertNotIn("2026-005", description)
        self.assertIn("A", description)

    def test_submission_activity_carries_target_platform_and_status_without_run_id(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs, evidence, reports, profiles, submissions = self._workspace(tmp_dir)
            self._write_submission_log(submissions, status="success")

            items = self._activity(outputs, evidence, reports, profiles, submissions)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["type"], "submission_sent")
        self.assertEqual(item["target_role"], "高级全栈工程师")
        self.assertEqual(item["company"], "某上海专业技术服务公司")
        self.assertEqual(item["platform"], "liepin")
        self.assertEqual(item["status"], "success")
        self.assertNotIn("native-f61d", item["description"])

    def test_submission_activity_fallback_does_not_claim_sent_when_blocked(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs, evidence, reports, profiles, submissions = self._workspace(tmp_dir)
            self._write_submission_log(submissions, status="blocked")

            items = self._activity(outputs, evidence, reports, profiles, submissions)

        description = items[0]["description"]
        self.assertNotIn("Submitted to", description)
        self.assertIn("blocked", description)
        self.assertIn("高级全栈工程师", description)

    def _write_submission_log(self, submissions: Path, status: str) -> None:
        run_dir = submissions / "liepin" / "native-f61d3037e09f4a8dbdc0d15684746fa9"
        run_dir.mkdir(parents=True)
        (run_dir / "submission_log.json").write_text(
            json.dumps(
                {
                    "run_id": "native-f61d3037e09f4a8dbdc0d15684746fa9",
                    "platform": "liepin",
                    "mode": "submit",
                    "status": status,
                    "ended_at": "2026-10-21T15:17:33+00:00",
                    "input_artifacts": {
                        "company": "某上海专业技术服务公司",
                        "position": "高级全栈工程师",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_resume_activity_ignores_non_variant_suffix(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs, evidence, reports, profiles, submissions = self._workspace(tmp_dir)
            (outputs / "resume_mr-qr_20261021133955495233.md").write_text(
                "# 简历\n", encoding="utf-8"
            )

            items = self._activity(outputs, evidence, reports, profiles, submissions)

        item = items[0]
        self.assertNotIn("variant", item)
        self.assertNotIn("20261021133955495233", item["description"])

    def test_evidence_activity_carries_title(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs, evidence, reports, profiles, submissions = self._workspace(tmp_dir)
            (evidence / "ec_1.yaml").write_text(
                'title: "MongoDB 索引治理"\n', encoding="utf-8"
            )

            items = self._activity(outputs, evidence, reports, profiles, submissions)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "evidence_imported")
        self.assertEqual(items[0]["title"], "MongoDB 索引治理")
        self.assertIn("MongoDB 索引治理", items[0]["description"])


if __name__ == "__main__":
    unittest.main()
