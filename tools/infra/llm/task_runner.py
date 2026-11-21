"""LLM 任务执行器：让任务契约真正生效。

之前契约只是"声明"，各任务仍各自调用模型、各自处理失败。执行器把
「能力校验 → 调用 → 校验 → 状态 → 记录」收敛成唯一路径：

- 执行前按契约检查输入预算（超了必须拆批，不许硬塞）；
- 只对**可重试的原因**（结构错误/截断）重试，能力问题不重试；
- 每次执行都产出 `TaskRun`：状态、原因码、尝试次数、耗时——可进台账；
- 执行器不猜：能力不足直接 unavailable，不尝试"再试一次也许就好了"。

设计见 docs/reports/llm-task-contract-design-20261110.md。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from tools.infra.llm.task_contract import (
    REASON_INPUT_BUDGET_EXCEEDED,
    REASON_INVALID_JSON,
    REASON_OUTPUT_TRUNCATED,
    REASON_TIMEOUT,
    TaskContract,
    TaskOutcome,
    complete,
    partial,
    unavailable,
)

# 结构性错误值得重试一次：模型偶尔输出坏 JSON，这不是能力问题。
RETRYABLE_REASONS = frozenset({REASON_INVALID_JSON, REASON_OUTPUT_TRUNCATED})
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class TaskRun:
    """一次任务执行的完整记录。"""

    contract: str
    model: str
    outcome: TaskOutcome
    attempts: int
    elapsed_seconds: float

    @property
    def status(self) -> str:
        return self.outcome.status

    @property
    def reason_code(self) -> str:
        return self.outcome.reason_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "model": self.model,
            "status": self.outcome.status,
            "reason_code": self.outcome.reason_code,
            "detail": self.outcome.detail,
            "attempts": self.attempts,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


def _payload_chars(payload: Mapping[str, Any]) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


def check_budget(contract: TaskContract, payload: Mapping[str, Any]) -> str:
    """返回预算校验结论：空串表示通过，否则是拒绝原因。"""
    size = _payload_chars(payload)
    if size > contract.capability.max_input_chars:
        return f"input_budget_exceeded:{size}>{contract.capability.max_input_chars}"
    return ""


def execute(
    contract: TaskContract,
    *,
    model: str,
    payload: Mapping[str, Any],
    call: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    extract: Callable[[Mapping[str, Any]], str],
    validate: Callable[[Any], Any],
    on_retry: Callable[[Mapping[str, Any], ValueError], Mapping[str, Any]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> TaskRun:
    """执行一次任务：预算校验 → 调用 → 校验 → 状态。

    `call` 只负责发请求，`extract` 取正文，`validate` 做结构与事实校验并
    返回结果（校验失败抛 ValueError）。执行器不吞异常语义：结构与事实问题
    归为可重试/不可核实，服务问题归为不可用。
    """
    started = clock()
    budget_reason = check_budget(contract, payload)
    if budget_reason:
        return TaskRun(
            contract.name,
            model,
            unavailable(contract, reason_code=REASON_INPUT_BUDGET_EXCEEDED, detail=budget_reason),
            0,
            clock() - started,
        )

    attempts = 0
    last_reason = REASON_INVALID_JSON
    last_detail = ""
    current_payload = payload
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        try:
            response = call(current_payload)
        except TimeoutError as exc:
            return TaskRun(
                contract.name,
                model,
                unavailable(contract, reason_code=REASON_TIMEOUT, detail=str(exc)[:200]),
                attempts,
                clock() - started,
            )
        except Exception as exc:  # noqa: BLE001 - 服务层失败统一降级为"不可用"
            return TaskRun(
                contract.name,
                model,
                unavailable(contract, reason_code="model_unavailable", detail=str(exc)[:200]),
                attempts,
                clock() - started,
            )

        try:
            content = extract(response)
        except Exception as exc:  # noqa: BLE001
            last_reason, last_detail = REASON_INVALID_JSON, f"extract_failed:{exc}"[:200]
            continue

        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            last_reason, last_detail = REASON_INVALID_JSON, "模型输出不是合法 JSON"
            continue

        try:
            result = validate(parsed)
        except ValueError as exc:
            last_reason, last_detail = REASON_INVALID_JSON, str(exc)[:200]
            if on_retry is not None and attempts < MAX_ATTEMPTS:
                try:
                    current_payload = on_retry(current_payload, exc)
                except Exception:  # noqa: BLE001 - 修复请求构造失败就按原样重发
                    current_payload = payload
            continue

        return TaskRun(contract.name, model, complete(result), attempts, clock() - started)

    # 重试耗尽：明确不可用，不把坏结果交给下游。
    return TaskRun(
        contract.name,
        model,
        unavailable(contract, reason_code=last_reason, detail=last_detail),
        attempts,
        clock() - started,
    )


def run_partial(
    contract: TaskContract,
    *,
    model: str,
    succeeded: dict[str, Any],
    failed: dict[str, str],
    clock: Callable[[], float] = time.monotonic,
) -> TaskRun:
    """批量任务的部分完成：成功项 + 失败项（key → 原因）。

    这是"部分完成"的显式表达：下游拿到 succeeded，并知道 failed 里每一项
    为什么没有结果，而不是面对一个笼统的失败。
    """
    from tools.infra.llm.task_contract import REASON_PARTIAL_COVERAGE

    total = len(succeeded) + len(failed)
    if not failed:
        return TaskRun(contract.name, model, complete(succeeded), 1, 0.0)
    detail = f"{len(failed)}/{total} 项未完成：" + "；".join(
        f"{key}={reason}" for key, reason in list(failed.items())[:5]
    )
    return TaskRun(
        contract.name,
        model,
        partial(reason_code=REASON_PARTIAL_COVERAGE, detail=detail[:600], result=succeeded),
        1,
        0.0,
    )
