"""Phase A：四层简历质量标准、规则判项与质量报告结构。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.engines.evaluation import tiered_evaluator as te


def career_profile(**overrides):
    profile = {
        "revision": "rev-1",
        "career_status": {"reviewed": True, "ready": True, "missing": []},
        "career": {
            "schema_version": 1,
            "summary": "负责平台架构与交付。",
            "education_visibility": "show",
            "work": [
                {
                    "id": "w1",
                    "company": "示例科技",
                    "title": "平台负责人",
                    "start": "2021-03",
                    "end": "",
                    "current": True,
                    "scope": "负责平台架构与交付。",
                    "contributions": ["搭建统一平台"],
                    "evidence_ids": ["ec_00000001"],
                }
            ],
            "education": [
                {
                    "id": "e1",
                    "school": "示例大学",
                    "major": "软件工程",
                    "degree": "本科",
                    "start": "2010-09",
                    "end": "2014-06",
                    "current": False,
                }
            ],
            "skills": [{"id": "s1", "category": "架构", "description": "平台治理", "evidence_ids": []}],
            "extras": [],
        },
    }
    profile.update(overrides)
    return profile


def card(card_id="ec_00000001", **overrides):
    value = {
        "id": card_id,
        "title": "统一平台建设",
        "time_range": "2022-03 ~ 2023-09",
        "role_scope": "平台负责人",
        "context": "多品牌微服务散落。",
        "results": ["查询耗时从 2 秒降至 300 毫秒", "覆盖 8 个品牌"],
        "artifacts": ["性能报告.pdf"],
        "actions": ["完成平台抽象"],
    }
    value.update(overrides)
    return value


def trace(claims, inputs=None):
    return {
        "claims": claims,
        "inputs": inputs or {},
        "evidence_card_ids": ["ec_00000001"],
        "status": "verified",
    }


RESUME = """# 张三
13800000000 | zhangsan@example.com | 上海
当前定位：平台负责人
求职意向：示例科技 · 平台负责人

## 职业概述
负责平台架构与交付，覆盖 8 个品牌。

## 核心能力
- 架构：平台治理

<!-- first-screen-end -->

## 核心技能
Java、Redis

## 项目经历
### 统一平台建设（2022-03 ~ 2023-09）
角色：平台负责人
场景：多品牌微服务散落。
所属工作：示例科技
- 完成平台抽象
- 查询耗时从 2 秒降至 300 毫秒

## 工作经历
### 示例科技 · 平台负责人（2021-03 ~ 至今）

