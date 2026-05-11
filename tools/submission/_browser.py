"""统一的反反爬浏览器上下文构造 + 人类化操作节奏。

设计原则：
- stealth 注入（覆盖 navigator.webdriver / chrome / plugins / languages / permissions 等）
- 真实 macOS Chrome User-Agent
- 视觉、时区、locale 与本机一致
- 提供 human_pause / human_scroll / human_click_link 工具
- 提供 is_security_blocked() 兜底检测
"""
from __future__ import annotations

import random
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

DEFAULT_SESSION = Path("outputs/submissions/liepin/session/liepin")

# 真实的 macOS Chrome UA（与本机一致；定期更新）
MAC_CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

VIEWPORT = {"width": 1440, "height": 900}


def _make_stealth() -> Stealth:
    return Stealth(
        navigator_languages_override=("zh-CN", "zh", "en-US", "en"),
        navigator_platform_override="MacIntel",
        navigator_user_agent_override=MAC_CHROME_UA,
        navigator_vendor_override="Google Inc.",
        sec_ch_ua_override='"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
        webgl_vendor_override="Google Inc. (Apple)",
        webgl_renderer_override="ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
    )


@contextmanager
def make_context(
    session_dir: Path = DEFAULT_SESSION,
    headless: bool = True,
    channel: str = "chrome",
):
    """构造一个反反爬增强的 persistent context。"""
    session_dir.mkdir(parents=True, exist_ok=True)
    stealth = _make_stealth()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=headless,
            channel=channel,
            viewport=VIEWPORT,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent=MAC_CHROME_UA,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            ignore_default_args=["--enable-automation"],
        )
        # 把 stealth 应用到 context（对所有现有和未来的 page 生效）
        stealth.apply_stealth_sync(ctx)
        try:
            yield ctx
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def human_pause(min_s: float = 1.5, max_s: float = 4.0):
    time.sleep(random.uniform(min_s, max_s))


def human_long_pause(min_s: float = 8.0, max_s: float = 25.0):
    """模拟人在阅读 JD 的停留时间。"""
    time.sleep(random.uniform(min_s, max_s))


def human_scroll(page: "Page", steps: int = 3):
    """模拟人滑动页面查看。"""
    for _ in range(steps):
        delta = random.randint(300, 900)
        page.mouse.wheel(0, delta)
        time.sleep(random.uniform(0.4, 1.2))


def human_mouse_jiggle(page: "Page"):
    """轻微移动鼠标，避免完全静止的指纹。"""
    try:
        x = random.randint(200, 1200)
        y = random.randint(200, 700)
        page.mouse.move(x, y, steps=random.randint(8, 20))
    except Exception:
        pass


def is_security_blocked(page: "Page") -> bool:
    """检测是否被猟聘安全中心拦截。"""
    try:
        title = (page.title() or "").lower()
        url = (page.url or "").lower()
    except Exception:
        return False
    if "安全中心" in title or "verify" in title.lower():
        return True
    if "safe.liepin" in url or "/security" in url:
        return True
    return False


def safe_goto(page: "Page", url: str, timeout_ms: int = 45000) -> bool:
    """带安全中心检测的 goto。返回 True=成功，False=被拦截。"""
    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    human_pause(2.0, 4.0)
    if is_security_blocked(page):
        return False
    return True
