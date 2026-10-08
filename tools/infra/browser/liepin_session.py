"""由同步 sidecar 持有的猎聘登录浏览器；不依赖开发工具连接。"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


LOGIN_PROMPTS = (
    "[data-selector='inline-login']:visible, .inline-login-container:visible, "
    ".pc-login-pop-container:visible, .ant-modal-root:has-text('登录'):visible, "
    "a:has-text('登录'):visible, button:has-text('登录/注册'):visible, "
    "#header-quick-menu-login:visible"
)
AUTHENTICATED_USER = ".nav-user-item:visible, [data-selector='c-logout']:visible"


def _reject_blank_redirect(page) -> None:
    if page.url == "about:blank":
        raise RuntimeError("LOGIN_PAGE_REDIRECTED_TO_BLANK: 网站将登录页跳转为空白，当前浏览器连接方式不兼容")


def observe_login_page(page) -> dict:
    url = urlparse(str(page.url))
    host = (url.hostname or "").lower()
    if url.scheme != "https" or not (host == "liepin.com" or host.endswith(".liepin.com")):
        return {"login_signals": {}}
    if host in {"passport.liepin.com", "safe.liepin.com"} or "login" in url.path.lower():
        return {"login_signals": {"login_required": True}}
    if page.locator(LOGIN_PROMPTS).count() > 0:
        return {"login_signals": {"login_required": True}}
    return {"login_signals": {
        "authenticated_user_visible": page.locator(AUTHENTICATED_USER).count() > 0,
        "login_modal_absent": True,
    }}


class LiepinSessionBrowser:
    """stdio RPC 串行运行于同一线程，复用该线程创建的 Playwright 上下文。"""

    def __init__(self):
        self._playwright = None
        self._context = None
        self._profile = None

    def _start_playwright(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("PLAYWRIGHT_UNAVAILABLE: 当前 App Python 缺少 Playwright，请使用已有项目运行环境") from exc
        return sync_playwright().start()

    def _page(self, profile: Path, *, headless: bool):
        profile = profile.resolve()
        if self._context is not None:
            try:
                if self._profile == profile and self._context.pages:
                    page = self._context.pages[0]
                    # 同步 sidecar 等待 stdin 时不会泵事件，先经有界 IPC 刷新导航/关闭状态。
                    page.locator(":root").wait_for(state="attached", timeout=3_000)
                    if not page.is_closed():
                        return page
            except Exception:
                pass
            self.close()
        profile.mkdir(parents=True, exist_ok=True)
        self._playwright = self._start_playwright()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile), channel="chrome", headless=headless,
            timeout=10_000,
        )
        self._profile = profile
        return self._context.pages[0] if self._context.pages else self._context.new_page()

    def start(self, profile: Path, login_url: str) -> bool:
        try:
            page = self._page(profile, headless=False)
            response = page.goto(login_url, wait_until="domcontentloaded", timeout=15_000)
            if response is not None and isinstance(response.status, int) and response.status >= 400:
                raise RuntimeError(f"LOGIN_PAGE_UNAVAILABLE: HTTP {response.status}")
            # 当前网站脚本在加载后轮询；瞬间可见不代表页面能保持可用。
            page.wait_for_timeout(4_000)
            _reject_blank_redirect(page)
            if observe_login_page(page)["login_signals"].get("authenticated_user_visible"):
                return True
            phone = page.locator("input[placeholder='手机号']:visible")
            if phone.count() == 0:
                # 来源于当前官网首页的真实登录入口；不再使用失效的 passport URL。
                entry = page.locator("#header-quick-menu-login").first
                entry.wait_for(state="visible", timeout=10_000)
                entry.click(timeout=3_000)
            phone.first.wait_for(state="visible", timeout=10_000)
            page.bring_to_front()
            return False
        except Exception as exc:
            self.close()
            raise RuntimeError(f"LOGIN_BROWSER_START_FAILED: {exc}") from exc

    def check(self, profile: Path) -> dict:
        if self._context is None and (not profile.is_dir() or not any(profile.iterdir())):
            return {"login_signals": {}}
        previous_context = self._context
        had_context = previous_context is not None
        opened_for_check = not had_context
        try:
            page = self._page(profile, headless=not had_context)
            opened_for_check = not had_context or self._context is not previous_context
            if opened_for_check:
                page.goto("https://www.liepin.com/", wait_until="domcontentloaded", timeout=15_000)
                page.wait_for_timeout(4_000)
            _reject_blank_redirect(page)
            observed = observe_login_page(page)
            if observed["login_signals"].get("authenticated_user_visible"):
                self.close()
            return observed
        except Exception as exc:
            self.close()
            raise RuntimeError(f"LOGIN_BROWSER_CHECK_FAILED: {exc}") from exc
        finally:
            # 独立检查关闭后释放 profile；人工登录窗口则继续保留。
            if opened_for_check:
                self.close()

    def close(self) -> None:
        context, playwright = self._context, self._playwright
        self._context = self._playwright = self._profile = None
        try:
            if context is not None:
                context.close()
        except Exception as exc:
            if type(exc).__name__ != "TargetClosedError":
                raise
        finally:
            if playwright is not None:
                playwright.stop()


session_browser = LiepinSessionBrowser()
