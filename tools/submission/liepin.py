from __future__ import annotations

import json
import re
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
    "button:has-text('聊一聊')",
    "a:has-text('聊一聊')",
    "button:has-text('立即申请')",
    "a:has-text('立即申请')",
    "button:has-text('申请职位')",
    "a:has-text('申请职位')",
]

MAIN_CHAT_SELECTOR = (
    "a[data-tlg-elem-id='c_pc_job_detail_chat_btn'],"
    "a[data-tlg-elem-id='c_pc_job_detail_recruiter_chat_btn']"
)
RECOMMENDED_CHAT_SELECTOR = "a[data-tlg-elem-id='c_pc_job_detail_like_chat_btn']"


@dataclass(frozen=True)
class TargetVerification:
    ok: bool
    reason: str = ""
    url_job_id: str = ""
    dom_jobid: str = ""
    params_jobid: str = ""
    recruiter_name: str = ""
    recruiter_id: str = ""
    matched_count: int = 0


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
    browser_channel: str = "chrome"
    rate_limit_max_per_batch: int = 5
    rate_limit_cooldown_seconds: int = 900
    rate_limit_daily_limit: int = 30


def run_liepin_submission(config: LiepinSubmissionConfig) -> int:
    mode = "dry_run" if config.dry_run else ("submit" if config.submit else "check")
    recorder = SubmissionRecorder(output_root=Path(config.output_dir), platform="liepin", mode=mode)
    recorder.set_meta(
        job_url=config.job_url,
        resume_path=config.resume_path,
        profile_path=config.profile_path,
        headless=config.headless,
        browser_channel=config.browser_channel,
    )

    if config.dry_run:
        _record_dry_run(recorder, config)
        recorder.finish(status="success")
        print(f"[DONE] dry-run log: {recorder.log_yaml}")
        return 0

    rate_limit_decision = _check_rate_limit(config)
    if not rate_limit_decision.allowed:
        recorder.add_step(
            "rate_limit",
            "blocked",
            (
                f"{rate_limit_decision.reason}; "
                f"wait_seconds={rate_limit_decision.wait_seconds}; "
                f"batch_count={rate_limit_decision.batch_count}; "
                f"daily_count={rate_limit_decision.daily_count}"
            ),
        )
        recorder.finish(status="blocked", error=rate_limit_decision.reason)
        print(f"[INFO] log: {recorder.log_yaml}")
        return 14
    recorder.add_step(
        "rate_limit",
        "success",
        (
            f"batch_count={rate_limit_decision.batch_count}; "
            f"daily_count={rate_limit_decision.daily_count}"
        ),
    )

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        recorder.add_step("playwright", "error", "playwright is not installed")
        recorder.finish(status="failed", error="playwright_missing")
        print("[ERROR] playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        print(f"[INFO] log: {recorder.log_yaml}")
        return 3

    session_root = Path(config.session_dir) / "liepin" / "session" / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)

    try:
        with _launch_liepin_context(config, session_root, sync_playwright) as browser_context:
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            _ = page.goto(config.job_url, wait_until="networkidle", timeout=config.timeout_ms)
            _human_browsing_pause(page)
            page.wait_for_timeout(3000)  # Wait for JS and modals to settle

            # Check for security page redirect
            if "安全中心" in page.title() or "safe.liepin" in page.url.lower():
                recorder.add_step("security_check", "failed", "redirected to security page")
                recorder.finish(status="blocked", error="security_redirect")
                return 11

            # Dismiss initial blockers (like app download prompts)
            _close_modals(page)

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

            verification = _verify_main_chat_target(page, config.job_url)
            if not verification.ok:
                snapshot_paths = _dump_dom_snapshots(page, recorder.run_dir / "html")
                snapshot_text = ",".join(snapshot_paths) if snapshot_paths else "none"
                shot_target = recorder.screenshot_path("target_verify")
                _ = page.screenshot(path=str(shot_target), full_page=True)
                recorder.add_step("target_verify", "failed", verification.reason, shot_target)
                recorder.add_step("dom_snapshot", "success", f"saved html snapshots: {snapshot_text}")
                recorder.finish(status="failed", error=verification.reason or "target_verify_failed")
                print(f"[INFO] log: {recorder.log_yaml}")
                return 12
            recorder.add_step(
                "target_verify",
                "success",
                (
                    f"url_job_id={verification.url_job_id}; "
                    f"dom_jobid={verification.dom_jobid}; "
                    f"params_jobid={verification.params_jobid}; "
                    f"recruiter={verification.recruiter_name}"
                ),
            )

            chat_ok, chat_detail = _send_resume_via_chat(
                page,
                config.job_url,
                config.timeout_ms,
                submit=config.submit,
            )
            shot_chat = recorder.screenshot_path("chat_send_resume")
            _ = page.screenshot(path=str(shot_chat), full_page=True)
            if not chat_ok:
                snapshot_paths = _dump_dom_snapshots(page, recorder.run_dir / "html")
                snapshot_text = ",".join(snapshot_paths) if snapshot_paths else "none"
                recorder.add_step("chat_send_resume", "failed", chat_detail, shot_chat)
                recorder.add_step("dom_snapshot", "success", f"saved html snapshots: {snapshot_text}")
                recorder.finish(status="failed", error=chat_detail)
                print(f"[INFO] log: {recorder.log_yaml}")
                return 13
            recorder.add_step("chat_send_resume", "success", chat_detail, shot_chat)

            if not config.submit:
                recorder.add_step("submit", "skipped", "submit not enabled; stopped before final confirm")
                recorder.finish(status="success")
                print(f"[DONE] check-mode log: {recorder.log_yaml}")
                return 0

            outcome = _detect_submission_outcome(page)
            recorder.add_step("submit", outcome["status"], outcome["detail"], shot_chat)
            final_status = "success" if outcome["status"] == "success" else "uncertain"
            recorder.finish(status=final_status, error="" if final_status == "success" else "submission_uncertain")
            print(f"[DONE] submit log: {recorder.log_yaml}")
            return 0 if final_status == "success" else 7
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
    recorder.add_step(
        "rate_limit",
        "planned",
        (
            f"max_per_batch={config.rate_limit_max_per_batch}; "
            f"cooldown_seconds={config.rate_limit_cooldown_seconds}; "
            f"daily_limit={config.rate_limit_daily_limit}"
        ),
    )
    recorder.add_step("open_job_page", "planned", config.job_url)
    recorder.add_step("target_verify", "planned", "verify main job chat button jobId")
    recorder.add_step("chat_send_resume", "planned", "聊一聊 -> 发简历 -> confirmation dialog")
    recorder.add_step("submit", "planned", "final confirm only when submit is enabled")


