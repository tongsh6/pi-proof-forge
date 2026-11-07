"""受控改写的生成引擎：模板为事实基线，改写只允许措辞，违规回退。

事实保真校验不依赖提示词：数字与英文实体集合必须原样保留、长度变化有界，
任何违规或空响应都回退模板基线（回退即安全）。
"""

from __future__ import annotations

import pytest

from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.engines.generation.llm_rewriter import LLMRewriter


class FakeClient:
    chat_completions_url = "http://fake/v1/chat/completions"

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def post_json(self, url: str, payload: dict) -> dict:
        self.calls += 1
        return {"choices": [{"message": {"content": self.content}}]}

    @staticmethod
    def extract_content(response: dict) -> str:
        return response["choices"][0]["message"]["content"]


def _card() -> EvidenceCard:
    return EvidenceCard(
        id="ec-1",
        title="订单链路优化",
        raw_source="materials/worklog.md",
        results=("接口 P95 从 1200ms 降至 300ms",),
        artifacts=("性能报告.pdf",),
        actions=("重构异步队列，削峰填谷",),
        period="2024-01 ~ 2024-06",
        context="大促期间订单峰值压力",
        role_scope="模块负责人",
    )


def _report() -> MatchingReport:
    return MatchingReport(
        job_profile_id="jp-1",
        evidence_card_ids=("ec-1",),
        score_breakdown={"total": 0.6},
        gap_tasks=(),
    )


def _engine(content: str, **kwargs) -> LLMRewriter:
    return LLMRewriter(FakeClient(content), "test-model", **kwargs)


def test_generate_accepts_rewrite_that_preserves_numbers_and_entities():
    baseline = _engine("占位")._baseline(_report(), [_card()], "A")
    rewritten = baseline.content.replace("削峰填谷", "峰值削峰与填谷")
    engine = _engine(rewritten)
    result = engine.generate(_report(), [_card()], "A")
    assert result.content == rewritten
    assert result.version == "A"
    assert "1200ms" in result.content and "300ms" in result.content


def test_generate_falls_back_when_rewrite_adds_new_number():
    baseline = _engine("占位")._baseline(_report(), [_card()], "A")
    engine = _engine(baseline.content + "\n- 团队规模 50 人")
    result = engine.generate(_report(), [_card()], "A")
    assert result.content == baseline.content
    assert "团队规模 50 人" not in result.content


def test_generate_falls_back_when_rewrite_drops_number():
    baseline = _engine("占位")._baseline(_report(), [_card()], "A")
    engine = _engine(baseline.content.replace("1200ms", "较慢"))
    result = engine.generate(_report(), [_card()], "A")
    assert result.content == baseline.content


def test_generate_falls_back_when_rewrite_adds_new_english_entity():
    baseline = _engine("占位")._baseline(_report(), [_card()], "A")
    engine = _engine(baseline.content + "\n- 使用 Kubernetes 部署")
    result = engine.generate(_report(), [_card()], "A")
    assert result.content == baseline.content


def test_generate_falls_back_on_empty_response():
    baseline = _engine("占位")._baseline(_report(), [_card()], "A")
    engine = _engine("   ")
    result = engine.generate(_report(), [_card()], "A")
    assert result.content == baseline.content


def test_generate_falls_back_when_length_changes_excessively():
    baseline = _engine("占位")._baseline(_report(), [_card()], "A")
    engine = _engine("短")
    result = engine.generate(_report(), [_card()], "A")
    assert result.content == baseline.content


def test_generate_requires_eligible_cards():
    from tools.domain.invariants import FabricationGuardError

    with pytest.raises(FabricationGuardError):
        _engine("x").generate(_report(), [], "A")


def test_rewriter_keeps_legacy_rewrite_contract():
    resume = ResumeOutput("A", "jp", "# 张三\n- 参与改造\n", "markdown")
    engine = LLMRewriter(FakeClient("# 张三\n- 推动改造\n"), "m")
    result = engine.rewrite(resume, "jd", "company")
    assert result.content == "# 张三\n- 推动改造\n"
