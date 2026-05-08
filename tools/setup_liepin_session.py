#!/usr/bin/env python3
"""Capture Liepin login session from your real Chrome.

Usage:
    python3 tools/setup_liepin_session.py [--session-dir <dir>]

This temporarily restarts your Chrome with remote debugging enabled so
Playwright can extract cookies. Your tabs are saved and restored — you
won't lose anything. Because it's your real Chrome profile, password
autofill (Keychain) works as usual.
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

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_DIR = Path.home() / "Library/Application Support/Google/Chrome"
SESSION_FILE = "Session_Restore"


def _chrome_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-x", "Google Chrome"], capture_output=True, text=True
    )
    return result.returncode == 0


def _save_tabs() -> list[str]:
    """Get currently open tabs via AppleScript."""
    try:
        result = subprocess.run(
            [
                "osascript", "-e",
                'tell application "Google Chrome" to get URL of every tab of every window',
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [u.strip() for u in result.stdout.split(",") if u.strip()]
    except Exception:
        pass
    return []


def _restore_tabs(urls: list[str]) -> None:
    """Reopen tabs via AppleScript."""
    window_open = (
        'tell application "Google Chrome"\n'
        '  make new window\n'
        + "".join(
            f'  tell window 1 to make new tab with properties {{URL:"{url}"}}\n'
            for url in urls[:20]  # limit to 20 to avoid flooding
        )
        + "end tell"
    )
    try:
        subprocess.run(["osascript", "-e", window_open], timeout=10)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture Liepin login session from your real Chrome"
    )
    _ = parser.add_argument(
        "--session-dir",
        default="outputs/sessions",
        help="Directory to store session cookies (default: outputs/sessions)",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright not installed. Run: pip install playwright")
        return 3

    if not Path(CHROME_PATH).exists():
        print("[ERROR] Google Chrome not found.")
        return 1

    session_root = Path(args.session_dir) / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)
    cookie_file = session_root / "cookies.json"

    # ── Save current tabs ────────────────────────────────────
    saved_urls: list[str] = []
    if _chrome_running():
        print("Saving your open tabs ...")
        saved_urls = _save_tabs()
        print(f"  {len(saved_urls)} tabs saved")

        print("Restarting Chrome with remote debugging ...")
        subprocess.run(["pkill", "-x", "Google Chrome"], capture_output=True)
        time.sleep(1)

    # ── Launch Chrome with CDP ──────────────────────────────
    chrome = subprocess.Popen(
        [
            CHROME_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            "https://www.liepin.com/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for CDP to become available
    cdp_url = f"http://127.0.0.1:{CDP_PORT}"
    for _ in range(10):
        time.sleep(0.5)
        try:
            from urllib.request import urlopen
            urlopen(f"{cdp_url}/json/version", timeout=2)
            break
        except Exception:
            pass
    else:
        print("[ERROR] Chrome launched but CDP not responding.")
        chrome.terminate()
        return 4

    # ── Connect via CDP, let user log in ────────────────────
    print()
    print("Your Chrome is open with password autofill.")
    print("Log in to Liepin, then close Chrome (Cmd+Q).")
    print()

    cookies: list[dict] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                print("[ERROR] No browser context.")
                chrome.terminate()
                return 5

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Wait for user to close Chrome
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass

            # Extract Liepin cookies
            try:
                all_cookies = context.cookies()
                cookies = [
                    c for c in all_cookies
                    if any(d in c.get("domain", "") for d in LIEPIN_DOMAINS)
                ]
            except Exception:
                pass

            try:
                browser.close()
            except Exception:
                pass
    except Exception as exc:
        print(f"[WARN] CDP ended: {exc}")
    finally:
        try:
            chrome.terminate()
        except Exception:
            pass
        try:
            chrome.wait(timeout=3)
        except Exception:
            pass

    if not cookies:
        # Restore tabs before exiting
        if saved_urls:
            print("Restoring your tabs ...")
            _restore_tabs(saved_urls)
        print("[ERROR] No Liepin cookies captured. Did you log in?")
        return 7

    # ── Save cookies ────────────────────────────────────────
    cookie_file.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ {len(cookies)} Liepin cookies saved to {cookie_file}")

    # ── Restart Chrome normally & restore tabs ──────────────
    chrome_restart = subprocess.Popen(
        [CHROME_PATH],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if saved_urls:
        time.sleep(1)
        print("Restoring your tabs ...")
        _restore_tabs(saved_urls)

    # ── Inject cookies into automation profile ──────────────
    print("Injecting cookies into automation profile ...")
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=True,
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto("https://www.liepin.com/", wait_until="domcontentloaded", timeout=15000)
            url = page.url.lower()
            if "passport" in url or "login" in url:
                print("  ⚠️  Verification: login page detected — may need re-login")
            else:
                print("  ✅ Verification: session active")
            ctx.close()
    except Exception as exc:
        print(f"  [WARN] Verification skipped: {exc}")

    print()
    print("Done. To enable real submission:")
    print(f"  export PPF_SESSION_DIR={Path(args.session_dir).resolve()}")
    print("  export PPF_SUBMIT_ENABLED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
