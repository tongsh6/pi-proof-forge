import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    session_dir = Path("outputs/submissions/liepin/session/liepin")
    session_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[*] 正在启动 Chrome，加载 Session: {session_dir}")
    print("[!] 请在打开的窗口中完成登录和验证码校验。")
    print("[!] 完成后，请直接关闭浏览器窗口，脚本会自动保存状态。")
    
    try:
        with sync_playwright() as p:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir),
                headless=False,
                channel="chrome",  # 使用本地 Chrome 减少指纹特征
                viewport={"width": 1440, "height": 900},
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser_context.pages[0]
            page.goto("https://www.liepin.com/", wait_until="networkidle")
            
            # 保持运行直到用户关闭浏览器
            print("[*] 窗口已打开，等待你的操作...")
            
            # 阻塞直到浏览器关闭
            try:
                while len(browser_context.pages) > 0:
                    page.wait_for_timeout(1000)
            except Exception:
                pass
            
            print("[*] 浏览器已关闭，Session 已保存。")
    except Exception as e:
        print(f"[!] 启动失败: {e}")
        print("[!] 请确保本机已安装 Chrome 且可通过 playwright 调用。")

if __name__ == "__main__":
    main()
