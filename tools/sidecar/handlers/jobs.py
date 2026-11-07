from __future__ import annotations

import json
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib import request
from urllib.parse import urlparse
from uuid import uuid4

from tools.engines.matching import fit_precheck as fit_precheck_engine
from tools.infra.llm.client import LLMClient
from tools.infra.liepin_readonly import liepin_readonly
from tools.infra.persistence.job_lead_binding import same_official_source_url
from tools.infra.persistence.yaml_io import ParsedDoc, parse_simple_yaml
from tools.sidecar.handlers import settings as settings_handler

_ROOT_DIR = Path(".")
_JOB_PROFILE_DIR = _ROOT_DIR / "job_profiles"
_JOB_LEAD_DIR = _ROOT_DIR / "job_leads"
_MATCHING_REPORT_DIR = _ROOT_DIR / "matching_reports"
_SCORECARD_DIR = _ROOT_DIR / "outputs" / "scorecards"
_SUBMISSIONS_DIR = _ROOT_DIR / "outputs" / "submissions"
_EVIDENCE_CARD_DIR = _ROOT_DIR / "evidence_cards"
# 证据库规则预检语料缓存：(证据卡文件指纹, 语料)；只读，不写卡。
_PRECHECK_CORPUS_CACHE: tuple[tuple[tuple[str, int, int], ...], dict[str, Any]] | None = None

class MatchSnapshot(TypedDict):
    score: int
    evidence_count: int
    updated_at: str
    sort_key: float
    fit_state: str
    fit_failures: int
    fit_score: int | None
    advice: dict[str, Any] | None


class JobProfileItem(TypedDict):
    job_profile_id: str
    title: str
    company: str
    status: str
    match_score: int
    evidence_count: int
    resume_count: int
    fit_state: str
    fit_failures: int
    updated_at: str
    business_domain: str
    source_jd: str
    tone: str
    keywords: list[str]
    must_have: list[str]
    nice_to_have: list[str]
    seniority_signal: list[str]
    fit_precheck: dict[str, Any]
    native_pdf_delivery: dict[str, Any]


class JobsListResult(TypedDict):
    meta: dict[str, str]
    items: list[JobProfileItem]
    next_cursor: str | None


class JobLeadItem(TypedDict):
    job_lead_id: str
    company: str
    position: str
    salary: str
    location: str
    source: str
    status: str
    favorited: bool
    created_at: str
    updated_at: str
    url: str
    platform: str
    platform_job_id: str
    platform_job_type: str
    jd_status: str
    fetched_at: str
    company_size: str
    financing_stage: str
    industry: str
    work_years: str
    education: str


_COMPANY_FACT_KEYS = ("company_size", "financing_stage", "industry", "work_years", "education")
_OFFICIAL_COMPANY_FACTS = {"companySize": "company_size", "financingStage": "financing_stage",
                           "industry": "industry", "workYears": "work_years", "education": "education"}


def _company_size_upper_bound(text: str) -> int | None:
    """解析平台“1-49人 / 少于50人 / 50人以下”文案的人数上界；“10000人以上”等无上界返回 None。"""
    compact = re.sub(r"\s", "", str(text or ""))
    match = re.fullmatch(r"(\d+)-(\d+)人", compact)
    if match:
        return int(match.group(2))
    match = re.fullmatch(r"少于(\d+)人", compact)
    if match:
        return int(match.group(1)) - 1
    match = re.fullmatch(r"(\d+)人以下", compact)
    if match:
        return int(match.group(1))
    return None


def _glob_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.glob(pattern))


def _read_yaml_doc(path: Path) -> ParsedDoc:
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def _utcnow_iso() -> str:
    return _format_utc_datetime(datetime.now(timezone.utc))


