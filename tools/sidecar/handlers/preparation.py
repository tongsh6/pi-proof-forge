"""每日准备的只读适配器：复用岗位列表、稳定投递身份和现有占位，不创建授权。"""
from __future__ import annotations
import re
import sqlite3
from collections import Counter
from tools.channels.base import DeliveryRequest
from tools.engines.discovery.preparation_plan import build_preparation_plan
from tools.orchestration.approved_delivery import _job_key
from tools.sidecar.handlers import jobs, jobs_matching, preparation_assessment, preparation_semantic

def handle_plan_daily_preparation(params):
    maximum = params.get("maximum", 3)
    if type(maximum) is not int or not 1 <= maximum <= 3:
        raise ValueError("daily_invalid_maximum")
    database = jobs._SUBMISSIONS_DIR / "delivery_attempts.sqlite3"
    attempted = set()
    if database.exists():
        try:
            with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
                attempted = {row[0] for row in db.execute("SELECT job_key FROM attempts")}
        except sqlite3.Error:
            raise ValueError("delivery_state_unavailable") from None
    profiles, cursor, seen_cursors = [], None, set()
    continuation_tickets: dict[str, str] = {}
    for _ in range(100):
        request = {"meta":params["meta"], "page_size":100}
        if cursor is not None:
            request["cursor"] = cursor
        page = jobs_matching.handle_jobs_list_profiles(request, continuation_tickets=continuation_tickets)
        for row in page["items"]:
            row = dict(row)
            if row.get("source_url") and row.get("platform"):
                row["preparation_key"] = _job_key(DeliveryRequest(
                    "", "", str(row["platform"]), "", str(row["source_url"]), True, row))
            profiles.append(row)
        cursor = page.get("next_cursor")
        if cursor is None:
            break
        if cursor in seen_cursors:
            raise ValueError("preparation_source_pagination_invalid")
        seen_cursors.add(cursor)
    else:
        raise ValueError("preparation_source_limit_exceeded")
    plan = build_preparation_plan(profiles, maximum=maximum, attempted_keys=attempted)
    by_profile = {p["job_profile_id"]: p for p in profiles}
    identity_counts = Counter(p.get("preparation_key") for p in profiles)
    profile_counts = Counter(p["job_profile_id"] for p in profiles)
    for row in (*plan["selected"], *plan["deferred"]):
        row["recovery_action"] = None
        saved = row.get("preparation", {})
        matching = saved.get("semantic_matching")
        token = None
        if isinstance(matching, dict) and "contract_recheck_digest" in matching:
            public_matching = dict(matching)
            token = public_matching.pop("contract_recheck_digest")
            row["preparation"] = {**saved, "semantic_matching":public_matching}
        profile = by_profile.get(row["job_profile_id"], {})
        identity = profile.get("preparation_key")
        if (profile.get("status") != "draft" or profile.get("platform") != "liepin"
                or profile_counts[row["job_profile_id"]] != 1 or not identity
                or identity in attempted or identity_counts[identity] != 1):
            continue
        if row["reason"] == "preparation_saved_unapproved":
            if (saved.get("state") == "fresh" and saved.get("requirements_grounded") is True
                    and (saved.get("direction") or {}).get("status") in ("aligned", "needs_review")
                    and "semantic_matching" in saved):
                if matching is None and preparation_semantic.can_start_without_audit(row["job_profile_id"]):
                    row["recovery_action"] = {"kind":"start_matching"}
                elif (isinstance(matching, dict) and matching.get("status") == "stale"
                      and isinstance(token, str) and re.fullmatch(r"[0-9a-f]{64}", token)):
                    row["recovery_action"] = {"kind":"recheck_matching", "audit_digest":token}
                elif (isinstance(matching, dict) and matching.get("status") == "partial"
                      and matching.get("input_fresh") is True and matching.get("continuation_needed") is True
                      and (ticket := continuation_tickets.get(row["job_profile_id"]))):
                    row["recovery_action"] = {"kind":"continue_matching", "audit_digest":ticket}
            continue
        if row["reason"] != "profile_review_required":
            continue
        try:
            _, _, fields, _, _, _ = preparation_assessment._bound(row["job_profile_id"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not preparation_assessment.is_source_only_draft(fields) or _job_key(DeliveryRequest(
                "", "", fields["platform"], "", fields["source_url"], True, fields)) != identity:
            continue
        # Read-only capability hint: the assess route revalidates the binding on click.
        row["recovery_action"] = {"kind":"resume_assessment"}
    return {"meta":params["meta"], **plan}
