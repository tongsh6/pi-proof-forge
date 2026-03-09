from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    event_type: str
    round_index: int
    payload: dict[str, object]
    timestamp: str = ""
