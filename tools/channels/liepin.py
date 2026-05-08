from __future__ import annotations

import os
from pathlib import Path

from tools.channels.base import DeliveryRequest
from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import ChannelFailure, DeliveryResult


class LiepinChannel:
    channel_id = "liepin"

    def deliver(
        self, request: DeliveryRequest
    ) -> Result[DeliveryResult, ChannelFailure]:
        if request.dry_run:
            return Ok(
                DeliveryResult(
                    channel_id=self.channel_id,
                    success=True,
                    submission_id=f"dry-{request.candidate_id}",
                    message="dry-run",
                )
            )

        if not request.job_url.startswith("http"):
            return Err(
                ChannelFailure(
                    channel_id=self.channel_id,
                    reason="invalid_job_url",
                    details=request.job_url,
                )
            )

        # Check if playwright is available; gracefully degrade if not
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return Ok(
                DeliveryResult(
                    channel_id=self.channel_id,
                    success=True,
                    submission_id=f"sim-{request.candidate_id}",
                    message="simulated: playwright not installed",
                )
            )

        # Delegate to the real Playwright-based submission module
        from tools.submission.liepin import (
            LiepinSubmissionConfig,
            run_liepin_submission,
        )

        output_dir = os.path.join(
            os.getenv("PPF_OUTPUT_DIR", "outputs/submissions/liepin"),
            request.run_id,
        )
        session_dir = os.path.join(
            os.getenv("PPF_SESSION_DIR", "outputs/sessions"),
            request.run_id,
        )
        profile_path = request.metadata.get("profile_path", "profiles/candidate_profile.yaml") if request.metadata else "profiles/candidate_profile.yaml"
        headless = os.getenv("PPF_HEADLESS", "1") == "1"
        submit = os.getenv("PPF_SUBMIT_ENABLED", "0") == "1"
        browser_channel = os.getenv("PPF_BROWSER_CHANNEL", "chrome")

        config = LiepinSubmissionConfig(
            job_url=request.job_url,
            resume_path=request.resume_path,
            profile_path=str(profile_path),
            headless=headless,
            dry_run=False,
            submit=submit,
            output_dir=output_dir,
            session_dir=session_dir,
            timeout_ms=30_000,
            browser_channel=browser_channel,
        )

        exit_code = run_liepin_submission(config)
        if exit_code == 0:
            return Ok(
                DeliveryResult(
                    channel_id=self.channel_id,
                    success=True,
                    submission_id=f"lp-{request.candidate_id}",
                    message=f"submitted; log_dir={output_dir}",
                )
            )

        error_messages = {
            3: ("playwright_missing", "playwright is not installed"),
            4: ("login_required", "login session expired or missing"),
            5: ("upload_input_not_found", "resume upload input not found on page"),
            6: ("submit_button_not_found", "submit button not found on page"),
            7: ("submission_uncertain", "submit clicked but outcome uncertain"),
            8: ("timeout", "timeout during page operation"),
            9: ("unexpected_error", "unexpected error during submission"),
            10: ("job_page_unavailable", "job page is unavailable or invalid"),
        }
        reason, detail = error_messages.get(exit_code, ("unknown_error", f"exit_code={exit_code}"))
        return Err(ChannelFailure(channel_id=self.channel_id, reason=reason, details=detail))
