# tools/poc_diagnose_dom_v2.py
"""
深度诊断猎聘 DOM：
- 等待网络真正空闲 + 额外等待 JS 渲染
- 列出页面上所有可见按钮 / a 标签 / file input
- 输出"投递路径假说"以便人工/代码核对
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION = Path("outputs/submissions/liepin/session/liepin")
URL = "https://www.liepin.com/job/1982028827.shtml"

KEY_TEXTS = [
    "立即沟通", "投递简历", "聊一聊", "立即申请", "申请职位",
    "上传简历", "上传附件", "更新简历", "重新上传",
    "登录", "登 录", "扫码登录", "继续",
]

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION),
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0]
        page.goto(URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(5000)  # 给 SPA 充分渲染时间

        print(f"[+] 当前 URL: {page.url}")
        print(f"[+] 页面标题: {page.title()}")

        # 1. 关键文本命中数（不限可见）
        print("\n[关键文本命中（all/visible）]")
        for txt in KEY_TEXTS:
            try:
                all_n = page.locator(f"text={txt}").count()
                vis_n = page.locator(f"text={txt}").locator("visible=true").count() if all_n else 0
            except Exception:
                all_n = vis_n = 0
            if all_n:
                print(f"  {txt:8s}  all={all_n:3d}  visible={vis_n:3d}")

        # 2. 列出所有可见 button + a 的文本（前 60 条）
        print("\n[可见按钮/链接 文本采样（前 60）]")
        elems = page.locator("button:visible, a:visible")
        n = elems.count()
        print(f"  total visible buttons+anchors = {n}")
        seen = set()
        out = []
        for i in range(min(n, 300)):
            try:
                t = elems.nth(i).inner_text(timeout=500).strip()
            except Exception:
                continue
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= 60:
                break
        for t in out:
            print(f"   • {t!r}")

        # 3. file inputs
        print("\n[file input 总览]")
        file_inputs = page.locator("input[type='file']")
        print(f"  count = {file_inputs.count()}")
        for i in range(min(file_inputs.count(), 5)):
            try:
                attrs = file_inputs.nth(i).evaluate(
                    "el => ({name: el.name, accept: el.accept, hidden: el.hidden, "
                    "display: getComputedStyle(el).display, visibility: getComputedStyle(el).visibility})"
                )
                print(f"  [{i}] {attrs}")
            except Exception as e:
                print(f"  [{i}] err: {e}")

        # 4. iframe 列表
        print("\n[iframes]")
        for i, fr in enumerate(page.frames):
            print(f"  [{i}] url={fr.url}")

        # 5. 保存最新截图与 HTML
        page.screenshot(path="debug_dom_v2.png", full_page=True)
        Path("debug_dom_v2.html").write_text(page.content(), encoding="utf-8")
        print("\n[+] 已保存 debug_dom_v2.png / debug_dom_v2.html")

        ctx.close()

if __name__ == "__main__":
    main()
