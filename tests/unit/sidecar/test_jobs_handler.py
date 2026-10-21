import unittest
import json
from io import BytesIO
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

from tools.sidecar.handlers.jobs import (
    handle_jobs_convert_lead,
    handle_jobs_create_profile,
    handle_jobs_delete_profile,
    handle_jobs_generate_profile_draft,
    handle_jobs_list_leads,
    handle_jobs_list_profiles,
    handle_jobs_save_profile_draft,
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
            scorecards_dir = root / "outputs" / "scorecards"
            scorecards_dir.mkdir(parents=True)
            (scorecards_dir / "scorecard_mr-2026-001_A.json").write_text(
                json.dumps(
                    {"quality_report": {"tiers": {"fit": {"passed": False, "failures": [{"rule": "R2.2"}, {"rule": "R2.4"}]}}}},
                    ensure_ascii=False,
                ),
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
                patch(
                    "tools.sidecar.handlers.jobs._SCORECARD_DIR",
                    scorecards_dir,
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
        self.assertEqual(item["fit_state"], "failed")
        self.assertEqual(item["fit_failures"], 2)

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


class JobsProfileDraftReviewTests(unittest.TestCase):
    def _write_policy(self, path: Path) -> None:
        path.write_text(
            "\n".join(
                [
                    'llm_provider: "lm_studio"',
                    'llm_model: "local-model"',
                    'llm_base_url: "http://127.0.0.1:1234/v1"',
                    'llm_timeout: "60"',
                    'llm_temperature: "0.2"',
                    'llm_api_key_configured: "true"',
                    'llm_api_key_placeholder: "lm-studio"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_generate_profile_draft_calls_llm_and_does_not_save(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policy_path = root / "policy.yaml"
            profiles_dir = root / "job_profiles"
            self._write_policy(policy_path)
            llm_response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "target_role": "Senior Backend Engineer",
                                    "company": "Acme",
                                    "source_url": "https://jobs.example.com/1",
                                    "jd_summary": "Own checkout reliability.",
                                    "must_have": ["Python", "Distributed systems"],
                                    "keywords": ["Python", "Reliability"],
                                    "nice_to_have": ["Kafka"],
                                    "business_domain": "E-commerce",
                                    "seniority_signal": ["Owner"],
                                    "tone": "technical",
                                }
                            )
                        }
                    }
                ]
            }

            with (
                patch(
                    "tools.sidecar.handlers.settings._resolve_policy_path",
                    return_value=policy_path,
                ),
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch(
                    "tools.infra.llm.client.request.urlopen",
                    return_value=BytesIO(json.dumps(llm_response).encode()),
                ) as urlopen,
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_generate_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_job_draft"},
                            "jd_text": "Acme needs Python reliability owner.",
                            "source_url": "https://jobs.example.com/1",
                        }
                    ),
                )

        self.assertEqual(result["status"], "draft_ready_for_review")
        self.assertFalse(result["active_target_eligible"])
        self.assertEqual(result["draft"]["target_role"], "Senior Backend Engineer")
        self.assertEqual(result["draft"]["source_url"], "https://jobs.example.com/1")
        self.assertEqual(urlopen.call_count, 1)
        request_payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(request_payload["response_format"]["type"], "json_schema")
        schema = request_payload["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["required"]), {"target_role", "must_have", "keywords", "jd_summary"})
        for field in ("must_have", "nice_to_have", "keywords", "seniority_signal"):
            self.assertEqual(schema["properties"][field]["type"], "array")
            self.assertGreater(schema["properties"][field]["maxItems"], 0)
            self.assertGreater(schema["properties"][field]["items"]["maxLength"], 0)
        for field in ("target_role", "company", "city", "jd_summary", "business_domain", "tone"):
            self.assertEqual(schema["properties"][field]["type"], "string")
            self.assertGreater(schema["properties"][field]["maxLength"], 0)
        self.assertNotIn("source_url", schema["properties"])
        self.assertFalse(schema["additionalProperties"])
        self.assertLessEqual(request_payload["max_tokens"], 2048)
        self.assertFalse(profiles_dir.exists())

    def test_generate_profile_draft_rejects_invalid_json_without_repair(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policy_path = root / "policy.yaml"
            self._write_policy(policy_path)

            with (
                patch(
                    "tools.sidecar.handlers.settings._resolve_policy_path",
                    return_value=policy_path,
                ),
                patch(
                    "tools.sidecar.handlers.jobs.LLMClient.post_json",
                    return_value={"choices": [{"message": {"content": "not-json"}}]},
                ),
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_generate_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_job_bad_json"},
                            "jd_text": "Acme needs Python reliability owner.",
                        }
                    ),
                )

        self.assertEqual(result["status"], "parse_invalid_json")
        self.assertEqual(result["code"], "parse_invalid_json")
        self.assertIsNone(result["draft"])

    def test_generate_profile_draft_blocks_when_llm_base_url_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "policy.yaml"
            policy_path.write_text('llm_model: "local-model"\n', encoding="utf-8")

            with patch(
                "tools.sidecar.handlers.settings._resolve_policy_path",
                return_value=policy_path,
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_generate_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_job_blocked"},
                            "jd_text": "Acme needs Python reliability owner.",
                        }
                    ),
                )

        self.assertEqual(result["status"], "parse_blocked_local_provider")
        self.assertEqual(result["code"], "BLOCKED_LOCAL_PROVIDER")

    def test_save_profile_draft_requires_review_and_keeps_incomplete_inactive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            profiles_dir = Path(temp_dir) / "job_profiles"
            draft = {
                "target_role": "Senior Backend Engineer",
                "company": "Acme",
                "source_jd": "Acme needs Python reliability owner.",
                "jd_summary": "",
                "source_url": "",
                "must_have": ["Python"],
                "keywords": [],
                "nice_to_have": [],
                "business_domain": "E-commerce",
                "seniority_signal": [],
                "tone": "technical",
            }

            with patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir):
                with self.assertRaises(ValueError):
                    handle_jobs_save_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_job_no_review"},
                            "draft": draft,
                            "save_mode": "incomplete",
                        }
                    )
                result = cast(
                    dict[str, Any],
                    handle_jobs_save_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_job_incomplete"},
                            "draft": draft,
                            "review": {"decision": "approved"},
                            "save_mode": "incomplete",
                        }
                    ),
                )
                saved_text = (
                    profiles_dir / f"{result['job_profile_id']}.yaml"
                ).read_text(encoding="utf-8")

        self.assertEqual(result["status"], "saved_incomplete")
        self.assertFalse(result["active_target_eligible"])
        self.assertIn("missing_keywords", result["missing_items"])
        self.assertIn('status: "saved_incomplete"', saved_text)

    def test_save_complete_profile_creates_bidirectional_job_lead_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profiles_dir = root / "job_profiles"
            leads_dir = root / "job_leads"
            draft = {
                "target_role": "Senior Backend Engineer",
                "company": "Acme",
                "source_jd": "Acme needs Python reliability owner.",
                "jd_summary": "Own checkout reliability.",
                "source_url": "https://jobs.example.com/1",
                "must_have": ["Python"],
                "keywords": ["Reliability"],
                "nice_to_have": [],
                "business_domain": "E-commerce",
                "seniority_signal": ["Owner"],
                "tone": "technical",
            }

            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
                patch(
                    "tools.sidecar.handlers.jobs._check_source_url_accessible",
                    return_value={
                        "checked": True,
                        "accessible": True,
                        "status": "accessible",
                        "status_code": 200,
                    },
                ),
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_save_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_job_complete"},
                            "draft": draft,
                            "review": {
                                "decision": "approved",
                                "reviewed_at": "2026-05-21T00:00:00Z",
                            },
                            "save_mode": "complete",
                        }
                    ),
                )
                profile_text = (
                    profiles_dir / f"{result['job_profile_id']}.yaml"
                ).read_text(encoding="utf-8")
                lead_text = (leads_dir / f"{result['job_lead_id']}.yaml").read_text(
                    encoding="utf-8"
                )
                active_profiles = cast(
                    dict[str, Any],
                    handle_jobs_list_profiles(
                        {
                            "meta": {"correlation_id": "corr_job_active_list"},
                            "cursor": None,
                            "page_size": 20,
                            "sort": {"field": "updated_at", "order": "desc"},
                            "filters": {"status": "active", "query": "", "tags": []},
                        }
                    ),
                )

        self.assertEqual(result["status"], "saved_complete")
        self.assertTrue(result["active_target_eligible"])
        self.assertEqual(result["missing_items"], [])
        self.assertTrue(result["job_lead_id"].startswith("jl_"))
        self.assertIn(f'job_lead_id: "{result["job_lead_id"]}"', profile_text)
        self.assertIn(f'job_profile_id: "{result["job_profile_id"]}"', lead_text)
        self.assertEqual(active_profiles["items"][0]["job_profile_id"], result["job_profile_id"])


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


