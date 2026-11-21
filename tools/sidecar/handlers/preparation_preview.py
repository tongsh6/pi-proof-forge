"""Read-only bridge from a current advisory audit to internal factual excerpts."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from tools.engines.generation.preparation_preview import build_targeted_excerpt
from tools.engines.matching.semantic_matching import _facts, _profile_facts, VERSION
from tools.engines.matching.semantic_review import requirement_checks, validate_assessments, aggregate_assessments
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.evidence_fact_scope import personal_claim_exclusions
from tools.infra.material_paths import materials_dir_for
from tools.sidecar.handlers import preparation_semantic as semantic


def _base(profile_id):
    return {"status":"blocked", "code":"preview_inputs_unavailable", "job_profile_id":profile_id,
            "scope":"internal_targeted_excerpt", "input_fresh":False, "markdown":"", "claims":[],
            "limitations":[], "source_audit_digest":"", "preview_fact_count":0, "partial":True,
            "model_calls":0, "active_target_eligible":False, "deliverable":False, "send_ready":False,
            "trace":{}, "source_freshness_unverified_count":None}


def _read_audit(profile_id, inputs):
    path = semantic._audit_path(profile_id)
    if not path.is_file():
        raise ValueError("preview_audit_missing")
    data = path.read_bytes()
    try:
        record = json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError("preview_audit_invalid") from None
    if (not isinstance(record, dict) or record.get("schema_version") != 1
            or record.get("digest") != semantic._record_digest(record)):
        raise ValueError("preview_audit_invalid")
    summary, raw = record.get("summary"), record.get("result")
    if not isinstance(summary, dict) or not isinstance(raw, dict):
        raise ValueError("preview_audit_invalid")
    if summary.get("job_profile_id") != profile_id or raw.get("job_profile_id") != profile_id:
        raise ValueError("preview_target_mismatch")
    if (summary.get("scope") != "advisory_partial" or raw.get("advisory_scope") is not True
            or raw.get("method") != VERSION):
        raise ValueError("preview_audit_invalid")
    if record.get("snapshot") != inputs["snapshot"] or summary.get("input_fresh") is not True:
        raise ValueError("preview_inputs_changed")
    return record, hashlib.sha256(data).hexdigest()


def render_reviewed_excerpt(profile_id, inputs, raw):
    if (raw.get("job_profile_id") != profile_id or raw.get("advisory_scope") is not True
            or raw.get("method") != VERSION):
        raise ValueError("preview_audit_invalid")
    # Reuse canonical clause validation/aggregation rather than trusting persisted summary labels.
    checks = requirement_checks(raw["requirements"])
    if checks != raw.get("requirement_checks"):
        raise ValueError("preview_audit_invalid")
    validated = validate_assessments({"assessments":raw["criterion_assessments"]}, raw["facts"], checks)
    if aggregate_assessments(raw["requirements"], checks, validated) != raw["assessments"]:
        raise ValueError("preview_audit_invalid")
    completed = raw.get("completed_check_ids", [])
    if not isinstance(completed, list) or any(not isinstance(c, str) for c in completed):
        raise ValueError("preview_audit_invalid")
    unfinished = {c["id"] for c in checks} - set(completed)
    safe_raw = {**raw, "budget_deferred_check_ids":sorted(unfinished | set(raw.get("budget_deferred_check_ids", [])))}
    flags = SimpleNamespace(model_calls=0, budget_exhausted=False, provider_timeout=False)
    summary = semantic._safe_summary(profile_id, inputs, flags, safe_raw, "")
    current_facts = _profile_facts(inputs["personal_profile"])
    excluded = set()
    material_dir = materials_dir_for(inputs["personal_profile"])
    for path in inputs["evidence_files"]:
        doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        excluded.update(personal_claim_exclusions(doc, material_dir, card_id=path.stem))
        current_facts.update(_facts(path.stem, doc))
    fields = parse_simple_yaml(inputs["job_path"].read_text(encoding="utf-8"))["scalars"]
    target = {key:fields.get(key, "") for key in ("company", "target_role")}
    excerpt = build_targeted_excerpt(assessments=summary["assessments"], requirements=raw["requirements"],
                audit_facts=raw["facts"], current_facts=current_facts, target=target, personal_claim_exclusions=excluded)
    legacy_count = inputs.get("pool", {}).get("source_freshness_unverified_count", 0)
    if legacy_count:
        excerpt["markdown"] = (f"> 当前证据池有 {legacy_count} 条沿用旧审核兼容口径，来源版本未重验；不代表本预览全部来源已重新核验。\n\n" + excerpt["markdown"])
    return excerpt


def handle_preview_preparation(params):
    profile_id = str(params.get("job_profile_id") or "")
    base = {"meta":params["meta"], **_base(profile_id)}
    try:
        inputs = semantic._inputs(profile_id)
        base["source_freshness_unverified_count"] = inputs.get("pool", {}).get("source_freshness_unverified_count", 0)
        record, audit_hash = _read_audit(profile_id, inputs)
        raw = record["result"]
        excerpt = render_reviewed_excerpt(profile_id, inputs, raw)
        current = semantic._inputs(profile_id)
        _, final_audit_hash = _read_audit(profile_id, current)
        if current["snapshot"] != inputs["snapshot"] or final_audit_hash != audit_hash:
            raise ValueError("preview_inputs_changed")
        return {**base, **excerpt, "status":"preview", "code":"preview_partial_ready", "input_fresh":True,
                "source_audit_digest":record["digest"], "trace":{"job_profile_id":profile_id,
                    "input_snapshot":inputs["snapshot"], "source_audit_digest":record["digest"]}}
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        allowed = {"preview_audit_missing", "preview_audit_invalid", "preview_target_mismatch",
                   "preview_inputs_changed", "preview_fact_changed", "no_presentable_supported_work"}
        code = str(exc) if str(exc) in allowed else (
            "preview_render_blocked" if str(exc) == "internal_metadata_in_resume_fact" else "preview_inputs_unavailable")
        return {**base, "code":code}
