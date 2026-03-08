import unittest
from pathlib import Path
from unittest.mock import patch
from typing import Any

from tools.sidecar.handlers.evidence import handle_evidence_list, handle_evidence_get


SAMPLE_YAML = """\
id: "ec-2026-001"
title: "Order stability"
time_range: "2025-10 ~ 2026-01"
context: "Peak 5k QPS"
role_scope: "Owner"
actions:
  - "Refactored circuit breaker"
results:
  - "Failure rate dropped 43%"
stack:
  - "Java"
  - "Redis"
artifacts:
  - "postmortem.pdf"
tags:
  - "stability"
"""


class EvidenceListTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.evidence._load_evidence_cards")
    def test_list_returns_items_with_contract_fields(self, mock_load: Any) -> None:
        mock_load.return_value = [
            {
                "evidence_id": "ec-2026-001",
                "title": "Order stability",
                "time_range": "2025-10 ~ 2026-01",
                "role_scope": "Owner",
                "score": 0,
                "status": "ready",
                "updated_at": "2026-03-07T10:00:00Z",
            }
        ]
        params = {
            "meta": {"correlation_id": "corr_001"},
            "cursor": None,
            "page_size": 20,
            "sort": {"field": "updated_at", "order": "desc"},
            "filters": {},
        }
        result = handle_evidence_list(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertIn("items", result)
        self.assertIn("next_cursor", result)
        item = result["items"][0]
        self.assertEqual(item["evidence_id"], "ec-2026-001")
        self.assertIn("title", item)
        self.assertIn("time_range", item)
        self.assertIn("role_scope", item)
        self.assertIn("status", item)
        self.assertIn("updated_at", item)

    @patch("tools.sidecar.handlers.evidence._load_evidence_cards")
    def test_list_respects_page_size(self, mock_load: Any) -> None:
        mock_load.return_value = [
            {"evidence_id": f"ec-{i}", "title": f"Card {i}", "time_range": "", "role_scope": "", "score": 0, "status": "ready", "updated_at": ""}
            for i in range(5)
        ]
        params = {
            "meta": {"correlation_id": "corr_002"},
            "cursor": None,
            "page_size": 2,
            "sort": {"field": "updated_at", "order": "desc"},
            "filters": {},
        }
        result = handle_evidence_list(params)
        self.assertEqual(len(result["items"]), 2)
        self.assertIsNotNone(result["next_cursor"])


class EvidenceGetTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.evidence._load_evidence_detail")
    def test_get_returns_full_evidence(self, mock_load: Any) -> None:
        mock_load.return_value = {
            "evidence_id": "ec-2026-001",
            "title": "Order stability",
            "time_range": "2025-10 ~ 2026-01",
            "context": "Peak 5k QPS",
            "role_scope": "Owner",
            "actions": "Refactored circuit breaker",
            "results": "Failure rate dropped 43%",
            "stack": ["Java", "Redis"],
            "tags": ["stability"],
            "artifacts": [],
        }
        params = {
            "meta": {"correlation_id": "corr_003"},
            "evidence_id": "ec-2026-001",
        }
        result = handle_evidence_get(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_003")
        evidence = result["evidence"]
        self.assertEqual(evidence["evidence_id"], "ec-2026-001")
        self.assertIn("title", evidence)
        self.assertIn("context", evidence)
        self.assertIn("stack", evidence)
        self.assertIn("artifacts", evidence)

    @patch("tools.sidecar.handlers.evidence._load_evidence_detail")
    def test_get_not_found_raises(self, mock_load: Any) -> None:
        mock_load.return_value = None
        params = {
            "meta": {"correlation_id": "corr_004"},
            "evidence_id": "ec-nonexistent",
        }
        with self.assertRaises(KeyError):
            handle_evidence_get(params)


if __name__ == "__main__":
    unittest.main()
