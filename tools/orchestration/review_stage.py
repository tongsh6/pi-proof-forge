from __future__ import annotations

from tools.config.fragments import PolicyConfig
from tools.orchestration.stage import RunContext, StageResult


class ReviewStage:
    name = "REVIEW"

    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy

    def execute(self, context: RunContext) -> StageResult:
        if self._policy.delivery_mode == "auto":
            return StageResult(
                success=True, data={"mode": "auto", "pass_through": True}
            )

        if self._policy.batch_review:
            all_rounds_done = bool(context.get("all_rounds_done", False))
            if all_rounds_done:
                return StageResult(
                    success=True,
                    data={
                        "mode": "manual",
                        "batch_review": True,
                        "waiting_for_review": True,
                    },
                )
            return StageResult(
                success=True,
                data={"mode": "manual", "batch_review": True, "collecting": True},
            )

        events = context.get("events")
        if isinstance(events, list):
            events.append("agent.review.pending")
        return StageResult(
            success=True,
            data={"mode": "manual", "batch_review": False, "waiting_for_review": True},
        )
