from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

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
                    payload={"channel": delivery.value.channel_id},
                )
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
            dry_run=False,
            metadata={"round": round_index},
        )
        return deliver_with_fallback(request, [LiepinChannel(), EmailChannel()])

    # ------------------------------------------------------------------
    # full pipeline (engines injected via Composer)
    # ------------------------------------------------------------------

    def _run_full_pipeline(self) -> AgentLoopResult:
        rounds_completed = 0
        deliveries_completed = 0
        sm = self._state_machine

        self._log_state("INIT", 0, {"dry_run": self._dry_run})

        for round_index in range(self._policy.max_rounds):
            rounds_completed += 1

            # --- DISCOVER ---
            accepted_candidates = list(self._candidates)
            discovery_payload: dict[str, object] = {"candidates": len(accepted_candidates)}
            if self._discovery is not None and self._candidates:
                disc_result = self._discovery.filter_candidates(list(self._candidates))
                accepted_candidates = list(disc_result.accepted)
                discovery_payload = {
                    "candidates": len(accepted_candidates),
                    "total": len(self._candidates),
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
            matching_report = self._run_matching()
            matching_total = matching_report.score_breakdown.get("total", 0.0)
            self._log_state("SCORE", round_index,
                            {"matching_total": matching_total})

            # --- GENERATE ---
            resume = self._run_generation(matching_report, f"v{round_index + 1}")
            self._log_state("GENERATE", round_index,
                            {"resume_version": resume.version})

            # --- EVALUATE ---
            scorecard = self._run_evaluation(resume)
            self._log_state("EVALUATE", round_index,
                            {"evaluation_total": scorecard.total_score})

            # --- GATE ---
            gate_passed = False
            gate_candidate: Candidate | None = None

            for candidate in accepted_candidates:
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
                continue

            self._log_state("GATE", round_index,
                            {"result": "pass",
                             "candidate": gate_candidate.candidate_id if gate_candidate else ""})

            # --- REVIEW ---
            review_ctx: dict[str, object] = {"events": [], "all_rounds_done": False}
            review_result = self._review.execute(review_ctx) if self._review else None
            self._log_state("REVIEW", round_index, {"mode": self._policy.delivery_mode})

            # --- DELIVER ---
            if not self._dry_run and gate_candidate is not None:
                delivery = self._run_delivery(gate_candidate, round_index, resume)
                if isinstance(delivery, Ok):
                    deliveries_completed += 1
                    self._log_state("DELIVER", round_index,
                                    {"channel": delivery.value.channel_id})
                else:
                    self._log_state("DELIVER", round_index,
                                    {"error": delivery.error.reason})
            else:
                self._log_state("DELIVER", round_index,
                                {"dry_run": True, "would_deliver": True})

            # --- LEARN ---
            stop_reason = ""
            if self._policy.max_deliveries > 0 and deliveries_completed >= self._policy.max_deliveries:
                stop_reason = "max_deliveries"
            self._log_state("LEARN", round_index,
                            {"deliveries": deliveries_completed,
                             "stop_reason": stop_reason})

            if stop_reason:
                self._log_state("DONE", round_index,
                                {"stop_reason": stop_reason,
                                 "deliveries_completed": deliveries_completed})
                return AgentLoopResult(
                    run_id=self._run_id, status="DONE",
                    rounds_completed=rounds_completed,
                )

        # exhausted max_rounds
        self._log_state("DONE", max(self._policy.max_rounds - 1, 0),
                        {"stop_reason": "max_rounds",
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
        return self._generation.assemble(report, self._evidence_cards, version)

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
        if not self._channels:
            from tools.channels.email import EmailChannel
            from tools.channels.liepin import LiepinChannel
            channels: list[DeliveryChannel] = [LiepinChannel(), EmailChannel()]
        else:
            channels = list(self._channels)

        request = DeliveryRequest(
            run_id=self._run_id,
            candidate_id=candidate.candidate_id,
            channel=candidate.direction,
            resume_path=f"outputs/{resume.version}.md",
            job_url=candidate.job_url,
            dry_run=False,
            metadata={"round": round_index},
        )
        return deliver_with_fallback(request, channels)

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


def _gate_engine_for_round(
    policy: PolicyConfig, run_id: str, round_index: int
) -> object:
    from tools.orchestration.gate_engine import GateEngine
    return GateEngine(policy, run_id, round_index)
