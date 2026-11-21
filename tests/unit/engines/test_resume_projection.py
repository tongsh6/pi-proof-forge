"""共享正文入口使用现行FactIndex/plan，不保留preferred_facts第二通道。"""
from copy import deepcopy
import json

import pytest

from tests.unit.engines.test_fact_index import reviewed_card_results
from tests.unit.engines.test_generation_engines import RESULT, generation

from tools.engines.generation.resume_renderer import build_template_resume
from tools.engines.generation.fact_index import build_fact_index
from tools.engines.evaluation.tiers.common import inspect_bullet_trace


def inputs():
    profile = {"name": "合成候选人", "career": {
        "summary": "参与接口联调，但不负责整体架构。",
        "work": [{"id": "w1", "company": "合成任职公司", "title": "工程师",
                  "start": "2021-03", "end": "", "current": True, "scope": "平台接口与联调",
                  "contributions": ["完成测试数据与接口对接"], "evidence_ids": ["ec-projection"]}],
        "education_visibility": "omit", "education": [], "skills": [], "extras": []}}
    card = {"id": "ec-projection", "title": "消息队列", "time_range": "2024-01 ~ 2024-06",
            "role_scope": "接口对接负责人", "context": "性能数据来自本机验证，不是生产指标。",
            "actions": ["完成消费端与平台订阅接口接入", "设计合成请求回归用例"],
            "results": ["在本机测试环境中，1000 条请求处理耗时由 38 秒降到 6 秒。"],
            "stack": ["Java", "Docker Swarm"], "artifacts": ["合成验收记录"]}
    return profile, reviewed_card_results(card, measurement_quotes={0: card["results"][0]})


def test_shared_body_preserves_ownership_and_environment():
    profile, card = inputs()
    claims = []
    text = build_template_resume("A", [card], personal_profile=profile, claims=claims)
    assert profile["career"]["summary"] in text
    assert card["role_scope"] in text and card["context"] in text
    assert card["results"][0] in text and "Docker Swarm" in text
    assert "所属工作：合成任职公司" in text
    assert "消息队列" in text and "合成任职公司" in text
    assert all(claim["text"] in text for claim in claims)


def test_scope_exclusion_preserves_sibling_original_index_and_occurrence():
    profile, card = inputs()
    card["actions"].append("对接同事交付的订阅接口")
    card["personal_claim_exclusions"] = {"ec-projection:actions:1"}
    claims = []
    text = build_template_resume("A", [card], personal_profile=profile, claims=claims)
    assert card["actions"][1] not in text
    assert card["actions"][0] in text and card["actions"][2] in text
    row, = [c for c in claims if c.get("fact_id") == "ec-projection:actions:2"]
    assert row["text"] == card["actions"][2]
    assert row["text"] in text.splitlines()[row["render_line"] - 1]


def test_partial_child_support_does_not_grant_negative_fact_weight():
    _, card = inputs()
    report = {"requirements": [{"id": "r1"}], "assessments": [{
        "requirement_id": "r1", "status": "partial",
        "citations": [{"fact_id": "ec-projection:actions:0"}, {"fact_id": "ec-projection:actions:1"}],
        "checks": [
            {"status": "supported", "citations": [{"fact_id": "ec-projection:actions:0"}]},
            {"status": "insufficient", "citations": [{"fact_id": "ec-projection:actions:1"}]},
        ]}]}
    index = build_fact_index([card], {}, report)
    assert index.get("ec-projection:actions:0").support_weight > 0
    assert index.get("ec-projection:actions:1").support_weight == 0


def test_body_only_claims_actual_facts_and_keeps_every_full_condition():
    profile, card = inputs()
    original = deepcopy(card)
    claims = []
    text = build_template_resume("B", [card], personal_profile=profile, claims=claims)
    assert card == original
    trace = {"occurrence_lineage_version": 1, "claims": claims}
    checked = inspect_bullet_trace(text, trace)
    assert checked["verified_bullets"] == checked["total_bullets"]
    result, = [c for c in claims if c.get("fact_id") == "ec-projection:results:0"]
    assert result["text"] == original["results"][0]
    assert text.count(result["text"]) == 1


# The trailing ownership and environment constraints are beyond the former display limit.
FULL_PROJECT_CONTEXT = (
    "本项目面向订单处理和库存同步的接口验收，调用链覆盖请求校验、重复消息处理、超时重试与失败回滚。"
    "开发记录按接口契约、联调日志和回归用例分别归档，验收人员核对每次执行的输入数据、响应内容及日志关联。"
    "部署与观测采用独立的合成任务，不包含客户流量，也不代表生产容量。"
    "本人仅承担接口实现与联调，不负责生产发布；所有结果只适用于隔离测试环境下的固定负载。"
)
PROJECT_CONTEXT_TAIL = "本人仅承担接口实现与联调，不负责生产发布；所有结果只适用于隔离测试环境下的固定负载。"


def test_shared_builder_preserves_full_project_context_and_selected_result():
    _, card = inputs()
    card["context"] = FULL_PROJECT_CONTEXT
    original = deepcopy(card)
    assert card["context"].index(PROJECT_CONTEXT_TAIL) > 120
    claims = []
    markdown = build_template_resume("B", [card], claims=claims)
    result, = [row for row in claims if row.get("fact_id") == "ec-projection:results:0"]
    assert markdown.splitlines()[result["render_line"] - 1] == "- " + card["results"][0]
    assert result["text"] == card["results"][0]
    assert result["field"] == "results" and result["evidence_id"] == card["id"]
    background, = [row for row in claims if row.get("field") == "context"]
    assert background["text"] in markdown
    assert card == original
    assert "背景：" + FULL_PROJECT_CONTEXT in markdown
    assert background["text"] == FULL_PROJECT_CONTEXT