## 教育经历
### 示例大学（2010-09 ~ 2014-06）
软件工程 · 本科
"""


def claims_for_resume():
    return [
        {"text": "张三", "source_kind": "personal_profile", "field": "name", "evidence_id": ""},
        {"text": "13800000000", "source_kind": "personal_profile", "field": "phone", "evidence_id": ""},
        {"text": "zhangsan@example.com", "source_kind": "personal_profile", "field": "email", "evidence_id": ""},
        {"text": "上海", "source_kind": "personal_profile", "field": "city", "evidence_id": ""},
        {"text": "平台负责人", "source_kind": "personal_profile", "field": "current_position", "evidence_id": ""},
        {"text": "负责平台架构与交付，覆盖 8 个品牌。", "source_kind": "personal_profile", "field": "career.summary", "evidence_id": ""},
        {"text": "架构：平台治理", "source_kind": "personal_profile", "field": "career.skills.s1.category", "evidence_id": ""},
        {"text": "Java", "source_kind": "evidence", "field": "stack", "evidence_id": "ec_00000001"},
        {"text": "统一平台建设", "source_kind": "evidence", "field": "title", "evidence_id": "ec_00000001"},
        {"text": "2022-03 ~ 2023-09", "source_kind": "evidence", "field": "time_range", "evidence_id": "ec_00000001"},
        {"text": "平台负责人", "source_kind": "evidence", "field": "role_scope", "evidence_id": "ec_00000001"},
        {"text": "多品牌微服务散落。", "source_kind": "evidence", "field": "context", "evidence_id": "ec_00000001"},
        {"text": "示例科技", "source_kind": "personal_profile", "field": "career.work.w1.company", "evidence_id": ""},
        {"text": "平台负责人", "source_kind": "personal_profile", "field": "career.work.w1.title", "evidence_id": ""},
        {"text": "完成平台抽象", "source_kind": "evidence", "field": "actions", "evidence_id": "ec_00000001"},
        {"text": "查询耗时从 2 秒降至 300 毫秒", "source_kind": "evidence", "field": "results", "evidence_id": "ec_00000001"},
        {"text": "示例大学", "source_kind": "personal_profile", "field": "career.education.e1.school", "evidence_id": ""},
        {"text": "软件工程 · 本科", "source_kind": "personal_profile", "field": "career.education.e1.major", "evidence_id": ""},
    ]


def semantic_review(statuses=("supported",)):
    rows = []
    for index, status in enumerate(statuses, start=1):
        rows.append(
            {
                "requirement_id": f"d{index}",
                "kind": "responsibility",
                "text": f"{index}. 负责核心平台交付 {index}",
                "status": status if status != "not_present" else "supported",
                "resume_status": status,
                "reason": "示例理由",
                "citations": [
                    {
                        "fact_id": "f1",
                        "quote": "完成平台抽象",
                        "source_id": "ec_00000001",
                        "field": "actions",
                        "text": "完成平台抽象",
                        "in_resume": True,
                    }
                ],
            }
        )
    return {
        "mode": "semantic",
        "fit_score": 80,
        "resume_score": 80,
        "requirements": rows,
        "all_requirements_supported": all(row["resume_status"] == "supported" for row in rows),
    }


def job_context():
    return {
        "target_role": "平台负责人",
        "company": "示例科技",
        "education": "本科",
        "work_years": "5-10年",
        "keywords": ["Java"],
        "must_have": ["本科及以上学历"],
    }


def build(resume=RESUME, cards=None, claims=None, pdf_check=..., semantic=None, highlights=None, profile=None, context=None, judgments=None, decisions=None):
    return te.build_quality_report(
        resume=resume,
        trace=trace(claims if claims is not None else claims_for_resume()),
        career_profile=profile if profile is not None else career_profile(),
        cards=cards if cards is not None else {"ec_00000001": card()},
        semantic_review=semantic if semantic is not None else semantic_review(),
        job_context=context if context is not None else job_context(),
        pdf_check={"pages": 2, "clipped": False} if pdf_check is ... else pdf_check,
        highlights=highlights,
        judgments=judgments,
        decisions=decisions,
        resume_version="sha-test",
        job_profile_id="jp-test",
    )


def rules(report, tier):
    return [failure["rule"] for failure in report["tiers"][tier]["failures"]]


def test_first_screen_uses_explicit_marker_and_falls_back_without_one():
    first, rest = te.split_first_screen(RESUME)
    assert "职业概述" in first and "核心技能" not in first
    assert "<!-- first-screen-end -->" not in first + rest
    fallback_first, _ = te.split_first_screen("# 张三\n当前定位：平台负责人\n\n## 工作经历\n- x")
    assert "当前定位" in fallback_first


def test_eligible_tier_passes_for_traceable_two_page_resume():
    report = build()
    eligible = report["tiers"]["eligible"]
    assert eligible["passed"] is True, eligible["failures"]
    assert eligible["metrics"]["pdf_pages"] == 2


def test_r1_3_missing_card_time_fails_and_points_to_card():
    report = build(cards={"ec_00000001": card(time_range="")})
    assert report["tiers"]["eligible"]["passed"] is False
    failure = next(item for item in report["tiers"]["eligible"]["failures"] if item["rule"] == "R1.3")
    assert "ec_00000001" in failure["target"]
    assert "统一平台建设" in failure["target"]


def test_r1_1_untraceable_bullet_fails():
    claims = [claim for claim in claims_for_resume() if claim["text"] != "完成平台抽象"]
    report = build(claims=claims)
    assert "R1.1" in rules(report, "eligible")


def test_r1_6_internal_ids_and_paths_are_rejected():
    report = build(resume=RESUME.replace("Java、Redis", "Java、Redis、ec_1234abcd"))
    assert "R1.6" in rules(report, "eligible")
    report = build(resume=RESUME.replace("上海", "/Users/loong/private"))
    assert "R1.6" in rules(report, "eligible")


def test_r1_2_requires_confirmed_career_profile_and_consistent_period():
    unconfirmed = career_profile(career_status={"reviewed": False, "ready": False, "missing": [{"field": "work"}]})
    report = build(profile=unconfirmed)
    assert "R1.2" in rules(report, "eligible")
    conflict = career_profile()
    conflict["career"]["work"][0]["start"] = "2010-01"
    conflict["career"]["work"][0]["end"] = "2012-01"
    conflict["career"]["work"][0]["current"] = False
    report = build(profile=conflict)
    assert "R1.2" in rules(report, "eligible")


def test_r1_7_hard_condition_conflict_is_marked_not_hidden():
    context = job_context()
    context["education"] = "本科"
    profile = career_profile()
    profile["career"]["education"] = [
        {"id": "e1", "school": "示例学院", "major": "软件工程", "degree": "大专", "start": "2010-09", "end": "2013-06", "current": False}
    ]
    report = build(profile=profile, context=context)
    assert "R1.7" in rules(report, "eligible")


def test_r1_8_required_resume_sections():
    report = build(resume=RESUME.replace("## 教育经历", "## 其他"))
    assert "R1.8" in rules(report, "eligible")


def test_r1_4_unconfirmed_l3_ownership_requires_confirmation():
    cards = {"ec_00000001": card(role_scope_provenance={"level": "L3", "evidence": []})}
    claims = claims_for_resume()
    claims = [
        {**claim, "text": "负责完成平台抽象"} if claim["text"] == "完成平台抽象" else claim
        for claim in claims
    ]
    report = build(
        resume=RESUME.replace("- 完成平台抽象", "- 负责完成平台抽象"),
        cards=cards,
        claims=claims,
    )
    assert "R1.4" in rules(report, "eligible")


@pytest.mark.parametrize("serialized", [False,True])
def test_r1_4_confirmed_l3_ownership_is_not_rejected_only_for_its_level(serialized):
    provenance={"level":"L3","confirmed_by_user":True,
                "evidence":[{"material_id":"m","document_id":"d","excerpt":"承担平台建设相关职责"}]}
    value=card(role_scope_provenance=provenance)
    if serialized:
        value.pop("role_scope_provenance")
        value["role_scope_provenance_json"]=json.dumps(provenance)
    claims=[{**claim,"text":"负责完成平台抽象"} if claim["text"]=="完成平台抽象" else claim
            for claim in claims_for_resume()]
    report=build(resume=RESUME.replace("- 完成平台抽象","- 负责完成平台抽象"),
                 cards={"ec_00000001":value},claims=claims)
    assert "R1.4" not in rules(report,"eligible")


def test_fit_tier_matrix_marks_first_screen_and_top_three_requirements():
    report = build(semantic=semantic_review(("supported", "partial", "not_present")))
    fit = report["tiers"]["fit"]
    assert fit["matrix"], fit
    assert fit["matrix"][0]["status"] == "supported"
    assert fit["matrix"][0]["first_screen"] is False
    assert "R2.2" in [failure["rule"] for failure in fit["failures"]]
    assert any(task for task in report["gap_tasks"])


def test_strong_tier_quantification_filler_duplicates_and_casing():
    resume = RESUME.replace(
        "- 完成平台抽象\n- 查询耗时从 2 秒降至 300 毫秒",
        "- 深入理解平台架构\n- 深入理解平台架构\n- 使用 redis 与 Redis 开发",
    )
    cards = {"ec_00000001": card(results=["覆盖 8 个品牌"])}
    report = build(resume=resume, cards=cards)
    strong_rules = rules(report, "strong")
    assert "R3.2" in strong_rules
    assert "R3.3" in strong_rules
    assert "R3.4" in strong_rules
    assert "R3.6" in strong_rules


def test_distinct_tier_requires_one_or_two_first_screen_highlights():
    report = build(highlights=[])
    assert "R4.2" in rules(report, "distinct")
    assert "R4.1" in report["llm_pending"]
    three = [
        {"bullet_ref": "bullet#1", "jd_item": "d1", "level": "L1", "exceeds": "规模"},
        {"bullet_ref": "bullet#2", "jd_item": "d2", "level": "L1", "exceeds": "难度"},
        {"bullet_ref": "bullet#3", "jd_item": "d3", "level": "L1", "exceeds": "范围"},
    ]
    assert "R4.2" in rules(build(highlights=three), "distinct")
    weak = [{"bullet_ref": "bullet#1", "jd_item": "d1", "level": "L3", "exceeds": "规模"}]
    assert "R4.3" in rules(build(highlights=weak), "distinct")


def test_quality_report_auto_pass_requires_all_tiers_and_no_pending_llm_rules():
    report = build()
    assert report["tiers"]["eligible"]["passed"] is True
    assert report["auto_pass"] is False
    assert set(report["llm_pending"]) >= {"R1.4", "R2.1", "R3.1", "R3.5", "R4.1"}
    assert report["legacy_scores"] == {"rule_total": None, "llm_expression": None}


def test_apply_pdf_check_updates_r1_5_and_auto_pass():
    report = build(pdf_check=None)
    assert "R1.5" in rules(report, "eligible")
    updated = te.apply_pdf_check(report, {"pages": 3, "clipped": False})
    assert "R1.5" in rules(updated, "eligible")
    updated = te.apply_pdf_check(report, {"pages": 2, "clipped": False})
    assert "R1.5" not in [failure["rule"] for failure in updated["tiers"]["eligible"]["failures"]]
    assert updated["tiers"]["eligible"]["metrics"]["pdf_pages"] == 2
    assert updated["tiers"]["eligible"]["passed"] is True
    assert all(not updated["tiers"][tier].get("blocked_by") for tier in ("fit","strong","distinct"))
    assert not any("R1.5" in task for task in updated["gap_tasks"])
    again=te.apply_pdf_check(updated,{"pages":3,"clipped":False})
    assert all(again["tiers"][tier].get("blocked_by")=="eligible" for tier in ("fit","strong","distinct"))
    assert any("R1.5" in task for task in again["gap_tasks"])
    assert "R1.5" in rules(report,"eligible"), "回填不得修改原始报告"


def test_quality_config_loads_thresholds_and_filler_lexicon():
    config = te.load_quality_config(Path.cwd())
    assert config.thresholds["strong"]["quant_first_screen_min_ratio"] == pytest.approx(0.6)
    assert "深入理解" in config.filler_terms
    assert any(term.lower() == "proven" for term in config.filler_terms)


def judged_payload(*, semantic_ids=("d1",), r1_4=None, r3_1=None, r3_5=None, r4_1=None, r2_1=None):
    return {
        "schema_version": 1,
        "prompt_version": 1,
        "judged_sections": ["r1_4", "r2_1", "r3_1", "r3_5", "r4_1"],
        "rejected_items": 0,
        "r1_4": r1_4 if r1_4 is not None else [],
        "r2_1": r2_1 if r2_1 is not None else [
            {"jd_item_id": jd_id, "status": "supported", "bullet_ref": "bullet#1",
             "citations": ["ec_00000001"], "reason": "首屏技能区支撑"} for jd_id in semantic_ids
        ],
        "r3_1": r3_1 if r3_1 is not None else [
            {"bullet": 2, "scene": True, "action": True, "result": True, "citations": ["ec_00000001"], "reason": ""},
            {"bullet": 3, "scene": True, "action": True, "result": True, "citations": ["ec_00000001"], "reason": ""},
        ],
        "r3_5": r3_5 if r3_5 is not None else {
            "summary_lines": 2, "role_scale_match": True, "generic_adjectives": [],
            "citations": ["bullet#1"], "reason": "",
        },
        "r4_1": r4_1 if r4_1 is not None else [
            {"bullet": 1, "jd_item_id": "d1", "exceeds": ["scale"], "level": "L1",
             "citations": ["ec_00000001"], "reason": "规模超出 JD 字面"}
        ],
    }


def test_judged_mode_clears_pending_and_feeds_matrix_and_highlights():
    report = build(judgments=judged_payload())
    assert report["llm_pending"] == []
    assert report["quality_judge"] is None  # judge_meta 由调用方传入，纯函数不伪造
    fit = report["tiers"]["fit"]
    assert fit["matrix"][0]["judged"] is True
    assert fit["matrix"][0]["first_screen"] is True
    distinct = report["tiers"]["distinct"]
    assert distinct["highlights"][0]["highlight_id"] == "hl_b1_d1"
    assert distinct["metrics"]["candidate_count"] == 1
    # 四层仍未全部通过（R3.2 首屏量化），所以 auto_pass 仍为 False，但不再因 LLM pending 而挂起。
    assert report["auto_pass"] is False


def test_judged_r3_1_and_r3_5_and_r1_4_failures_are_reported():
    payload = judged_payload(
        r1_4=[{"bullet": 2, "supported": False, "citations": ["ec_00000001"], "reason": "卡中没有本人负责表述"}],
        r3_1=[
            {"bullet": 2, "scene": True, "action": False, "result": True, "citations": ["ec_00000001"], "reason": "缺动作"},
            {"bullet": 3, "scene": True, "action": True, "result": True, "citations": ["ec_00000001"], "reason": ""},
        ],
        r3_5={"summary_lines": 4, "role_scale_match": False, "generic_adjectives": ["丰富经验"],
              "citations": ["bullet#1"], "reason": ""},
    )
    claims = [
        {**claim, "text": "负责完成平台抽象"} if claim["text"] == "完成平台抽象" else claim
        for claim in claims_for_resume()
    ]
    report = build(resume=RESUME.replace("- 完成平台抽象", "- 负责完成平台抽象"), claims=claims, judgments=payload)
    all_rules = rules(report, "eligible") + rules(report, "strong")
    assert all_rules.count("R1.4") == 1
    assert all_rules.count("R3.1") == 1
    assert all_rules.count("R3.5") >= 2


def test_judged_r2_1_overrides_matrix_status_and_top_responsibility():
    payload = judged_payload(
        semantic_ids=("d1",),
        r2_1=[{"jd_item_id": "d1", "status": "weak", "bullet_ref": "bullet#2",
               "citations": ["ec_00000001"], "reason": "仅部分支撑"}],
    )
    report = build(judgments=payload)
    matrix = report["tiers"]["fit"]["matrix"]
    assert matrix[0]["status"] == "weak"
    assert matrix[0]["first_screen"] is False
    assert "R2.2" in rules(report, "fit")


def test_project_relevance_uses_mapped_bullets_instead_of_title_words():
    report = build()
    assert "R2.4" not in rules(report, "fit")
    resume = RESUME + "\n## 项目经历\n### 无关项目（2022 ~ 2023）\n- 制作宣传海报\n"
    report = build(resume=resume)
    failures = [f for f in report["tiers"]["fit"]["failures"] if f["rule"] == "R2.4"]
    assert len(failures) == 1 and "无关项目" in failures[0]["target"]


def test_quantification_requires_result_text_not_version_number_coincidence():
    assert not te._has_verifiable_quant("采用 Java 8", ["响应延迟降至 80ms"])
    assert not te._has_verifiable_quant("采用 Java 8", ["覆盖 8 个品牌"])
    assert te._has_verifiable_quant("改造查询 · 响应延迟降至 80ms", ["响应延迟降至 80ms"])
    assert not te._has_verifiable_quant("2023 年完成升级 Java 8", ["2023 年完成升级 Java 8"])


def test_project_mapping_accepts_visible_context_line():
    resume = "## 项目经历\n### 售后服务（2024 ~ 2025）\n场景：多品牌售后履约\n- 设计履约流程\n"
    judged = judged_payload(r2_1=[{"jd_item_id": "d1", "status": "weak", "bullet_ref": "line#3",
                                  "citations": ["line#3"], "reason": "相关业务场景"}])
    result = build(resume=resume, judgments=judged)
    assert "R2.4" not in rules(result, "fit")


def test_resume_judge_cannot_upgrade_partial_pool_support_to_full_support():
    semantic = semantic_review(statuses=("partial",))
    report = build(semantic=semantic, judgments=judged_payload())
    row = report["tiers"]["fit"]["matrix"][0]
    assert row["status"] == "weak"


def test_verified_result_text_is_an_outcome_without_numeric_metric():
    resume = "## 项目经历\n### 接口对接（2024）\n- 实现用友 NC 接口集成\n"
    claims = [{"text": "实现用友 NC 接口集成", "source_kind": "evidence", "evidence_id": "ec_1", "field": "results"}]
    judged = judged_payload(r3_1=[{"bullet": 1, "scene": True, "action": True, "result": False,
                                   "citations": ["ec_1"], "reason": "没有量化指标"}])
    result = te.evaluate_strong(resume=resume, cards={"ec_1": {"results": ["实现用友 NC 接口集成"]}},
        trace={"claims": claims}, config=te.load_quality_config(), judgments=judged)
    assert not any(f.rule == "R3.1" for f in result.failures)
    assert any(f.rule == "R3.2" for f in result.failures)


def test_three_nominations_are_ranked_to_two_not_rejected_as_three_chosen():
    candidates = [{"highlight_id": f"hl_{i}", "bullet": 1, "jd_item_id": f"d{i}",
                   "exceeds": ["scale"], "level": "L1"} for i in range(3)]
    result = te.evaluate_distinct(resume="- 完成平台\n<!-- first-screen-end -->",
                                 candidates=candidates, config=te.load_quality_config())
    assert result.passed and len(result.highlights) == 2


def test_verbatim_confirmed_profile_role_does_not_need_duplicate_model_confirmation():
    text = "承担开发负责人职责"
    profile = career_profile()
    profile["career"]["skills"][0]["description"] = text
    claims = [{"text": text, "source_kind": "personal_profile",
               "field": "career.skills.s1.description", "evidence_id": ""}]
    report = build(resume="## 核心能力\n- " + text, claims=claims, profile=profile,
                   judgments=judged_payload(r1_4=[]))
    assert "R1.4" not in rules(report, "eligible")
    profile["career"]["skills"][0]["description"] = "参与联调"
    report = build(resume="## 核心能力\n- " + text, claims=claims, profile=profile,
                   judgments=judged_payload(r1_4=[]))
    assert "R1.4" in rules(report, "eligible")


def test_highlight_decisions_reject_and_select_are_applied():
    candidates = [
        {"bullet": 1, "jd_item_id": "d1", "exceeds": ["scale"], "level": "L1",
         "citations": ["ec_00000001"], "reason": "规模"},
        {"bullet": 2, "jd_item_id": "d1", "exceeds": ["difficulty"], "level": "L1",
         "citations": ["ec_00000001"], "reason": "难度"},
    ]
    payload = judged_payload(r4_1=candidates)
    report = build(
        judgments=payload,
        decisions={"rejected": ["hl_b1_d1"], "selected": ["hl_b2_d1"]},
    )
    distinct = report["tiers"]["distinct"]
    assert distinct["metrics"]["rejected"] == 1
    assert distinct["metrics"]["selected"] == 1
    assert [item["highlight_id"] for item in distinct["highlights"]] == ["hl_b2_d1"]


def test_distinct_prefers_first_screen_highlight_candidates():
    from tools.engines.evaluation.tiered_evaluator import (
        _candidate_highlights,
        evaluate_distinct,
        load_quality_config,
    )

    resume = (
        "# 候选人\n\n## 项目经历\n### 交易平台（2024）\n"
        "- 主导交易链路重构：延迟从 800ms 降至 120ms\n\n"
        "<!-- first-screen-end -->\n\n"
        "- 把构建耗时从 20 分钟降到 4 分钟\n"
    )
    candidates = [
        {"highlight_id": "hl_page2", "bullet": 2, "jd_item_id": "d1", "exceeds": ["scale", "scope"],
         "level": "L1", "reason": "第二页突出点", "citations": ["ec_1"]},
        {"highlight_id": "hl_first", "bullet": 1, "jd_item_id": "d1", "exceeds": ["difficulty"],
         "level": "L1", "reason": "首屏突出点", "citations": ["ec_1"]},
    ]
    items = _candidate_highlights(resume, candidates, {})
    assert items[0]["highlight_id"] == "hl_first" and items[0]["first_screen"] is True
    report = evaluate_distinct(resume=resume, candidates=candidates, decisions={}, config=load_quality_config())
    assert report.passed


# ---------------------------------------------------------------------------
# 投递建议与缺口类型（2026-10-21）：证据缺失 / 未表达 / 建议仅供参考
# ---------------------------------------------------------------------------

FIRST_SCREEN_PROJECT_RESUME = """# 张三
13800000000 | zhangsan@example.com | 上海
当前定位：平台负责人

