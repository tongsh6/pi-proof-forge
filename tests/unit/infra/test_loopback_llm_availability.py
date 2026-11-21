"""配置门禁回归，无网络调用。"""
import pytest
from tools.infra.llm.client import llm_request_available
from tools.orchestration.pipeline import has_llm_env

GOOD = ["http://127.0.0.1:8000/v1", "https://localhost/v1", "http://[::1]:8000/v1"]
BAD = ["", "http://localhost.evil/v1", "http://127.0.0.1.evil/v1",
       "http://user@localhost/v1", "http://localhost:bad/v1", "http://localhost:65536/v1",
       "http://localhost:/v1", "http://localhost:0/v1", "ftp://localhost/v1",
       "//localhost/v1", "http://127.1/v1", "http://2130706433/v1",
       "http://localhost\\@evil/v1", "http://local\nhost/v1",
       "http://[::1/v1", "http://remote.example/v1"]

@pytest.mark.parametrize("url", GOOD)
def test_explicit_loopback_compatible_is_keyless(url):
    assert llm_request_available(provider="openai_compatible", model="local", base_url=url)

@pytest.mark.parametrize("url", BAD)
def test_invalid_or_remote_without_key_is_not_available(url):
    assert not llm_request_available(provider="openai_compatible", model="local", base_url=url)

def test_model_required_and_remote_key_preserved():
    assert not llm_request_available(provider="openai_compatible", model=" ", base_url=GOOD[0])
    assert llm_request_available(provider="openai_compatible", model="local", api_key="example", base_url=BAD[-1])
    assert not llm_request_available(provider="openai", model="local", base_url=GOOD[0])

def test_explicit_remote_is_not_overridden_by_loopback_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", GOOD[0])
    assert not llm_request_available(provider="openai_compatible", model="local", base_url=BAD[-1])
    assert not llm_request_available(provider="openai_compatible", model="local")

def test_pipeline_passes_actual_environment_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "local")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", GOOD[0])
    assert has_llm_env()
    monkeypatch.setenv("LLM_BASE_URL", BAD[-1])
    assert not has_llm_env()

def test_flow_gates_use_config_url_not_environment(monkeypatch):
    from types import SimpleNamespace
    from tools.orchestration import generation_flow, matching_flow
    from tools.infra.llm import client

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", GOOD[0])
    seen = []
    def availability(**kwargs):
        seen.append(kwargs["base_url"])
        return llm_request_available(**kwargs)
    monkeypatch.setattr(client, "llm_request_available", availability)
    config = SimpleNamespace(model="local", api_key="", base_url=BAD[-1], require_llm=True)
    with pytest.raises(ValueError, match="llm_configuration_missing"):
        generation_flow._llm_select_cards(
            config, report_text="", cards=[], profile={}, target={}, version="A"
        )
    assert matching_flow._run_semantic(config, []) == 1
    assert seen == [BAD[-1], BAD[-1]]

