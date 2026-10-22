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
        "LLM_PROVIDER_OPTIONS",
        "llmConnectionSummary",
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
        "thinkingEffort",
        "thinkingEffortHint",
        "effortLow",
        "effortHigh",
        "effortMax",
        "providerStrataHint",
        "strataBaseUrlHint",
        "strataModelManagedHint",
        "keyLocalOptional",
        "keyOptionalPlaceholder",
        "thinkingModeHintStrata",
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
    assert "nextDefaults.base_url" in source
    assert "thinking_enabled: current.thinking_enabled" in source
    assert 'setLlmConnection(null)' in source
    assert "thinking_enabled" in source
    assert "thinking_effort" in source
    assert "thinking_effort: current.thinking_effort" in source
    assert "payload.thinking_effort = form.thinking_effort" in source
    assert "LLM_THINKING_EFFORTS" in source
    assert "effort.value" in source
    assert 'role="switch"' in source
    assert "LLM_PROVIDER_OPTIONS" in source
    assert "notChecked" in source
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


def test_strata_provider_defaults_and_option_are_wired():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")
    helper = (ROOT / "ui" / "src" / "lib" / "llmConfig.ts").read_text(
        encoding="utf-8"
    )

    # Strata 不再写死模型/引擎端口：统一后台地址来自共享常量，模型由 App 管理。
    assert 'strata: {' in source
    assert 'export const STRATA_UNIFIED_BASE_URL = "http://127.0.0.1:47831/v1";' in helper
    assert "import { KEYLESS_PROVIDERS, STRATA_UNIFIED_BASE_URL }" in source
    assert '"http://127.0.0.1:8081/v1"' not in source
    assert '"qwen3.8-flash-next-q2_0"' not in source
    assert "model: \"\"," in source
    assert "base_url: STRATA_UNIFIED_BASE_URL" in source
    assert (
        '{ id: "strata", label: "Strata", hintKey: "providerStrataHint" }' in source
    )
    # 默认推理后台是 Strata App 统一入口。
    assert 'const provider = config?.provider ?? "strata";' in source
    # 端点与模型字段对 Strata 只读，模型需从 /v1/models 选择。
    assert 'readOnly={llmForm.provider === "strata"}' in source
    assert "strataBaseUrlHint" in source
    assert "strataModelManagedHint" in source
    # Provider 顺序：LM Studio / Strata / OpenAI / DeepSeek / OpenAI Compatible。
    assert source.index('{ id: "lm_studio"') < source.index('{ id: "strata"')
    assert source.index('{ id: "strata"') < source.index('{ id: "openai"')
    assert "mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5" in source


def test_strata_thinking_toggle_and_payload_are_wired():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    # 思考开关对 DeepSeek 与 Strata 显示，Strata 使用独立提示文案。
    assert 'llmForm.provider === "deepseek" || llmForm.provider === "strata"' in source
    assert "thinkingModeHintStrata" in source
    # Strata 只渲染 low/high；max 在切换 provider 时归一到 high。
    assert 'effort.value !== "max"' in source
    assert "thinkingEffortsForProvider(llmForm.provider).map" in source
    assert "function normalizeThinkingEffort" in source
    assert (
        'return provider === "strata" && effort === "max" ? "high" : effort;'
        in source
    )
    assert "normalizeThinkingEffort(nextProvider," in source
    # Strata 保存/检查连接同样提交思考字段。
    assert 'form.provider === "deepseek" || form.provider === "strata"' in source
    assert "payload.thinking_enabled = form.thinking_enabled" in source
    assert "payload.thinking_effort = form.thinking_effort" in source


def test_strata_keyless_credential_status_is_wired():
    source = SYSTEM_SETTINGS_PAGE.read_text(encoding="utf-8")

    # LM Studio 与 Strata 的 keyless 判定收敛在共享 helper。
    assert (
        'import { KEYLESS_PROVIDERS, STRATA_UNIFIED_BASE_URL } from "@/lib/llmConfig";'
        in source
    )
    assert "KEYLESS_PROVIDERS.has(provider)" in source
    # 卡片状态点：Strata 无已保存/环境变量 Key 时按“本地服务，无需密钥（可选）”展示。
    assert "providerKeyStatusLabel" in source
    assert 'provider === "strata" && providerKeySource(provider) === "none"' in source
    assert "providerKeyStatusLabel(option.id)" in source
    assert "keyLocalOptional" in source
    # 无已保存/环境变量 Key 时 placeholder 不再误示“留空则保留已有密钥”。
    assert "keyOptionalPlaceholder" in source
    # 清除入口仍只在本机确有凭据文件时显示。
    assert "const canClearProviderKey = configuredProviders.includes(llmForm.provider);" in source


def test_unified_backend_address_stays_consistent_across_backend_ui_and_i18n():
    from tools.infra.llm.client import STRATA_UNIFIED_BASE_URL

    helper = (ROOT / "ui" / "src" / "lib" / "llmConfig.ts").read_text(
        encoding="utf-8"
    )
    assert (
        f'export const STRATA_UNIFIED_BASE_URL = "{STRATA_UNIFIED_BASE_URL}";'
        in helper
    )
    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        llm = messages["pages"]["systemSettings"]["llm"]
        assert "47831" in llm["providerStrataHint"]
        assert STRATA_UNIFIED_BASE_URL in llm["strataBaseUrlHint"]
