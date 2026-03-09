from __future__ import annotations

from dataclasses import dataclass

from tools.channels.base import DeliveryRequest, deliver_with_fallback
from tools.channels.email import EmailChannel
from tools.channels.liepin import LiepinChannel
from tools.config.fragments import PolicyConfig
from tools.domain.events import RunEvent
from tools.domain.result import Err, Ok
from tools.domain.run_state import RunState
from tools.infra.logging import make_logger
from tools.infra.persistence.file_run_store import FileRunStore


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
        run_store: FileRunStore | None = None,
    ) -> None:
        self._policy = policy
        self._run_id = run_id
        self._dry_run = dry_run
        self._logger = make_logger(run_id)
        self._run_store = run_store

    def run(self) -> AgentLoopResult:
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

            delivery = self._deliver(round_index)
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

    def _deliver(self, round_index: int):
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