## 职业概述
负责平台架构与交付，覆盖 8 个品牌。

## 项目经历
### 统一平台建设（2022-03 ~ 2023-09）
角色：平台负责人
场景：多品牌微服务散落。
- 完成平台抽象
- 查询耗时从 2 秒降至 300 毫秒
- 覆盖 8 个品牌

<!-- first-screen-end -->

## 工作经历
### 示例科技 · 平台负责人（2021-03 ~ 至今）

## 核心技能
Java、Redis

## 教育经历
### 示例大学（2010-09 ~ 2014-06）
软件工程 · 本科
"""


def first_screen_project_claims():
    claims = claims_for_resume()
    claims.append(
        {"text": "覆盖 8 个品牌", "source_kind": "evidence", "field": "results", "evidence_id": "ec_00000001"}
    )
    return claims


def first_screen_highlight():
    return [{"bullet_ref": "bullet#2", "jd_item": "d1", "level": "L1", "exceeds": "规模", "reason": "示例"}]


FIRST_SCREEN_NO_SUMMARY_RESUME = """# 张三
13800000000 | zhangsan@example.com | 上海

## 项目经历
### 统一平台建设（2022-03 ~ 2023-09）
角色：平台负责人
场景：多品牌微服务散落。
- 完成平台抽象
- 查询耗时从 2 秒降至 300 毫秒
- 覆盖 8 个品牌

