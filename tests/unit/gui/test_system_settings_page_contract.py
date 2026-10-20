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
        "deepseek",
        "thinking_enabled",
        "providerKeyConfigured",
        "canClearProviderKey",
        "clearLlmApiKey",
    ):
        assert marker in source


def test_system_settings_page_does_not_embed_page_hooks():
    page_source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    for marker in (
        "applyProviderDefaults",
        "checkLlmConnection",
        "updateLlmConfig",
        "getSettings",
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
        "keySaved",
        "keyEnvironment",
        "keyLocalPlaceholder",
        "keyStorageError",
        "keyMissing",
        "clearKey",
        "thinkingMode",
        "thinkingModeHint",
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


def test_deepseek_provider_defaults_and_thinking_toggle_are_wired():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    assert 'deepseek: {' in source
    assert '"https://api.deepseek.com"' in source
    assert '"deepseek-flash"' in source
    assert "model: nextDefaults.model" in source
    assert "base_url: nextDefaults.base_url" in source
    assert "thinking_enabled: current.thinking_enabled" in source
    assert 'setLlmConnection(null)' in source
    assert "thinking_enabled" in source
    assert "clearLlmApiKey" in source
    assert "canClearProviderKey" in source
    assert 'result.status === "pass"' in source


def test_llm_credential_contract_exposes_provider_scoped_status():
    api_source = (ROOT / "ui" / "src" / "lib" / "sidecar" / "api.ts").read_text(
        encoding="utf-8"
    )
    types_source = (
        ROOT / "ui" / "src" / "lib" / "sidecar" / "types.ts"
    ).read_text(encoding="utf-8")

    assert "settings.clearLlmApiKey" in api_source
    assert "configured_providers" in types_source
    assert "thinking_enabled" in types_source
    assert "source?:" in types_source
