"""岗位画像的匹配快照、预检与列表 handler。

从 ``jobs.py`` 拆出；路径常量仍从原模块运行时读取，保证测试 patch 生效。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from tools.engines.matching import fit_precheck as fit_precheck_engine
from tools.engines.discovery.preparation_state import describe_preparation
from tools.infra.job_preferences import load_preferences, validate_direction
from tools.sidecar.handlers._shared.profile_state import profile_path
from tools.infra.persistence.yaml_io import ParsedDoc
from tools.sidecar.handlers import jobs as _origin
from tools.sidecar.handlers.jobs import (
    JobProfileItem,
    MatchSnapshot,
    _find_lead_path,
    _format_utc_datetime,
    _format_utc_timestamp,
    _glob_files,
    _lead_identity,
    _load_precheck_corpus,
    _parse_cursor,
    _parse_page_size,
    _parse_sort_field,
    _parse_sort_order,
    _read_yaml_doc,
    _safe_parse_iso_date,
    _try_read_yaml_doc,
)


def _load_fit_snapshot(
    matching_stem: str,
) -> tuple[str, int, dict[str, Any] | None, int | None]:
    """读取与匹配报告同 stem 的质量评分卡，给出对位预检状态、投递建议与语义适配分。"""
    path = _origin._SCORECARD_DIR / f"scorecard_{matching_stem}_A.json"
    if not path.is_file():
        return "unassessed", 0, None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        quality_report = payload.get("quality_report")
        tiers = quality_report.get("tiers") if isinstance(quality_report, dict) else None
        fit = tiers.get("fit") if isinstance(tiers, dict) else None
        # 旧评分卡没有四层报告/对位层时不能谎报“已预检失败”，交给规则预检。
        if not isinstance(fit, dict) or "passed" not in fit:
            return "unassessed", 0, None, None
        passed = bool(fit.get("passed"))
        failures = len(fit.get("failures") or [])
        advice = quality_report.get("delivery_advice") if isinstance(quality_report, dict) else None
        raw_fit_score = (payload.get("semantic_review") or {}).get("fit_score")
        try:
            fit_score = int(raw_fit_score) if raw_fit_score is not None else None
        except (TypeError, ValueError):
            fit_score = None
        return (
            "passed" if passed else "failed",
            failures,
            advice if isinstance(advice, dict) else None,
            fit_score,
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return "unassessed", 0, None, None


def _load_matching_snapshots() -> dict[str, MatchSnapshot]:
    snapshots: dict[str, MatchSnapshot] = {}

    for path in _glob_files(_origin._MATCHING_REPORT_DIR, "*.yaml"):
        doc = _try_read_yaml_doc(path)
        if doc is None:
            continue
        job_profile_id = doc["scalars"].get("job_profile_id", "").strip()
        if not job_profile_id:
            continue

        generated_at = doc["scalars"].get("generated_at", "")
        parsed_generated_at = _safe_parse_iso_date(generated_at)
        sort_key = (
            parsed_generated_at.timestamp()
            if parsed_generated_at is not None
            else path.stat().st_mtime
        )
        updated_at = (
            _format_utc_datetime(parsed_generated_at)
            if parsed_generated_at is not None
            else _format_utc_timestamp(sort_key)
        )

        try:
            score = int(doc["scalars"].get("score_total", "0") or "0")
        except ValueError:
            score = 0

        fit_state, fit_failures, fit_advice, fit_score = _load_fit_snapshot(path.stem)
        snapshot: MatchSnapshot = {
            "score": score,
            "evidence_count": len(doc["lists"].get("evidence_card_ids", [])),
            "updated_at": updated_at,
            "sort_key": sort_key,
            "fit_state": fit_state,
            "fit_failures": fit_failures,
            "fit_score": fit_score,
            "advice": fit_advice,
        }
        existing = snapshots.get(job_profile_id)
        if existing is None or snapshot["sort_key"] >= existing["sort_key"]:
            snapshots[job_profile_id] = snapshot

    return snapshots

def _derive_status(doc: ParsedDoc, snapshot: MatchSnapshot | None) -> str:
    explicit_status = doc["scalars"].get("status", "").strip()
    if explicit_status:
        return explicit_status
    if snapshot is not None:
        return "active"
    return "draft"


def _native_pdf_delivery_state(
    scalars: dict[str, str], job_profile_id: str
) -> dict[str, Any]:
    """判断画像能否走 App 内原生 PDF 投递（只用于界面提示，不替代投递门禁）。

    原生投递要求目标绑定已审核的猎聘官方线索，且画像与线索的 JD 指纹一致；
    手工导入或未绑定线索的画像只能手动投递并记录。
    """
    lead_id = str(scalars.get("job_lead_id", "") or "").strip()
    if not lead_id:
        reason = "manual_import" if scalars.get("import_mode") == "manual" else "job_lead_missing"
        return {"supported": False, "reason": reason}
    lead_path = _find_lead_path(lead_id)
    if lead_path is None:
        return {"supported": False, "reason": "job_lead_missing"}
    lead = _read_yaml_doc(lead_path)["scalars"]
    if lead.get("source") != "liepin_official":
        return {"supported": False, "reason": "not_official_channel"}
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile

    if reviewed_official_profile(lead, _origin._JOB_PROFILE_DIR) is None:
        return {"supported": False, "reason": "job_review_required"}
    if lead.get("job_profile_id") != job_profile_id:
        return {"supported": False, "reason": "job_binding_mismatch"}
    if str(scalars.get("source_jd_sha256", "")) != str(lead.get("source_jd_sha256", "")):
        return {"supported": False, "reason": "jd_fingerprint_mismatch"}
    # 来源已审核不等于渠道支持上传定制 PDF。猎头岗保持平台默认简历路线，
    # 这里只做前置能力提示；不替代每日执行器的快照门禁，不放宽来源/指纹校验。
    from urllib.parse import urlsplit
    if urlsplit(str(lead.get("url", ""))).path.startswith("/a/"):
        return {"supported": False, "reason": "platform_default_only"}
    from tools.domain.job_lead_state import current_jd_capture

    if current_jd_capture(lead) is None:
        return {"supported": False, "reason": "quick_official_capture_required"}
    return {"supported": True, "reason": ""}

def _preparation_context():
    try:
        return load_preferences(profile_path()), ""
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        return None, "preferences_source_unavailable"


def _saved_preparation(profile_id, fields, context, corpus, *, continuation_tickets=None):
    lead, preferences, error = None, None, ""
    if fields.get("preparation_json"):
        preferences, error = context()
        try:
            lead_path = _find_lead_path(str(fields.get("job_lead_id") or ""))
            if lead_path is not None:
                lead = _read_yaml_doc(lead_path)["scalars"]
        except (ValueError, OSError, TypeError, KeyError):
            lead = None
    state = describe_preparation(profile_id, fields, lead, preferences,
                                 validate_direction=validate_direction, preferences_error=error)
    if state["state"] == "fresh":
        # Deliberately ignore historical assessed reports: this is current rule overlap only.
        overlap = fit_precheck_engine.precheck_profile(fields, None, corpus)
        state["evidence_precheck"] = {**overlap, **{
            key: corpus.get(key, {} if key == "excluded_reasons" else 0)
            for key in ("card_count", "source_freshness_unverified_count", "verified_source_count",
                        "excluded_count", "excluded_reasons")}}
    from tools.sidecar.handlers.preparation_semantic import read_semantic_preparation
    state["semantic_matching"] = read_semantic_preparation(profile_id, continuation_tickets=continuation_tickets)
    return state


def _build_profile_item(
    path: Path, snapshots: dict[str, MatchSnapshot], corpus: dict[str, Any], preparation_context=None, *, continuation_tickets=None
) -> JobProfileItem | None:
    doc = _try_read_yaml_doc(path)
    if doc is None:
        return None
    job_profile_id = path.stem
    fields = {**doc["scalars"], **doc["lists"]}
    preparation = _saved_preparation(job_profile_id, fields, preparation_context or _preparation_context, corpus,
                                     continuation_tickets=continuation_tickets)
    try:
        native = _native_pdf_delivery_state(doc["scalars"], job_profile_id)
    except (ValueError, OSError, TypeError, KeyError):
        native = {"supported": False, "reason": "job_source_unavailable"}
    snapshot = snapshots.get(job_profile_id)
    updated_at = (
        snapshot["updated_at"]
        if snapshot is not None
        else _format_utc_timestamp(path.stat().st_mtime)
    )
    precheck = fit_precheck_engine.precheck_profile(
        {**doc["scalars"], **doc["lists"]},
        snapshot,
        corpus,
    )
    return {
        "job_profile_id": job_profile_id,
        "title": doc["scalars"].get("target_role", job_profile_id),
        "company": doc["scalars"].get("company", ""),
        "status": _derive_status(doc, snapshot),
        "match_score": snapshot["score"] if snapshot is not None else 0,
        "evidence_count": snapshot["evidence_count"] if snapshot is not None else 0,
        "resume_count": 0,
        "fit_state": snapshot["fit_state"] if snapshot is not None else "unassessed",
        "fit_failures": snapshot["fit_failures"] if snapshot is not None else 0,
        "fit_precheck": precheck,
        "native_pdf_delivery": native,
        "preparation": preparation,
        "updated_at": updated_at,
        "business_domain": doc["scalars"].get("business_domain", ""),
        "source_jd": doc["scalars"].get("source_jd", ""),
        "tone": doc["scalars"].get("tone", ""),
        "keywords": doc["lists"].get("keywords", []),
        "must_have": doc["lists"].get("must_have", []),
        "nice_to_have": doc["lists"].get("nice_to_have", []),
        "seniority_signal": doc["lists"].get("seniority_signal", []),
        "source_url": doc["scalars"].get("source_url", ""),
        "job_lead_id": doc["scalars"].get("job_lead_id", ""),
        "source_jd_sha256": doc["scalars"].get("source_jd_sha256", ""),
        "import_mode": doc["scalars"].get("import_mode", ""),
        "source_recorded_at": doc["scalars"].get("source_recorded_at", ""),
        **_lead_identity(doc["scalars"]),
    }

def _matches_query(item: JobProfileItem, query: str) -> bool:
    if not query:
        return True
    normalized_query = query.casefold()
    haystack = " ".join(
        [
            item["title"],
            item["company"],
            item["business_domain"],
            item["source_jd"],
            item["tone"],
            *item["keywords"],
            *item["must_have"],
            *item["nice_to_have"],
            *item["seniority_signal"],
        ]
    ).casefold()
    return normalized_query in haystack


def _matches_tags(item: JobProfileItem, tags: list[str]) -> bool:
    if not tags:
        return True
    normalized_keywords = {value.casefold() for value in item["keywords"]}
    return all(tag.casefold() in normalized_keywords for tag in tags)


def _coerce_tag_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    tags: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            tags.append(item)
    return tags

def _apply_filters(
    items: list[JobProfileItem], filters: dict[str, object]
) -> list[JobProfileItem]:
    status_filter = str(filters.get("status") or "").strip()
    query_filter = str(filters.get("query") or "").strip()
    tags_filter = _coerce_tag_list(filters.get("tags"))

    filtered: list[JobProfileItem] = []
    for item in items:
        if status_filter and item["status"] != status_filter:
            continue
        if not _matches_query(item, query_filter):
            continue
        if not _matches_tags(item, tags_filter):
            continue
        filtered.append(item)
    return filtered


def _sort_items(
    items: list[JobProfileItem], field: str, order: str
) -> list[JobProfileItem]:
    reverse = order != "asc"
    if field == "fit_precheck":
        return sorted(
            items,
            key=lambda item: (
                fit_precheck_engine.precheck_rank(item.get("fit_precheck")),
                item["updated_at"],
                item["job_profile_id"],
            ),
            reverse=reverse,
        )
    if field == "match_score":
        return sorted(
            items,
            key=lambda item: (
                item["match_score"],
                item["updated_at"],
                item["job_profile_id"],
            ),
            reverse=reverse,
        )
    return sorted(
        items,
        key=lambda item: (item["updated_at"], item["job_profile_id"]),
        reverse=reverse,
    )

def handle_jobs_list_profiles(params: dict[str, object], *,
                              continuation_tickets: dict[str, str] | None = None) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = cast(dict[str, str], params.get("sort") or {})
    filters = cast(dict[str, object], params.get("filters") or {})

    snapshots = _load_matching_snapshots()
    corpus = _load_precheck_corpus()
    items: list[JobProfileItem] = []
    context = None
    def preparation_context():
        nonlocal context
        if context is None:
            context = _preparation_context()
        return context
    for path in _glob_files(_origin._JOB_PROFILE_DIR, "*.yaml"):
        item = _build_profile_item(path, snapshots, corpus, preparation_context,
                                   continuation_tickets=continuation_tickets)
        if item is not None:
            items.append(item)
    items = _apply_filters(items, filters)
    sort_field = _parse_sort_field(sort.get("field"))
    sort_order = _parse_sort_order(sort.get("order"))
    # 推荐排序默认 rank 升序；显式 order 优先。
    if sort_field == "fit_precheck" and not str(sort.get("order") or "").strip():
        sort_order = "asc"
    items = _sort_items(items, sort_field, sort_order)

    paged_items = items[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(items) else None

    result: dict[str, object] = {
        "meta": {"correlation_id": correlation_id},
        "items": paged_items,
        "next_cursor": next_cursor,
    }
    return result
