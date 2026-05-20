from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml
from tools.policy.exclusions import (
    load_delivery_settings,
    load_exclusion_list,
    load_legal_entity_exclusion_list,
    save_delivery_settings,
    save_exclusion_list,
    save_legal_entity_exclusion_list,
)

_SUPPORTED_GATE_POLICY_UPDATE_FIELDS = {"delivery_mode", "batch_review"}
_SUPPORTED_LLM_CONFIG_UPDATE_FIELDS = {
    "provider",
    "model",
    "base_url",
    "api_key",
    "timeout",
    "temperature",
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
        "channels": [
            {
                "id": "liepin",
                "label": "Liepin",
                "enabled": True,
                "priority": 1,
                "fallback_to": "email",
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
            },
            "timeout": llm_config["timeout"],
            "temperature": llm_config["temperature"],
        },
    }


def handle_settings_check_llm_connection(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    payload = params.get("payload")
    config = _merge_llm_config_payload(_load_llm_config(), payload)
    models_url = _models_url(str(config["base_url"] or ""))

    if not models_url:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": "BLOCKED_LOCAL_PROVIDER",
            "message": "LM Studio base_url is not configured.",
            "base_url": config["base_url"],
            "model_count": 0,
            "models": [],
        }

    try:
        client = LLMClient(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key_for_request"]),
            timeout=int(config["timeout"]),
        )
        models = client.list_models()
        if not models:
            return {
                "meta": {"correlation_id": correlation_id},
                "status": "blocked",
                "code": "BLOCKED_LOCAL_PROVIDER",
                "message": f"LM Studio returned no models from {models_url}.",
                "base_url": config["base_url"],
                "model_count": 0,
                "models": [],
            }
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "pass",
            "code": "OK",
            "message": f"LM Studio models endpoint is reachable at {models_url}.",
            "base_url": config["base_url"],
            "model_count": len(models),
            "models": models[:20],
        }
    except Exception as exc:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "blocked",
            "code": "BLOCKED_LOCAL_PROVIDER",
            "message": f"LM Studio models endpoint is unavailable at {models_url}: {exc}",
            "base_url": config["base_url"],
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


def _load_llm_config() -> dict[str, Any]:
    scalars, _ = _load_policy_doc()
    configured_raw = scalars.get("llm_api_key_configured", "")
    env_api_key = os.environ.get("LLM_API_KEY", "")
    return {
        "provider": scalars.get("llm_provider") or os.environ.get("LLM_PROVIDER", "openai"),
        "model": scalars.get("llm_model") or os.environ.get("LLM_MODEL", "gpt-4"),
        "base_url": scalars.get("llm_base_url") or os.environ.get("LLM_BASE_URL"),
        "api_key_configured": _to_bool(configured_raw, bool(env_api_key)),
        "api_key_updated_at": scalars.get("llm_api_key_updated_at", ""),
        "api_key_for_request": env_api_key or scalars.get("llm_api_key_placeholder", "lm-studio"),
        "timeout": _to_int(scalars.get("llm_timeout", ""), 60),
        "temperature": _to_float(scalars.get("llm_temperature", ""), 0.2),
    }


def _merge_llm_config_payload(
    config: dict[str, Any],
    payload: object,
) -> dict[str, Any]:
    merged = dict(config)
    if isinstance(payload, dict):
        for key in ("provider", "model", "base_url", "timeout", "temperature"):
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
    if "api_key" in payload:
        api_key = _require_non_empty_str(payload["api_key"], "api_key")
        scalars["llm_api_key_configured"] = "true"
        scalars["llm_api_key_updated_at"] = _utcnow()
        scalars["llm_api_key_placeholder"] = api_key if api_key == "lm-studio" else "configured"

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
    env_path = os.environ.get("PPF_POLICY_PATH")
    if env_path:
        return Path(env_path)
    return Path("policy.yaml")


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
