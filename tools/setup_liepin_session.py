#!/usr/bin/env python3
"""Initialize a persistent Playwright/Chrome Liepin login profile."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

LIEPIN_URL = "https://www.liepin.com/"
DEFAULT_SESSION_DIR = "outputs/sessions"
DEFAULT_BROWSER_CHANNEL = "chrome"


def _wait_for_login_confirmation() -> None:
    if not sys.stdin.isatty():
        return
    input("Log in to Liepin in the Playwright browser, then press Enter to verify ... ")


def _launch_options(
    session_root: Path,
    browser_channel: str,
    headless: bool,
) -> dict[str, object]:
    options: dict[str, object] = {
        "user_data_dir": str(session_root),
        "headless": headless,
    }
    if browser_channel:
        options["channel"] = browser_channel
    return options


def _setup_playwright_login_session(
    *,
    session_root: Path,
    browser_channel: str,
    headless: bool,
    timeout_ms: int,
    sync_playwright_factory: Callable[[], Any] | None = None,
) -> bool:
    try:
        if sync_playwright_factory is None:
            from playwright.sync_api import sync_playwright

            sync_playwright_factory = sync_playwright
    except ImportError:
        print("[ERROR] playwright is not installed.")
        print("        Run: pip install playwright && python -m playwright install chromium")
        return False

    session_root.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright_factory() as p:
            context = p.chromium.launch_persistent_context(
                **_launch_options(session_root, browser_channel, headless)
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(LIEPIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                print("A Playwright browser has opened with an isolated persistent profile.")
                print("Manually enter your Liepin credentials in that browser window.")
                _wait_for_login_confirmation()
                page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
                if not _is_session_ready(page):
                    print("[ERROR] Liepin still appears to be logged out in the Playwright profile.")
                    return False
                return True
            finally:
                context.close()
    except Exception as exc:
        print(f"[ERROR] failed to initialize Playwright login session: {exc}")
        return False


def _is_session_ready(page: object) -> bool:
    current_url = str(getattr(page, "url", "")).lower()
    if "passport" in current_url or "login" in current_url:
        return False

    login_selectors = [
        "a:has-text('登录')",
        "button:has-text('登录')",
        "text=登录/注册",
    ]
    for selector in login_selectors:
        try:
            if page.locator(selector).count() > 0:
                return False
        except Exception:
            continue
    return True


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a persistent Playwright/Chrome Liepin profile for one-time manual login"
    )
    _ = parser.add_argument(
        "--session-dir",
        default=DEFAULT_SESSION_DIR,
        help=f"Directory to store the Playwright session profile (default: {DEFAULT_SESSION_DIR})",
    )
    _ = parser.add_argument(
        "--browser-channel",
        default=DEFAULT_BROWSER_CHANNEL,
        help="Playwright browser channel to use; pass an empty value for bundled Chromium",
    )
    _ = parser.add_argument(
        "--timeout-ms",
        type=int,
        default=300_000,
        help="Navigation timeout while waiting for manual login verification",
    )
    _ = parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run browser headless; login setup normally requires headed mode",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    session_root = Path(str(args.session_dir)) / "liepin"
    browser_channel = str(args.browser_channel)
    timeout_ms = int(args.timeout_ms)
    headless = bool(args.headless)

    ok = _setup_playwright_login_session(
        session_root=session_root,
        browser_channel=browser_channel,
        headless=headless,
        timeout_ms=timeout_ms,
    )
    if not ok:
        return 1

    print("Session ready.")
    print(f"Use with: --session-dir {Path(str(args.session_dir)).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
