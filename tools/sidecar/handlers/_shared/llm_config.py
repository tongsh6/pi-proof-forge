"""LLM 配置读取与回写的共享实现。

原先这些逻辑散落在 ``handlers/settings.py``，并被 ``agent``、``jobs``、
``evidence``、``native_pdf``、``job_preferences`` 等 handler 直接 import 下划线
函数。现在统一收敛到本模块：

- ``load_llm_config``：供其它 handler 读取当前生效配置的公开入口；运行时经
  ``settings`` 模块属性取值，兼容测试对 ``settings._load_llm_config`` 的 patch。
- ``load_llm_config_impl`` / ``save_llm_config_impl``：真正的实现，由
  ``settings`` 模块 re-export 为 ``_load_llm_config`` / ``_save_llm_config``。

注意：策略文件的路径解析（``_resolve_policy_path``）仍归属 ``settings`` 模块，
因为测试会 patch ``tools.sidecar.handlers.settings._resolve_policy_path``；
实现里因此改为运行时读取 ``settings`` 模块属性，而不是复制一份路径逻辑。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.llm.client import STRATA_UNIFIED_BASE_URL
from tools.infra.llm_credentials import LLMApiKeyStore, normalize_provider
from tools.infra.liepin_token_file import CredentialStorageError
from tools.infra.persistence.yaml_io import dump_yaml

# 默认推理后台：Strata App 管理的统一入口（见 2026-10-22 方案修正）。
DEFAULT_LLM_PROVIDER = "strata"

THINKING_EFFORTS = ("low", "high", "max")


def _settings_module():
    """延迟获取 settings 模块，避免循环 import 且保证运行时能读到 patch 后的属性。"""
    from tools.sidecar.handlers import settings

    return settings


def load_llm_config() -> dict[str, Any]:
    """读取当前生效的 LLM 配置（跨 handler 的公开入口）。"""
    return _settings_module()._load_llm_config()


def saved_api_key_for_provider(provider: str) -> str:
    try:
        return LLMApiKeyStore().load(provider) or ""
    except (ValueError, CredentialStorageError):
        return ""


def valid_api_key(value: str) -> bool:
    return (
        bool(value.strip())
        and len(value) <= 8192
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def normalize_thinking_effort(value: object) -> str:
    effort = str(value or "").strip().lower()
    return effort if effort in THINKING_EFFORTS else "high"


def load_llm_config_impl() -> dict[str, Any]:
    scalars, _ = _settings_module()._load_policy_doc()
    provider = str(
        scalars.get("llm_provider")
        or os.environ.get("LLM_PROVIDER", DEFAULT_LLM_PROVIDER)
    ).strip() or DEFAULT_LLM_PROVIDER
    try:
        provider = normalize_provider(provider)
    except ValueError:
        pass
    store = LLMApiKeyStore()
    saved_key = ""
    storage_failed = False
    try:
        saved_key = store.load(provider) or ""
    except CredentialStorageError:
        storage_failed = True
    except ValueError:
        # 旧配置可能使用不在白名单内的 provider 字符串；不读写其凭据文件。
        storage_failed = False

    env_api_key = os.environ.get("LLM_API_KEY", "").strip()

    if saved_key:
        api_key_for_request, api_key_source = saved_key, "saved"
    elif env_api_key:
        api_key_for_request, api_key_source = env_api_key, "environment"
    elif provider == "lm_studio":
        api_key_for_request, api_key_source = "lm-studio", "legacy"
    else:
        api_key_for_request, api_key_source = "", "none"

    if storage_failed:
        api_key_for_request, api_key_source = "", "storage_error"

    if saved_key:
        updated_at = str(store.status(provider).get("updated_at", ""))
    elif api_key_source == "legacy":
        updated_at = str(scalars.get("llm_api_key_updated_at", ""))
    else:
        updated_at = ""

    try:
        configured_providers = store.configured_providers()
    except ValueError:
        configured_providers = []

    default_model = "" if provider == "strata" else "gpt-4"
    base_url: str | None = scalars.get("llm_base_url") or os.environ.get("LLM_BASE_URL")
    if provider == "strata":
        # 统一推理后台端点固定；旧配置里直连引擎的 8081/8082 等地址不再生效。
        base_url = STRATA_UNIFIED_BASE_URL
    return {
        "provider": provider,
        "model": scalars.get("llm_model")
        or os.environ.get("LLM_MODEL", default_model),
        "base_url": base_url,
        "api_key_configured": bool(api_key_for_request),
        "api_key_updated_at": updated_at,
        "api_key_for_request": api_key_for_request,
        "api_key_source": api_key_source,
        "configured_providers": configured_providers,
        "thinking_enabled": to_bool(scalars.get("llm_thinking_enabled", ""), False),
        "thinking_effort": normalize_thinking_effort(
            scalars.get("llm_thinking_effort", "high")
        ),
        "timeout": to_int(scalars.get("llm_timeout", ""), 60),
        "temperature": to_float(scalars.get("llm_temperature", ""), 0.2),
    }


def merge_llm_config_payload(
    config: dict[str, Any],
    payload: object,
) -> dict[str, Any]:
    merged = dict(config)
    if isinstance(payload, dict):
        for key in (
            "provider",
            "model",
            "base_url",
            "timeout",
            "temperature",
            "thinking_enabled",
            "thinking_effort",
        ):
            if key in payload:
                merged[key] = payload[key]
        if isinstance(payload.get("api_key"), str) and payload["api_key"]:
            merged["api_key_for_request"] = payload["api_key"]
            merged["api_key_configured"] = True
    return merged


def save_llm_config_impl(payload: dict[str, Any]) -> Path | None:
    settings = _settings_module()
    scalars, lists = settings._load_policy_doc()
    current_provider = str(
        scalars.get("llm_provider")
        or os.environ.get("LLM_PROVIDER", DEFAULT_LLM_PROVIDER)
    ).strip()
    try:
        current_provider = normalize_provider(current_provider)
    except ValueError:
        current_provider = ""
    target_provider = current_provider
    if "provider" in payload:
        provider = require_non_empty_str(payload["provider"], "provider")
        try:
            provider = normalize_provider(provider)
        except ValueError:
            raise ValueError("unsupported provider id") from None
        scalars["llm_provider"] = provider
        target_provider = provider
    if target_provider != current_provider:
        # 切换 provider 时模型/端点必须跟新 provider 走；旧值不能继续生效。
        if "model" not in payload:
            scalars.pop("llm_model", None)
        if "base_url" not in payload:
            scalars.pop("llm_base_url", None)
    if "model" in payload:
        model = require_non_empty_str(payload["model"], "model")
        scalars["llm_model"] = model
    if "base_url" in payload:
        base_url = require_non_empty_str(payload["base_url"], "base_url")
        scalars["llm_base_url"] = base_url
    if "timeout" in payload:
        scalars["llm_timeout"] = str(require_positive_int(payload["timeout"], "timeout"))
    if "temperature" in payload:
        scalars["llm_temperature"] = str(
            require_float_in_range(payload["temperature"], "temperature", 0.0, 2.0)
        )
    if "thinking_enabled" in payload:
        enabled = payload["thinking_enabled"]
        if not isinstance(enabled, bool):
            raise ValueError("thinking_enabled must be a boolean")
        scalars["llm_thinking_enabled"] = "true" if enabled else "false"
    if "thinking_effort" in payload:
        effort = payload["thinking_effort"]
        if not isinstance(effort, str) or effort.strip().lower() not in THINKING_EFFORTS:
            raise ValueError("thinking_effort must be low, high or max")
        scalars["llm_thinking_effort"] = effort.strip().lower()
    if "api_key" in payload:
        api_key = require_non_empty_str(payload["api_key"], "api_key")
        effective_provider = target_provider or str(
            scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "")
        )
        try:
            normalized_provider = normalize_provider(effective_provider)
        except ValueError:
            raise ValueError("unsupported provider id") from None
        if not (normalized_provider == "lm_studio" and api_key == "lm-studio"):
            try:
                LLMApiKeyStore().save(normalized_provider, api_key)
            except CredentialStorageError:
                raise ValueError("本机凭据文件保存失败。") from None
            for legacy_key in (
                "llm_api_key_configured",
                "llm_api_key_updated_at",
                "llm_api_key_placeholder",
            ):
                scalars.pop(legacy_key, None)
        else:
            scalars["llm_api_key_configured"] = "true"
            scalars["llm_api_key_updated_at"] = utcnow()
            scalars["llm_api_key_placeholder"] = "lm-studio"

    if target_provider == "strata":
        # 统一推理后台只有一个入口：忽略页面/旧配置地址，保存时归一为固定端点。
        scalars["llm_base_url"] = STRATA_UNIFIED_BASE_URL

    effective_provider = target_provider or str(
        scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "")
    ).strip()
    try:
        normalized_effective = normalize_provider(effective_provider)
    except ValueError:
        normalized_effective = ""
    if normalized_effective != "lm_studio":
        # 旧版 LM Studio 占位不能继续为在线 provider 提供“已配置”假象。
        for legacy_key in (
            "llm_api_key_configured",
            "llm_api_key_updated_at",
            "llm_api_key_placeholder",
        ):
            scalars.pop(legacy_key, None)

    policy_path = settings._resolve_policy_path()
    if policy_path is None:
        return None
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(dump_yaml(scalars, lists), encoding="utf-8")
    return policy_path


def provider_label(provider: str) -> str:
    return {
        "lm_studio": "LM Studio",
        "strata": "Strata App",
        "openai": "OpenAI",
        "deepseek": "DeepSeek",
        "openai_compatible": "OpenAI-compatible provider",
    }.get(provider, provider or "Provider")


def models_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    return f"{cleaned}/models"


def require_non_empty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def require_positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def require_float_in_range(value: object, field: str, minimum: float, maximum: float) -> float:
    if not isinstance(value, (float, int)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return number


def to_bool(value: str, default: bool) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    return default


def to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
