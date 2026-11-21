"""任务执行器：预算、重试边界与状态语义。"""
import json

import pytest

from tools.infra.llm.task_contract import (
    SEMANTIC_MATCHING,
    Capability,
    TaskContract,
)
from tools.infra.llm.task_runner import TaskRun, check_budget, execute, run_partial


def _contract(**kwargs) -> TaskContract:
    return TaskContract(
        name="t",
        capability=Capability(**kwargs),
        on_unavailable="degrade",
        degrade_note="降级",
    )


def test_budget_rejects_oversized_payload():
    contract = _contract(max_input_chars=20)
    reason = check_budget(contract, {"a": "x" * 100})
    assert reason.startswith("input_budget_exceeded")


def test_budget_passes_normal_payload():
    assert check_budget(SEMANTIC_MATCHING, {"a": "b"}) == ""


def test_execute_returns_complete_on_valid_output():
    run = execute(
        SEMANTIC_MATCHING,
        model="m",
        payload={"a": 1},
        call=lambda _p: {"choices": [{"message": {"content": '{"ok":true}'}}]},
        extract=lambda r: r["choices"][0]["message"]["content"],
        validate=lambda parsed: parsed,
    )
    assert isinstance(run, TaskRun)
    assert run.status == "complete" and run.attempts == 1


def test_invalid_json_is_retried_once_then_succeeds():
    calls = {"n": 0}

    def call(_p):
        calls["n"] += 1
        content = '{"ok":true}' if calls["n"] > 1 else "not json"
        return {"choices": [{"message": {"content": content}}]}

    run = execute(
        SEMANTIC_MATCHING, model="m", payload={}, call=call,
        extract=lambda r: r["choices"][0]["message"]["content"],
        validate=lambda parsed: parsed,
    )
    assert run.status == "complete" and run.attempts == 2


def test_repeated_invalid_json_ends_unavailable_not_partial():
    run = execute(
        SEMANTIC_MATCHING, model="m", payload={},
        call=lambda _p: {"choices": [{"message": {"content": "garbage"}}]},
        extract=lambda r: r["choices"][0]["message"]["content"],
        validate=lambda parsed: parsed,
    )
    assert run.status == "unavailable"
    assert run.reason_code == "invalid_json"
    assert run.attempts == 2


def test_service_failure_is_unavailable_without_retry():
    calls = {"n": 0}

    def call(_p):
        calls["n"] += 1
        raise ConnectionError("boom")

    run = execute(
        SEMANTIC_MATCHING, model="m", payload={}, call=call,
        extract=lambda r: "",
        validate=lambda parsed: parsed,
    )
    assert run.status == "unavailable" and run.reason_code == "model_unavailable"
    assert calls["n"] == 1  # 服务不可用不重试：重试只会拖长等待


def test_timeout_maps_to_timeout_reason():
    def call(_p):
        raise TimeoutError("slow")

    run = execute(
        SEMANTIC_MATCHING, model="m", payload={}, call=call,
        extract=lambda r: "", validate=lambda parsed: parsed,
    )
    assert run.reason_code == "timeout"


def test_partial_completion_reports_failed_items_with_reasons():
    run = run_partial(
        SEMANTIC_MATCHING, model="m",
        succeeded={"e1": {"score": 90}}, failed={"e2": "quote_unresolved"},
    )
    assert run.status == "partial"
    assert run.reason_code == "partial_coverage"
    assert "e2=quote_unresolved" in run.outcome.detail
    assert run.outcome.result == {"e1": {"score": 90}}


def test_full_success_is_complete():
    run = run_partial(SEMANTIC_MATCHING, model="m", succeeded={"e1": 1}, failed={})
    assert run.status == "complete"
