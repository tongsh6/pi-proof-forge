"""D1/D2/D4：按可信等级降级措辞、首屏组织与 trace 字段等级。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.domain.models import EvidenceCard, JobProfile, ResumeOutput
from tools.engines.generation import template_assembler as ta
from tools.engines.generation.llm_rewriter import LLMRewriter
from tools.engines.generation.template_assembler import TemplateAssembler
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.run_generation import build_template_resume, load_cards


PROFILE = {
    "name": "测试候选人", "phone": "13800000000", "email": "a@b.com", "city": "上海",
    "current_position": "平台负责人",
    "career": {"summary": "负责平台架构与交付。", "work": [], "education": [],
               "education_visibility": "omit", "skills": [], "extras": []},
}
JOB = {"target_role": "平台负责人", "company": "示例科技", "keywords": []}


def card(card_id, *, title, time_range, role_scope, time_level=None, role_level=None,
         precision="month", actions=(), results=()):
    value = {
        "id": card_id, "title": title, "time_range": time_range, "role_scope": role_scope,
        "context": title + "背景", "actions": list(actions) or [title + "动作"],
        "results": list(results) or [title + "结果"], "stack": ["Java"], "artifacts": ["报告.pdf"],
        "source_sha256": "x",
    }
    if time_level:
        value["time_range_level"] = time_level
        if time_level in {"L2", "L3"}:
            value["time_range_provenance"] = {
                "level": time_level, "precision": precision, "confidence": 0.6,
                "evidence": [{"material_id": "mat_1", "document_id": "doc_1",
                              "excerpt": "2022 年以来持续投入"}]}
    if role_level:
        value["role_scope_level"] = role_level
        if role_level == "L3":
            value["role_scope_provenance"] = {
                "level": "L3", "confidence": 0.6,
                "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "excerpt": "我推动改造"}],
                "first_person_hits": {"owner": 2, "participant": 3}}
    return value


def test_format_time_role_text_and_downgrade_rules():
    assert ta.format_time("2021-03 ~ 2024-03", "L1", "day") == "2021-03 ~ 2024-03"
    assert ta.format_time("2022-03 ~ 2022-09", "L3", "year") == "2022"
    assert ta.format_time("2022-03", "L5", "month") == ""
    assert ta.role_text("平台负责人", "L1") == "平台负责人"
    assert ta.role_text("平台负责人", "L3") == "参与 / 推动 · 平台负责人"
    assert ta.role_text("平台负责人", "L5") == ""
    assert ta.downgrade_wording("负责统一运动中心改造并主导上线", "L3") == "参与统一运动中心改造并推动上线"
    assert ta.downgrade_wording("负责统一运动中心改造", "L1") == "负责统一运动中心改造"
    assert ta.visible_in_resume(card("ec-2", title="无时间", time_range="", role_scope="", time_level="L5")) is False


def test_build_template_resume_applies_levels_first_screen_and_trace_provenance():
    cards = [
        card("ec-1", title="交易服务重构", time_range="2021-03 ~ 2024-03", role_scope="负责人"),
        card("ec-2", title="统一运动中心", time_range="2022-03 ~ 2022-09", role_scope="平台负责人",
             time_level="L3", role_level="L3", precision="year",
             actions=["负责统一运动中心改造", "推动活动报名聚合"],
             results=["主导会员中心上线"]),
        card("ec-3", title="无时间项目", time_range="", role_scope="", time_level="L5"),
    ]
    semantic = {
        "facts": {"f1": {"source_id": "ec-2"}},
        "assessments": [{"requirement_id": "d1", "citations": [{"fact_id": "f1"}]}],
    }
    claims: list[dict] = []
    content = build_template_resume(
        "A", "mr-1", 80, "now", cards, personal_profile=PROFILE, job_context=JOB,
        claims=claims, semantic_report=semantic,
    )
    # JD 引用的 L3 卡优先，且 L5 卡不进入正文。
    assert "无时间项目" not in content
    assert content.index("统一运动中心") < content.index("交易服务重构")
    # 年精度只呈现年；L3 角色与动作/结果降级。
    assert "### 统一运动中心（2022）" in content
    assert "角色：参与 / 推动 · 平台负责人" in content
    segment = content[content.index("统一运动中心"):content.index("交易服务重构")]
    assert "- 负责" not in segment and "主导" not in segment
    assert "参与统一运动中心改造" in segment and "推动会员中心上线" in segment
    # 首屏标记位于第一条经历之后：第一条经历 bullet 在首屏内。
    first, rest = content.split(FIRST_SCREEN_MARKER)
    assert "统一运动中心" in first and "交易服务重构" in rest
    # trace claims 带字段等级与依据。
    time_claim = next(item for item in claims if item["field"] == "time_range" and item["evidence_id"] == "ec-2")
    role_claim = next(item for item in claims if item["field"] == "role_scope" and item["evidence_id"] == "ec-2")
    assert time_claim["text"] == "2022"
    assert time_claim["provenance"]["level"] == "L3" and time_claim["provenance"]["precision"] == "year"
    assert role_claim["provenance"]["level"] == "L3"
    assert role_claim["provenance"]["first_person_hits"] == {"owner": 2, "participant": 3}


def test_load_cards_reads_provenance_levels(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ec-l3.yaml").write_text(
        'id: "ec-l3"\ntitle: "统一运动中心"\ntime_range: "2022"\ncontext: "背景"\nrole_scope: "平台负责人"\n'
        'time_range_provenance_json: \'{"level":"L3","precision":"year","evidence":[{"material_id":"mat_1","document_id":"doc_1","excerpt":"2022 年持续投入"}]}\'\n'
        'role_scope_provenance_json: \'{"level":"L3","evidence":[{"material_id":"mat_1","document_id":"doc_1","excerpt":"我推动改造"}]}\'\n'
        'actions:\n  - "负责改造"\nresults:\n  - "上线"\nartifacts:\n  - "报告.pdf"\n',
        encoding="utf-8",
    )
    cards = load_cards(evidence, ["ec-l3"])
    assert cards[0]["time_range_level"] == "L3"
    assert cards[0]["role_scope_level"] == "L3"
    assert cards[0]["time_range_provenance"]["precision"] == "year"


class FakeClient:
    chat_completions_url = "http://fake/v1/chat/completions"

    def __init__(self, content):
        self.content = content

    def post_json(self, url, payload):
        return {"choices": [{"message": {"content": self.content}}]}

    @staticmethod
    def extract_content(response):
        return response["choices"][0]["message"]["content"]


def test_rewriter_detects_role_strength_and_time_precision_violations():
    original = "# 张三\n\n## 项目经历\n### 统一运动中心（2022）\n角色：参与 / 推动 · 平台负责人\n- 参与统一运动中心改造\n"
    resume = ResumeOutput("A", "jp", original, "markdown")
    stronger = original.replace("参与统一运动中心改造", "负责统一运动中心改造")
    result = LLMRewriter(FakeClient(stronger), "m").rewrite(
        resume, "jd", "company", level_context={"max_role_level": "L3", "time_precision": "year"})
    assert result.content == original
    more_precise = original.replace("（2022）", "（2022-03）")
    result = LLMRewriter(FakeClient(more_precise), "m").rewrite(
        resume, "jd", "company", level_context={"max_role_level": "L3", "time_precision": "year"})
    assert result.content == original
    safe = original.replace("参与统一运动中心改造", "推动统一运动中心改造")
    result = LLMRewriter(FakeClient(safe), "m").rewrite(
        resume, "jd", "company", level_context={"max_role_level": "L3", "time_precision": "year"})
    assert result.content == safe


def test_template_assembler_engine_uses_levels():
    from tools.domain.models import MatchingReport
    card_l3 = EvidenceCard(id="ec-2", title="统一运动中心", raw_source="m", results=("系统上线完成",),
                           artifacts=("报告.pdf",), period="2022-03 ~ 2022-09", context="背景", role_scope="平台负责人")
    with_provenance = EvidenceCard(
        id="ec-2", title="统一运动中心", raw_source="m", results=("系统上线完成",), artifacts=("报告.pdf",),
        period="2022-03 ~ 2022-09", context="背景", role_scope="平台负责人",
        time_range_provenance={"level": "L3", "precision": "year", "evidence": [{"material_id": "m", "document_id": "d", "excerpt": "2022"}]},
        role_scope_provenance={"level": "L3", "evidence": [{"material_id": "m", "document_id": "d", "excerpt": "我推动"}]},
    )
    report = MatchingReport("jp", ("ec-2",), {}, ())
    content = TemplateAssembler().generate(report, [with_provenance], "A").content
    assert "（2022）" in content and "2022-03" not in content
    assert "参与 / 推动 · 平台负责人" in content
    assert "系统上线完成" in content
    # 显式 L5 时间卡不得进入正文；旧数据（无 provenance）保持兼容。
    empty_time = EvidenceCard(id="ec-3", title="无时间", raw_source="m", results=("结果",),
                              artifacts=("报告.pdf",),
                              time_range_provenance={"level": "L5", "evidence": []})
    with pytest.raises(Exception):
        TemplateAssembler().generate(report, [empty_time], "A")
    legacy = EvidenceCard(id="ec-4", title="旧卡", raw_source="m", results=("结果",),
                          artifacts=("报告.pdf",))
    assert "旧卡" in TemplateAssembler().generate(report, [legacy], "A").content
