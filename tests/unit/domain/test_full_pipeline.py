"""Integration tests for AgentLoop running the full 10-state pipeline.

These tests verify that the AgentLoop correctly orchestrates all engine
stages (DISCOVER → SCORE → GENERATE → EVALUATE → GATE → REVIEW → DELIVER →
LEARN → DONE) when built via Composer with real rule-mode engines.
"""

import json
import os
import unittest
from importlib import import_module
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def synthetic_review_pdf(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('tools.infra.persistence.review_snapshot._render_pdf',
                        lambda source, destination: destination.write_bytes(b'%PDF-unit-test'))

from tools.config.fragments import PolicyConfig
from tools.domain.models import EvidenceCard, JobProfile
from tools.domain.result import Ok
from tools.domain.value_objects import Candidate, DeliveryResult


def _composer_class():
    module = import_module("tools.config.composer")
    return module.Composer


def _file_run_store_class():
    module = import_module("tools.infra.persistence.file_run_store")
    return module.FileRunStore


def _make_policy(**overrides) -> PolicyConfig:
    defaults = dict(
        n_pass_required=1,
        matching_threshold=0.5,
        evaluation_threshold=0.5,
        max_rounds=3,
        gate_mode="simulate",
        delivery_mode="auto",
        batch_review=False,
        excluded_companies=(),
        excluded_legal_entities=(),
    )
    defaults.update(overrides)
    return PolicyConfig(**defaults)


def _make_evidence_cards() -> tuple[EvidenceCard, ...]:
    return (
        EvidenceCard(
            id="ec-test-001",
            title="High-throughput API Gateway migration",
            raw_source="test/logs.txt",
            results=("Reduced p99 latency by 60%", "Handled 50k QPS"),
            artifacts=("PR #1234", "grafana-dashboard.json"),
            tags=("api", "performance", "go"),
        ),
        EvidenceCard(
            id="ec-test-002",
            title="Distributed tracing rollout",
            raw_source="test/notes.md",
            results=("100% service coverage", "MTTR reduced by 40%"),
            artifacts=("opentelemetry-config.yaml", "runbook.md"),
            tags=("observability", "distributed-systems"),
        ),
        EvidenceCard(
            id="ec-test-003",
            title="Database sharding migration",
            raw_source="test/design.md",
            results=("Zero downtime migration", "Storage cost reduced 35%"),
            artifacts=("sharding-plan.md", "migration-script.sql"),
            tags=("database", "mysql", "performance"),
        ),
    )


def _make_job_profile() -> JobProfile:
    return JobProfile(
        id="jp-test-001",
        title="Senior Backend Engineer",
        keywords=("api", "performance", "go", "distributed-systems", "database"),
        level="senior",
        tone="architecture",
        must_have=("api design", "performance tuning"),
        nice_to_have=("observability", "database"),
    )


def _make_candidates() -> tuple[Candidate, ...]:
    return (
        Candidate(
            candidate_id="cand-001",
            direction="backend",
            company="TechCorp",
            job_url="https://example.com/jobs/123",
            confidence=0.85,
            source="job_leads",
            merged_sources=("job_leads",),
        ),
        Candidate(
            candidate_id="cand-002",
            direction="platform",
            company="CloudInc",
            job_url="https://example.com/jobs/456",
            confidence=0.75,
            source="jd_inputs",
            merged_sources=("jd_inputs",),
        ),
    )


class FullPipelineIntegrationTests(unittest.TestCase):
    """Verify AgentLoop runs all 10 states with real engines wired via Composer."""

    def test_full_pipeline_dry_run_all_states_visited(self) -> None:
        """Dry-run should visit INIT→DISCOVER→SCORE→GENERATE→EVALUATE→GATE→REVIEW→DELIVER→LEARN→DONE."""
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 2\n"
                "gate_mode: simulate\n"
                "delivery_mode: auto\n"
                "batch_review: false\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)

            loop = composer.build_agent_loop(
                run_id="run-full-int-001",
                dry_run=True,
                run_store=store,
                evidence_cards=_make_evidence_cards(),
                job_profile=_make_job_profile(),
                candidates=_make_candidates(),
            )

            result = loop.run()
            self.assertEqual(result.status, "DONE")
            self.assertGreaterEqual(result.rounds_completed, 1)

            # verify events were recorded
            events = store.load_events("run-full-int-001")
            event_types = [e.event_type for e in events]

            required_states = [
                "INIT", "DISCOVER", "SCORE", "GENERATE", "EVALUATE",
                "GATE", "REVIEW", "DELIVER", "LEARN", "DONE",
            ]
            for state in required_states:
                self.assertIn(state, event_types,
                              f"Missing state in event log: {state}")

            # verify SCORE produced a real score
            score_events = [e for e in events if e.event_type == "SCORE"]
            self.assertTrue(len(score_events) > 0)
            self.assertIn("matching_total", score_events[0].payload)

            # verify EVALUATE produced a real score
            eval_events = [e for e in events if e.event_type == "EVALUATE"]
            self.assertTrue(len(eval_events) > 0)
            self.assertIn("evaluation_total", eval_events[0].payload)

    def test_full_pipeline_respects_max_rounds(self) -> None:
        """AgentLoop should stop after max_rounds when gate keeps failing."""
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 2\n"          # requires 2 passes
                "matching_threshold: 0.99\n"     # impossibly high
                "evaluation_threshold: 0.99\n"   # impossibly high
                "max_rounds: 2\n"
                "gate_mode: strict\n"
                "delivery_mode: auto\n"
                "batch_review: false\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)

            loop = composer.build_agent_loop(
                run_id="run-max-rounds",
                dry_run=False,
                run_store=store,
                evidence_cards=_make_evidence_cards(),
                job_profile=_make_job_profile(),
                candidates=_make_candidates(),
            )

            result = loop.run()
            self.assertEqual(result.status, "DONE")
            self.assertEqual(result.rounds_completed, 2)

            events = store.load_events("run-max-rounds")
            done_events = [e for e in events if e.event_type == "DONE"]
            self.assertTrue(len(done_events) > 0)
            self.assertEqual(done_events[-1].payload.get("stop_reason"), "max_rounds")

    def test_full_pipeline_event_replay_restores_state(self) -> None:
        """RunState.replay() should restore the final state after a dry-run."""
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 1\n"
                "gate_mode: simulate\n"
                "delivery_mode: auto\n"
                "batch_review: false\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)

            loop = composer.build_agent_loop(
                run_id="run-replay-test",
                dry_run=True,
                run_store=store,
                evidence_cards=_make_evidence_cards(),
                job_profile=_make_job_profile(),
                candidates=_make_candidates(),
            )
            loop.run()

            # Replay should restore state
            replayed = loop.replay_state()
            self.assertEqual(replayed.run_id, "run-replay-test")
            self.assertEqual(replayed.current_status, "DONE")
            self.assertGreaterEqual(replayed.round_index, 0)

    def test_full_pipeline_gate_passes_with_good_scores(self) -> None:
        """When matching/evaluation scores meet threshold, GATE should pass."""
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 1\n"
                "gate_mode: strict\n"
                "delivery_mode: auto\n"
                "batch_review: false\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)

            loop = composer.build_agent_loop(
                run_id="run-gate-pass",
                dry_run=True,
                run_store=store,
                evidence_cards=_make_evidence_cards(),
                job_profile=_make_job_profile(),
                candidates=_make_candidates(),
            )
            result = loop.run()
            self.assertEqual(result.status, "DONE")

            events = store.load_events("run-gate-pass")
            event_types = [e.event_type for e in events]

            # With low thresholds and simulate mode, gate should pass,
            # so REVIEW and DELIVER should appear
            self.assertIn("REVIEW", event_types)
            self.assertIn("DELIVER", event_types)

    def test_manual_review_pauses_before_delivery_and_writes_queue(self) -> None:
        """Manual REVIEW should create a GUI-visible queue and stop before DELIVER."""
        with TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 1\n"
                "gate_mode: strict\n"
                "delivery_mode: manual\n"
                "batch_review: false\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)
            os.chdir(tmp)
            try:
                loop = composer.build_agent_loop(
                    run_id="run-review-pending",
                    dry_run=True,
                    run_store=store,
                    evidence_cards=_make_evidence_cards(),
                    job_profile=_make_job_profile(),
                    candidates=_make_candidates(),
                )

                result = loop.run()
            finally:
                os.chdir(cwd)

            self.assertEqual(result.status, "REVIEW_PENDING")
            self.assertEqual(result.rounds_completed, 1)

            events = store.load_events("run-review-pending")
            event_types = [event.event_type for event in events]
            self.assertIn("REVIEW", event_types)
            self.assertNotIn("DELIVER", event_types)
            review_event = [event for event in events if event.event_type == "REVIEW"][
                -1
            ]
            self.assertEqual(review_event.payload.get("waiting_for_review"), True)
            self.assertEqual(review_event.payload.get("pending_candidates"), 1)

            queue_path = (
                Path(tmp) / "outputs" / "review_queue" / "run-review-pending.json"
            )
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(queue["run_id"], "run-review-pending")
            self.assertEqual(queue["candidates"][0]["status"], "pending")
            self.assertEqual(queue["candidates"][0]["job_lead_id"], "cand-001")

    def test_manual_batch_review_collects_candidates_before_pause(self) -> None:
        """Batch REVIEW should collect candidates and pause once the batch is ready."""
        with TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 3\n"
                "gate_mode: strict\n"
                "delivery_mode: manual\n"
                "batch_review: true\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)
            os.chdir(tmp)
            try:
                loop = composer.build_agent_loop(
                    run_id="run-batch-review-pending",
                    dry_run=True,
                    run_store=store,
                    evidence_cards=_make_evidence_cards(),
                    job_profile=_make_job_profile(),
                    candidates=_make_candidates(),
                )

                result = loop.run()
            finally:
                os.chdir(cwd)

            self.assertEqual(result.status, "REVIEW_PENDING")
            self.assertEqual(result.rounds_completed, 2)
            events = store.load_events("run-batch-review-pending")
            event_types = [event.event_type for event in events]
            self.assertNotIn("DELIVER", event_types)
            self.assertEqual(event_types.count("REVIEW"), 2)
            review_events = [event for event in events if event.event_type == "REVIEW"]
            self.assertEqual(review_events[0].payload.get("collecting"), True)
            self.assertEqual(review_events[-1].payload.get("waiting_for_review"), True)

            queue_path = (
                Path(tmp) / "outputs" / "review_queue" / "run-batch-review-pending.json"
            )
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [candidate["job_lead_id"] for candidate in queue["candidates"]],
                ["cand-001", "cand-002"],
            )
            self.assertTrue(
                all(
                    candidate["status"] == "pending"
                    for candidate in queue["candidates"]
                )
            )

    def test_full_pipeline_batches_multiple_candidates_without_repeating_selection(self) -> None:
        """Multi-candidate delivery should advance through the candidate batch once per round."""
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 3\n"
                "max_deliveries: 2\n"
                "gate_mode: strict\n"
                "delivery_mode: auto\n"
                "batch_review: false\n"
                "excluded_companies: []\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)

            loop = composer.build_agent_loop(
                run_id="run-multi-candidate-batch",
                dry_run=True,
                run_store=store,
                evidence_cards=_make_evidence_cards(),
                job_profile=_make_job_profile(),
                candidates=_make_candidates(),
            )

            result = loop.run()

            self.assertEqual(result.status, "DONE")
            self.assertEqual(result.rounds_completed, 2)
            events = store.load_events("run-multi-candidate-batch")
            deliver_events = [e for e in events if e.event_type == "DELIVER"]
            selected_ids = [event.payload.get("candidate") for event in deliver_events]
            self.assertEqual(selected_ids, ["cand-001", "cand-002"])
            self.assertTrue(
                all(
                    event.payload.get("selection_strategy") == "confidence_desc_round_robin"
                    for event in deliver_events
                )
            )
            done_events = [e for e in events if e.event_type == "DONE"]
            self.assertEqual(done_events[-1].payload.get("stop_reason"), "max_deliveries")

    def test_full_pipeline_excluded_company_filtered(self) -> None:
        """Candidates from excluded companies should be filtered at DISCOVER."""
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                "n_pass_required: 1\n"
                "matching_threshold: 0.3\n"
                "evaluation_threshold: 0.3\n"
                "max_rounds: 1\n"
                "gate_mode: strict\n"
                "delivery_mode: auto\n"
                "batch_review: false\n"
                "excluded_companies:\n"
                "  - exact:TechCorp\n"
                "excluded_legal_entities: []\n",
                encoding="utf-8",
            )
            composer = _composer_class().from_policy_path(str(policy_path))
            store = _file_run_store_class()(base_dir=tmp)

            loop = composer.build_agent_loop(
                run_id="run-exclusion-test",
                dry_run=True,
                run_store=store,
                evidence_cards=_make_evidence_cards(),
                job_profile=_make_job_profile(),
                candidates=_make_candidates(),
            )
            loop.run()

            events = store.load_events("run-exclusion-test")
            discover_events = [e for e in events if e.event_type == "DISCOVER"]
            self.assertTrue(len(discover_events) > 0)
            payload = discover_events[0].payload
            self.assertIn("accepted", payload)
            self.assertIn("excluded", payload)
            self.assertEqual(payload["excluded"], 1)  # TechCorp excluded
            self.assertEqual(payload["accepted"], 1)  # CloudInc still in
            self.assertEqual(payload["total"], 2)  # 2 total before filtering

    def test_backward_compat_simplified_loop_still_works(self) -> None:
        """AgentLoop without engines should still work in simplified mode."""
        agent_loop_cls = getattr(
            import_module("tools.orchestration.agent_loop"), "AgentLoop"
        )
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = agent_loop_cls(
                policy=_make_policy(max_rounds=2),
                run_id="run-compat",
                dry_run=True,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DRY_RUN_COMPLETE")
            self.assertEqual(result.rounds_completed, 1)


@pytest.mark.parametrize("second_submission_success", [False, True])
def test_agent_counts_only_confirmed_submissions(tmp_path, monkeypatch, second_submission_success):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tools.infra.export.pdf_exporter.markdown_to_pdf", lambda source, destination: destination.write_bytes(b"%PDF-test-only"))
    composer = _composer_class()(policy=_make_policy(
        max_rounds=2, max_deliveries=1,
        gate_mode="strict", matching_threshold=0, evaluation_threshold=0,
    ))
    store = _file_run_store_class()(base_dir=str(tmp_path / "runs"))
    loop = composer.build_agent_loop(
        run_id="count-confirmed",
        dry_run=False,
        run_store=store,
        evidence_cards=_make_evidence_cards(),
        job_profile=_make_job_profile(),
        candidates=tuple(replace(candidate, platform="liepin", job_url=f"https://www.liepin.com/job/{index + 1}.shtml") for index, candidate in enumerate(_make_candidates())),
    )
    outcomes = [
        Ok(DeliveryResult("liepin", False, "", "checked_not_submitted", outcome="not_submitted")),
        Ok(DeliveryResult("liepin", second_submission_success, "submission-2", "已记录",
                          outcome="submitted" if second_submission_success else "not_submitted")),
    ]
    with patch("tools.channels.liepin.LiepinChannel.deliver", side_effect=outcomes):
        result = loop.run()
    events = store.load_events("count-confirmed")
    assert result.rounds_completed == 2
    deliveries = [event for event in events if event.event_type == "DELIVER"]
    assert [event.payload.get("success") for event in deliveries] == [False, second_submission_success]
    learn = [event for event in events if event.event_type == "LEARN"]
    assert learn[-1].payload["deliveries"] == int(second_submission_success)
    done = [event for event in events if event.event_type == "DONE"]
    assert done[-1].payload["stop_reason"] == (
        "max_deliveries" if second_submission_success else "max_rounds"
    )


def test_unknown_delivery_pauses_other_candidates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('tools.infra.export.pdf_exporter.markdown_to_pdf',
                        lambda source, destination: destination.write_bytes(b'%PDF-test-only'))
    composer = _composer_class()(policy=_make_policy(max_rounds=2, gate_mode='strict',
        matching_threshold=0, evaluation_threshold=0))
    loop = composer.build_agent_loop(run_id='unknown-pauses', dry_run=False,
        evidence_cards=_make_evidence_cards(), job_profile=_make_job_profile(),
        candidates=tuple(replace(c, platform='liepin', job_url=f'https://www.liepin.com/job/{i+1}.shtml')
                         for i,c in enumerate(_make_candidates())))
    with patch('tools.channels.liepin.LiepinChannel.deliver', side_effect=TimeoutError('unknown')) as channel:
        result = loop.run()
    assert channel.call_count == 1
    assert result.status == 'DELIVERY_BLOCKED'


def test_manual_mode_without_injected_review_stage_still_waits(tmp_path):
    composer = _composer_class()(policy=_make_policy(delivery_mode='manual', max_rounds=1,
        gate_mode='strict', matching_threshold=0, evaluation_threshold=0))
    loop = composer.build_agent_loop(run_id='missing-review-stage', dry_run=True,
        evidence_cards=_make_evidence_cards(), job_profile=_make_job_profile(), candidates=_make_candidates())
    loop._review = None
    assert loop.run().status == 'REVIEW_PENDING'


def test_full_pipeline_dry_run_separates_simulated_and_real_delivery_counts(tmp_path):
    composer = _composer_class()(policy=_make_policy(
        max_rounds=2, max_deliveries=1,
        gate_mode="strict", matching_threshold=0, evaluation_threshold=0,
    ))
    store = _file_run_store_class()(base_dir=str(tmp_path))
    loop = composer.build_agent_loop(
        run_id="dry-counts", dry_run=True, run_store=store,
        evidence_cards=_make_evidence_cards(), job_profile=_make_job_profile(),
        candidates=_make_candidates(),
    )
    result = loop.run()
    events = store.load_events("dry-counts")
    assert result.rounds_completed == 1
    learn = [event for event in events if event.event_type == "LEARN"]
    assert learn[-1].payload["deliveries"] == 0
    assert learn[-1].payload["simulated_deliveries"] == 1
    done = [event for event in events if event.event_type == "DONE"]
    assert done[-1].payload["deliveries_completed"] == 0
    deliveries = [event for event in events if event.event_type == "DELIVER"]
    assert all(event.payload.get("success") is False for event in deliveries)


if __name__ == "__main__":
    _ = unittest.main()


@pytest.mark.parametrize("profile_id", ["jp-other", ""])
def test_official_candidates_cannot_use_another_profile_in_cli_auto_discovery(tmp_path, monkeypatch, profile_id):
    monkeypatch.chdir(tmp_path)
    candidate = replace(_make_candidates()[0], source="liepin_official", platform="liepin",
                        job_url="https://www.liepin.com/job/19123456.shtml",
                        job_profile_id=profile_id, jd_status="complete_reviewed", source_jd_sha256="a" * 64)
    monkeypatch.setattr("tools.engines.discovery.job_leads_loader.discover_candidates", lambda **kwargs: [candidate])
    store = _file_run_store_class()(base_dir=str(tmp_path / "runs"))
    loop = _composer_class()(policy=_make_policy(max_rounds=1, gate_mode="strict",
        matching_threshold=0, evaluation_threshold=0, delivery_mode="manual", batch_review=True)).build_agent_loop(
        run_id="bound-cli", dry_run=True, run_store=store, evidence_cards=_make_evidence_cards(),
        job_profile=_make_job_profile())
    loop.run()
    events = store.load_events("bound-cli")
    discovered = [event for event in events if event.event_type == "DISCOVER"]
    assert discovered[0].payload["candidates"] == 0
    assert not (tmp_path / "outputs/review_queue/bound-cli.json").exists()
