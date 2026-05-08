#!/usr/bin/env python3
"""PoC: Use AppleScript to drive real Chrome for Liepin job search.

This bypasses Playwright's navigator.webdriver detection by controlling
the actual Chrome browser on macOS via AppleScript.

Usage:
    python3 tools/poc_liepin_applescript_search.py
    python3 tools/poc_liepin_applescript_search.py --keyword "Java 后端 上海"
    python3 tools/poc_liepin_applescript_search.py --keyword "Go 架构师 上海" --max-jobs 10
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from urllib.parse import quote


def build_search_url(keyword: str) -> str:
    return f"https://www.liepin.com/zhaopin/?key={quote(keyword)}"


def run_applescript(script: str) -> tuple[int, str, str]:
    """Execute AppleScript and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _build_extract_js(max_jobs: int) -> str:
    """Build JavaScript extractor for Liepin search results page.

    Based on diagnosed DOM structure (2026-05-09):
      DIV.job-list-box > DIV.job-card-pc-container > DIV.job-detail-box
        A[href*="/job/"]          → position, city, salary, exp, edu (all in text)
        DIV[data-nick="job-detail-company-info"]  → company name, industry, size
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
        "  /* Parse link text: position,city,tags,salary,exp,edu */"
        "  var linkText=(link.textContent||'').trim();"
        "  var parsed=linkText.match(/^(.+?)\\u3010(.+?)\\u3011(.*)$/);"
        "  var position=parsed?parsed[1].trim():linkText.slice(0,60);"
        "  var city=parsed?parsed[2].trim():'';"
        "  var meta=parsed?parsed[3].trim():'';"
        "  /* Company: sibling div with data-nick=job-detail-company-info */"
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
        "  /* Salary: parse from meta string */"
        "  var salary='';"
        "  var salaryM=meta.match(/(\\d{1,3}-\\d{1,3}k[^\\s]*|\\u85aa\\u8d44\\u9762\\u8bae)/);"
        "  if(salaryM)salary=salaryM[1];"
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
        "  /* Fallback: if .job-detail-box not found, grab all /job/ links */"
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


def capture_job_listings(search_url: str, max_jobs: int = 5) -> list[dict]:
    """Open Liepin search in real Chrome and extract job listings via AppleScript JS."""

    extract_js = _build_extract_js(max_jobs)

    # Write JS to temp file so AppleScript can read it — avoids all escaping issues
    import tempfile, os as _os
    js_file = _os.path.join(tempfile.gettempdir(), 'liepin_search_extract.js')
    with open(js_file, 'w', encoding='utf-8') as f:
        f.write(extract_js)

    # AppleScript: open new Chrome window, navigate, wait, execute JS from file, close.
    applescript = (
        'tell application "Google Chrome"\n'
        '    activate\n'
        '    set searchWindow to make new window\n'
        '    set searchTab to tab 1 of searchWindow\n'
        f'    set URL of searchTab to "{search_url}"\n'
        '    set maxWait to 15\n'
        '    repeat with i from 1 to maxWait\n'
        '        delay 1\n'
        '        try\n'
        '            set linkCount to execute searchTab javascript "document.querySelectorAll(\'a[href*=\\\"/job/\\\"]\').length"\n'
        '            if linkCount > 0 then exit repeat\n'
        '        end try\n'
        '    end repeat\n'
        '    delay 1\n'
        '    set rawJson to "{}"\n'
        '    try\n'
        f'        set jsCode to read "{js_file}"\n'
        '        set rawJson to execute searchTab javascript jsCode\n'
        '    on error errMsg\n'
        '        set rawJson to "{\\"error\\": \\"" & errMsg & "\\"}"\n'
        '    end try\n'
        '    close searchWindow\n'
        '    return rawJson\n'
        'end tell'
    )

    print(f"  Opening: {search_url}")
    rc, stdout, stderr = run_applescript(applescript)

    if rc != 0:
        print(f"  [ERROR] AppleScript failed (rc={rc}): {stderr}")
        return []

    if not stdout:
        print("  [WARN] AppleScript returned empty output")
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"  [WARN] Failed to parse JSON. Raw output (first 500 chars):")
        print(f"  {stdout[:500]}")
        return []

    if isinstance(data, dict) and data.get("captcha"):
        print("  [CAPTCHA] Liepin triggered captcha on search page")
        return []

    if isinstance(data, dict) and data.get("error"):
        print(f"  [ERROR] JS execution failed: {data['error'][:200]}")
        return []

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return jobs


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="PoC: Search Liepin via AppleScript-controlled real Chrome"
    )
    _ = parser.add_argument(
        "--keyword", default="Java 后端 上海",
        help="Search keyword (default: 'Java 后端 上海')"
    )
    _ = parser.add_argument(
        "--max-jobs", type=int, default=5,
        help="Max jobs to extract (default: 5)"
    )
    args = parser.parse_args()

    search_url = build_search_url(args.keyword)
    print("Searching Liepin with AppleScript-driven Chrome...")
    print(f"  Keyword : {args.keyword}")
    print(f"  Max jobs: {args.max_jobs}")
    print()

    start = time.time()
    jobs = capture_job_listings(search_url, max_jobs=args.max_jobs)
    elapsed = time.time() - start

    print()
    if not jobs:
        print("No jobs found. Possible reasons:")
        print("  1. Chrome needs Automation permission (System Settings > Privacy > Automation)")
        print("  2. Liepin DOM has changed — selectors need updating")
        print("  3. Captcha triggered on search page")
        print("  4. Network issue or Liepin blocked the request")
        return 1

    print(f"Found {len(jobs)} jobs in {elapsed:.1f}s:")
    print()
    for idx, job in enumerate(jobs, 1):
        pos = job.get('position', 'N/A')
        comp = job.get('company', 'N/A')
        city = job.get('city', '')
        salary = job.get('salary', '')
        industry = job.get('industry', '')
        comp_size = job.get('companySize', '')
        extras = ' | '.join(filter(None, [city, salary, industry, comp_size]))
        print(f"  {idx}. {pos}")
        print(f"     {comp}  {extras}")
        print(f"     {job.get('job_url', '')}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
