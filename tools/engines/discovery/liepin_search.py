"""Liepin job search: construct search URLs and extract job listing links.

This is Level 2.5 of the discovery chain — it takes candidates without URLs
from jd_inputs/job_profiles and finds real job URLs on Liepin.
"""

from __future__ import annotations

from urllib.parse import quote


def build_liepin_search_url(
    keywords: list[str],
    city: str = "上海",
) -> str:
    """Build a Liepin search URL from job profile keywords."""
    key = " ".join(keywords[:5])
    encoded = quote(f"{key} {city}")
    return f"https://www.liepin.com/zhaopin/?key={encoded}&city={city}"


def extract_job_links_from_page(page: object) -> list[dict]:
    """Extract job listing links from a Liepin search results page.

    Returns list of dicts with: job_url, company, position, salary.
    """
    results: list[dict] = []

    # Liepin search result selectors
    link_selectors = [
        "a[data-nick]",
        ".job-list-item a.job-title",
        ".job-card a.job-title",
    ]

    jobs_seen: set[str] = set()
    for selector in link_selectors:
        try:
            elements = page.locator(selector)
            count = elements.count()
            for i in range(min(count, 10)):
                try:
                    el = elements.nth(i)
                    href = el.get_attribute("href") or ""
                    text = el.inner_text().strip()
                    if href and "liepin.com/job" in href and href not in jobs_seen:
                        jobs_seen.add(href)
                        results.append({
                            "job_url": href.split("?")[0],
                            "position": text[:60] if text else "",
                            "company": "",
                            "salary": "",
                        })
                except Exception:
                    continue
        except Exception:
            continue

    return results


def discover_liepin_jobs(
    keywords: list[str],
    city: str = "上海",
    *,
    sync_playwright: object = None,
    headless: bool = True,
    session_dir: str = "outputs/sessions",
    timeout_ms: int = 15000,
) -> list[dict]:
    """Full Liepin job discovery: search → extract links.

    Requires Playwright and a valid Liepin login session.
    Returns list of dicts with job_url, company, position.
    """
    try:
        from playwright.sync_api import sync_playwright as sp
    except ImportError:
        return []

    search_url = build_liepin_search_url(keywords, city)
    results: list[dict] = []

    try:
        with sp() as p:
            session_root = __import__("pathlib").Path(session_dir) / "liepin"
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=headless,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Let results load
            page.wait_for_timeout(2000)

            results = extract_job_links_from_page(page)
            ctx.close()
    except Exception:
        pass

    return results
