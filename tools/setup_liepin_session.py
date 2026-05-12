from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a persistent Liepin session.")
    parser.add_argument(
        "--session-dir",
        default="outputs/submissions/liepin/session",
        help="Base session directory. The Liepin profile is stored under <session-dir>/liepin.",
    )
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Playwright browser channel. Use an empty value for bundled Chromium.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=45_000)
    args = parser.parse_args(argv)

    session_root = Path(args.session_dir) / "liepin"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sync_playwright = _missing_playwright_factory

    ok = _setup_playwright_login_session(
        session_root=session_root,
        browser_channel=args.browser_channel,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        sync_playwright_factory=sync_playwright,
    )
    return 0 if ok else 1


def _missing_playwright_factory() -> object:
    raise ImportError("Playwright is not installed. Run: pip install playwright")


def _setup_playwright_login_session(
    *,
    session_root: Path,
    browser_channel: str,
    headless: bool,
    timeout_ms: int,
    sync_playwright_factory: Callable[[], object],
) -> bool:
    session_root.mkdir(parents=True, exist_ok=True)

    print(f"[*] 正在启动 Chrome，加载 Session: {session_root}")
    print("[!] 请在打开的窗口中完成登录和验证码校验。")
    print("[!] 完成后，请直接关闭浏览器窗口，脚本会自动保存状态。")

    launch_options: dict[str, object] = {
        "user_data_dir": str(session_root),
        "headless": headless,
    }
    if browser_channel:
        launch_options["channel"] = browser_channel

    try:
        with sync_playwright_factory() as p:
            context = p.chromium.launch_persistent_context(**launch_options)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(
                    "https://www.liepin.com/",
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                _wait_for_login_confirmation()
                return _is_session_ready(page)
            finally:
                context.close()
    except Exception as exc:
        print(f"[!] 启动失败: {exc}")
        print("[!] 请确保本机已安装 Chrome 且可通过 playwright 调用。")
        return False


def _is_session_ready(page: object) -> bool:
    current_url = str(getattr(page, "url", "")).lower()
    if "passport" in current_url or "login" in current_url:
        return False

    login_prompt = page.locator(
        "[data-selector='inline-login']:visible, "
        ".inline-login-container:visible, "
        "a:has-text('登录'):visible, "
        "button:has-text('登录/注册'):visible"
    )
    return login_prompt.count() == 0


def _wait_for_login_confirmation() -> None:
    if sys.stdin.isatty():
        input("完成登录后按 Enter 继续...")


if __name__ == "__main__":
    raise SystemExit(main())
