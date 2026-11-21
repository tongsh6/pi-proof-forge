"""唯一正文生成保留已采纳责任限定，并按原Fact身份建立occurrence。"""
from __future__ import annotations

import pytest
from tests.unit.engines.test_fact_index import reviewed_card_results

from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.generation.resume_renderer import build_template_resume, load_cards

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
                "level": time_level, "precision": precision, "confidence": 0.6, "confirmed_by_user": True,
                "evidence": [{"material_id": "mat_1", "document_id": "doc_1",
                              "excerpt": "2022 年以来持续投入"}]}
    if role_level:
        value["role_scope_level"] = role_level
        if role_level == "L3":
            value["role_scope_provenance"] = {
                "level": "L3", "confidence": 0.6, "confirmed_by_user": True,
                "evidence": [{"material_id": "mat_1", "document_id": "doc_1", "excerpt": "我推动改造"}],
                "first_person_hits": {"owner": 2, "participant": 3}}
    return reviewed_card_results(value)


@pytest.mark.parametrize("role", [
    "非负责人，仅参与联调", "协助负责人完成上线", "不负责总体设计",
    "参与接口联调，由平台组负责总体设计",
    "主导接口联调，但不负责总体设计", "协助联调并主导架构设计",
    "协助负责人并独立负责上线", "主导或深度参与方案设计与核心开发",
])
@pytest.mark.parametrize("version", ["A", "B"])
@pytest.mark.parametrize("level", ["L1", "L3", "L4"])
def test_adopted_role_qualifiers_are_preserved_without_word_replacement(role, version, level):
    current = card("ec-role", title="队列接口", time_range="2024", role_scope=role, role_level=level,
                   actions=["实现接口适配并完成测试联调"], results=["完成合成请求回归验收"])
    claims = []
    content = build_template_resume(version, [current], personal_profile=PROFILE, job_context=JOB, claims=claims)
    assert "角色：" + role in content
    assert current["role_scope"] == role
    assert any(c["text"] == role and c["source_kind"] == "presentation" for c in claims)
    result, = [c for c in claims if c.get("fact_id") == "ec-role:results:0"]
    assert result["text"] == current["results"][0]
    assert result["text"] in content.splitlines()[result["render_line"] - 1]


def test_load_cards_reads_provenance_levels(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ec-l3.yaml").write_text(
        'id: "ec-l3"\ntitle: "合成活动平台"\ntime_range: "2022"\ncontext: "背景"\nrole_scope: "平台负责人"\n'
        'time_range_provenance_json: \'{"level":"L3","precision":"year","evidence":[{"material_id":"mat_1","document_id":"doc_1","excerpt":"2022 年持续投入"}]}\'\n'
        'role_scope_provenance_json: \'{"level":"L3","evidence":[{"material_id":"mat_1","document_id":"doc_1","excerpt":"我推动改造"}]}\'\n'
        'actions:\n  - "负责改造"\nresults:\n  - "上线"\nartifacts:\n  - "报告.pdf"\n',
        encoding="utf-8",
    )
    cards = load_cards(evidence, ["ec-l3"])
    assert cards[0]["time_range_level"] == "L3"
    assert cards[0]["role_scope_level"] == "L3"
    assert cards[0]["time_range_provenance"]["precision"] == "year"


def test_actions_and_results_remain_independent_full_facts():
    current = card("ec-full", title="合成队列", time_range="2024", role_scope="接口负责人",
                   actions=["实现重试消费与事务回滚"],
                   results=["在隔离测试环境中，1000 条合成记录处理耗时由 20 秒降至 12 秒。",
                            "完成消息格式及接口兼容性验收"])
    claims = []
    content = build_template_resume("A", [current], personal_profile=PROFILE, claims=claims)
    first = content.split(FIRST_SCREEN_MARKER)[0]
    for field in ("actions", "results"):
        for index, original in enumerate(current[field]):
            row, = [claim for claim in claims if claim.get("fact_id") == f"ec-full:{field}:{index}"]
            assert row["text"] == original
            assert content.splitlines()[row["render_line"] - 1] == "- " + original
            assert original in first
    assert "生产环境" not in content

