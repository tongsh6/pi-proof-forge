from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_journey_report,
    write_journey_report,
)
from tools.sidecar.handlers.jobs import (
    handle_jobs_generate_profile_draft,
    handle_jobs_list_profiles,
    handle_jobs_save_profile_draft,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def _write_policy(path: Path) -> None:
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


def _llm_response(content: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


def test_setup_job_target_l1_acceptance_writes_report(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "job_profiles"
    leads_dir = tmp_path / "job_leads"
    matching_dir = tmp_path / "matching_reports"
    policy_path = tmp_path / "policy.yaml"
    jd_text = (
        "Acme is hiring a Senior Backend Engineer to own checkout reliability. "
        "Must have Python and distributed systems experience."
    )
    source_url = "https://jobs.example.com/acme/backend"
    _write_policy(policy_path)
    complete_payload = {
        "target_role": "Senior Backend Engineer",
        "company": "Acme",
        "source_url": source_url,
        "jd_summary": "Own checkout reliability for Acme.",
        "must_have": ["Python", "Distributed systems"],
        "keywords": ["Python", "Reliability"],
        "nice_to_have": ["Kafka"],
        "business_domain": "E-commerce",
        "seniority_signal": ["Owner"],
        "tone": "technical",
    }

    with (
        patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
        patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
        patch("tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR", matching_dir),
        patch(
            "tools.sidecar.handlers.settings._resolve_policy_path",
            return_value=policy_path,
        ),
        patch(
            "tools.sidecar.handlers.jobs.LLMClient.post_json",
            return_value=_llm_response(complete_payload),
        ) as post_json,
        patch(
            "tools.sidecar.handlers.jobs._check_source_url_accessible",
            return_value={
                "checked": True,
                "accessible": True,
                "status": "accessible",
                "status_code": 200,
            },
        ) as url_check,
    ):
        generated = handle_jobs_generate_profile_draft(
            {
                "meta": {"correlation_id": "corr_job_generate"},
                "jd_text": jd_text,
                "source_url": source_url,
            }
        )
        with patch(
            "tools.sidecar.handlers.jobs.LLMClient.post_json",
            return_value={"choices": [{"message": {"content": "not-json"}}]},
        ):
            invalid_json = handle_jobs_generate_profile_draft(
                {
                    "meta": {"correlation_id": "corr_job_bad_json"},
                    "jd_text": jd_text,
                }
            )
        incomplete_draft = dict(generated["draft"])
        incomplete_draft["keywords"] = []
        no_review_rejected = False
        try:
            handle_jobs_save_profile_draft(
                {
                    "meta": {"correlation_id": "corr_job_no_review"},
                    "draft": incomplete_draft,
                    "save_mode": "incomplete",
                }
            )
        except ValueError:
            no_review_rejected = True
        incomplete = handle_jobs_save_profile_draft(
            {
                "meta": {"correlation_id": "corr_job_incomplete"},
                "draft": incomplete_draft,
                "review": {"decision": "approved"},
                "save_mode": "incomplete",
            }
        )
        complete = handle_jobs_save_profile_draft(
            {
                "meta": {"correlation_id": "corr_job_complete"},
                "draft": generated["draft"],
                "review": {
                    "decision": "approved",
                    "reviewed_at": "2026-05-21T00:00:00Z",
                },
                "save_mode": "complete",
            }
        )
        active_profiles = handle_jobs_list_profiles(
            {
                "meta": {"correlation_id": "corr_job_active"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": "active", "query": "", "tags": []},
            }
        )

    assert post_json.call_count == 1
    assert generated["status"] == "draft_ready_for_review"
    assert generated["active_target_eligible"] is False
    assert invalid_json["status"] == "parse_invalid_json"
    assert no_review_rejected is True
    assert incomplete["status"] == "saved_incomplete"
    assert incomplete["active_target_eligible"] is False
    assert "missing_keywords" in incomplete["missing_items"]
    assert complete["status"] == "saved_complete"
    assert complete["active_target_eligible"] is True
    assert complete["job_lead_id"].startswith("jl_")
    assert url_check.call_count == 1
    profile_text = (profiles_dir / f"{complete['job_profile_id']}.yaml").read_text(
        encoding="utf-8"
    )
    lead_text = (leads_dir / f"{complete['job_lead_id']}.yaml").read_text(
        encoding="utf-8"
    )
    assert f'job_lead_id: "{complete["job_lead_id"]}"' in profile_text
    assert f'job_profile_id: "{complete["job_profile_id"]}"' in lead_text
    assert active_profiles["items"][0]["job_profile_id"] == complete["job_profile_id"]

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="setup_job_target_l1",
        generated_at="2026-05-21T00:00:00Z",
        results={
            "job_target_ready_for_runs": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Pasted JD parsing, strict JSON rejection, review-required save, "
                    "incomplete inactive profile, complete active profile, source URL "
                    "check, and Job Profile/Job Lead bidirectional links are validated."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "job_target_ready_for_runs" in markdown_path.read_text(encoding="utf-8")
