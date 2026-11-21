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
from urllib.request import Request

from tools.infra.llm.task_contract import (
    REASON_INPUT_BUDGET_EXCEEDED,
    REASON_INVALID_JSON,
    REASON_INVALID_REQUEST,
    REASON_MODE_MISSING,
    REASON_TIMEOUT,
    TaskContract,
    TaskOutcome,
    complete,
    partial,
    unavailable,
)

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


def _request_chars(prepared: Request) -> int:
    if not isinstance(prepared, Request) or not isinstance(prepared.data, bytes):
        raise ValueError(REASON_INVALID_REQUEST)
    try:
        payload = json.loads(prepared.data.decode("utf-8"))
        return len(json.dumps(payload, ensure_ascii=False))
    except (TypeError, ValueError, RecursionError):
        raise ValueError(REASON_INVALID_REQUEST) from None


def check_budget(contract: TaskContract, prepared: Request) -> str:
    """Measure the complete prepared request; malformed requests are local input failures."""
    size = _request_chars(prepared)
    if size > contract.capability.max_input_chars:
        return f"{REASON_INPUT_BUDGET_EXCEEDED}:{size}>{contract.capability.max_input_chars}"
    return ""


def execute(
    contract: TaskContract,
    *,
    model: str,
    prepare: Callable[[], Request],
    call: Callable[[Request], Mapping[str, Any]],
    extract: Callable[[Mapping[str, Any]], str],
    validate: Callable[[Any], Any],
    on_retry: Callable[[Request, ValueError], Request] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> TaskRun:
    """Prepare once, check each request, then send that same request.

    A repair is a new prepared request. Local construction or budget failures
    never enter the sending callback and retain only earlier call attempts.
    """
    started = clock()
    attempts = 0

    def rejected(reason: str, detail: str) -> TaskRun:
        return TaskRun(
            contract.name,
            model,
            unavailable(contract, reason_code=reason, detail=detail),
            attempts,
            clock() - started,
        )

    try:
        current_request = prepare()
    except Exception as exc:  # noqa: BLE001 - 本地构造失败不是模型或 transport 失败
        return rejected(REASON_INVALID_REQUEST, f"request_preparation_failed:{type(exc).__name__}")

    last_reason = REASON_INVALID_JSON
    last_detail = ""
    while attempts < MAX_ATTEMPTS:
        try:
            budget_reason = check_budget(contract, current_request)
        except ValueError:
            return rejected(REASON_INVALID_REQUEST, "invalid_prepared_request")
        if budget_reason:
            return rejected(REASON_INPUT_BUDGET_EXCEEDED, budget_reason)

        attempts += 1
        try:
            response = call(current_request)
        except TimeoutError as exc:
            return rejected(REASON_TIMEOUT, str(exc)[:200])
        except Exception as exc:  # noqa: BLE001 - 服务层失败统一降级为"不可用"
            return rejected(REASON_MODE_MISSING, str(exc)[:200])

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
                    current_request = on_retry(current_request, exc)
                except Exception as repair_exc:  # noqa: BLE001 - 不把失败的修复变成原样重发
                    return rejected(
                        REASON_INVALID_REQUEST,
                        f"request_repair_failed:{type(repair_exc).__name__}",
                    )
            continue

        return TaskRun(contract.name, model, complete(result), attempts, clock() - started)

    # 重试耗尽：明确不可用，不把坏结果交给下游。
    return rejected(last_reason, last_detail)


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
