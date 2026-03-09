from __future__ import annotations

import json
from datetime import datetime, timezone


class StructuredLogger:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id

    def _emit(self, level: str, event: str, **kwargs: object) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "run_id": self._run_id,
            "event": event,
            **kwargs,
        }
        print(json.dumps(record, ensure_ascii=False))

    def info(self, event: str, **kwargs: object) -> None:
        self._emit("INFO", event, **kwargs)

    def warning(self, event: str, **kwargs: object) -> None:
        self._emit("WARNING", event, **kwargs)

    def error(self, event: str, **kwargs: object) -> None:
        self._emit("ERROR", event, **kwargs)


def make_logger(run_id: str) -> StructuredLogger:
    return StructuredLogger(run_id=run_id)
