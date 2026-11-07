"""Agent 编排的投递执行辅助：平台路由、门禁引擎、候选排序与单次投递。

从 orchestration/agent_loop.py 拆出；agent_loop 保留同名符号 re-export，
供 Composer/审批链路复用。
"""
from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tools.channels.base import DeliveryChannel, DeliveryRequest, deliver_with_fallback
from tools.config.fragments import PolicyConfig
from tools.domain.models import ResumeOutput
from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import Candidate, ChannelFailure, DeliveryResult


def _delivery_platform(candidate: Candidate) -> Result[str, ChannelFailure]:
    """使用显式平台或可信 HTTPS 域名，业务方向不参与渠道选择。"""
    platform_domains = {
        "liepin": "liepin.com",
        "boss": "zhipin.com",
        "zhilian": "zhaopin.com",
        "51job": "51job.com",
    }
    platform = candidate.platform
    try:
        if "\\" in candidate.job_url or any(char.isspace() for char in candidate.job_url):
            raise ValueError("invalid_job_url")
        url = urlsplit(candidate.job_url)
        if (
            url.scheme != "https" or not url.hostname
            or url.username is not None or url.password is not None
            or url.port not in (None, 443)
        ):
            raise ValueError("invalid_job_url")
    except ValueError:
        return Err(ChannelFailure(
            channel_id=platform or "none", reason="invalid_job_url",
            details="岗位链接须为不含认证信息的 HTTPS 平台地址",
        ))

    url_platform = next((
        name for name, domain in platform_domains.items()
        if url.hostname == domain or url.hostname.endswith("." + domain)
    ), "")
    if platform and (url_platform or platform in platform_domains) and platform != url_platform:
        return Err(ChannelFailure(
            channel_id=platform, reason="platform_url_mismatch",
            details="候选平台与岗位链接所属平台不一致",
        ))
    if not platform:
        platform = url_platform
    if not platform:
        return Err(ChannelFailure(
            channel_id="none", reason="unknown_platform",
            details="岗位未声明平台，且链接不属于已知招聘平台",
        ))
    return Ok(platform)

def _gate_engine_for_round(
    policy: PolicyConfig, run_id: str, round_index: int
) -> object:
    from tools.orchestration.gate_engine import GateEngine
    return GateEngine(policy, run_id, round_index)

def _rank_candidate_batch(
    candidates: Sequence[Candidate],
    selected_candidate_ids: set[str],
) -> list[Candidate]:
    remaining = [
        candidate for candidate in candidates
        if candidate.candidate_id not in selected_candidate_ids
    ]
    return sorted(
        remaining,
        key=lambda candidate: (-candidate.confidence, candidate.candidate_id),
    )

def run_delivery(
    *,
    run_id: str,
    candidate: Candidate,
    round_index: int,
    resume: ResumeOutput,
    channels: Sequence[DeliveryChannel],
    append_event: Callable[..., None],
    logger: Any,
) -> Result[DeliveryResult, ChannelFailure]:
    """执行一次受控投递：平台路由 → 通道检查 → 导出并绑定 PDF → 单次投递。"""
    route = _delivery_platform(candidate)
    if isinstance(route, Err):
        return route
    platform = route.value
    if candidate.source == "liepin_official":
        return Err(ChannelFailure(
            channel_id=platform, reason="official_delivery_contract_unverified",
            details="官方投递的发送版本与回执契约尚未验证，禁止转入旧浏览器投递",
        ))

    if not channels:
        from tools.channels.email import EmailChannel
        from tools.channels.liepin import LiepinChannel
        resolved: list[DeliveryChannel] = [LiepinChannel(), EmailChannel()]
    else:
        resolved = list(channels)

    if not any(channel.channel_id == platform for channel in resolved):
        return Err(ChannelFailure(
            channel_id=platform, reason="no_channel",
            details="未配置与目标平台匹配的投递通道",
        ))

    from tools.engines.generation.exporter import ResumeExporter
    from tools.infra.export.pdf_exporter import markdown_to_pdf

    # 每次尝试保留独立附件，重试或同名版本不能覆盖前次文件。
    try:
        output_root = Path("outputs") / "agent_runs" / run_id / "deliveries"
        output_root.mkdir(parents=True, exist_ok=True)
        attempt_dir = Path(tempfile.mkdtemp(prefix=f"round-{round_index}-", dir=output_root))
        markdown_path = ResumeExporter().export_markdown(resume, str(attempt_dir))
        pdf_path = markdown_path.with_suffix(".pdf")
        markdown_to_pdf(markdown_path, pdf_path)
        metadata = {
            "round": round_index,
            "platform": platform,
            "platform_job_id": candidate.platform_job_id,
            "platform_job_type": candidate.platform_job_type,
            "job_profile_id": candidate.job_profile_id,
            "jd_status": candidate.jd_status,
            "source": candidate.source,
            "source_jd_sha256": candidate.source_jd_sha256,
            "resume_version": resume.version,
            "resume_markdown_path": str(markdown_path.resolve()),
            "resume_markdown_sha256": hashlib.sha256(markdown_path.read_bytes()).hexdigest(),
            "resume_pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        }
        resume_path = str(pdf_path.resolve())
        append_event("resume_exported", round_index, {
            **metadata, "resume_path": resume_path, "candidate_id": candidate.candidate_id,
        })
    except (OSError, RuntimeError) as exc:
        logger.warning("agent_loop.resume_pdf_export_failed", error=str(exc))
        return Err(ChannelFailure(
            channel_id="none", reason="resume_pdf_export_failed", details=str(exc),
        ))

    request = DeliveryRequest(
        run_id=run_id,
        candidate_id=candidate.candidate_id,
        channel=platform,
        resume_path=resume_path,
        job_url=candidate.job_url,
        dry_run=False,
        metadata=metadata,
    )
    from tools.orchestration.approved_delivery import deliver_once
    return deliver_once(request, resolved, source=candidate.source)


def deliver_mock(run_id: str, round_index: int):
    """简化模式的模拟投递（不触碰真实平台）。"""
    from tools.channels.email import EmailChannel
    from tools.channels.liepin import LiepinChannel

    request = DeliveryRequest(
        run_id=run_id,
        candidate_id=f"candidate-{round_index}",
        channel="liepin",
        resume_path="outputs/resume_latest.pdf",
        job_url="https://example.com/job",
        dry_run=True,
        metadata={"round": round_index},
    )
    return deliver_with_fallback(request, [LiepinChannel(), EmailChannel()])
