from __future__ import annotations

TRANSITIONS: dict[str, dict[str, str]] = {
    "INIT": {"start": "DISCOVER"},
    "DISCOVER": {"next": "SCORE", "empty": "DONE"},
    "SCORE": {"next": "GENERATE"},
    "GENERATE": {"next": "EVALUATE"},
    "EVALUATE": {"next": "GATE"},
    "GATE": {"pass": "REVIEW", "fail": "LEARN"},
    "REVIEW": {"approve": "DELIVER", "reject": "LEARN", "skip": "LEARN"},
    "DELIVER": {"next": "LEARN"},
    "LEARN": {"next": "DISCOVER", "stop": "DONE"},
    "DONE": {},
}


class StateMachine:
    def transition(self, state: str, event: str) -> str:
        if state not in TRANSITIONS:
            raise ValueError(f"Unknown state: {state}")
        mapping = TRANSITIONS[state]
        if event not in mapping:
            raise ValueError(f"Invalid transition: {state} --{event}--> ?")
        return mapping[event]
