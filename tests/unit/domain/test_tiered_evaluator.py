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
