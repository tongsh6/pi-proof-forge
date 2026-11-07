"""agent 域共享运行时工具：时间、ID 校验、路径解析。

这些函数被 quick_run / agent_run / agent_review 三个子模块复用；
无模块级可变状态，patch 场景不受拆分影响。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed

def _elapsed_seconds_between(start: Any, end: Any) -> int | None:
    start_dt = _parse_iso_datetime(start)
    end_dt = _parse_iso_datetime(end)
    if start_dt is None or end_dt is None:
        return None
    return max(0, int(round((end_dt - start_dt).total_seconds())))

def _validate_run_resource_id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    normalized = value.strip()
    if "/" in normalized or "\\" in normalized or normalized.startswith("."):
        raise ValueError(f"{name} is invalid")
    return normalized

def _coerce_positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default

def _find_project_root(start: Path) -> Path:
    for parent in start.parents:
        if (parent / "tools" / "cli" / "entrypoints.py").exists():
            return parent
    return start.parents[3] if len(start.parents) > 3 else start.parent
