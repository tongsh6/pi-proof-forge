from __future__ import annotations

import datetime
import hashlib
import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tools.channels.base import DeliveryChannel, DeliveryRequest, deliver_with_fallback
from tools.config.fragments import PolicyConfig
from tools.domain.events import RunEvent
from tools.domain.models import EvidenceCard, JobProfile, MatchingReport, ResumeOutput, Scorecard
from tools.domain.result import Err, Ok, Result
from tools.domain.run_state import RunState
from tools.domain.value_objects import Candidate, ChannelFailure, DeliveryResult, GateDecision, GateFailure
from tools.infra.logging import make_logger


@dataclass(frozen=True)
class AgentLoopResult:
    run_id: str
    status: str
    rounds_completed: int


class AgentLoop:
    def __init__(
        self,
        policy: PolicyConfig,
        run_id: str,
        dry_run: bool = False,
        run_store: object | None = None,
        *,
        matching_engine: object | None = None,
        generation_engine: object | None = None,
        evaluation_engine: object | None = None,
        discovery_engine: object | None = None,
        gate_engine: object | None = None,
        review_stage: object | None = None,
        state_machine: object | None = None,
        channels: Sequence[DeliveryChannel] | None = None,
        evidence_cards: Sequence[EvidenceCard] | None = None,
        job_profile: JobProfile | None = None,
        candidates: Sequence[Candidate] | None = None,
    ) -> None:
        self._policy = policy
        self._run_id = run_id
        self._dry_run = dry_run
        self._run_store = run_store
        self._logger = make_logger(run_id)

        self._matching = matching_engine
        self._generation = generation_engine
        self._evaluation = evaluation_engine
        self._discovery = discovery_engine
        self._gate = gate_engine
        self._review = review_stage
        self._state_machine = state_machine
        self._channels = tuple(channels) if channels else ()
        self._evidence_cards = tuple(evidence_cards) if evidence_cards else ()
        self._job_profile = job_profile
        self._candidates = tuple(candidates) if candidates else ()

        self._has_full_pipeline = (
            self._matching is not None
            and self._generation is not None
            and self._evaluation is not None
        )

    def run(self) -> AgentLoopResult:
        if self._has_full_pipeline:
            return self._run_full_pipeline()
        return self._run_simplified()

    # ------------------------------------------------------------------
    # simplified loop (backward compat — no engines injected)
    # ------------------------------------------------------------------

    def _run_simplified(self) -> AgentLoopResult:
        rounds_completed = 0
        deliveries_completed = 0
        self._logger.info("agent_loop.start", dry_run=self._dry_run, state="INIT")
        self._append_event("INIT", round_index=0, payload={"dry_run": self._dry_run})

        for round_index in range(self._policy.max_rounds):
            self._logger.info("agent_loop.round", round=round_index, state="DISCOVER")
            self._append_event("DISCOVER", round_index=round_index, payload={})
            rounds_completed += 1

            if self._dry_run:
                self._logger.info(
                    "agent_loop.dry_run_stop", round=round_index, state="DONE"
                )
                self._append_event(
                    "DONE", round_index=round_index, payload={"dry_run": True}
                )
                return AgentLoopResult(
                    run_id=self._run_id,
                    status="DRY_RUN_COMPLETE",
                    rounds_completed=rounds_completed,
                )

            delivery = self._deliver_mock(round_index)
            if isinstance(delivery, Err):
                self._logger.warning(
                    "agent_loop.channel_error",
                    round=round_index,
                    channel=delivery.error.channel_id,
                    reason=delivery.error.reason,
                )
                self._append_event(
                    "channel_error",
                    round_index=round_index,
                    payload={
                        "channel_id": delivery.error.channel_id,
                        "reason": delivery.error.reason,
                    },
                )
                self._append_event("LEARN", round_index=round_index, payload={})
                continue

            if isinstance(delivery, Ok):
                self._append_event(
                    "DELIVER",
                    round_index=round_index,
                    payload={"channel": delivery.value.channel_id, "success": delivery.value.success},
                )
                if delivery.value.success:
                    deliveries_completed += 1
                if (
                    self._policy.max_deliveries > 0
                    and deliveries_completed >= self._policy.max_deliveries
                ):
                    self._append_event(
                        "DONE",
                        round_index=round_index,
                        payload={
                            "dry_run": False,
                            "stop_reason": "max_deliveries",
                            "deliveries_completed": deliveries_completed,
                        },
                    )
                    return AgentLoopResult(
                        run_id=self._run_id,
                        status="DONE",
                        rounds_completed=rounds_completed,
                    )

            self._append_event("LEARN", round_index=round_index, payload={})

        self._append_event(
            "DONE",
            round_index=max(self._policy.max_rounds - 1, 0),
            payload={"dry_run": False},
        )
        return AgentLoopResult(
            run_id=self._run_id,
            status="DONE",
            rounds_completed=rounds_completed,
        )

    def _deliver_mock(self, round_index: int):
        from tools.channels.email import EmailChannel
        from tools.channels.liepin import LiepinChannel

        request = DeliveryRequest(
            run_id=self._run_id,
            candidate_id=f"candidate-{round_index}",
            channel="liepin",
            resume_path="outputs/resume_latest.pdf",
            job_url="https://example.com/job",
            dry_run=True,
            metadata={"round": round_index},
        )
        return deliver_with_fallback(request, [LiepinChannel(), EmailChannel()])

    # ------------------------------------------------------------------
    # full pipeline (engines injected via Composer)
    # ------------------------------------------------------------------

    def _run_full_pipeline(self) -> AgentLoopResult:
        rounds_completed = 0
        deliveries_completed = 0
        simulated_deliveries = 0
        selected_candidate_ids: set[str] = set()
        batch_review_candidates: list[dict[str, object]] = []
        sm = self._state_machine

        self._log_state("INIT", 0, {"dry_run": self._dry_run})
        current_state = self._transition(sm, "INIT", "start")

        for round_index in range(self._policy.max_rounds):
            rounds_completed += 1

            # --- DISCOVER ---
            accepted_candidates = list(self._candidates)

            # Auto-discover: 3-level fallback if no candidates explicitly provided
            if not accepted_candidates:
                try:
                    from tools.engines.discovery.job_leads_loader import (
                        discover_candidates,
                    )
                    # Use job_profile keywords for targeted search if available
                    kwargs: dict[str, object] = {}
                    if self._job_profile is not None:
                        jp_keywords = getattr(self._job_profile, "keywords", ())
                        if jp_keywords:
                            kwargs["search_keywords"] = list(jp_keywords)
                    discovered = discover_candidates(**kwargs)
                    if discovered:
                        accepted_candidates = discovered
                except ImportError:
                    pass

            # 单画像运行只能消费绑定同一画像的岗位，CLI 自动发现与 App 使用相同边界。
            profile_id = self._job_profile.id if self._job_profile is not None else ""
            accepted_candidates = [candidate for candidate in accepted_candidates
                if (not candidate.job_profile_id or candidate.job_profile_id == profile_id)
                and (candidate.source != "liepin_official" or (
                    bool(profile_id) and candidate.job_profile_id == profile_id
                    and candidate.jd_status == "complete_reviewed" and bool(candidate.source_jd_sha256)))]
            discovery_payload: dict[str, object] = {"candidates": len(accepted_candidates)}
            if self._discovery is not None and accepted_candidates:
                disc_result = self._discovery.discover(accepted_candidates)
                accepted_candidates = list(disc_result.accepted)
                discovery_payload = {
                    "candidates": len(accepted_candidates),
                    "total": discovery_payload["candidates"],
                }
                if disc_result.excluded:
                    discovery_payload["accepted"] = len(disc_result.accepted)
                    discovery_payload["excluded"] = len(disc_result.excluded)
            self._log_state("DISCOVER", round_index, discovery_payload)

            if not accepted_candidates and not self._dry_run:
                self._log_state("DONE", round_index, {"reason": "no_candidates"})
                return AgentLoopResult(
                    run_id=self._run_id, status="DONE",
                    rounds_completed=rounds_completed,
                )

            # --- SCORE ---
            current_state = self._transition(sm, current_state, "next")
            matching_report = self._run_matching()
            matching_total = matching_report.score_breakdown.get("total", 0.0)
            self._log_state("SCORE", round_index,
                            {"matching_total": matching_total})

            # --- GENERATE ---
            current_state = self._transition(sm, current_state, "next")
            resume = self._run_generation(matching_report, f"v{round_index + 1}")
            self._log_state("GENERATE", round_index,
                            {"resume_version": resume.version})

            # --- EVALUATE ---
            current_state = self._transition(sm, current_state, "next")
            scorecard = self._run_evaluation(resume)
            self._log_state("EVALUATE", round_index,
                            {"evaluation_total": scorecard.total_score})

            # --- GATE ---
            current_state = self._transition(sm, current_state, "next")

            # Only consider candidates with valid job URLs for delivery
            deliverable = _rank_candidate_batch(
                [
                    c for c in accepted_candidates
                    if c.job_url and c.job_url.startswith("http")
                ],
                selected_candidate_ids,
            )
            if not deliverable and accepted_candidates:
                self._log_state("GATE", round_index,
                                {"result": "skip", "reason": "no_deliverable_candidates"})
                self._log_state("LEARN", round_index,
                                {"action": "retry", "reason": "no_deliverable_urls"})
                current_state = self._transition(sm, current_state, "fail")
                current_state = self._transition(sm, current_state, "next")
                continue

            gate_passed = False
            gate_candidate: Candidate | None = None

            for candidate in deliverable:
                gate_result = self._run_gate(
                    candidate, matching_total, scorecard.total_score, round_index,
                )
                if isinstance(gate_result, Ok):
                    gate_passed = True
                    gate_candidate = candidate
                    break
                self._log_state("GATE", round_index,
                                {"result": "fail", "reason": gate_result.error.reason})

            if not gate_passed:
                self._log_state("GATE", round_index, {"result": "fail"})
                self._log_state("LEARN", round_index,
                                {"action": "retry", "reason": "gate_failed"})
                current_state = self._transition(sm, current_state, "fail")
                current_state = self._transition(sm, current_state, "next")  # LEARN → DISCOVER
                continue

            self._log_state("GATE", round_index,
                            {"result": "pass",
                             "candidate": gate_candidate.candidate_id if gate_candidate else "",
                             "candidate_pool": [c.candidate_id for c in deliverable],
                             "selection_strategy": "confidence_desc_round_robin"})
            if gate_candidate is not None:
                selected_candidate_ids.add(gate_candidate.candidate_id)
            current_state = self._transition(sm, current_state, "pass")

            # --- REVIEW ---
            review_candidate = _build_review_candidate_payload(
                candidate=gate_candidate,
                matching_score=matching_total,
                evaluation_score=scorecard.total_score,
                round_index=round_index,
                resume_version=resume.version,
            )
            if self._policy.delivery_mode == "manual":
                from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
                try:
                    review_candidate['snapshot'] = ReviewSnapshotStore().create(
                        self._run_id, review_candidate, resume.content, dry_run=self._dry_run,
                    )
                except ValueError:
                    self._log_state('REVIEW', round_index, {'error': 'review_snapshot_export_failed'})
                    return AgentLoopResult(self._run_id, 'REVIEW_SNAPSHOT_BLOCKED', rounds_completed)
            if self._policy.delivery_mode == "manual" and self._policy.batch_review:
                batch_review_candidates.append(review_candidate)

            remaining_after_selection = _rank_candidate_batch(
                [
                    c for c in accepted_candidates
                    if c.job_url and c.job_url.startswith("http")
                ],
                selected_candidate_ids,
            )
            is_last_round = round_index + 1 >= self._policy.max_rounds
            no_more_deliverable = len(remaining_after_selection) == 0
            batch_ready = bool(
                self._policy.delivery_mode == "manual"
                and self._policy.batch_review
                and (is_last_round or no_more_deliverable)
            )
            review_events: list[str] = []
            review_ctx: dict[str, object] = {
                "events": review_events,
                "all_rounds_done": batch_ready,
            }
            review_result = self._review.execute(review_ctx) if self._review else None

            review_payload: dict[str, object] = {
                "mode": self._policy.delivery_mode,
                "events": review_events,
            }
            if review_result is not None:
                review_payload.update(dict(review_result.data))
            elif self._policy.delivery_mode == 'manual':
                # 组件缺失不能把人工审批静默降级为自动通过。
                review_payload['waiting_for_review'] = True

            if review_payload.get("waiting_for_review") is True:
                pending_candidates = (
                    batch_review_candidates
                    if self._policy.batch_review
                    else [review_candidate]
                )
                _write_review_queue(self._run_id, pending_candidates)
                review_payload["pending_candidates"] = len(pending_candidates)
                review_payload["queue_path"] = str(_review_queue_path(self._run_id))
                self._log_state("REVIEW", round_index, review_payload)
                return AgentLoopResult(
                    run_id=self._run_id,
                    status="REVIEW_PENDING",
                    rounds_completed=rounds_completed,
                )

            self._log_state("REVIEW", round_index, review_payload)
            if review_payload.get("collecting") is True:
                self._log_state(
                    "LEARN",
                    round_index,
                    {
                        "action": "collect_review",
                        "pending_candidates": len(batch_review_candidates),
                    },
                )
                current_state = self._transition(sm, current_state, "reject")
                if round_index + 1 < self._policy.max_rounds:
                    current_state = self._transition(sm, current_state, "next")
                    continue
                _write_review_queue(self._run_id, batch_review_candidates)
                return AgentLoopResult(
                    run_id=self._run_id,
                    status="REVIEW_PENDING",
                    rounds_completed=rounds_completed,
                )

            current_state = self._transition(sm, current_state, "approve")

            # --- DELIVER ---
            if not self._dry_run and gate_candidate is not None:
                delivery = self._run_delivery(gate_candidate, round_index, resume)
                if isinstance(delivery, Ok):
                    if delivery.value.success:
                        deliveries_completed += 1
                    self._log_state("DELIVER", round_index,
                                    {"channel": delivery.value.channel_id,
                                     "success": delivery.value.success,
                                     "submission_id": delivery.value.submission_id,
                                     "candidate": gate_candidate.candidate_id,
                                     "selection_strategy": "confidence_desc_round_robin"})
                else:
                    self._log_state("DELIVER", round_index,
                                    {"error": delivery.error.reason, "success": False})
                    if delivery.error.reason in {
                        'delivery_result_unknown', 'delivery_receipt_missing',
                        'delivery_already_attempted', 'delivery_state_unavailable',
                    }:
                        self._log_state('LEARN', round_index, {'action': 'pause', 'reason': delivery.error.reason})
                        self._log_state('DONE', round_index, {'stop_reason': delivery.error.reason,
                                        'deliveries_completed': deliveries_completed})
                        return AgentLoopResult(self._run_id, 'DELIVERY_BLOCKED', rounds_completed)
            else:
                simulated_deliveries += 1
                self._log_state("DELIVER", round_index,
                                {"dry_run": True,
                                 "success": False,
                                 "would_deliver": True,
                                 "candidate": gate_candidate.candidate_id if gate_candidate else "",
                                 "selection_strategy": "confidence_desc_round_robin"})
            current_state = self._transition(sm, current_state, "next")

            # --- LEARN ---
            stop_reason = ""
            # 模拟沿用单次预算上限，但其数量不进入真实成功计数。
            budget_count = simulated_deliveries if self._dry_run else deliveries_completed
            if self._policy.max_deliveries > 0 and budget_count >= self._policy.max_deliveries:
                stop_reason = "max_deliveries"
            self._log_state("LEARN", round_index,
                            {"deliveries": deliveries_completed,
                             "simulated_deliveries": simulated_deliveries,
                             "stop_reason": stop_reason})

            if stop_reason:
                current_state = self._transition(sm, current_state, "stop")
                self._log_state("DONE", round_index,
                                {"stop_reason": stop_reason,
                                 "deliveries_completed": deliveries_completed,
                                 "simulated_deliveries": simulated_deliveries})
                return AgentLoopResult(
                    run_id=self._run_id, status="DONE",
                    rounds_completed=rounds_completed,
                )

            # Prepare for next round: LEARN → DISCOVER (if more rounds remain)
            if round_index + 1 < self._policy.max_rounds:
                current_state = self._transition(sm, current_state, "next")

        # exhausted max_rounds
        current_state = self._transition(sm, current_state, "stop")
        self._log_state("DONE", max(self._policy.max_rounds - 1, 0),
                        {"stop_reason": "max_rounds",
                         "deliveries_completed": deliveries_completed,
                         "simulated_deliveries": simulated_deliveries,
                         "rounds_completed": rounds_completed})
        return AgentLoopResult(
            run_id=self._run_id, status="DONE",
            rounds_completed=rounds_completed,
        )

    # ------------------------------------------------------------------
    # pipeline step helpers
    # ------------------------------------------------------------------

    def _run_matching(self) -> MatchingReport:
        if self._job_profile is None:
            return MatchingReport(
                job_profile_id="default",
                evidence_card_ids=(),
                score_breakdown={"total": 1.0},
                gap_tasks=(),
            )
        return self._matching.score(self._evidence_cards, self._job_profile)

    def _run_generation(self, report: MatchingReport, version: str) -> ResumeOutput:
        return self._generation.generate(report, self._evidence_cards, version)

    def _run_evaluation(self, resume: ResumeOutput) -> Scorecard:
        profile = self._job_profile
        if profile is None:
            profile = JobProfile(id="default", title="", keywords=(), level="")
        return self._evaluation.evaluate(resume, profile)

    def _run_gate(
        self,
        candidate: Candidate,
        matching_score: float,
        evaluation_score: float,
        round_index: int,
    ) -> Result[GateDecision, GateFailure]:
        gate = _gate_engine_for_round(self._policy, self._run_id, round_index)
        return gate.evaluate(candidate, matching_score, evaluation_score)

    def _run_delivery(
        self,
        candidate: Candidate,
        round_index: int,
        resume: ResumeOutput,
    ) -> Result[DeliveryResult, ChannelFailure]:
        route = _delivery_platform(candidate)
        if isinstance(route, Err):
            return route
        platform = route.value
        if candidate.source == "liepin_official":
            return Err(ChannelFailure(
                channel_id=platform, reason="official_delivery_contract_unverified",
                details="官方投递的发送版本与回执契约尚未验证，禁止转入旧浏览器投递",
            ))

        if not self._channels:
            from tools.channels.email import EmailChannel
            from tools.channels.liepin import LiepinChannel
            channels: list[DeliveryChannel] = [LiepinChannel(), EmailChannel()]
        else:
            channels = list(self._channels)

        if not any(channel.channel_id == platform for channel in channels):
            return Err(ChannelFailure(
                channel_id=platform, reason="no_channel",
                details="未配置与目标平台匹配的投递通道",
            ))

        from tools.engines.generation.exporter import ResumeExporter
        from tools.infra.export.pdf_exporter import markdown_to_pdf

        # 每次尝试保留独立附件，重试或同名版本不能覆盖前次文件。
        try:
            output_root = Path("outputs") / "agent_runs" / self._run_id / "deliveries"
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
            self._append_event("resume_exported", round_index, {
                **metadata, "resume_path": resume_path, "candidate_id": candidate.candidate_id,
            })
        except (OSError, RuntimeError) as exc:
            self._logger.warning("agent_loop.resume_pdf_export_failed", error=str(exc))
            return Err(ChannelFailure(
                channel_id="none", reason="resume_pdf_export_failed", details=str(exc),
            ))

        request = DeliveryRequest(
            run_id=self._run_id,
            candidate_id=candidate.candidate_id,
            channel=platform,
            resume_path=resume_path,
            job_url=candidate.job_url,
            dry_run=False,
            metadata=metadata,
        )
        from tools.orchestration.approved_delivery import deliver_once
        return deliver_once(request, channels, source=candidate.source)

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------

    def replay_state(self) -> RunState:
        if self._run_store is None:
            return RunState.initial(self._run_id)
        events = self._run_store.load_events(self._run_id)
        return RunState.replay(self._run_id, events)

    def _append_event(
        self, event_type: str, round_index: int, payload: dict[str, object]
    ) -> None:
        if self._run_store is None:
            return
        self._run_store.append_event(
            RunEvent(
                run_id=self._run_id,
                event_type=event_type,
                round_index=round_index,
                payload=payload,
            )
        )

    def _log_state(
        self, state: str, round_index: int, payload: dict[str, object]
    ) -> None:
        self._logger.info(
            "agent_loop.state", run_id=self._run_id, round=round_index, state=state
        )
        self._append_event(state, round_index=round_index, payload=payload)

    def _transition(self, sm: object, current: str, transition_event: str) -> str:
        if sm is None:
            return current
        try:
            return sm.transition(current, transition_event)
        except ValueError:
            self._logger.warning(
                "agent_loop.invalid_transition",
                current=current,
                transition=transition_event,
            )
            return current


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


