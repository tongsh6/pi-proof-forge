from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.infra.llm.client import LLMClient
from tools.infra.llm_credentials import LLMApiKeyStore, normalize_provider
from tools.infra.liepin_readonly import liepin_readonly
from tools.infra.liepin_token_file import CredentialStorageError
from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml
from tools.policy.exclusions import (
    resolve_policy_path,
    load_delivery_settings,
    load_evidence_inference_enabled,
    load_exclusion_list,
    load_legal_entity_exclusion_list,
    load_material_source_roots,
    save_delivery_settings,
    save_evidence_inference_enabled,
    save_exclusion_list,
    save_legal_entity_exclusion_list,
    save_material_source_roots,
)

_SUPPORTED_GATE_POLICY_UPDATE_FIELDS = {"delivery_mode", "batch_review"}
_SUPPORTED_LLM_CONFIG_UPDATE_FIELDS = {
    "provider",
    "model",
    "base_url",
    "api_key",
    "timeout",
    "temperature",
    "thinking_enabled",
    "thinking_effort",
}


def handle_settings_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]

    smtp_configured = bool(os.environ.get("SMTP_USER")) and bool(
        os.environ.get("SMTP_PASS")
    )
    liepin_session_configured = bool(os.environ.get("PPF_LIEPIN_SESSION_DIR"))
    exclusion_list = load_exclusion_list()
    legal_entity_exclusion_list = load_legal_entity_exclusion_list()
    delivery_mode, batch_review = load_delivery_settings()
    llm_config = _load_llm_config()

    return {
        "meta": {"correlation_id": correlation_id},
        "liepin_api": liepin_readonly.snapshot(),
        "gate_policy": {
            "n_pass_required": 3,
            "matching_threshold": 70,
            "evaluation_threshold": 75,
            "max_rounds": 5,
            "gate_mode": "strict",
            "delivery_mode": delivery_mode,
            "batch_review": batch_review,
        },
        "exclusion_list": exclusion_list,
        "excluded_legal_entities": legal_entity_exclusion_list,
        "material_source_roots": load_material_source_roots(),
        "evidence_inference": {"enabled": load_evidence_inference_enabled()},
        "channels": [
            {
                "id": "liepin",
                "label": "Liepin",
                "enabled": True,
                "priority": 1,
                "fallback_to": "",
                "credential_status": "configured"
                if liepin_session_configured
                else "missing",
                "last_check_status": "unknown",
                "last_success_at": "",
                "last_error": ""
                if liepin_session_configured
                else "PPF_LIEPIN_SESSION_DIR is not configured",
            },
            {
                "id": "email",
                "label": "Email",
                "enabled": True,
                "priority": 2,
                "fallback_to": "",
                "credential_status": "configured" if smtp_configured else "missing",
                "last_check_status": "unknown",
                "last_success_at": "",
                "last_error": ""
                if smtp_configured
                else "SMTP_USER and SMTP_PASS are not configured",
            },
        ],
        "llm_config": {
            "provider": llm_config["provider"],
            "model": llm_config["model"],
            "base_url": llm_config["base_url"],
            "api_key": {
                "configured": llm_config["api_key_configured"],
                "masked": True,
                "updated_at": llm_config["api_key_updated_at"],
                "source": llm_config["api_key_source"],
            },
            "configured_providers": llm_config["configured_providers"],
            "thinking_enabled": llm_config["thinking_enabled"],
            "thinking_effort": llm_config["thinking_effort"],
            "timeout": llm_config["timeout"],
            "temperature": llm_config["temperature"],
        },
    }