class ManualImportSourceContractTests(unittest.TestCase):
    """人工导入来源契约：按域名识别平台；人工平台不做可达性 GET；记录平台、人工导入与来源时间；仅链接不算完整 JD。"""

    def _draft(self, source_url: str, source_jd: str = "脉脉招聘高级后端工程师，负责交易链路稳定性，要求 Python 与分布式系统经验。") -> dict[str, Any]:
        return {
            "target_role": "高级后端工程师",
            "company": "示例科技",
            "source_jd": source_jd,
            "jd_summary": "负责交易链路稳定性。",
            "source_url": source_url,
            "must_have": ["Python"],
            "keywords": ["分布式"],
            "nice_to_have": [],
            "business_domain": "互联网",
            "seniority_signal": ["高级"],
            "tone": "technical",
        }

    def test_platform_from_url_recognizes_known_domains(self) -> None:
        from tools.sidecar.handlers.jobs import platform_from_url

        self.assertEqual(platform_from_url("https://maimai.cn/job_detail?jid=1"), "maimai")
        self.assertEqual(platform_from_url("https://m.maimai.cn/job/1"), "maimai")
        self.assertEqual(platform_from_url("https://www.lagou.com/wn/jobs/1.html"), "lagou")
        self.assertEqual(platform_from_url("https://www.zhipin.com/job_detail/1.html"), "boss")
        self.assertEqual(platform_from_url("https://jobs.zhaopin.com/1.htm"), "zhilian")
        self.assertEqual(platform_from_url("https://jobs.51job.com/shanghai/1.html"), "qiancheng")
        self.assertEqual(platform_from_url("https://www.liepin.com/job/1.shtml"), "liepin")
        self.assertEqual(platform_from_url("https://jobs.example.com/1"), "other")
        self.assertEqual(platform_from_url(""), "")
        self.assertEqual(platform_from_url("https://notmaimai.cn/x"), "other")

    def test_complete_save_with_maimai_link_skips_fetch_and_labels_manual_import(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profiles_dir = root / "job_profiles"
            leads_dir = root / "job_leads"
            profiles_dir.mkdir()
            leads_dir.mkdir()
            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
                patch(
                    "tools.sidecar.handlers.jobs._check_source_url_accessible",
                    side_effect=AssertionError("人工导入平台不得向平台发请求"),
                ),
            ):
                result = cast(
                    dict[str, Any],
                    handle_jobs_save_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_manual_maimai"},
                            "draft": self._draft("https://maimai.cn/job_detail?jid=123456"),
                            "review": {"decision": "approved", "reviewed_at": "2026-10-11T00:00:00Z"},
                            "save_mode": "complete",
                        }
                    ),
                )
                profile_text = (profiles_dir / f"{result['job_profile_id']}.yaml").read_text(encoding="utf-8")
                lead_text = (leads_dir / f"{result['job_lead_id']}.yaml").read_text(encoding="utf-8")
                profiles = cast(
                    dict[str, Any],
                    handle_jobs_list_profiles(
                        {
                            "meta": {"correlation_id": "corr_manual_list"},
                            "cursor": None,
                            "page_size": 20,
                            "sort": {"field": "updated_at", "order": "desc"},
                            "filters": {"status": "active", "query": "", "tags": []},
                        }
                    ),
                )
                leads = cast(
                    dict[str, Any],
                    handle_jobs_list_leads(
                        {
                            "meta": {"correlation_id": "corr_manual_leads"},
                            "cursor": None,
                            "page_size": 20,
                            "sort": {"field": "updated_at", "order": "desc"},
                            "filters": {"source": None, "status": None, "favorited": None, "query": ""},
                        }
                    ),
                )

        self.assertEqual(result["status"], "saved_complete")
        self.assertEqual(result["source_url_check"]["status"], "manual_platform_not_checked")
        self.assertEqual(result["source_url_check"]["platform"], "maimai")
        self.assertIn('platform: "maimai"', profile_text)
        self.assertIn('import_mode: "manual"', profile_text)
        self.assertIn("source_recorded_at: ", profile_text)
        self.assertIn('platform: "maimai"', lead_text)
        self.assertIn('source: "manual_jd"', lead_text)
        self.assertIn('import_mode: "manual"', lead_text)
        item = profiles["items"][0]
        self.assertEqual(item["platform"], "maimai")
        self.assertEqual(item["import_mode"], "manual")
        self.assertTrue(item["source_recorded_at"])
        lead_item = leads["items"][0]
        self.assertEqual(lead_item["platform"], "maimai")
        self.assertEqual(lead_item["import_mode"], "manual")

    def test_other_domain_still_requires_accessibility_check(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profiles_dir = root / "job_profiles"
            leads_dir = root / "job_leads"
            profiles_dir.mkdir()
            leads_dir.mkdir()
            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
                patch(
                    "tools.sidecar.handlers.jobs._check_source_url_accessible",
                    return_value={"checked": True, "accessible": False, "status": "job_source_unavailable"},
                ),
            ):
                with self.assertRaises(ValueError) as raised:
                    handle_jobs_save_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_other_domain"},
                            "draft": self._draft("https://jobs.example.com/1"),
                            "review": {"decision": "approved", "reviewed_at": "2026-10-11T00:00:00Z"},
                            "save_mode": "complete",
                        }
                    )
        self.assertEqual(str(raised.exception), "job_source_unavailable")

    def test_link_only_jd_cannot_be_saved_complete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profiles_dir = root / "job_profiles"
            leads_dir = root / "job_leads"
            profiles_dir.mkdir()
            leads_dir.mkdir()
            with (
                patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
                patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
            ):
                with self.assertRaises(ValueError):
                    handle_jobs_save_profile_draft(
                        {
                            "meta": {"correlation_id": "corr_link_only"},
                            "draft": self._draft(
                                "https://maimai.cn/job_detail?jid=123456",
                                source_jd="https://maimai.cn/job_detail?jid=123456",
                            ),
                            "review": {"decision": "approved", "reviewed_at": "2026-10-11T00:00:00Z"},
                            "save_mode": "complete",
                        }
                    )


