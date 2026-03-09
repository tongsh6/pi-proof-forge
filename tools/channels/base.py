from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tools.domain.result import Result
from tools.domain.value_objects import ChannelFailure, DeliveryResult


@dataclass(frozen=True)
class DeliveryRequest:
    run_id: str
    candidate_id: str
    channel: str
    resume_path: str
    job_url: str
    dry_run: bool = True
    metadata: dict[str, object] | None = None


class DeliveryChannel(Protocol):
    channel_id: str

    def deliver(
        self, request: DeliveryRequest
    ) -> Result[DeliveryResult, ChannelFailure]: ...


def deliver_with_fallback(
    request: DeliveryRequest,
    channels: list[DeliveryChannel],
) -> Result[DeliveryResult, ChannelFailure]:
    last_error: ChannelFailure | None = None
    for channel in channels:
        result = channel.deliver(request)
        from tools.domain.result import Err, Ok

        if isinstance(result, Ok):
            return result
        if isinstance(result, Err):
            last_error = result.error
            if not _is_retryable(last_error):
                return result

    from tools.domain.result import Err

    if last_error is None:
        return Err(
            ChannelFailure(channel_id="none", reason="no_channel", details="no channel")
        )
    return Err(last_error)


def _is_retryable(failure: ChannelFailure) -> bool:
    lowered = failure.reason.casefold()
    return lowered in {"timeout", "network_error", "temporary_failure", "retryable"}
