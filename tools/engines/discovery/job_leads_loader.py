"""Load job candidates with 3-level fallback discovery.

Level 1: job_leads/*.yaml        — explicit leads with URLs
Level 2: jd_inputs/*.txt          — extract company/position/direction from JD text
Level 3: job_profiles/*.yaml      — derive candidates from target profiles
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.domain.value_objects import Candidate
from tools.infra.persistence.yaml_io import parse_simple_yaml

JOB_LEADS_DIR = Path("job_leads")
JD_INPUTS_DIR = Path("jd_inputs")
JOB_PROFILES_DIR = Path("job_profiles")

# Known job search platforms for URL detection
PLATFORM_PATTERNS = {
    "liepin": re.compile(r"https?://(?:www\.)?liepin\.com/\S+", re.IGNORECASE),
    "zhipin": re.compile(r"https?://(?:www\.)?zhipin\.com/\S+", re.IGNORECASE),
    "51job": re.compile(r"https?://(?:www\.)?51job\.com/\S+", re.IGNORECASE),
}

DIRECTION_KEYWORDS: dict[str, list[str]] = {
    "backend": ["后端", "java", "go", "python", "平台", "架构", "服务端", "中间件"],
    "frontend": ["前端", "react", "vue", "h5", "小程序"],
    "data": ["数据", "数仓", "etl", "大数据", "算法", "ai"],
    "sre": ["sre", "运维", "稳定性", "devops", "基础设施"],
    "fullstack": ["全栈", "fullstack", "full-stack"],
}


def _detect_direction(text: str) -> str:
    text_lower = text.casefold()
    scores: dict[str, int] = {}
    for direction, keywords in DIRECTION_KEYWORDS.items():
        scores[direction] = sum(1 for kw in keywords if kw.casefold() in text_lower)
    if not scores or max(scores.values()) == 0:
        return "backend"
    return max(scores, key=lambda k: scores[k])


def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for pattern in PLATFORM_PATTERNS.values():
        urls.extend(pattern.findall(text))
    return urls


def _extract_company(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        for prefix in ("公司：", "公司:", "Company:", "company:"):
            if line.startswith(prefix):
                return line[len(prefix):].strip().split("（")[0].split("(")[0].strip()
    return ""


def _extract_position(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        for prefix in ("岗位：", "职位：", "Title:", "Position:"):
            if line.startswith(prefix):
                return line[len(prefix):].strip()
    first_line = text.strip().split("\n")[0].strip()
    return first_line[:80] if first_line else ""


def load_candidates_from_job_leads(base_dir: Path | None = None) -> list[Candidate]:
    """Level 1: explicit job leads with URLs."""
    leads_dir = base_dir or JOB_LEADS_DIR
    if not leads_dir.exists():
        return []

    candidates: list[Candidate] = []
    for path in sorted(leads_dir.glob("*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = doc.get("lists", {}).get("items", [])
        for idx, item in enumerate(items):
            if isinstance(item, dict) and item.get("job_url"):
                candidates.append(_make_candidate(item, path.stem, idx))
    return candidates


def load_candidates_from_jd_inputs(base_dir: Path | None = None) -> list[Candidate]:
    """Level 2: extract candidates from JD text files."""
    jd_dir = base_dir or JD_INPUTS_DIR
    if not jd_dir.exists():
        return []

    candidates: list[Candidate] = []
    for path in sorted(jd_dir.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        company = _extract_company(text)
        position = _extract_position(text)
        urls = _extract_urls(text)
        direction = _detect_direction(text)
        job_url = urls[0] if urls else ""

        candidates.append(Candidate(
            candidate_id=f"jd-{path.stem}",
            direction=direction,
            company=company or path.stem,
            job_url=job_url,
            confidence=0.7 if urls else 0.3,
            source=f"jd_inputs:{path.name}",
            merged_sources=(f"jd_inputs:{path.name}",),
        ))
    return candidates


def load_candidates_from_job_profiles(base_dir: Path | None = None) -> list[Candidate]:
    """Level 3: derive candidates from job profiles (no URLs, for direction discovery)."""
    jp_dir = base_dir or JOB_PROFILES_DIR
    if not jp_dir.exists():
        return []

    candidates: list[Candidate] = []
    for path in sorted(jp_dir.glob("*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        scalars = doc.get("scalars", {})
        lists = doc.get("lists", {})
        title = scalars.get("target_role", scalars.get("title", path.stem))
        keywords = lists.get("keywords", [])
        city = scalars.get("city", "上海")
        business_domain = scalars.get("business_domain", "")

        # Build synthetic candidate without URL — used for direction discovery
        # and matching practice, not delivery
        candidates.append(Candidate(
            candidate_id=f"jp-{path.stem}",
            direction=_detect_direction(" ".join(keywords) + " " + title),
            company=f"{city} · {business_domain}" if business_domain else city,
            job_url="",
            confidence=0.4,
            source=f"job_profiles:{path.stem}",
            merged_sources=(f"job_profiles:{path.stem}",),
        ))
    return candidates


def discover_candidates(
    base_dir: Path | None = None,
    base_jd_dir: Path | None = None,
    base_jp_dir: Path | None = None,
) -> list[Candidate]:
    """Full 3-level fallback: job_leads → jd_inputs → job_profiles.

    Returns all discovered candidates. Each level's results are appended.
    Candidates without job_url can be used for direction discovery/matching
    but not for delivery.
    """
    candidates: list[Candidate] = []

    # Level 1
    leads = load_candidates_from_job_leads(base_dir)
    if leads:
        return leads  # explicit leads override all fallbacks

    # Level 2
    jd_candidates = load_candidates_from_jd_inputs(base_jd_dir)
    candidates.extend(jd_candidates)

    # Level 3
    jp_candidates = load_candidates_from_job_profiles(base_jp_dir)
    candidates.extend(jp_candidates)

    return candidates


def _make_candidate(data: dict, source_id: str, index: int) -> Candidate:
    return Candidate(
        candidate_id=f"{source_id}-{index}",
        direction=data.get("direction", data.get("role_keyword", "backend")),
        company=data.get("company_name", data.get("company", "")),
        job_url=data.get("job_url", ""),
        confidence=float(data.get("confidence", 0.7)),
        source=f"job_leads:{source_id}",
        merged_sources=(f"job_leads:{source_id}",),
    )