class LeadCompanySizeFilterTests(unittest.TestCase):
    """公司规模按平台文案解析上界；筛选只保留有明确上界且不超过阈值的线索。"""

    def _lead(self, size: str, location: str = "上海") -> dict[str, Any]:
        return {"job_lead_id": f"jl_{size}", "company": "C", "position": "P", "salary": "", "location": location,
                "source": "liepin_official", "status": "new", "favorited": False, "created_at": "", "updated_at": "",
                "url": "", "platform": "liepin", "platform_job_id": "1", "platform_job_type": "2", "jd_status": "",
                "fetched_at": "", "company_size": size}

    def test_upper_bound_parsing(self) -> None:
        from tools.sidecar.handlers.jobs import _company_size_upper_bound

        self.assertEqual(_company_size_upper_bound("1-49人"), 49)
        self.assertEqual(_company_size_upper_bound("50-99人"), 99)
        self.assertEqual(_company_size_upper_bound("100-499人"), 499)
        self.assertEqual(_company_size_upper_bound("少于50人"), 49)
        self.assertEqual(_company_size_upper_bound("50人以下"), 50)
        self.assertIsNone(_company_size_upper_bound("10000人以上"))
        self.assertIsNone(_company_size_upper_bound(""))
        self.assertIsNone(_company_size_upper_bound("保密"))

    def test_filter_by_company_size_max_and_location_query(self) -> None:
        from tools.sidecar.handlers.jobs import _apply_lead_filters

        items = cast(list[Any], [self._lead("1-49人"), self._lead("50-99人", "北京"), self._lead("100-499人"),
                                 self._lead("10000人以上"), self._lead("")])
        kept = _apply_lead_filters(items, {"company_size_max": 99})
        self.assertEqual([item["company_size"] for item in kept], ["1-49人", "50-99人"])
        self.assertEqual([item["company_size"] for item in _apply_lead_filters(items, {"company_size_max": 499})],
                         ["1-49人", "50-99人", "100-499人"])
        self.assertEqual(len(_apply_lead_filters(items, {"company_size_max": "bad"})), 5)
        self.assertEqual(len(_apply_lead_filters(items, {"company_size_max": None})), 5)
        self.assertEqual([item["location"] for item in _apply_lead_filters(items, {"company_size_max": 99, "query": "上海"})],
                         ["上海"])


