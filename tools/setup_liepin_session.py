#!/usr/bin/env python3
"""Initialize Liepin login session for automated submission.

Usage:
    python3 tools/setup_liepin_session.py [--session-dir <dir>]

This opens a Chromium browser to liepin.com. Log in manually, then close
the browser. The session is saved and can be reused by the LiepinChannel.

After setup, set PPF_SUBMIT_ENABLED=1 to enable real submission.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize Liepin login session"
    )
    _ = parser.add_argument(
        "--session-dir",
        default="outputs/sessions",
        help="Directory to store browser session (default: outputs/sessions)",
    )
    args = parser.parse_args()

    session_root = Path(args.session_dir) / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)

    print(f"Session directory: {session_root}")
    print("Opening browser to liepin.com ...")
    print("→ Please log in to your Liepin account in the browser window.")
    print("→ After logging in, close the browser window to save the session.")
    print()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright not installed.")
        print("  Run: pip install playwright && python -m playwright install chromium")
        print("  Or use the project venv: source .venv/bin/activate")
        return 3

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=False,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.liepin.com/", wait_until="domcontentloaded")
            print("[READY] Browser opened. Log in and then close the browser.")
            print("         Waiting for browser to close ...")
            page.wait_for_event("close", timeout=0)
            context.close()
    except Exception as exc:
        # User closed the browser — this is the expected path
        if "close" in str(exc).lower() or "timeout" in str(exc).lower():
            pass
        else:
            print(f"[WARN] Unexpected: {exc}")

    print()
    print("Session saved. To use it for automated submission:")
    print(f"  export PPF_SESSION_DIR={Path(args.session_dir).resolve()}")
    print("  export PPF_SUBMIT_ENABLED=1")
    print()
    print("To verify the session, run a check-mode submission:")
    print("  PPF_SUBMIT_ENABLED=0 PPF_HEADLESS=1 python3 -c \"")
    print("    from tools.channels.liepin import LiepinChannel")
    print("    from tools.channels.base import DeliveryRequest")
    print("    req = DeliveryRequest(run_id='check', candidate_id='c1',")
    print("        channel='liepin', resume_path='outputs/test.pdf',")
    print("        job_url='https://www.liepin.com/job/YOUR_JOB_ID', dry_run=False)")
    print("    result = LiepinChannel().deliver(req)")
    print("    print(result)\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
