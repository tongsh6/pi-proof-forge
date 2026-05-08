"""Liepin job search: automated discovery of real job URLs.

Given a job profile (keywords + city), constructs a Liepin search URL,
opens it with Playwright, and extracts job listing links with metadata.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


def build_liepin_search_url(keywords: list[str], city: str = "上海") -> str:
    """Build a Liepin search URL from job profile keywords."""
    key = " ".join(keywords[:5])
    encoded = quote(f"{key} {city}")
    return f"https://www.liepin.com/zhaopin/?key={encoded}"


def discover_liepin_jobs(
    keywords: list[str],
    city: str = "上海",
    *,
    session_dir: str = "outputs/sessions",
    headless: bool = True,
    max_jobs: int = 5,
    timeout_ms: int = 20000,
) -> list[dict]:
    """Search Liepin and extract job listings with URLs.

    Returns list of dicts with: job_url, position, company, city, salary.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    search_url = build_liepin_search_url(keywords, city)
    results: list[dict] = []

    try:
        with sync_playwright() as p:
            session_root = Path(session_dir) / "liepin"
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=headless,
            )
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(3000)

                current_url = page.url.lower()
                if "captcha" in current_url or "safe.liepin" in current_url:
                    return []  # Anti-bot captcha — cannot automate

                results = _extract_job_listings(page, max_jobs)
            finally:
                ctx.close()
    except ImportError:
        pass  # Playwright not available
    except Exception:
        pass  # Best-effort search: network errors, timeouts are non-fatal

    return results


def _extract_job_listings(page: object, max_jobs: int) -> list[dict]:
    """Extract job listings from a Liepin search results page."""
    results: list[dict] = []
    job_links = page.locator("a[href*='/job/']")
    count = job_links.count()

    seen_urls: set[str] = set()
    for i in range(min(count, max_jobs * 3)):
        try:
            el = job_links.nth(i)
            href = (el.get_attribute("href") or "").split("?")[0]
            if not href or "liepin.com/job/" not in href:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            text = el.inner_text().strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            position = lines[0] if lines else ""
            company = ""
            salary = ""
            job_city = ""

            # Try to get company from data-nick on nearby element
            try:
                parent = el.locator("..")
                nick = parent.locator("[data-nick]")
                if nick.count() > 0:
                    company = nick.first.get_attribute("data-nick") or ""
            except Exception:
                pass

            # Parse text lines for metadata
            for line in lines[1:]:
                if "【" in line:
                    job_city = line.replace("【", "").replace("】", "").strip()
                elif "k" in line.lower() and "·" in line:
                    salary = line.strip()
                elif company == "" and len(line) > 1 and "·" not in line:
                    company = line.strip()

            results.append({
                "job_url": href,
                "position": position[:80],
                "company": company,
                "city": job_city or city,
                "salary": salary,
            })

            if len(results) >= max_jobs:
                break
        except Exception:  # noqa: PERF203
            # Individual element extraction failure — skip this listing
            continue

    return results


def discover_and_filter(
    keywords: list[str],
    city: str = "上海",
    *,
    excluded_companies: tuple[str, ...] = (),
    session_dir: str = "outputs/sessions",
    headless: bool = True,
    max_jobs: int = 5,
) -> list[dict]:
    """Discover jobs and apply company exclusion filters.

    Returns filtered list ready for Candidate creation.
    """
    jobs = discover_liepin_jobs(
        keywords=keywords, city=city,
        session_dir=session_dir, headless=headless, max_jobs=max_jobs,
    )

    if not excluded_companies:
        return jobs

    excluded_lower = set()
    for rule in excluded_companies:
        r = rule.casefold()
        if r.startswith("contains:"):
            excluded_lower.add(r.split(":", 1)[1])
        elif r.startswith("exact:"):
            excluded_lower.add(r.split(":", 1)[1])
        else:
            excluded_lower.add(r)

    filtered: list[dict] = []
    for job in jobs:
        company = job.get("company", "").casefold()
        blocked = False
        for ex in excluded_lower:
            if ex and ex in company:
                blocked = True
                break
        if not blocked:
            filtered.append(job)

    return filtered
