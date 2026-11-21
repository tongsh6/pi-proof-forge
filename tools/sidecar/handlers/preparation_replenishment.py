"""Explicit bounded source-only replenishment; never approves or sends applications."""
from __future__ import annotations
import re
import sqlite3
import threading
from tools.channels.base import DeliveryRequest
from tools.engines.discovery.search_queries import prioritize_search_results
from tools.infra.job_preferences import load_preferences
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.orchestration.approved_delivery import _job_key
from tools.sidecar.handlers import jobs
from tools.sidecar.handlers._shared.profile_state import profile_path
from tools.sidecar.handlers.preparation import handle_plan_daily_preparation
from tools.sidecar.handlers.jobs_leads import handle_jobs_search_liepin, _build_lead_item
from tools.infra.liepin_job_detail import DETAIL_UNAVAILABLE_REASONS
from tools.sidecar.handlers.jobs_profiles import handle_jobs_fetch_liepin_detail, handle_jobs_convert_lead

_LOCK = threading.Lock()

def _attempted_keys():
    path = jobs._SUBMISSIONS_DIR / "delivery_attempts.sqlite3"
    if not path.exists():
        return set()
    try:
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as db:
            return {row[0] for row in db.execute("SELECT job_key FROM attempts")}
    except sqlite3.Error:
        raise ValueError("delivery_state_unavailable") from None

def _read_current(lead_id):
    return _build_lead_item(jobs._lead_path(lead_id))

def _identity(row):
    if (row.get("platform") != "liepin" or not row.get("platform_job_id")
            or not row.get("platform_job_type") or not row.get("url")):
        return ""
    return _job_key(DeliveryRequest("", "", "liepin", "", row["url"], True, row))

def _city(value):
    # Only explicit city or district-delimited city; no substring matching.
    return re.split(r"[-·/，,\s]", str(value).strip(), maxsplit=1)[0].removesuffix("市")

def _query_plan(profile):
    from tools.engines.discovery.search_queries import build_search_query_plan
    prefs = load_preferences(profile)
    city = parse_simple_yaml(profile.read_text(encoding="utf-8"))["scalars"].get("city", "")
    return build_search_query_plan(prefs, city)


def _queries(profile):
    plan = _query_plan(profile)
    return plan["city"], [row["query"] for row in plan["queries"]]

def _reason(row, city, attempted):
    if not row or row.get("source") != "liepin_official":
        return "lead_unavailable"
    if row.get("job_profile_id"):
        return "profile_already_linked"
    if row.get("status", "new") != "new":
        return "lead_not_new"
    if not _identity(row):
        return "job_identity_missing"
    if _identity(row) in attempted:
        return "already_attempted"
    if not _city(row.get("location", "")):
        return "city_unknown"
    if _city(row["location"]) != city:
        return "city_mismatch"
    return ""

