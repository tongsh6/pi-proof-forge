from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SIDECAR_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"1.0.0"})
SUPPORTED_CAPABILITIES = ["events", "file-preview"]

_current_state = "ready"


def handle_handshake(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    protocol_version = params.get("protocol_version", "")

    if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ValueError(f"UNSUPPORTED_VERSION: {protocol_version}")

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted_protocol_version": protocol_version,
        "sidecar_version": SIDECAR_VERSION,
        "capabilities": list(SUPPORTED_CAPABILITIES),
        "deprecations": [],
    }


def handle_ping(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "state": _current_state,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def handle_shutdown(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": True,
    }
