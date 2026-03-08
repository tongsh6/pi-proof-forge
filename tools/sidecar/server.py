from __future__ import annotations

import json
import sys
from typing import Any

from tools.sidecar.error_mapper import ErrorMapper
from tools.sidecar.router import Router
from tools.sidecar.lifecycle import handle_handshake, handle_ping, handle_shutdown
from tools.sidecar.handlers.evidence import handle_evidence_list, handle_evidence_get
from tools.sidecar.handlers.overview import handle_overview_get
from tools.sidecar.handlers.settings import handle_settings_get, handle_settings_update


def _create_router() -> Router:
    router = Router()
    router.register("system.handshake", handle_handshake)
    router.register("system.ping", handle_ping)
    router.register("system.shutdown", handle_shutdown)
    router.register("evidence.list", handle_evidence_list)
    router.register("evidence.get", handle_evidence_get)
    router.register("overview.get", handle_overview_get)
    router.register("settings.get", handle_settings_get)
    router.register("settings.update", handle_settings_update)
    return router


_router = _create_router()


def build_success_response(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def build_error_response(
    request_id: str, code: str, message: str, correlation_id: str
) -> dict[str, Any]:
    err = ErrorMapper.create(code, message, correlation_id)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": err.to_dict(),
    }


def process_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id", "")
    method = request.get("method", "")
    params = request.get("params")

    if params is None or not isinstance(params, dict):
        return build_error_response(
            request_id, "VALIDATION_ERROR", "params is required", ""
        )

    meta = params.get("meta")
    if not isinstance(meta, dict) or "correlation_id" not in meta:
        return build_error_response(
            request_id, "VALIDATION_ERROR", "params.meta.correlation_id is required", ""
        )

    correlation_id = meta["correlation_id"]

    try:
        result = _router.dispatch(method, params)
        return build_success_response(request_id, result)
    except KeyError as e:
        error_str = str(e)
        if "NOT_FOUND" in error_str:
            return build_error_response(
                request_id, "NOT_FOUND", error_str, correlation_id
            )
        return build_error_response(
            request_id, "VALIDATION_ERROR", f"Unknown method: {method}", correlation_id
        )
    except ValueError as e:
        error_str = str(e)
        if "UNSUPPORTED_VERSION" in error_str:
            return build_error_response(
                request_id, "UNSUPPORTED_VERSION", error_str, correlation_id
            )
        return build_error_response(
            request_id, "VALIDATION_ERROR", error_str, correlation_id
        )
    except Exception as e:
        return build_error_response(
            request_id, "INTERNAL_ERROR", str(e), correlation_id
        )


def run_stdio_loop() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            resp = build_error_response("", "VALIDATION_ERROR", "Invalid JSON", "")
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        response = process_request(request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

        if request.get("method") == "system.shutdown":
            break


if __name__ == "__main__":
    run_stdio_loop()
