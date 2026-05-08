from __future__ import annotations

from collections.abc import Sequence

from tools.domain.protocols import Stage, StageResult


class LinearPipeline:
    """Linear sequence of Stage objects. Stops on first failure."""

    def __init__(self, stages: Sequence[Stage]) -> None:
        self._stages = tuple(stages)

    def run(self, context: dict[str, object]) -> StageResult:
        for stage in self._stages:
            result = stage.execute(context)
            if not result.success:
                return result
            context[stage.name] = result.data
        return StageResult(success=True, data=context)
