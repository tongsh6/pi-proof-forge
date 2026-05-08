from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from tools.domain.events import RunEvent


@dataclass(frozen=True)
class RunState:
    run_id: str
    current_status: str
    round_index: int
    pass_count: int = 0
    delivered_count: int = 0

    @classmethod
    def initial(cls, run_id: str) -> "RunState":
        return cls(run_id=run_id, current_status="INIT", round_index=0, pass_count=0, delivered_count=0)

    def apply(self, event: RunEvent) -> "RunState":
        """Pure function: old state + event → new state."""
        pass_delta = 1 if event.event_type == "GATE" and event.payload.get("result") == "pass" else 0
        deliver_delta = 1 if event.event_type == "DELIVER" else 0
        return RunState(
            run_id=self.run_id,
            current_status=event.event_type,
            round_index=event.round_index,
            pass_count=self.pass_count + pass_delta,
            delivered_count=self.delivered_count + deliver_delta,
        )

    @classmethod
    def replay(cls, run_id: str, events: Sequence[RunEvent]) -> "RunState":
        state = cls.initial(run_id)
        for event in events:
            state = state.apply(event)
        return state