class JobFitPrecheckTests(unittest.TestCase):
    """岗位批量适配预检：assessed（最近 Quick Run）优先，未预检用证据库规则预检。"""

    def _profile_lines(self, *, role: str, company: str, keywords: list[str], must_have: list[str] | None = None) -> str:
        lines = [f'target_role: "{role}"', f'company: "{company}"', "keywords:"]
        lines.extend(f'  - "{item}"' for item in keywords)
        if must_have:
            lines.append("must_have:")
            lines.extend(f'  - "{item}"' for item in must_have)
        return "\n".join(lines) + "\n"

    def _card_lines(self, card_id: str, *, title: str, status: str = "saved_eligible", stack: list[str] | None = None,
                    context: str = "", eligible: str = "true") -> str:
        lines = [
            f'id: "{card_id}"',
            f'title: "{title}"',
            f'status: "{status}"',
            f'candidate_pool_eligible: "{eligible}"',
            f'context: "{context}"',
            "stack:",
        ]
        lines.extend(f'  - "{item}"' for item in (stack or []))
        return "\n".join(lines) + "\n"

    def _workspace(self, root: Path) -> tuple[Path, Path, Path, Path]:
        job_profiles_dir = root / "job_profiles"
        matching_reports_dir = root / "matching_reports"
        scorecards_dir = root / "outputs" / "scorecards"
        evidence_cards_dir = root / "evidence_cards"
        for path in (job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir):
            path.mkdir(parents=True, exist_ok=True)
        return job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir

    def _call(self, root: Path, dirs: tuple[Path, Path, Path, Path], *, sort: dict[str, str] | None = None) -> dict[str, Any]:
        job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir = dirs
        params: dict[str, object] = {
            "meta": {"correlation_id": "corr_precheck"},
            "cursor": None,
            "page_size": 20,
            "sort": sort or {"field": "updated_at", "order": "desc"},
            "filters": {"status": None, "query": "", "tags": []},
        }
        import tools.sidecar.handlers.jobs as jobs_module

        with (
            patch.object(jobs_module, "_JOB_PROFILE_DIR", job_profiles_dir),
            patch.object(jobs_module, "_MATCHING_REPORT_DIR", matching_reports_dir),
            patch.object(jobs_module, "_SCORECARD_DIR", scorecards_dir),
            patch.object(jobs_module, "_EVIDENCE_CARD_DIR", evidence_cards_dir),
        ):
            return cast(dict[str, Any], handle_jobs_list_profiles(params))

    def test_assessed_profile_precheck_uses_quick_run_advice_and_fit_result(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dirs = self._workspace(root)
            job_profiles_dir, matching_reports_dir, scorecards_dir, _ = dirs
            (job_profiles_dir / "jp_assessed.yaml").write_text(
                self._profile_lines(role="Java Tech Lead", company="Dewu", keywords=["Java", "Redis"]),
                encoding="utf-8",
            )
            (matching_reports_dir / "mr-2026-010.yaml").write_text(
                'job_profile_id: "jp_assessed"\nscore_total: "85"\ngenerated_at: "2026-10-21T09:00:00Z"\n',
                encoding="utf-8",
            )
            (scorecards_dir / "scorecard_mr-2026-010_A.json").write_text(
                json.dumps(
                    {
                        "semantic_review": {"fit_score": 85, "resume_score": 35},
                        "quality_report": {
                            "tiers": {"fit": {"passed": False, "failures": [{"rule": "R2.2"}, {"rule": "R2.4"}]}},
                            "delivery_advice": {"recommendation": "strengthen"},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = self._call(root, dirs)

        item = result["items"][0]
        self.assertEqual(item["fit_state"], "failed")
        self.assertEqual(item["fit_failures"], 2)
        precheck = item["fit_precheck"]
        self.assertEqual(precheck["source"], "assessed")
        self.assertEqual(precheck["state"], "consider")
        self.assertEqual(precheck["rank"], 1)
        self.assertEqual(precheck["basis"], "assessed_quick_run")
        self.assertEqual(precheck["match_score"], 85)
        self.assertEqual(precheck["fit_failures"], 2)

    def test_unassessed_profiles_get_rule_precheck_from_eligible_evidence_cards(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dirs = self._workspace(root)
            job_profiles_dir, _, _, evidence_cards_dir = dirs
            (job_profiles_dir / "jp_backend.yaml").write_text(
                self._profile_lines(
                    role="Java 后端工程师",
                    company="Backend Co",
                    keywords=["Java", "Redis", "MySQL", "微服务"],
                    must_have=["熟悉 Java 微服务开发"],
                ),
                encoding="utf-8",
            )
            (job_profiles_dir / "jp_ic.yaml").write_text(
                self._profile_lines(
                    role="模拟芯片设计工程师",
                    company="Chip Co",
                    keywords=["LDO", "Bandgap", "CMOS", "模拟IC"],
                ),
                encoding="utf-8",
            )
            (evidence_cards_dir / "custom_java_import.yaml").write_text(
                self._card_lines(
                    "ec_java",
                    title="电商交易平台核心开发",
                    context="Java 微服务与 Redis 缓存",
                    stack=["Java", "Redis", "MySQL"],
                ),
                encoding="utf-8",
            )
            (evidence_cards_dir / "ec_incomplete.yaml").write_text(
                self._card_lines("ec_incomplete", title="未完成卡", status="saved_incomplete", stack=["Java"]),
                encoding="utf-8",
            )
            (evidence_cards_dir / "ec_ineligible.yaml").write_text(
                self._card_lines("ec_ineligible", title="不可入池卡", stack=["Java"], eligible="false"),
                encoding="utf-8",
            )

            result = self._call(root, dirs)

        by_id = {item["job_profile_id"]: item for item in result["items"]}
        backend = by_id["jp_backend"]["fit_precheck"]
        self.assertEqual(backend["source"], "rule")
        self.assertIn(backend["state"], {"promising", "caution"})
        self.assertGreater(backend["coverage"], 0)
        self.assertGreaterEqual(backend["matched_requirements"], 2)
        self.assertGreaterEqual(backend["evidence_hits"], 1)
        self.assertIn("Java", backend["matched_terms"])
        self.assertTrue(backend["matched_terms"] and backend["total_requirements"] >= backend["matched_requirements"])
        self.assertEqual(backend["basis"], "rule_evidence_overlap")

        ic = by_id["jp_ic"]["fit_precheck"]
        self.assertEqual(ic["state"], "low")
        self.assertLess(ic["coverage"], 0.35)
        self.assertTrue(ic["missing_terms"])

    def test_fit_precheck_sort_puts_recommended_first(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dirs = self._workspace(root)
            job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir = dirs
            (job_profiles_dir / "jp_pass.yaml").write_text(
                self._profile_lines(role="Pass", company="A", keywords=["Java"]), encoding="utf-8"
            )
            (job_profiles_dir / "jp_caution.yaml").write_text(
                self._profile_lines(role="Caution", company="B", keywords=["Java"]), encoding="utf-8"
            )
            (job_profiles_dir / "jp_low.yaml").write_text(
                self._profile_lines(role="Low", company="C", keywords=["LDO"]), encoding="utf-8"
            )
            (evidence_cards_dir / "ec_java.yaml").write_text(
                self._card_lines("ec_java", title="Java 服务", stack=["Java"]), encoding="utf-8"
            )
            (matching_reports_dir / "mr-pass.yaml").write_text(
                'job_profile_id: "jp_pass"\nscore_total: "90"\ngenerated_at: "2026-10-21T09:00:00Z"\n', encoding="utf-8"
            )
            (matching_reports_dir / "mr-caution.yaml").write_text(
                'job_profile_id: "jp_caution"\nscore_total: "50"\ngenerated_at: "2026-10-21T09:00:00Z"\n', encoding="utf-8"
            )
            (scorecards_dir / "scorecard_mr-pass_A.json").write_text(
                json.dumps({"quality_report": {"tiers": {"fit": {"passed": True, "failures": []}}}}),
                encoding="utf-8",
            )
            (scorecards_dir / "scorecard_mr-caution_A.json").write_text(
                json.dumps({
                    "semantic_review": {"fit_score": 50},
                    "quality_report": {"tiers": {"fit": {"passed": False, "failures": [{"rule": "R2.2"}] * 5}}},
                }),
                encoding="utf-8",
            )

            result = self._call(root, dirs, sort={"field": "fit_precheck", "order": "asc"})
            default_order = self._call(root, dirs, sort={"field": "fit_precheck"})

        ids = [item["job_profile_id"] for item in result["items"]]
        self.assertEqual(ids, ["jp_pass", "jp_caution", "jp_low"])
        ranks = [item["fit_precheck"]["rank"] for item in result["items"]]
        self.assertEqual(ranks, sorted(ranks))
        default_ids = [item["job_profile_id"] for item in default_order["items"]]
        self.assertEqual(default_ids, ids, "未显式 order 时 fit_precheck 默认应按 rank 升序")


class JobFitPrecheckLegacyScorecardTests(unittest.TestCase):
    """旧评分卡没有四层报告时不得冒充“已预检失败”，退回证据库规则预检。"""

    def test_legacy_scorecard_falls_back_to_rule_precheck(self) -> None:
        from tools.sidecar.handlers import jobs as jobs_module

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            scorecards_dir = root / "outputs" / "scorecards"
            evidence_cards_dir = root / "evidence_cards"
            for path in (job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir):
                path.mkdir(parents=True, exist_ok=True)
            (job_profiles_dir / "jp_legacy.yaml").write_text(
                'target_role: "Java Tech Lead"\n'
                'company: "Legacy Co"\n'
                "keywords:\n"
                '  - "Java"\n'
                '  - "Redis"\n',
                encoding="utf-8",
            )
            (matching_reports_dir / "mr-legacy.yaml").write_text(
                'job_profile_id: "jp_legacy"\nscore_total: "50"\ngenerated_at: "2026-05-20T09:00:00Z"\n',
                encoding="utf-8",
            )
            # 旧版 scorecard：只有 legacy 字段，没有 quality_report.tiers。
            (scorecards_dir / "scorecard_mr-legacy_A.json").write_text(
                json.dumps({"total_score": 50, "semantic_review": {"fit_score": 50}}),
                encoding="utf-8",
            )
            (evidence_cards_dir / "ec_java.yaml").write_text(
                'id: "ec_java"\ntitle: "Java 微服务与 Redis"\nstatus: "saved_eligible"\n'
                'candidate_pool_eligible: "true"\nstack:\n  - "Java"\n  - "Redis"\n',
                encoding="utf-8",
            )
            params: dict[str, object] = {
                "meta": {"correlation_id": "corr_legacy"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }
            with (
                patch.object(jobs_module, "_JOB_PROFILE_DIR", job_profiles_dir),
                patch.object(jobs_module, "_MATCHING_REPORT_DIR", matching_reports_dir),
                patch.object(jobs_module, "_SCORECARD_DIR", scorecards_dir),
                patch.object(jobs_module, "_EVIDENCE_CARD_DIR", evidence_cards_dir),
            ):
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

        item = result["items"][0]
        self.assertEqual(item["fit_state"], "unassessed")
        self.assertEqual(item["fit_precheck"]["source"], "rule")
        self.assertIn(item["fit_precheck"]["state"], {"promising", "caution"})


class JobFitPrecheckUntrustedAssessmentTests(unittest.TestCase):
    """四层报告缺语义评审分与投递建议时，不能把 assessed 当作可信推荐依据。"""

    def test_four_tier_report_without_semantic_score_falls_back_to_rule(self) -> None:
        from tools.sidecar.handlers import jobs as jobs_module

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            scorecards_dir = root / "outputs" / "scorecards"
            evidence_cards_dir = root / "evidence_cards"
            for path in (job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir):
                path.mkdir(parents=True, exist_ok=True)
            (job_profiles_dir / "jp_untrusted.yaml").write_text(
                'target_role: "Java Tech Lead"\n'
                'company: "Untrusted Co"\n'
                "keywords:\n"
                '  - "Java"\n'
                '  - "Redis"\n',
                encoding="utf-8",
            )
            (matching_reports_dir / "mr-untrusted.yaml").write_text(
                'job_profile_id: "jp_untrusted"\nscore_total: "80"\ngenerated_at: "2026-10-21T09:00:00Z"\n',
                encoding="utf-8",
            )
            (scorecards_dir / "scorecard_mr-untrusted_A.json").write_text(
                json.dumps({"quality_report": {"tiers": {"fit": {"passed": False, "failures": [{"rule": "R2.1"}]}}}}),
                encoding="utf-8",
            )
            (evidence_cards_dir / "ec_java.yaml").write_text(
                'id: "ec_java"\ntitle: "Java 服务"\nstatus: "saved_eligible"\n'
                'candidate_pool_eligible: "true"\nstack:\n  - "Java"\n  - "Redis"\n',
                encoding="utf-8",
            )
            params: dict[str, object] = {
                "meta": {"correlation_id": "corr_untrusted"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": None, "query": "", "tags": []},
            }
            with (
                patch.object(jobs_module, "_JOB_PROFILE_DIR", job_profiles_dir),
                patch.object(jobs_module, "_MATCHING_REPORT_DIR", matching_reports_dir),
                patch.object(jobs_module, "_SCORECARD_DIR", scorecards_dir),
                patch.object(jobs_module, "_EVIDENCE_CARD_DIR", evidence_cards_dir),
            ):
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

        precheck = result["items"][0]["fit_precheck"]
        self.assertEqual(result["items"][0]["fit_state"], "failed")
        self.assertEqual(precheck["source"], "rule")
        self.assertNotEqual(precheck["state"], "consider")
        self.assertEqual(precheck["fit_score"], None)


class JobFitPrecheckZeroScoreTests(unittest.TestCase):
    """语义 fit_score=0 是显式评估结果，不得被当成缺失后退回规则预检并重回推荐位。"""

    def test_zero_semantic_score_keeps_assessed_low(self) -> None:
        from tools.sidecar.handlers import jobs as jobs_module

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_profiles_dir = root / "job_profiles"
            matching_reports_dir = root / "matching_reports"
            scorecards_dir = root / "outputs" / "scorecards"
            evidence_cards_dir = root / "evidence_cards"
            for path in (job_profiles_dir, matching_reports_dir, scorecards_dir, evidence_cards_dir):
                path.mkdir(parents=True, exist_ok=True)
            (job_profiles_dir / "jp_zero.yaml").write_text(
                'target_role: "Java Tech Lead"\n'
                'company: "Zero Co"\n'
                "keywords:\n"
                '  - "Java"\n'
                '  - "Redis"\n',
                encoding="utf-8",
            )
            (matching_reports_dir / "mr-zero.yaml").write_text(
                'job_profile_id: "jp_zero"\nscore_total: "90"\ngenerated_at: "2026-10-21T09:00:00Z"\n',
                encoding="utf-8",
            )
            (scorecards_dir / "scorecard_mr-zero_A.json").write_text(
                json.dumps({
                    "semantic_review": {"fit_score": 0, "resume_score": 0},
                    "quality_report": {
                        "tiers": {"fit": {"passed": False, "failures": [{"rule": "R2.2"}] * 3}}
                    },
                }),
                encoding="utf-8",
            )
            (evidence_cards_dir / "ec_java.yaml").write_text(
                'id: "ec_java"\ntitle: "Java 服务"\nstatus: "saved_eligible"\n'
                'candidate_pool_eligible: "true"\nstack:\n  - "Java"\n  - "Redis"\n',
                encoding="utf-8",
            )
            params: dict[str, object] = {
                "meta": {"correlation_id": "corr_zero"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "fit_precheck", "order": "asc"},
                "filters": {"status": None, "query": "", "tags": []},
            }
            with (
                patch.object(jobs_module, "_JOB_PROFILE_DIR", job_profiles_dir),
                patch.object(jobs_module, "_MATCHING_REPORT_DIR", matching_reports_dir),
                patch.object(jobs_module, "_SCORECARD_DIR", scorecards_dir),
                patch.object(jobs_module, "_EVIDENCE_CARD_DIR", evidence_cards_dir),
            ):
                result = cast(dict[str, Any], handle_jobs_list_profiles(params))

        precheck = result["items"][0]["fit_precheck"]
        self.assertEqual(precheck["source"], "assessed")
        self.assertEqual(precheck["state"], "low")
        self.assertEqual(precheck["fit_score"], 0)
        self.assertEqual(precheck["rank"], 6)
