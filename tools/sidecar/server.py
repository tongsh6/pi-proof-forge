from __future__ import annotations

import json
import sys
from typing import Any

from tools.sidecar.error_mapper import ErrorMapper
from tools.sidecar.handlers.jobs import (
    handle_jobs_convert_lead,
    handle_jobs_create_profile,
    handle_jobs_delete_profile,
    handle_jobs_generate_profile_draft,
    handle_jobs_list_leads,
    handle_jobs_list_profiles,
    handle_jobs_search_liepin,
    handle_jobs_fetch_liepin_detail,
    handle_jobs_save_profile_draft,
    handle_jobs_update_profile,
)
from tools.sidecar.router import Router
from tools.sidecar.handlers import daily_delivery
from tools.sidecar.handlers import job_preferences
from tools.sidecar.lifecycle import handle_handshake, handle_ping, handle_shutdown
from tools.sidecar.handlers.evidence import (
    handle_evidence_create,
    handle_evidence_delete,
    handle_evidence_generate_draft,
    handle_list_material_documents,
    handle_read_material_document,
    handle_evidence_get,
    handle_evidence_import,
    handle_evidence_list,
    handle_evidence_save_draft,
    handle_evidence_reconcile,
    handle_evidence_triage_set,
    handle_evidence_confirm_inference,
    handle_evidence_infer_fields,
    handle_evidence_update,
)
from tools.sidecar.handlers.overview import handle_overview_get
from tools.sidecar.handlers.quality import handle_quality_decide_highlight
from tools.sidecar.handlers.native_pdf import handle_authorize_single_pdf_delivery, handle_prepare_pdf, handle_begin_upload, handle_finish_upload, handle_inspect_pdf_packet, handle_record_pdf_inspection
from tools.sidecar.handlers.native_pdf import handle_pdf_target_packet, handle_record_pdf_target
from tools.sidecar.handlers.native_pdf import handle_begin_pdf_delivery, handle_record_pdf_communication
from tools.sidecar.handlers.native_pdf import handle_pdf_interaction_packet, handle_record_pdf_interaction
from tools.sidecar.handlers.native_pdf import handle_verify_pdf_receipt, handle_begin_pdf_removal, handle_finish_pdf_removal, handle_recheck_pdf_removal
from tools.sidecar.handlers.profile import handle_profile_get, handle_profile_update, handle_profile_review, handle_profile_auto_link_evidence
from tools.sidecar.handlers.resume import (
    handle_resume_export_pdf,
    handle_resume_get_preview,
    handle_resume_list,
    handle_resume_upload,
)
from tools.sidecar.handlers.submission import (
    handle_channel_session_check,
    handle_channel_session_clear,
    handle_channel_session_get,
    handle_channel_session_start,
    handle_feedback_create_iteration,
    handle_feedback_list,
    handle_submission_check_mode,
    handle_submission_detail,
    handle_submission_list,
    handle_submission_record_manual,
    handle_submission_retry,
)
from tools.sidecar.handlers.agent import (
    handle_agent_get,
    handle_prepare_liepin_default,
    handle_recheck_receipt,
    handle_agent_start,
    handle_agent_stop,
    handle_create_review_candidates,
    handle_get_pending_review,
    handle_quick_cancel,
    handle_quick_get,
    handle_quick_start,
    handle_submit_review,
)
from tools.sidecar.handlers.settings import (
    handle_settings_check_llm_connection,
    handle_settings_clear_llm_api_key,
    handle_settings_get,
    handle_settings_update,
    handle_settings_liepin_credential,
    handle_settings_liepin_resume,
)
from tools.sidecar.handlers.materials import (
    handle_evidence_list_material_sources,
    handle_material_list,
    handle_material_readiness,
    handle_material_reference_create,
    handle_material_reference_refresh,
    handle_material_reference_remove,
    handle_material_reference_scan,
    handle_material_reference_status,
    handle_material_upload,
)


