from __future__ import annotations

import os
from typing import Any

from tools.policy.exclusions import (
    load_exclusion_list,
    load_legal_entity_exclusion_list,
    save_exclusion_list,
    save_legal_entity_exclusion_list,
)


def handle_settings_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]

    api_key_configured = bool(os.environ.get("LLM_API_KEY"))
    exclusion_list = load_exclusion_list()
    legal_entity_exclusion_list = load_legal_entity_exclusion_list()

    return {
        "meta": {"correlation_id": correlation_id},
        "gate_policy": {
            "n_pass_required": 3,
            "matching_threshold": 70,
            "evaluation_threshold": 75,
            "max_rounds": 5,
            "gate_mode": "strict",
        },
        "exclusion_list": exclusion_list,
        "excluded_legal_entities": legal_entity_exclusion_list,
        "channels": [],
        "llm_config": {
            "provider": os.environ.get("LLM_PROVIDER", "openai"),
            "model": os.environ.get("LLM_MODEL", "gpt-4"),
            "base_url": os.environ.get("LLM_BASE_URL"),
            "api_key": {
                "configured": api_key_configured,
                "masked": True,
                "updated_at": "",
            },
            "timeout": 60,
            "temperature": 0.2,
        },
    }


def handle_settings_update(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    section = params.get("section")
    payload = params.get("payload")

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
