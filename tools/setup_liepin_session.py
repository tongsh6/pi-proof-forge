#!/usr/bin/env python3
"""Initialize Liepin login session — uses your REAL Chrome profile.

Usage:
    python3 tools/setup_liepin_session.py [--session-dir <dir>]

Flow:
  1. Connect Playwright to your real Chrome via CDP (all saved passwords work)
  2. You log in to Liepin ONCE
  3. Close Chrome — cookies are extracted and saved to session_dir
  4. Future automated submissions load these cookies via Playwright Chromium

After setup, set PPF_SUBMIT_ENABLED=1 to enable real submission.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CDP_PORT = 9222
LIEPIN_DOMAINS = ["liepin.com", "www.liepin.com", ".liepin.com"]


def _find_chrome() -> Path | None:
    for p in [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]:
        if p.exists():
            return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize Liepin login session with your real Chrome"
    )
    _ = parser.add_argument(
        "--session-dir",
        default="outputs/sessions",
        help="Directory to store session cookies (default: outputs/sessions)",
    )
    _ = parser.add_argument(
        "--port",
        type=int,
        default=CDP_PORT,
        help=f"CDP debugging port (default: {CDP_PORT})",
    )
    args = parser.parse_args()

    chrome = _find_chrome()
    if chrome is None:
        print("[ERROR] Google Chrome not found at /Applications/Google Chrome.app")
        return 1

    session_root = Path(args.session_dir) / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)
    cookie_file = session_root / "cookies.json"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright not installed.")
        print("  Run: pip install playwright")
        return 3

    print("Opening YOUR Chrome (with saved passwords) to liepin.com ...")
    print("→ Log in, then close Chrome. Cookies will be saved automatically.")
    print()

    # ── Step 1: Launch real Chrome with CDP ──────────────────────
    chrome_proc = subprocess.Popen(
        [
            str(chrome),
            f"--remote-debugging-port={args.port}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.liepin.com/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)

    cookies: list[dict] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
            contexts = browser.contexts
            if not contexts:
                print("[ERROR] No browser context — is Chrome already running?")
                print("        Close all Chrome windows and retry.")
                chrome_proc.terminate()
                return 5

            context = contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            if not page.url.startswith("http"):
                page.goto("https://www.liepin.com/")

            print("[READY] Log in to Liepin now, then close Chrome.")
            print("        Waiting for Chrome to close ...")

            # Wait for disconnect (user closes Chrome)
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass

            # Extract cookies before browser fully disconnects
            try:
                all_cookies = context.cookies()
                cookies = [c for c in all_cookies if any(d in c.get("domain", "") for d in LIEPIN_DOMAINS)]
            except Exception:
                pass

            try:
                browser.close()
            except Exception:
                pass
    except Exception as exc:
        print(f"[WARN] CDP session ended: {exc}")
    finally:
        try:
            chrome_proc.terminate()
        except Exception:
            pass
        try:
            chrome_proc.wait(timeout=5)
        except Exception:
            pass

    if not cookies:
        print("[ERROR] No Liepin cookies captured. Did you log in?")
        return 7

    # ── Step 2: Save cookies to session_dir ──────────────────────
    cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(cookies)} Liepin cookies saved to {cookie_file}")

    # ── Step 3: Inject cookies into automation profile ────────────
    print("Injecting cookies into automation profile ...")
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=True,
            )
            ctx.add_cookies(cookies)
            # Verify
            page = ctx.new_page()
            page.goto("https://www.liepin.com/", wait_until="domcontentloaded", timeout=15000)
            if "passport" in page.url.lower() or "login" in page.url.lower():
                print("⚠️  Cookie verification: login page detected — may need re-login")
            else:
                print("✅ Cookie verification: session looks active")
            ctx.close()
    except Exception as exc:
        print(f"[WARN] Cookie injection check failed: {exc}")
        print("       Cookies are saved — verify manually with check-mode.")

    print()
    print("Session ready. To use it for automated submission:")
    print(f"  export PPF_SESSION_DIR={Path(args.session_dir).resolve()}")
    print("  export PPF_SUBMIT_ENABLED=1")
    print()
    print("Verify with check-mode (no actual submission):")
    print("  PPF_SUBMIT_ENABLED=0 PPF_HEADLESS=1 .venv/bin/python3 -c \"")
    print("    import os; os.environ['PPF_SESSION_DIR'] = 'outputs/sessions'")
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
