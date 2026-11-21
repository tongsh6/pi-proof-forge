"""共享正文入口使用现行FactIndex/plan，不保留preferred_facts第二通道。"""
from copy import deepcopy
import hashlib
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
    assert background.get("source_kind") == "evidence"
    assert background.get("evidence_id") == card["id"]
    assert background.get("fact_id") == card["id"] + ":context:0"
    assert markdown.splitlines()[background["render_line"] - 1] == "背景：" + FULL_PROJECT_CONTEXT
    from tools.engines.matching.semantic_review import resume_assessment
    context_id = card["id"] + ":context:0"
    report = {
        "facts": {context_id: {"source_id": card["id"], "field": "context", "text": card["context"]}},
        "requirements": [{"id": "r-context", "kind": "must_have", "text": "合成场景要求"}],
        "assessments": [{"requirement_id": "r-context", "status": "supported",
                         "citations": [{"fact_id": context_id, "quote": card["context"]}]}],
    }
    assessment = resume_assessment(report, claims, occurrence_coverage_known=True)
    requirement, = assessment["requirements"]
    assert requirement["resume_status"] == "supported"
    assert requirement["citations"][0]["render_lines"] == [background["render_line"]]


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
    assert background.get("source_kind") == "evidence"
    assert background.get("evidence_id") == second["id"]
    assert background.get("fact_id") == second["id"] + ":context:0"
    assert markdown.splitlines()[background["render_line"] - 1] == "背景：" + second["context"]
    assert not any(row.get("fact_id") == first["id"] + ":context:0" for row in claims)


def test_guided_generation_keeps_full_context_through_trace_and_actual_evaluation(generation):
    from tools.infra.persistence.review_snapshot import read_generation_trace
    from tools.orchestration.evaluation_flow import EvaluationFlowConfig, run_evaluation_flow

    assembler, identity, report, paths = generation
    raw = paths["card"].read_text()
    previous = 'context: "合成队列处理验收"'
    assert raw.count(previous) == 1
    paths["card"].write_text(raw.replace(previous, "context: " + json.dumps("  " + FULL_PROJECT_CONTEXT + "  ", ensure_ascii=False)))
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
    assert background.get("source_kind") == "evidence"
    assert background.get("evidence_id") == identity.id
    assert background.get("fact_id") == identity.id + ":context:0"
    assert resume.content.splitlines()[background["render_line"] - 1] == "背景：" + FULL_PROJECT_CONTEXT



def test_same_text_backgrounds_only_cover_the_rendered_context_identity():
    from tools.engines.evaluation.tiers.common import load_quality_config
    from tools.engines.evaluation.tiers.strong import evaluate_strong
    from tools.engines.matching.semantic_review import resume_assessment

    _, first = inputs()
    value = first["results"][0]
    first.update(context=value, project_key="共同验收项目", results=[], result_reviews={})
    second = {
        **deepcopy(first), "id": "ec-other-context",
        "actions": ["完成独立的消费回执与异常处理联调"],
        "results": [value], "result_reviews": {},
    }
    claims = []
    markdown = build_template_resume("A", [first, second], claims=claims)
    assert markdown.splitlines().count("背景：" + value) == 1
    assert "- " + value not in markdown.splitlines()
    assert [row["evidence_id"] for row in claims if row.get("field") == "actions"] == [
        first["id"], first["id"], second["id"],
    ]
    identities = [
        (first["id"], "context", "r-used"),
        (second["id"], "context", "r-other-context"),
        (second["id"], "results", "r-unreviewed-result"),
    ]
    report = {
        "facts": {f"{source}:{field}:0": {"source_id": source, "field": field, "text": value}
                  for source, field, _ in identities},
        "requirements": [{"id": requirement, "kind": "must_have", "text": "合成精确引用"}
                         for _, _, requirement in identities],
        "assessments": [{"requirement_id": requirement, "status": "supported",
                         "citations": [{"fact_id": f"{source}:{field}:0", "quote": value}]}
                        for source, field, requirement in identities],
    }
    assessment = resume_assessment(report, claims, occurrence_coverage_known=True)
    statuses = {row["requirement_id"]: row["resume_status"] for row in assessment["requirements"]}
    assert statuses["r-other-context"] == "not_present"
    assert statuses["r-unreviewed-result"] == "not_present"
    quality = evaluate_strong(
        resume=markdown, cards={first["id"]: first, second["id"]: second},
        trace={"occurrence_lineage_version": 1, "claims": claims}, config=load_quality_config(),
    )
    assert quality.metrics["quant_total"] == 0.0
    assert statuses["r-used"] == "supported"


def test_trace_rejects_changed_background_even_when_original_text_remains_in_result(generation):
    from tools.infra.persistence.review_snapshot import read_generation_trace

    assembler, identity, report, paths = generation
    raw = paths["card"].read_text()
    previous = 'context: "合成队列处理验收"'
    assert raw.count(previous) == 1
    # The original scalar has harmless spacing; the body and source match use the normal display form.
    source_context = "  " + RESULT + "  "
    paths["card"].write_text(raw.replace(previous, "context: " + json.dumps(source_context, ensure_ascii=False)))
    before = paths["card"].read_bytes()
    resume = assembler.generate(report, [identity], "same-text-context")
    root = paths["card"].parent.parent
    output = root / "synthetic-same-text-context.md"
    output.write_text(resume.content)
    output.with_suffix(".trace.json").write_text(json.dumps(resume.generation_trace))
    trace, valid = read_generation_trace(output)
    assert valid
    lines = resume.content.splitlines()
    assert lines.count("背景：" + RESULT) == 1
    assert lines.count("- " + RESULT) == 1
    background_line = lines.index("背景：" + RESULT)
    result, = [row for row in trace["claims"] if row.get("fact_id") == identity.id + ":results:0"]
    assert lines[result["render_line"] - 1] == "- " + RESULT
    background, = [row for row in trace["claims"] if row.get("field") == "context"]
    assert background["text"] == RESULT

    changed_lines = list(lines)
    changed_lines[background_line] = "背景：" + RESULT.removeprefix("在隔离测试环境中，")
    assert changed_lines[background_line] != lines[background_line]
    changed_text = "\n".join(changed_lines) + ("\n" if resume.content.endswith("\n") else "")
    # A global substring check can still find the whole original statement in the result bullet.
    assert RESULT in changed_text
    assert changed_lines[result["render_line"] - 1] == "- " + RESULT
    changed_trace = deepcopy(trace)
    changed_trace["resume_sha256"] = hashlib.sha256(changed_text.encode("utf-8")).hexdigest()
    assert changed_trace["claims"] == trace["claims"]
    output.write_text(changed_text)
    output.with_suffix(".trace.json").write_text(json.dumps(changed_trace))
    _, valid = read_generation_trace(output)
    assert paths["card"].read_bytes() == before
    assert valid is False
