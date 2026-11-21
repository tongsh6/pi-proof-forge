import copy
import json
from io import BytesIO

import pytest

from tools.infra.llm.client import LLMClient
from tools.infra.job_preferences import assess_direction


@pytest.fixture
def wire(monkeypatch):
    sent = []
    response = {'choices': [{'message': {'content': '{"ok":true}'}}]}
    def open_request(self, req):
        sent.append(json.loads(req.data))
        return BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(LLMClient, '_open_with_retry', open_request)
    return sent, response


def test_direction_uses_real_client_splash_policy(wire, tmp_path):
    sent, response = wire
    jd = 'Build Python backend APIs.'
    response['choices'][0]['message']['content'] = json.dumps({
        'status': 'aligned', 'reason': '后端职责相符', 'criterion_index': 0, 'jd_quote': jd})
    client = LLMClient('http://127.0.0.1:8000/v1/', '', provider='openai_compatible',
                       thinking_enabled=True)
    result = assess_direction({'revision': 'fixture', 'items': [
        {'kind': 'primary', 'text': 'Python backend'}]}, jd, client, 'new-model-alias', tmp_path)
    assert result['status'] == 'aligned' and result['model_calls'] == 1
    assert len(sent) == 1
    assert sent[0]['reasoning_effort'] == 'none'
    assert sent[0]['max_tokens'] == 800
    assert sent[0]['response_format'] == {'type': 'json_object'}


@pytest.mark.parametrize('base_url,provider,format,effort,expected', [
    ('http://127.0.0.1:8000/v1', 'openai_compatible', {'type':'json_object'}, None, 'none'),
    ('http://127.0.0.1:8000/v1', 'openai_compatible', {'type':'json_object'}, 'high', 'high'),
    ('http://127.0.0.1:8000/v1', 'openai_compatible', None, None, None),
    ('http://127.0.0.1:1234/v1', 'openai_compatible', {'type':'json_object'}, None, None),
    ('https://remote.example/v1', 'openai_compatible', {'type':'json_object'}, None, None),
    ('http://127.0.0.1:8000/v1', 'openai', {'type':'json_object'}, None, None),
])
def test_policy_scope_and_explicit_override(wire, base_url, provider, format, effort, expected):
    sent, _ = wire
    client = LLMClient(base_url, '', provider=provider, thinking_enabled=True)
    payload = {'model':'any-alias', 'messages':[{'role':'user','content':'Synthetic JSON test'}]}
    if format is not None:
        payload['response_format'] = format
    if effort is not None:
        payload['reasoning_effort'] = effort
    before = copy.deepcopy(payload)
    client.post_json(client.chat_completions_url, payload)
    assert sent[0].get('reasoning_effort') == expected
    assert payload == before
