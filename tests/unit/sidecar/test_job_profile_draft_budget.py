import json
from io import BytesIO

import pytest

from tools.sidecar.handlers import jobs
from tools.infra.llm.task_contract import JOB_PROFILE_DRAFT


@pytest.fixture
def invocation(monkeypatch):
    config = dict(provider='openai_compatible', model='local/Q4-PLE4',
                  base_url='http://127.0.0.1:8000/v1', api_key_for_request='',
                  timeout=600, temperature=0.7, thinking_enabled=False, thinking_effort='high')
    monkeypatch.setattr(jobs.settings_handler, '_load_llm_config', lambda: dict(config))
    calls = []
    response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
        'target_role': 'Python engineer', 'must_have': ['Python'], 'keywords': ['Python'],
        'jd_summary': 'Develop Python APIs'})}}]}
    def open_request(req, **kwargs):
        calls.append((json.loads(req.data), {}))
        return BytesIO(json.dumps(response).encode())
    monkeypatch.setattr('tools.infra.llm.client.request.urlopen', open_request)
    def run():
        return jobs.handle_jobs_generate_profile_draft({'meta': {'correlation_id': 'budget-test'},
                                                       'jd_text': 'Python engineer builds APIs.'})
    return config, calls, response, run


def test_explicit_off_json_request_uses_contract_budget_without_thinking(invocation):
    config, calls, _, run = invocation
    result = run()
    assert len(calls) == 1
    payload, kwargs = calls[0]
    assert payload['max_tokens'] == JOB_PROFILE_DRAFT.capability.max_output_tokens
    assert payload['reasoning_effort'] == 'none'
    assert payload['response_format'] == {'type': 'json_object'}
    assert config['thinking_enabled'] is False
    assert result['draft'] is not None and result['active_target_eligible'] is False


def test_explicit_control_survives_model_alias_change(invocation):
    config, calls, _, run = invocation
    config['model'] = 'another-local-quantization'
    run()
    assert calls[0][0]['reasoning_effort'] == 'none'


@pytest.mark.parametrize('changes', [
    {'base_url': 'https://remote.example/v1'}, {'base_url': 'http://127.0.0.1:1234/v1'}, {'provider': 'openai'},
])
def test_provider_default_does_not_infer_control_from_deployment(invocation, changes):
    config, calls, _, run = invocation
    config.update(changes)
    config['thinking_enabled'] = None
    run()
    assert 'reasoning_effort' not in calls[0][0]
    assert calls[0][0]['max_tokens'] == JOB_PROFILE_DRAFT.capability.max_output_tokens


def test_truncated_even_valid_json_is_not_provider_failure_or_usable(invocation):
    _, calls, response, run = invocation
    response['choices'][0]['finish_reason'] = 'length'
    result = run()
    assert len(calls) == 1
    assert result['code'] == 'output_truncated'
    assert result['status'] == 'parse_output_truncated'
    assert result['draft'] is None and result['active_target_eligible'] is False
    assert 'JD' in result['message']

@pytest.mark.parametrize("mode,expected", [(None, None), (False, "none"), (True, "high")])
def test_request_control_from_jd_configuration_preserves_budget_and_mode(invocation, mode, expected):
    config, calls, _, run = invocation
    config["thinking_enabled"] = mode
    original = dict(config)
    result = run()
    assert result["draft"] is not None and result["active_target_eligible"] is False
    assert len(calls) == 1
    payload = calls[0][0]
    assert payload["max_tokens"] == JOB_PROFILE_DRAFT.capability.max_output_tokens
    assert payload["response_format"] == {"type": "json_object"}
    assert "thinking" not in payload
    assert config == original
    if expected is None:
        assert "reasoning_effort" not in payload
    else:
        assert payload.get("reasoning_effort") == expected