@pytest.mark.parametrize("review", ("measured", "nonquant", "unreviewed"))
def test_same_text_project_context_never_lends_result_identity_or_measurement(review):
    from tools.engines.evaluation.tiers.common import load_quality_config
    from tools.engines.evaluation.tiers.strong import evaluate_strong
    from tools.engines.matching.semantic_review import resume_assessment

    _, card = inputs()
    value = card["results"][0]
    card["context"] = value
    if review == "unreviewed":
        card["result_reviews"] = {}
    else:
        card.pop("result_reviews")
        card = reviewed_card_results(card, measurement_quotes={0: value if review == "measured" else None})
    claims = []
    markdown = build_template_resume("A", [card], claims=claims)
    fact_id = card["id"] + ":results:0"
    rows = [row for row in claims if row.get("fact_id") == fact_id]
    expected_result = review != "unreviewed"
    assert len(rows) == int(expected_result)
    assert "背景：" + value in markdown
    background, = [row for row in claims if row.get("field") == "context"]
    assert background["text"] == value
    assert ("- " + value in markdown.splitlines()) is expected_result
    if rows:
        assert rows[0]["text"] == value
        assert markdown.splitlines()[rows[0]["render_line"] - 1] == "- " + value
    report = {
        "facts": {fact_id: {"source_id": card["id"], "field": "results", "text": value}},
        "requirements": [{"id": "r-result", "kind": "must_have", "text": "合成结果要求"}],
        "assessments": [{"requirement_id": "r-result", "status": "supported",
                         "citations": [{"fact_id": fact_id, "quote": value}]}],
    }
    assessment = resume_assessment(report, claims, occurrence_coverage_known=True)
    assert assessment["requirements"][0]["resume_status"] == ("supported" if expected_result else "not_present")
    quality = evaluate_strong(
        resume=markdown, cards={card["id"]: card},
        trace={"occurrence_lineage_version": 1, "claims": claims}, config=load_quality_config(),
    )
    assert quality.metrics["quant_total"] == pytest.approx(1 / 3 if review == "measured" else 0.0, abs=0.0001)


def test_merged_project_keeps_later_cards_background_without_result_borrowing():
    _, first = inputs()
    first["context"] = ""
    first["project_key"] = "共同接口验收项目"
    first["actions"] = ["完成请求解析与幂等校验接口实现"]
    second = {
        **deepcopy(first), "id": "ec-background", "context": "仅在隔离环境进行回归验收，尚未接入生产流量。",
        "actions": ["完成回归用例设计与边界条件核对"], "results": ["完成独立的回归验收报告。"],
    }
    second.pop("result_reviews")
    second = reviewed_card_results(second, measurement_quotes={0: None})
    claims = []
    markdown = build_template_resume("A", [first, second], claims=claims)
    actions = [row for row in claims if row.get("field") == "actions"]
    assert [row["evidence_id"] for row in actions] == [first["id"], second["id"]]
    assert "背景：" + second["context"] in markdown
    background, = [row for row in claims if row.get("field") == "context"]
    assert background["text"] == second["context"]
    result, = [row for row in claims if row.get("fact_id") == "ec-background:results:0"]
    assert markdown.splitlines()[result["render_line"] - 1] == "- " + second["results"][0]


def test_guided_generation_keeps_full_context_through_trace_and_actual_evaluation(generation):
    from tools.infra.persistence.review_snapshot import read_generation_trace
    from tools.orchestration.evaluation_flow import EvaluationFlowConfig, run_evaluation_flow

    assembler, identity, report, paths = generation
    raw = paths["card"].read_text()
    previous = 'context: "合成队列处理验收"'
    assert raw.count(previous) == 1
    paths["card"].write_text(raw.replace(previous, "context: " + json.dumps(FULL_PROJECT_CONTEXT, ensure_ascii=False)))
    before = paths["card"].read_bytes()
    assert FULL_PROJECT_CONTEXT.index(PROJECT_CONTEXT_TAIL) > 120
    resume = assembler.generate(report, [identity], "complete-context")
    root = paths["card"].parent.parent
    output = root / "synthetic-full-context.md"
    output.write_text(resume.content)
    output.with_suffix(".trace.json").write_text(json.dumps(resume.generation_trace))
    trace, valid = read_generation_trace(output)
    assert valid
    result, = [row for row in trace["claims"] if row.get("fact_id") == identity.id + ":results:0"]
    assert result["text"] == RESULT
    assert resume.content.splitlines()[result["render_line"] - 1] == "- " + RESULT
    quality_path = root / "synthetic-full-context-quality.md"
    assert run_evaluation_flow(EvaluationFlowConfig(
        input_path=output, output_path=quality_path, job_profile_path=paths["job"],
    )) == 0
    quality = json.loads(quality_path.with_suffix(".json").read_text())
    assert quality["traceability"]["status"] == "verified"
    assert quality["quality_report"]["tiers"]["strong"]["metrics"]["quant_total"] == 0.5
    assert quality["quality_report"]["auto_pass"] is False
    assert paths["card"].read_bytes() == before
    background, = [row for row in trace["claims"] if row.get("field") == "context"]
    assert "背景：" + FULL_PROJECT_CONTEXT in resume.content
    assert background["text"] == FULL_PROJECT_CONTEXT
