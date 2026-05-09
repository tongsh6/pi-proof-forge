from __future__ import annotations

import json
import os
import subprocess
import tempfile


def run_liepin_applescript_search(
    search_url: str,
    extract_js: str,
    *,
    max_jobs: int,
    timeout_ms: int,
) -> list[dict]:
    """Open a Liepin search URL in real Chrome and extract job listings."""

    js_file = os.path.join(tempfile.gettempdir(), "ppf_liepin_search.js")
    with open(js_file, "w", encoding="utf-8") as handle:
        handle.write(extract_js)

    max_wait = max(3, min(timeout_ms // 1000, 30))
    applescript = (
        'tell application "Google Chrome"\n'
        "    activate\n"
        "    set searchWindow to make new window\n"
        "    set searchTab to tab 1 of searchWindow\n"
        f'    set URL of searchTab to "{search_url}"\n'
        f"    set maxWait to {max_wait}\n"
        "    repeat with i from 1 to maxWait\n"
        "        delay 1\n"
        "        try\n"
        "            set linkCount to execute searchTab javascript "
        "\"document.querySelectorAll('a[href*=\\\"/job/\\\"]').length\"\n"
        "            if linkCount > 0 then exit repeat\n"
        "        end try\n"
        "    end repeat\n"
        "    delay 1\n"
        '    set rawJson to "{}"\n'
        "    try\n"
        f'        set jsCode to read "{js_file}"\n'
        "        set rawJson to execute searchTab javascript jsCode\n"
        "    on error errMsg\n"
        '        set rawJson to "{\\"error\\": \\"" & errMsg & "\\"}"\n'
        "    end try\n"
        "    close searchWindow\n"
        "    return rawJson\n"
        "end tell"
    )

    proc_timeout = min(timeout_ms / 1000 + 15, 60)

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=proc_timeout,
        )
    except subprocess.TimeoutExpired:
        return []
    except FileNotFoundError:
        return []

    if result.returncode != 0:
        return []

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict) and data.get("captcha"):
        return []

    if isinstance(data, dict) and data.get("error"):
        return []

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return jobs[:max_jobs] if isinstance(jobs, list) else []
