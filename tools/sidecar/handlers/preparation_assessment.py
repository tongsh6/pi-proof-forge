"""Source-bound semantic preparation. Advisory only; no approval or delivery."""
from __future__ import annotations
import hashlib
import json
import threading
from tools.domain.job_lead_state import canonical_liepin_detail_url, current_jd_capture
from tools.infra.job_preferences import load_preferences, assess_direction, validate_direction
from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.sidecar.handlers import jobs
from tools.sidecar.handlers._shared.profile_state import profile_path
from tools.sidecar.handlers._shared.llm_config import load_llm_config
from tools.sidecar.handlers.jobs_profiles import handle_jobs_generate_profile_draft

_LOCK = threading.Lock()
_SPLASH = "http://127.0.0.1:8000/v1"

from tools.engines.discovery.preparation_state import content_fingerprint as _fingerprint

def _bound(profile_id):
    path = jobs._profile_path(profile_id)
    raw = path.read_bytes()
    fields = jobs._preserved_profile_fields(parse_simple_yaml(raw.decode("utf-8")))
    if fields.get("status") != "draft" or fields.get("review_decision") or fields.get("reviewed_at"):
        raise ValueError("profile_not_unapproved")
    if not fields.get("job_lead_id"):
        raise ValueError("source_binding_mismatch")
    lead_path = jobs._lead_path(fields["job_lead_id"])
    lead_raw = lead_path.read_bytes()
    lead = parse_simple_yaml(lead_raw.decode("utf-8"))["scalars"]
    body = fields.get("source_jd", "")
    digest = hashlib.sha256(body.encode()).hexdigest()
    if (not body.strip() or lead.get("source") != "liepin_official"
            or not (capture := current_jd_capture(lead))
            or canonical_liepin_detail_url(fields.get("source_url")) != capture["source_url"]
            or fields.get("job_lead_id") != lead.get("id")
            or lead.get("job_profile_id") != profile_id
            or lead.get("status", "new") != "new"
            or lead.get("jd_status") != "full_unreviewed"
            or lead.get("jd_origin") != "public_page"
            or lead.get("source_jd") != body
            or fields.get("source_jd_sha256") != digest
            or lead.get("source_jd_sha256") != digest
            or any(not fields.get(key) or fields.get(key) != lead.get(key)
                   for key in ("source", "platform", "platform_job_id", "platform_job_type"))):
        raise ValueError("source_binding_mismatch")
    return path, raw, fields, lead_path, lead_raw, digest

def is_source_only_draft(fields):
    """Call after binding validation; already assessed or manual drafts are not resumable."""
    return not fields.get("preparation_json") and fields.get("import_mode") != "manual"


def _requirements(draft, body):
    sources = []
    for kind in ("must_have", "nice_to_have"):
        values = draft.get(kind)
        if not isinstance(values, list):
            raise ValueError("requirement_source_missing")
        for index, text in enumerate(values):
            if not isinstance(text, str) or not text.strip() or text not in body:
                raise ValueError("requirement_source_missing")
            start = body.index(text)
            sources.append({"kind":kind, "index":index, "quote":text, "start":start, "end":start+len(text)})
    if not draft.get("must_have"):
        raise ValueError("requirements_incomplete")
    return sources

