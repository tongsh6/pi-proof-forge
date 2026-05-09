"""Liepin job search via AppleScript-driven real Chrome.

Uses AppleScript to control the user's real Chrome browser on macOS.
This bypasses Playwright's navigator.webdriver detection and the IP captcha
that blocks automated search — because from Liepin's perspective, this is
just a normal user browsing in their real Chrome.

Prior implementation used Playwright which triggered captchaPage_ip_PC.
"""

from __future__ import annotations

from urllib.parse import quote


def build_liepin_search_url(keywords: list[str], city: str = "上海") -> str:
    """Build a Liepin search URL from job profile keywords."""
    key = " ".join(keywords[:5])
    encoded = quote(f"{key} {city}")
    return f"https://www.liepin.com/zhaopin/?key={encoded}"


def _build_extract_js(max_jobs: int) -> str:
    """Build JavaScript extractor for Liepin search results page.

    DOM structure (verified 2026-05-09):
      DIV.job-list-box > DIV.job-card-pc-container > DIV.job-detail-box
        A[href*="/job/"]
          ellipsis-1[title]      → position name
          ellipsis-1 (no title)  → city/district
          SPAN                    → tags, salary, experience, education
        DIV[data-nick="job-detail-company-info"]
          SPAN.ellipsis-1        → company name
          DIV.ellipsis-1
            SPAN                 → industry
            SPAN                 → financing stage
            SPAN                 → company size
    """
    return (
        "(function(){"
        "var r=[],s={};"
        "var cards=document.querySelectorAll('.job-detail-box');"
        "for(var i=0;i<cards.length;i++){"
        "  var card=cards[i];"
        "  var link=card.querySelector('a[href*=\"/job/\"]');"
        "  if(!link)continue;"
        "  var href=link.href.split('?')[0];"
        "  if(!href||href.indexOf('liepin.com/job/')===-1)continue;"
        "  if(s[href])continue;s[href]=true;"
        "  /* Parse link text: position(chinese-city)tags salary exp edu */"
        "  var linkText=(link.textContent||'').trim();"
        "  var parsed=linkText.match(/^(.+?)\\u3010(.+?)\\u3011(.*)$/);"
        "  var position=parsed?parsed[1].trim():linkText.slice(0,60);"
        "  var city=parsed?parsed[2].trim():'';"
        "  var meta=parsed?parsed[3].trim():'';"
        "  /* Salary from meta: '25-55k 14xin' or '薪资面议' */"
        "  var salary='';"
        "  var sm=meta.match(/(\\d{1,3}-\\d{1,3}k[^\\u4e00-\\u9fa5]*|\\u85aa\\u8d44\\u9762\\u8bae)/);"
        "  if(sm)salary=sm[1];"
        "  /* Company from sibling div */"
        "  var company='';var industry='';var compSize='';"
        "  var compDiv=card.parentElement.querySelector('[data-nick=\"job-detail-company-info\"]');"
        "  if(compDiv){"
        "    var cn=compDiv.querySelector('span.ellipsis-1');"
        "    if(cn)company=(cn.textContent||'').trim();"
        "    var metaDiv=compDiv.querySelector('div.ellipsis-1');"
        "    if(metaDiv){"
        "      var sps=metaDiv.querySelectorAll('span');"
        "      if(sps.length>=1)industry=(sps[0].textContent||'').trim();"
        "      if(sps.length>=2)compSize=(sps[sps.length-1].textContent||'').trim();"
        "    }"
        "  }"
        "  r.push({"
        "    job_url:href,"
        "    position:position.slice(0,120),"
        "    company:company.slice(0,60),"
        "    city:city.slice(0,20),"
        "    salary:salary.slice(0,30),"
        "    industry:industry.slice(0,30),"
        "    companySize:compSize.slice(0,30),"
        "    meta:meta.slice(0,200)"
        "  });"
        f"  if(r.length>={max_jobs})break;"
        "}"
        "  /* Fallback: grab all /job/ links */"
        "if(r.length===0){"
        "  var as=document.querySelectorAll('a[href*=\"/job/\"]');"
        "  for(var j=0;j<as.length;j++){"
        "    var a=as[j];var h=a.href.split('?')[0];"
        "    if(!h||h.indexOf('liepin.com/job/')===-1)continue;"
        "    if(s[h])continue;s[h]=true;"
        "    r.push({job_url:h,position:(a.textContent||'').trim().slice(0,120),"
        "      company:'',city:'',salary:'',industry:'',companySize:'',meta:''});"
        f"    if(r.length>={max_jobs})break;"
        "  }"
        "}"
        "return JSON.stringify({captcha:window.location.href.indexOf('captcha')>-1,total:r.length,jobs:r});"
        "})()"
    )


def _run_applescript_search(search_url: str, max_jobs: int, timeout_ms: int) -> list[dict]:
    """Open Liepin search URL in real Chrome via AppleScript and extract job listings."""

    from tools.infra.browser.liepin_applescript import run_liepin_applescript_search

    return run_liepin_applescript_search(
        search_url,
        _build_extract_js(max_jobs),
        max_jobs=max_jobs,
        timeout_ms=timeout_ms,
    )


def discover_liepin_jobs(
    keywords: list[str],
    city: str = "上海",
    *,
    session_dir: str = "outputs/sessions",  # kept for API compat, unused with AppleScript
    headless: bool = True,                   # kept for API compat, unused with AppleScript
    max_jobs: int = 5,
    timeout_ms: int = 20000,
) -> list[dict]:
    """Search Liepin and extract job listings with URLs.

    Uses AppleScript to control the real Chrome browser on macOS.
    Returns list of dicts with: job_url, position, company, city, salary,
    industry, companySize, meta.
    """
    if not keywords:
        return []

    search_url = build_liepin_search_url(keywords, city)
    return _run_applescript_search(search_url, max_jobs=max_jobs, timeout_ms=timeout_ms)


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
        blocked = any(ex and ex in company for ex in excluded_lower)
        if not blocked:
            filtered.append(job)

    return filtered
