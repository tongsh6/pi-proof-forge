# tools/poc_probe_jobs.py
"""
随机采样多个猎聘职位详情页，统计每个页面暴露的"投递动作入口"，判断：
- 是否所有职位都只剩"聊一聊"
- 是否仍有部分职位保留传统"投递简历/上传简历"入口
"""
import sys
import re
import random
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION = Path("outputs/submissions/liepin/session/liepin")
LIST_URLS = [
    "https://www.liepin.com/zhaopin/?key=Java",
    "https://www.liepin.com/zhaopin/?key=%E5%89%8D%E7%AB%AF",  # 前端
    "https://www.liepin.com/zhaopin/?key=%E4%BA%A7%E5%93%81",  # 产品
]
SAMPLE_PER_LIST = 4

KEY_TEXTS = [
    "立即沟通", "投递简历", "聊一聊", "立即申请", "申请职位",
    "上传简历", "上传附件", "更新简历", "重新上传",
    "继续投递", "在线沟通",
]

JOB_URL_RE = re.compile(r"https?://(?:www\.)?liepin\.com/job/\d+\.shtml")

def collect_job_urls(page, list_url):
    page.goto(list_url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(2000)
    hrefs = page.eval_on_selector_all(
        "a", "els => els.map(e => e.href).filter(Boolean)"
    )
    urls = set()
    for h in hrefs:
        if JOB_URL_RE.match(h):
            urls.add(h.split("?")[0])
    return list(urls)

def probe_job(page, url):
    out = {"url": url, "title": "", "final_url": "", "hits": {}, "file_inputs": 0, "iframes": 0}
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3500)
    except Exception as e:
        out["error"] = f"goto failed: {e}"
        return out
    out["final_url"] = page.url
    try: out["title"] = page.title()
    except Exception: pass
    for txt in KEY_TEXTS:
        try:
            vis = page.locator(f"text={txt}").locator("visible=true").count()
        except Exception:
            vis = 0
        if vis:
            out["hits"][txt] = vis
    try: out["file_inputs"] = page.locator("input[type='file']").count()
    except Exception: pass
    try: out["iframes"] = len(page.frames)
    except Exception: pass
    return out

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION),
            headless=True, channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0]

        all_urls = []
        for lu in LIST_URLS:
            print(f"[*] 采集列表: {lu}")
            try:
                urls = collect_job_urls(page, lu)
                print(f"    -> {len(urls)} 个职位 URL")
                random.shuffle(urls)
                all_urls.extend(urls[:SAMPLE_PER_LIST])
            except Exception as e:
                print(f"    !! 失败: {e}")

        # 保留 1 个老 URL 做对照
        all_urls.insert(0, "https://www.liepin.com/job/1982028827.shtml")
        seen = set(); dedup = []
        for u in all_urls:
            if u not in seen:
                seen.add(u); dedup.append(u)
        print(f"\n[*] 共将探测 {len(dedup)} 个职位\n")

        results = []
        for i, u in enumerate(dedup, 1):
            print(f"[{i}/{len(dedup)}] {u}")
            r = probe_job(page, u)
            results.append(r)
            print(f"    title: {r.get('title','')[:60]}")
            if r.get("error"):
                print(f"    ERR: {r['error']}")
            else:
                print(f"    hits: {r['hits']}  file_inputs={r['file_inputs']}  iframes={r['iframes']}")

        # 统计
        print("\n========== 汇总 ==========")
        from collections import Counter
        c = Counter()
        for r in results:
            for k in r.get("hits", {}):
                c[k] += 1
        print(f"采样职位数: {len(results)}")
        for k, n in c.most_common():
            print(f"  {k:8s}: 出现于 {n} 个职位")
        n_file = sum(1 for r in results if r.get("file_inputs",0) > 0)
        print(f"  含 input[type=file] 的职位: {n_file}")

        ctx.close()

if __name__ == "__main__":
    main()
