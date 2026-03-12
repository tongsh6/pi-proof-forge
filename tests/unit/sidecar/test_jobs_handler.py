import unittest
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

from tools.sidecar.handlers.jobs import (
    handle_jobs_convert_lead,
    handle_jobs_create_profile,
    handle_jobs_delete_profile,
    handle_jobs_list_leads,
    handle_jobs_list_profiles,
    handle_jobs_update_profile,
)


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

            params: dict[str, object] = {
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
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

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

            params: dict[str, object] = {
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
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

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

            first_params: dict[str, object] = {
                "meta": {"correlation_id": "corr_jobs_cursor_1"},
                "cursor": None,
                "page_size": 1,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }
            second_params: dict[str, object] = {
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
                first_result = cast(
                    dict[str, Any], handle_jobs_list_profiles(first_params)
                )
                second_result = cast(
                    dict[str, Any], handle_jobs_list_profiles(second_params)
                )

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

            params: dict[str, object] = {
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
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

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

            params: dict[str, object] = {
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
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

        self.assertEqual(
            [item["job_profile_id"] for item in result["items"]], ["jp-2026-001"]
        )


if __name__ == "__main__":
    unittest.main()


class JobsListLeadsTests(unittest.TestCase):
    def test_returns_leads_with_contract_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            leads_dir = root / "job_leads"
            leads_dir.mkdir()
            (leads_dir / "jl_001.yaml").write_text(
                "\n".join(
                    [
                        'id: "jl_001"',
                        'company: "Acme"',
                        'position: "Backend Engineer"',
                        'source: "liepin"',
                        'status: "new"',
                        'favorited: "true"',
                        'updated_at: "2026-03-07T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            params: dict[str, object] = {
                "meta": {"correlation_id": "corr_leads_1"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {
                    "source": None,
                    "status": None,
                    "favorited": None,
                    "query": "",
                },
            }

            with patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir):
                result = cast(dict[str, Any], handle_jobs_list_leads(params))

        self.assertEqual(result["meta"]["correlation_id"], "corr_leads_1")
        self.assertIsNone(result["next_cursor"])
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["job_lead_id"], "jl_001")
        self.assertEqual(item["company"], "Acme")
        self.assertEqual(item["position"], "Backend Engineer")
        self.assertEqual(item["source"], "liepin")
        self.assertEqual(item["status"], "new")
        self.assertTrue(item["favorited"])

    def test_sorts_by_created_at(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            leads_dir = root / "job_leads"
            leads_dir.mkdir()
            (leads_dir / "a.yaml").write_text(
                "\n".join(
                    [
                        'id: "jl_001"',
                        'company: "Acme"',
                        'position: "Backend Engineer"',
                        'source: "liepin"',
                        'created_at: "2026-03-07T09:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (leads_dir / "b.yaml").write_text(
                "\n".join(
                    [
                        'id: "jl_002"',
                        'company: "Beta"',
                        'position: "Java Engineer"',
                        'source: "boss"',
                        'created_at: "2026-03-08T09:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            params: dict[str, object] = {
                "meta": {"correlation_id": "corr_leads_sort"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "created_at", "order": "desc"},
                "filters": {
                    "source": None,
                    "status": None,
                    "favorited": None,
                    "query": "",
                },
            }

            with patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir):
                result = cast(dict[str, Any], handle_jobs_list_leads(params))

        self.assertEqual(
            [item["job_lead_id"] for item in result["items"]], ["jl_002", "jl_001"]
        )


class JobsProfileCrudTests(unittest.TestCase):
    def test_create_profile_persists_yaml(self) -> None:
        with TemporaryDirectory() as temp_dir:
            profiles_dir = Path(temp_dir) / "job_profiles"
            with patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir):
                result = cast(
                    dict[str, Any],
                    handle_jobs_create_profile(
                        {
                            "meta": {"correlation_id": "corr_jobs_create"},
                            "title": "Senior Backend Engineer",
                            "description": "Looking for distributed systems experience.",
                            "tags": ["Python", "Go"],
                            "status": "draft",
                        }
                    ),
                )
                created = profiles_dir / f"{result['job_profile_id']}.yaml"
                created_text = created.read_text(encoding="utf-8")

        self.assertEqual(result["meta"]["correlation_id"], "corr_jobs_create")
        self.assertEqual(result["status"], "draft")
        self.assertIn('target_role: "Senior Backend Engineer"', created_text)
        self.assertIn(
            'description: "Looking for distributed systems experience."', created_text
        )
        self.assertIn('  - "Python"', created_text)

    def test_update_profile_persists_partial_patch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            profiles_dir = Path(temp_dir) / "job_profiles"
            profiles_dir.mkdir()
            (profiles_dir / "jp-001.yaml").write_text(
                "\n".join(
                    [
                        'target_role: "Old Title"',
                        'company: "Acme"',
                        'status: "draft"',
                        'description: "old desc"',
                        "keywords:",
                        '  - "Python"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir):
                result = cast(
                    dict[str, Any],
                    handle_jobs_update_profile(
                        {
                            "meta": {"correlation_id": "corr_jobs_update"},
                            "job_profile_id": "jp-001",
                            "patch": {
                                "title": "New Title",
                                "status": "active",
                                "tags": ["Go"],
                            },
                        }
                    ),
                )
                updated = (profiles_dir / "jp-001.yaml").read_text(encoding="utf-8")

        self.assertEqual(result["job_profile_id"], "jp-001")
        self.assertIn('target_role: "New Title"', updated)
        self.assertIn('status: "active"', updated)
        self.assertIn('  - "Go"', updated)
        self.assertIn('company: "Acme"', updated)

    def test_delete_profile_soft_deletes_and_conflict_when_running(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profiles_dir = root / "job_profiles"
            submissions_dir = root / "outputs" / "submissions"
            profiles_dir.mkdir(parents=True)
            run_dir = submissions_dir / "liepin" / "run-001"
            run_dir.mkdir(parents=True)
            (profiles_dir / "jp-001.yaml").write_text(
                'target_role: "Old Title"\n', encoding="utf-8"
            )
            (run_dir / "submission_log.json").write_text(
                '{"run_id":"run-001","status":"running","profile_path":"job_profiles/jp-001.yaml"}',
                encoding="utf-8",
            )
            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._SUBMISSIONS_DIR", submissions_dir),
            ):
                with self.assertRaises(RuntimeError):
                    handle_jobs_delete_profile(
                        {
                            "meta": {"correlation_id": "corr_jobs_delete_conflict"},
                            "job_profile_id": "jp-001",
                        }
                    )

            (run_dir / "submission_log.json").write_text(
                '{"run_id":"run-001","status":"failed","profile_path":"job_profiles/jp-001.yaml"}',
                encoding="utf-8",
            )
            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._SUBMISSIONS_DIR", submissions_dir),
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_delete_profile(
                        {
                            "meta": {"correlation_id": "corr_jobs_delete"},
                            "job_profile_id": "jp-001",
                        }
                    ),
                )
                self.assertTrue(result["deleted"])
                self.assertTrue((profiles_dir / "jp-001.yaml.deleted").exists())

    def test_delete_profile_clears_exact_matching_lead_reference_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profiles_dir = root / "job_profiles"
            leads_dir = root / "job_leads"
            submissions_dir = root / "outputs" / "submissions"
            profiles_dir.mkdir(parents=True)
            leads_dir.mkdir(parents=True)
            submissions_dir.mkdir(parents=True)
            (profiles_dir / "jp-01.yaml").write_text(
                'target_role: "Old Title"\n', encoding="utf-8"
            )
            (leads_dir / "lead-a.yaml").write_text(
                'id: "jl_a"\njob_profile_id: "jp-01"\n', encoding="utf-8"
            )
            (leads_dir / "lead-b.yaml").write_text(
                'id: "jl_b"\njob_profile_id: "jp-010"\n', encoding="utf-8"
            )
            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.jobs._SUBMISSIONS_DIR", submissions_dir),
            ):
                _ = handle_jobs_delete_profile(
                    {
                        "meta": {"correlation_id": "corr_jobs_delete_exact"},
                        "job_profile_id": "jp-01",
                    }
                )
                lead_a = (leads_dir / "lead-a.yaml").read_text(encoding="utf-8")
                lead_b = (leads_dir / "lead-b.yaml").read_text(encoding="utf-8")

        self.assertIn('job_profile_id: ""', lead_a)
        self.assertIn('job_profile_id: "jp-010"', lead_b)


class JobsConvertLeadTests(unittest.TestCase):
    def test_convert_lead_creates_profile(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            leads_dir = root / "job_leads"
            profiles_dir = root / "job_profiles"
            leads_dir.mkdir()
            profiles_dir.mkdir()
            (leads_dir / "jl_001.yaml").write_text(
                "\n".join(
                    [
                        'id: "jl_001"',
                        'company: "Acme"',
                        'position: "Backend Engineer"',
                        'url: "https://example.com/jd/1"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_convert_lead(
                        {
                            "meta": {"correlation_id": "corr_jobs_convert"},
                            "job_lead_id": "jl_001",
                        }
                    ),
                )
                created = (profiles_dir / f"{result['job_profile_id']}.yaml").read_text(
                    encoding="utf-8"
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_jobs_convert")
        self.assertIn('target_role: "Backend Engineer"', created)
        self.assertIn('company: "Acme"', created)

    def test_convert_lead_uses_yaml_id_not_filename(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            leads_dir = root / "job_leads"
            profiles_dir = root / "job_profiles"
            leads_dir.mkdir()
            profiles_dir.mkdir()
            (leads_dir / "mismatched-file.yaml").write_text(
                "\n".join(
                    [
                        'id: "jl_001"',
                        'company: "Acme"',
                        'position: "Backend Engineer"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_convert_lead(
                        {
                            "meta": {"correlation_id": "corr_jobs_convert_id"},
                            "job_lead_id": "jl_001",
                        }
                    ),
                )
                self.assertTrue(
                    (profiles_dir / f"{result['job_profile_id']}.yaml").exists()
                )