def handle_settings_liepin_credential(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action")
    if action == "set":
        auth = liepin_readonly.configure(params.get("token"))
    elif action == "clear":
        auth = liepin_readonly.clear()
    elif action == "check":
        auth = liepin_readonly.read_resume()["auth"]
    else:
        raise ValueError("unsupported credential action")
    return {"meta": {"correlation_id": params["meta"]["correlation_id"]}, "auth": auth}


def handle_settings_liepin_resume(params: dict[str, Any]) -> dict[str, Any]:
    return {"meta": {"correlation_id": params["meta"]["correlation_id"]},
            **liepin_readonly.read_resume()}


def handle_settings_check_llm_connection(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    payload = params.get("payload")
    active = _load_llm_config()
    config = _merge_llm_config_payload(active, payload)
    requested_provider = str(config.get("provider") or "").strip()
    try:
        requested_provider = normalize_provider(requested_provider)
    except ValueError:
        pass
    label = _provider_label(requested_provider)
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
    payload_key = payload.get("api_key") if isinstance(payload, dict) else None
    if isinstance(payload_key, str) and payload_key.strip():
        api_key = payload_key.strip()
    elif requested_provider == str(active.get("provider") or "").strip().lower():
        api_key = str(active.get("api_key_for_request") or "").strip()
    else:
        # 不同 provider 之间不得复用当前生效的密钥；只读取该 provider 自己的文件。
        api_key = _saved_api_key_for_provider(requested_provider)
    if requested_provider == "lm_studio" and not api_key:
        api_key = "lm-studio"

    models_url = _models_url(base_url)
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except ValueError:
        host = ""
    local_host = host in ("127.0.0.1", "localhost", "::1")
    lm_studio_compat = requested_provider == "lm_studio" or api_key == "lm-studio"
    local_endpoint = local_host and (
        requested_provider == "openai_compatible" or lm_studio_compat
    )
    display_label = "LM Studio" if lm_studio_compat else label
    blocked_code = "BLOCKED_LOCAL_PROVIDER" if lm_studio_compat else "BLOCKED_PROVIDER"

    if api_key and not _valid_api_key(api_key):
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": "BLOCKED_PROVIDER_CREDENTIAL",
            "message": f"{label} API key format is invalid.",
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }

    if not models_url:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": blocked_code,
            "message": f"{display_label} base_url is not configured.",
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }

    if not api_key and not (lm_studio_compat or local_endpoint):
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
        client = LLMClient(
            base_url=base_url,
            api_key=api_key,
            timeout=int(config["timeout"]),
            provider=requested_provider,
            thinking_enabled=bool(config.get("thinking_enabled", False)),
            reasoning_effort=_normalize_thinking_effort(
                config.get("thinking_effort", "high")
            ),
        )
        models = client.list_models()
        if not models:
            return {
                "meta": {"correlation_id": correlation_id},
                "status": "blocked",
                "code": blocked_code,
                "message": f"{display_label} returned no models from {models_url}.",
                "base_url": base_url,
                "model_count": 0,
                "models": [],
            }
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "pass",
            "code": "OK",
            "message": f"{display_label} models endpoint is reachable at {models_url}.",
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
                f"{display_label} models endpoint is unavailable at {models_url}: {message}"
            ),
            "base_url": base_url,
            "model_count": 0,
            "models": [],
        }