def handle_assess_preparation(params):
    profile_id = str(params.get("job_profile_id") or "")
    result = {"meta":params["meta"], "status":"blocked", "code":"assessment_unavailable",
              "job_profile_id":profile_id, "direction":None, "requirements_grounded":False,
              "requirement_count":0, "model_calls":0, "active_target_eligible":False, "send_ready":False}
    if not _LOCK.acquire(blocking=False):
        return {**result, "code":"assessment_busy"}
    stage = "inputs"
    try:
        path, raw, fields, lead_path, lead_raw, digest = _bound(profile_id)
        if params.get("resume_source_only") is True and not is_source_only_draft(fields):
            return {**result, "code":"preparation_resume_unavailable"}
        preferences = load_preferences(profile_path())
        if not preferences or not preferences.get("confirmed_at") or not preferences.get("revision"):
            raise ValueError("preferences_not_confirmed")
        config = load_llm_config()
        if (config.get("provider") != "openai_compatible"
                or str(config.get("base_url", "")).rstrip("/") != _SPLASH
                or not str(config.get("model", "")).strip()):
            raise ValueError("local_splash_required")
        config = {**config, "timeout":min(60, max(1, int(config.get("timeout", 60))))}
        client = LLMClient(base_url=config["base_url"], api_key=str(config.get("api_key_for_request", "")),
                           timeout=config["timeout"], provider=config["provider"],
                           thinking_enabled=config.get("thinking_enabled"),
                           reasoning_effort=str(config.get("thinking_effort", "high")))
        stage = "direction"
        direction = assess_direction(preferences, fields["source_jd"], client, str(config["model"]),
                                     jobs._JOB_PROFILE_DIR.parent / "outputs" / "cache" / "preparation_direction")
        result["model_calls"] += int(direction.get("model_calls", 0))
        try:
            validated = validate_direction({key:direction[key] for key in
                                           ("status", "reason", "criterion_index", "jd_quote")},
                                          preferences, fields["source_jd"])
            if validated["status"] == "aligned" and validated["preference"]["kind"] == "avoid":
                raise ValueError("aligned_avoid")
        except (ValueError, KeyError, TypeError):
            raise ValueError("direction_invalid") from None
        model_direction = dict(validated)
        direction_adjustment = ""
        if validated["status"] == "excluded" and validated["preference"]["kind"] != "avoid":
            direction_adjustment = "excluded_without_avoid_evidence"
            validated = {**validated, "status":"needs_review",
                         "reason":"模型排除建议未引用已确认回避项，不能据此自动暂缓；方向仍待核实。"}
        result["direction"] = validated
        deferred = validated["status"] == "excluded"
        draft, sources = {}, []
        if not deferred:
            stage = "requirements"
            result["model_calls"] += 1
            generated = handle_jobs_generate_profile_draft(
                {"meta":params["meta"], "jd_text":fields["source_jd"], "source_url":fields["source_url"],
                 "job_lead_id":fields["job_lead_id"], "strict_extract":True}, llm_config_override=config)
            draft = generated.get("draft")
            if generated.get("code") != "OK" or not isinstance(draft, dict):
                raise ValueError("draft_generation_failed")
            sources = _requirements(draft, fields["source_jd"])
        stage = "snapshot"
        fresh_preferences = load_preferences(profile_path())
        if (path.read_bytes() != raw or lead_path.read_bytes() != lead_raw
                or not fresh_preferences or fresh_preferences.get("revision") != preferences["revision"]):
            raise ValueError("assessment_inputs_changed")
        # Copy only semantic fields; identity, original JD and review authority stay owned by existing source.
        updated = dict(fields)
        for key in ("jd_summary", "description", "keywords", "must_have", "nice_to_have", "seniority_signal"):
            if key in draft:
                updated[key] = draft[key]
        updated.update(status="draft", review_decision="", reviewed_at="", updated_at=jobs._utcnow_iso())
        metadata = {"status":"direction_deferred" if deferred else "prepared_unapproved",
                    "model_calls_scope":"logical_stage_calls_not_http_retries", "source_jd_sha256":digest,
                    "preferences_revision":preferences["revision"], "direction":validated,
                    "model_direction":model_direction, "direction_adjustment":direction_adjustment,
                    "model":config["model"], "provider":config["provider"], "endpoint":config["base_url"],
                    "extraction_contract":"verbatim_requirements_v1",
                    "requirement_sources":sources, "model_calls":result["model_calls"],
                    "content_fingerprint":_fingerprint(updated), "assessment_scope":"advisory_not_fit_or_approval"}
        updated["preparation_json"] = json.dumps(metadata, ensure_ascii=False)
        stage = "save"
        jobs._write_job_profile_file(path, updated)
        return {**result, "status":"deferred" if deferred else "prepared", "code":"direction_excluded" if deferred else "OK", "requirements_grounded":not deferred,
                "requirement_count":len(sources)}
    except Exception as exc:
        safe = {"profile_not_unapproved", "source_binding_mismatch", "preferences_not_confirmed",
                "local_splash_required", "direction_invalid", "requirement_source_missing",
                "requirements_incomplete", "assessment_inputs_changed", "draft_generation_failed",
                "job_preferences_source_changed", "invalid_job_profile_id"}
        code = str(exc) if str(exc) in safe else "assessment_"+stage+"_failed"
        return {**result, "code":code}
    finally:
        _LOCK.release()
