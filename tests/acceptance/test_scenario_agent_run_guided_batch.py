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
from tools.sidecar.handlers.agent import (
    handle_agent_get,
    handle_agent_start,
    handle_get_pending_review,
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
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_active_profile(project_root: Path) -> None:
    profile_dir = project_root / "job_profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "jp_agent_acceptance.yaml").write_text(
        "\n".join(
            [
                'target_role: "Backend Tech Lead"',
                'company: "Acme"',
                'status: "active"',
                "keywords:",
                '  - "Java"',
                '  - "Kafka"',
                '  - "Redis"',
                "must_have:",
                '  - "Distributed systems"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_eligible_evidence(project_root: Path) -> None:
    evidence_dir = project_root / "evidence_cards"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "ec_agent_acceptance.yaml").write_text(
        "\n".join(
            [
                'id: "ec_agent_acceptance"',
                'title: "Inventory reliability platform"',
                'time_range: "2025-06 ~ 2025-09"',
                'context: "Peak traffic inventory consistency"',
                'role_scope: "Backend Tech Lead"',
                'status: "saved_eligible"',
                'candidate_pool_eligible: "true"',
                "actions:",
                '  - "Built Java Kafka Redis pipeline"',
                "results:",
                '  - "Reduced latency by 42%"',
                "stack:",
                '  - "Java"',
                '  - "Kafka"',
                '  - "Redis"',
                "artifacts:",
                '  - "latency.md"',
                "tags:",
                '  - "reliability"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_job_leads(project_root: Path) -> None:
    lead_dir = project_root / "job_leads"
    lead_dir.mkdir(parents=True, exist_ok=True)
    for index, lead_id in enumerate(["jl_agent_acceptance_1", "jl_agent_acceptance_2"], start=1):
        (lead_dir / f"{lead_id}.yaml").write_text(
            "\n".join(
                [
                    f'id: "{lead_id}"',
                    f'company: "Agent Acceptance {index}"',
                    'position: "Backend Tech Lead"',
                    'source: "fixture"',
                    f'url: "https://jobs.example.com/{lead_id}"',
                    'status: "new"',
                    'confidence: "0.90"',
                    "",
                ]
            ),
            encoding="utf-8",
        )


def test_agent_run_guided_batch_l1_acceptance_writes_report(tmp_path: Path) -> None:
    project_root = tmp_path
    runs_dir = project_root / "outputs" / "agent_runs"
    review_dir = project_root / "outputs" / "review_queue"
    policy_path = project_root / "policy.yaml"
    _write_policy(policy_path)
    _write_active_profile(project_root)
    _write_eligible_evidence(project_root)
    _write_job_leads(project_root)

    with (
        patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
        patch("tools.sidecar.handlers.agent._AGENT_RUN_DIR", runs_dir),
        patch("tools.sidecar.handlers.agent._REVIEW_QUEUE_DIR", review_dir),
        patch(
            "tools.sidecar.handlers.agent._build_agent_run_id",
            return_value="ar_agent_acceptance",
        ),
        patch(
            "tools.sidecar.handlers.settings._resolve_policy_path",
            return_value=policy_path,
        ),
    ):
        missing_preflight_rejected = False
        try:
            handle_agent_start(
                {
                    "meta": {"correlation_id": "corr_agent_missing_preflight"},
                    "job_profile_id": "jp_agent_acceptance",
                    "options": {"execute_guided_batch": True},
                }
            )
        except ValueError as exc:
            missing_preflight_rejected = "preflight_confirmation_required" in str(exc)

        submit_enabled_rejected = False
        try:
            handle_agent_start(
                {
                    "meta": {"correlation_id": "corr_agent_submit_enabled"},
                    "job_profile_id": "jp_agent_acceptance",
                    "options": {
                        "execute_guided_batch": True,
                        "preflight_confirmed": True,
                        "confirmed_no_real_submit": True,
                        "submit_enabled": True,
                    },
                }
            )
        except ValueError as exc:
            submit_enabled_rejected = "submit_enable_blocked_for_case" in str(exc)

        start = handle_agent_start(
            {
                "meta": {"correlation_id": "corr_agent_guided"},
                "job_profile_id": "jp_agent_acceptance",
                "options": {
                    "execute_guided_batch": True,
                    "preflight_confirmed": True,
                    "confirmed_no_real_submit": True,
                    "max_rounds": 2,
                    "max_candidates": 2,
                    "candidate_ids": [
                        "jl_agent_acceptance_1",
                        "jl_agent_acceptance_2",
                    ],
                    "evidence_ids": ["ec_agent_acceptance"],
                },
            }
        )
        fetched = handle_agent_get(
            {
                "meta": {"correlation_id": "corr_agent_guided_get"},
                "run_id": "ar_agent_acceptance",
            }
        )
        pending = handle_get_pending_review(
            {
                "meta": {"correlation_id": "corr_agent_pending"},
                "run_id": "ar_agent_acceptance",
            }
        )

    assert missing_preflight_rejected is True
    assert submit_enabled_rejected is True
    assert start["status"] == "REVIEW_PENDING"
    assert fetched["run"]["guided_batch"] is True
    assert fetched["run"]["preflight_confirmation"]["confirmed_no_real_submit"] is True
    assert fetched["run"]["policy_limits"]["submit_enabled"] is False
    assert fetched["run"]["delivery_plan"]["external_submission_attempted"] is False
    assert fetched["run"]["delivery_plan"]["delivery_events"] == 0
    assert fetched["run"]["review_queue"]["pending_count"] == 2
    assert len(pending["candidates"]) == 2
    event_types = [event["event_type"] for event in fetched["events"]]
    for required in ["INIT", "DISCOVER", "SCORE", "GENERATE", "EVALUATE", "GATE", "REVIEW"]:
        assert required in event_types
    assert "DELIVER" not in event_types
    assert len(fetched["gate_checks"]) >= 1
    assert (project_root / fetched["run"]["run_log"]).exists()

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="agent_run_guided_batch_l1",
        generated_at="2026-05-22T00:00:00Z",
        results={
            "agent_run_batch_is_guarded": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Guided Agent Run records preflight confirmation, selected "
                    "candidates, gate events, review queue, run log traceability, "
                    "and a delivery plan with no external submission."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "agent_run_batch_is_guarded" in markdown_path.read_text(encoding="utf-8")
