"""端到端真实投递 PoC（带反反爬 + 人类化节奏 + 多级安全护栏）。

流程：
1. 用 stealth context 打开职位 URL
2. 检测安全中心 / 登录态
3. 模拟人类停留浏览（滚动 + 长停留）
4. 点击"聊一聊"，等待聊天面板出现
5. 在聊天面板里点"发简历"
6. 选择简历文件 / 选默认简历
7. （可选）点击最终"发送"

用法：
    .venv/bin/python tools/poc_e2e_send.py <job_url> [--really-send]

不带 --really-send 时停在"发送前"，截图保留全部 DOM 供人工核对。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# 让 tools.submission._browser 可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.submission._browser import (  # noqa: E402
    DEFAULT_SESSION,
    human_long_pause,
    human_mouse_jiggle,
    human_pause,
    human_scroll,
    is_security_blocked,
    make_context,
)

OUT_DIR = Path("outputs/poc_e2e_send")


def snap(page, name: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / f"{name}.png"
    html = OUT_DIR / f"{name}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
        html.write_text(page.content(), encoding="utf-8")
        print(f"  snap → {png.name}")
    except Exception as e:
        print(f"  snap fail({name}): {e}")


def extract_job_id(url: str) -> str | None:
    m = re.search(r"/job/(\d+)\.shtml", url)
    return m.group(1) if m else None


def run(job_url: str, really_send: bool, headless: bool):
    job_id = extract_job_id(job_url)
    if not job_id:
        print(f"[!] 无法从 URL 提取 job_id: {job_url}")
        return 20
    print(f"[*] job_url      = {job_url}")
    print(f"[*] job_id       = {job_id}")
    print(f"[*] really_send  = {really_send}")
    print(f"[*] headless     = {headless}")
    print(f"[*] session_dir  = {DEFAULT_SESSION}")

    with make_context(session_dir=DEFAULT_SESSION, headless=headless) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # ---------- step 1: 打开职位 ----------
        print("\n[1/6] 打开职位详情页 ...")
        page.goto(job_url, wait_until="networkidle", timeout=45000)
        human_pause(2.0, 4.0)
        if is_security_blocked(page):
            snap(page, "01_blocked")
            print(f"[!] 命中安全中心：{page.title()} | {page.url}")
            print("[!] 停止。冷却 15-30 分钟后重试。")
            return 11
        print(f"  title : {page.title()[:80]}")
        print(f"  url   : {page.url}")
        snap(page, "01_job_loaded")

        # ---------- step 2: 模拟人类浏览 ----------
        print("\n[2/6] 模拟人类浏览节奏 ...")
        human_mouse_jiggle(page)
        human_scroll(page, steps=3)
        human_long_pause(6.0, 14.0)  # 装作在读 JD
        snap(page, "02_after_browsing")

        # ---------- step 3: 用 data-tlg-elem-id 锁定主职位 chat 按钮 ----------
        print("\n[3/6] 锁定主职位聊天按钮（按 tlg-elem-id） ...")
        # 主职位 chat 按钮 tlg-elem-id：
        #   - c_pc_job_detail_chat_btn          （顶部主按钮）
        #   - c_pc_job_detail_recruiter_chat_btn （HR 卡片里的按钮，同一个 HR）
        # 推荐区按钮 tlg-elem-id：
        #   - c_pc_job_detail_like_chat_btn      ← 必须排除
        main_chat_sel = (
            "a[data-tlg-elem-id='c_pc_job_detail_chat_btn'],"
            "a[data-tlg-elem-id='c_pc_job_detail_recruiter_chat_btn']"
        )
        main_chat = page.locator(main_chat_sel)
        cnt = main_chat.count()
        print(f"  主职位 chat 按钮匹配 = {cnt}")
        if cnt == 0:
            print("[!] 未找到主职位 chat 按钮，停止")
            snap(page, "03_no_main_chat")
            return 12

        # Sanity check：解析 data-params 中的 jobId/recruiterName
        try:
            params_raw = main_chat.first.get_attribute("data-params") or "{}"
            params = json.loads(params_raw)
            recruiter_name = params.get("recruiterName", "")
            recruiter_id = params.get("recruiterId", "")
            param_job_id = params.get("jobId", "")
            # data-jobid 属性
            dom_jobid = main_chat.first.get_attribute("data-jobid") or ""
            print(f"  recruiterName : {recruiter_name}")
            print(f"  recruiterId   : {recruiter_id}")
            print(f"  params.jobId  : {param_job_id}")
            print(f"  data-jobid    : {dom_jobid}")
            # job_id 一致性：URL path 末几位应包含在 data-jobid 中
            if dom_jobid and dom_jobid not in job_id:
                print(f"[!] sanity check 失败：data-jobid({dom_jobid}) 不在 url.job_id({job_id}) 中")
                snap(page, "03_sanity_failed")
                return 17
            # 所有主按钮的 jobid 必须相同（防止 selector 串到别的职位）
            jobids = set()
            for i in range(cnt):
                jid = main_chat.nth(i).get_attribute("data-jobid") or ""
                jobids.add(jid)
            print(f"  按钮共享 jobid 集合: {jobids}")
            if len(jobids) > 1:
                print("[!] 主按钮 jobid 不一致，停止")
                snap(page, "03_jobid_mismatch")
                return 19
        except Exception as e:
            print(f"[!] 解析 data-params 失败: {e}")
            snap(page, "03_parse_params_failed")
            return 18

        # 同时探测"直接投简历"按钮
        apply_sel = "a[data-tlg-elem-id='c_pc_job_detail_apply_btn']"
        apply_btn = page.locator(apply_sel)
        apply_btn_cnt = apply_btn.count()
        print(f"  直投按钮（apply-job）匹配 = {apply_btn_cnt}")
        if apply_btn_cnt > 0:
            try:
                apply_text = apply_btn.first.inner_text(timeout=1000).strip()
                print(f"  直投按钮文本: {apply_text!r}")
            except Exception:
                pass

        # 看主 chat 按钮当前文字（"聊一聊" 或 "继续聊"）
        try:
            chat_text = main_chat.first.inner_text(timeout=1000).strip()
            print(f"  主 chat 按钮文本: {chat_text!r}")
        except Exception:
            chat_text = ""

        print("\n[3.5/6] 点击主职位 chat 按钮 ...")
        try:
            main_chat.first.scroll_into_view_if_needed(timeout=3000)
            human_pause(0.5, 1.5)
            main_chat.first.click(timeout=8000)
        except Exception as e:
            print(f"[!] 点击主 chat 失败: {e}")
            snap(page, "03_click_main_chat_failed")
            return 13
        human_pause(3.0, 5.0)
        snap(page, "03_after_chat_clicked")

        # ---------- step 4: 等待聊天面板 ----------
        print("\n[4/6] 等待聊天面板出现 ...")
        send_resume_loc = page.locator("text=发简历").locator("visible=true")
        for i in range(10):
            if send_resume_loc.count() > 0:
                break
            page.wait_for_timeout(500)
        if send_resume_loc.count() == 0:
            print("[!] 聊天面板未出现/未找到'发简历'按钮")
            snap(page, "04_no_send_resume")
            # 列一下当前可见 button 帮诊断
            try:
                btns = page.locator("button:visible")
                for i in range(min(btns.count(), 20)):
                    try:
                        print(f"   btn[{i}]: {btns.nth(i).inner_text(timeout=300)!r}")
                    except Exception:
                        pass
            except Exception:
                pass
            return 14
        print(f"  visible '发简历' = {send_resume_loc.count()}")

        # ---------- step 5: 点'发简历'（弹出选择器/确认） ----------
        print("\n[5/6] 点击'发简历' ...")
        try:
            send_resume_loc.first.click(timeout=5000)
        except Exception as e:
            print(f"[!] 点击'发简历'失败: {e}")
            snap(page, "05_click_send_resume_failed")
            return 15
        human_pause(2.0, 4.0)
        snap(page, "05_after_send_resume_clicked")

        # 看是否弹出"确认发送"或"选择简历"对话框
        print("\n  检查后续控件 ...")
        for txt in ["确认发送", "确定", "发送", "继续投递", "我的简历", "选择简历"]:
            try:
                c = page.locator(f"text={txt}").locator("visible=true").count()
            except Exception:
                c = 0
            if c:
                print(f"    visible {txt!r} = {c}")

        # ---------- step 6: 真实发送（可选） ----------
        if not really_send:
            print("\n[6/6] dry-run 模式：不点击最终发送，PoC 结束。")
            print(f"\n[OK] 流程走到'发简历'弹窗，DOM/截图见 {OUT_DIR.resolve()}")
            human_pause(2.0, 3.0)
            return 0

        print("\n[6/6] 真实发送：寻找最终发送按钮 ...")
        # 关键：猟聘 modal 按钮文本是「确 定」（带空格），需要兼容
        # 优先点 modal-confirm-btns 区域里的 ant-im-btn-primary
        confirm_btn = page.locator(
            ".ant-im-modal-confirm-btns button.ant-im-btn-primary:visible"
        )
        if confirm_btn.count() > 0:
            print(f"  命中 confirm modal primary button = {confirm_btn.count()}")
            try:
                confirm_btn.first.click(timeout=5000)
                human_pause(3.0, 5.0)
                snap(page, "06_after_final_send")
                print("\n[DONE] 真实发送已触发。请人工核对截图与你的猟聘聊天界面。")
                return 0
            except Exception as e:
                print(f"[!] 点击 confirm modal primary 失败: {e}")
        # 兜底：按文本兼容（带/不带空格）
        for txt in ["确 定", "确定", "确认发送", "确定发送"]:
            loc = page.locator(f"button:has-text('{txt}')").locator("visible=true")
            if loc.count() > 0:
                print(f"  点击 {txt!r}")
                try:
                    loc.first.click(timeout=5000)
                    human_pause(3.0, 5.0)
                    snap(page, "06_after_final_send")
                    print("\n[DONE] 真实发送已触发。请人工核对截图与你的猟聘聊天界面。")
                    return 0
                except Exception as e:
                    print(f"[!] 点击 {txt!r} 失败: {e}")
        print("[!] 未找到'确认发送/确定'按钮，停止以避免误操作。")
        snap(page, "06_no_confirm_btn")
        return 16


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_url", help="猟聘职位详情页 URL，例如 https://www.liepin.com/job/1982028827.shtml")
    ap.add_argument("--really-send", action="store_true",
                    help="真实点击发送（默认 dry-run，停在最终发送前）")
    ap.add_argument("--headed", action="store_true", help="以可视模式跑（默认 headless）")
    args = ap.parse_args()

    code = run(args.job_url, really_send=args.really_send, headless=not args.headed)
    sys.exit(code)


if __name__ == "__main__":
    main()
