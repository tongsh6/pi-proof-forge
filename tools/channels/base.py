from __future__ import annotations

from dataclasses import dataclass

from tools.domain.protocols import DeliveryChannel as _DeliveryChannel
from tools.domain.result import Err, Result
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


# Re-export with specific request type
DeliveryChannel = _DeliveryChannel


def deliver_with_fallback(
    request: DeliveryRequest,
    channels: list[DeliveryChannel],
) -> Result[DeliveryResult, ChannelFailure]:
    # 保留兼容入口名；未建立跨渠道授权契约前，只执行一次明确目标通道。
    for channel in channels:
        if channel.channel_id == request.channel:
            return channel.deliver(request)
    return Err(ChannelFailure(
        channel_id=request.channel or "none", reason="no_channel",
        details="未配置与目标平台匹配的投递通道",
    ))
