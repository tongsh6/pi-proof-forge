"""共享正文入口使用现行FactIndex/plan，不保留preferred_facts第二通道。"""
from copy import deepcopy
from tests.unit.engines.test_fact_index import reviewed_card_results

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
