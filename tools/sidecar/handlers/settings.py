from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tools.infra.ai_disclosure import AI_DISCLOSURE_TEXT
from tools.infra.llm.client import LLMClient
from tools.infra.liepin_readonly import liepin_readonly
from tools.infra.llm_credentials import LLMApiKeyStore, normalize_provider
from tools.infra.liepin_token_file import CredentialStorageError
from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml
from tools.policy.exclusions import (
    resolve_policy_path,
    load_ai_disclosure_enabled,
    load_delivery_settings,
    load_evidence_inference_enabled,
    load_exclusion_list,
    load_legal_entity_exclusion_list,
    load_material_source_roots,
    save_ai_disclosure_enabled,
    save_delivery_settings,
    save_evidence_inference_enabled,
    save_exclusion_list,
    save_legal_entity_exclusion_list,
    save_material_source_roots,
)
from tools.sidecar.handlers._shared.llm_config import (
    DEFAULT_LLM_PROVIDER as _DEFAULT_LLM_PROVIDER,
    load_llm_config_impl as _load_llm_config,
    save_llm_config_impl as _save_llm_config,
    utcnow as _utcnow,
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
        "ai_disclosure": {
            "enabled": load_ai_disclosure_enabled(),
            "text": AI_DISCLOSURE_TEXT,
        },
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

    if section == "ai_disclosure":
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
            raise ValueError("ai_disclosure payload must be {enabled: bool}")
        _ = save_ai_disclosure_enabled(payload["enabled"])
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
        scalars.get("llm_provider")
        or os.environ.get("LLM_PROVIDER", _DEFAULT_LLM_PROVIDER)
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


def _load_policy_doc() -> tuple[dict[str, str], dict[str, list[str]]]:
    policy_path = _resolve_policy_path()
    if policy_path is None or not policy_path.exists():
        return {}, {}
    doc = parse_simple_yaml(policy_path.read_text(encoding="utf-8"))
    return doc.get("scalars", {}), doc.get("lists", {})


def _resolve_policy_path() -> Path | None:
    # 与排除名单共用同一规则，避免设置页把本机配置写回仓库默认策略文件。
    return resolve_policy_path()


# 兼容旧路径：探测逻辑已拆到 settings_llm_connection，这里继续 re-export。
from tools.sidecar.handlers.settings_llm_connection import (  # noqa: E402
    handle_settings_check_llm_connection,
)
