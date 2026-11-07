"""猎聘投递主流程：配置、频控、浏览器创建与投递编排。

页内交互（目标核验/上传/聊天/截图）在 submission/liepin_browser.py，类型与
选择器常量在 submission/liepin_types.py；本模块保留同名符号 re-export，
既有 import 与测试 patch 不受影响。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

from .liepin_browser import (
    _capture_browser_screenshot,
    _click_confirm_send_resume,
    _click_submit,
    _close_modals,
    _detect_page_mode,
    _detect_submission_outcome,
    _dump_dom_snapshots,
    _external_l3_mode,
    _extract_liepin_job_id,
    _fill_profile_fields,
    _has_any_selector_in_page_and_frames,
    _has_any_selector_in_scope,
    _is_error_page,
    _load_profile_data,
    _open_apply_dialog,
    _open_upload_panel,
    _plan_upload_phases,
    _record_dom_snapshot_step,
    _run_upload_phase,
    _send_resume_via_chat,
    _target_verification_detail,
    _upload_in_page_and_frames,
    _upload_in_scope,
    _upload_resume,
    _upload_via_file_chooser,
    _verify_main_chat_target,
    _verify_submit_safety,
)
from .liepin_types import (
    APPLY_DIALOG_TRIGGERS,
    MAIN_CHAT_SELECTOR,
    RECOMMENDED_CHAT_SELECTOR,
    UPLOAD_PANEL_TRIGGERS,
    LiepinSubmissionConfig,
    TargetVerification,
)
from .storage import SubmissionRecorder


def run_liepin_submission(
    config: LiepinSubmissionConfig, *, recorder: SubmissionRecorder | None = None
) -> int:
    mode = "dry_run" if config.dry_run else ("submit" if config.submit else "check")
    if recorder is None:
        recorder = SubmissionRecorder(output_root=Path(config.output_dir), platform="liepin", mode=mode)
    recorder.set_meta(
        job_url=config.job_url,
        resume_path=config.resume_path,
        profile_path=config.profile_path,
        headless=config.headless,
        browser_channel=config.browser_channel,
        external_l3_validation_run_id=config.external_l3_validation_run_id,
        external_l3_validation_path=config.external_l3_validation_path,
        redaction_values=[
            config.confirm_submit_job_id,
            config.confirm_submit_recruiter,
            _extract_liepin_job_id(config.job_url) or "",
        ],
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

    session_root = Path(config.session_profile_path) if config.session_profile_path else Path(config.session_dir) / "liepin" / "session" / "liepin"
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

            shot_open = _capture_browser_screenshot(
                page,
                recorder,
                config,
                "open_job_page",
            )
            recorder.add_step("open_job_page", "success", "job page opened", shot_open)

            if _is_error_page(page):
                recorder.add_step("page_health", "failed", "job page is unavailable or invalid")
                _record_dom_snapshot_step(recorder, config, page)
                recorder.finish(status="blocked", error="job_page_unavailable")
                print("[ERROR] job page unavailable. Please verify --job-url points to a valid, accessible job detail page.")
                print(f"[INFO] log: {recorder.log_yaml}")
                return 10

            if not _is_logged_in(page):
                shot_login = _capture_browser_screenshot(
                    page,
                    recorder,
                    config,
                    "login_required",
                )
                recorder.add_step("login_check", "failed", "login required", shot_login)
                recorder.finish(status="blocked", error="login_required")
                print("[ERROR] login required. Please login once with the same session dir and retry.")
                print(f"[INFO] log: {recorder.log_yaml}")
                return 4
            recorder.add_step("login_check", "success", "login session valid")

            verification = _verify_main_chat_target(page, config.job_url)
            if not verification.ok:
                shot_target = _capture_browser_screenshot(
                    page,
                    recorder,
                    config,
                    "target_verify",
                )
                recorder.add_step("target_verify", "failed", verification.reason, shot_target)
                _record_dom_snapshot_step(recorder, config, page)
                recorder.finish(status="failed", error=verification.reason or "target_verify_failed")
                print(f"[INFO] log: {recorder.log_yaml}")
                return 12
            recorder.add_step(
                "target_verify",
                "success",
                _target_verification_detail(config, verification),
            )

            if config.submit:
                safety_ok, safety_detail = _verify_submit_safety(config, verification)
                if not safety_ok:
                    recorder.add_step("submit_safety", "blocked", safety_detail)
                    recorder.finish(status="blocked", error=safety_detail)
                    print(f"[INFO] log: {recorder.log_yaml}")
                    return 15
                recorder.add_step("submit_safety", "success", safety_detail)

            chat_ok, chat_detail = _send_resume_via_chat(
                page,
                config.job_url,
                config.timeout_ms,
                submit=config.submit,
            )
            shot_chat = _capture_browser_screenshot(
                page,
                recorder,
                config,
                "chat_send_resume",
            )
            if not chat_ok:
                binding_blocked = chat_detail == "resume_attachment_binding_unverified"
                recorder.add_step("chat_send_resume", "blocked" if binding_blocked else "failed", chat_detail, shot_chat)
                _record_dom_snapshot_step(recorder, config, page)
                recorder.finish(status="blocked" if binding_blocked else "failed", error=chat_detail)
                print(f"[INFO] log: {recorder.log_yaml}")
                return 16 if binding_blocked else 13
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

def _is_logged_in(page: object) -> bool:
    from tools.infra.browser.liepin_session import observe_login_page
    return bool(observe_login_page(page)["login_signals"].get("authenticated_user_visible"))
