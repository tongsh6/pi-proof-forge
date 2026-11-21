"""任务执行器：预算、重试边界与状态语义。"""
import json
from urllib.request import Request

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


def _request(payload):
    return Request("http://localhost/v1/chat/completions",
                   data=json.dumps(payload, ensure_ascii=False).encode(), method="POST")


def test_budget_rejects_oversized_payload():
    contract = _contract(max_input_chars=20)
    reason = check_budget(contract, _request({"a": "x" * 100}))
    assert reason.startswith("input_budget_exceeded")


def test_budget_passes_normal_payload():
    assert check_budget(SEMANTIC_MATCHING, _request({"a": "b"})) == ""


def test_execute_returns_complete_on_valid_output():
    run = execute(
        SEMANTIC_MATCHING,
        model="m",
        prepare=lambda: _request({"a": 1}),
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
        SEMANTIC_MATCHING, model="m", prepare=lambda: _request({}), call=call,
        extract=lambda r: r["choices"][0]["message"]["content"],
        validate=lambda parsed: parsed,
    )
    assert run.status == "complete" and run.attempts == 2


def test_repeated_invalid_json_ends_unavailable_not_partial():
    run = execute(
        SEMANTIC_MATCHING, model="m", prepare=lambda: _request({}),
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
        SEMANTIC_MATCHING, model="m", prepare=lambda: _request({}), call=call,
        extract=lambda r: "",
        validate=lambda parsed: parsed,
    )
    assert run.status == "unavailable" and run.reason_code == "model_unavailable"
    assert calls["n"] == 1  # 服务不可用不重试：重试只会拖长等待


def test_timeout_maps_to_timeout_reason():
    def call(_p):
        raise TimeoutError("slow")

    run = execute(
        SEMANTIC_MATCHING, model="m", prepare=lambda: _request({}), call=call,
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


_BUDGET_FACT = '仅在本机隔离环境，以固定合成请求验证 "重试协议"；路径标签为 local\\sample。\n结论不代表生产容量。'
_BUDGET_SCHEMA = {
    "type": "object", "properties": {"ok": {"type": "boolean", "description": "合成事实是否按原条件核对"}},
    "required": ["ok"], "additionalProperties": False,
}


def _budget_payload():
    return {
        "model": "synthetic-budget-model", "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "核对完整合成事实，只返回 JSON。"},
            {"role": "user", "content": json.dumps(
                {"facts": {"synthetic:results:0": {"text": _BUDGET_FACT}}}, ensure_ascii=False,
            )},
        ],
    }


def _budget_http_client(monkeypatch, provider="openai_compatible"):
    import io
    from tools.infra.llm.client import LLMClient

    requests = []
    responses = []

    def open_request(req, **kwargs):
        requests.append(req)
        content = responses.pop(0) if responses else '{"ok":true}'
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", open_request)
    client = LLMClient("http://127.0.0.1:8000/v1", "", provider=provider, thinking_enabled=False)
    return client, requests, responses


def _logical_request_chars(req):
    return len(json.dumps(json.loads(req.data), ensure_ascii=False))


def _require_true(parsed):
    if parsed.get("ok") is not True:
        raise ValueError("synthetic_output_requires_true")
    return parsed


def _execute_http(contract, client, payload, *, on_retry=None):
    # Exercise the current runner and real client injection; only the HTTP boundary is synthetic.
    def prepare(body):
        return client.prepare_request(client.chat_completions_url, body, response_schema=_BUDGET_SCHEMA)

    return execute(
        contract, model=payload["model"], prepare=lambda: prepare(payload), call=client.send_request,
        extract=client.extract_content, validate=_require_true,
        on_retry=(lambda request, exc: prepare(on_retry(payload, exc))) if on_retry is not None else None,
    )


@pytest.mark.parametrize("provider", ["openai_compatible", "lm_studio"])
def test_budget_counts_complete_request_logical_json_and_preserves_fact(monkeypatch, provider):
    import copy

    payload = _budget_payload()
    original = copy.deepcopy(payload)
    client, requests, _ = _budget_http_client(monkeypatch, provider)
    client.post_json(client.chat_completions_url, payload, response_schema=_BUDGET_SCHEMA)
    baseline, = requests
    size = _logical_request_chars(baseline)
    sent = json.loads(baseline.data)
    assert len(json.dumps(payload, ensure_ascii=False)) < size < len(baseline.data)
    assert "PiProofForge" in sent["messages"][0]["content"]
    assert sent["messages"][-1] == payload["messages"][-1]
    assert json.loads(sent["messages"][-1]["content"])["facts"]["synthetic:results:0"]["text"] == _BUDGET_FACT
    if provider == "lm_studio":
        assert sent["response_format"]["json_schema"]["schema"] == _BUDGET_SCHEMA
    else:
        assert json.dumps(_BUDGET_SCHEMA, ensure_ascii=False, sort_keys=True) in sent["messages"][0]["content"]
        assert sent["reasoning_effort"] == "none"
    requests.clear()

    run = _execute_http(_contract(max_input_chars=size), client, payload)
    assert (run.status, run.attempts, len(requests)) == ("complete", 1, 1)
    assert json.loads(requests[0].data) == sent
    requests.clear()
    refused = _execute_http(_contract(max_input_chars=size - 1), client, payload)
    assert (refused.status, refused.reason_code, refused.attempts, len(requests)) == (
        "unavailable", "input_budget_exceeded", 0, 0,
    )
    assert payload == original


