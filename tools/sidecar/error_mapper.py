from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_RETRYABLE_CODES = frozenset({"SIDECAR_UNAVAILABLE", "TIMEOUT"})


@dataclass(frozen=True)
class SidecarError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


class ErrorMapper:
    @staticmethod
    def create(code: str, message: str, correlation_id: str) -> SidecarError:
        retryable = code in _RETRYABLE_CODES
        return SidecarError(
            code=code,
            message=message,
            details={
                "correlation_id": correlation_id,
                "retryable": retryable,
            },
        )
