import json
import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate


def _agent_loop_class():
    module = import_module("tools.orchestration.agent_loop")
    return module.AgentLoop


def _file_run_store_class():
    module = import_module("tools.infra.persistence.file_run_store")
    return module.FileRunStore


def _rank_candidate_batch():
    module = import_module("tools.orchestration.agent_loop")
    return module._rank_candidate_batch


class AgentLoopTests(unittest.TestCase):
    def _policy(self, max_rounds: int = 2) -> PolicyConfig:
        return PolicyConfig(
            n_pass_required=1,
            matching_threshold=0.6,
            evaluation_threshold=0.6,
            max_rounds=max_rounds,
            gate_mode="simulate",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
        )

    def _policy_with_limits(self, max_rounds: int, max_deliveries: int) -> PolicyConfig:
        return PolicyConfig(
            n_pass_required=1,
            matching_threshold=0.6,
            evaluation_threshold=0.6,
            max_rounds=max_rounds,
            gate_mode="simulate",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
            max_deliveries=max_deliveries,
        )

    def test_dry_run_completes_early(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = _agent_loop_class()(
                policy=self._policy(3),
                run_id="run-1",
                dry_run=True,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DRY_RUN_COMPLETE")
            self.assertEqual(result.rounds_completed, 1)
            replayed = loop.replay_state()
            self.assertEqual(replayed.current_status, "DONE")

    def test_non_dry_run_reaches_max_rounds(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = _agent_loop_class()(
                policy=self._policy(2),
                run_id="run-2",
                dry_run=False,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DONE")
            self.assertEqual(result.rounds_completed, 2)
            events = store.load_events("run-2")
            event_types = [event.event_type for event in events]
            self.assertIn("DELIVER", event_types)

    def test_run_agent_cli_outputs_json(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                """n_pass_required: 1
matching_threshold: 0.6
evaluation_threshold: 0.6
max_rounds: 2
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies: []
excluded_legal_entities: []
""",
                encoding="utf-8",
            )

            import subprocess

            result = subprocess.run(
                [
                    "python3",
                    "tools/run_agent.py",
                    "--policy",
                    str(policy_path),
                    "--dry-run",
                    "--run-id",
                    "run-test-cli",
                    "--output-dir",
                    str(Path(tmp) / "agent_runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            output_lines = [line for line in result.stdout.splitlines() if line.strip()]
            payload = json.loads(output_lines[-1])
            self.assertEqual(payload["run_id"], "run-test-cli")
            self.assertIn(payload["status"], ("DRY_RUN_COMPLETE", "DONE"))
            run_log = Path(tmp) / "agent_runs" / "run-test-cli" / "run_log.json"
            self.assertTrue(run_log.exists())

    def test_non_dry_run_stops_at_max_deliveries(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = _agent_loop_class()(
                policy=self._policy_with_limits(max_rounds=5, max_deliveries=1),
                run_id="run-max-deliveries",
                dry_run=False,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DONE")
            self.assertEqual(result.rounds_completed, 1)

    def test_candidate_batch_ranking_is_stable_and_excludes_selected(self) -> None:
        candidates = (
            Candidate(
                candidate_id="cand-b",
                direction="backend",
                company="B",
                job_url="https://example.com/b",
                confidence=0.9,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
            Candidate(
                candidate_id="cand-a",
                direction="backend",
                company="A",
                job_url="https://example.com/a",
                confidence=0.9,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
            Candidate(
                candidate_id="cand-c",
                direction="backend",
                company="C",
                job_url="https://example.com/c",
                confidence=0.7,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
        )

        ranked = _rank_candidate_batch()(candidates, {"cand-a"})

        self.assertEqual([candidate.candidate_id for candidate in ranked], ["cand-b", "cand-c"])


if __name__ == "__main__":
    _ = unittest.main()
