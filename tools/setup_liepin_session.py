#!/usr/bin/env python3
"""Initialize Liepin login session for automated submission.

Usage:
    python3 tools/setup_liepin_session.py [--session-dir <dir>]

Opens a Chromium window to liepin.com. Log in once. Close the window.
Cookies are saved to session_dir. Future automated submissions reuse them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Liepin login session")
    _ = parser.add_argument(
        "--session-dir",
        default="outputs/sessions",
        help="Directory to store browser session (default: outputs/sessions)",
    )
    args = parser.parse_args()

    session_root = Path(args.session_dir) / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)

    print(f"Session: {session_root}")
    print("Opening Chromium to liepin.com ...")
    print("→ Log in, then close the window.")
    print()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright not installed. Run: pip install playwright")
        return 3

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=False,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.liepin.com/", wait_until="domcontentloaded")
            print("[READY] Log in, then close the window.")
            page.wait_for_event("close", timeout=0)
            ctx.close()
    except Exception as exc:
        if "close" not in str(exc).lower():
            print(f"[WARN] {exc}")

    print()
    print("Session saved.")
    print(f"  export PPF_SESSION_DIR={Path(args.session_dir).resolve()}")
    print("  export PPF_SUBMIT_ENABLED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
