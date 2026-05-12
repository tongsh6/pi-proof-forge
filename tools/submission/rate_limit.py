from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class RateLimitConfig:
    max_per_batch: int = 5
    cooldown_seconds: int = 900
    daily_limit: int = 30


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str = ""
    wait_seconds: int = 0
    batch_count: int = 0
    daily_count: int = 0


class SubmissionRateLimiter:
    def __init__(
        self,
        state_path: Path,
        *,
        now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._state_path = state_path
        self._now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def check_and_record(self, config: RateLimitConfig) -> RateLimitDecision:
        if (
            config.max_per_batch <= 0
            and config.cooldown_seconds <= 0
            and config.daily_limit <= 0
        ):
            return RateLimitDecision(allowed=True)

        now = self._normalized_now()
        state = self._load_state()
        today = now.date().isoformat()
        if state.get("day") != today:
            state = {
                "day": today,
                "daily_count": 0,
                "batch_count": 0,
                "last_at": 0.0,
            }

        daily_count = int(state.get("daily_count", 0))
        batch_count = int(state.get("batch_count", 0))
        last_at = float(state.get("last_at", 0.0))

        if config.daily_limit > 0 and daily_count >= config.daily_limit:
            return RateLimitDecision(
                allowed=False,
                reason="daily_limit_exceeded",
                batch_count=batch_count,
                daily_count=daily_count,
            )

        elapsed = max(0, int(now.timestamp() - last_at)) if last_at else config.cooldown_seconds
        if config.max_per_batch > 0 and batch_count >= config.max_per_batch:
            if config.cooldown_seconds > 0 and elapsed < config.cooldown_seconds:
                return RateLimitDecision(
                    allowed=False,
                    reason="batch_cooldown",
                    wait_seconds=config.cooldown_seconds - elapsed,
                    batch_count=batch_count,
                    daily_count=daily_count,
                )
            batch_count = 0

        batch_count += 1
        daily_count += 1
        state.update(
            {
                "day": today,
                "daily_count": daily_count,
                "batch_count": batch_count,
                "last_at": now.timestamp(),
            }
        )
        self._write_state(state)
        return RateLimitDecision(
            allowed=True,
            batch_count=batch_count,
            daily_count=daily_count,
        )

    def _normalized_now(self) -> datetime.datetime:
        current = self._now()
        if current.tzinfo is None:
            return current.replace(tzinfo=datetime.timezone.utc)
        return current.astimezone(datetime.timezone.utc)

    def _load_state(self) -> dict[str, object]:
        if not self._state_path.exists():
            return {}
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_state(self, state: dict[str, object]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