def _quote(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _write_list(lines: list[str], key: str, values: list[str]) -> None:
    lines.append(f"{key}:")
    for value in values:
        lines.append(f"  - {_quote(value)}")


def _validate_string_list(name: str, value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    items: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"{name} must be a list of strings")
        items.append(item)
    return items


def _validate_non_empty_string_list(name: str, value: object) -> list[str]:
    return [item.strip() for item in _validate_string_list(name, value) if item.strip()]

def _write_job_profile_file(path: Path, fields: dict[str, Any]) -> None:
    lines = [
        f"target_role: {_quote(fields.get('target_role', ''))}",
        f"company: {_quote(fields.get('company', ''))}",
        f"source_jd: {_quote(fields.get('source_jd', ''))}",
        f"jd_summary: {_quote(fields.get('jd_summary', ''))}",
        f"source_url: {_quote(fields.get('source_url', ''))}",
        f"job_lead_id: {_quote(fields.get('job_lead_id', ''))}",
        f"business_domain: {_quote(fields.get('business_domain', ''))}",
        f"tone: {_quote(fields.get('tone', ''))}",
        f"description: {_quote(fields.get('description', ''))}",
        f"status: {_quote(fields.get('status', 'draft'))}",
        f"created_at: {_quote(fields.get('created_at', ''))}",
        f"updated_at: {_quote(fields.get('updated_at', ''))}",
        f"review_decision: {_quote(fields.get('review_decision', ''))}",
        f"reviewed_at: {_quote(fields.get('reviewed_at', ''))}",
    ]
    for key in ("source", "platform", "platform_job_id", "platform_job_type", "source_jd_sha256", "jd_origin",
                "import_mode", "source_recorded_at", *_COMPANY_FACT_KEYS):
        if key in fields:
            lines.append(f"{key}: {_quote(fields[key])}")
    _write_list(lines, "keywords", fields.get("keywords", []))
    _write_list(lines, "must_have", fields.get("must_have", []))
    _write_list(lines, "nice_to_have", fields.get("nice_to_have", []))
    _write_list(lines, "seniority_signal", fields.get("seniority_signal", []))
    _write_list(lines, "missing_items", fields.get("missing_items", []))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_job_lead_file(path: Path, fields: dict[str, Any]) -> None:
    defaults = {"id": path.stem, "company": "", "position": "", "source": "manual_jd",
                "url": "", "status": "new", "favorited": "false", "job_profile_id": "",
                "created_at": "", "updated_at": ""}
    values = {key: fields.get(key, default) for key, default in defaults.items()}
    for key in ("platform", "platform_job_id", "platform_job_type", "jd_status", "fetched_at",
                "source_jd", "source_jd_sha256", "jd_origin", "salary", "location",
                "import_mode", "source_recorded_at", *_COMPANY_FACT_KEYS):
        if key in fields:
            values[key] = fields[key]
    # JSON 字符串是合法 YAML 标量，保留换行同时避免外部职位文本注入 YAML 字段。
    lines = [f"{key}: {json.dumps(str(value), ensure_ascii=False)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".yaml.tmp")
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _profile_path(job_profile_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", job_profile_id):
        raise ValueError("invalid_job_profile_id")
    return _JOB_PROFILE_DIR / f"{job_profile_id}.yaml"


def _lead_path(job_lead_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", job_lead_id):
        raise ValueError("invalid_job_lead_id")
    return _JOB_LEAD_DIR / f"{job_lead_id}.yaml"


def _bound_lead(job_lead_id: object, source_url: str = "") -> tuple[Path, dict[str, str]] | None:
    if not job_lead_id:
        return None
    if not isinstance(job_lead_id, str):
        raise ValueError("invalid_job_lead_id")
    path = _find_lead_path(job_lead_id)
    if path is None:
        raise KeyError("NOT_FOUND: job_lead")
    fields = _read_yaml_doc(path)["scalars"]
    original = fields.get("url", "")
    if source_url and source_url != original:
        # 猎聘的 query/fragment 是跟踪参数，岗位身份由原始 ID 和详情 path 共同核实。
        same_official_page = (fields.get("source") == "liepin_official" and
                             same_official_source_url(source_url, original))
        if not same_official_page:
            raise ValueError("source_url_mismatch")
    return path, fields


def _lead_identity(lead: dict[str, str]) -> dict[str, str]:
    identity = {key: lead.get(key, "") for key in ("source", "platform", "platform_job_id", "platform_job_type")}
    identity.update({key: lead[key] for key in _COMPANY_FACT_KEYS if lead.get(key)})
    return identity


def _preserved_profile_fields(doc: ParsedDoc) -> dict[str, Any]:
    return {**doc["scalars"], **doc["lists"]}


def _try_read_yaml_doc(path: Path) -> ParsedDoc | None:
    try:
        return _read_yaml_doc(path)
    except (OSError, UnicodeDecodeError):
        return None


# 来源链接按域名识别平台；识别只看域名，不向平台发请求。
_PLATFORM_DOMAINS: tuple[tuple[str, str], ...] = (
    ("maimai.cn", "maimai"),
    ("lagou.com", "lagou"),
    ("zhipin.com", "boss"),
    ("zhaopin.com", "zhilian"),
    ("51job.com", "qiancheng"),
    ("liepin.com", "liepin"),
)
# 这些平台的协议禁止脚本访问，链接会触发登录或验证页：人工导入时只做 HTTPS 语法校验，不做可达性 GET。
MANUAL_IMPORT_PLATFORMS = frozenset({"maimai", "lagou", "boss", "zhilian", "qiancheng"})


def platform_from_url(source_url: str) -> str:
    if not source_url.strip():
        return ""
    host = (urlparse(source_url.strip()).hostname or "").lower()
    if not host:
        return "other"
    for domain, platform in _PLATFORM_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return platform
    return "other"


def _check_source_url_accessible(
    source_url: str, timeout_seconds: int = 5
) -> dict[str, object]:
    if not source_url:
        return {"checked": False, "accessible": False, "status": "not_provided"}
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return {"checked": True, "accessible": False, "status": "invalid_url"}
    if os.environ.get("PPF_JOB_SOURCE_URL_CHECK_MODE") == "stub":
        return {
            "checked": True,
            "accessible": True,
            "status": "accessible",
            "status_code": 200,
            "mode": "stub",
        }
    req = request.Request(
        source_url, method="GET", headers={"User-Agent": "PiProofForge/0.1"}
    )
    try:
        response = request.urlopen(req, timeout=timeout_seconds)
        try:
            status_code = int(getattr(response, "status", 200))
        finally:
            response.close()
    except Exception as exc:
        return {
            "checked": True,
            "accessible": False,
            "status": "job_source_unavailable",
            "error": str(exc),
        }
    accessible = 200 <= status_code < 400
    return {
        "checked": True,
        "accessible": accessible,
        "status": "accessible" if accessible else "job_source_unavailable",
        "status_code": status_code,
    }


def _format_utc_datetime(value: datetime) -> str:
    normalized = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_utc_timestamp(value: float) -> str:
    return _format_utc_datetime(datetime.fromtimestamp(value, tz=timezone.utc))


def _safe_parse_iso_date(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed

def _load_precheck_corpus() -> dict[str, Any]:
    """加载已审核证据卡的规则预检语料；按文件指纹缓存，不读取未完成/不可入池卡。"""
    global _PRECHECK_CORPUS_CACHE
    paths = _glob_files(_EVIDENCE_CARD_DIR, "*.yaml")
    fingerprint = tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths
    )
    cached = _PRECHECK_CORPUS_CACHE
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    cards: list[dict[str, Any]] = []
    for path in paths:
        doc = _try_read_yaml_doc(path)
        if doc is None:
            continue
        scalars = doc["scalars"]
        if scalars.get("status", "").strip() != "saved_eligible":
            continue
        if scalars.get("candidate_pool_eligible", "").strip().lower() == "false":
            continue
        cards.append({**scalars, **doc["lists"]})
    corpus = fit_precheck_engine.build_evidence_corpus(cards)
    _PRECHECK_CORPUS_CACHE = (fingerprint, corpus)
    return corpus

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


def _parse_cursor(value: object) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _parse_sort_field(value: object) -> str:
    field = str(value or "updated_at")
    if field in {"match_score", "updated_at", "fit_precheck"}:
        return field
    return "updated_at"


def _parse_lead_sort_field(value: object) -> str:
    field = str(value or "updated_at")
    if field in {"updated_at", "created_at"}:
        return field
    return "updated_at"


def _parse_sort_order(value: object) -> str:
    order = str(value or "desc")
    if order in {"asc", "desc"}:
        return order
    return "desc"

def _running_submission_profile_ids() -> set[str]:
    profile_ids: set[str] = set()
    if not _SUBMISSIONS_DIR.exists():
        return profile_ids
    for path in _SUBMISSIONS_DIR.rglob("submission_log.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") != "running":
            continue
        profile_path = str(payload.get("profile_path", "")).strip()
        if profile_path:
            profile_ids.add(Path(profile_path).stem)
    return profile_ids


def _clear_lead_profile_reference(job_profile_id: str) -> None:
    if not _JOB_LEAD_DIR.exists():
        return
    for path in _JOB_LEAD_DIR.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        updated_lines: list[str] = []
        changed = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("job_profile_id:"):
                current_value = stripped.split(":", 1)[1].strip().strip('"')
                if current_value == job_profile_id:
                    updated_lines.append('job_profile_id: ""')
                    changed = True
                    continue
            updated_lines.append(line)
        if changed:
            path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def _find_lead_path(job_lead_id: str) -> Path | None:
    direct_path = _lead_path(job_lead_id)
    if direct_path.exists():
        return direct_path
    for path in _glob_files(_JOB_LEAD_DIR, "*.yaml"):
        doc = _try_read_yaml_doc(path)
        if doc is None:
            continue
        if doc["scalars"].get("id", path.stem) == job_lead_id:
            return path
    return None

# 拆分子模块继续以 jobs 作为公开入口 re-export。
from tools.sidecar.handlers.jobs_matching import (  # noqa: E402
    handle_jobs_list_profiles,
)
from tools.sidecar.handlers.jobs_leads import (  # noqa: E402
    _apply_lead_filters,
    handle_jobs_list_leads,
    handle_jobs_search_liepin,
)
from tools.sidecar.handlers.jobs_profiles import (  # noqa: E402
    _build_job_profile_draft,
    handle_jobs_convert_lead,
    handle_jobs_create_profile,
    handle_jobs_delete_profile,
    handle_jobs_fetch_liepin_detail,
    handle_jobs_generate_profile_draft,
    handle_jobs_save_profile_draft,
    handle_jobs_update_profile,
)