def _review_queue_path(run_id: str) -> Path:
    return Path("outputs") / "review_queue" / f"{run_id}.json"


def _utcnow_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _build_review_candidate_payload(
    *,
    candidate: Candidate | None,
    matching_score: float,
    evaluation_score: float,
    round_index: int,
    resume_version: str,
) -> dict[str, object]:
    return {
        "job_lead_id": candidate.candidate_id if candidate else "",
        "company": candidate.company if candidate else "",
        "legal_entity": candidate.legal_entity if candidate else "",
        "position": candidate.direction if candidate else "",
        "matching_score": matching_score,
        "evaluation_score": evaluation_score,
        "round_index": round_index,
        "resume_version": resume_version,
        "job_url": candidate.job_url if candidate else "",
        "platform": candidate.platform if candidate else "",
        "platform_job_id": candidate.platform_job_id if candidate else "",
        "platform_job_type": candidate.platform_job_type if candidate else "",
        "job_profile_id": candidate.job_profile_id if candidate else "",
        "jd_status": candidate.jd_status if candidate else "",
        "source_jd_sha256": candidate.source_jd_sha256 if candidate else "",
        "source": candidate.source if candidate else "",
        "status": "pending",
        "created_at": _utcnow_iso(),
    }


def _write_review_queue(run_id: str, candidates: Sequence[dict[str, object]]) -> Path:
    queue_path = _review_queue_path(run_id)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue = {
        "run_id": run_id,
        "candidates": list(candidates),
        "created_at": _utcnow_iso(),
    }
    from tools.infra.persistence.review_queue import atomic_write_json, locked_review_queue
    with locked_review_queue(queue_path):
        if queue_path.exists():
            raise ValueError('review_queue_already_exists')
        atomic_write_json(queue_path, queue)
    return queue_path
