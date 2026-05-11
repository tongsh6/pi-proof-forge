# tools/poc_chat_flow.py
"""
单职位"聊一聊"流程探测：
1. 打开职位页（带随机延迟避免触发安全中心）
2. 点击"聊一聊"
3. 等待跳转 / 弹窗，记录新的 URL / DOM
4. 在新页面/弹窗里枚举"发送简历附件"相关控件：
   - input[type=file]
   - 含"简历/附件/发送/+"等关键文本的按钮
5. 保存截图与 HTML 供人工核对
"""
import sys
import time
import random
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION = Path("outputs/submissions/liepin/session/liepin")
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.liepin.com/job/1982028827.shtml"

KEY_TEXTS = [
    "聊一聊", "立即沟通", "在线沟通",
    "发送简历", "发简历", "投递简历", "附件简历", "上传附件", "上传简历",
    "我的简历", "选择简历", "添加附件", "+",
    "发送", "确认发送", "确定", "继续",
]

def slow_open(page, url):
    page.goto(url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(int(random.uniform(2500, 4500)))

def dump_scope(scope, label, out_dir):
    """枚举一个 page 或 frame 上的关键交互元素"""
    print(f"\n=== [{label}] {getattr(scope, 'url', '')} ===")
    try:
        title = scope.title() if hasattr(scope, "title") else "(frame)"
    except Exception:
        title = "(unknown)"
    print(f"    title: {title}")

    # file inputs
    try:
        n_file = scope.locator("input[type='file']").count()
    except Exception:
        n_file = 0
    print(f"    input[type=file] count = {n_file}")
    for i in range(min(n_file, 5)):
        try:
            attrs = scope.locator("input[type='file']").nth(i).evaluate(
                "el => ({name: el.name, accept: el.accept, hidden: el.hidden, "
                "display: getComputedStyle(el).display})"
            )
            print(f"      [{i}] {attrs}")
        except Exception as e:
            print(f"      [{i}] err: {e}")

    # key text hits (visible)
    print("    关键文本 (visible):")
    for txt in KEY_TEXTS:
        try:
            n = scope.locator(f"text={txt}").locator("visible=true").count()
        except Exception:
            n = 0
        if n:
            print(f"      • {txt!r:14s}  visible={n}")

    # 可见按钮采样
    try:
        n_btn = scope.locator("button:visible").count()
        print(f"    可见 button 总数 = {n_btn}")
        seen = set()
        for i in range(min(n_btn, 50)):
            try:
                t = scope.locator("button:visible").nth(i).inner_text(timeout=300).strip()
            except Exception:
                continue
            if t and t not in seen:
                seen.add(t)
                if len(seen) <= 30:
                    print(f"      • {t!r}")
    except Exception as e:
        print(f"    枚举 button 失败: {e}")

def main():
    out_dir = Path("outputs/poc_chat_flow")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION),
            headless=False,  # 用 headed，更接近真人
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0]

        print(f"[*] 打开职位: {URL}")
        slow_open(page, URL)
        print(f"[+] 当前 URL: {page.url}")
        print(f"[+] 标题: {page.title()}")

        if "安全中心" in page.title():
            print("[!] 命中安全中心验证码页，停止")
            page.screenshot(path=str(out_dir / "00_security.png"), full_page=True)
            ctx.close()
            return

        # 投递前快照
        page.screenshot(path=str(out_dir / "01_before_chat.png"), full_page=True)
        Path(out_dir / "01_before_chat.html").write_text(page.content(), encoding="utf-8")

        chat_loc = page.locator("text=聊一聊").locator("visible=true")
        cnt = chat_loc.count()
        print(f"\n[*] 可见'聊一聊'命中: {cnt}")
        if cnt == 0:
            print("[!] 未找到'聊一聊'入口，退出")
            ctx.close()
            return

        # 监听新页面
        new_pages = []
        ctx.on("page", lambda pg: new_pages.append(pg))

        before_urls = {p.url for p in ctx.pages}
        print("[*] 点击'聊一聊'...")
        try:
            chat_loc.first.click(timeout=8000)
        except Exception as e:
            print(f"[!] 点击失败: {e}")
        page.wait_for_timeout(5000)

        # 等待新页面/iframe出现
        for _ in range(8):
            if new_pages:
                break
            page.wait_for_timeout(500)

        # 当前 page 状态
        print(f"\n[+] 点击后原 page URL: {page.url}")
        dump_scope(page, "原 page", out_dir)
        for i, fr in enumerate(page.frames):
            if fr is page.main_frame:
                continue
            print(f"  - frame[{i}]: {fr.url}")

        # 新页面
        print(f"\n[*] 新打开的 page 数: {len(new_pages)}")
        for i, pg in enumerate(new_pages):
            try:
                pg.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            pg.wait_for_timeout(2500)
            print(f"  - new page[{i}] URL: {pg.url}")
            dump_scope(pg, f"new_page[{i}]", out_dir)
            try:
                pg.screenshot(path=str(out_dir / f"02_chat_page_{i}.png"), full_page=True)
                Path(out_dir / f"02_chat_page_{i}.html").write_text(pg.content(), encoding="utf-8")
            except Exception as e:
                print(f"    截图失败: {e}")

        print(f"\n[+] 产物在: {out_dir.resolve()}")
        # 让用户看一眼再关
        page.wait_for_timeout(3000)
        ctx.close()

if __name__ == "__main__":
    main()
