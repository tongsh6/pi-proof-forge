"""猎聘投递进展只读同步：把 App 自有会话观察到的平台状态落为可追溯反馈，不改回执，不编造。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.persistence.review_queue import atomic_write_json
from tools.infra.persistence.yaml_io import parse_simple_yaml, unquote
from tools.sidecar.handlers import submission as _submission
from tools.sidecar.handlers.native_pdf import _sanitize_observation

SCHEMA_VERSION = 1
DISCOVERY = {"start_url": "https://c.liepin.com/", "link_keywords": ["投递"], "allowed_hosts": ["c.liepin.com", "www.liepin.com"]}
FUNNEL_STATES = ("delivered", "viewed", "interested", "interview", "rejected", "unknown")
# 顺序即优先级：同一标签同时命中多条时取靠前的。
_STATUS_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("interview", ("面试", "邀约", "约面")),
    ("rejected", ("不合适", "不匹配", "已拒绝", "未通过", "婉拒", "已关闭")),
    ("interested", ("感兴趣", "有意向", "合适", "待沟通", "已沟通", "已回复", "沟通中")),
    ("viewed", ("已查看", "已浏览", "已读", "查看过", "被查看")),
    ("delivered", ("已投递", "投递成功", "已申请", "已发送", "待查看", "未查看")),
)
_RECOMMENDED_ACTION = {"rejected": "update_job_target", "interview": "acknowledge_and_skip", "interested": "acknowledge_and_skip",
                       "delivered": "acknowledge_and_skip", "unknown": "acknowledge_and_skip"}
_STALE_VIEWED_DAYS = 7
_MAX_ROWS, _MAX_TEXT, _MAX_PAYLOAD = 100, 300, 65536
_JOB_ID = re.compile(r"/job/(\d+)")
# 时间只接受日期样式；"50-70k"、"3-5年" 这类区间不是时间。
_TIME_RE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2}(?:\s\d{1,2}:\d{2})?|\d{1,2}月\d{1,2}日(?:\s\d{1,2}:\d{2})?|(?<![\d-])\d{1,2}-\d{1,2}(?:\s\d{1,2}:\d{2})?(?![\dkK万元年/-])|\d+\s*(?:天|小时|分钟)前|今天|昨天)")
_MAX_LINES, _MAX_STATUS_LINE = 16, 12


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_url(value: object) -> str:
    text = str(value or "").strip()
    return re.split(r"[?#]", text, maxsplit=1)[0] if text.startswith("https://") else ""


def _text(value: object, limit: int = _MAX_TEXT) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _job_id_from_url(url: str) -> str:
    match = _JOB_ID.search(url)
    return match.group(1) if match else ""


def _clean_time(value: object) -> str:
    """只接受日期样式；裸的“月-日”还要满足月 1-12、日 1-31，排除“50-70”这类区间。"""
    for match in _TIME_RE.finditer(str(value or "")):
        token = match.group(1)
        month_day = re.match(r"^(\d{1,2})-(\d{1,2})", token)
        if month_day and not (1 <= int(month_day.group(1)) <= 12 and 1 <= int(month_day.group(2)) <= 31):
            continue
        return token
    return ""


def _status_line(lines: list[str]) -> str:
    """状态徽标都是短行；按优先级在短行里找关键词，长标题行不参与，避免“面试官”之类误判。"""
    for _status, keywords in _STATUS_RULES:
        for line in lines:
            if len(line) <= _MAX_STATUS_LINE and any(keyword in line for keyword in keywords):
                return line
    return ""


def normalize_status(label: str) -> str:
    for status, keywords in _STATUS_RULES:
        if any(keyword in label for keyword in keywords):
            return status
    return "unknown"


def _lead_identity(candidate_id: str) -> dict[str, str]:
    path = _submission._JOB_LEAD_DIR / f"{candidate_id}.yaml"
    if not candidate_id or not re.fullmatch(r"[A-Za-z0-9_-]+", candidate_id) or not path.is_file():
        return {}
    scalars = parse_simple_yaml(path.read_text(encoding="utf-8")).get("scalars", {})
    return {key: unquote(str(scalars.get(key, ""))) for key in ("platform_job_id", "url", "company", "position")}


def _managed_success_submissions() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for log_path in _submission._submission_log_paths():
        payload = _submission._load_submission_log(log_path)
        if not _submission._managed_delivery(payload) or str(payload.get("status")) != "success":
            continue
        inputs = payload.get("input_artifacts", {}) if isinstance(payload.get("input_artifacts"), dict) else {}
        lead = _lead_identity(str(inputs.get("candidate_id") or ""))
        job_url = _clean_url(lead.get("url") or "")
        items.append({
            "submission_id": str(payload.get("run_id") or log_path.parent.name),
            "log_path": log_path,
            "company": _text(inputs.get("company") or lead.get("company"), 120),
            "position": _text(inputs.get("position") or lead.get("position"), 120),
            "platform_job_id": _text(lead.get("platform_job_id"), 40),
            "job_url": job_url,
            "url_job_id": _job_id_from_url(job_url),
            "delivered_at": str(payload.get("ended_at") or payload.get("started_at") or ""),
            "delivery_kind": str(inputs.get("delivery_kind") or ("platform_default" if payload.get("transport") == "liepin_api" else "")),
        })
    return items


def handle_sync_packet(params: dict[str, Any]) -> dict[str, Any]:
    submissions = [{k: v for k, v in item.items() if k != "log_path"} for item in _managed_success_submissions()]
    return {"meta": {"correlation_id": params["meta"]["correlation_id"]}, "submissions": submissions,
            "discovery": dict(DISCOVERY), "read_only": True}


def _validated_observation(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or len(json.dumps(raw, ensure_ascii=False)) > _MAX_PAYLOAD:
        raise ValueError("invalid_feedback_observation")
    observation = _sanitize_observation(raw) or {}
    status = str(observation.get("status") or "unknown")
    if status not in {"records", "records_page_not_found", "unknown"}:
        raise ValueError("invalid_feedback_observation")
    rows_raw = observation.get("rows") if isinstance(observation.get("rows"), list) else []
    rows = []
    for row in rows_raw[:_MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        job_url = _clean_url(row.get("job_url"))
        lines = [_text(line, 60) for line in (row.get("lines") if isinstance(row.get("lines"), list) else [])[:_MAX_LINES] if isinstance(line, str) and _text(line, 60)]
        status_label = _text(row.get("status_label"), 60) or _status_line(lines)
        time_label = _clean_time(row.get("time_label")) or next((_clean_time(line) for line in lines if _clean_time(line)), "")
        rows.append({"job_url": job_url, "job_id": _text(row.get("job_id"), 40) or _job_id_from_url(job_url),
                     "company": _text(row.get("company"), 120), "position": _text(row.get("position"), 120),
                     "status_label": status_label, "time_label": time_label, "lines": lines,
                     "excerpt": _text(row.get("excerpt")) or " ".join(lines)[:_MAX_TEXT]})
    discovery = observation.get("discovery") if isinstance(observation.get("discovery"), dict) else {}
    links_raw = discovery.get("links") if isinstance(discovery.get("links"), list) else []
    links = [{"label": _text(link.get("label"), 60), "url": _clean_url(link.get("url"))} for link in links_raw[:20] if isinstance(link, dict)]
    hints_raw = observation.get("hints") if isinstance(observation.get("hints"), list) else []
    page_hints = [_text(hint, 60) for hint in hints_raw[:20] if isinstance(hint, str) and _text(hint, 60)]
    return {"status": status, "page_url": _clean_url(observation.get("page_url")), "rows": rows, "discovery_links": links, "page_hints": page_hints}


def _match_row(row: dict[str, Any], submissions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if row["job_id"]:
        for item in submissions:
            ids = {item["url_job_id"], item["platform_job_id"]} - {""}
            if row["job_id"] in ids or any(row["job_id"].endswith(value) for value in ids if len(value) >= 6):
                return item, "job_id"
    if row["company"] and row["position"]:
        hits = [item for item in submissions if item["company"] == row["company"] and item["position"] == row["position"]]
        if len(hits) == 1:
            return hits[0], "company_position"
    return None, ""


def _feedback_path(submission_dir: Path) -> Path:
    return submission_dir / "platform_feedback.json"


def _append_feedback(item: dict[str, Any], row: dict[str, Any], basis: str, page_url: str, observed_at: str) -> dict[str, Any]:
    path = _feedback_path(item["log_path"].parent)
    record = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": SCHEMA_VERSION, "submission_id": item["submission_id"], "history": []}
    entry = {"observed_at": observed_at, "page_url": page_url, "status_label": row["status_label"],
             "normalized_status": normalize_status(row["status_label"]), "match_basis": basis,
             "time_label": row["time_label"], "excerpt": row["excerpt"], "job_id": row["job_id"], "lines": row.get("lines", [])}
    record["history"] = (record.get("history") or [])[-199:] + [entry]
    record["latest"] = entry
    atomic_write_json(path, record)
    path.chmod(0o600)
    return entry


def handle_record_platform_status(params: dict[str, Any]) -> dict[str, Any]:
    observation = _validated_observation(params.get("observation"))
    observed_at = _now_iso()
    submissions = _managed_success_submissions()
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    seen: set[str] = set()
    if observation["status"] == "records":
        for row in observation["rows"]:
            item, basis = _match_row(row, submissions)
            if item is None or item["submission_id"] in seen:
                unmatched.append({k: row[k] for k in ("job_id", "company", "position", "status_label")})
                continue
            seen.add(item["submission_id"])
            entry = _append_feedback(item, row, basis, observation["page_url"], observed_at)
            matched.append({"submission_id": item["submission_id"], "normalized_status": entry["normalized_status"],
                            "status_label": entry["status_label"], "match_basis": basis})
    sync_log = {"schema_version": SCHEMA_VERSION, "synced_at": observed_at, "status": observation["status"], "page_url": observation["page_url"],
                "rows_total": len(observation["rows"]), "matched": len(matched), "unmatched_rows": unmatched[:20],
                "updated_submissions": [m["submission_id"] for m in matched], "discovery_links": observation["discovery_links"],
                "submissions_total": len(submissions), "page_hints": observation["page_hints"], "read_only": True}
    atomic_write_json(_submission._SUBMISSIONS_DIR / "liepin" / "platform_feedback_sync.json", sync_log)
    return {"meta": {"correlation_id": params["meta"]["correlation_id"]}, "status": observation["status"], "page_url": observation["page_url"],
            "matched": matched, "unmatched_rows": len(unmatched), "submissions_total": len(submissions), "synced_at": observed_at}


def platform_feedback_summary(submission_dir: Path) -> dict[str, str]:
    path = _feedback_path(submission_dir)
    if not path.is_file():
        return {}
    try:
        latest = json.loads(path.read_text(encoding="utf-8")).get("latest") or {}
    except (ValueError, OSError):
        return {}
    return {"status": str(latest.get("normalized_status") or "unknown"), "label": str(latest.get("status_label") or ""),
            "observed_at": str(latest.get("observed_at") or ""), "time_label": str(latest.get("time_label") or "")}


def recommended_action(summary: dict[str, str]) -> tuple[str, str]:
    """返回 (动作, 优先级)；已查看超过 7 天无进展提示补证据。"""
    status = summary.get("status", "unknown")
    if status == "viewed":
        try:
            observed = datetime.fromisoformat(summary.get("observed_at", "").replace("Z", "+00:00"))
            stale = (datetime.now(timezone.utc) - observed).days >= _STALE_VIEWED_DAYS
        except ValueError:
            stale = False
        return ("add_or_edit_evidence_card", "medium") if stale else ("acknowledge_and_skip", "info")
    return _RECOMMENDED_ACTION.get(status, "acknowledge_and_skip"), ("high" if status == "rejected" else "info")


def feedback_funnel() -> dict[str, int]:
    funnel = {state: 0 for state in FUNNEL_STATES}
    funnel["unsynced"] = 0
    for item in _managed_success_submissions():
        summary = platform_feedback_summary(item["log_path"].parent)
        if not summary:
            funnel["unsynced"] += 1
        else:
            funnel[summary["status"] if summary["status"] in funnel else "unknown"] += 1
    return funnel
