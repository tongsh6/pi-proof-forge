import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tools.infra.llm_credentials import LLMApiKeyStore
from tools.sidecar.handlers.settings import (
    _load_llm_config,
    handle_settings_check_llm_connection,
    handle_settings_clear_llm_api_key,
    handle_settings_get,
    handle_settings_update,
)



class SettingsGetTests(unittest.TestCase):
    def test_channels_do_not_advertise_automatic_cross_platform_fallback(self) -> None:
        result = handle_settings_get({"meta": {"correlation_id": "routing-contract"}})
        liepin = next(channel for channel in result["channels"] if channel["id"] == "liepin")
        self.assertEqual(liepin["fallback_to"], "")

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

    def test_update_prefers_existing_local_policy_file_in_cwd(self) -> None:
        # 未设置环境变量时，存在 policy.local.yaml 就读写它，仓库默认 policy.yaml 不被改动。
        with tempfile.TemporaryDirectory() as tmp_dir, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PPF_POLICY_PATH", None)
            root = Path(tmp_dir)
            repo_policy = root / "policy.yaml"
            local_policy = root / "policy.local.yaml"
            repo_policy.write_text('delivery_mode: "auto"\nbatch_review: "false"\n', encoding="utf-8")
            local_policy.write_text('delivery_mode: "auto"\nbatch_review: "false"\nllm_model: "local-model"\n', encoding="utf-8")
            previous = os.getcwd()
            os.chdir(root)
            try:
                handle_settings_update({"meta": {"correlation_id": "corr_local"}, "section": "gate_policy",
                                        "payload": {"delivery_mode": "manual", "batch_review": True}})
                result = handle_settings_get({"meta": {"correlation_id": "corr_local_get"}})
            finally:
                os.chdir(previous)
            self.assertEqual(repo_policy.read_text(encoding="utf-8"), 'delivery_mode: "auto"\nbatch_review: "false"\n')
            local_text = local_policy.read_text(encoding="utf-8")
            self.assertIn('delivery_mode: "manual"', local_text)
            self.assertIn('llm_model: "local-model"', local_text)
        self.assertEqual(result["gate_policy"]["delivery_mode"], "manual")

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


