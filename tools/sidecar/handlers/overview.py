from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast

from tools.infra.persistence.yaml_io import ParsedDoc, parse_simple_yaml

_ROOT_DIR = Path(".")
_EVIDENCE_DIR = _ROOT_DIR / "evidence_cards"
_MATCHING_REPORT_DIR = _ROOT_DIR / "matching_reports"
_OUTPUTS_DIR = _ROOT_DIR / "outputs"
_SUBMISSIONS_DIR = _OUTPUTS_DIR / "submissions"


class SubmissionPayload(TypedDict, total=False):
    run_id: str
    platform: str
    status: str
    ended_at: str


class ActivityItem(TypedDict):
    activity_id: str
    type: str
    description: str
    timestamp: str
    sort_key: float


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


def _count_matching_reports() -> int:
    return len(_glob_files(_MATCHING_REPORT_DIR, "*.yaml"))


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
    """Extract match score from doc, preferring score_total, falling back to score_breakdown sum."""
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
        doc = _read_yaml_doc(path)
        generated_at = doc["scalars"].get("generated_at", "")
        parsed_date = _safe_parse_iso_date(generated_at)
        if parsed_date is None:
            parsed_date = datetime.fromtimestamp(path.stat().st_mtime)

        score = _score_from_doc(doc)

        trend.append({"date": parsed_date.date().isoformat(), "score": score})

    trend.sort(key=lambda item: cast(str, item["date"]))
    return trend[-30:]


def _list_recent_activity() -> list[dict[str, str]]:
    activity_items: list[ActivityItem] = []

    for path in _glob_files(_EVIDENCE_DIR, "*.yaml"):
        doc = _read_yaml_doc(path)
        title = doc["scalars"].get("title", path.stem)
        activity_items.append(
            {
                "activity_id": f"evidence_{path.stem}",
                "type": "evidence_imported",
                "description": f"Evidence updated: {title}",
                "timestamp": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "sort_key": path.stat().st_mtime,
            }
        )

    for path in _glob_files_recursive(_OUTPUTS_DIR, "resume_*.md"):
        activity_items.append(
            {
                "activity_id": f"resume_{path.stem}",
                "type": "resume_generated",
                "description": f"Generated {path.name}",
                "timestamp": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "sort_key": path.stat().st_mtime,
            }
        )

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
        activity_items.append(
            {
                "activity_id": f"submission_{run_id}",
                "type": "submission_sent",
                "description": f"Submission {status} via {platform}",
                "timestamp": timestamp,
                "sort_key": sort_key,
            }
        )

    activity_items.sort(key=lambda item: item["sort_key"], reverse=True)
    return [
        {
            "activity_id": item["activity_id"],
            "type": item["type"],
            "description": item["description"],
            "timestamp": item["timestamp"],
        }
        for item in activity_items[:6]
    ]


def handle_overview_get(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "metrics": {
            "evidence_count": _count_evidence_cards(),
            "matched_jobs_count": _count_matching_reports(),
            "resume_count": _count_resume_versions(),
            "submission_count": _count_submission_runs(),
        },
        "recent_activities": _list_recent_activity(),
        "match_trend": _build_match_trend(),
        "gaps": _build_gaps(),
    }
