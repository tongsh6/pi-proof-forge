"""Tests for agent run / REVIEW handlers."""

import json
import os
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def synthetic_review_pdf(monkeypatch):
    monkeypatch.setattr('tools.infra.persistence.review_snapshot._render_pdf',
                        lambda source, destination: destination.write_bytes(b'%PDF-unit-test'))

from tools.sidecar.handlers import agent
from tools.sidecar.handlers.agent import (
    _persisted_llm_runtime_context,
    _stage_progress_from_events,
    handle_agent_get,
    handle_agent_start,
    handle_create_review_candidates,
    handle_get_pending_review,
    handle_quick_cancel,
    handle_quick_get,
    handle_quick_start,
    handle_submit_review,
)

_QUICK_RUN_TERMINAL_STATUSES = {"DONE", "SKIPPED", "FAILED", "TIMEOUT", "stopped"}


class _FakeQuickRunProcess:
    """subprocess.Popen 替身：只实现 Quick Run 后台线程使用的接口。"""

    def __init__(
        self,
        *,
        returncode: int | None = 0,
        finish_event: threading.Event | None = None,
        respond_to_terminate: bool = True,
    ) -> None:
        self.returncode = returncode
        self._finish_event = finish_event
        self._respond_to_terminate = respond_to_terminate
        self.terminated = 0
        self.killed = 0
        self.poll_calls = 0

    def poll(self) -> int | None:
        self.poll_calls += 1
        if self._finish_event is not None and not self._finish_event.is_set():
            return None
        return self.returncode

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated += 1
        if self._respond_to_terminate:
            self.returncode = -15
            if self._finish_event is not None:
                self._finish_event.set()

    def kill(self) -> None:
        self.killed += 1
        self.returncode = -9
        if self._finish_event is not None:
            self._finish_event.set()


def _quick_run_popen(
    *,
    returncode: int | None = 0,
    stdout_text: str = "",
    stderr_text: str = "",
    finish_event: threading.Event | None = None,
    respond_to_terminate: bool = True,
    on_spawn=None,
):
    """构造 Popen 替身；返回 (spawner, process)，spawner 用于 patch agent.Popen。"""

    process = _FakeQuickRunProcess(
        returncode=returncode,
        finish_event=finish_event,
        respond_to_terminate=respond_to_terminate,
    )

    def spawn(command, **kwargs):
        stdout = kwargs.get("stdout")
        if stdout is not None and stdout_text:
            stdout.write(stdout_text.encode("utf-8"))
            stdout.flush()
        stderr = kwargs.get("stderr")
        if stderr is not None and stderr_text:
            stderr.write(stderr_text.encode("utf-8"))
            stderr.flush()
        if on_spawn is not None:
            on_spawn(command, process)
        return process

    return spawn, process


def _get_quick_run(run_id: str) -> dict:
    return handle_quick_get(
        {"meta": {"correlation_id": "corr_quick_get"}, "run_id": run_id}
    )