@pytest.mark.parametrize("blocked", [True, False])
def test_repair_budget_is_checked_before_another_http_attempt(monkeypatch, blocked):
    payload = _budget_payload()
    client, requests, responses = _budget_http_client(monkeypatch)
    client.post_json(client.chat_completions_url, payload, response_schema=_BUDGET_SCHEMA)
    initial_size = _logical_request_chars(requests[0])
    requests.clear()
    responses[:] = ['{"ok":false}', '{"ok":true}']

    def repair(body, exc):
        return {**body, "messages": [
            *body["messages"], {"role": "assistant", "content": '{"ok":false}'},
            {"role": "user", "content": "完整保留原事实及限定。" + "修复说明" * 1000},
        ]}

    run = _execute_http(
        _contract(max_input_chars=initial_size if blocked else 24_000), client, payload, on_retry=repair,
    )
    expected = ("unavailable", "input_budget_exceeded", 1, 1) if blocked else ("complete", "", 2, 2)
    assert (run.status, run.reason_code, run.attempts, len(requests)) == expected
    assert json.loads(requests[0].data)["messages"][-1] == payload["messages"][-1]
    if not blocked:
        assert all(_logical_request_chars(req) <= 24_000 for req in requests)
        assert json.loads(requests[1].data)["messages"][1] == payload["messages"][1]


@pytest.mark.parametrize("invalid", ["object", "cycle"])
def test_unserializable_initial_request_is_local_invalid_request_without_attempt(monkeypatch, invalid):
    payload = _budget_payload()
    payload["unserializable"] = object() if invalid == "object" else payload
    client, requests, _ = _budget_http_client(monkeypatch)
    run = _execute_http(SEMANTIC_MATCHING, client, payload)
    assert (run.status, run.reason_code, run.attempts, len(requests)) == (
        "unavailable", "invalid_request", 0, 0,
    )


@pytest.mark.parametrize("invalid", ["serialization", "construction"])
def test_invalid_repair_request_does_not_resend_original_or_count_an_attempt(monkeypatch, invalid):
    payload = _budget_payload()
    client, requests, responses = _budget_http_client(monkeypatch)
    responses[:] = ['{"ok":false}', '{"ok":true}']

    def repair(body, exc):
        if invalid == "construction":
            raise RuntimeError("synthetic_request_construction_failed")
        return {**body, "unserializable": object()}

    run = _execute_http(SEMANTIC_MATCHING, client, payload, on_retry=repair)
    assert (run.status, run.reason_code, run.attempts, len(requests)) == (
        "unavailable", "invalid_request", 1, 1,
    )


def test_budget_and_transport_use_same_prepared_request_without_reinjection(monkeypatch):
    import copy

    payload = _budget_payload()
    original = copy.deepcopy(payload)
    client, requests, _ = _budget_http_client(monkeypatch)
    prepared = client.prepare_request(client.chat_completions_url, payload, response_schema=_BUDGET_SCHEMA)
    accepted_url, accepted_data = prepared.full_url, prepared.data
    assert payload == original and requests == []
    payload["messages"][-1]["content"] = "changed after preparation"
    client._base_url = "http://127.0.0.1:9999/v1"
    monkeypatch.setattr("tools.infra.llm.client.with_job_search_context",
                        lambda body: pytest.fail("Sending an accepted Request must not inject context again"))
    run = execute(
        _contract(max_input_chars=_logical_request_chars(prepared)), model="synthetic-budget-model",
        prepare=lambda: prepared, call=client.send_request,
        extract=client.extract_content, validate=_require_true,
    )
    assert (run.status, run.attempts, len(requests)) == ("complete", 1, 1)
    assert requests[0] is prepared
    assert (prepared.full_url, prepared.data) == (accepted_url, accepted_data)
    sent = json.loads(prepared.data)
    assert json.loads(sent["messages"][-1]["content"])["facts"]["synthetic:results:0"]["text"] == _BUDGET_FACT
