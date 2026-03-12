"""Tests for agent run / REVIEW handlers."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.agent import (
    handle_create_review_candidates,
    handle_get_pending_review,
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
