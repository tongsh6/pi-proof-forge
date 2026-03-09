import unittest

from tools.sidecar.handlers.agent import (
    handle_get_pending_review,
    handle_submit_review,
)


class GetPendingReviewTests(unittest.TestCase):
    def test_returns_candidates_key(self) -> None:
        params = {"meta": {"correlation_id": "c1"}}
        result = handle_get_pending_review(params)
        self.assertIn("candidates", result)
        self.assertEqual(result["candidates"], [])

    def test_stub_returns_empty_list(self) -> None:
        params = {"meta": {"correlation_id": "c2"}}
        result = handle_get_pending_review(params)
        self.assertIsInstance(result["candidates"], list)
        self.assertEqual(len(result["candidates"]), 0)


class SubmitReviewTests(unittest.TestCase):
    def test_returns_accepted_key(self) -> None:
        params = {"meta": {"correlation_id": "c3"}, "decisions": []}
        result = handle_submit_review(params)
        self.assertIn("accepted", result)
        self.assertEqual(result["accepted"], 0)

    def test_stub_accepts_any_payload(self) -> None:
        params = {"meta": {"correlation_id": "c4"}, "decisions": [{"job_lead_id": "jl-1", "action": "approve"}]}
        result = handle_submit_review(params)
        self.assertEqual(result["accepted"], 0)
