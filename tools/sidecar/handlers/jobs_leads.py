"""招聘线索的搜索、导入与列表 handler。

从 ``jobs.py`` 拆出；路径常量仍从原模块运行时读取，保证测试 patch 生效。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from tools.infra.liepin_readonly import liepin_readonly
from tools.sidecar.handlers import jobs as _origin
from tools.sidecar.handlers.jobs import (
    JobLeadItem,
    _COMPANY_FACT_KEYS,
    _OFFICIAL_COMPANY_FACTS,
    _company_size_upper_bound,
    _format_utc_timestamp,
    _glob_files,
    _lead_path,
    _parse_cursor,
    _parse_lead_sort_field,
    _parse_page_size,
    _parse_sort_order,
    _read_yaml_doc,
    _try_read_yaml_doc,
    _utcnow_iso,
    _write_job_lead_file,
)


def _build_lead_item(path: Path) -> JobLeadItem | None:
    doc = _try_read_yaml_doc(path)
    if doc is None:
        return None
    s = doc["scalars"]
    favorited_raw = s.get("favorited", "false").strip().lower()
    created_at = s.get("created_at", _format_utc_timestamp(path.stat().st_mtime))
    return {
        "job_lead_id": s.get("id", path.stem),
        "company": s.get("company", ""),
        "position": s.get("position", s.get("title", "")),
        "salary": s.get("salary", ""),
        "location": s.get("location", ""),
        "source": s.get("source", ""),
        "status": s.get("status", "new"),
        "favorited": favorited_raw in {"true", "1", "yes"},
        "created_at": created_at,
        "updated_at": s.get("updated_at", created_at),
        "url": s.get("url", ""),
        "platform": s.get("platform", ""),
        "platform_job_id": s.get("platform_job_id", ""),
        "platform_job_type": s.get("platform_job_type", ""),
        "jd_status": s.get("jd_status", ""),
        "fetched_at": s.get("fetched_at", ""),
        "job_profile_id": s.get("job_profile_id", ""),
        "source_jd": s.get("source_jd", ""),
        "source_jd_sha256": s.get("source_jd_sha256", ""),
        "import_mode": s.get("import_mode", ""),
        "source_recorded_at": s.get("source_recorded_at", ""),
        **{key: s.get(key, "") for key in _COMPANY_FACT_KEYS},
    }


def _apply_lead_filters(
    items: list[JobLeadItem], filters: dict[str, object]
) -> list[JobLeadItem]:
    source_filter = str(filters.get("source") or "").strip()
    status_filter = str(filters.get("status") or "").strip()
    query_filter = str(filters.get("query") or "").strip().casefold()
    favorited_filter = filters.get("favorited")
    size_max_raw = filters.get("company_size_max")
    size_max = size_max_raw if type(size_max_raw) is int else None

    filtered: list[JobLeadItem] = []
    for item in items:
        if source_filter and item["source"] != source_filter:
            continue
        if status_filter and item["status"] != status_filter:
            continue
        if favorited_filter is not None and item["favorited"] != bool(favorited_filter):
            continue
        if size_max is not None:
            upper = _company_size_upper_bound(item.get("company_size", ""))
            if upper is None or upper > size_max:
                continue
        if query_filter:
            haystack = f"{item['company']} {item['position']} {item.get('location', '')}".casefold()
            if query_filter not in haystack:
                continue
        filtered.append(item)
    return filtered


def _sort_leads(items: list[JobLeadItem], field: str, order: str) -> list[JobLeadItem]:
    reverse = order != "asc"
    return sorted(
        items, key=lambda item: (item[field], item["job_lead_id"]), reverse=reverse
    )

def handle_jobs_search_liepin(params: dict[str, Any]) -> dict[str, Any]:
    keyword, page = params.get("keyword"), params.get("page", 0)
    base = {"meta": {"correlation_id": params["meta"]["correlation_id"]},
            "items": [], "received_count": 0, "imported_count": 0,
            "page": page if type(page) is int else 0}
    if (not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 200
            or type(page) is not int or not 0 <= page <= 100):
        return {**base, **liepin_readonly.result("INVALID_INPUT")}
    result = liepin_readonly.search(keyword.strip(), page)
    if result["status"] != "pass":
        return {**base, **result}
    raw_items = result.pop("data")
    now = _utcnow_iso()
    normalized: dict[str, dict[str, Any]] = {}
    try:
        for item in raw_items:
            job_id, job_type = str(item["jobId"]), str(item["jobType"])
            url = item["jobDetailUrl"]
            if not isinstance(url, str) or not url or not isinstance(item.get("company"), str):
                raise ValueError("invalid official job fields")
            if any(item.get(key) is not None and not isinstance(item[key], str)
                   for key in ("salary", "location", *_OFFICIAL_COMPANY_FACTS)):
                raise ValueError("invalid official pay or location")
            parsed = urlparse(url)
            if (parsed.scheme != "https" or not parsed.hostname
                    or not (parsed.hostname == "liepin.com" or parsed.hostname.endswith(".liepin.com"))
                    or parsed.username or parsed.password or parsed.port not in (None, 443)):
                raise ValueError("invalid official detail URL")
            digest = hashlib.sha256(f"liepin:{job_type}:{job_id}".encode()).hexdigest()[:20]
            lead_id = f"jl_liepin_{digest}"
            normalized[lead_id] = {
                "id": lead_id, "company": item["company"], "position": item["jobName"],
                "salary": item.get("salary") or "", "location": item.get("location") or "",
                "source": "liepin_official", "url": url, "platform": "liepin",
                "platform_job_id": job_id, "platform_job_type": job_type,
                "jd_status": "summary_only", "fetched_at": now,
                "created_at": now, "updated_at": now,
                **{field: item[key].strip() for key, field in _OFFICIAL_COMPANY_FACTS.items()
                   if isinstance(item.get(key), str) and item[key].strip()},
            }
    except (KeyError, TypeError, ValueError):
        return {**base, **liepin_readonly.failure("INVALID_RESPONSE")}
    items = []
    imported_count = 0
    try:
        for lead_id, fields in normalized.items():
            path = _lead_path(lead_id)
            if path.exists():
                # 已审核/收藏/关联的本地状态不被重复搜索覆盖。
                previous = _read_yaml_doc(path)["scalars"]
                for key in ("status", "favorited", "job_profile_id", "created_at", "jd_status", "source_jd", "source_jd_sha256", "jd_origin"):
                    if key in previous:
                        fields[key] = previous[key]
            else:
                fields["status"] = "new"
            is_new = not path.exists()
            _write_job_lead_file(path, fields)
            imported_count += int(is_new)
            saved = _build_lead_item(path)
            if saved:
                items.append(saved)
    except OSError:
        return {**base, **liepin_readonly.result("STORAGE_ERROR"),
                "items": items, "received_count": len(raw_items), "imported_count": imported_count}
    return {**base, **result, "items": items, "received_count": len(raw_items),
            "imported_count": imported_count}


def handle_jobs_list_leads(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = cast(dict[str, object], params.get("sort") or {})
    filters = cast(dict[str, object], params.get("filters") or {})

    items: list[JobLeadItem] = []
    for path in _glob_files(_origin._JOB_LEAD_DIR, "*.yaml"):
        item = _build_lead_item(path)
        if item is not None:
            items.append(item)
    items = _apply_lead_filters(items, filters)
    items = _sort_leads(
        items,
        _parse_lead_sort_field(sort.get("field")),
        _parse_sort_order(sort.get("order")),
    )
    paged_items = items[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(items) else None
    return {
        "meta": {"correlation_id": correlation_id},
        "items": paged_items,
        "next_cursor": next_cursor,
    }