def _wait_quick_run(run_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    result: dict = {}
    while time.monotonic() < deadline:
        result = _get_quick_run(run_id)
        if result["status"] in _QUICK_RUN_TERMINAL_STATUSES:
            agent._join_quick_run_thread(5.0)
            return result
        time.sleep(0.01)
    agent._join_quick_run_thread(1.0)
    raise AssertionError(f"quick run {run_id} did not reach a terminal state: {result}")


def _wait_quick_run_until(run_id: str, predicate, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    result: dict = {}
    while time.monotonic() < deadline:
        result = _get_quick_run(run_id)
        if predicate(result):
            return result
        time.sleep(0.01)
    raise AssertionError(f"quick run {run_id} progress condition not met: {result}")


def _wait_active_process(run_id: str, *, timeout: float = 5.0) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        active = agent._QUICK_RUN_ACTIVE
        if active is not None and active.get("run_id") == run_id and active.get("process") is not None:
            return active["process"]
        time.sleep(0.005)
    raise AssertionError(f"quick run {run_id} never registered an active process")


def _stage_statuses(progress: dict) -> dict[str, str]:
    return {stage["key"]: stage["status"] for stage in progress["stages"]}


def _pipeline_event(event_type: str, timestamp: str, **payload) -> dict:
    return {
        "run_id": "qr_test",
        "event_type": event_type,
        "round_index": 0,
        "payload": payload,
        "timestamp": timestamp,
    }


def _write_active_profile(profile_dir: Path, profile_id: str = "jp-001") -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / f"{profile_id}.yaml").write_text(
        "\n".join(
            [
                "target_role: Backend",
                "status: active",
                "keywords:",
                '  - "Kafka"',
                "must_have:",
                '  - "Java"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_eligible_evidence(
    project_root: Path, evidence_id: str = "ec_saved", raw_source: str = "materials/mat.md"
) -> None:
    evidence_dir = project_root / "evidence_cards"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"{evidence_id}.yaml").write_text(
        "\n".join(
            [
                f'id: "{evidence_id}"',
                'title: "Saved eligible card"',
                'time_range: "2025-06 ~ 2025-09"',
                'context: "Inventory reliability"',
                'role_scope: "Tech Lead"',
                'status: "saved_eligible"',
                'candidate_pool_eligible: "true"',
                "actions:",
                '  - "Built Java Kafka inventory sync"',
                "results:",
                '  - "P95 latency dropped to 1.8s"',
                "stack:",
                '  - "Java"',
                '  - "Kafka"',
                "artifacts:",
                '  - "latency.md"',
                "tags:",
                '  - "reliability"',
                f'raw_source: "{raw_source}"',
                "source_material_ids:",
                '  - "mat_001"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_job_lead(project_root: Path, lead_id: str, company: str = "Acme") -> None:
    lead_dir = project_root / "job_leads"
    lead_dir.mkdir(parents=True, exist_ok=True)
    (lead_dir / f"{lead_id}.yaml").write_text(
        "\n".join(
            [
                f'id: "{lead_id}"',
                f'company: "{company}"',
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


class TestCreateReviewCandidates:
    def test_creates_candidates_successfully(self):
        with TemporaryDirectory() as tmp:
            review_dir = Path(tmp) / "review_queue"
            with patch("tools.sidecar.handlers.agent._REVIEW_QUEUE_DIR", review_dir):
                result = handle_create_review_candidates(
                    {
                        "meta": {"correlation_id": "corr_001"},
                        "run_id": "run_2026_001",
                        "candidates": [
                            {
                                "job_lead_id": "jl_001",
                                "company": "Acme",
                                "position": "Backend Engineer",
                                "matching_score": 85,
                                "evaluation_score": 90,
                                "round_index": 1,
                                "resume_version": "v1",
                            }
                        ],
                    }
                )

        assert result["meta"]["correlation_id"] == "corr_001"
        assert result["run_id"] == "run_2026_001"
        assert result["created"] == 1


class TestGetPendingReview:
    def test_returns_pending_candidates(self):
        with TemporaryDirectory() as tmp:
            review_dir = Path(tmp) / "review_queue"
            review_dir.mkdir()
            queue_file = review_dir / "run_001.json"
            queue_file.write_text(
                json.dumps(
                    {
                        "run_id": "run_001",
                        "candidates": [
                            {
                                "job_lead_id": "jl_001",
                                "company": "Acme",
                                "position": "Backend",
                                "matching_score": 85,
                                "evaluation_score": 90,
                                "round_index": 1,
                                "resume_version": "v1",
                                "status": "pending",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("tools.sidecar.handlers.agent._REVIEW_QUEUE_DIR", review_dir):
                result = handle_get_pending_review(
                    {"meta": {"correlation_id": "corr_002"}, "run_id": "run_001"}
                )

        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["job_lead_id"] == "jl_001"


class TestSubmitReview:
    def test_legacy_queue_without_snapshot_cannot_be_approved(self):
        with TemporaryDirectory() as tmp:
            review_dir = Path(tmp) / "review_queue"
            review_dir.mkdir()
            queue_file = review_dir / "run_001.json"
            queue_file.write_text(
                json.dumps(
                    {
                        "run_id": "run_001",
                        "candidates": [
                            {
                                "job_lead_id": "jl_001",
                                "company": "Acme",
                                "position": "Backend",
                                "matching_score": 85,
                                "status": "pending",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("tools.sidecar.handlers.agent._REVIEW_QUEUE_DIR", review_dir):
                with pytest.raises(ValueError, match='review_snapshot'):
                    handle_submit_review(
                    {
                        "meta": {"correlation_id": "corr_004"},
                        "run_id": "run_001",
                        "decisions": [
                            {
                                "job_lead_id": "jl_001",
                                "action": "approve",
                                "decided_by": "user",
                            }
                        ],
                    }
                )

                updated = json.loads(queue_file.read_text(encoding="utf-8"))

        assert updated["candidates"][0]["status"] == "pending"


class TestQuickRunStart:
    def test_resolves_default_paths_from_project_root_when_cwd_differs(self):
        with TemporaryDirectory() as project_tmp, TemporaryDirectory() as cwd_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            tools_dir = project_root / "tools"
            profile_dir = project_root / "job_profiles"
            tools_dir.mkdir()
            (tools_dir / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(profile_dir)
            _write_eligible_evidence(project_root)

            spawn, _process = _quick_run_popen(stdout_text="[pipeline] done\n")

            cwd = Path.cwd()
            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_root"),
                patch(
                    "tools.sidecar.handlers.agent.Popen",
                    side_effect=spawn,
                ) as run_mock,
            ):
                try:
                    os.chdir(cwd_tmp)
                    started = handle_quick_start(
                        {
                            "meta": {"correlation_id": "corr_quick_root"},
                            "job_profile_id": "jp-001",
                        }
                    )
                    result = _wait_quick_run(started["run_id"])
                finally:
                    os.chdir(cwd)

        assert started["status"] == "RUNNING"
        assert started["progress"]["stages"][0]["key"] == "extract"
        assert result["status"] == "DONE"
        command = run_mock.call_args.args[0]
        assert command[1] == str(project_root / "tools" / "run_pipeline.py")
        assert command[command.index("--personal-profile") + 1] == str(project_root / "personal_profile.yaml")
        assert run_mock.call_args.kwargs["cwd"] == str(project_root)

    def test_returns_stdout_artifacts_and_matching_scores(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            tools_dir = project_root / "tools"
            profile_dir = project_root / "job_profiles"
            matching_dir = project_root / "matching_reports"
            summary_dir = project_root / "outputs" / "agent_runs" / "qr_test"
            tools_dir.mkdir()
            matching_dir.mkdir()
            summary_dir.mkdir(parents=True)
            (tools_dir / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(profile_dir)
            _write_eligible_evidence(project_root, evidence_id="ec_test")
            (matching_dir / "mr-qr_test.yaml").write_text(
                "\n".join(
                    [
                        "score_total: 82",
                        "score_breakdown:",
                        '  K: { score: 18, reason: "stack match" }',
                        '  D: { score: 14, reason: "domain match" }',
                        '  S: { score: 15, reason: "scope match" }',
                        '  Q: { score: 13, reason: "quality match" }',
                        '  E: { score: 12, reason: "impact match" }',
                        '  R: { score: 10, reason: "recency match" }',
                    ]
                ),
                encoding="utf-8",
            )
            (summary_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "status": "DONE",
                        "artifacts": {
                            "matching": "matching_reports/mr-qr_test.yaml",
                            "scorecard": "outputs/scorecards/scorecard_mr-qr_test_A.md",
                        },
                    }
                ),
                encoding="utf-8",
            )

            spawn, _process = _quick_run_popen(stdout_text="[pipeline] done\n")

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_test"),
                patch(
                    "tools.sidecar.handlers.agent.Popen",
                    side_effect=spawn,
                ),
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_scores"},
                        "job_profile_id": "jp-001",
                    }
                )
                result = _wait_quick_run(started["run_id"])

        assert result["stdout"] == "[pipeline] done\n"
        assert result["artifacts"]["matching"] == "matching_reports/mr-qr_test.yaml"
        assert result["score_total"] == 82
        assert result["score_breakdown"]["K"]["score"] == 18

    def test_quick_run_records_masked_persisted_llm_config_summary(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            tools_dir = project_root / "tools"
            profile_dir = project_root / "job_profiles"
            policy_path = project_root / "policy.yaml"
            tools_dir.mkdir()
            (tools_dir / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(profile_dir)
            _write_eligible_evidence(project_root)
            policy_path.write_text(
                "\n".join(
                    [
                        'llm_provider: "lm_studio"',
                        'llm_model: "local-model"',
                        'llm_base_url: "http://127.0.0.1:1234/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_updated_at: "2026-05-21T00:00:00Z"',
                        'llm_api_key_placeholder: "configured"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            spawn, _process = _quick_run_popen(stdout_text="[pipeline] done\n")

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch(
                    "tools.sidecar.handlers.agent._build_quick_run_id",
                    return_value="qr_llm",
                ),
                patch.dict(
                    os.environ,
                    {"PPF_POLICY_PATH": str(policy_path)},
                    clear=True,
                ),
                patch(
                    "tools.sidecar.handlers.agent.Popen",
                    side_effect=spawn,
                ) as run_mock,
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_llm"},
                        "job_profile_id": "jp-001",
                    }
                )
                result = _wait_quick_run(started["run_id"])
                run_payload = json.loads(
                    (quick_dir / "qr_llm.json").read_text(encoding="utf-8")
                )

            summary = result["llm_config_summary"]
            assert summary["provider"] == "lm_studio"
            assert summary["model"] == "local-model"
            assert summary["base_url"] == "http://127.0.0.1:1234/v1"
            assert summary["api_key"]["configured"] is True
            assert summary["api_key"]["masked"] is True
            assert "value" not in summary["api_key"]
            assert "secret" not in summary["api_key"]
            env = run_mock.call_args.kwargs["env"]
            assert env["LLM_PROVIDER"] == "lm_studio"
            assert env["LLM_MODEL"] == "local-model"
            assert env["LLM_BASE_URL"] == "http://127.0.0.1:1234/v1"
            assert env["LLM_TIMEOUT"] == str(summary["timeout"]), "系统设置超时必须下发给管线各 LLM 阶段"
            assert run_payload["run"]["llm_config_summary"] == summary

    def test_quick_run_uses_latest_material_source_and_isolated_evidence_dir(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            tools_dir = project_root / "tools"
            profile_dir = project_root / "job_profiles"
            materials_dir = project_root / "materials"
            summary_dir = project_root / "outputs" / "agent_runs" / "qr_material"
            tools_dir.mkdir()
            _write_active_profile(profile_dir)
            materials_dir.mkdir()
            summary_dir.mkdir(parents=True)
            (tools_dir / "sample_raw.txt").write_text("fallback", encoding="utf-8")
            _write_eligible_evidence(
                project_root,
                evidence_id="ec-qr_material",
                raw_source=str(materials_dir / "mat_001.md"),
            )
            (materials_dir / "mat_001.md").write_text("material raw", encoding="utf-8")
            (materials_dir / "mat_001.meta.yaml").write_text(
                "\n".join(
                    [
                        'material_id: "mat_001"',
                        'resource_id: "res_001"',
                        'label: "Material One"',
                        'kind: "raw_work_material"',
                        'filename: "mat_001.md"',
                        'extension: ".md"',
                        'uploaded_at: "2026-05-21T00:00:00Z"',
                        'preview: "material raw"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            evidence_path = (
                project_root
                / "outputs"
                / "quick_runs"
                / "qr_material"
                / "evidence_cards"
                / "ec-qr_material.yaml"
            )
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text(
                "\n".join(
                    [
                        'id: "ec-qr_material"',
                        'title: "Material One"',
                        f'raw_source: "{materials_dir / "mat_001.md"}"',
                        "results:",
                        '  - "P95 从 6s 降至 1.8s"',
                        "artifacts:",
                        '  - "latency.png"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            matching_dir = project_root / "matching_reports"
            matching_dir.mkdir()
            (matching_dir / "mr-qr_material.yaml").write_text(
                "\n".join(
                    [
                        'job_profile_id: "jp-001"',
                        "evidence_card_ids:",
                        '  - "ec-qr_material"',
                        "score_total: 20",
                        "score_breakdown:",
                        '  K: { score: 10, reason: "material match" }',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            resume_dir = project_root / "outputs" / "qr_material"
            resume_dir.mkdir(parents=True)
            (resume_dir / "resume_mr-qr_material_A.md").write_text(
                "Evidence trace: id=ec-qr_material\n", encoding="utf-8"
            )
            (summary_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "status": "DONE",
                        "artifacts": {
                            "evidence": "outputs/quick_runs/qr_material/evidence_cards/ec-qr_material.yaml",
                            "matching": "matching_reports/mr-qr_material.yaml",
                            "resume_dir": "outputs/qr_material",
                            "scorecard": "outputs/scorecards/scorecard_mr-qr_material_A.md",
                        },
                    }
                ),
                encoding="utf-8",
            )

            spawn, _process = _quick_run_popen(stdout_text="[pipeline] done\n")

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch(
                    "tools.sidecar.handlers.agent._build_quick_run_id",
                    return_value="qr_material",
                ),
                patch(
                    "tools.sidecar.handlers.agent.Popen",
                    side_effect=spawn,
                ) as run_mock,
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_material"},
                        "job_profile_id": "jp-001",
                    }
                )
                result = _wait_quick_run(started["run_id"])
                run_payload = json.loads(
                    (quick_dir / "qr_material.json").read_text(encoding="utf-8")
                )

        command = run_mock.call_args.args[0]
        assert command[command.index("--raw") + 1] == str(materials_dir / "mat_001.md")
        assert command[command.index("--evidence-dir") + 1] == str(
            Path("outputs") / "quick_runs" / "qr_material" / "evidence_cards"
        )
        assert result["material_source"]["material_id"] == "mat_001"
        assert result["traceability"]["evidence_card_ids"] == ["ec-qr_material"]
        assert result["traceability"]["evidence"]["raw_source"] == str(
            materials_dir / "mat_001.md"
        )
        assert result["traceability"]["resume_traceable"] is False
        assert result["resume_readiness"]["deliverable"] is False
        assert result["resume_readiness"]["manual_override_allowed"] is True
        assert result["resume_readiness"]["quality_gate_blocking"] is False
        assert run_payload["run"]["material_source"]["material_id"] == "mat_001"
        assert run_payload["traceability"]["resume_traceable"] is False

    def test_start_returns_immediately_while_pipeline_keeps_running(self, monkeypatch):
        monkeypatch.setattr(agent, "_QUICK_RUN_POLL_INTERVAL_SECONDS", 0.02)
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            (project_root / "tools").mkdir()
            (project_root / "tools" / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(project_root / "job_profiles")
            _write_eligible_evidence(project_root)

            finish_event = threading.Event()
            spawn, process = _quick_run_popen(finish_event=finish_event)

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_async"),
                patch("tools.sidecar.handlers.agent.Popen", side_effect=spawn),
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_async"},
                        "job_profile_id": "jp-001",
                    }
                )
                assert started["status"] == "RUNNING"
                assert started["run_id"] == "qr_async"
                assert started["started_at"]
                assert started["finished_at"] == ""
                assert started["progress"]["current_stage"] == "extract"
                assert _stage_statuses(started["progress"])["extract"] == "running"
                assert started["progress"]["stages"][0]["started_at"] == started["started_at"]
                assert "artifacts" not in started
                assert "stdout" not in started

                running = _get_quick_run("qr_async")
                assert running["status"] == "RUNNING"
                assert running["progress"]["stages"]

                finish_event.set()
                result = _wait_quick_run(started["run_id"])

        assert result["status"] == "DONE"
        assert process.poll_calls >= 1

    def test_get_unknown_run_raises_not_found(self):
        with TemporaryDirectory() as tmp:
            quick_dir = Path(tmp) / "outputs" / "quick_runs"
            with patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir):
                with pytest.raises(KeyError, match="NOT_FOUND"):
                    _get_quick_run("qr_missing")

    def test_second_start_rejected_while_first_run_is_active(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            (project_root / "tools").mkdir()
            (project_root / "tools" / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(project_root / "job_profiles")
            _write_eligible_evidence(project_root)

            finish_event = threading.Event()
            spawn, _process = _quick_run_popen(finish_event=finish_event)

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_active"),
                patch("tools.sidecar.handlers.agent.Popen", side_effect=spawn),
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_active"},
                        "job_profile_id": "jp-001",
                    }
                )
                _wait_active_process(started["run_id"])
                with pytest.raises(ValueError, match="quick_run_already_running"):
                    handle_quick_start(
                        {
                            "meta": {"correlation_id": "corr_quick_active_2"},
                            "job_profile_id": "jp-001",
                        }
                    )
                finish_event.set()
                assert _wait_quick_run(started["run_id"])["status"] == "DONE"

    def test_sync_validation_failure_raises_before_background_start(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            (project_root / "tools").mkdir()
            (project_root / "tools" / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_eligible_evidence(project_root)
            # 缺 job_profiles/jp-001.yaml，应在启动后台线程前同步抛错。
            spawn, _process = _quick_run_popen()

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent.Popen", side_effect=spawn) as popen_mock,
            ):
                with pytest.raises(ValueError, match="job_profile_path does not exist"):
                    handle_quick_start(
                        {
                            "meta": {"correlation_id": "corr_quick_invalid"},
                            "job_profile_id": "jp-001",
                        }
                    )
                popen_mock.assert_not_called()
                assert agent._QUICK_RUN_ACTIVE is None

    def test_cancel_while_running_marks_stopped(self, monkeypatch):
        monkeypatch.setattr(agent, "_QUICK_RUN_POLL_INTERVAL_SECONDS", 0.02)
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            (project_root / "tools").mkdir()
            (project_root / "tools" / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(project_root / "job_profiles")
            _write_eligible_evidence(project_root)

            finish_event = threading.Event()
            spawn, process = _quick_run_popen(finish_event=finish_event)

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_cancel"),
                patch("tools.sidecar.handlers.agent.Popen", side_effect=spawn),
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_cancel"},
                        "job_profile_id": "jp-001",
                    }
                )
                _wait_active_process(started["run_id"])
                cancelled = handle_quick_cancel(
                    {
                        "meta": {"correlation_id": "corr_quick_cancel_2"},
                        "run_id": started["run_id"],
                    }
                )
                result = _wait_quick_run(started["run_id"])
                run_payload = json.loads(
                    (quick_dir / "qr_cancel.json").read_text(encoding="utf-8")
                )

        assert cancelled["accepted"] is True
        assert result["status"] == "stopped"
        assert result["finished_at"]
        assert process.terminated == 1
        assert run_payload["run"]["cancel_requested_at"]
        assert run_payload["run"]["status"] == "stopped"
        assert all(
            stage["status"] != "running" for stage in result["progress"]["stages"]
        )
        assert result["progress"]["current_stage"] is None

    def test_timeout_terminates_process_and_marks_timeout(self, monkeypatch):
        monkeypatch.setattr(agent, "_QUICK_RUN_POLL_INTERVAL_SECONDS", 0.02)
        monkeypatch.setattr(agent, "_QUICK_RUN_TERMINATE_GRACE_SECONDS", 0.05)
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            (project_root / "tools").mkdir()
            (project_root / "tools" / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(project_root / "job_profiles")
            _write_eligible_evidence(project_root)

            spawn, process = _quick_run_popen(
                returncode=None, respond_to_terminate=False
            )

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_timeout"),
                patch("tools.sidecar.handlers.agent.Popen", side_effect=spawn),
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_timeout"},
                        "job_profile_id": "jp-001",
                        "options": {"timeout_seconds": 1},
                    }
                )
                result = _wait_quick_run(started["run_id"], timeout=10.0)

        assert result["status"] == "TIMEOUT"
        assert process.terminated >= 1
        assert process.killed >= 1
        assert _stage_statuses(result["progress"])["extract"] == "error"

    def test_progress_advances_from_pipeline_run_log(self, monkeypatch):
        monkeypatch.setattr(agent, "_QUICK_RUN_POLL_INTERVAL_SECONDS", 0.02)
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            (project_root / "tools").mkdir()
            (project_root / "tools" / "sample_raw.txt").write_text("raw", encoding="utf-8")
            _write_active_profile(project_root / "job_profiles")
            _write_eligible_evidence(project_root)

            finish_event = threading.Event()

            def write_stage_events(command, _process):
                run_id = command[command.index("--run-id") + 1]
                run_dir = project_root / "outputs" / "agent_runs" / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                events = [
                    _pipeline_event("PIPELINE_START", "2026-10-22T00:00:00Z"),
                    _pipeline_event(
                        "PIPELINE_STEP_SUCCESS",
                        "2026-10-22T00:00:01Z",
                        step="evidence-selection",
                    ),
                    _pipeline_event(
                        "PIPELINE_STEP_START",
                        "2026-10-22T00:00:02Z",
                        step="matching-scoring",
                    ),
                ]
                (run_dir / "run_log.json").write_text(
                    json.dumps(events), encoding="utf-8"
                )

            spawn, _process = _quick_run_popen(
                finish_event=finish_event, on_spawn=write_stage_events
            )

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch("tools.sidecar.handlers.agent._build_quick_run_id", return_value="qr_progress"),
                patch("tools.sidecar.handlers.agent.Popen", side_effect=spawn),
            ):
                started = handle_quick_start(
                    {
                        "meta": {"correlation_id": "corr_quick_progress"},
                        "job_profile_id": "jp-001",
                    }
                )
                intermediate = _wait_quick_run_until(
                    started["run_id"],
                    lambda result: _stage_statuses(result["progress"]).get("match")
                    == "running",
                )
                assert _stage_statuses(intermediate["progress"]) == {
                    "extract": "done",
                    "match": "running",
                    "generate": "waiting",
                    "evaluate": "waiting",
                }
                assert intermediate["progress"]["current_stage"] == "match"
                finish_event.set()
                final = _wait_quick_run(started["run_id"])

        assert final["status"] == "DONE"
        assert all(
            stage["status"] == "done" for stage in final["progress"]["stages"]
        )


class TestQuickRunStageProgress:
    STARTED_AT = "2026-10-22T00:00:00Z"

    def test_empty_events_mark_first_stage_running(self):
        progress = _stage_progress_from_events([], started_at=self.STARTED_AT)
        assert [stage["key"] for stage in progress["stages"]] == [
            "extract",
            "match",
            "generate",
            "evaluate",
        ]
        assert _stage_statuses(progress) == {
            "extract": "running",
            "match": "waiting",
            "generate": "waiting",
            "evaluate": "waiting",
        }
        assert progress["stages"][0]["started_at"] == self.STARTED_AT
        assert progress["current_stage"] == "extract"

    def test_events_advance_stages_in_order_with_elapsed_seconds(self):
        events = [
            _pipeline_event("PIPELINE_START", self.STARTED_AT),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:01Z",
                step="evidence-selection",
            ),
            _pipeline_event(
                "PIPELINE_STEP_START",
                "2026-10-22T00:00:02Z",
                step="matching-scoring",
            ),
        ]
        progress = _stage_progress_from_events(events, started_at=self.STARTED_AT)
        assert _stage_statuses(progress) == {
            "extract": "done",
            "match": "running",
            "generate": "waiting",
            "evaluate": "waiting",
        }
        assert progress["current_stage"] == "match"
        assert progress["stages"][0]["finished_at"] == "2026-10-22T00:00:01Z"
        assert progress["stages"][0]["elapsed_seconds"] == 1

    def test_failed_step_marks_error_and_leaves_remaining_waiting(self):
        events = [
            _pipeline_event("PIPELINE_START", self.STARTED_AT),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:01Z",
                step="evidence-selection",
            ),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:03Z",
                step="matching-scoring",
            ),
            _pipeline_event(
                "PIPELINE_STEP_START",
                "2026-10-22T00:00:04Z",
                step="generation",
            ),
            _pipeline_event(
                "PIPELINE_STEP_FAILURE",
                "2026-10-22T00:00:06Z",
                step="generation",
                returncode=1,
            ),
            _pipeline_event(
                "PIPELINE_FAILED",
                "2026-10-22T00:00:06Z",
                status="FAILED",
                failed_step="generation",
            ),
        ]
        progress = _stage_progress_from_events(events, started_at=self.STARTED_AT)
        assert _stage_statuses(progress) == {
            "extract": "done",
            "match": "done",
            "generate": "error",
            "evaluate": "waiting",
        }
        assert progress["stages"][2]["elapsed_seconds"] == 2
        assert progress["current_stage"] is None

    def test_done_event_completes_remaining_stages(self):
        events = [
            _pipeline_event("PIPELINE_START", self.STARTED_AT),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:01Z",
                step="evidence-selection",
            ),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:03Z",
                step="matching-scoring",
            ),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:05Z",
                step="generation",
            ),
            _pipeline_event(
                "PIPELINE_DONE",
                "2026-10-22T00:00:07Z",
                status="DONE",
                exit_code=0,
            ),
        ]
        progress = _stage_progress_from_events(events, started_at=self.STARTED_AT)
        assert all(stage["status"] == "done" for stage in progress["stages"])
        assert progress["current_stage"] is None

    def test_skipped_pipeline_marks_unfinished_stages_skipped(self):
        events = [
            _pipeline_event("PIPELINE_START", self.STARTED_AT),
            _pipeline_event(
                "PIPELINE_STEP_SUCCESS",
                "2026-10-22T00:00:01Z",
                step="evidence-selection",
            ),
            _pipeline_event(
                "PIPELINE_STEP_START",
                "2026-10-22T00:00:02Z",
                step="matching-scoring",
            ),
            _pipeline_event(
                "PIPELINE_STEP_FAILURE",
                "2026-10-22T00:00:03Z",
                step="matching-scoring",
                returncode=2,
            ),
            _pipeline_event(
                "PIPELINE_DONE",
                "2026-10-22T00:00:03Z",
                status="SKIPPED",
                exit_code=2,
                failed_step="matching-scoring",
            ),
        ]
        progress = _stage_progress_from_events(events, started_at=self.STARTED_AT)
        assert _stage_statuses(progress) == {
            "extract": "done",
            "match": "skipped",
            "generate": "skipped",
            "evaluate": "skipped",
        }

    def test_timeout_marks_running_stage_error(self):
        progress = _stage_progress_from_events(
            [], started_at=self.STARTED_AT, final_status="TIMEOUT"
        )
        assert _stage_statuses(progress)["extract"] == "error"
        assert progress["current_stage"] is None

    def test_process_failure_without_events_marks_first_stage_error(self):
        # 管线进程异常退出且没来得及写 run_log 时，不能停在 extract=running。
        progress = _stage_progress_from_events(
            [], started_at=self.STARTED_AT, final_status="FAILED"
        )
        assert _stage_statuses(progress)["extract"] == "error"
        assert progress["current_stage"] is None


def test_pdf_failure_keeps_generated_artifacts_and_reports_reason(tmp_path, monkeypatch):
    from tools.sidecar.handlers import agent
    resume_dir = tmp_path / 'outputs/run-export-failure'
    resume_dir.mkdir(parents=True)
    (resume_dir / 'resume_mr-run-export-failure_A.md').write_text('# 候选简历\n', encoding='utf-8')
    summary = tmp_path / 'outputs/agent_runs/run-export-failure/summary.json'
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({'artifacts': {'resume_dir': str(resume_dir)}}), encoding='utf-8')
    monkeypatch.setattr(agent, '_PROJECT_ROOT', tmp_path)
    with patch.object(agent, 'markdown_to_pdf', side_effect=RuntimeError('PDF_RENDERER_UNAVAILABLE')):
        result = agent._quick_run_result_details('run-export-failure', '', '')
    assert result['resume_pdf'] == ''
    assert result['pdf_export_error'] == 'PDF_RENDERER_UNAVAILABLE'
    assert result['artifacts']['resume_dir'] == str(resume_dir)
    assert result['resume_readiness']['quality_passed'] is False


def test_failed_matching_step_without_report_reports_reason_instead_of_crashing(tmp_path, monkeypatch):
    """匹配阶段（如本地模型超时）失败时报告文件不存在，结果解析应给出失败步骤而不是 KeyError。"""
    from tools.sidecar.handlers import agent
    summary = tmp_path / 'outputs/agent_runs/run-match-failed/summary.json'
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({'status': 'FAILED', 'failed_step': 'matching-scoring',
                                   'artifacts': {'matching': 'matching_reports/mr-run-match-failed.yaml',
                                                 'resume_dir': 'outputs/run-match-failed'}}), encoding='utf-8')
    monkeypatch.setattr(agent, '_PROJECT_ROOT', tmp_path)
    result = agent._quick_run_result_details('run-match-failed', '', 'LLM timeout')
    assert result['failed_step'] == 'matching-scoring'
    assert result['gaps'] == [] and result['gap_tasks'] == []
    assert result['score_total'] is None
    assert result['resume_readiness']['deliverable'] is False


def test_skipped_matching_does_not_claim_a_resume_exists(tmp_path, monkeypatch):
    from tools.sidecar.handlers import agent
    summary=tmp_path/'outputs/agent_runs/skipped/summary.json';summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({'status':'SKIPPED','reason':'matching_excluded','failed_step':'matching-scoring',
        'artifacts':{'resume_dir':'outputs/skipped'}}))
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    result=agent._quick_run_result_details('skipped','','')
    assert result['resume_readiness']['status']=='NOT_GENERATED'
    assert result['resume_readiness']['content_ready'] is False
    assert not result['resume_pdf']
    assert result['resume_readiness']['reasons']==['本次未生成简历']


class TestAgentRunStart:
    def test_guided_batch_records_gate_review_queue_and_blocks_delivery(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            runs_dir = project_root / "outputs" / "agent_runs"
            policy_path = project_root / "policy.yaml"
            (project_root / "tools").mkdir()
            _write_active_profile(project_root / "job_profiles", "jp-guided")
            _write_eligible_evidence(project_root, evidence_id="ec_guided")
            _write_job_lead(project_root, "jl-guided-1")
            _write_job_lead(project_root, "jl-guided-2", company="Beta")
            policy_path.write_text(
                "\n".join(
                    [
                        'llm_provider: "lm_studio"',
                        'llm_model: "local-model"',
                        'llm_base_url: "http://127.0.0.1:1234/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_placeholder: "configured"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._AGENT_RUN_DIR", runs_dir),
                patch(
                    "tools.sidecar.handlers.agent._REVIEW_QUEUE_DIR",
                    project_root / "outputs" / "review_queue",
                ),
                patch(
                    "tools.sidecar.handlers.agent._build_agent_run_id",
                    return_value="ar_guided",
                ),
                patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}, clear=True),
            ):
                result = handle_agent_start(
                    {
                        "meta": {"correlation_id": "corr_agent_guided"},
                        "job_profile_id": "jp-guided",
                        "options": {
                            "execute_guided_batch": True,
                            "preflight_confirmed": True,
                            "confirmed_no_real_submit": True,
                            "max_rounds": 2,
                            "max_candidates": 2,
                            "candidate_ids": ["jl-guided-1", "jl-guided-2"],
                            "evidence_ids": ["ec_guided"],
                        },
                    }
                )
                fetched = handle_agent_get(
                    {
                        "meta": {"correlation_id": "corr_agent_guided_get"},
                        "run_id": "ar_guided",
                    }
                )
                pending = handle_get_pending_review(
                    {
                        "meta": {"correlation_id": "corr_agent_guided_pending"},
                        "run_id": "ar_guided",
                    }
                )

        assert result["status"] == "REVIEW_PENDING"
        assert result["guided_batch"] is True
        assert all(candidate['snapshot_status'] == 'ready' for candidate in pending['candidates'])
        assert fetched["run"]["guided_batch"] is True
        assert fetched["run"]["selected_candidate_ids"] == [
            "jl-guided-1",
            "jl-guided-2",
        ]
        assert fetched["run"]["policy_limits"]["submit_enabled"] is False
        assert fetched["run"]["preflight_confirmation"]["confirmed_no_real_submit"] is True
        assert fetched["run"]["delivery_plan"]["external_submission_attempted"] is False
        assert fetched["run"]["delivery_plan"]["delivery_events"] == 0
        assert fetched["run"]["review_queue"]["pending_count"] == 2
        event_types = [event["event_type"] for event in fetched["events"]]
        assert "GATE" in event_types
        assert "REVIEW" in event_types
        assert "DELIVER" not in event_types
        assert len(fetched["gate_checks"]) >= 1
        assert len(pending["candidates"]) == 2

    def test_guided_batch_requires_preflight_and_submit_disabled(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            runs_dir = project_root / "outputs" / "agent_runs"
            policy_path = project_root / "policy.yaml"
            _write_active_profile(project_root / "job_profiles", "jp-guided")
            _write_eligible_evidence(project_root, evidence_id="ec_guided")
            _write_job_lead(project_root, "jl-guided-1")
            policy_path.write_text(
                "\n".join(
                    [
                        'llm_provider: "lm_studio"',
                        'llm_model: "local-model"',
                        'llm_base_url: "http://127.0.0.1:1234/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_placeholder: "configured"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._AGENT_RUN_DIR", runs_dir),
                patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}, clear=True),
            ):
                try:
                    handle_agent_start(
                        {
                            "meta": {"correlation_id": "corr_agent_no_confirm"},
                            "job_profile_id": "jp-guided",
                            "options": {"execute_guided_batch": True},
                        }
                    )
                    no_confirm_rejected = False
                except ValueError as exc:
                    no_confirm_rejected = "preflight_confirmation_required" in str(exc)
                try:
                    handle_agent_start(
                        {
                            "meta": {"correlation_id": "corr_agent_submit"},
                            "job_profile_id": "jp-guided",
                            "options": {
                                "execute_guided_batch": True,
                                "preflight_confirmed": True,
                                "confirmed_no_real_submit": True,
                                "submit_enabled": True,
                            },
                        }
                    )
                    submit_rejected = False
                except ValueError as exc:
                    submit_rejected = "submit_enable_blocked_for_case" in str(exc)

        assert no_confirm_rejected is True
        assert submit_rejected is True

    def test_agent_run_records_masked_persisted_llm_config_summary(self):
        with TemporaryDirectory() as project_tmp:
            project_root = Path(project_tmp)
            runs_dir = project_root / "outputs" / "agent_runs"
            policy_path = project_root / "policy.yaml"
            policy_path.write_text(
                "\n".join(
                    [
                        'llm_provider: "lm_studio"',
                        'llm_model: "agent-local-model"',
                        'llm_base_url: "http://127.0.0.1:1234/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_updated_at: "2026-05-21T00:00:00Z"',
                        'llm_api_key_placeholder: "configured"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch("tools.sidecar.handlers.agent._AGENT_RUN_DIR", runs_dir),
                patch(
                    "tools.sidecar.handlers.agent._build_agent_run_id",
                    return_value="ar_llm",
                ),
                patch.dict(
                    os.environ,
                    {"PPF_POLICY_PATH": str(policy_path)},
                    clear=True,
                ),
            ):
                start = handle_agent_start(
                    {
                        "meta": {"correlation_id": "corr_agent_llm"},
                        "job_profile_id": "jp-001",
                        "options": {"max_rounds": 1},
                    }
                )
                fetched = handle_agent_get(
                    {
                        "meta": {"correlation_id": "corr_agent_llm_get"},
                        "run_id": "ar_llm",
                    }
                )

            summary = start["llm_config_summary"]
            assert summary["provider"] == "lm_studio"
            assert summary["model"] == "agent-local-model"
            assert summary["base_url"] == "http://127.0.0.1:1234/v1"
            assert summary["api_key"]["configured"] is True
            assert summary["api_key"]["masked"] is True
            assert "value" not in summary["api_key"]
            assert "secret" not in summary["api_key"]
            assert fetched["run"]["llm_config_summary"] == summary


def test_persisted_llm_runtime_context_propagates_thinking_mode() -> None:
    config = {
        "provider": "deepseek",
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com",
        "api_key_configured": True,
        "api_key_updated_at": "2026-10-20T00:00:00Z",
        "api_key_for_request": "sk-test",
        "thinking_enabled": True,
        "thinking_effort": "max",
        "timeout": 60,
        "temperature": 0.2,
    }
    with patch(
        "tools.sidecar.handlers.settings._load_llm_config",
        return_value=config,
    ):
        summary, env = _persisted_llm_runtime_context()

    assert summary["thinking_enabled"] is True
    assert summary["thinking_effort"] == "max"
    assert env["LLM_THINKING"] == "on"
    assert env["LLM_THINKING_EFFORT"] == "max"
    assert env["LLM_PROVIDER"] == "deepseek"
    assert env["LLM_API_KEY"] == "sk-test"


def test_persisted_llm_runtime_context_keeps_keyless_strata_keyless() -> None:
    # keyless Strata 不注入伪 placeholder Key：请求头保持无 Authorization。
    config = {
        "provider": "strata",
        "model": "qwen3.8-flash-next-q2_0",
        "base_url": "http://127.0.0.1:8081/v1",
        "api_key_configured": False,
        "api_key_updated_at": "",
        "api_key_for_request": "",
        "thinking_enabled": False,
        "thinking_effort": "high",
        "timeout": 60,
        "temperature": 0.2,
    }
    with patch(
        "tools.sidecar.handlers.settings._load_llm_config",
        return_value=config,
    ):
        summary, env = _persisted_llm_runtime_context()

    assert summary["provider"] == "strata"
    assert summary["api_key"]["configured"] is False
    assert "LLM_API_KEY" not in env
    assert env["LLM_PROVIDER"] == "strata"
    assert env["LLM_MODEL"] == "qwen3.8-flash-next-q2_0"
