"""Load job candidates with fallback discovery.

Level 1: job_leads/*.yaml        — explicit leads with URLs
Level 1.5: optional platform search — real job URLs from profile keywords
Level 2: jd_inputs/*.txt          — extract company/position/direction from JD text
Level 3: job_profiles/*.yaml      — derive candidates from target profiles
"""

from __future__ import annotations

import re
import os
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
    *,
    enable_liepin_search: bool | None = None,
    enable_boss_agent_search: bool | None = None,
    session_dir: str = "outputs/sessions",
    excluded_companies: tuple[str, ...] = (),
    search_keywords: list[str] | None = None,
    search_city: str = "上海",
    boss_agent_platforms: tuple[str, ...] = ("boss", "zhilian"),
) -> list[Candidate]:
    """Full discovery: job_leads → optional platform search → jd_inputs → job_profiles.

    Level 1: job_leads/*.yaml — explicit leads with real URLs
    Level 1.5a: boss-agent-cli search — optional BOSS/智联 read-only search
    Level 1.5b: Liepin search — optional real job URLs from profile keywords
    Level 2: jd_inputs/*.txt — extract company/position/direction from JD text
    Level 3: job_profiles/*.yaml — derive search directions

    If search_keywords is provided, use them directly for targeted platform search
    instead of deriving keywords from job_profiles.
    """
    candidates: list[Candidate] = []
    if enable_liepin_search is None:
        enable_liepin_search = os.getenv("PPF_ENABLE_LIEPIN_SEARCH", "0") == "1"
    if enable_boss_agent_search is None:
        enable_boss_agent_search = os.getenv("PPF_ENABLE_BOSS_AGENT_SEARCH", "0") == "1"

    # Level 1: explicit leads override all fallbacks
    leads = load_candidates_from_job_leads(base_dir)
    if leads:
        return leads

    # Levels 2 + 3: load from jd_inputs + job_profiles
    jd_candidates = load_candidates_from_jd_inputs(base_jd_dir)
    jp_candidates = load_candidates_from_job_profiles(base_jp_dir)
    candidates.extend(jd_candidates)
    candidates.extend(jp_candidates)

    # Level 1.5a: optional BOSS/智联 read-only search via external CLI
    if enable_boss_agent_search:
        try:
            boss_agent_candidates = _search_boss_agent_for_candidates(
                keywords=search_keywords,
                city=search_city,
                jp_dir=base_jp_dir or JOB_PROFILES_DIR,
                platforms=boss_agent_platforms,
            )
            if boss_agent_candidates:
                return boss_agent_candidates
        except Exception:
            pass

    # Level 1.5b: Liepin search for real URLs
    if enable_liepin_search:
        try:
            if search_keywords:
                # Targeted search with specific keywords
                liepin_candidates = _search_with_keywords(
                    keywords=search_keywords,
                    city=search_city,
                    session_dir=session_dir,
                    excluded_companies=excluded_companies,
                )
            else:
                liepin_candidates = _search_liepin_for_candidates(
                    base_jp_dir or JOB_PROFILES_DIR,
                    session_dir=session_dir,
                    excluded_companies=excluded_companies,
                    max_profiles=2,  # Limit when searching all profiles
                )
            if liepin_candidates:
                return liepin_candidates
        except Exception:
            pass

    return candidates


def _search_boss_agent_for_candidates(
    *,
    keywords: list[str] | None,
    city: str,
    jp_dir: Path,
    platforms: tuple[str, ...],
) -> list[Candidate]:
    from tools.infra.discovery.boss_agent_cli import search_jobs

    keyword_sets = [keywords] if keywords else _load_profile_keyword_sets(jp_dir, max_profiles=2)
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for keyword_set in keyword_sets:
        if not keyword_set:
            continue
        jobs = search_jobs(
            [str(keyword) for keyword in keyword_set],
            city=city,
            platforms=platforms,
            limit=5,
        )
        for idx, job in enumerate(jobs):
            url = str(job.get("job_url") or job.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            platform = str(job.get("platform") or "boss_agent")
            position = str(job.get("position") or job.get("title") or "")
            company = str(job.get("company") or job.get("company_name") or "")
            candidates.append(
                Candidate(
                    candidate_id=f"boss-agent-{platform}-{len(candidates)}",
                    direction=_detect_direction(" ".join(keyword_set) + " " + position),
                    company=company,
                    job_url=url,
                    confidence=float(job.get("confidence", 0.72)),
                    source=f"boss_agent:{platform}",
                    merged_sources=(f"boss_agent:{platform}",),
                )
            )
    return candidates


def _load_profile_keyword_sets(jp_dir: Path, max_profiles: int) -> list[list[str]]:
    keyword_sets: list[list[str]] = []
    for path in sorted(jp_dir.glob("*.yaml")):
        if len(keyword_sets) >= max_profiles:
            break
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        lists = doc.get("lists", {})
        keywords = [str(k) for k in lists.get("keywords", []) if str(k).strip()]
        if keywords:
            keyword_sets.append(keywords)
    return keyword_sets


def _search_with_keywords(
    keywords: list[str],
    city: str,
    session_dir: str,
    excluded_companies: tuple[str, ...],
) -> list[Candidate]:
    """Search Liepin with specific keywords and return candidates."""
    from tools.engines.discovery.liepin_search import discover_and_filter

    jobs = discover_and_filter(
        keywords=keywords, city=city,
        session_dir=session_dir, headless=True, max_jobs=5,
    )
    candidates: list[Candidate] = []
    for idx, job in enumerate(jobs):
        url = job.get("job_url", "")
        if not url:
            continue
        direction = _detect_direction(" ".join(keywords) + " " + job.get("position", ""))
        candidates.append(Candidate(
            candidate_id=f"liepin-targeted-{idx}",
            direction=direction,
            company=job.get("company", ""),
            job_url=url,
            confidence=0.8,
            source="liepin_search:targeted",
            merged_sources=("liepin_search:targeted",),
        ))
    return candidates


def _search_liepin_for_candidates(
    jp_dir: Path,
    session_dir: str,
    excluded_companies: tuple[str, ...],
    max_profiles: int = 2,
) -> list[Candidate]:
    """Search Liepin for each job profile and return candidates with real URLs."""
    from tools.engines.discovery.liepin_search import discover_and_filter

    all_candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    searched = 0

    for path in sorted(jp_dir.glob("*.yaml")):
        if searched >= max_profiles:
            break
        searched += 1
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        scalars = doc.get("scalars", {})
        lists = doc.get("lists", {})
        keywords = [str(k) for k in lists.get("keywords", [])]
        city = scalars.get("city", "上海")
        business_domain = scalars.get("business_domain", "")

        if not keywords:
            continue

        jobs = discover_and_filter(
            keywords=keywords,
            city=city,
            excluded_companies=excluded_companies,
            session_dir=session_dir,
            headless=True,
            max_jobs=3,
        )

        for idx, job in enumerate(jobs):
            url = job.get("job_url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            all_candidates.append(Candidate(
                candidate_id=f"liepin-{path.stem}-{idx}",
                direction=_detect_direction(" ".join(keywords) + " " + job.get("position", "")),
                company=job.get("company", "") or business_domain,
                job_url=url,
                confidence=0.75,
                source=f"liepin_search:{path.stem}",
                merged_sources=(f"liepin_search:{path.stem}",),
            ))

    return all_candidates


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
