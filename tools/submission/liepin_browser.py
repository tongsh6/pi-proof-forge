"""猎聘页内交互：目标核验、聊天发简历、附件上传与页面模式检测。

从 submission/liepin.py 拆出；liepin.py 保留同名符号 re-export，主流程按原顺序
调用页内动作。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

from .liepin_types import (
    APPLY_DIALOG_TRIGGERS,
    MAIN_CHAT_SELECTOR,
    UPLOAD_PANEL_TRIGGERS,
    LiepinSubmissionConfig,
    TargetVerification,
)
from .storage import SubmissionRecorder


def _extract_liepin_job_id(url: str) -> str | None:
    match = re.search(r"/job/(\d+)\.shtml", url)
    return match.group(1) if match else None

def _verify_main_chat_target(page: Page, job_url: str) -> TargetVerification:
    url_job_id = _extract_liepin_job_id(job_url) or ""
    if not url_job_id:
        return TargetVerification(ok=False, reason="invalid_job_url")

    main_chat = page.locator(MAIN_CHAT_SELECTOR)
    matched_count = main_chat.count()
    if matched_count == 0:
        return TargetVerification(
            ok=False,
            reason="main_chat_button_not_found",
            url_job_id=url_job_id,
        )

    first = main_chat.first
    params_raw = first.get_attribute("data-params") or "{}"
    try:
        params = json.loads(params_raw)
    except json.JSONDecodeError:
        params = {}

    recruiter_name = str(params.get("recruiterName", "") or "")
    recruiter_id = str(params.get("recruiterId", "") or "")
    params_jobid = str(params.get("jobId", "") or "")
    dom_jobid = str(first.get_attribute("data-jobid") or params_jobid)

    candidate_jobids: set[str] = set()
    for index in range(matched_count):
        item = main_chat.nth(index)
        item_jobid = str(item.get_attribute("data-jobid") or "")
        if item_jobid:
            candidate_jobids.add(item_jobid)

    if len(candidate_jobids) > 1:
        return TargetVerification(
            ok=False,
            reason="target_mismatch",
            url_job_id=url_job_id,
            dom_jobid=dom_jobid,
            params_jobid=params_jobid,
            recruiter_name=recruiter_name,
            recruiter_id=recruiter_id,
            matched_count=matched_count,
        )

    if dom_jobid and dom_jobid not in url_job_id:
        return TargetVerification(
            ok=False,
            reason="target_mismatch",
            url_job_id=url_job_id,
            dom_jobid=dom_jobid,
            params_jobid=params_jobid,
            recruiter_name=recruiter_name,
            recruiter_id=recruiter_id,
            matched_count=matched_count,
        )

    return TargetVerification(
        ok=True,
        url_job_id=url_job_id,
        dom_jobid=dom_jobid,
        params_jobid=params_jobid,
        recruiter_name=recruiter_name,
        recruiter_id=recruiter_id,
        matched_count=matched_count,
    )

def _verify_submit_safety(
    config: LiepinSubmissionConfig,
    verification: TargetVerification,
) -> tuple[bool, str]:
    if Path(config.resume_path).suffix.lower() != ".pdf":
        return False, "submit_resume_must_be_pdf"
    expected_job_id = config.confirm_submit_job_id.strip()
    expected_recruiter = config.confirm_submit_recruiter.strip()
    if not expected_job_id or not expected_recruiter:
        return False, "submit_confirmation_missing"
    if expected_job_id != verification.url_job_id:
        return False, "submit_confirmation_job_id_mismatch"
    if expected_recruiter != verification.recruiter_name:
        return False, "submit_confirmation_recruiter_mismatch"
    return (
        True,
        f"submit_confirmed:job_id={expected_job_id}; recruiter={expected_recruiter}",
    )

def _target_verification_detail(
    config: LiepinSubmissionConfig,
    verification: TargetVerification,
) -> str:
    if config.external_l3_validation_run_id or config.external_l3_validation_path:
        return (
            f"url_job_id_present={bool(verification.url_job_id)}; "
            f"dom_jobid_present={bool(verification.dom_jobid)}; "
            f"params_jobid_present={bool(verification.params_jobid)}; "
            f"recruiter_present={bool(verification.recruiter_name)}; "
            f"matched_count={verification.matched_count}; "
            "raw_values_redacted=true"
        )
    return (
        f"url_job_id={verification.url_job_id}; "
        f"dom_jobid={verification.dom_jobid}; "
        f"params_jobid={verification.params_jobid}; "
        f"recruiter={verification.recruiter_name}"
    )

def _send_resume_via_chat(
    page: Page,
    job_url: str,
    timeout_ms: int,
    submit: bool,
) -> tuple[bool, str]:
    # 当前默认“发简历”发送平台已有简历，尚不能绑定本次本地 PDF。
    # 在真实附件入口完成验证与接通前，必须停在打开聊天之前。
    if submit:
        return False, "resume_attachment_binding_unverified"

    verification = _verify_main_chat_target(page, job_url)
    if not verification.ok:
        return False, verification.reason

    main_chat = page.locator(MAIN_CHAT_SELECTOR)
    try:
        main_chat.first.scroll_into_view_if_needed(timeout=3000)
        main_chat.first.click(timeout=min(timeout_ms, 8000))
        page.wait_for_timeout(3000)
    except Exception as exc:
        return False, f"main_chat_click_failed:{exc}"

    send_resume = page.locator("text=发简历").locator("visible=true")
    for _ in range(10):
        if send_resume.count() > 0:
            break
        page.wait_for_timeout(500)

    if send_resume.count() == 0:
        return False, "send_resume_button_not_found"

    try:
        send_resume.first.click(timeout=min(timeout_ms, 5000))
        page.wait_for_timeout(2000)
    except Exception as exc:
        return False, f"send_resume_click_failed:{exc}"

    return True, "chat_send_resume_ready"

def _click_confirm_send_resume(page: Page, timeout_ms: int) -> tuple[bool, str]:
    confirm_btn = page.locator(
        ".ant-im-modal-confirm-btns button.ant-im-btn-primary:visible"
    )
    if confirm_btn.count() > 0:
        confirm_btn.first.click(timeout=timeout_ms)
        page.wait_for_timeout(3000)
        return True, "confirm_modal_primary"

    for text in ("确 定", "确定", "确认发送", "确定发送"):
        loc = page.locator(f"button:has-text('{text}')").locator("visible=true")
        if loc.count() > 0:
            loc.first.click(timeout=timeout_ms)
            page.wait_for_timeout(3000)
            return True, f"confirm_text:{text}"

    return False, "confirm_send_button_not_found"

def _upload_resume(page: Page, resume_path: str, timeout_ms: int, page_mode: str) -> tuple[bool, str]:
    resume_file = Path(resume_path)
    if not resume_file.exists() or not resume_file.is_file():
        return False, f"resume file not found: {resume_path}"

    input_selectors = [
        "input[type='file'][accept*='pdf']",
        "input[type='file'][name*='resume']",
        "input[name*='resume'][type='file']",
        "input[accept*='.pdf']",
        "input[type='file']",
    ]
    attempt_details: list[str] = []

    for phase in _plan_upload_phases(page_mode):
        ok, detail = _run_upload_phase(page, resume_path, timeout_ms, input_selectors, phase)
        if ok:
            return True, detail
        attempt_details.append(detail)

    detail_text = " | ".join(attempt_details)
    return False, f"upload input not found after phases: direct, upload_trigger, apply_dialog; details={detail_text}"

def _plan_upload_phases(page_mode: str) -> list[str]:
    if page_mode == "apply_entry":
        return ["apply_dialog", "upload_trigger", "direct"]
    return ["direct", "upload_trigger", "apply_dialog"]

def _run_upload_phase(
    page: Page,
    resume_path: str,
    timeout_ms: int,
    input_selectors: list[str],
    phase: str,
) -> tuple[bool, str]:
    if phase == "direct":
        ok, detail = _upload_in_page_and_frames(page, resume_path, input_selectors)
        return (True, f"phase=direct; {detail}") if ok else (False, f"phase=direct; {detail}")

    if phase == "upload_trigger":
        _open_upload_panel(page, timeout_ms)
        ok, detail = _upload_via_file_chooser(page, resume_path, timeout_ms, UPLOAD_PANEL_TRIGGERS, phase_name="upload_trigger")
        if ok:
            return True, detail
        ok, detail2 = _upload_in_page_and_frames(page, resume_path, input_selectors)
        return (
            (True, f"phase=upload_trigger; {detail2}")
            if ok
            else (False, f"phase=upload_trigger; chooser={detail}; locator={detail2}")
        )

    _open_apply_dialog(page, timeout_ms)
    ok, detail = _upload_via_file_chooser(page, resume_path, timeout_ms, APPLY_DIALOG_TRIGGERS, phase_name="apply_dialog")
    if ok:
        return True, detail
    _open_upload_panel(page, timeout_ms)
    ok, detail2 = _upload_in_page_and_frames(page, resume_path, input_selectors)
    return (
        (True, f"phase=apply_dialog; {detail2}")
        if ok
        else (False, f"phase=apply_dialog; chooser={detail}; locator={detail2}")
    )

def _upload_in_page_and_frames(page: Page, resume_path: str, selectors: list[str]) -> tuple[bool, str]:
    ok, detail = _upload_in_scope(page, resume_path, selectors, scope_name="main_page")
    if ok:
        return True, detail

    last_detail = detail
    for index, frame in enumerate(page.frames):
        ok, detail = _upload_in_scope(frame, resume_path, selectors, scope_name=f"frame[{index}]")
        if ok:
            return True, detail
        last_detail = detail

    return False, last_detail

def _upload_in_scope(scope: Page | Frame, resume_path: str, selectors: list[str], scope_name: str) -> tuple[bool, str]:
    last_error = f"no upload input found in {scope_name}"
    for selector in selectors:
        try:
            file_input = scope.locator(selector)
            if file_input.count() == 0:
                continue
            file_input.first.set_input_files(resume_path)
            return True, f"uploaded in {scope_name} via selector: {selector}"
        except Exception as exc:
            last_error = f"upload failed in {scope_name} via selector {selector}: {exc}"

    return False, last_error

def _upload_via_file_chooser(
    page: Page,
    resume_path: str,
    timeout_ms: int,
    triggers: list[str],
    phase_name: str,
) -> tuple[bool, str]:
    last_error = f"phase={phase_name}; no trigger for file chooser"
    for selector in triggers:
        trigger = page.locator(selector)
        if trigger.count() == 0:
            continue
        try:
            with page.expect_file_chooser(timeout=timeout_ms) as chooser_info:
                trigger.first.click(timeout=timeout_ms)
            chooser_info.value.set_files(resume_path)
            page.wait_for_timeout(800)
            return True, f"phase={phase_name}; uploaded via file chooser trigger: {selector}"
        except Exception as exc:
            last_error = f"phase={phase_name}; trigger failed: {selector}; error={exc}"
    return False, last_error

def _detect_page_mode(page: Page) -> str:
    file_input_selectors = [
        "input[type='file'][accept*='pdf']",
        "input[type='file'][name*='resume']",
        "input[name*='resume'][type='file']",
        "input[accept*='.pdf']",
        "input[type='file']",
    ]
    if _has_any_selector_in_page_and_frames(page, file_input_selectors):
        return "upload_ready"

    has_apply = _has_any_selector_in_page_and_frames(page, APPLY_DIALOG_TRIGGERS)
    has_upload = _has_any_selector_in_page_and_frames(page, UPLOAD_PANEL_TRIGGERS)
    if has_apply:
        return "apply_entry"
    if has_upload:
        return "upload_entry"
    return "unknown"

def _is_error_page(page: Page) -> bool:
    current_url = page.url.lower()
    if any(token in current_url for token in ("/error", "/404", "notfound")):
        return True

    error_selectors = [
        ".error-main-container",
        "#error-pc",
        "#error-h5",
        "text=页面不存在",
        "text=访问的页面不存在",
        "text=页面走丢了",
        "text=您访问的页面",
        "text=已下线",
        "text=浏览更多优质职位",
    ]
    return _has_any_selector_in_page_and_frames(page, error_selectors)

def _has_any_selector_in_page_and_frames(page: Page, selectors: list[str]) -> bool:
    if _has_any_selector_in_scope(page, selectors):
        return True
    for frame in page.frames:
        if _has_any_selector_in_scope(frame, selectors):
            return True
    return False

def _has_any_selector_in_scope(scope: Page | Frame, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            if scope.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False

def _dump_dom_snapshots(page: Page, html_dir: Path) -> list[str]:
    html_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    scopes: list[tuple[str, Page | Frame]] = [("main_page", page)]
    for idx, frame in enumerate(page.frames):
        scopes.append((f"frame_{idx}", frame))

    for idx, (scope_name, scope) in enumerate(scopes, start=1):
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in scope_name)
        file_path = html_dir / f"{idx:02d}_{safe_name}.html"
        try:
            content = scope.content()
        except Exception as exc:
            content = f"<!-- failed to dump html for {scope_name}: {exc} -->"
        _ = file_path.write_text(content, encoding="utf-8")
        saved.append(str(file_path))

    return saved

def _external_l3_mode(config: LiepinSubmissionConfig) -> bool:
    return bool(
        config.external_l3_validation_run_id or config.external_l3_validation_path
    )

def _capture_browser_screenshot(
    page: Page,
    recorder: SubmissionRecorder,
    config: LiepinSubmissionConfig,
    step_name: str,
) -> Path | None:
    if _external_l3_mode(config):
        return None
    screenshot = recorder.screenshot_path(step_name)
    _ = page.screenshot(path=str(screenshot), full_page=True)
    return screenshot

def _record_dom_snapshot_step(
    recorder: SubmissionRecorder,
    config: LiepinSubmissionConfig,
    page: Page,
) -> None:
    if _external_l3_mode(config):
        recorder.add_step(
            "dom_snapshot",
            "skipped",
            "raw_browser_artifacts_persisted=false; reason=external_l3_redaction_policy",
        )
        return
    snapshot_paths = _dump_dom_snapshots(page, recorder.run_dir / "html")
    snapshot_text = ",".join(snapshot_paths) if snapshot_paths else "none"
    recorder.add_step(
        "dom_snapshot",
        "success",
        f"saved html snapshots: {snapshot_text}",
    )

def _open_apply_dialog(page: Page, timeout_ms: int) -> None:
    for selector in APPLY_DIALOG_TRIGGERS:
        trigger = page.locator(selector)
        if trigger.count() == 0:
            continue
        try:
            trigger.first.click(timeout=timeout_ms)
            page.wait_for_timeout(500)
        except Exception:
            continue

def _open_upload_panel(page: Page, timeout_ms: int) -> None:
    for selector in UPLOAD_PANEL_TRIGGERS:
        trigger = page.locator(selector)
        if trigger.count() == 0:
            continue
        try:
            trigger.first.click(timeout=timeout_ms)
            page.wait_for_timeout(300)
        except Exception:
            continue

def _load_profile_data(profile_path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in Path(profile_path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_text = key.strip()
        value_text = value.strip().strip('"').strip("'")
        if key_text and value_text:
            data[key_text] = value_text
    return data

def _fill_profile_fields(page: Page, profile_data: dict[str, str]) -> int:
    filled = 0
    mapping = {
        "name": ["input[placeholder*='姓名']", "input[name*='name']"],
        "phone": ["input[placeholder*='手机']", "input[name*='phone']"],
        "email": ["input[placeholder*='邮箱']", "input[name*='email']"],
    }
    for key, selectors in mapping.items():
        if key not in profile_data:
            continue
        value = profile_data[key]
        for selector in selectors:
            loc = page.locator(selector)
            if loc.count() == 0:
                continue
            target = loc.first
            current_value = target.input_value()
            if current_value.strip():
                break
            target.fill(value)
            filled += 1
            break
    return filled

def _click_submit(page: Page, timeout_ms: int) -> bool:
    submit_loc = page.locator("button:has-text('投递'),button:has-text('立即沟通'),a:has-text('投递')")
    if submit_loc.count() == 0:
        return False
    submit_loc.first.click(timeout=timeout_ms)
    page.wait_for_timeout(1500)
    return True

def _detect_submission_outcome(page: Page) -> dict[str, str]:
    success_keywords = ["已投递", "申请成功", "投递成功", "已沟通"]
    for keyword in success_keywords:
        if page.locator(f"text={keyword}").count() > 0:
            return {"status": "success", "detail": f"found keyword: {keyword}"}
    return {"status": "uncertain", "detail": "submit clicked but no definitive success keyword found"}

def _close_modals(page: Page) -> int:
    """Try to close any blocking modals. Returns number of closed modals."""
    closed_count = 0
    close_selectors = [
        ".ant-modal-close:visible",
        ".pc-login-pop-container ._40108gWOOl:visible",  # 登录弹窗关闭按钮 (基于诊断)
        ".ant-modal-confirm-btns button:has-text('知道了'):visible",
        ".ant-modal-confirm-btns button:has-text('OK'):visible",
        ".ant-modal-close-x:visible",
        "button[aria-label='Close']:visible",
    ]
    
    for selector in close_selectors:
        try:
            loc = page.locator(selector)
            if loc.count() > 0:
                loc.first.click(timeout=2000)
                page.wait_for_timeout(500)
                closed_count += 1
        except Exception:
            continue
    return closed_count