def handle_settings_update(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    section = params.get("section")
    payload = params.get("payload")

    if section == "gate_policy":
        if not isinstance(payload, dict):
            raise ValueError("gate_policy payload must be an object")
        unsupported_fields = set(payload) - _SUPPORTED_GATE_POLICY_UPDATE_FIELDS
        if unsupported_fields:
            unsupported = ", ".join(sorted(unsupported_fields))
            raise ValueError(f"unsupported gate_policy fields: {unsupported}")
        mode = str(payload.get("delivery_mode", "")).strip()
        batch_raw = payload.get("batch_review")
        if mode and mode not in ("auto", "manual"):
            raise ValueError(f"unsupported delivery_mode: {mode}")
        if batch_raw is not None and not isinstance(batch_raw, bool):
            raise ValueError("batch_review must be a boolean")
        if mode or batch_raw is not None:
            current_mode, current_batch = load_delivery_settings()
            new_mode = mode if mode else current_mode
            new_batch = bool(batch_raw) if batch_raw is not None else current_batch
            _ = save_delivery_settings(new_mode, new_batch)
        return {
            "meta": {"correlation_id": correlation_id},
            "section": section,
            "saved": True,
        }

    if section == "llm_config":
        if not isinstance(payload, dict):
            raise ValueError("llm_config payload must be an object")
        unsupported_fields = set(payload) - _SUPPORTED_LLM_CONFIG_UPDATE_FIELDS
        if unsupported_fields:
            unsupported = ", ".join(sorted(unsupported_fields))
            raise ValueError(f"unsupported llm_config fields: {unsupported}")
        _ = _save_llm_config(payload)
        return {
            "meta": {"correlation_id": correlation_id},
            "section": section,
            "saved": True,
        }

    if section == "evidence_inference":
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
            raise ValueError("evidence_inference payload must be {enabled: bool}")
        _ = save_evidence_inference_enabled(payload["enabled"])
        return {
            "meta": {"correlation_id": correlation_id},
            "section": section,
            "saved": True,
        }

    if section == "material_source_roots":
        if not isinstance(payload, list):
            raise ValueError("material_source_roots payload must be a list")
        _ = save_material_source_roots(payload)
        return {
            "meta": {"correlation_id": correlation_id},
            "section": section,
            "saved": True,
        }

    if section not in {"exclusion_list", "excluded_legal_entities"}:
        raise ValueError(f"unsupported settings section: {section}")

    if not isinstance(payload, list):
        raise ValueError("exclusion_list payload must be a list of strings")

    payload_list: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            raise ValueError("exclusion_list payload must be a list of strings")
        payload_list.append(item)

    if section == "exclusion_list":
        _ = save_exclusion_list(payload_list)
    else:
        _ = save_legal_entity_exclusion_list(payload_list)
    return {
        "meta": {"correlation_id": correlation_id},
        "section": section,
        "saved": True,
    }


def handle_settings_clear_llm_api_key(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    provider_value = params.get("provider")
    if not isinstance(provider_value, str) or not provider_value.strip():
        provider_value = _load_llm_config()["provider"]
    try:
        provider = normalize_provider(provider_value)
        store = LLMApiKeyStore()
        store.delete(provider)
    except ValueError as exc:
        raise ValueError(str(exc)) from None
    except CredentialStorageError:
        raise ValueError("本机凭据文件删除失败。") from None

    scalars, lists = _load_policy_doc()
    active = str(
        scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "openai")
    ).strip().lower()
    if active == provider:
        for key in (
            "llm_api_key_configured",
            "llm_api_key_updated_at",
            "llm_api_key_placeholder",
        ):
            scalars.pop(key, None)
        policy_path = _resolve_policy_path()
        if policy_path is not None:
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(dump_yaml(scalars, lists), encoding="utf-8")

    return {
        "meta": {"correlation_id": correlation_id},
        "provider": provider,
        "cleared": True,
        "configured_providers": store.configured_providers(),
    }


def _saved_api_key_for_provider(provider: str) -> str:
    try:
        return LLMApiKeyStore().load(provider) or ""
    except (ValueError, CredentialStorageError):
        return ""


def _valid_api_key(value: str) -> bool:
    return (
        bool(value.strip())
        and len(value) <= 8192
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


_THINKING_EFFORTS = ("low", "high", "max")


def _normalize_thinking_effort(value: object) -> str:
    effort = str(value or "").strip().lower()
    return effort if effort in _THINKING_EFFORTS else "high"


def _load_llm_config() -> dict[str, Any]:
    scalars, _ = _load_policy_doc()
    provider = str(
        scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "openai")
    ).strip() or "openai"
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

    return {
        "provider": provider,
        "model": scalars.get("llm_model") or os.environ.get("LLM_MODEL", "gpt-4"),
        "base_url": scalars.get("llm_base_url") or os.environ.get("LLM_BASE_URL"),
        "api_key_configured": bool(api_key_for_request),
        "api_key_updated_at": updated_at,
        "api_key_for_request": api_key_for_request,
        "api_key_source": api_key_source,
        "configured_providers": configured_providers,
        "thinking_enabled": _to_bool(scalars.get("llm_thinking_enabled", ""), False),
        "thinking_effort": _normalize_thinking_effort(
            scalars.get("llm_thinking_effort", "high")
        ),
        "timeout": _to_int(scalars.get("llm_timeout", ""), 60),
        "temperature": _to_float(scalars.get("llm_temperature", ""), 0.2),
    }


def _merge_llm_config_payload(
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


def _save_llm_config(payload: dict[str, Any]) -> Path | None:
    scalars, lists = _load_policy_doc()
    if "provider" in payload:
        provider = _require_non_empty_str(payload["provider"], "provider")
        try:
            provider = normalize_provider(provider)
        except ValueError:
            raise ValueError("unsupported provider id") from None
        scalars["llm_provider"] = provider
    if "model" in payload:
        model = _require_non_empty_str(payload["model"], "model")
        scalars["llm_model"] = model
    if "base_url" in payload:
        base_url = _require_non_empty_str(payload["base_url"], "base_url")
        scalars["llm_base_url"] = base_url
    if "timeout" in payload:
        scalars["llm_timeout"] = str(_require_positive_int(payload["timeout"], "timeout"))
    if "temperature" in payload:
        scalars["llm_temperature"] = str(
            _require_float_in_range(payload["temperature"], "temperature", 0.0, 2.0)
        )
    if "thinking_enabled" in payload:
        enabled = payload["thinking_enabled"]
        if not isinstance(enabled, bool):
            raise ValueError("thinking_enabled must be a boolean")
        scalars["llm_thinking_enabled"] = "true" if enabled else "false"
    if "thinking_effort" in payload:
        effort = payload["thinking_effort"]
        if not isinstance(effort, str) or effort.strip().lower() not in _THINKING_EFFORTS:
            raise ValueError("thinking_effort must be low, high or max")
        scalars["llm_thinking_effort"] = effort.strip().lower()
    if "api_key" in payload:
        api_key = _require_non_empty_str(payload["api_key"], "api_key")
        effective_provider = str(
            scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "openai")
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
            scalars["llm_api_key_updated_at"] = _utcnow()
            scalars["llm_api_key_placeholder"] = "lm-studio"

    effective_provider = str(
        scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "openai")
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

    policy_path = _resolve_policy_path()
    if policy_path is None:
        return None
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(dump_yaml(scalars, lists), encoding="utf-8")
    return policy_path


def _load_policy_doc() -> tuple[dict[str, str], dict[str, list[str]]]:
    policy_path = _resolve_policy_path()
    if policy_path is None or not policy_path.exists():
        return {}, {}
    doc = parse_simple_yaml(policy_path.read_text(encoding="utf-8"))
    return doc.get("scalars", {}), doc.get("lists", {})


def _resolve_policy_path() -> Path | None:
    # 与排除名单共用同一规则，避免设置页把本机配置写回仓库默认策略文件。
    return resolve_policy_path()


def _provider_label(provider: str) -> str:
    return {
        "lm_studio": "LM Studio",
        "openai": "OpenAI",
        "deepseek": "DeepSeek",
        "openai_compatible": "OpenAI-compatible provider",
    }.get(provider, provider or "Provider")


def _models_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    return f"{cleaned}/models"


def _require_non_empty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _require_float_in_range(value: object, field: str, minimum: float, maximum: float) -> float:
    if not isinstance(value, (float, int)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return number


def _to_bool(value: str, default: bool) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    return default


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
