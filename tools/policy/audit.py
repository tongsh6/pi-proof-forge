from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import cast

from tools.domain.value_objects import Candidate


def write_exclusion_audit(log_path: Path, candidate: Candidate, source: str) -> None:
    event: dict[str, object] = {
        "event_type": "excluded_by_policy",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "source": source,
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "company": candidate.company,
            "direction": candidate.direction,
            "job_url": candidate.job_url,
            "confidence": candidate.confidence,
            "source": candidate.source,
            "merged_sources": list(candidate.merged_sources),
        },
    }
    events: list[dict[str, object]] = []
    if log_path.exists():
        raw = log_path.read_text(encoding="utf-8")
        try:
            parsed = cast(object, json.loads(raw))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            parsed_list = cast(list[object], parsed)
            for item in parsed_list:
                if isinstance(item, dict):
                    events.append(cast(dict[str, object], item))
        elif isinstance(parsed, dict):
            events = [cast(dict[str, object], parsed)]
    events.append(event)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _ = log_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
