import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tools.sidecar.handlers.settings import (
    handle_settings_check_llm_connection,
    handle_settings_get,
    handle_settings_update,
)


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

    def test_channels_include_runtime_status_fields(self) -> None:
        params = {"meta": {"correlation_id": "corr_channels"}}
        result = handle_settings_get(params)
        channels = result["channels"]
        self.assertEqual([channel["id"] for channel in channels], ["liepin", "email"])
        for channel in channels:
            self.assertIn("label", channel)
            self.assertIn("enabled", channel)
            self.assertIn("priority", channel)
            self.assertIn("fallback_to", channel)
            self.assertIn("credential_status", channel)
            self.assertIn("last_check_status", channel)
            self.assertIn("last_success_at", channel)
            self.assertIn("last_error", channel)

    def test_channel_credential_status_uses_environment(self) -> None:
        params = {"meta": {"correlation_id": "corr_channels_env"}}
        with patch.dict(
            os.environ,
            {
                "PPF_LIEPIN_SESSION_DIR": "/tmp/ppf-liepin-session",
                "SMTP_USER": "bot@example.com",
                "SMTP_PASS": "secret",
            },
        ):
            result = handle_settings_get(params)
        statuses = {
            channel["id"]: channel["credential_status"]
            for channel in result["channels"]
        }
        self.assertEqual(statuses, {"liepin": "configured", "email": "configured"})

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

    def test_auto_delivery_forces_batch_review_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                'delivery_mode: "auto"\nbatch_review: "true"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                result = handle_settings_get(
                    {"meta": {"correlation_id": "corr_auto_batch"}}
                )
        self.assertEqual(result["gate_policy"]["delivery_mode"], "auto")
        self.assertFalse(result["gate_policy"]["batch_review"])


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

    def test_update_auto_delivery_persists_batch_review_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            params = {
                "meta": {"correlation_id": "corr_dm_auto"},
                "section": "gate_policy",
                "payload": {"delivery_mode": "auto", "batch_review": True},
            }
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                result = handle_settings_update(params)
                self.assertTrue(result["saved"])
                stored = handle_settings_get(
                    {"meta": {"correlation_id": "corr_dm_auto2"}}
                )
        self.assertEqual(stored["gate_policy"]["delivery_mode"], "auto")
        self.assertFalse(stored["gate_policy"]["batch_review"])

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

    def test_update_llm_config_persists_masked_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            params = {
                "meta": {"correlation_id": "corr_llm"},
                "section": "llm_config",
                "payload": {
                    "provider": "lm_studio",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "api_key": "lm-studio",
                    "model": "local-model",
                    "timeout": 3,
                    "temperature": 0.1,
                },
            }
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}, clear=True):
                result = handle_settings_update(params)
                stored = handle_settings_get({"meta": {"correlation_id": "corr_llm2"}})

        self.assertTrue(result["saved"])
        llm = stored["llm_config"]
        self.assertEqual(llm["provider"], "lm_studio")
        self.assertEqual(llm["base_url"], "http://127.0.0.1:1234/v1")
        self.assertEqual(llm["model"], "local-model")
        self.assertEqual(llm["timeout"], 3)
        self.assertEqual(llm["temperature"], 0.1)
        self.assertTrue(llm["api_key"]["configured"])
        self.assertTrue(llm["api_key"]["masked"])
        self.assertNotIn("value", llm["api_key"])
        self.assertNotIn("secret", llm["api_key"])
        self.assertNotIn("lm-studio", str(stored))

    def test_update_llm_config_rejects_unsupported_fields(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_llm_bad"},
            "section": "llm_config",
            "payload": {"provider": "lm_studio", "extra": "x"},
        }
        with self.assertRaises(ValueError):
            _ = handle_settings_update(params)


class SettingsCheckLlmConnectionTests(unittest.TestCase):
    def test_check_llm_connection_returns_pass_with_models(self) -> None:
        with patch(
            "tools.sidecar.handlers.settings.LLMClient.list_models",
            return_value=["local-model"],
        ):
            result = handle_settings_check_llm_connection(
                {
                    "meta": {"correlation_id": "corr_check"},
                    "payload": {
                        "base_url": "http://127.0.0.1:1234/v1",
                        "api_key": "lm-studio",
                        "timeout": 1,
                    },
                }
            )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["code"], "OK")
        self.assertEqual(result["model_count"], 1)
        self.assertEqual(result["models"], ["local-model"])

    def test_check_llm_connection_returns_structured_blocked_on_unavailable(self) -> None:
        with patch(
            "tools.sidecar.handlers.settings.LLMClient.list_models",
            side_effect=OSError("connection refused"),
        ):
            result = handle_settings_check_llm_connection(
                {
                    "meta": {"correlation_id": "corr_blocked"},
                    "payload": {
                        "base_url": "http://127.0.0.1:1234/v1",
                        "api_key": "lm-studio",
                        "timeout": 1,
                    },
                }
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BLOCKED_LOCAL_PROVIDER")
        self.assertIn("http://127.0.0.1:1234/v1/models", result["message"])


if __name__ == "__main__":
    unittest.main()
