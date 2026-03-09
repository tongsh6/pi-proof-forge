from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from tools.domain.events import RunEvent


class FileRunStore:
    def __init__(self, base_dir: str = "outputs/agent_runs") -> None:
        self._base_dir = Path(base_dir)

    def append_event(self, event: RunEvent) -> None:
        run_dir = self._base_dir / event.run_id
        rounds_dir = run_dir / "rounds" / str(event.round_index)
        run_dir.mkdir(parents=True, exist_ok=True)
        rounds_dir.mkdir(parents=True, exist_ok=True)

        run_log_path = run_dir / "run_log.json"
        entries = self._read_raw_entries(run_log_path)
        payload: dict[str, object] = {
            "run_id": event.run_id,
            "event_type": event.event_type,
            "round_index": event.round_index,
            "payload": event.payload,
            "timestamp": event.timestamp,
        }
        entries.append(payload)
        _ = run_log_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        event_path = rounds_dir / "events.jsonl"
        _ = event_path.write_text(
            event_path.read_text(encoding="utf-8")
            + json.dumps(payload, ensure_ascii=False)
            + "\n"
            if event_path.exists()
            else json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load_events(self, run_id: str) -> list[RunEvent]:
        run_log_path = self._base_dir / run_id / "run_log.json"
        entries = self._read_raw_entries(run_log_path)
        output: list[RunEvent] = []
        for item in entries:
            output.append(
                RunEvent(
                    run_id=str(item.get("run_id", run_id)),
                    event_type=str(item.get("event_type", "")),
                    round_index=_to_int(item.get("round_index", 0)),
                    payload=_ensure_dict(item.get("payload", {})),
                    timestamp=str(item.get("timestamp", "")),
                )
            )
        return output

    @staticmethod
    def _read_raw_entries(path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        loaded = cast(object, json.loads(text))
        if isinstance(loaded, list):
            out: list[dict[str, object]] = []
            for item in loaded:
                if isinstance(item, dict):
                    normalized: dict[str, object] = {}
                    for key, value in item.items():
                        normalized[str(key)] = value
                    out.append(normalized)
            return out
        return []


def _ensure_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            out[str(key)] = item
        return out
    return {}


def _to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
