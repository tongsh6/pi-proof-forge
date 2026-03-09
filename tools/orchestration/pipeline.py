from __future__ import annotations

from collections.abc import Sequence

from tools.orchestration.stage import RunContext, StageProtocol, StageResult


class LinearPipeline:
    def __init__(self, stages: Sequence[StageProtocol]) -> None:
        self._stages = tuple(stages)

    def run(self, context: RunContext) -> StageResult:
        for stage in self._stages:
            result = stage.execute(context)
            if not result.success:
                return result
            context[stage.name] = result.data
        return StageResult(success=True, data=context)