class SettingsLlmCredentialTests(unittest.TestCase):
    def _policy(self, tmp: str) -> Path:
        return Path(tmp) / "policy.yaml"

    def _update(self, payload: dict[str, Any]) -> dict[str, Any]:
        return handle_settings_update(
            {
                "meta": {"correlation_id": "corr_llm_credentials"},
                "section": "llm_config",
                "payload": payload,
            }
        )

    def _get(self) -> dict[str, Any]:
        return handle_settings_get({"meta": {"correlation_id": "corr_llm_get"}})

    def test_deepseek_key_is_saved_to_provider_file_and_never_returned(self) -> None:
        key = "sk-deepseek-test-only"
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                result = self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": key,
                        "thinking_enabled": True,
                        "thinking_effort": "max",
                    }
                )
                stored = self._get()
                loaded = _load_llm_config()

            from tools.infra.llm_credentials import LLMApiKeyStore
            store = LLMApiKeyStore()
            saved_path = store.path_for("deepseek")

            self.assertTrue(result["saved"])
            self.assertEqual(store.load("deepseek"), key)
            self.assertEqual(saved_path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(key, policy.read_text(encoding="utf-8"))
            self.assertNotIn(key, str(stored))
            self.assertNotIn(key, repr(stored["llm_config"]))
            self.assertEqual(stored["llm_config"]["provider"], "deepseek")
            self.assertEqual(stored["llm_config"]["model"], "deepseek-flash")
            self.assertTrue(stored["llm_config"]["api_key"]["configured"])
            self.assertEqual(stored["llm_config"]["api_key"]["source"], "saved")
            self.assertEqual(stored["llm_config"]["configured_providers"], ["deepseek"])
            self.assertTrue(stored["llm_config"]["thinking_enabled"])
            self.assertEqual(stored["llm_config"]["thinking_effort"], "max")
            self.assertEqual(loaded["api_key_for_request"], key)

    def test_provider_keys_are_isolated_and_survive_switching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update({"provider": "openai", "model": "gpt-4", "api_key": "sk-openai"})
                self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-deepseek",
                    }
                )
                deepseek = self._get()
                self._update({"provider": "openai"})
                openai = self._get()
                self._update({"provider": "deepseek"})
                back = self._get()

            self.assertEqual(deepseek["llm_config"]["configured_providers"], ["deepseek", "openai"])
            self.assertTrue(openai["llm_config"]["api_key"]["configured"])
            self.assertEqual(openai["llm_config"]["api_key"]["source"], "saved")
            self.assertTrue(back["llm_config"]["api_key"]["configured"])
            self.assertEqual(back["llm_config"]["api_key"]["source"], "saved")
            self.assertNotEqual(openai["llm_config"]["api_key"]["updated_at"], "")

    def test_clear_llm_api_key_only_removes_selected_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update({"provider": "openai", "model": "gpt-4", "api_key": "sk-openai"})
                self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-deepseek",
                    }
                )
                cleared = handle_settings_clear_llm_api_key(
                    {
                        "meta": {"correlation_id": "corr_clear"},
                        "provider": "deepseek",
                    }
                )
                stored = self._get()

            self.assertTrue(cleared["cleared"])
            self.assertNotIn("deepseek", cleared["configured_providers"])
            self.assertIn("openai", cleared["configured_providers"])
            self.assertEqual(stored["llm_config"]["provider"], "deepseek")
            self.assertEqual(stored["llm_config"]["model"], "deepseek-flash")
            self.assertFalse(stored["llm_config"]["api_key"]["configured"])
            self.assertEqual(stored["llm_config"]["api_key"]["source"], "none")

    def test_check_connection_blocks_deepseek_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                    }
                )
                result = handle_settings_check_llm_connection(
                    {
                        "meta": {"correlation_id": "corr_check_deepseek"},
                        "payload": {"provider": "deepseek", "timeout": 1},
                    }
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BLOCKED_PROVIDER_CREDENTIAL")
        self.assertIn("DeepSeek", result["message"])
        self.assertNotIn("LM Studio", result["message"])

    def test_check_connection_uses_saved_provider_key(self) -> None:
        key = "sk-deepseek-test-only"
        captured: list[dict[str, Any]] = []

        class FakeClient:
            def __init__(self, **kwargs: Any) -> None:
                captured.append(kwargs)

            def list_models(self) -> list[str]:
                return ["deepseek-flash", "deepseek-v4-pro"]

        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": key,
                        "thinking_enabled": True,
                    }
                )
                with patch("tools.sidecar.handlers.settings.LLMClient", FakeClient):
                    result = handle_settings_check_llm_connection(
                        {
                            "meta": {"correlation_id": "corr_check_saved"},
                            "payload": {"provider": "deepseek", "timeout": 1},
                        }
                    )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["model_count"], 2)
        self.assertEqual(result["models"], ["deepseek-flash", "deepseek-v4-pro"])
        self.assertEqual(captured[0]["api_key"], key)
        self.assertEqual(captured[0]["provider"], "deepseek")
        self.assertTrue(captured[0]["thinking_enabled"])
        self.assertIn("DeepSeek", result["message"])

    def test_legacy_lm_studio_placeholder_stays_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            policy.write_text(
                "\n".join(
                    [
                        'llm_provider: "lm_studio"',
                        'llm_model: "local-model"',
                        'llm_base_url: "http://127.0.0.1:1234/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_placeholder: "configured"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                loaded = _load_llm_config()

        self.assertEqual(loaded["api_key_for_request"], "lm-studio")
        self.assertTrue(loaded["api_key_configured"])
        self.assertEqual(loaded["api_key_source"], "legacy")

    def test_legacy_online_flag_without_key_is_not_reported_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            policy.write_text(
                "\n".join(
                    [
                        'llm_provider: "openai"',
                        'llm_model: "gpt-4"',
                        'llm_base_url: "https://api.openai.com/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_placeholder: "configured"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                loaded = _load_llm_config()

        self.assertEqual(loaded["api_key_for_request"], "")
        self.assertFalse(loaded["api_key_configured"])
        self.assertEqual(loaded["api_key_source"], "none")

    def test_thinking_enabled_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                with self.assertRaises(ValueError):
                    self._update({"thinking_enabled": "true"})

    def test_thinking_effort_defaults_to_high_and_rejects_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update({"provider": "deepseek", "model": "deepseek-flash"})
                stored = self._get()
                with self.assertRaises(ValueError):
                    self._update({"thinking_effort": "ultra"})

        self.assertEqual(stored["llm_config"]["thinking_effort"], "high")

    def test_thinking_effort_accepts_low_high_max(self) -> None:
        for effort in ("low", "high", "max"):
            with self.subTest(effort=effort), tempfile.TemporaryDirectory() as tmp:
                policy = self._policy(tmp)
                with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                    self._update({"thinking_effort": effort})
                    stored = self._get()
                self.assertEqual(stored["llm_config"]["thinking_effort"], effort)

    def test_invalid_provider_cannot_write_credential_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = self._policy(tmp)
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                with self.assertRaises(ValueError):
                    self._update({"provider": "../evil", "api_key": "sk-test"})


if __name__ == "__main__":
    unittest.main()



class SettingsLlmProviderIsolationTests(unittest.TestCase):
    def _update(self, payload: dict[str, Any]) -> dict[str, Any]:
        return handle_settings_update(
            {
                "meta": {"correlation_id": "corr_llm_isolated"},
                "section": "llm_config",
                "payload": payload,
            }
        )

    def _get(self) -> dict[str, Any]:
        return handle_settings_get({"meta": {"correlation_id": "corr_llm_isolated_get"}})

    def test_connection_check_uses_requested_provider_key_not_active_key(self) -> None:
        captured: list[dict[str, Any]] = []

        class FakeClient:
            def __init__(self, **kwargs: Any) -> None:
                captured.append(kwargs)

            def list_models(self) -> list[str]:
                return ["gpt-4"]

        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update({"provider": "openai", "model": "gpt-4", "api_key": "sk-openai"})
                self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-deepseek",
                    }
                )
                with patch("tools.sidecar.handlers.settings.LLMClient", FakeClient):
                    result = handle_settings_check_llm_connection(
                        {
                            "meta": {"correlation_id": "corr_check_openai"},
                            "payload": {
                                "provider": "openai",
                                "base_url": "https://api.openai.com/v1",
                                "timeout": 1,
                            },
                        }
                    )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(captured[0]["api_key"], "sk-openai")
        self.assertEqual(captured[0]["provider"], "openai")
        self.assertNotEqual(captured[0]["api_key"], "sk-deepseek")

    def test_connection_check_blocks_when_requested_provider_has_no_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-deepseek",
                    }
                )
                result = handle_settings_check_llm_connection(
                    {
                        "meta": {"correlation_id": "corr_check_openai_missing"},
                        "payload": {
                            "provider": "openai",
                            "base_url": "https://api.openai.com/v1",
                            "timeout": 1,
                        },
                    }
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BLOCKED_PROVIDER_CREDENTIAL")
        self.assertNotIn("sk-deepseek", result["message"])

    def test_legacy_lm_studio_placeholder_does_not_configure_online_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            policy.write_text(
                "\n".join(
                    [
                        'llm_provider: "deepseek"',
                        'llm_model: "deepseek-flash"',
                        'llm_base_url: "https://api.deepseek.com"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_placeholder: "lm-studio"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                loaded = _load_llm_config()

        self.assertEqual(loaded["api_key_for_request"], "")
        self.assertFalse(loaded["api_key_configured"])
        self.assertEqual(loaded["api_key_source"], "none")

    def test_switching_from_legacy_lm_studio_to_online_clears_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            policy.write_text(
                "\n".join(
                    [
                        'llm_provider: "lm_studio"',
                        'llm_model: "local-model"',
                        'llm_base_url: "http://127.0.0.1:1234/v1"',
                        'llm_api_key_configured: "true"',
                        'llm_api_key_placeholder: "lm-studio"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                self._update({"provider": "deepseek"})
                stored = self._get()

        self.assertEqual(stored["llm_config"]["provider"], "deepseek")
        self.assertFalse(stored["llm_config"]["api_key"]["configured"])
        self.assertEqual(stored["llm_config"]["api_key"]["source"], "none")

    def test_environment_key_is_used_and_saved_file_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            policy.write_text(
                "\n".join(
                    [
                        'llm_provider: "openai"',
                        'llm_model: "gpt-4"',
                        'llm_base_url: "https://api.openai.com/v1"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"PPF_POLICY_PATH": str(policy), "LLM_API_KEY": "sk-env"},
            ):
                env_loaded = _load_llm_config()
                store = LLMApiKeyStore()
                store.save("openai", "sk-saved")
                saved_loaded = _load_llm_config()

        self.assertEqual(env_loaded["api_key_for_request"], "sk-env")
        self.assertEqual(env_loaded["api_key_source"], "environment")
        self.assertEqual(saved_loaded["api_key_for_request"], "sk-saved")
        self.assertEqual(saved_loaded["api_key_source"], "saved")

    def test_invalid_provider_is_rejected_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                with self.assertRaises(ValueError):
                    self._update({"provider": "../evil"})

    def test_malformed_api_key_is_not_echoed_in_connection_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
                result = handle_settings_check_llm_connection(
                    {
                        "meta": {"correlation_id": "corr_bad_key"},
                        "payload": {
                            "provider": "deepseek",
                            "base_url": "https://api.deepseek.com",
                            "api_key": "sk-bad\nvalue",
                            "timeout": 1,
                        },
                    }
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BLOCKED_PROVIDER_CREDENTIAL")
        self.assertNotIn("sk-bad", result["message"])

    def test_local_non_lm_studio_endpoint_uses_its_own_label(self) -> None:
        with patch(
            "tools.sidecar.handlers.settings.LLMClient.list_models",
            side_effect=OSError("connection refused"),
        ):
            result = handle_settings_check_llm_connection(
                {
                    "meta": {"correlation_id": "corr_local_compatible"},
                    "payload": {
                        "provider": "openai_compatible",
                        "base_url": "http://127.0.0.1:8080/v1",
                        "timeout": 1,
                    },
                }
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BLOCKED_PROVIDER")
        self.assertIn("OpenAI-compatible provider", result["message"])
        self.assertNotIn("LM Studio", result["message"])


def test_cross_provider_check_without_base_url_does_not_use_active_endpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        policy = Path(tmp) / "policy.yaml"
        with patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy)}):
            handle_settings_update(
                {
                    "meta": {"correlation_id": "corr_cross_no_url"},
                    "section": "llm_config",
                    "payload": {
                        "provider": "deepseek",
                        "model": "deepseek-flash",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-deepseek",
                    },
                }
            )
            result = handle_settings_check_llm_connection(
                {
                    "meta": {"correlation_id": "corr_cross_no_url_check"},
                    "payload": {"provider": "openai", "timeout": 1},
                }
            )

    assert result["status"] == "blocked"
    assert result["code"] == "BLOCKED_PROVIDER"
    assert result["base_url"] == ""
    assert "deepseek.com" not in result["message"]