def _create_router() -> Router:
    router = Router()
    router.register("system.handshake", handle_handshake)
    router.register("system.ping", handle_ping)
    router.register("system.shutdown", handle_shutdown)
    router.register("evidence.list", handle_evidence_list)
    router.register("evidence.get", handle_evidence_get)
    router.register("evidence.listMaterialSources", handle_evidence_list_material_sources)
    router.register("evidence.create", handle_evidence_create)
    router.register("evidence.update", handle_evidence_update)
    router.register("evidence.delete", handle_evidence_delete)
    router.register("evidence.import", handle_evidence_import)
    router.register("evidence.generateDraft", handle_evidence_generate_draft)
    router.register("evidence.listMaterialDocuments", handle_list_material_documents)
    router.register("evidence.readMaterialDocument", handle_read_material_document)
    router.register("evidence.saveDraft", handle_evidence_save_draft)
    router.register("evidence.reconcile", handle_evidence_reconcile)
    router.register("evidence.triage.set", handle_evidence_triage_set)
    router.register("evidence.inferFields", handle_evidence_infer_fields)
    router.register("evidence.confirmInference", handle_evidence_confirm_inference)
    router.register("jobs.listLeads", handle_jobs_list_leads)
    router.register("jobs.searchLiepin", handle_jobs_search_liepin)
    router.register("jobs.fetchLiepinDetail", handle_jobs_fetch_liepin_detail)
    router.register("jobs.convertLead", handle_jobs_convert_lead)
    router.register("jobs.listProfiles", handle_jobs_list_profiles)
    router.register("jobs.createProfile", handle_jobs_create_profile)
    router.register("jobs.updateProfile", handle_jobs_update_profile)
    router.register("jobs.deleteProfile", handle_jobs_delete_profile)
    router.register("jobs.generateProfileDraft", handle_jobs_generate_profile_draft)
    router.register("jobs.saveProfileDraft", handle_jobs_save_profile_draft)
    router.register("overview.get", handle_overview_get)
    router.register("quality.decideHighlight", handle_quality_decide_highlight)
    router.register("profile.get", handle_profile_get)
    router.register("profile.generateJobPreferences", job_preferences.handle_generate)
    router.register("profile.saveJobPreferences", job_preferences.handle_save)
    router.register("profile.update", handle_profile_update)
    router.register("profile.review", handle_profile_review)
    router.register("profile.autoLinkEvidence", handle_profile_auto_link_evidence)
    router.register("resume.list", handle_resume_list)
    router.register("resume.upload", handle_resume_upload)
    router.register("resume.getPreview", handle_resume_get_preview)
    router.register("resume.exportPdf", handle_resume_export_pdf)
    router.register("material.upload", handle_material_upload)
    router.register("material.list", handle_material_list)
    router.register("material.readiness", handle_material_readiness)
    router.register("material.reference.scan", handle_material_reference_scan)
    router.register("material.reference.create", handle_material_reference_create)
    router.register("material.reference.status", handle_material_reference_status)
    router.register("material.reference.refresh", handle_material_reference_refresh)
    router.register("material.reference.remove", handle_material_reference_remove)
    router.register("submission.detail", handle_submission_detail)
    router.register("submission.list", handle_submission_list)
    router.register("submission.retry", handle_submission_retry)
    router.register("submission.recordManual", handle_submission_record_manual)
    router.register("submission.channelSession.get", handle_channel_session_get)
    router.register("submission.channelSession.start", handle_channel_session_start)
    router.register("submission.channelSession.check", handle_channel_session_check)
    router.register("submission.channelSession.clear", handle_channel_session_clear)
    router.register("submission.checkMode.start", handle_submission_check_mode)
    router.register("submission.feedback.list", handle_feedback_list)
    router.register("submission.feedback.createIteration", handle_feedback_create_iteration)
    from tools.sidecar.handlers.platform_feedback import handle_sync_packet, handle_record_platform_status
    router.register("submission.feedback.syncPacket", handle_sync_packet)
    router.register("submission.feedback.recordPlatformStatus", handle_record_platform_status)
    router.register("settings.get", handle_settings_get)
    router.register("settings.liepinCredential", handle_settings_liepin_credential)
    router.register("settings.liepinResume", handle_settings_liepin_resume)
    router.register("settings.update", handle_settings_update)
    router.register("settings.checkLlmConnection", handle_settings_check_llm_connection)
    router.register("settings.clearLlmApiKey", handle_settings_clear_llm_api_key)
    router.register("run.quick.start", handle_quick_start)
    router.register("run.quick.get", handle_quick_get)
    router.register("run.quick.cancel", handle_quick_cancel)
    router.register("run.agent.start", handle_agent_start)
    router.register("run.agent.get", handle_agent_get)
    router.register("run.agent.prepareLiepinDefault", handle_prepare_liepin_default)
    router.register("run.agent.prepareLiepinPdf", handle_prepare_pdf)
    router.register("run.agent.authorizeSinglePdfDelivery", handle_authorize_single_pdf_delivery)
    router.register("run.agent.beginPdfUpload", handle_begin_upload)
    router.register("run.agent.finishPdfUpload", handle_finish_upload)
    router.register("run.agent.inspectPdfPacket", handle_inspect_pdf_packet)
    router.register("run.agent.recordPdfInspection", handle_record_pdf_inspection)
    router.register("run.agent.pdfTargetPacket", handle_pdf_target_packet)
    router.register("run.agent.recordPdfTarget", handle_record_pdf_target)
    router.register("run.agent.beginPdfDelivery", handle_begin_pdf_delivery)
    router.register("run.agent.recordPdfCommunication", handle_record_pdf_communication)
    router.register("run.agent.pdfInteractionPacket", handle_pdf_interaction_packet)
    router.register("run.agent.recordPdfInteraction", handle_record_pdf_interaction)
    router.register("run.agent.verifyPdfReceipt", handle_verify_pdf_receipt)
    router.register("run.agent.beginPdfRemoval", handle_begin_pdf_removal)
    router.register("run.agent.finishPdfRemoval", handle_finish_pdf_removal)
    router.register("run.agent.recheckPdfRemoval", handle_recheck_pdf_removal)
    router.register("run.agent.recheckReceipt", handle_recheck_receipt)
    router.register("run.agent.stop", handle_agent_stop)
    router.register("run.agent.getPendingReview", handle_get_pending_review)
    router.register("run.agent.submitReview", handle_submit_review)
    router.register("run.agent.createReviewCandidates", handle_create_review_candidates)
    for name in ("status", "save", "change", "claim", "check", "finish", "permit", "preview"):
        router.register("daily."+name,lambda params, handler=getattr(daily_delivery,"handle_"+name): {"meta":params["meta"],**handler(params)})
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
    try:
        run_stdio_loop()
    finally:
        from tools.infra.liepin_readonly import liepin_readonly
        liepin_readonly.unload()
        from tools.infra.browser.liepin_session import session_browser
        session_browser.close()
