import json
import subprocess
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

    def test_submission_detail_method_returns_success(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": "req_007",
            "method": "submission.detail",
            "params": {
                "meta": {"correlation_id": "corr_007"},
                "submission_id": "run-001",
            },
        }
        with TemporaryDirectory() as tmp_dir:
            submissions_dir = Path(tmp_dir) / "submissions"
            run_dir = submissions_dir / "liepin" / "run-001"
            run_dir.mkdir(parents=True)
            (run_dir / "submission_log.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-001",
                        "platform": "liepin",
                        "status": "success",
                        "steps": [],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir
            ):
                response = process_request(request)

        self.assertIn("result", response)
        self.assertEqual(response["result"]["submission"]["submission_id"], "run-001")

    def test_run_agent_start_get_stop_methods_return_persisted_state(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            runs_dir = Path(tmp_dir) / "agent_runs"
            with patch("tools.sidecar.handlers.agent._AGENT_RUN_DIR", runs_dir, create=True):
                start_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_agent_start",
                        "method": "run.agent.start",
                        "params": {
                            "meta": {"correlation_id": "corr_agent"},
                            "job_profile_id": "jp-001",
                            "options": {"max_rounds": 2},
                        },
                    }
                )

                self.assertIn("result", start_response)
                start_result = start_response["result"]
                self.assertEqual(start_result["meta"]["correlation_id"], "corr_agent")
                self.assertEqual(start_result["status"], "queued")
                self.assertTrue(start_result["run_id"].startswith("ar_"))

                get_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_agent_get",
                        "method": "run.agent.get",
                        "params": {
                            "meta": {"correlation_id": "corr_agent_get"},
                            "run_id": start_result["run_id"],
                            "event_cursor": None,
                            "event_limit": 50,
                        },
                    }
                )

                self.assertIn("result", get_response)
                run_payload = get_response["result"]["run"]
                self.assertEqual(run_payload["run_id"], start_result["run_id"])
                self.assertEqual(run_payload["status"], "queued")
                self.assertEqual(run_payload["job_profile_id"], "jp-001")
                self.assertEqual(get_response["result"]["gate_checks"], [])
                self.assertEqual(get_response["result"]["events"], [])

                stop_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_agent_stop",
                        "method": "run.agent.stop",
                        "params": {
                            "meta": {"correlation_id": "corr_agent_stop"},
                            "run_id": start_result["run_id"],
                        },
                    }
                )

                self.assertIn("result", stop_response)
                self.assertTrue(stop_response["result"]["accepted"])

                stopped_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_agent_get_stopped",
                        "method": "run.agent.get",
                        "params": {
                            "meta": {"correlation_id": "corr_agent_stopped"},
                            "run_id": start_result["run_id"],
                            "event_cursor": None,
                            "event_limit": 50,
                        },
                    }
                )

                self.assertEqual(stopped_response["result"]["run"]["status"], "stopped")

    def test_run_agent_start_can_execute_local_dry_run(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            runs_dir = Path(tmp_dir) / "agent_runs"
            with patch("tools.sidecar.handlers.agent._AGENT_RUN_DIR", runs_dir, create=True):
                start_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_agent_dry_run",
                        "method": "run.agent.start",
                        "params": {
                            "meta": {"correlation_id": "corr_agent_dry"},
                            "job_profile_id": "jp-001",
                            "options": {
                                "max_rounds": 3,
                                "execute_dry_run": True,
                            },
                        },
                    }
                )

                self.assertIn("result", start_response)
                start_result = start_response["result"]
                self.assertEqual(start_result["status"], "DRY_RUN_COMPLETE")

                get_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_agent_dry_run_get",
                        "method": "run.agent.get",
                        "params": {
                            "meta": {"correlation_id": "corr_agent_dry_get"},
                            "run_id": start_result["run_id"],
                            "event_cursor": None,
                            "event_limit": 50,
                        },
                    }
                )

                self.assertIn("result", get_response)
                run_payload = get_response["result"]["run"]
                self.assertEqual(run_payload["status"], "DRY_RUN_COMPLETE")
                self.assertEqual(run_payload["round"], 1)
                event_types = [
                    event["event_type"] for event in get_response["result"]["events"]
                ]
                self.assertEqual(event_types, ["INIT", "DISCOVER", "DONE"])

    def test_run_quick_start_and_cancel_methods_are_registered(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            quick_runs_dir = Path(tmp_dir) / "quick_runs"
            raw_path = Path(tmp_dir) / "sample_raw.txt"
            profile_dir = Path(tmp_dir) / "job_profiles"
            profile_path = profile_dir / "jp-001.yaml"
            raw_path.write_text("raw", encoding="utf-8")
            profile_dir.mkdir()
            profile_path.write_text("target_role: Backend\n", encoding="utf-8")

            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="[pipeline] done\n",
                stderr="",
            )
            with (
                patch(
                    "tools.sidecar.handlers.agent._QUICK_RUN_DIR",
                    quick_runs_dir,
                    create=True,
                ),
                patch(
                    "tools.sidecar.handlers.agent.subprocess.run",
                    return_value=completed,
                ) as run_mock,
            ):
                start_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_quick_start",
                        "method": "run.quick.start",
                        "params": {
                            "meta": {"correlation_id": "corr_quick"},
                            "job_profile_id": "jp-001",
                            "options": {
                                "raw_path": str(raw_path),
                                "job_profile_path": str(profile_path),
                            },
                        },
                    }
                )

                self.assertIn("result", start_response)
                start_result = start_response["result"]
                self.assertEqual(start_result["meta"]["correlation_id"], "corr_quick")
                self.assertEqual(start_result["status"], "DONE")
                self.assertTrue(start_result["run_id"].startswith("qr_"))
                self.assertIn("run_record", start_result)
                command = run_mock.call_args.args[0]
                self.assertIn("tools/run_pipeline.py", command)
                self.assertIn(str(profile_path), command)

                cancel_response = process_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req_quick_cancel",
                        "method": "run.quick.cancel",
                        "params": {
                            "meta": {"correlation_id": "corr_quick_cancel"},
                            "run_id": start_result["run_id"],
                        },
                    }
                )

                self.assertIn("result", cancel_response)
                self.assertTrue(cancel_response["result"]["accepted"])


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
