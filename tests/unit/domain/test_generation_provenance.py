"""职责表达保留已采纳范围，来源等级与确认记录仍可追溯。"""
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


def test_time_precision_and_adopted_role_rendering():
    assert ta.format_time("2021-03 ~ 2024-03", "L1", "day") == "2021-03 ~ 2024-03"
    assert ta.format_time("2022-03 ~ 2022-09", "L3", "year") == "2022"
    assert ta.format_time("2022-03", "L5", "month") == ""
    assert ta.role_text("平台负责人", "L1") == "平台负责人"
    assert ta.role_text("平台负责人", "L3") == "平台负责人"
    assert ta.role_text("平台负责人", "L5") == ""
    assert ta.downgrade_wording("负责统一运动中心改造并主导上线", "L3") == "负责统一运动中心改造并主导上线"
    assert ta.downgrade_wording("负责统一运动中心改造", "L1") == "负责统一运动中心改造"
    assert ta.visible_in_resume(card("ec-2", title="无时间", time_range="", role_scope="", time_level="L5")) is False


@pytest.mark.parametrize("text", ["非负责人，仅参与联调", "协助负责人完成上线", "不负责总体设计",
                                  "参与接口联调，由平台组负责总体设计"])
def test_l3_keeps_negation_and_other_peoples_responsibility(text):
    assert ta.role_text(text,"L3")==text


def test_l3_keeps_self_claim_and_exclusion_in_the_same_sentence():
    assert ta.role_text("主导接口联调，但不负责总体设计","L3")=="主导接口联调，但不负责总体设计"


@pytest.mark.parametrize("original,expected", [
    ("协助联调并主导架构设计","协助联调并主导架构设计"),
    ("协助负责人并独立负责上线","协助负责人并独立负责上线"),
])
def test_l3_keeps_mixed_assistance_and_ownership_scope(original,expected):
    assert ta.role_text(original,"L3")==expected

@pytest.mark.parametrize("version", ["A", "B"])
def test_inferred_role_keeps_adopted_scope_in_resume_and_trace_without_changing_source(version):
    original="主导或深度参与方案设计与核心开发"
    inferred=card("ec-inferred",title="售后服务",time_range="2023",role_scope=original,role_level="L3")
    claims=[]
    content=build_template_resume(version,"mr",80,"now",[inferred],
                                  personal_profile=PROFILE,job_context=JOB,claims=claims)
    role=next(c for c in claims if c["field"]=="role_scope")
    assert "角色：主导或深度参与方案设计与核心开发" in content
    assert role["text"]==original
    assert role["provenance"]["level"]=="L3"
    assert inferred["role_scope"]==original
    assert ta.role_text(original,"L1")==original
    assert ta.role_text(original,"L4")==original


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
    # 时间按精度显示；L3 来源等级不改变已采纳职责和原文行动。
    assert "### 统一运动中心（2022）" in content
    assert "角色：平台负责人" in content
    segment = content[content.index("统一运动中心"):content.index("交易服务重构")]
    assert "负责统一运动中心改造" in segment and "主导会员中心上线" in segment
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
    original = "# 张三\n\n## 项目经历\n### 统一运动中心（2022）\n角色：平台负责人\n- 参与统一运动中心改造\n"
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
    assert "平台负责人" in content
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


def test_action_result_pairing_requires_lexical_association_and_unique_use():
    from tools.engines.generation.template_assembler import pair_actions_results, paired_bullet_text

    pairs, unpaired_actions, unpaired_results = pair_actions_results(
        ["将核心存储迁移至 MongoDB", "修复聚合查询慢查询", "整理接口文档"],
        ["迁移后 20 万名单往返次数从 201,208 次降至 508 次",
         "慢查询 P95 从 2 秒降至 300 毫秒",
         "服务 6 个品牌"],
    )
    assert len(pairs) == 2
    assert unpaired_actions == ["整理接口文档"]
    assert unpaired_results == ["服务 6 个品牌"]
    used = set()
    for action, results in pairs:
        text = paired_bullet_text(action, results)
        assert action in text
        for result in results:
            assert result in text and result not in used
            used.add(result)


def test_generation_pairs_action_with_related_result_inside_first_screen():
    card = {
        "id": "ec-1", "title": "站内消息存储改造", "time_range": "2024 ~ 2025", "role_scope": "负责人",
        "context": "发送链改造。",
        "actions": ["将核心存储迁移至 MongoDB 并重写查询索引",
                    "对大名单发送链采用流式批量写入"],
        "results": ["慢查询 P95 从 2 秒降至 300 毫秒",
                    "20 万名单发送链往返次数从 201,208 次降至 508 次"],
        "stack": ["Java"], "artifacts": ["报告"],
    }
    claims: list[dict] = []
    text = build_template_resume("A", "r", 80, "now", [card], personal_profile={"career": {}}, claims=claims)
    first = text.split(FIRST_SCREEN_MARKER)[0]
    bullets = [line for line in first.splitlines() if line.startswith("- ")]
    assert bullets
    assert all("- " not in line or "：" in line for line in bullets)
    assert any(card["actions"][0] in line and card["results"][0] in line for line in bullets)
    from tools.engines.evaluation.tiered_evaluator import evaluate_strong
    from tools.engines.evaluation.tiered_evaluator import load_quality_config

    report = evaluate_strong(resume=text, cards={"ec-1": card}, trace={"claims": claims},
                             config=load_quality_config())
    assert report.metrics["quant_first_screen"] == 1.0


def test_work_history_responsibilities_render_without_achievement_bullets():
    profile = {
        "career": {
            "work": [{"id": "w1", "company": "示例公司", "title": "工程师", "start": "2020-01",
                      "end": "2024-01", "current": False, "scope": "交易平台",
                      "contributions": ["负责后端开发与接口联调"]}],
            "education_visibility": "omit", "education": [], "skills": [], "extras": [],
        }
    }
    text = build_template_resume("A", "r", 60, "now", [], personal_profile=profile,
                                 preferred_facts=[{"source_id": "personal_profile",
                                                   "field": "career.work.w1.contributions",
                                                   "text": "负责后端开发与接口联调"}] if False else None)
    assert "职责：负责后端开发与接口联调" in text
    work_section = text.split("## 工作经历", 1)[1].split("## ", 1)[0]
    assert not any(line.startswith("- ") for line in work_section.splitlines() if "接口联调" in line)


def test_first_screen_priority_orders_by_quantified_pairs_not_original_first_card():
    from tools.engines.generation.template_assembler import first_screen_priority

    context_only = {
        "id": "ec_context", "title": "微服务架构",
        "actions": ["使用 Spring Boot 构建微服务", "通过 HTTP/REST 通信"],
        "results": ["减少业务开发成本", "提高业务开发效率"],
    }
    quantified = {
        "id": "ec_quant", "title": "性能治理",
        "actions": ["执行慢查询改写与索引优化"],
        "results": ["门店预约列表查询 2–3s → 300–400ms"],
    }
    ordered = first_screen_priority([context_only, quantified])
    assert [card["id"] for card in ordered] == ["ec_quant", "ec_context"]
