# tools/poc_pick_low_profile.py
"""挑一个低关注度职位用于真实端到端验证：
   - 优先小城市 + 小公司
   - 排除大厂/已上市
"""
import random
from playwright.sync_api import sync_playwright
from pathlib import Path

SESSION = Path("outputs/submissions/liepin/session/liepin")
LIST_URL = "https://www.liepin.com/zhaopin/?key=Java&dqs=080050"  # 080050 = 长沙

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION),
            headless=True, channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0]
        page.goto(LIST_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3000)
        # 滚动触发懒加载
        for _ in range(4):
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(800)
        try:
            page.wait_for_selector("a[href*='/job/']", timeout=15000)
        except Exception:
            page.screenshot(path="outputs/poc_chat_flow/list_debug.png", full_page=True)
            Path("outputs/poc_chat_flow/list_debug.html").write_text(page.content(), encoding="utf-8")
            print("[!] 列表未加载出 a[href*='/job/']，已存 list_debug.png/html")

        # 抓职位卡片：URL + 公司名 + 公司规模/行业
        cards = page.eval_on_selector_all(
            "a[href*='/job/']",
            """anchors => {
              const out = [];
              const seen = new Set();
              for (const a of anchors) {
                const href = a.href.split('?')[0];
                if (seen.has(href)) continue;
                seen.add(href);
                // 找最近的卡片祖先
                let card = a;
                for (let k = 0; k < 8 && card; k++) {
                  if (card.innerText && card.innerText.length > 60) break;
                  card = card.parentElement;
                }
                const text = card ? card.innerText : a.innerText;
                out.push({href, text: text.slice(0, 400)});
              }
              return out;
            }"""
        )
        print(f"[*] 抓到 {len(cards)} 张卡片")
        # 排除大厂关键词
        BIG = ["已上市", "10000人以上", "5000-10000", "字节", "阿里", "腾讯", "百度", "京东",
               "美团", "拼多多", "小红书", "快手", "B站", "携程", "蚂蚁"]
        candidates = []
        for c in cards:
            blob = c["text"]
            if not blob or "/job/" not in c["href"]:
                continue
            if any(k in blob for k in BIG):
                continue
            candidates.append(c)

        print(f"[*] 排除大厂后剩 {len(candidates)} 个候选")
        random.shuffle(candidates)
        for c in candidates[:6]:
            print("  ----")
            print(f"  href: {c['href']}")
            print(f"  text: {c['text'][:200]}")
        ctx.close()

if __name__ == "__main__":
    main()
