from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from tools.domain.events import RunEvent


@dataclass(frozen=True)
class RunState:
    run_id: str
    current_status: str
    round_index: int

    @classmethod
    def initial(cls, run_id: str) -> "RunState":
        return cls(run_id=run_id, current_status="INIT", round_index=0)

    @classmethod
    def replay(cls, run_id: str, events: Sequence[RunEvent]) -> "RunState":
        state = cls.initial(run_id)
        for event in events:
            state = cls(
                run_id=run_id,
                current_status=event.event_type,
                round_index=event.round_index,
            )
        return state
