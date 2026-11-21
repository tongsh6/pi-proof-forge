"""Bounded advisory semantic work, isolated from canonical matching and delivery."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from tools.engines.discovery.preparation_state import describe_preparation
from tools.engines.matching.requirement_sections import bind_explicit_requirement_sections
from tools.engines.matching.semantic_matching import run_semantic_matching, VERSION
from tools.infra.career_profile import load_career_profile
from tools.infra.evidence_sources import assert_captured_source, validated_source_inputs
from tools.infra.job_preferences import load_preferences, validate_direction
from tools.infra.llm.bounded_local import BoundedLocalClient, SPLASH
from tools.infra.material_paths import materials_dir_for
from tools.infra.persistence.atomic_io import atomic_write_json
from tools.infra.persistence.review_queue import locked_review_queue
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.evidence_pool import pool_approval_reason, pool_eligible_scalars
from tools.prompts.context import context_fingerprint
from tools.sidecar.handlers import jobs
from tools.sidecar.handlers._shared.llm_config import load_llm_config
from tools.sidecar.handlers._shared.profile_state import profile_path

_LOCK = threading.Lock()
_ENGINE_FAILURES = ("semantic_all_cards_degraded", "semantic_no_relevant_evidence",
                    "semantic_no_eligible_evidence", "semantic_inputs_changed",
                    "semantic_engine_unavailable", "semantic_result_missing")

_MAX_PASSES = 3
_ADVISORY_CONTRACT = "advisory-preparation-v2"


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _record_digest(record):
    return _sha(json.dumps({k:v for k,v in record.items() if k != "digest"},
                           ensure_ascii=False, sort_keys=True).encode())


def _audit_path(profile_id):
    path = jobs._profile_path(profile_id)  # Existing identifier validation.
    return jobs._JOB_PROFILE_DIR.parent / "outputs" / "preparation_matching" / (path.stem + ".json")


def _inputs(profile_id, *, historical_validator=None):
    snapshot = {}
    def freeze(path):
        raw = path.read_bytes()
        snapshot[str(path.resolve())] = _sha(raw)
        return raw
    job = jobs._profile_path(profile_id)
    fields = jobs._preserved_profile_fields(parse_simple_yaml(freeze(job).decode("utf-8")))
    personal = profile_path()
    freeze(personal)
    prefs = load_preferences(personal)
    lead_path = jobs._lead_path(str(fields.get("job_lead_id") or ""))
    lead = parse_simple_yaml(freeze(lead_path).decode("utf-8"))["scalars"]
    if historical_validator is not None:
        requirement_sources = historical_validator(profile_id, fields, lead)
        if not prefs or not prefs.get("confirmed_at") or not prefs.get("revision"):
            raise ValueError("historical_preferences_unconfirmed")
        direction = None
    else:
        preparation = describe_preparation(profile_id, fields, lead, prefs, validate_direction=validate_direction)
        if (preparation["state"] != "fresh" or not preparation["requirements_grounded"]
                or preparation["reason"] == "preparation_direction_deferred"):
            raise ValueError("semantic_preparation_not_fresh_grounded")
        direction = preparation["direction"]
        requirement_sources = json.loads(fields.get("preparation_json") or "{}").get("requirement_sources", [])
    career = load_career_profile(personal)
    if not career.get("career_status", {}).get("reviewed"):
        raise ValueError("semantic_career_unconfirmed")
    evidence, seen = [], set()
    material_dir = materials_dir_for(personal)
    verified = unverified = excluded = 0
    # Validate eligibility and hash from the SAME bytes; never reuse a previously allowed id.
    for path in sorted(jobs._EVIDENCE_CARD_DIR.glob("*.yaml")):
        try:
            raw = freeze(path)
            doc = parse_simple_yaml(raw.decode("utf-8"))
            scalars = doc["scalars"]
            card_id = str(scalars.get("id") or path.stem)
            fields_card = {**scalars, **doc["lists"]}
            if (card_id != path.stem or scalars.get("status") != "saved_eligible"
                    or scalars.get("candidate_pool_eligible", "").strip().lower() != "true"
                    or not pool_eligible_scalars(scalars, card_id=card_id)
                    or pool_approval_reason(fields_card)):
                excluded += 1
                continue
            evidence_sources = validated_source_inputs(doc, material_dir)
            fingerprints = json.loads(scalars.get("source_material_fingerprints_json") or "{}")
            for source_key, source in evidence_sources.items():
                digest = _sha(freeze(source))
                if hasattr(evidence_sources, "snapshots"):
                    assert_captured_source(evidence_sources, source_key, digest)
                elif digest != fingerprints[source_key.split(":", 1)[1]]["sha256"]:
                    raise ValueError("semantic_source_changed")
        except (ValueError, OSError, TypeError, KeyError, UnicodeError):
            if str(path.resolve()) not in snapshot:
                snapshot[str(path.resolve())] = "unreadable"
            excluded += 1
            continue
        if card_id in seen:
            raise ValueError("semantic_duplicate_evidence_identity")
        seen.add(card_id)
        evidence.append(path)
        verified += int(bool(evidence_sources)); unverified += int(not evidence_sources)
    if not evidence:
        raise ValueError("semantic_no_eligible_evidence")
    freeze(material_dir / prefs["source"]["filename"])
    # Recheck the complete pre-call snapshot after helpers that read live files.
    for filename, expected in snapshot.items():
        try:
            current = _sha(Path(filename).read_bytes())
        except OSError:
            current = "unreadable"
        if current != expected:
            raise ValueError("semantic_inputs_changed")
    snapshot["contract"] = ":".join((VERSION, context_fingerprint(), _ADVISORY_CONTRACT))
    snapshot["preferences_revision"] = prefs["revision"]
    return {"job_path":job, "personal_profile":personal, "evidence_files":evidence,
            "snapshot":snapshot, "direction":direction, "preferences":prefs, "job_fields":fields,
            "requirement_section_bindings":bind_explicit_requirement_sections(fields.get("source_jd", ""),
                requirement_sources),
            "pool":{"card_count":len(evidence), "verified_source_count":verified,
                    "source_freshness_unverified_count":unverified, "excluded_count":excluded}}


def _base(profile_id):
    return {"status":"blocked", "code":"semantic_unavailable", "job_profile_id":profile_id,
            "scope":"advisory_partial", "input_fresh":False, "direction":None,
            "eligible_card_count":0, "reviewed_card_count":0, "degraded_card_count":0,
            "degraded_check_count":0, "coverage":{}, "coverage_known":False, "model_calls":0,
            "budget_exhausted":False, "continuation_needed":False,
            "timing_scope":"request_start_deadline_and_socket_idle_timeout",
            "assessments":[], "evidence_pool":{}, "send_ready":False}


def _outcome(engine, reason=None, *, stop_causes=None, completed=0):
    return {"engine":engine, "reason":reason, "stop_causes":stop_causes or [],
            "completed_check_count":completed, "usable_current_result":completed > 0}


def _read_outcome(profile_id, value, raw):
    # Historical records without diagnostics stay unknown; malformed data is never echoed.
    if not isinstance(value, dict):
        return None
    engine, reason, stops = (value.get(k) for k in ("engine", "reason", "stop_causes"))
    if not isinstance(stops, list) or any(c not in ("timeout", "budget") for c in stops):
        return None
    normalized = [c for c in ("timeout", "budget") if c in stops]
    if engine == "returned" and reason is None and isinstance(raw, dict):
        expected = _outcome(engine, stop_causes=normalized, completed=_completed_check_count(profile_id, raw))
    elif engine == "failed" and reason in _ENGINE_FAILURES and raw is None:
        expected = _outcome(engine, reason, stop_causes=normalized)
    else:
        return None
    return expected if (value == expected and type(value.get("completed_check_count")) is int
                        and type(value.get("usable_current_result")) is bool) else None


def _safe_summary(profile_id, inputs, client, raw, failure):
    failed_reason = (failure if failure in _ENGINE_FAILURES else "semantic_engine_unavailable") if failure else (
        None if isinstance(raw, dict) else "semantic_result_missing")
    completed = _completed_check_count(profile_id, raw) if failed_reason is None else 0
    stop_causes = [cause for cause, happened in (("timeout",client.provider_timeout), ("budget",client.budget_exhausted))
                   if happened]
    diagnosis = _outcome("failed" if failed_reason else "returned", failed_reason,
                         stop_causes=stop_causes, completed=completed)
    raw = raw or {}
    degraded = raw.get("degraded_check_ids", [])
    deferred = raw.get("budget_deferred_check_ids", [])
    unfinished = set(degraded) | set(deferred)
    parents = {c["id"]:c["parent_id"] for c in raw.get("requirement_checks", [])}
    unknown_mapping = bool(unfinished - parents.keys())
    unfinished_parents = {parents[c] for c in unfinished if c in parents}
    assessments = []
    requirements = {r["id"]:r.get("text", "") for r in raw.get("requirements", [])}
    facts = raw.get("facts", {})
    for row in raw.get("assessments", []):
        row = dict(row)
        row["requirement_text"] = requirements.get(row.get("requirement_id"), "")
        row["citations"] = [{"fact_id":c["fact_id"], "source_id":facts[c["fact_id"]].get("source_id", ""),
                             "quote":facts[c["fact_id"]].get("text", ""),
                             **({"candidate_support": False} if c.get("candidate_support") is False else {})}
                            for c in row.get("citations", []) if c.get("fact_id") in facts]
        if unknown_mapping or row.get("requirement_id") in unfinished_parents:
            row.update(status="unassessed", reason="部分检查未完成，不能将降级当作能力不足。", citations=[])
        elif row.get("status") == "insufficient":
            row["reason"] = "可见事实范围内缺证；并非穷尽能力判断。" + str(row.get("reason", ""))
        assessments.append(row)
    code = ("semantic_provider_timeout" if client.provider_timeout else
            "semantic_budget_exhausted" if client.budget_exhausted else
            failure or "semantic_advisory_partial")
    return {**_base(profile_id), "status":"partial", "code":code, "input_fresh":True,
            "direction":inputs["direction"], "eligible_card_count":len(inputs["evidence_files"]),
            "reviewed_card_count":len({row["id"] for row in raw.get("card_reviews", [])}),
            "degraded_card_count":len(raw.get("degraded_card_ids", [])),
            "deferred_card_count":len(raw.get("budget_deferred_card_ids", [])),
            "unreviewed_card_count":max(0, len(inputs["evidence_files"]) - len({r["id"] for r in raw.get("card_reviews", [])})),
            "deferred_check_count":len(set(deferred)), "unassessed_check_count":len(unfinished),
            "degraded_check_count":len(degraded), "coverage":raw.get("assessment_visibility", {}),
            "coverage_known":bool(raw.get("assessment_visibility")),
            "assessment_schedule":raw.get("assessment_schedule"),
            "model_calls":client.model_calls, "budget_exhausted":client.budget_exhausted,
            "continuation_needed":client.budget_exhausted and not client.provider_timeout,
            "assessment_counts":{state:sum(a.get("status") == state for a in assessments)
                                 for state in ("supported", "partial", "insufficient", "conflict", "unassessed")},
            "assessments":assessments, "evidence_pool":inputs["pool"], "match_outcome":diagnosis}


def _cache_snapshot(directory):
    out = {}
    for path in directory.rglob("*.json") if directory.exists() else []:
        try:
            raw = path.read_bytes()
            if isinstance(json.loads(raw), dict):
                out[str(path)] = _sha(raw)
        except (OSError, ValueError):
            continue
    return out


def _previous_completed_hint(profile_id, snapshot):
    """A current audit may inform ordering, never supply matching conclusions."""
    try:
        record = json.loads(_audit_path(profile_id).read_text())
        if (record.get("schema_version") != 1 or record.get("digest") != _record_digest(record)
                or record.get("snapshot") != snapshot
                or record.get("summary", {}).get("input_fresh") is not True):
            return []
        result = record.get("result") or {}
        schedule = result.get("assessment_schedule") or {}
        if schedule and schedule.get("policy") != "pending_source_requirements_v1":
            return []
        ids = schedule.get("checked_check_ids", result.get("completed_check_ids", []))
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
            return []
        return list(dict.fromkeys(ids))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


def can_start_without_audit(profile_id):
    """A missing saved audit is not proof no model request was sent before."""
    try:
        _audit_path(profile_id).lstat()
    except FileNotFoundError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    return False


def _read_audit_record(profile_id):
    path = _audit_path(profile_id)
    if path.is_symlink():
        raise ValueError("invalid audit")
    record = json.loads(path.read_text())
    if (not isinstance(record, dict) or record.get("schema_version") != 1
            or record.get("digest") != _record_digest(record)
            or not isinstance(record.get("summary"), dict)):
        raise ValueError("invalid audit")
    return record


def _completed_check_count(profile_id, raw, *, method=VERSION):
    if (not isinstance(raw, dict) or raw.get("advisory_scope") is not True
            or raw.get("job_profile_id") != profile_id or raw.get("method") != method):
        return 0
    completed = raw.get("completed_check_ids")
    checks = raw.get("requirement_checks")
    judgments = raw.get("criterion_assessments")
    if not all(isinstance(rows, list) for rows in (completed, checks, judgments)):
        return 0
    known = {r.get("id") for r in checks if isinstance(r, dict) and isinstance(r.get("id"), str)}
    validated = {r.get("requirement_id") for r in judgments if isinstance(r, dict)
                 and isinstance(r.get("requirement_id"), str)
                 and r.get("status") in ("supported", "partial", "insufficient", "conflict")}
    return len(set(completed)) if all(isinstance(c, str) and c in known and c in validated for c in completed) else 0


def _has_completed_result(profile_id, raw):
    return _completed_check_count(profile_id, raw) > 0


def _snapshot_digest(snapshot):
    return _sha(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode())


def _pass_budget(record, snapshot):
    budget = record.get("pass_budget")
    if (not isinstance(budget, dict) or set(budget) != {"snapshot_digest", "used", "state"}
            or budget["snapshot_digest"] != _snapshot_digest(snapshot)
            or type(budget["used"]) is not int or not 1 <= budget["used"] <= _MAX_PASSES
            or budget["state"] not in ("reserved", "settled", "closed")):
        return None
    return budget


def _continuation_digest(profile_id, record, snapshot):
    summary = record["summary"]
    budget = _pass_budget(record, snapshot)
    if (budget is None or budget["state"] != "settled" or budget["used"] >= _MAX_PASSES
            or record.get("snapshot") != snapshot or summary.get("job_profile_id") != profile_id
            or summary.get("status") != "partial" or summary.get("scope") != "advisory_partial"
            or summary.get("send_ready") is not False or summary.get("input_fresh") is not True
            or summary.get("continuation_needed") is not True or summary.get("code") != "semantic_budget_exhausted"
            or type(summary.get("cache_progress_count")) is not int or summary["cache_progress_count"] < 1):
        return None
    raw = record.get("result")
    outcome = _read_outcome(profile_id, summary.get("match_outcome"), raw)
    if (not outcome or not outcome["usable_current_result"] or outcome["stop_causes"] != ["budget"]
            or raw.get("degraded_check_ids") != []):
        return None
    pending = raw.get("budget_deferred_check_ids")
    completed = set(raw["completed_check_ids"])
    known = {r["id"] for r in raw["requirement_checks"] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    return record["digest"] if isinstance(pending, list) and pending and all(
        isinstance(check, str) and check in known and check not in completed for check in pending) else None


def _save_audit(path, record):
    record = {**record, "digest": _record_digest(record)}
    atomic_write_json(path, record)
    return record


def _reserve_pass(profile_id, snapshot, *, continuation, expected):
    path = _audit_path(profile_id)
    with locked_review_queue(path):
        if can_start_without_audit(profile_id):
            if continuation:
                return None
            old = {"schema_version":1, "snapshot":snapshot,
                   "summary":{**_base(profile_id), "code":"semantic_pass_reserved", "input_fresh":True},
                   "result":None}
            used = 1
        else:
            if not continuation or not isinstance(expected, str) or not expected:
                return None
            try:
                old = _read_audit_record(profile_id)
            except (OSError, ValueError, TypeError, KeyError):
                return None
            if _continuation_digest(profile_id, old, snapshot) != expected:
                return None
            used = old["pass_budget"]["used"] + 1
        return _save_audit(path, {**old, "pass_budget":{
            "snapshot_digest":_snapshot_digest(snapshot), "used":used, "state":"reserved"}})


def _finish_pass(profile_id, reserved, result, *, usable):
    path = _audit_path(profile_id)
    with locked_review_queue(path):
        current = _read_audit_record(profile_id)
        if current["digest"] != reserved["digest"]:
            return None
        budget = current["pass_budget"]
        if not usable and _has_completed_result(profile_id, current.get("result")):
            _save_audit(path, {**current, "pass_budget":{**budget, "state":"closed"}})
            return False
        summary = result["summary"]
        result = {**result, "pass_budget":{**budget, "state":"settled" if usable else "closed"}}
        # Suppress exhausted/invalid/degraded/missing results in the stored summary too.
        candidate = {**result, "digest":"candidate"}
        summary["continuation_needed"] = bool(_continuation_digest(profile_id, candidate, result["snapshot"]))
        return _save_audit(path, result)


def _contract_recheck_digest(profile_id, record, inputs):
    if (inputs.get("job_fields") or {}).get("import_mode") == "manual" or (
            isinstance(record.get("pass_budget"), dict) and record["pass_budget"].get("state") == "reserved"):
        return None
    summary = record["summary"]
    old, current = record.get("snapshot"), inputs["snapshot"]
    if (summary.get("job_profile_id") != profile_id or summary.get("scope") != "advisory_partial"
            or summary.get("status") != "partial" or summary.get("input_fresh") is not True
            or summary.get("send_ready") is not False
            or summary.get("code") not in ("semantic_advisory_partial", "semantic_budget_exhausted")
            or not isinstance(old, dict) or not isinstance(current, dict)):
        return None
    a, b = old.get("contract"), current.get("contract")
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
        return None
    if {**old, "contract":b} != current:
        return None
    # Historical findings are not current results. This structural check only
    # admits a deliberate new assessment against the exact same input snapshot.
    method, _, remainder = a.partition(":")
    context, _, scope = remainder.partition(":")
    # Allow only the verified same-shape predecessor, not an old schema adapter.
    if (method not in (VERSION, "evidence-semantic-v5") or not context
            or scope != _ADVISORY_CONTRACT or not b.startswith(VERSION + ":")
            or _completed_check_count(profile_id, record.get("result"), method=method) == 0):
        return None
    return record["digest"]


def _matches_contract_recheck(profile_id, expected, inputs):
    if not isinstance(expected, str) or not expected:
        return False
    try:
        return _contract_recheck_digest(profile_id, _read_audit_record(profile_id), inputs) == expected
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def handle_match_preparation(params):
    profile_id = str(params.get("job_profile_id") or "")
    base = {"meta":params["meta"], **_base(profile_id)}
    def preflight(code):
        return {**base, "code":code, "match_outcome":_outcome("preflight", code)}

    if not _LOCK.acquire(blocking=False):
        return preflight("semantic_preparation_busy")
    engine_entered = False
    recheck = "recheck_contract_digest" in params
    previous_digest = params.get("recheck_contract_digest")
    continuing = "continue_matching_digest" in params
    starting = params.get("start_if_no_audit") is True
    try:
        if sum((recheck, continuing, starting)) > 1:
            return preflight("semantic_continuation_unavailable")
        if starting and not can_start_without_audit(profile_id):
            return preflight("semantic_start_unavailable")
        inputs = _inputs(profile_id)
        if recheck and not _matches_contract_recheck(profile_id, previous_digest, inputs):
            return preflight("semantic_contract_recheck_unavailable")
        config = load_llm_config()
        if (config.get("provider") != "openai_compatible"
                or str(config.get("base_url", "")).rstrip("/") != SPLASH
                or not str(config.get("model", "")).strip()):
            return preflight("local_splash_required")
        # Re-run owner/source validators before any network request, not only file hashing.
        verified_inputs = _inputs(profile_id)
        if verified_inputs["snapshot"] != inputs["snapshot"]:
            return preflight("semantic_inputs_changed")
        inputs = verified_inputs
        reserved = None
        if not recheck:
            reserved = _reserve_pass(profile_id, inputs["snapshot"], continuation=continuing,
                                     expected=params.get("continue_matching_digest"))
            if reserved is None:
                return preflight("semantic_start_unavailable" if starting else "semantic_continuation_unavailable")
        client = BoundedLocalClient(model=config["model"], api_key=str(config.get("api_key_for_request") or ""))
        raw, failure = None, ""
        cache_dir = _audit_path(profile_id).parent / ".semantic-cache"
        cache_before = _cache_snapshot(cache_dir)
        def before_model_call(stage):
            # Actual HTTP attempts include repairs. Cache reads never enter this hook.
            if stage == "recall" and client.model_calls >= 2:
                client.budget_exhausted = True
                raise ValueError("semantic_stage_budget_deferred")
        engine_entered = True
        try:
            raw = run_semantic_matching(job_path=inputs["job_path"], evidence_files=inputs["evidence_files"],
                personal_profile=inputs["personal_profile"], client=client, model=config["model"],
                cache_dir=cache_dir, batch_size=8, advisory=True,
                reused_direction=inputs["direction"], before_model_call=before_model_call,
                previous_completed_check_ids=_previous_completed_hint(profile_id, inputs["snapshot"]),
                requirement_section_bindings=inputs.get("requirement_section_bindings", []))
        except (ValueError, OSError, TypeError, KeyError, RuntimeError) as exc:
            failure = str(exc) if str(exc) in _ENGINE_FAILURES else "semantic_engine_unavailable"
        summary = _safe_summary(profile_id, inputs, client, raw, failure)
        cache_after = _cache_snapshot(cache_dir)
        summary["cache_progress_count"] = sum(cache_before.get(k) != v for k, v in cache_after.items())
        summary["continuation_needed"] = summary["continuation_needed"] and summary["cache_progress_count"] > 0
        try:
            current = _inputs(profile_id)
            unchanged = current["snapshot"] == inputs["snapshot"]
        except (ValueError, OSError, TypeError, KeyError):
            unchanged = False
        if not unchanged:
            summary.update(code="semantic_inputs_changed", input_fresh=False,
                           continuation_needed=False, assessments=[], direction=None)
            summary.pop("match_outcome", None)
        if recheck:
            receipt = {**base, "model_calls":client.model_calls}
            if not unchanged or not _matches_contract_recheck(profile_id, previous_digest, inputs):
                return {**receipt, "code":"semantic_contract_recheck_unavailable"}
            if failure or client.provider_timeout or not _has_completed_result(profile_id, raw):
                return {**receipt, "code":"semantic_contract_recheck_retained", "match_outcome":{
                    **summary["match_outcome"], "completed_check_count":0, "usable_current_result":False}}
        record = {"schema_version":1, "snapshot":inputs["snapshot"], "summary":summary,
                  "result":raw, "provenance":{"model":config["model"], "provider":config["provider"],
                                            "endpoint":SPLASH, "created_at":jobs._utcnow_iso()}}
        if recheck:
            summary["continuation_needed"] = False
            path = _audit_path(profile_id)
            with locked_review_queue(path):
                if not _matches_contract_recheck(profile_id, previous_digest, inputs):
                    return {**receipt, "code":"semantic_contract_recheck_unavailable"}
                _save_audit(path, record)
        else:
            usable = unchanged and not failure and not client.provider_timeout and _has_completed_result(profile_id, raw)
            finished = _finish_pass(profile_id, reserved, record, usable=usable)
            if finished is None:
                return {**base, "code":"semantic_continuation_unavailable", "model_calls":client.model_calls}
            if finished is False:
                return {"meta":params["meta"], **summary, "code":"semantic_continuation_retained",
                        "continuation_needed":False}
            token = _continuation_digest(profile_id, finished, inputs["snapshot"])
            if token:
                return {"meta":params["meta"], **summary, "continuation_digest":token}
        return {"meta":params["meta"], **summary}
    except (ValueError, OSError, TypeError, KeyError) as exc:
        safe = {"semantic_preparation_not_fresh_grounded", "semantic_career_unconfirmed",
                "semantic_no_eligible_evidence", "semantic_duplicate_evidence_identity", "semantic_inputs_changed", "invalid_job_profile_id"}
        code = str(exc) if str(exc) in safe else "semantic_inputs_unavailable"
        return {**base, "code":code} if engine_entered else preflight(code)
    except ImportError:
        return preflight("semantic_budget_lock_unavailable")
    finally:
        _LOCK.release()


def read_semantic_preparation(profile_id, *, continuation_tickets: dict[str, str] | None = None):
    try:
        if can_start_without_audit(profile_id):
            return None
        record = _read_audit_record(profile_id)
        summary = {**record["summary"]}
        try:
            inputs = _inputs(profile_id)
            fresh = (inputs["snapshot"] == record["snapshot"] and summary.get("input_fresh") is True)
        except (ValueError, OSError, TypeError, KeyError):
            inputs, fresh = None, False
        if not fresh:
            reply = {**_base(profile_id), "status":"stale", "code":"semantic_inputs_changed"}
            token = _contract_recheck_digest(profile_id, record, inputs) if inputs is not None else None
            if token:
                reply["contract_recheck_digest"] = token
            return reply
        summary.pop("assessments", None)  # List projection is aggregate; full findings remain in audit/RPC.
        token = _continuation_digest(profile_id, record, inputs["snapshot"])
        summary.pop("continuation_digest", None)
        summary["continuation_needed"] = bool(token)
        if token and continuation_tickets is not None:
            continuation_tickets[profile_id] = token
        outcome = _read_outcome(profile_id, summary.pop("match_outcome", None), record.get("result"))
        if outcome is not None:
            summary["match_outcome"] = outcome
        return summary
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        return {**_base(profile_id), "status":"invalid", "code":"semantic_audit_invalid"}