def handle_replenish_preparation(params):
    maximum = params.get("maximum", 3)
    if type(maximum) is not int or not 1 <= maximum <= 3:
        raise ValueError("daily_invalid_maximum")
    out = {"meta":params["meta"], "status":"completed", "code":"OK", "maximum":maximum,
           "shortfall":0, "queries":[], "received_count":0, "imported_count":0,
           "source_prepared_count":0, "source_prepared":[], "deferred":[], "errors":[],
           "send_ready":False, "query_plan":None}
    if not _LOCK.acquire(blocking=False):
        return {**out, "status":"blocked", "code":"replenishment_busy"}
    try:
        try:
            out["shortfall"] = handle_plan_daily_preparation(params)["shortfall"]
            budget = min(maximum, out["shortfall"])
            if budget <= 0:
                return out
            _attempted_keys()
            out["query_plan"] = _query_plan(profile_path())
            city = out["query_plan"]["city"]
            queries = [row["query"] for row in out["query_plan"]["queries"]]
        except (ValueError, OSError, KeyError, TypeError) as exc:
            safe_codes = {"delivery_state_unavailable", "job_preferences_source_changed",
                          "preferences_not_confirmed", "city_unknown", "safe_primary_query_missing"}
            code = str(exc) if str(exc) in safe_codes else "replenishment_inputs_unavailable"
            return {**out, "status":"blocked", "code":code,
                    "errors":[{"stage":"inputs", "code":code}]}
        seen, details = set(), 0
        stop_reason = ""
        held = []

        def attempt_rows(rows, limit, *, retain=False):
            nonlocal details, stop_reason
            for row in rows:
                lead_id = row.get("job_lead_id", "")
                try:
                    current = _read_current(lead_id)
                    reason = _reason(current, city, _attempted_keys())
                    identity = _identity(current) if current else ""
                    if not reason and identity in seen:
                        reason = "duplicate_job"
                    if not reason and stop_reason:
                        reason = stop_reason
                    if not reason and details >= limit:
                        if retain:
                            held.append(row)
                            continue
                        reason = "detail_budget"
                    if reason:
                        out["deferred"].append({"job_lead_id":lead_id, "reason":reason})
                        continue
                    seen.add(identity)
                    details += 1
                    detail = handle_jobs_fetch_liepin_detail({"meta":params["meta"], "job_lead_id":lead_id})
                    if detail.get("status") != "pass":
                        detail_code = detail.get("code", "detail_failed")
                        error = {"stage":"detail", "job_lead_id":lead_id, "code":detail_code}
                        reason = detail.get("detail_reason")
                        if detail_code == "JOB_DETAIL_UNAVAILABLE" and isinstance(reason, str) and reason in DETAIL_UNAVAILABLE_REASONS:
                            error["detail_reason"] = reason
                        out["errors"].append(error)
                        # A provider challenge applies to this run, not merely the current lead.
                        if detail_code == "SECURITY_CHALLENGE" or (
                                detail_code == "JOB_DETAIL_UNAVAILABLE" and reason == "access_required"):
                            stop_reason = "detail_security_deferred"
                        continue
                    fresh = _read_current(lead_id)
                    reason = _reason(fresh, city, _attempted_keys())
                    if not reason and _identity(fresh) != identity:
                        reason = "lead_changed"
                    if reason:
                        out["deferred"].append({"job_lead_id":lead_id, "reason":reason})
                        continue
                    converted = handle_jobs_convert_lead({"meta":params["meta"], "job_lead_id":lead_id})
                    out["source_prepared"].append({"job_lead_id":lead_id,
                        "job_profile_id":converted["job_profile_id"],
                        "company":fresh.get("company", ""), "title":fresh.get("position", "")})
                except (ValueError, OSError, KeyError, TypeError):
                    out["errors"].append({"stage":"source", "job_lead_id":lead_id, "code":"source_preparation_failed"})

        # Two queries' first pages, or one query's pages 0 and 1; never more than two requests.
        requests = [(q, 0) for q in queries] if len(queries) == 2 else [(queries[0], 0), (queries[0], 1)]
        reserve_backup = len(queries) == 2 and budget >= 2
        for index, (query, page) in enumerate(requests):
            if stop_reason or details >= budget:
                break
            out["queries"].append(query)
            try:
                result = handle_jobs_search_liepin({"meta":params["meta"], "keyword":query, "page":page, "address":city})
            except (ValueError, OSError, KeyError, TypeError):
                result = {"status":"blocked", "code":"search_failed"}
            out["received_count"] += result.get("received_count", 0)
            out["imported_count"] += result.get("imported_count", 0)
            if result.get("status") != "pass":
                out["errors"].append({"stage":"search", "code":result.get("code", "search_failed")})
                stop_reason = "detail_search_deferred"
                break
            reserve = reserve_backup and index == 0
            attempt_rows(prioritize_search_results(result.get("items", []), queries),
                         budget - 1 if reserve else budget, retain=reserve)
            if not result.get("items") and len(queries) == 1:
                break
        # Recheck retained leads if the reserved slot was unused. If provider
        # access stopped, classify them without making a further detail request.
        attempt_rows(held, budget)
        out["source_prepared_count"] = len(out["source_prepared"])
        if out["errors"]:
            out["status"] = "partial" if out["source_prepared"] or out["imported_count"] else "blocked"
            out["code"] = "replenishment_incomplete"
        return out
    finally:
        _LOCK.release()
