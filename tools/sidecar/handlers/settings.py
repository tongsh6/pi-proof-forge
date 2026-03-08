from __future__ import annotations

import os
from typing import Any


def handle_settings_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]

    api_key_configured = bool(os.environ.get("LLM_API_KEY"))

    return {
        "meta": {"correlation_id": correlation_id},
        "gate_policy": {
            "n_pass_required": 3,
            "matching_threshold": 70,
            "evaluation_threshold": 75,
            "max_rounds": 5,
            "gate_mode": "strict",
        },
        "exclusion_list": [],
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
