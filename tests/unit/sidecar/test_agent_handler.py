"""Tests for agent run / REVIEW handlers."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.agent import (
    handle_create_review_candidates,
    handle_get_pending_review,
    handle_quick_start,
    handle_submit_review,
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
    def test_approves_candidates(self):
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
                result = handle_submit_review(
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

        assert result["accepted"] == 1
        assert updated["candidates"][0]["status"] == "approved"


class TestQuickRunStart:
    def test_resolves_default_paths_from_project_root_when_cwd_differs(self):
        with TemporaryDirectory() as project_tmp, TemporaryDirectory() as cwd_tmp:
            project_root = Path(project_tmp)
            quick_dir = project_root / "outputs" / "quick_runs"
            tools_dir = project_root / "tools"
            profile_dir = project_root / "job_profiles"
            tools_dir.mkdir()
            profile_dir.mkdir()
            (tools_dir / "sample_raw.txt").write_text("raw", encoding="utf-8")
            (profile_dir / "jp-001.yaml").write_text(
                "target_role: Backend\n", encoding="utf-8"
            )

            completed = type(
                "Completed",
                (),
                {"returncode": 0, "stdout": "[pipeline] done\n", "stderr": ""},
            )()

            cwd = Path.cwd()
            with (
                patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
                patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
                patch(
                    "tools.sidecar.handlers.agent.subprocess.run",
                    return_value=completed,
                ) as run_mock,
            ):
                try:
                    os.chdir(cwd_tmp)
                    result = handle_quick_start(
                        {
                            "meta": {"correlation_id": "corr_quick_root"},
                            "job_profile_id": "jp-001",
                        }
                    )
                finally:
                    os.chdir(cwd)

        assert result["status"] == "DONE"
        command = run_mock.call_args.args[0]
        assert command[1] == str(project_root / "tools" / "run_pipeline.py")
        assert run_mock.call_args.kwargs["cwd"] == str(project_root)
