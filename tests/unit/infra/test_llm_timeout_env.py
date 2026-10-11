"""管线各 LLM 阶段的超时来自 App 系统设置下发的 LLM_TIMEOUT。"""
import pytest

from tools.infra.llm.client import llm_timeout_from_env


@pytest.mark.parametrize("raw,expected", [("600", 600), ("", 120), ("abc", 120), ("0", 120), ("-5", 120)])
def test_timeout_from_env_with_fallback(monkeypatch, raw, expected):
    monkeypatch.setenv("LLM_TIMEOUT", raw)
    assert llm_timeout_from_env() == expected


def test_timeout_default_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    assert llm_timeout_from_env() == 120
    assert llm_timeout_from_env(300) == 300
