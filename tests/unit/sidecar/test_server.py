import json
import unittest
from typing import Any

from tools.sidecar.server import process_request, build_success_response, build_error_response


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
