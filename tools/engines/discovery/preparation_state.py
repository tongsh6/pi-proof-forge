"""Pure saved-preparation projection. Fresh means input consistency, never fit or approval."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from tools.domain.job_lead_state import canonical_liepin_detail_url, current_jd_capture


def content_fingerprint(fields: Mapping[str, Any]) -> str:
    clean = {key: value for key, value in fields.items()
             if key not in {"preparation_json", "updated_at"}}
    return hashlib.sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def describe_preparation(profile_id, fields, lead, preferences, *, validate_direction: Callable,
                         preferences_error=""):
    # The adapter supplies the existing pure direction validator, not an IO capability.
    def result(state, reason, **extra):
        return {"state": state, "reason": reason, "scope": "input_consistency_only",
                "direction": None, "requirements_grounded": False, "requirement_count": 0,
                "evidence_precheck": None, "send_ready": False, **extra}
    raw = fields.get("preparation_json")
    if not raw:
        return result("absent", "preparation_absent")
    try:
        meta = json.loads(raw)
        required = {"status", "source_jd_sha256", "preferences_revision", "content_fingerprint",
                    "extraction_contract", "assessment_scope", "direction", "model_direction",
                    "direction_adjustment", "requirement_sources", "model", "provider", "endpoint"}
        if not isinstance(meta, dict) or not required.issubset(meta):
            return result("invalid", "preparation_metadata_invalid")
        if (meta["extraction_contract"] != "verbatim_requirements_v1"
                or meta["assessment_scope"] != "advisory_not_fit_or_approval"
                or meta["status"] not in {"prepared_unapproved", "direction_deferred"}):
            return result("invalid", "preparation_contract_unknown")
        if any(not isinstance(meta[key], str) or not meta[key] for key in
               ("source_jd_sha256", "preferences_revision", "content_fingerprint", "model", "provider", "endpoint")):
            return result("invalid", "preparation_metadata_invalid")
        if preferences_error or not preferences or not preferences.get("confirmed_at"):
            return result("stale", "preparation_preferences_unavailable")
        if preferences.get("revision") != meta["preferences_revision"]:
            return result("stale", "preparation_preferences_changed")
        if fields.get("status") != "draft" or fields.get("review_decision") or fields.get("reviewed_at"):
            return result("stale", "preparation_lifecycle_changed")
        body = fields.get("source_jd", "")
        digest = hashlib.sha256(body.encode()).hexdigest()
        if (not body.strip() or meta["source_jd_sha256"] != digest
                or fields.get("source_jd_sha256") != digest):
            return result("stale", "preparation_source_changed")
        if (not isinstance(lead, Mapping) or lead.get("source") != "liepin_official"
                or lead.get("id") != fields.get("job_lead_id")
                or lead.get("job_profile_id") != profile_id
                or not (capture := current_jd_capture(lead))
                or canonical_liepin_detail_url(fields.get("source_url")) != capture["source_url"]
                or lead.get("source_jd") != body or lead.get("source_jd_sha256") != digest
                or lead.get("jd_status") != "full_unreviewed"
                or lead.get("jd_origin") != "public_page" or lead.get("status", "new") != "new"
                or any(not fields.get(k) or fields.get(k) != lead.get(k)
                       for k in ("source", "platform", "platform_job_id", "platform_job_type"))):
            return result("stale", "preparation_binding_changed")
        if content_fingerprint(fields) != meta["content_fingerprint"]:
            return result("stale", "preparation_content_changed")
        def direction(value):
            checked = validate_direction({key: value[key] for key in
                                          ("status", "reason", "criterion_index", "jd_quote")},
                                         preferences, body)
            if checked["preference"] != value.get("preference"):
                raise ValueError("preference changed")
            return checked
        effective = direction(meta["direction"])
        original = direction(meta["model_direction"])
        if effective["status"] in {"aligned", "excluded"}:
            avoid = effective["preference"]["kind"] == "avoid"
            if (effective["status"] == "aligned" and avoid) or (effective["status"] == "excluded" and not avoid):
                return result("invalid", "preparation_direction_invalid")
        adjusted = original["status"] == "excluded" and original["preference"]["kind"] != "avoid"
        if adjusted:
            if (meta["direction_adjustment"] != "excluded_without_avoid_evidence"
                    or effective["status"] != "needs_review"
                    or any(effective[k] != original[k] for k in ("criterion_index", "jd_quote", "preference"))):
                return result("invalid", "preparation_direction_invalid")
        elif meta["direction_adjustment"] != "" or effective != original:
            return result("invalid", "preparation_direction_invalid")
        deferred = meta["status"] == "direction_deferred"
        if deferred != (effective["status"] == "excluded"):
            return result("invalid", "preparation_direction_invalid")
        sources = meta["requirement_sources"]
        if not isinstance(sources, list):
            return result("invalid", "preparation_requirements_invalid")
        if deferred:
            if sources:
                return result("invalid", "preparation_requirements_invalid")
        else:
            expected = []
            for kind in ("must_have", "nice_to_have"):
                values = fields.get(kind)
                if not isinstance(values, list):
                    return result("invalid", "preparation_requirements_invalid")
                for index, quote in enumerate(values):
                    if not isinstance(quote, str) or not quote.strip() or quote not in body:
                        return result("invalid", "preparation_requirements_invalid")
                    expected.append((kind, index, quote))
            if not fields.get("must_have") or len(sources) != len(expected):
                return result("invalid", "preparation_requirements_invalid")
            for source, (kind, index, quote) in zip(sources, expected):
                if (not isinstance(source, dict) or source.get("kind") != kind
                        or type(source.get("index")) is not int or source["index"] != index
                        or source.get("quote") != quote or type(source.get("start")) is not int
                        or type(source.get("end")) is not int
                        or not 0 <= source["start"] < source["end"] <= len(body)
                        or body[source["start"]:source["end"]] != quote):
                    return result("invalid", "preparation_requirements_invalid")
        return result("fresh", "preparation_direction_deferred" if deferred else "preparation_saved_unapproved",
                      direction=effective, requirements_grounded=not deferred, requirement_count=len(sources))
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        return result("invalid", "preparation_metadata_invalid")
