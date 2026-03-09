from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


RunContext = dict[str, object]


@dataclass(frozen=True)
class StageResult:
    success: bool
    data: object
    errors: tuple[object, ...] = ()


class StageProtocol(Protocol):
    name: str

    def execute(self, context: RunContext) -> StageResult: ...