def _browser_context_options(config: LiepinSubmissionConfig, session_root: Path) -> dict[str, object]:
    options: dict[str, object] = {
        "user_data_dir": str(session_root),
        "headless": config.headless,
        "viewport": {"width": 1440, "height": 900},
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    if config.browser_channel:
        options["channel"] = config.browser_channel
    return options


def _check_rate_limit(config: LiepinSubmissionConfig):
    from tools.submission.rate_limit import RateLimitConfig, SubmissionRateLimiter

    limiter = SubmissionRateLimiter(Path(config.output_dir) / "liepin_rate_limit.json")
    return limiter.check_and_record(
        RateLimitConfig(
            max_per_batch=config.rate_limit_max_per_batch,
            cooldown_seconds=config.rate_limit_cooldown_seconds,
            daily_limit=config.rate_limit_daily_limit,
        )
    )


def _launch_liepin_context(
    config: LiepinSubmissionConfig,
    session_root: Path,
    sync_playwright_factory: object,
):
    try:
        from tools.submission._browser import make_context
    except Exception:
        make_context = None

    if make_context is not None:
        return make_context(
            session_dir=session_root,
            headless=config.headless,
            channel=config.browser_channel,
        )

    class _RawPlaywrightContext:
        def __enter__(self):
            self._playwright_cm = sync_playwright_factory()
            playwright = self._playwright_cm.__enter__()
            self._context = playwright.chromium.launch_persistent_context(
                **_browser_context_options(config, session_root),
            )
            return self._context

        def __exit__(self, exc_type, exc, tb):
            try:
                self._context.close()
            finally:
                self._playwright_cm.__exit__(exc_type, exc, tb)
            return False

    return _RawPlaywrightContext()


def _human_browsing_pause(page: Page) -> None:
    try:
        from tools.submission._browser import human_long_pause, human_mouse_jiggle, human_scroll
    except Exception:
        return

    human_mouse_jiggle(page)
    human_scroll(page, steps=2)
    human_long_pause(3.0, 8.0)


def _is_logged_in(page: Page) -> bool:
    current_url = page.url.lower()
    if "passport" in current_url or "login" in current_url:
        return False

    # Check for login modal (even if indicators exist in background)
    login_modal = page.locator(".pc-login-pop-container:visible, .ant-modal-root:has-text('登录'):visible")
    if login_modal.count() > 0:
        return False

    # Positive check: elements that only appear when logged in
    # These are highly reliable indicators of a valid session
    user_indicators = page.locator(
        "[data-selector='chat-chat']:visible, "
        "[data-selector='c-logout']:visible, "
        ".recruiter-info-box:visible, "
        ".nav-user-item:visible"
    )
    if user_indicators.count() > 0:
        return True

    # Negative check: If no positive indicators, look for visible login prompts
    inline_login = page.locator("[data-selector='inline-login']:visible, .inline-login-container:visible")
    if inline_login.count() > 0:
        return False

    login_btn = page.locator("a:has-text('登录'):visible, button:has-text('登录/注册'):visible")
    if login_btn.count() > 0:
        return False

    # Fallback: if we are on a job page and see action buttons, we are likely logged in
    job_action = page.locator("button:has-text('投递简历'):visible, button:has-text('立即沟通'):visible, button:has-text('聊一聊'):visible")
    return job_action.count() > 0 or "liepin.com/job" in current_url


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


def _send_resume_via_chat(
    page: Page,
    job_url: str,
    timeout_ms: int,
    submit: bool,
) -> tuple[bool, str]:
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

    if not submit:
        return True, "chat_send_resume_ready"

    ok, detail = _click_confirm_send_resume(page, timeout_ms)
    return (True, f"submitted_via_{detail}") if ok else (False, detail)


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
