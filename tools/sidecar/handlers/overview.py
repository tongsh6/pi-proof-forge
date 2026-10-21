from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast

from tools.infra.persistence.yaml_io import ParsedDoc, parse_simple_yaml

_ROOT_DIR = Path(".")
_EVIDENCE_DIR = _ROOT_DIR / "evidence_cards"
_MATCHING_REPORT_DIR = _ROOT_DIR / "matching_reports"
_OUTPUTS_DIR = _ROOT_DIR / "outputs"
_SUBMISSIONS_DIR = _OUTPUTS_DIR / "submissions"
_JOB_PROFILE_DIR = _ROOT_DIR / "job_profiles"


class SubmissionPayload(TypedDict, total=False):
    run_id: str
    platform: str
    status: str
    ended_at: str
    input_artifacts: dict[str, object]
    company: str
    position: str
    job_company: str
    job_title: str


class ActivityItemBase(TypedDict):
    activity_id: str
    type: str
    description: str
    timestamp: str
    sort_key: float


class ActivityItem(ActivityItemBase, total=False):
    # 可读展示字段：GUI 按语言本地化这些字段，description 仅作人类可读回退。
    target_role: str
    company: str
    variant: str
    platform: str
    status: str
    title: str


def _glob_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.glob(pattern))


def _glob_files_recursive(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.rglob(pattern))


def _count_evidence_cards() -> int:
    return len(_glob_files(_EVIDENCE_DIR, "*.yaml"))


def _count_matched_job_profiles() -> int:
    job_profile_ids: set[str] = set()
    for path in _glob_files(_MATCHING_REPORT_DIR, "*.yaml"):
        try:
            doc = _read_yaml_doc(path)
            job_profile_id = doc["scalars"].get("job_profile_id", "").strip()
            if job_profile_id:
                job_profile_ids.add(job_profile_id)
        except Exception:
            # Best-effort metric: skip unparseable report files
            pass
    return len(job_profile_ids)


def _count_resume_versions() -> int:
    return len(_glob_files_recursive(_OUTPUTS_DIR, "resume_*.md"))


def _count_submission_runs() -> int:
    return len(_glob_files_recursive(_SUBMISSIONS_DIR, "submission_log.json"))


