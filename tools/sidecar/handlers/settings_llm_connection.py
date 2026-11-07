"""LLM 连接探测 handler。

从 ``settings.py`` 拆出：原文件超过 600 行，本模块只承载
``settings.checkLlmConnection`` 的探测逻辑与结果归一。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from tools.infra.llm.client import STRATA_UNIFIED_BASE_URL
from tools.infra.llm_credentials import normalize_provider
from tools.sidecar.handlers._shared.llm_config import (
    load_llm_config,
    merge_llm_config_payload,
    models_url,
    normalize_thinking_effort,
    provider_label,
    saved_api_key_for_provider,
    valid_api_key,
)


def _settings_module():
    """延迟获取 settings 模块：保留测试对 settings.LLMClient 等符号的 patch 能力。"""
    from tools.sidecar.handlers import settings

    return settings


def handle_settings_check_llm_connection(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    payload = params.get("payload")
    active = load_llm_config()
    config = merge_llm_config_payload(active, payload)
    requested_provider = str(config.get("provider") or "").strip()
    try:
        requested_provider = normalize_provider(requested_provider)
    except ValueError:
        pass
    label = provider_label(requested_provider)
    base_url = str(config["base_url"] or "").strip()
    payload_provider = payload.get("provider") if isinstance(payload, dict) else None
    payload_base_url = payload.get("base_url") if isinstance(payload, dict) else None
    active_provider = str(active.get("provider") or "").strip().lower()
    if (
        isinstance(payload_provider, str)
        and payload_provider.strip()
        and requested_provider != active_provider
        and not (isinstance(payload_base_url, str) and payload_base_url.strip())
    ):
        # 切换目标 provider 但未提供地址时，不能把该 provider 的密钥发往当前生效端点。
        base_url = ""
    if requested_provider == "strata":
        # Strata 只有一套由 App 管理的统一推理后台：不接受页面或旧配置里的其他地址。
        base_url = STRATA_UNIFIED_BASE_URL
    payload_key = payload.get("api_key") if isinstance(payload, dict) else None
    if isinstance(payload_key, str) and payload_key.strip():
        api_key = payload_key.strip()
    elif requested_provider == str(active.get("provider") or "").strip().lower():
        api_key = str(active.get("api_key_for_request") or "").strip()
    else:
        # 不同 provider 之间不得复用当前生效的密钥；只读取该 provider 自己的文件。
        api_key = saved_api_key_for_provider(requested_provider)
    if requested_provider == "lm_studio" and not api_key:
        api_key = "lm-studio"

    models_endpoint = models_url(base_url)
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except ValueError:
        host = ""
    local_host = host in ("127.0.0.1", "localhost", "::1")
    strata_local = requested_provider == "strata"
    lm_studio_compat = requested_provider == "lm_studio" or api_key == "lm-studio"
    local_endpoint = local_host and (
        requested_provider == "openai_compatible" or lm_studio_compat
    )
    # Strata 与 LM Studio 同为本地服务：无 Key 时正常探测 /models，不报凭证缺失。
    keyless_local = strata_local or lm_studio_compat
    display_label = "LM Studio" if lm_studio_compat and not strata_local else label
    blocked_code = "BLOCKED_LOCAL_PROVIDER" if keyless_local else "BLOCKED_PROVIDER"

    if api_key and not valid_api_key(api_key):
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": "BLOCKED_PROVIDER_CREDENTIAL",
            "message": f"{label} API key format is invalid.",
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }

    if not models_endpoint:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": blocked_code,
            "message": f"{display_label} base_url is not configured.",
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }

    if not api_key and not (keyless_local or local_endpoint):
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": "BLOCKED_PROVIDER_CREDENTIAL",
            "message": f"{label} API key is not configured.",
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }

    try:
        client = _settings_module().LLMClient(
            base_url=base_url,
            api_key=api_key,
            timeout=int(config["timeout"]),
            provider=requested_provider,
            thinking_enabled=bool(config.get("thinking_enabled", False)),
            reasoning_effort=normalize_thinking_effort(
                config.get("thinking_effort", "high")
            ),
        )
        models = client.list_models()
        if not models:
            if strata_local:
                message = (
                    f"{display_label} unified backend is reachable at {models_endpoint} "
                    "but no model is currently loaded; load a model in Strata App "
                    "and check again."
                )
            else:
                message = f"{display_label} returned no models from {models_endpoint}."
            return {
                "meta": {"correlation_id": correlation_id},
                "status": "blocked",
                "code": blocked_code,
                "message": message,
                "base_url": base_url,
                "model_count": 0,
                "models": [],
            }
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "pass",
            "code": "OK",
            "message": (
                f"{display_label} unified backend is reachable at {models_endpoint}."
                if strata_local
                else f"{display_label} models endpoint is reachable at {models_endpoint}."
            ),
            "base_url": base_url,
            "model_count": len(models),
            "models": models[:20],
        }
    except Exception as exc:
        message = str(exc)
        if api_key:
            message = message.replace(api_key, "***")
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": blocked_code,
            "message": (
                f"{display_label} models endpoint is unavailable at {models_endpoint}: {message}"
            ),
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }
