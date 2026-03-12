from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from tools.infra.persistence.yaml_io import parse_simple_yaml

_OUTPUTS_DIR = Path("outputs")
_UPLOADED_DIR = Path("uploaded_resumes")
_MATCHING_REPORT_DIR = Path("matching_reports")
_JOB_PROFILE_DIR = Path("job_profiles")
_ALLOWED_SUFFIXES = {".pdf", ".docx"}


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _glob_generated_resumes() -> list[Path]:
    if not _OUTPUTS_DIR.exists():
        return []
    return sorted(_OUTPUTS_DIR.rglob("resume_*.md"))


def _glob_uploaded_meta() -> list[Path]:
    if not _UPLOADED_DIR.exists():
        return []
    return sorted(_UPLOADED_DIR.glob("*.meta.yaml"))


def _format_updated_at(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_cursor(value: object) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _parse_page_size(value: object) -> int:
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            parsed = 20
    else:
        parsed = 20
    return max(1, min(parsed, 100))


def _parse_sort_field(value: object) -> str:
    field = str(value or "updated_at")
    if field in {"updated_at", "score"}:
        return field
    return "updated_at"


def _parse_sort_order(value: object) -> str:
    order = str(value or "desc")
    if order in {"asc", "desc"}:
        return order
    return "desc"


def _safe_parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _job_profile_id_from_report_id(report_id: str) -> str:
    report_path = _MATCHING_REPORT_DIR / f"{report_id}.yaml"
    if not report_path.exists():
        return ""
    doc = parse_simple_yaml(report_path.read_text(encoding="utf-8"))
    return doc["scalars"].get("job_profile_id", "")


def _score_from_report_id(report_id: str) -> int:
    report_path = _MATCHING_REPORT_DIR / f"{report_id}.yaml"
    if not report_path.exists():
        return 0
    doc = parse_simple_yaml(report_path.read_text(encoding="utf-8"))
    score_raw = doc["scalars"].get("score_total", "")
    if not score_raw:
        return 0
    try:
        return int(score_raw)
    except ValueError:
        return 0


def _company_from_job_profile_id(job_profile_id: str) -> str:
    if not job_profile_id:
        return ""
    profile_path = _JOB_PROFILE_DIR / f"{job_profile_id}.yaml"
    if not profile_path.exists():
        return ""
    doc = parse_simple_yaml(profile_path.read_text(encoding="utf-8"))
    return doc["scalars"].get("company", "")


def _parse_generated_resume(path: Path) -> dict[str, Any]:
    name = path.stem
    parts = name.split("_")
    job_profile_id = ""
    score = 0
    company = ""
    if len(parts) >= 3:
        report_id = parts[1]
        if report_id.startswith("mr-"):
            job_profile_id = _job_profile_id_from_report_id(report_id)
            score = _score_from_report_id(report_id)
            company = _company_from_job_profile_id(job_profile_id)
    return {
        "resume_id": f"gen_{name}",
        "name": name,
        "job_profile_id": job_profile_id,
        "status": "latest",
        "score": score,
        "company": company,
        "updated_at": _format_updated_at(path),
    }


def _parse_uploaded_resume(meta_path: Path) -> dict[str, Any]:
    doc = parse_simple_yaml(meta_path.read_text(encoding="utf-8"))
    s = doc["scalars"]
    score_raw = s.get("score", "")
    try:
        score = int(score_raw) if score_raw else 0
    except ValueError:
        score = 0
    return {
        "resume_id": s.get("resume_id", meta_path.stem.removesuffix(".meta")),
        "name": s.get("label", meta_path.stem),
        "job_profile_id": "",
        "status": "uploaded",
        "score": score,
        "company": "",
        "updated_at": s.get("uploaded_at", _format_updated_at(meta_path)),
    }


def _find_generated_resume(resume_id: str) -> Path | None:
    for path in _glob_generated_resumes():
        if f"gen_{path.stem}" == resume_id:
            return path
    return None


def _find_uploaded_meta(resume_id: str) -> Path | None:
    path = _UPLOADED_DIR / f"{resume_id}.meta.yaml"
    if path.exists():
        return path
    return None


def _parse_preview_markdown(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    name = ""
    summary_lines: list[str] = []
    skills: list[str] = []
    experience: list[dict[str, Any]] = []
    current_section = ""
    current_experience: dict[str, Any] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not name:
            name = stripped[2:].strip()
            continue
        if stripped.startswith("Generated at:") or stripped.startswith(
            "Source report:"
        ):
            continue
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower()
            if current_section != "experience" and current_experience is not None:
                experience.append(current_experience)
                current_experience = None
            continue
        if current_section == "10-second summary" and stripped.startswith("- "):
            value = stripped[2:].strip()
            summary_lines.append(value)
            if value.startswith("核心技术栈："):
                stack_line = value.removeprefix("核心技术栈：").strip()
                skills.extend(
                    item.strip() for item in stack_line.split(",") if item.strip()
                )
            continue
        if current_section == "experience" and stripped.startswith("### "):
            if current_experience is not None:
                experience.append(current_experience)
            heading = stripped[4:].strip()
            company = heading
            period = ""
            if "（" in heading and heading.endswith("）"):
                company, period = heading[:-1].split("（", 1)
                company = company.strip()
                period = period.strip()
            current_experience = {
                "company": company,
                "title": "",
                "period": period,
                "bullets": [],
            }
            continue
        if current_section == "experience" and stripped.startswith("- "):
            if current_experience is None:
                continue
            bullet = stripped[2:].strip()
            if bullet.startswith("角色与范围："):
                current_experience["title"] = bullet.removeprefix(
                    "角色与范围："
                ).strip()
            else:
                current_experience["bullets"].append(bullet)
            continue

    if current_experience is not None:
        experience.append(current_experience)

    return {
        "name": name,
        "contact": {"phone": "", "email": "", "city": ""},
        "summary": " ".join(summary_lines).strip(),
        "experience": experience,
        "skills": skills,
    }


def handle_resume_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    cursor = _parse_cursor(params.get("cursor"))
    page_size = _parse_page_size(params.get("page_size"))
    sort = params.get("sort") or {}
    filters = params.get("filters") or {}

    items = [_parse_generated_resume(path) for path in _glob_generated_resumes()]
    items.extend(_parse_uploaded_resume(path) for path in _glob_uploaded_meta())

    job_profile_filter = str(filters.get("job_profile") or "").strip()
    status_filter = str(filters.get("status") or "").strip()
    company_filter = str(filters.get("company") or "").strip()

    filtered: list[dict[str, Any]] = []
    for item in items:
        if job_profile_filter and item["job_profile_id"] != job_profile_filter:
            continue
        if status_filter and item["status"] != status_filter:
            continue
        if company_filter and item["company"] != company_filter:
            continue
        filtered.append(item)

    sort_field = _parse_sort_field(sort.get("field"))
    sort_order = _parse_sort_order(sort.get("order"))
    reverse = sort_order != "asc"
    if sort_field == "score":
        filtered.sort(
            key=lambda item: (int(item.get("score", 0)), item.get("updated_at", "")),
            reverse=reverse,
        )
    else:
        filtered.sort(
            key=lambda item: item.get("updated_at", ""),
            reverse=reverse,
        )

    page = filtered[cursor : cursor + page_size]
    next_offset = cursor + page_size
    next_cursor = str(next_offset) if next_offset < len(filtered) else None
    return {
        "meta": {"correlation_id": correlation_id},
        "items": page,
        "next_cursor": next_cursor,
    }


def handle_resume_upload(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    source_paths = params.get("source_paths", [])
    if not isinstance(source_paths, list) or len(source_paths) != 1:
        raise ValueError("source_paths must contain exactly one file")
    source = Path(str(source_paths[0]))
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"resume source not found: {source}")
    if source.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise ValueError("unsupported resume file type")

    language = str(params.get("language", "zh") or "zh").strip()
    if language not in {"zh", "en"}:
        language = "zh"
    label = str(params.get("label", source.stem) or source.stem).strip()
    if len(label) > 100:
        raise ValueError("label must not exceed 100 characters")

    resume_id = f"rv_{uuid4().hex[:8]}"
    resource_id = f"res_{uuid4().hex[:8]}"
    uploaded_at = _utcnow_iso()

    _UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
    destination = _UPLOADED_DIR / f"{resume_id}{source.suffix.lower()}"
    shutil.copy2(source, destination)
    meta_path = _UPLOADED_DIR / f"{resume_id}.meta.yaml"
    meta_path.write_text(
        "\n".join(
            [
                f"resume_id: {_quote(resume_id)}",
                f"label: {_quote(label)}",
                f"language: {_quote(language)}",
                f"resource_id: {_quote(resource_id)}",
                f"uploaded_at: {_quote(uploaded_at)}",
                f"filename: {_quote(destination.name)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "meta": {"correlation_id": correlation_id},
        "resume_id": resume_id,
        "label": label,
        "language": language,
        "resource_id": resource_id,
        "uploaded_at": uploaded_at,
    }


def handle_resume_get_preview(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    resume_id = str(params["resume_id"])

    generated = _find_generated_resume(resume_id)
    if generated is not None:
        preview = _parse_preview_markdown(generated.read_text(encoding="utf-8"))
        return {
            "meta": {"correlation_id": correlation_id},
            "resume_id": resume_id,
            "preview": preview,
        }

    uploaded_meta = _find_uploaded_meta(resume_id)
    if uploaded_meta is not None:
        return {
            "meta": {"correlation_id": correlation_id},
            "resume_id": resume_id,
            "preview": None,
            "preview_status": "pending",
        }

    raise KeyError(f"NOT_FOUND: {resume_id}")


def handle_resume_export_pdf(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    resume_id = str(params["resume_id"])
    destination = Path(str(params["destination"]))

    source = _find_generated_resume(resume_id)
    if source is None:
        uploaded_meta = _find_uploaded_meta(resume_id)
        if uploaded_meta is not None:
            candidate_files = list(_UPLOADED_DIR.glob(f"{resume_id}.*"))
            source = next(
                (
                    path
                    for path in candidate_files
                    if path.name != f"{resume_id}.meta.yaml"
                ),
                None,
            )
    if source is None:
        raise KeyError(f"NOT_FOUND: {resume_id}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdf":
        shutil.copy2(source, destination)
    else:
        raise ValueError("cannot export non-PDF resume source")

    return {
        "meta": {"correlation_id": correlation_id},
        "resource_id": f"pdf_{uuid4().hex[:8]}",
    }
