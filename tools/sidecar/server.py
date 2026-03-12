from __future__ import annotations

import json
import sys
from typing import Any

from tools.sidecar.error_mapper import ErrorMapper
from tools.sidecar.handlers.jobs import (
    handle_jobs_convert_lead,
    handle_jobs_create_profile,
    handle_jobs_delete_profile,
    handle_jobs_list_leads,
    handle_jobs_list_profiles,
    handle_jobs_update_profile,
)
from tools.sidecar.router import Router
from tools.sidecar.lifecycle import handle_handshake, handle_ping, handle_shutdown
from tools.sidecar.handlers.evidence import (
    handle_evidence_create,
    handle_evidence_delete,
    handle_evidence_get,
    handle_evidence_import,
    handle_evidence_list,
    handle_evidence_update,
)
from tools.sidecar.handlers.overview import handle_overview_get
from tools.sidecar.handlers.profile import handle_profile_get, handle_profile_update
from tools.sidecar.handlers.resume import (
    handle_resume_export_pdf,
    handle_resume_get_preview,
    handle_resume_list,
    handle_resume_upload,
)
from tools.sidecar.handlers.submission import (
    handle_submission_list,
    handle_submission_retry,
)
from tools.sidecar.handlers.agent import (
    handle_get_pending_review,
    handle_submit_review,
)
from tools.sidecar.handlers.settings import handle_settings_get, handle_settings_update


def _create_router() -> Router:
    router = Router()
    router.register("system.handshake", handle_handshake)
    router.register("system.ping", handle_ping)
    router.register("system.shutdown", handle_shutdown)
    router.register("evidence.list", handle_evidence_list)
    router.register("evidence.get", handle_evidence_get)
    router.register("evidence.create", handle_evidence_create)
    router.register("evidence.update", handle_evidence_update)
    router.register("evidence.delete", handle_evidence_delete)
    router.register("evidence.import", handle_evidence_import)
    router.register("jobs.listLeads", handle_jobs_list_leads)
    router.register("jobs.convertLead", handle_jobs_convert_lead)
    router.register("jobs.listProfiles", handle_jobs_list_profiles)
    router.register("jobs.createProfile", handle_jobs_create_profile)
    router.register("jobs.updateProfile", handle_jobs_update_profile)
    router.register("jobs.deleteProfile", handle_jobs_delete_profile)
    router.register("overview.get", handle_overview_get)
    router.register("profile.get", handle_profile_get)
    router.register("profile.update", handle_profile_update)
    router.register("resume.list", handle_resume_list)
    router.register("resume.upload", handle_resume_upload)
    router.register("resume.getPreview", handle_resume_get_preview)
    router.register("resume.exportPdf", handle_resume_export_pdf)
    router.register("submission.list", handle_submission_list)
    router.register("submission.retry", handle_submission_retry)
    router.register("settings.get", handle_settings_get)
    router.register("settings.update", handle_settings_update)
    router.register("run.agent.getPendingReview", handle_get_pending_review)
    router.register("run.agent.submitReview", handle_submit_review)
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
        error_str = str(e)
        if error_str.startswith("CONFLICT:"):
            return build_error_response(
                request_id, "CONFLICT", error_str, correlation_id
            )
        return build_error_response(
            request_id, "INTERNAL_ERROR", error_str, correlation_id
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
