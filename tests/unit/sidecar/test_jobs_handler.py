import unittest
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.jobs import handle_jobs_list_profiles


class JobsListProfilesTests(unittest.TestCase):
    def test_returns_profiles_with_derived_matching_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            job_profiles_dir.mkdir()
            matching_reports_dir.mkdir()

            (job_profiles_dir / "jp-2026-001.yaml").write_text(
                "\n".join(
                    [
                        'target_role: "Senior Backend Engineer"',
                        'company: "Acme"',
                        'source_jd: "jd_inputs/jd-2026-001.txt"',
                        'business_domain: "E-commerce"',
                        'tone: "architecture"',
                        "must_have:",
                        '  - "Distributed systems"',
                        '  - "Stability"',
                        "nice_to_have:",
                        '  - "FinOps"',
                        "keywords:",
                        '  - "Python"',
                        '  - "Kafka"',
                        "seniority_signal:",
                        '  - "Owner"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (matching_reports_dir / "mr-2026-001.yaml").write_text(
                "\n".join(
                    [
                        'job_profile_id: "jp-2026-001"',
                        "evidence_card_ids:",
                        '  - "ec-001"',
                        '  - "ec-002"',
                        'score_total: "82"',
                        'generated_at: "2026-03-08T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            params = {
                "meta": {"correlation_id": "corr_jobs_1"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }

            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", job_profiles_dir),
                patch(
                    "tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR",
                    matching_reports_dir,
                ),
            ):
                result = handle_jobs_list_profiles(params)

        self.assertEqual(result["meta"]["correlation_id"], "corr_jobs_1")
        self.assertIsNone(result["next_cursor"])
        self.assertEqual(len(result["items"]), 1)

        item = result["items"][0]
        self.assertEqual(item["job_profile_id"], "jp-2026-001")
        self.assertEqual(item["title"], "Senior Backend Engineer")
        self.assertEqual(item["company"], "Acme")
        self.assertEqual(item["status"], "active")
        self.assertEqual(item["match_score"], 82)
        self.assertEqual(item["evidence_count"], 2)
        self.assertEqual(item["resume_count"], 0)
        self.assertEqual(item["business_domain"], "E-commerce")
        self.assertEqual(item["keywords"], ["Python", "Kafka"])
        self.assertEqual(item["must_have"], ["Distributed systems", "Stability"])

    def test_filters_profiles_by_status_query_and_tags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            job_profiles_dir.mkdir()
            matching_reports_dir.mkdir()

            (job_profiles_dir / "jp-2026-001.yaml").write_text(
                "\n".join(
                    [
                        'target_role: "Senior Backend Engineer"',
                        'company: "Acme"',
                        "keywords:",
                        '  - "Python"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (job_profiles_dir / "jp-2026-002.yaml").write_text(
                "\n".join(
                    [
                        'target_role: "Java Tech Lead"',
                        'company: "Dewu"',
                        'status: "draft"',
                        "keywords:",
                        '  - "Java"',
                        '  - "Redis"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (matching_reports_dir / "mr-2026-002.yaml").write_text(
                "\n".join(
                    [
                        'job_profile_id: "jp-2026-001"',
                        'score_total: "76"',
                        'generated_at: "2026-03-08T09:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            params = {
                "meta": {"correlation_id": "corr_jobs_2"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "match_score", "order": "desc"},
                "filters": {"status": "draft", "query": "java", "tags": ["Java"]},
            }

            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", job_profiles_dir),
                patch(
                    "tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR",
                    matching_reports_dir,
                ),
            ):
                result = handle_jobs_list_profiles(params)

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["job_profile_id"], "jp-2026-002")
        self.assertEqual(result["items"][0]["status"], "draft")
        self.assertEqual(result["items"][0]["match_score"], 0)

    def test_paginates_with_cursor_offset(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            job_profiles_dir.mkdir()
            matching_reports_dir.mkdir()

            for index in range(3):
                profile_id = f"jp-2026-00{index + 1}"
                report_id = f"mr-2026-00{index + 1}"
                (job_profiles_dir / f"{profile_id}.yaml").write_text(
                    f'target_role: "Role {index + 1}"\n',
                    encoding="utf-8",
                )
                (matching_reports_dir / f"{report_id}.yaml").write_text(
                    "\n".join(
                        [
                            f'job_profile_id: "{profile_id}"',
                            f'score_total: "{90 - index}"',
                            f'generated_at: "2026-03-08T0{index}:00:00Z"',
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

            first_params = {
                "meta": {"correlation_id": "corr_jobs_cursor_1"},
                "cursor": None,
                "page_size": 1,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }
            second_params = {
                "meta": {"correlation_id": "corr_jobs_cursor_2"},
                "cursor": "1",
                "page_size": 1,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }

            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", job_profiles_dir),
                patch(
                    "tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR",
                    matching_reports_dir,
                ),
            ):
                first_result = handle_jobs_list_profiles(first_params)
                second_result = handle_jobs_list_profiles(second_params)

        self.assertEqual(
            [item["job_profile_id"] for item in first_result["items"]], ["jp-2026-003"]
        )
        self.assertEqual(first_result["next_cursor"], "1")
        self.assertEqual(
            [item["job_profile_id"] for item in second_result["items"]], ["jp-2026-002"]
        )
        self.assertEqual(second_result["next_cursor"], "2")

    def test_uses_utc_z_updated_at_when_matching_report_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            job_profiles_dir.mkdir()
            matching_reports_dir.mkdir()

            job_profile_path = job_profiles_dir / "jp-2026-001.yaml"
            job_profile_path.write_text(
                'target_role: "Senior Backend Engineer"\n',
                encoding="utf-8",
            )
            utime(job_profile_path, (0, 0))

            params = {
                "meta": {"correlation_id": "corr_jobs_utc"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }

            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", job_profiles_dir),
                patch(
                    "tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR",
                    matching_reports_dir,
                ),
            ):
                result = handle_jobs_list_profiles(params)

        self.assertEqual(result["items"][0]["updated_at"], "1970-01-01T00:00:00Z")

    def test_skips_invalid_utf8_files_and_keeps_valid_profiles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            job_profiles_dir.mkdir()
            matching_reports_dir.mkdir()

            (job_profiles_dir / "jp-2026-001.yaml").write_text(
                'target_role: "Senior Backend Engineer"\n',
                encoding="utf-8",
            )
            (job_profiles_dir / "jp-2026-bad.yaml").write_bytes(b"\xff\xfe\x00")
            (matching_reports_dir / "mr-2026-bad.yaml").write_bytes(b"\xff\xfe\x00")

            params = {
                "meta": {"correlation_id": "corr_jobs_resilient"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }

            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", job_profiles_dir),
                patch(
                    "tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR",
                    matching_reports_dir,
                ),
            ):
                result = handle_jobs_list_profiles(params)

        self.assertEqual(
            [item["job_profile_id"] for item in result["items"]], ["jp-2026-001"]
        )


if __name__ == "__main__":
    unittest.main()
