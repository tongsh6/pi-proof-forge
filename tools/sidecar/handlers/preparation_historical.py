"""Explicit offline review of an immutable, already reviewed official target."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import re

from tools.domain.job_lead_state import JD_CAPTURE_KEY, canonical_liepin_detail_url, current_jd_capture

from tools.infra.job_preferences import assess_direction, validate_direction
from tools.sidecar.handlers import preparation_preview as preview
from tools.sidecar.handlers import preparation_semantic as semantic
from tools.sidecar.handlers.preparation_assessment import _requirements


def validate_historical_source(profile_id, fields, lead):
    if (fields.get("status") != "active" or fields.get("review_decision") != "approved"
            or not fields.get("reviewed_at")):
        raise ValueError("historical_not_reviewed")
    body = fields.get("source_jd", "")
    digest = hashlib.sha256(body.encode()).hexdigest()
    canonical = canonical_liepin_detail_url(fields.get("source_url"))
    job_id = fields.get("platform_job_id", "")
    kind = fields.get("platform_job_type")
    # Company display IDs differ from official job IDs; do not guess a mapping offline.
    valid_route = bool(canonical and
                       ((kind == "1" and canonical == f"https://www.liepin.com/a/{job_id}.shtml")
                        or (kind == "2" and "/job/" in canonical)))
    if (not body.strip() or not valid_route
            or not re.fullmatch(r"[0-9]+", job_id)
            or fields.get("source") != "liepin_official" or fields.get("platform") != "liepin"
            or lead.get("jd_status") != "complete_reviewed" or lead.get("status") != "new"
            or lead.get("id") != fields.get("job_lead_id") or lead.get("job_profile_id") != profile_id
            or canonical_liepin_detail_url(lead.get("url")) != canonical
            or (JD_CAPTURE_KEY in lead and not current_jd_capture(lead))
            or fields.get("jd_origin") != "public_page" or lead.get("jd_origin") != "public_page"
            or fields.get("source_jd_sha256") != digest or lead.get("source_jd_sha256") != digest
            or lead.get("source_jd") != body
            or any(not fields.get(k) or fields[k] != lead.get(k)
                   for k in ("source", "platform", "platform_job_id", "platform_job_type"))):
        raise ValueError("historical_source_binding_invalid")
    sources = _requirements({key:fields.get(key, []) for key in ("must_have", "nice_to_have")}, body)
    headings = list(re.finditer(r"(?im)^[ \t]*(任职要求|职位要求|任职资格|任职条件|岗位要求|Requirements|Qualifications|加分项|加分经历|Nice to have|Preferred qualifications|工作职责|岗位职责|Responsibilities)[ \t]*[:：]?[ \t]*$", body))
    ranges = {"must_have":[], "nice_to_have":[]}
    for index, heading in enumerate(headings):
        label = heading[1].lower()
        kind = ("must_have" if label in {"任职要求","职位要求","任职资格","任职条件","岗位要求",
                                         "requirements","qualifications"} else
                "nice_to_have" if label in {"加分项","加分经历","nice to have","preferred qualifications"} else None)
        if kind:
            ranges[kind].append((heading.end(), headings[index+1].start() if index+1 < len(headings) else len(body)))
    for source in sources:
        sections = ranges[source["kind"]]
        start, end = source["start"], source["end"]
        line_start = body.rfind("\n", 0, start) + 1
        line_end = body.find("\n", end)
        line_end = len(body) if line_end < 0 else line_end
        raw_line = body[line_start:line_end].strip()
        clause = re.sub(r"^(?:[0-9]+[.、)）]|[◦•·▪*\-])\s*", "", raw_line)
        clean = lambda value:value.strip().rstrip("。；;")
        if (len(sections) != 1 or not sections[0][0] <= start < end <= sections[0][1]
                or body.count(source["quote"]) != 1 or "\n" in source["quote"]
                or clean(source["quote"]) not in {clean(raw_line),clean(clause)}):
            raise ValueError("historical_requirement_section_invalid")
    return sources


def _inputs(profile_id):
    return semantic._inputs(profile_id, historical_validator=validate_historical_source)


def handle_review_historical_preparation(params):
    profile_id = str(params.get("job_profile_id") or "")
    out = {"meta":params["meta"], **preview._base(profile_id), "scope":"historical_internal_quality_only",
           "code":"historical_review_unavailable", "evidence_pool":{}, "assessment_counts":{}}
    # Share the existing advisory busy boundary, but never create a reusable audit.
    if not semantic._LOCK.acquire(blocking=False):
        return {**out, "code":"semantic_preparation_busy"}
    client = None
    try:
        inputs = _inputs(profile_id)
        out["evidence_pool"] = inputs["pool"]
        config = semantic.load_llm_config()
        if (config.get("provider") != "openai_compatible"
                or str(config.get("base_url", "")).rstrip("/") != semantic.SPLASH
                or not str(config.get("model", "")).strip()):
            raise ValueError("local_splash_required")
        if _inputs(profile_id)["snapshot"] != inputs["snapshot"]:
            raise ValueError("semantic_inputs_changed")
        model = str(config["model"])
        client = semantic.BoundedLocalClient(model=model, api_key=str(config.get("api_key_for_request") or ""),
                                             thinking_enabled=config.get("thinking_enabled"),
                                             reasoning_effort=str(config.get("thinking_effort", "high")))
        with TemporaryDirectory(prefix="ppf-historical-review-") as tmp:
            cache = Path(tmp)
            preferences, body = inputs["preferences"], inputs["job_fields"]["source_jd"]
            direction = assess_direction(preferences, body, client, model, cache)
            direction = validate_direction({k: direction[k] for k in
                                           ("status", "reason", "criterion_index", "jd_quote")}, preferences, body)
            avoid = direction["preference"]["kind"] == "avoid"
            if direction["status"] == "aligned" and avoid:
                raise ValueError("direction_invalid")
            if direction["status"] == "excluded" and avoid:
                raise ValueError("historical_direction_excluded")
            if direction["status"] == "excluded":
                direction = {**direction, "status":"needs_review", "reason":"排除建议无已确认回避项依据"}
            if _inputs(profile_id)["snapshot"] != inputs["snapshot"]:
                raise ValueError("semantic_inputs_changed")
            inputs = {**inputs, "direction":direction}

            def preserve_assessment_budget(stage):
                if stage == "recall" and client.model_calls >= 2:
                    client.budget_exhausted = True
                    raise ValueError("semantic_stage_budget_deferred")

            raw = semantic.run_semantic_matching(
                job_path=inputs["job_path"], evidence_files=inputs["evidence_files"],
                personal_profile=inputs["personal_profile"], client=client, model=model,
                cache_dir=cache, batch_size=8, advisory=True, reused_direction=direction,
                before_model_call=preserve_assessment_budget,
                requirement_section_bindings=inputs["requirement_section_bindings"])
            summary = semantic._safe_summary(profile_id, inputs, client, raw, "")
            out.update(assessment_counts=summary["assessment_counts"],
                       assessed_scope=raw.get("assessment_scope", {}),
                       reviewed_card_count=summary["reviewed_card_count"],
                       semantic_code=summary["code"],
                       source_freshness_unverified_count=inputs["pool"]["source_freshness_unverified_count"])
            excerpt = preview.render_reviewed_excerpt(profile_id, inputs, raw)
            if any(claim["source_id"] in raw.get("presentation_exclusions", {})
                   for claim in excerpt["claims"]):
                raise ValueError("historical_preview_excluded_fact")
            if _inputs(profile_id)["snapshot"] != inputs["snapshot"]:
                raise ValueError("semantic_inputs_changed")
            return {**out, **excerpt, "status":"preview", "code":"historical_preview_partial_ready",
                    "input_fresh":True, "model_calls":client.model_calls}
    except (ValueError, OSError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
        allowed = {"historical_not_reviewed", "historical_source_binding_invalid", "historical_preferences_unconfirmed",
                   "requirement_source_missing", "requirements_incomplete", "historical_requirement_section_invalid",
                   "local_splash_required",
                   "historical_direction_excluded", "direction_invalid", "semantic_inputs_changed",
                   "semantic_no_eligible_evidence", "semantic_career_unconfirmed", "semantic_provider_timeout",
                   "semantic_budget_exhausted", "preview_audit_invalid", "preview_fact_changed", "historical_preview_excluded_fact",
                   "no_presentable_supported_work", "internal_metadata_in_resume_fact", "invalid_job_lead_id",
                   "invalid_job_profile_id"}
        return {**out, "code":str(exc) if str(exc) in allowed else out["code"],
                "model_calls":client.model_calls if client is not None else 0}
    finally:
        semantic._LOCK.release()
