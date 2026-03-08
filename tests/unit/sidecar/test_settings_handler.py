import unittest
from typing import Any
from unittest.mock import patch

from tools.sidecar.handlers.settings import handle_settings_get


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


if __name__ == "__main__":
    unittest.main()