<!-- first-screen-end -->

## 职业概述
负责平台架构与交付，覆盖 8 个品牌。

## 工作经历
### 示例科技 · 平台负责人（2021-03 ~ 至今）

## 核心技能
Java、Redis

## 教育经历
### 示例大学（2010-09 ~ 2014-06）
软件工程 · 本科
"""


def no_summary_claims():
    return [
        claim for claim in first_screen_project_claims()
        if claim["text"] != "当前定位：平台负责人"
    ]


def fit_failure(report, rule="R2.2"):
    return next(failure for failure in report["tiers"]["fit"]["failures"] if failure["rule"] == rule)


def test_fit_gap_kind_separates_evidence_gap_from_not_expressed():
    # 证据池 supported、正文 weak：属于“未表达”，可重新生成/调整选材解决。
    semantic = semantic_review(statuses=("supported",))
    judged = judged_payload(r2_1=[{"jd_item_id": "d1", "status": "weak", "bullet_ref": "bullet#1",
                                   "citations": ["ec_00000001"], "reason": "正文未呈现已有支撑"}])
    report = build(semantic=semantic, judgments=judged)
    failure = fit_failure(report)
    assert failure["gap_kind"] == "not_expressed"
    assert report["tiers"]["fit"]["matrix"][0]["evidence_support"] == "supported"

    # 证据池 partial：属于“证据缺失”，需要补证据或更换更匹配的目标。
    semantic = semantic_review(statuses=("partial",))
    judged = judged_payload(r2_1=[{"jd_item_id": "d1", "status": "supported", "bullet_ref": "bullet#1",
                                   "citations": ["ec_00000001"], "reason": ""}])
    report = build(semantic=semantic, judgments=judged)
    failure = fit_failure(report)
    assert failure["gap_kind"] == "evidence_missing"
    assert report["tiers"]["fit"]["matrix"][0]["evidence_support"] == "partial"


def test_r2_2_supported_but_not_first_screen_reports_position_gap():
    report = build()  # 默认夹具：证据池 supported，但引用 bullet 在首屏标记之后
    failure = fit_failure(report)
    assert failure["gap_kind"] == "not_expressed"
    assert "不在首屏" in failure["reason"]
    assert "支撑状态 supported" not in failure["reason"]


def test_r2_4_selection_gap_has_no_evidence_or_expression_kind():
    report = build(resume=RESUME + "\n## 项目经历\n### 无关项目（2022 ~ 2023）\n- 制作宣传海报\n")
    failure = fit_failure(report, "R2.4")
    assert "gap_kind" not in failure


def test_eligible_failures_never_carry_gap_kind():
    unconfirmed = career_profile(career_status={"reviewed": False, "ready": False, "missing": [{"field": "work"}]})
    report = build(profile=unconfirmed)
    for failure in report["tiers"]["eligible"]["failures"]:
        assert "gap_kind" not in failure


def test_gap_tasks_label_fit_gap_kind():
    report = build()
    assert any("R2.2" in task and "未表达" in task for task in report["gap_tasks"]), report["gap_tasks"]


def test_delivery_advice_apply_when_eligible_and_fit_pass():
    report = build(
        resume=FIRST_SCREEN_PROJECT_RESUME,
        claims=first_screen_project_claims(),
        highlights=first_screen_highlight(),
    )
    advice = report["delivery_advice"]
    assert report["tiers"]["eligible"]["passed"] is True
    assert report["tiers"]["fit"]["passed"] is True
    assert advice["recommendation"] == "apply"
    assert advice["advisory_only"] is True
    assert advice["gap_counts"] == {"evidence_missing": 0, "not_expressed": 0}
    assert advice["summary"] and advice["reasons"] and advice["next_actions"]
    # 质量建议不依赖 auto_pass：LLM 判项未完成时 auto_pass 仍为 False。
    assert report["auto_pass"] is False


def test_delivery_advice_notes_optional_strong_tier_improvements_only():
    resume = FIRST_SCREEN_PROJECT_RESUME.replace("- 覆盖 8 个品牌\n", "")
    report = build(resume=resume, claims=first_screen_project_claims(), highlights=first_screen_highlight())
    assert report["tiers"]["fit"]["passed"] is True
    assert report["tiers"]["strong"]["passed"] is False
    advice = report["delivery_advice"]
    assert advice["recommendation"] == "apply"
    assert any("优质层" in reason for reason in advice["reasons"]), advice["reasons"]


def test_delivery_advice_strengthen_for_expression_gap_only():
    report = build()
    advice = report["delivery_advice"]
    assert advice["recommendation"] == "strengthen"
    assert advice["gap_counts"]["not_expressed"] >= 1
    assert advice["gap_counts"]["evidence_missing"] == 0
    assert any("首屏" in action or "重新生成" in action for action in advice["next_actions"])


def test_delivery_advice_reconsider_when_core_responsibilities_lack_evidence():
    report = build(semantic=semantic_review(statuses=("partial", "partial", "partial")))
    advice = report["delivery_advice"]
    assert advice["recommendation"] == "reconsider"
    assert advice["gap_counts"]["evidence_missing"] >= 2
    assert any("补" in action or "更换" in action for action in advice["next_actions"])


def test_delivery_advice_fix_facts_when_profile_or_hard_requirements_fail():
    unconfirmed = career_profile(career_status={"reviewed": False, "ready": False, "missing": [{"field": "work"}]})
    report = build(profile=unconfirmed)
    advice = report["delivery_advice"]
    assert advice["recommendation"] == "fix_facts"
    assert any("事实" in reason or "档案" in reason for reason in advice["reasons"])


def test_delivery_advice_marks_pdf_unverified_without_calling_it_evidence_gap():
    report = build(
        resume=FIRST_SCREEN_PROJECT_RESUME,
        claims=first_screen_project_claims(),
        highlights=first_screen_highlight(),
        pdf_check=None,
    )
    advice = report["delivery_advice"]
    assert advice["recommendation"] == "apply"
    assert any("未校验项" in reason and "PDF" in reason for reason in advice["reasons"])
    assert "除未校验项外" in advice["summary"]
    assert advice["gap_counts"] == {"evidence_missing": 0, "not_expressed": 0}


def test_pdf_pending_must_not_hide_first_screen_summary_gap():
    report = build(
        resume=FIRST_SCREEN_NO_SUMMARY_RESUME,
        claims=no_summary_claims(),
        highlights=first_screen_highlight(),
        pdf_check=None,
    )
    assert report["tiers"]["fit"]["passed"] is True
    targets = [
        (failure["rule"], failure.get("target"))
        for failure in report["tiers"]["eligible"]["failures"]
    ]
    assert ("R1.5", "pdf") in targets
    assert ("R1.5", "首屏") in targets
    advice = report["delivery_advice"]
    assert advice["recommendation"] != "apply", advice
    assert advice["recommendation"] == "strengthen"
    assert any("首屏" in reason for reason in advice["reasons"])
    assert any("首屏" in action for action in advice["next_actions"])

    # PDF 回填只替换 pdf 相关 R1.5；首屏缺口保留，建议不能“洗”成 apply。
    updated = te.apply_pdf_check(report, {"pages": 2, "clipped": False})
    targets = [
        (failure["rule"], failure.get("target"))
        for failure in updated["tiers"]["eligible"]["failures"]
    ]
    assert ("R1.5", "首屏") in targets and ("R1.5", "pdf") not in targets
    assert updated["delivery_advice"]["recommendation"] == "strengthen"
    assert any("首屏" in action for action in updated["delivery_advice"]["next_actions"])
    assert not any("压缩" in action for action in updated["delivery_advice"]["next_actions"])


def test_delivery_advice_apply_clears_unverified_wording_after_judge_and_pdf():
    judged = judged_payload(
        r2_1=[{"jd_item_id": "d1", "status": "supported", "bullet_ref": "bullet#1",
               "citations": ["ec_00000001"], "reason": "首屏项目支撑"}]
    )
    report = build(
        resume=FIRST_SCREEN_PROJECT_RESUME,
        claims=first_screen_project_claims(),
        highlights=first_screen_highlight(),
        pdf_check=None,
        judgments=judged,
    )
    assert report["llm_pending"] == []
    assert report["delivery_advice"]["recommendation"] == "apply"
    assert any("未校验项" in reason for reason in report["delivery_advice"]["reasons"])
    updated = te.apply_pdf_check(report, {"pages": 2, "clipped": False})
    assert updated["delivery_advice"]["recommendation"] == "apply"
    assert not any("未校验项" in reason for reason in updated["delivery_advice"]["reasons"])
    assert updated["delivery_advice"]["summary"].startswith("建议投递：合格层与对位层通过")


def test_apply_pdf_check_recomputes_delivery_advice():
    report = build(
        resume=FIRST_SCREEN_PROJECT_RESUME,
        claims=first_screen_project_claims(),
        highlights=first_screen_highlight(),
        pdf_check=None,
    )
    assert any("未校验项" in reason and "PDF" in reason for reason in report["delivery_advice"]["reasons"])
    updated = te.apply_pdf_check(report, {"pages": 2, "clipped": False})
    assert updated["delivery_advice"]["recommendation"] == "apply"
    assert not any("尚未回填" in reason for reason in updated["delivery_advice"]["reasons"])
    too_long = te.apply_pdf_check(report, {"pages": 3, "clipped": False})
    assert too_long["delivery_advice"]["recommendation"] == "strengthen"
    assert any("压缩" in action or "两页" in action for action in too_long["delivery_advice"]["next_actions"])


def test_apply_pdf_check_does_not_add_advice_to_legacy_reports():
    report = build(
        resume=FIRST_SCREEN_PROJECT_RESUME,
        claims=first_screen_project_claims(),
        highlights=first_screen_highlight(),
    )
    report.pop("delivery_advice")
    updated = te.apply_pdf_check(report, {"pages": 2, "clipped": False})
    assert "delivery_advice" not in updated


def test_apply_pdf_check_keeps_advice_when_tiers_are_sparse():
    report = build()  # 对位有 gap：建议为 strengthen；去掉 guard 后空 tiers 会翻成 apply
    assert report["delivery_advice"]["recommendation"] == "strengthen"
    before = json.dumps(report["delivery_advice"], sort_keys=True, ensure_ascii=False)
    report["tiers"] = {name: {} for name in report["tiers"]}
    updated = te.apply_pdf_check(report, {"pages": 2, "clipped": False})
    assert json.dumps(updated["delivery_advice"], sort_keys=True, ensure_ascii=False) == before


def test_must_have_gap_counts_follow_support_status_and_split_kinds():
    semantic = {
        "mode": "semantic",
        "fit_score": 50,
        "resume_score": 40,
        "requirements": [
            {"requirement_id": "m1", "kind": "must_have", "text": "要求 m1",
             "status": "supported", "resume_status": "supported", "reason": "", "citations": []},
            {"requirement_id": "m2", "kind": "must_have", "text": "要求 m2",
             "status": "partial", "resume_status": "partial", "reason": "", "citations": []},
            {"requirement_id": "m3", "kind": "must_have", "text": "要求 m3",
             "status": "supported", "resume_status": "not_present", "reason": "", "citations": []},
        ],
        "all_requirements_supported": False,
    }
    report = build(semantic=semantic)
    must_have_failures = [
        failure for failure in report["tiers"]["fit"]["failures"]
        if failure["rule"] == "R2.3"
    ]
    assert sorted(failure["gap_kind"] for failure in must_have_failures) == [
        "evidence_missing", "not_expressed",
    ]
    text = " ".join(failure["reason"] for failure in must_have_failures)
    # supported 但不在首屏的 m1 不计入 R2.3 计数，因此不是 2 项未表达。
    assert "证据缺口 1 项" in text and "未表达 1 项" in text
    assert "未表达 2 项" not in text
    advice = report["delivery_advice"]
    assert advice["recommendation"] == "strengthen"
    assert any("证据缺口" in reason for reason in advice["reasons"])
    assert any("正文未表达" in reason for reason in advice["reasons"])
    assert any("补充硬性要求相关的证据卡" == action for action in advice["next_actions"])
    assert any("正文表达出来并前置" in action for action in advice["next_actions"])
