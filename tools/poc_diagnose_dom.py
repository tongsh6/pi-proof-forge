# tools/poc_diagnose_dom.py
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    session_dir = Path("outputs/submissions/liepin/session/liepin")
    url = "https://www.liepin.com/job/1982028827.shtml"
    
    print(f"[*] 正在诊断 DOM，Session: {session_dir}")
    print(f"[*] 目标 URL: {url}")
    
    with sync_playwright() as p:
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=True, # 后台运行即可
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser_context.pages[0]
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000) # 等待渲染
            
            # 1. 保存截图
            page.screenshot(path="debug_dom.png", full_page=True)
            print("[+] 已保存截图: debug_dom.png")
            
            # 2. 保存 HTML
            Path("debug_dom.html").write_text(page.content(), encoding="utf-8")
            print("[+] 已保存 HTML: debug_dom.html")
            
            # 3. 检查当前 URL (确认是否被重定向)
            print(f"[+] 当前真实 URL: {page.url}")
            
            # 4. 模拟 _is_logged_in 逻辑
            current_url = page.url.lower()
            is_passport = "passport" in current_url or "login" in current_url
            inline_login = page.locator("[data-selector='inline-login']:visible, .inline-login-container:visible").count()
            login_btn = page.locator("a:has-text('登录'):visible, button:has-text('登录/注册'):visible").count()
            user_indicators = page.locator("[data-selector='chat-chat']:visible, [data-selector='c-logout']:visible, .recruiter-info-box:visible").count()
            
            print(f"[?] 检测详情:")
            print(f"    - is_passport_url: {is_passport}")
            print(f"    - inline_login_visible_count: {inline_login}")
            print(f"    - login_btn_visible_count: {login_btn}")
            print(f"    - user_indicators_count: {user_indicators}")
            
        finally:
            browser_context.close()

if __name__ == "__main__":
    main()
