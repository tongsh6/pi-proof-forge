import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from tools.sidecar.server import (
    process_request,
    build_success_response,
    build_error_response,
)


class ProcessRequestTests(unittest.TestCase):
    def test_valid_request_returns_success(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_001",
            "method": "system.ping",
            "params": {"meta": {"correlation_id": "corr_001"}},
        }
        response = process_request(request)
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], "req_001")
        self.assertIn("result", response)
        self.assertEqual(response["result"]["meta"]["correlation_id"], "corr_001")

    def test_unknown_method_returns_error(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_002",
            "method": "nonexistent.method",
            "params": {"meta": {"correlation_id": "corr_002"}},
        }
        response = process_request(request)
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], "req_002")
        self.assertIn("error", response)
        self.assertNotIn("result", response)

    def test_missing_correlation_id_returns_validation_error(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_003",
            "method": "system.ping",
            "params": {},
        }
        response = process_request(request)
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")

    def test_missing_params_returns_validation_error(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_004",
            "method": "system.ping",
        }
        response = process_request(request)
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")

    def test_evidence_delete_conflict_returns_conflict_error(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_005",
            "method": "evidence.delete",
            "params": {
                "meta": {"correlation_id": "corr_005"},
                "evidence_id": "ec-2026-001",
            },
        }
        sample_yaml = 'id: "ec-2026-001"\ntitle: "x"\n'
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            (evidence_dir / "ec_001.yaml").write_text(sample_yaml, encoding="utf-8")
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                with patch(
                    "tools.sidecar.handlers.evidence._is_evidence_referenced_by_active_run",
                    return_value=True,
                ):
                    response = process_request(request)

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], "CONFLICT")

    def test_jobs_delete_profile_conflict_returns_conflict_error(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_006",
            "method": "jobs.deleteProfile",
            "params": {
                "meta": {"correlation_id": "corr_006"},
                "job_profile_id": "jp-001",
            },
        }
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
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
                response = process_request(request)

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], "CONFLICT")


class BuildResponseTests(unittest.TestCase):
    def test_build_success_response(self) -> None:
        resp = build_success_response("req_100", {"data": "hello"})
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], "req_100")
        self.assertEqual(resp["result"]["data"], "hello")
        self.assertNotIn("error", resp)

    def test_build_error_response(self) -> None:
        resp = build_error_response("req_101", "TIMEOUT", "timed out", "corr_x")
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], "req_101")
        self.assertNotIn("result", resp)
        self.assertEqual(resp["error"]["code"], "TIMEOUT")
        self.assertEqual(resp["error"]["details"]["correlation_id"], "corr_x")


if __name__ == "__main__":
    unittest.main()