def _safe_parse_iso_date(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _read_yaml_doc(path: Path) -> ParsedDoc:
    text = path.read_text(encoding="utf-8")
    return parse_simple_yaml(text)


def _read_yaml_scalars(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return _read_yaml_doc(path)["scalars"]
    except (OSError, ValueError):
        return {}


def _target_label(target: dict[str, str]) -> str:
    return " · ".join(
        value for value in (target.get("target_role", ""), target.get("company", "")) if value
    )


def _resume_activity_target(path: Path) -> dict[str, str]:
    """按生成简历文件名里的匹配报告编号回查岗位画像，避免活动流显示原始运行编号。"""
    stem = path.stem
    if not stem.startswith("resume_"):
        return {}
    report_id, separator, variant = stem.removeprefix("resume_").rpartition("_")
    if not separator or not report_id.startswith("mr-") or not re.fullmatch(r"[A-Za-z]{1,2}", variant):
        return {}
    report = _read_yaml_scalars(_MATCHING_REPORT_DIR / f"{report_id}.yaml")
    job_profile_id = report.get("job_profile_id", "").strip()
    profile = (
        _read_yaml_scalars(_JOB_PROFILE_DIR / f"{job_profile_id}.yaml")
        if job_profile_id
        else {}
    )
    target: dict[str, str] = {}
    for key, value in (
        ("target_role", profile.get("target_role", "")),
        ("company", profile.get("company", "")),
        ("variant", variant),
    ):
        cleaned = value.strip()
        if cleaned:
            target[key] = cleaned
    return target


def _resume_activity_description(target: dict[str, str]) -> str:
    label = _target_label(target)
    variant = target.get("variant", "")
    if label and variant:
        return f"Resume generated for {label} (variant {variant})"
    if label:
        return f"Resume generated for {label}"
    if variant:
        return f"Resume generated (variant {variant})"
    return "Resume generated"


def _submission_activity_target(payload: SubmissionPayload) -> dict[str, str]:
    inputs = payload.get("input_artifacts")
    inputs = inputs if isinstance(inputs, dict) else {}
    company = str(
        inputs.get("company") or payload.get("company") or payload.get("job_company") or ""
    ).strip()
    position = str(
        inputs.get("position") or payload.get("position") or payload.get("job_title") or ""
    ).strip()
    target: dict[str, str] = {}
    if position:
        target["target_role"] = position
    if company:
        target["company"] = company
    return target


def _submission_activity_description(target: dict[str, str], platform: str, status: str) -> str:
    label = _target_label(target)
    if not label:
        return f"Submission {status} via {platform}"
    if status == "success":
        return f"Submitted to {label} via {platform}"
    return f"Submission {status} for {label} via {platform}"


def _score_from_text(text: str) -> int:
    lines = text.splitlines()
    in_breakdown = False
    total = 0

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("score_breakdown:"):
            in_breakdown = True
            continue
        if in_breakdown:
            if not line.startswith("  "):
                break
            match = re.search(r"score\s*:\s*(\d+)", stripped)
            if match:
                total += int(match.group(1))

    return min(100, total)


def _build_gaps() -> list[dict[str, str]]:
    reports = sorted(_glob_files(_MATCHING_REPORT_DIR, "*.yaml"))
    if not reports:
        return []

    latest = max(reports, key=lambda path: path.stat().st_mtime)
    doc = _read_yaml_doc(latest)
    descriptions = doc["lists"].get("gaps", [])
    suggested_actions = doc["lists"].get("gap_tasks", [])

    gaps: list[dict[str, str]] = []
    for index, description in enumerate(descriptions[:5], start=1):
        severity = "high" if index == 1 else "medium"
        suggested_action = (
            suggested_actions[index - 1]
            if index - 1 < len(suggested_actions)
            else "Review matching report and add supporting evidence"
        )
        gaps.append(
            {
                "gap_id": f"gap_{index}",
                "severity": severity,
                "description": description,
                "suggested_action": suggested_action,
            }
        )

    return gaps


def _score_from_doc(doc: ParsedDoc) -> int:
    total_str = doc["scalars"].get("score_total", "")
    if total_str:
        try:
            return min(100, int(total_str))
        except ValueError:
            pass
    breakdown = doc["lists"].get("score_breakdown", {})
    if isinstance(breakdown, dict):
        total = 0.0
        for val in breakdown.values():
            if isinstance(val, dict):
                try:
                    total += float(val.get("score", 0))
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    total += float(val)
                except (ValueError, TypeError):
                    pass
        return min(100, int(total))
    return 0


def _build_match_trend() -> list[dict[str, int | str]]:
    reports = sorted(_glob_files(_MATCHING_REPORT_DIR, "*.yaml"))
    trend: list[dict[str, int | str]] = []

    for path in reports:
        text = path.read_text(encoding="utf-8")
        doc = parse_simple_yaml(text)
        generated_at = doc["scalars"].get("generated_at", "")
        parsed_date = _safe_parse_iso_date(generated_at)
        if parsed_date is None:
            parsed_date = datetime.fromtimestamp(path.stat().st_mtime)

        score = _score_from_doc(doc)
        if score == 0 and "score_total" not in doc["scalars"]:
            score = _score_from_text(text)

        trend.append({"date": parsed_date.date().isoformat(), "score": score})

    trend.sort(key=lambda item: cast(str, item["date"]))
    return trend[-30:]


def _list_recent_activity() -> list[dict[str, str]]:
    activity_items: list[ActivityItem] = []

    for path in _glob_files(_EVIDENCE_DIR, "*.yaml"):
        doc = _read_yaml_doc(path)
        title = doc["scalars"].get("title", "").strip()
        item: ActivityItem = {
            "activity_id": f"evidence_{path.stem}",
            "type": "evidence_imported",
            "description": f"Evidence updated: {title}" if title else "Evidence updated",
            "timestamp": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "sort_key": path.stat().st_mtime,
        }
        if title:
            item["title"] = title
        activity_items.append(item)

    for path in _glob_files_recursive(_OUTPUTS_DIR, "resume_*.md"):
        target = _resume_activity_target(path)
        item = {
            "activity_id": f"resume_{path.stem}",
            "type": "resume_generated",
            "description": _resume_activity_description(target),
            "timestamp": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "sort_key": path.stat().st_mtime,
            **target,
        }
        activity_items.append(cast(ActivityItem, item))

    for path in _glob_files_recursive(_SUBMISSIONS_DIR, "submission_log.json"):
        payload = cast(SubmissionPayload, json.loads(path.read_text(encoding="utf-8")))
        run_id = payload.get("run_id", path.parent.name)
        platform = payload.get("platform", "submission")
        status = payload.get("status", "unknown")
        ended_at = payload.get("ended_at", "")
        parsed = _safe_parse_iso_date(ended_at)
        sort_key = parsed.timestamp() if parsed is not None else path.stat().st_mtime
        timestamp = (
            ended_at if ended_at else datetime.fromtimestamp(sort_key).isoformat()
        )
        target = _submission_activity_target(payload)
        item = {
            "activity_id": f"submission_{run_id}",
            "type": "submission_sent",
            "description": _submission_activity_description(target, platform, status),
            "timestamp": timestamp,
            "sort_key": sort_key,
            "platform": platform,
            "status": status,
            **target,
        }
        activity_items.append(cast(ActivityItem, item))

    activity_items.sort(key=lambda item: item["sort_key"], reverse=True)
    recent: list[dict[str, str]] = []
    for item in activity_items[:6]:
        entry: dict[str, str] = {
            "activity_id": item["activity_id"],
            "type": item["type"],
            "description": item["description"],
            "timestamp": item["timestamp"],
        }
        for key in ("target_role", "company", "variant", "platform", "status", "title"):
            value = item.get(key)
            if value:
                entry[key] = value
        recent.append(entry)
    return recent


def _feedback_funnel() -> dict[str, int]:
    from tools.sidecar.handlers.platform_feedback import feedback_funnel
    return feedback_funnel()


def handle_overview_get(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "metrics": {
            "evidence_count": _count_evidence_cards(),
            "matched_jobs_count": _count_matched_job_profiles(),
            "resume_count": _count_resume_versions(),
            "submission_count": _count_submission_runs(),
            "feedback_funnel": _feedback_funnel(),
        },
        "recent_activities": _list_recent_activity(),
        "match_trend": _build_match_trend(),
        "gaps": _build_gaps(),
    }