def dated_card(**changes):
    current = card("ec-period", title="合成队列交付", time_range="2023-03 ~ 2024-09",
                   role_scope="主导接口联调，但不负责总体设计",
                   actions=["实现队列消费与回调接口并完成联调"],
                   results=["完成消息格式及接口兼容性验收"])
    current.update(changes)
    return current


@pytest.mark.parametrize("level,precision,raw,expected", [
    ("L1", "day", "2023-03-14 ~ 2024-09-20", "2023-03-14 ~ 2024-09-20"),
    ("L4", "month", "2023-03-14 ~ 2024-09-20", "2023-03-14 ~ 2024-09-20"),
    ("L2", "year", "2023-03 ~ 2024-09", "2023 ~ 2024"),
    ("L2", "month", "2023-03-14 ~ 2024-09-20", "2023-03 ~ 2024-09"),
    ("L2", "day", "2023-03-14 ~ 2024-09-20", "2023-03 ~ 2024-09"),
    ("L3", "day", "2023-03-14 ~ 2024-09-20", "2023 ~ 2024"),
    ("L3", "month", "2023-03 ~ 2024-09", "2023 ~ 2024"),
    ("L3", "year", "2023-03 ~ 2023-09", "2023"),
    ("L3", "month", "2024 年 01 月 ~ 2024 年 03 月", "2024"),
    ("L2", "year", "2024 年 01 月 ~ 2024 年 03 月", "2024"),
    ("L2", "month", "2024 年 01 月 ~ 2024 年 03 月（内部 Beta 验证）",
     "2024-01 ~ 2024-03（内部 Beta 验证）"),
])
def test_public_builder_respects_proven_time_precision_without_mutating_source(level, precision, raw, expected):
    from copy import deepcopy
    current = dated_card(time_range=raw, time_range_level=level,
        time_range_provenance={"level": level, "precision": precision, "confirmed_by_user": True,
                               "evidence": [{"material_id": "m", "document_id": "d", "excerpt": raw}]})
    original = deepcopy(current)
    text = build_template_resume("A", [current], personal_profile=PROFILE)
    assert "### 合成队列交付（" + expected + "）" in text
    assert current == original
    assert current["results"][0] in text


@pytest.mark.parametrize("period,level", [("", "L5"), ("2023", "L5")])
def test_public_builder_excludes_untimed_or_explicitly_unproven_card_before_selection(period, level):
    unavailable = dated_card(id="ec-no-time", title="缺少项目时间", time_range=period,
                             time_range_level=level, results=["不应进入完整简历的项目结果"])
    available = dated_card()
    claims = []
    text = build_template_resume("A", [unavailable, available], personal_profile=PROFILE, claims=claims)
    assert "缺少项目时间" not in text and unavailable["results"][0] not in text
    assert available["results"][0] in text
    assert all(c.get("evidence_id") != "ec-no-time" for c in claims)
    with pytest.raises(ValueError, match="no_presentable_resume_facts"):
        build_template_resume("A", [unavailable], personal_profile=PROFILE)


def test_l5_role_omission_keeps_independent_actions_and_nonquantified_results():
    current = dated_card(role_scope_level="L5")
    text = build_template_resume("A", [current], personal_profile=PROFILE)
    assert "角色：" not in text
    assert current["actions"][0] in text and current["results"][0] in text


def test_unconfirmed_l3_role_is_not_promoted_by_card_eligibility():
    current = dated_card(role_scope_level="L3",
        role_scope_provenance={"level": "L3", "evidence": [{"material_id": "m", "document_id": "d", "excerpt": "候选归属"}]})
    text = build_template_resume("A", [current], personal_profile=PROFILE)
    assert "角色：" not in text
    assert current["actions"][0] in text and current["results"][0] in text


@pytest.mark.parametrize("level", ["L2", "L3"])
def test_unconfirmed_inferred_time_is_not_promoted_by_card_eligibility(level):
    current = dated_card(time_range_level=level,
        time_range_provenance={"level": level, "precision": "year",
                               "evidence": [{"material_id": "m", "document_id": "d", "excerpt": "候选时期"}]})
    with pytest.raises(ValueError, match="no_presentable_resume_facts"):
        build_template_resume("A", [current], personal_profile=PROFILE)
