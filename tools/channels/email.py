from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from tools.channels.base import DeliveryRequest
from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import ChannelFailure, DeliveryResult


class EmailChannel:
    channel_id = "email"

    def deliver(
        self, request: DeliveryRequest
    ) -> Result[DeliveryResult, ChannelFailure]:
        if request.dry_run:
            return Ok(
                DeliveryResult(
                    channel_id=self.channel_id,
                    success=True,
                    submission_id=f"dry-email-{request.candidate_id}",
                    message="dry-run",
                )
            )

        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASS", "")
        host = os.getenv("SMTP_HOST", "smtp.example.com")
        to_addr = os.getenv("SMTP_TO", user)

        if not user or not password or not to_addr:
            return Err(
                ChannelFailure(
                    channel_id=self.channel_id,
                    reason="missing_smtp_credentials",
                    details="SMTP_USER/SMTP_PASS/SMTP_TO required",
                )
            )

        message = EmailMessage()
        message["Subject"] = "PiProofForge Delivery"
        message["From"] = user
        message["To"] = to_addr
        message.set_content(
            f"run_id={request.run_id}\ncandidate_id={request.candidate_id}\njob_url={request.job_url}"
        )

        try:
            with smtplib.SMTP(host, timeout=10) as client:
                client.starttls()
                client.login(user, password)
                client.send_message(message)
        except Exception as exc:
            return Err(
                ChannelFailure(
                    channel_id=self.channel_id,
                    reason="retryable",
                    details=str(exc),
                )
            )

        return Ok(
            DeliveryResult(
                channel_id=self.channel_id,
                success=True,
                submission_id=f"email-{request.candidate_id}",
                message="submitted",
            )
        )
