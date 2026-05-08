#!/usr/bin/env python3
"""Capture the current Chrome tab URL as a job lead.

Usage:
    python3 tools/capture_job_url.py

Run while viewing a Liepin job page in Chrome. The URL and page title
are saved to job_leads/ for the Agent Loop to discover automatically.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone


def _get_chrome_tab() -> tuple[str, str]:
    """Get URL and title of Chrome's active tab via AppleScript."""
    script = """
    tell application "Google Chrome"
        set u to URL of active tab of window 1
        set t to title of active tab of window 1
        return u & "|||" & t
    end tell
    """
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        print(f"[ERROR] Cannot access Chrome: {result.stderr.strip()}")
        sys.exit(1)
    parts = result.stdout.strip().split("|||", 1)
    return parts[0] if len(parts) > 0 else "", parts[1] if len(parts) > 1 else ""


def _is_job_url(url: str) -> bool:
    return "liepin.com/job/" in url.lower()


def main() -> int:
    url, title = _get_chrome_tab()

    if not url:
        print("[ERROR] No active Chrome tab found.")
        return 1

    if not _is_job_url(url):
        print(f"Not a Liepin job page. Current URL: {url}")
        print("Open a job detail page on liepin.com and re-run.")
        return 0

    # Extract clean URL (strip query params)
    clean_url = url.split("?")[0]

    # Extract company and position from title
    title_parts = title.split(" - ") if " - " in title else title.split("_")
    position = title_parts[0].strip() if title_parts else title
    company = title_parts[1].strip() if len(title_parts) > 1 else ""

    # Write job lead
    leads_dir = Path("job_leads")
    leads_dir.mkdir(exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    lead_path = leads_dir / f"jl-captured-{ts}.yaml"

    content = f"""# Captured from Chrome
generated_at: "{datetime.now(timezone.utc).isoformat()}"
items:
  - job_url: "{clean_url}"
    position: "{position}"
    company_name: "{company}"
    direction: backend
    confidence: 0.85
"""
    lead_path.write_text(content, encoding="utf-8")
    print(f"✅ Saved: {lead_path}")
    print(f"   {company} — {position}")
    print(f"   {clean_url}")
    print()
    print("Agent Loop will discover this automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
