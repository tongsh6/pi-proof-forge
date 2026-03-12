import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tools.sidecar.handlers.settings import handle_settings_get, handle_settings_update


class SettingsGetTests(unittest.TestCase):
    def test_returns_all_sections(self) -> None:
        params = {"meta": {"correlation_id": "corr_001"}}
        result = handle_settings_get(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertIn("gate_policy", result)
        self.assertIn("exclusion_list", result)
        self.assertIn("excluded_legal_entities", result)
        self.assertIn("channels", result)
        self.assertIn("llm_config", result)

    def test_gate_policy_has_required_fields(self) -> None:
        params = {"meta": {"correlation_id": "corr_002"}}
        result = handle_settings_get(params)
        gp = result["gate_policy"]
        self.assertIn("n_pass_required", gp)
        self.assertIn("matching_threshold", gp)
        self.assertIn("evaluation_threshold", gp)
        self.assertIn("max_rounds", gp)
        self.assertIn("gate_mode", gp)

    def test_delivery_mode_and_batch_review_present(self) -> None:
        params = {"meta": {"correlation_id": "corr_dm"}}
        result = handle_settings_get(params)
        gp = result["gate_policy"]
        self.assertIn("delivery_mode", gp)
        self.assertIn("batch_review", gp)
        self.assertIn(gp["delivery_mode"], ("auto", "manual"))
        self.assertIsInstance(gp["batch_review"], bool)

    def test_llm_config_has_secret_status(self) -> None:
        params = {"meta": {"correlation_id": "corr_003"}}
        result = handle_settings_get(params)
        llm = result["llm_config"]
        self.assertIn("api_key", llm)
        api_key = llm["api_key"]
        self.assertIn("configured", api_key)
        self.assertIn("masked", api_key)
        self.assertIn("updated_at", api_key)

    def test_api_key_never_has_plaintext(self) -> None:
        params = {"meta": {"correlation_id": "corr_004"}}
        result = handle_settings_get(params)
        api_key = result["llm_config"]["api_key"]
        self.assertNotIn("value", api_key)
        self.assertNotIn("secret", api_key)

    def test_llm_config_has_provider_fields(self) -> None:
        params = {"meta": {"correlation_id": "corr_005"}}
        result = handle_settings_get(params)
        llm = result["llm_config"]
        self.assertIn("provider", llm)
        self.assertIn("model", llm)
        self.assertIn("timeout", llm)
        self.assertIn("temperature", llm)

    def test_exclusion_list_loads_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                "exclusion_list:\n  - 'Acme Inc'\n  - 'contains:Outsource'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                params = {"meta": {"correlation_id": "corr_006"}}
                result = handle_settings_get(params)
        self.assertEqual(result["exclusion_list"], ["Acme Inc", "contains:Outsource"])

    def test_legal_entities_load_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                "excluded_legal_entities:\n  - 'Acme Holdings Ltd'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                params = {"meta": {"correlation_id": "corr_006a"}}
                result = handle_settings_get(params)
        self.assertEqual(result["excluded_legal_entities"], ["Acme Holdings Ltd"])

    def test_delivery_settings_load_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                'delivery_mode: "manual"\nbatch_review: "true"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                params = {"meta": {"correlation_id": "corr_dm_load"}}
                result = handle_settings_get(params)
        self.assertEqual(result["gate_policy"]["delivery_mode"], "manual")
        self.assertTrue(result["gate_policy"]["batch_review"])


class SettingsUpdateTests(unittest.TestCase):
    def test_update_exclusion_list_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            payload = ["Acme Inc", "contains:Outsource"]
            params = {
                "meta": {"correlation_id": "corr_007"},
                "section": "exclusion_list",
                "payload": payload,
            }
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                result = handle_settings_update(params)
                self.assertTrue(result["saved"])
                get_params = {"meta": {"correlation_id": "corr_008"}}
                stored = handle_settings_get(get_params)
        self.assertEqual(stored["exclusion_list"], payload)

    def test_update_rejects_invalid_payload(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_009"},
            "section": "exclusion_list",
            "payload": "Acme Inc",
        }
        with self.assertRaises(ValueError):
            _ = handle_settings_update(params)

    def test_update_rejects_non_string_entries(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_010"},
            "section": "exclusion_list",
            "payload": ["Acme Inc", 42],
        }
        with self.assertRaises(ValueError):
            _ = handle_settings_update(params)

    def test_update_legal_entities_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            payload = ["Acme Holdings Ltd"]
            params = {
                "meta": {"correlation_id": "corr_011"},
                "section": "excluded_legal_entities",
                "payload": payload,
            }
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                result = handle_settings_update(params)
                self.assertTrue(result["saved"])
                stored = handle_settings_get({"meta": {"correlation_id": "corr_012"}})
        self.assertEqual(stored["excluded_legal_entities"], payload)

    def test_update_delivery_settings_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            params = {
                "meta": {"correlation_id": "corr_dm"},
                "section": "gate_policy",
                "payload": {"delivery_mode": "manual", "batch_review": True},
            }
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                result = handle_settings_update(params)
                self.assertTrue(result["saved"])
                stored = handle_settings_get({"meta": {"correlation_id": "corr_dm2"}})
        self.assertEqual(stored["gate_policy"]["delivery_mode"], "manual")
        self.assertTrue(stored["gate_policy"]["batch_review"])

    def test_update_gate_policy_rejects_unsupported_fields(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_gp_bad"},
            "section": "gate_policy",
            "payload": {"matching_threshold": 80},
        }
        with self.assertRaises(ValueError):
            _ = handle_settings_update(params)

    def test_update_gate_policy_rejects_invalid_delivery_mode(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_gp_mode_bad"},
            "section": "gate_policy",
            "payload": {"delivery_mode": "later"},
        }
        with self.assertRaises(ValueError):
            _ = handle_settings_update(params)

    def test_update_gate_policy_rejects_non_boolean_batch_review(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_gp_batch_bad"},
            "section": "gate_policy",
            "payload": {"batch_review": "false"},
        }
        with self.assertRaises(ValueError):
            _ = handle_settings_update(params)


if __name__ == "__main__":
    unittest.main()
