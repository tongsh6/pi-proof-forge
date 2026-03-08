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


if __name__ == "__main__":
    unittest.main()
