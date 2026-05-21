import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_SETTINGS_PAGE = ROOT / "ui" / "src" / "pages" / "system-settings" / "index.tsx"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_system_settings_page_renders_design_sections():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    for marker in (
        "activeSection",
        "ChannelCard",
        "fallbackOrder",
        "connectionSummary",
        "secretStatus",
        "settings.llm_config.api_key.configured",
        "llmForm",
        "updateLlmConfig",
        "checkLlmConnection",
        "handleSaveLlmConfig",
        "handleCheckLlmConnection",
        "LLM_PROVIDER_DEFAULTS",
        "applyProviderDefaults",
        "detectedModels",
        "supports_detected_model_select",
        "deepVerifyEnabled",
        "runDeepLlmVerify",
        "system_settings.llm.deep_verify.result",
        "system_settings.llm.form.ready",
    ):
        assert marker in source


def test_system_settings_native_verifier_is_deep_enough():
    page_source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")
    script_source = (
        ROOT / "ui" / "scripts" / "verify_system_settings_native.mjs"
    ).read_text(encoding="utf-8")

    for marker in (
        "VITE_SYSTEM_SETTINGS_DEEP_VERIFY",
        "VITE_SYSTEM_SETTINGS_LLM_STUB_BASE_URL",
        "PPF_POLICY_PATH",
        "ROOT_POLICY_PATH",
        "startLlmStubServer",
        "/v1/models",
        "waitForDeepVerifyEvent",
        "Bearer lm-studio",
        "modified root policy.yaml",
    ):
        assert marker in script_source

    for marker in (
        "applyProviderDefaults",
        "checkLlmConnection",
        "updateLlmConfig",
        "getSettings",
        "exposesPlaintextApiKey",
        "BLOCKED_LOCAL_PROVIDER",
    ):
        assert marker in page_source


def test_system_settings_page_does_not_degrade_to_channel_count_only():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    assert "{settings.channels.length}" not in source


def test_system_settings_llm_config_is_not_read_only():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    assert "pages.systemSettings.readOnly" not in source
    assert 'type="password"' in source
    assert "api_key.value" not in source
    assert "api_key.secret" not in source


def test_system_settings_i18n_contract_is_complete():
    required_keys = {
        "save",
        "nav",
        "channels",
        "llm",
        "secretStatus",
        "secretConfigured",
        "secretMissing",
    }
    required_channel_keys = {
        "title",
        "subtitle",
        "none",
        "priority",
        "fallback",
        "credential",
        "lastCheck",
        "lastSuccess",
        "lastError",
        "fallbackOrder",
        "connectionTests",
        "credentialStore",
        "credentialStoreStatus",
    }
    required_llm_keys = {
        "title",
        "subtitle",
        "provider",
        "model",
        "detectedModels",
        "baseUrl",
        "apiKey",
        "timeout",
        "temperature",
        "defaultModel",
        "connectionTest",
        "defaultEndpoint",
        "modelPlaceholder",
        "chooseDetectedModel",
        "noDetectedModels",
        "modelCount",
        "keepExistingSecret",
        "testConnection",
        "checking",
        "saving",
        "saved",
    }

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        system_settings_messages = messages["pages"]["systemSettings"]
        missing = required_keys.difference(system_settings_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"
        missing_channels = required_channel_keys.difference(
            system_settings_messages["channels"]
        )
        assert not missing_channels, (
            f"{i18n_file.name} missing channel keys: {sorted(missing_channels)}"
        )
        missing_llm = required_llm_keys.difference(system_settings_messages["llm"])
        assert not missing_llm, (
            f"{i18n_file.name} missing LLM keys: {sorted(missing_llm)}"
        )
