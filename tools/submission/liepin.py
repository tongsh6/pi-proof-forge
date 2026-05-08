from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

from .storage import SubmissionRecorder

UPLOAD_PANEL_TRIGGERS = [
    "button:has-text('上传简历')",
    "a:has-text('上传简历')",
    "button:has-text('上传附件')",
    "a:has-text('上传附件')",
    "button:has-text('更新简历')",
    "a:has-text('更新简历')",
    "button:has-text('重新上传')",
    "a:has-text('重新上传')",
]

APPLY_DIALOG_TRIGGERS = [
    "button:has-text('投递简历')",
    "a:has-text('投递简历')",
    "button:has-text('立即沟通')",
    "a:has-text('立即沟通')",
    "button:has-text('立即申请')",
    "a:has-text('立即申请')",
    "button:has-text('申请职位')",
    "a:has-text('申请职位')",
]


@dataclass
class LiepinSubmissionConfig:
    job_url: str
    resume_path: str
    profile_path: str
    headless: bool
    dry_run: bool
    submit: bool
    output_dir: str
    session_dir: str
    timeout_ms: int


def run_liepin_submission(config: LiepinSubmissionConfig) -> int:
    mode = "dry_run" if config.dry_run else ("submit" if config.submit else "check")
    recorder = SubmissionRecorder(output_root=Path(config.output_dir), platform="liepin", mode=mode)
    recorder.set_meta(
        job_url=config.job_url,
        resume_path=config.resume_path,
        profile_path=config.profile_path,
        headless=config.headless,
    )

    if config.dry_run:
        _record_dry_run(recorder, config)
        recorder.finish(status="success")
        print(f"[DONE] dry-run log: {recorder.log_yaml}")
        return 0

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        recorder.add_step("playwright", "error", "playwright is not installed")
        recorder.finish(status="failed", error="playwright_missing")
        print("[ERROR] playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        print(f"[INFO] log: {recorder.log_yaml}")
        return 3

    session_root = Path(config.session_dir) / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=config.headless,
            )
            try:
                page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
                _ = page.goto(config.job_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
                shot_open = recorder.screenshot_path("open_job_page")
                _ = page.screenshot(path=str(shot_open), full_page=True)
                recorder.add_step("open_job_page", "success", "job page opened", shot_open)

                if _is_error_page(page):
                    snapshot_paths = _dump_dom_snapshots(page, recorder.run_dir / "html")
                    snapshot_text = ",".join(snapshot_paths) if snapshot_paths else "none"
                    recorder.add_step("page_health", "failed", "job page is unavailable or invalid")
                    recorder.add_step("dom_snapshot", "success", f"saved html snapshots: {snapshot_text}")
                    recorder.finish(status="blocked", error="job_page_unavailable")
                    print("[ERROR] job page unavailable. Please verify --job-url points to a valid, accessible job detail page.")
                    print(f"[INFO] log: {recorder.log_yaml}")
                    return 10

                if not _is_logged_in(page):
                    shot_login = recorder.screenshot_path("login_required")
                    _ = page.screenshot(path=str(shot_login), full_page=True)
                    recorder.add_step("login_check", "failed", "login required", shot_login)
                    recorder.finish(status="blocked", error="login_required")
                    print("[ERROR] login required. Please login once with the same session dir and retry.")
                    print(f"[INFO] log: {recorder.log_yaml}")
                    return 4
                recorder.add_step("login_check", "success", "login session valid")

                page_mode = _detect_page_mode(page)
                recorder.add_step("page_mode", "success", f"detected mode: {page_mode}")

                shot_upload_prepare = recorder.screenshot_path("upload_prepare")
                _ = page.screenshot(path=str(shot_upload_prepare), full_page=True)
                recorder.add_step("upload_prepare", "success", "captured before upload attempts", shot_upload_prepare)

                upload_ok, upload_detail = _upload_resume(page, config.resume_path, config.timeout_ms, page_mode)
                shot_upload = recorder.screenshot_path("upload_resume")
                _ = page.screenshot(path=str(shot_upload), full_page=True)
                if not upload_ok:
                    snapshot_paths = _dump_dom_snapshots(page, recorder.run_dir / "html")
                    snapshot_text = ",".join(snapshot_paths) if snapshot_paths else "none"
                    recorder.add_step("upload_resume", "failed", upload_detail, shot_upload)
                    recorder.add_step("dom_snapshot", "success", f"saved html snapshots: {snapshot_text}")
                    recorder.finish(status="failed", error="upload_input_not_found")
                    print(f"[INFO] log: {recorder.log_yaml}")
                    return 5
                recorder.add_step("upload_resume", "success", upload_detail, shot_upload)

                profile_data = _load_profile_data(config.profile_path)
                fill_count = _fill_profile_fields(page, profile_data)
                shot_fill = recorder.screenshot_path("fill_profile")
                _ = page.screenshot(path=str(shot_fill), full_page=True)
                recorder.add_step("fill_profile", "success", f"filled fields: {fill_count}", shot_fill)

                if not config.submit:
                    recorder.add_step("submit", "skipped", "submit not enabled")
                    recorder.finish(status="success")
                    print(f"[DONE] check-mode log: {recorder.log_yaml}")
                    return 0

                click_ok = _click_submit(page, config.timeout_ms)
                shot_submit = recorder.screenshot_path("submit_result")
                _ = page.screenshot(path=str(shot_submit), full_page=True)
                if not click_ok:
                    recorder.add_step("submit", "failed", "submit button not found", shot_submit)
                    recorder.finish(status="failed", error="submit_button_not_found")
                    print(f"[INFO] log: {recorder.log_yaml}")
                    return 6

                outcome = _detect_submission_outcome(page)
                recorder.add_step("submit", outcome["status"], outcome["detail"], shot_submit)
                final_status = "success" if outcome["status"] == "success" else "uncertain"
                recorder.finish(status=final_status, error="" if final_status == "success" else "submission_uncertain")
                print(f"[DONE] submit log: {recorder.log_yaml}")
                return 0 if final_status == "success" else 7
            finally:
                browser_context.close()
    except PlaywrightTimeoutError:
        recorder.add_step("runtime", "failed", "timeout during page operation")
        recorder.finish(status="failed", error="timeout")
        print(f"[INFO] log: {recorder.log_yaml}")
        return 8
    except Exception as exc:
        recorder.add_step("runtime", "failed", f"unexpected error: {exc}")
        recorder.finish(status="failed", error="unexpected_error")
        print(f"[INFO] log: {recorder.log_yaml}")
        return 9


def _record_dry_run(recorder: SubmissionRecorder, config: LiepinSubmissionConfig) -> None:
    recorder.add_step("validate_login_session", "planned", f"session_dir={config.session_dir}")
    recorder.add_step("open_job_page", "planned", config.job_url)
    recorder.add_step("upload_resume", "planned", config.resume_path)
    recorder.add_step("fill_profile", "planned", config.profile_path)
    recorder.add_step("submit", "planned", "submit disabled in dry-run")


def _is_logged_in(page: Page) -> bool:
    current_url = page.url.lower()
    if "passport" in current_url or "login" in current_url:
        return False

    login_loc = page.locator("a:has-text('登录'),button:has-text('登录')")
    if login_loc.count() > 0 and "liepin.com/job" not in current_url:
        return False

    job_action = page.locator("button:has-text('投递'),button:has-text('立即沟通'),a:has-text('投递')")
    return job_action.count() > 0 or "liepin.com/job" in current_url


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
