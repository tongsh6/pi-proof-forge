from __future__ import annotations

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

        return Ok(
            DeliveryResult(
                channel_id=self.channel_id,
                success=True,
                submission_id=f"lp-{request.candidate_id}",
                message="submitted",
            )
        )
