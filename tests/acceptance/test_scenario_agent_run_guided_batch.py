from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.sidecar.test_evidence_source_merge import _scoped_review, sample as source_sample
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore, read_generation_trace
from tools.sidecar.handlers import agent, evidence

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
    (project_root / "personal_profile.yaml").write_text('name: "合成候选人"\n', encoding="utf-8")
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


@pytest.mark.parametrize("source_sample", [(
    ["完成 Java 接口对接并提交联调清单。"],
    ["在隔离测试环境中将队列延迟降低 37%。", "完成 Java 接口验收并提交可追溯的交接清单。"],
)], indirect=True)
def test_guided_api_preserves_reviewed_fact_scope_and_generation_trace(source_sample, monkeypatch):
    """同卡被排除成果不借用为本人业绩；其余原始事实与来源身份保持可验证。"""
    materials_dir, card_path, params, scope = _scoped_review(source_sample)
    excluded, retained = params["draft"]["results"]
    source = params["draft"]["source_documents"][0]
    params["draft"]["field_sources"].append({
        "field": "results", "value": excluded, "quote": excluded,
        "material_id": source["material_id"], "document_id": source["document_id"],
    })
    params["review"]["fact_scope"] = {
        **scope, "field": "results", "index": 0, "value": excluded,
        "source": {**scope["source"], "quote": excluded}, "attribution": "teammate",
    }
    evidence.handle_evidence_save_draft(params)
    outside_title = "未选择的合成项目"
    outside_id = evidence.handle_evidence_save_draft({
        "meta": params["meta"], "review": {"decision": "approved"}, "save_mode": "eligible",
        "draft": {**params["draft"], "title": outside_title},
    })["evidence_id"]
    project_root = materials_dir.parent
    _write_policy(project_root / "policy.yaml")
    _write_active_profile(project_root)
    _write_job_leads(project_root)
    (project_root / "personal_profile.yaml").write_text('name: "合成候选人"\n', encoding="utf-8")
    runs_dir = project_root / "outputs" / "agent_runs"
    monkeypatch.setattr(agent, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(agent, "_AGENT_RUN_DIR", runs_dir)
    monkeypatch.setattr(agent, "_REVIEW_QUEUE_DIR", project_root / "outputs" / "review_queue")
    monkeypatch.setattr(agent, "_build_agent_run_id", lambda: "ar_reviewed_scope")
    monkeypatch.setenv("PPF_POLICY_PATH", str(project_root / "policy.yaml"))
    monkeypatch.setattr("tools.infra.persistence.review_snapshot._render_pdf",
                        lambda _source, destination: destination.write_bytes(b"%PDF-synthetic-test"))
    result = handle_agent_start({
        "meta": {"correlation_id": "guided-reviewed-scope"},
        "job_profile_id": "jp_agent_acceptance",
        "options": {
            "execute_guided_batch": True, "preflight_confirmed": True,
            "confirmed_no_real_submit": True, "max_rounds": 1, "max_candidates": 1,
            "matching_threshold": 0.01, "evaluation_threshold": 0.01,
            "candidate_ids": ["jl_agent_acceptance_1"], "evidence_ids": [card_path.stem],
        },
    })
    assert result["status"] == "REVIEW_PENDING"
    pending = handle_get_pending_review({"meta": params["meta"], "run_id": result["run_id"]})
    candidate, = pending["candidates"]
    content = candidate["resume_preview"]
    assert excluded not in content
    assert params["draft"]["actions"][0] in content
    assert retained in content
    assert outside_title not in content
    snapshot = ReviewSnapshotStore(runs_dir).load(result["run_id"], candidate)
    trace, valid = read_generation_trace(Path(snapshot["resume_markdown_path"]))
    assert valid, "guided review must retain the shared, source-bound generation trace"
    assert trace["evidence_card_ids"] == [card_path.stem]
    assert outside_id not in trace["inputs"]
    fact_ids = {claim.get("fact_id") for claim in trace["claims"]}
    assert f"{card_path.stem}:actions:0" in fact_ids
    assert f"{card_path.stem}:results:0" not in fact_ids
    assert f"{card_path.stem}:results:1" in fact_ids
    assert str((materials_dir / "m1.txt").resolve()) in {
        value["path"] for value in trace["inputs"].values()
    }
    fetched = handle_agent_get({"meta": params["meta"], "run_id": result["run_id"]})
    assert fetched["run"]["delivery_plan"]["external_submission_attempted"] is False
    assert all(event["event_type"] != "DELIVER" for event in fetched["events"])
