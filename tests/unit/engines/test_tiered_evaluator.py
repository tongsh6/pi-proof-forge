"""Phase A：四层简历质量标准、规则判项与质量报告结构。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.engines.evaluation import tiered_evaluator as te
from tests.unit.engines.test_fact_index import reviewed_card_results, reviewed_result
from tests.unit.engines.test_generation_engines import generation


def career_profile(**overrides):
    profile = {
        "revision": "rev-1",
        "career_status": {"reviewed": True, "ready": True, "missing": []},
        "career": {
            "schema_version": 1,
            "summary": "负责平台架构与交付，覆盖 8 个品牌。",
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
        "stack": ["Java", "Redis"],
        "actions": ["完成平台抽象"],
    }
    value.update(overrides)
    return value


def trace(claims, inputs=None):
    return {
        "claims": claims,
        "occurrence_lineage_version": 1,
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
    # Explicit source identities and physical coordinates for the RESUME fixture.
    profile_rows = [
        ("career.summary", "负责平台架构与交付，覆盖 8 个品牌。", 7),
        ("career.skills.s1.category", "架构", 10),
        ("career.skills.s1.description", "平台治理", 10),
        ("career.work.w1.company", "示例科技", 21),
        ("career.work.w1.company", "示例科技", 26),
        ("career.work.w1.title", "平台负责人", 26),
        ("career.work.w1.start", "2021-03", 26),
        ("career.education.e1.school", "示例大学", 29),
        ("career.education.e1.start", "2010-09", 29),
        ("career.education.e1.end", "2014-06", 29),
        ("career.education.e1.major", "软件工程", 30),
        ("career.education.e1.degree", "本科", 30),
    ]
    evidence_rows = [
        ("stack", 0, "Java", 15), ("stack", 1, "Redis", 15),
        ("title", 0, "统一平台建设", 18),
        ("time_range", 0, "2022-03 ~ 2023-09", 18),
        ("role_scope", 0, "平台负责人", 19),
        ("context", 0, "多品牌微服务散落。", 20),
        ("actions", 0, "完成平台抽象", 22),
        ("results", 0, "查询耗时从 2 秒降至 300 毫秒", 23),
    ]
    return [
        {"text": text, "source_kind": "personal_profile", "field": field, "evidence_id": "",
         "fact_id": f"personal_profile:{field}:0", "render_line": line}
        for field, text, line in profile_rows
    ] + [
        {"text": text, "source_kind": "evidence", "field": field, "evidence_id": "ec_00000001",
         "fact_id": f"ec_00000001:{field}:{index}", "render_line": line}
        for field, index, text, line in evidence_rows
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
        "occurrence_coverage_known": True,
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
    # Author exact coordinates for this synthetic scored-document fixture,
    # outside the production matcher. Ambiguous occurrences are not resolved here.
    semantic = copy.deepcopy(semantic) if semantic is not None else semantic_review()
    for row in semantic.get("requirements", []):
        for cite in row.get("citations", []):
            if "render_lines" not in cite and cite.get("in_resume"):
                positions = [i for i, line in enumerate(resume.splitlines(), 1) if cite.get("quote") in line]
                cite["render_lines"] = positions if len(positions) == 1 else []
    return te.build_quality_report(
        resume=resume,
        trace=trace(claims if claims is not None else claims_for_resume()),
        career_profile=profile if profile is not None else career_profile(),
        cards=cards if cards is not None else {"ec_00000001": card()},
        semantic_review=semantic,
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
    report = build(resume=RESUME.replace("上海", "/Users/example/private"))
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


def test_r1_4_unconfirmed_l3_ownership_remains_pending_without_semantics():
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
    assert "R1.4" in report["llm_pending"]
    assert "R1.4" not in rules(report, "eligible")
    assert report["auto_pass"] is False


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
    assert "R1.4" in report["llm_pending"]


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
    assert "R1.4" in report["llm_pending"]
    assert set(report["llm_pending"]) >= {"R2.1", "R3.1", "R3.5", "R4.1"}
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
        "schema_version": 2,
        "prompt_version": 10,
        "judged_sections": ["r1_4", "r2_1", "r3_1", "r3_5", "r4_1"],
        "rejected_items": 0,
        "r1_4": r1_4 if r1_4 is not None else [
            {"render_line": line, "status": status, "citations": [source], "reason": reason}
            for line, status, source, reason in [
                (3, "supported", "personal_profile:career.work.w1.title:0", "当前任职确认了平台负责人定位"),
                (15, "not_applicable", "line#15", "此行只列技术栈"),
                (18, "not_applicable", "line#18", "此行是项目名称及期间"),
                (19, "supported", "ec_00000001", "项目角色范围与卡片一致"),
                (20, "not_applicable", "line#20", "此行说明系统背景"),
                (22, "supported", "ec_00000001", "本人活动来自该卡行动"),
                (23, "not_applicable", "line#23", "此行说明性能变化而未提升职责"),
                (26, "supported", "personal_profile:career.work.w1.title:0", "完整任职上下文与当前档案一致"),
            ]
        ],
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
    assert fit["matrix"][0]["first_screen"] is False  # the judge named bullet #1, not the cited occurrence
    distinct = report["tiers"]["distinct"]
    assert distinct["highlights"][0]["highlight_id"] == "hl_b1_d1"
    assert distinct["metrics"]["candidate_count"] == 1
    # 四层仍未全部通过（R3.2 首屏量化），所以 auto_pass 仍为 False，但不再因 LLM pending 而挂起。
    assert report["auto_pass"] is False


def test_judged_r3_1_and_r3_5_and_r1_4_failures_are_reported():
    payload = judged_payload(
        r1_4=[{"render_line": 22, "status": "unsupported", "citations": ["ec_00000001"], "reason": "卡中没有本人负责表述"}],
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
    # 没有当前结果核定；judge 的 True 不能为第二条另授结果信用。
    assert all_rules.count("R3.1") == 2
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
    measured = reviewed_result("ec", 0, "响应延迟降至 80ms", measurement_quote="响应延迟降至 80ms")
    coverage = reviewed_result("ec", 1, "覆盖 8 个品牌", measurement_quote="覆盖 8 个品牌")
    version = reviewed_result("ec", 2, "2023 年完成升级 Java 8")
    assert not te._has_verifiable_quant("采用 Java 8", [measured])
    assert not te._has_verifiable_quant("采用 Java 8", [coverage])
    assert te._has_verifiable_quant("改造查询 · 响应延迟降至 80ms", [measured])
    assert not te._has_verifiable_quant("2023 年完成升级 Java 8", [version])


@pytest.mark.parametrize(("rendered_field", "expected_ratio"), [("actions", 0.0), ("results", 1.0)])
def test_r3_2_counts_only_the_result_fact_actually_rendered(rendered_field, expected_ratio):
    # 同一张卡的两项事实同文同数字；同事范围排除 results:0 时，正文只引用 actions:0。
    # 精确行追溯已能区分这两项事实；R3.2 不得退回整卡 results 池取分。
    from tools.engines.evaluation.tiers.common import inspect_bullet_trace

    sentence = "压测 P95 从 200 ms 降至 120 ms"
    resume = f"## 项目经历\n### 合成性能场景\n- {sentence}\n<!-- first-screen-end -->\n"
    claims = [{
        "text": sentence, "source_kind": "evidence", "field": rendered_field,
        "evidence_id": "ec_same", "fact_id": f"ec_same:{rendered_field}:0", "render_line": 3,
    }]
    evidence = {"ec_same": reviewed_card_results(
        {"id": "ec_same", "actions": [sentence], "results": [sentence]}, measurement_quotes={0: sentence})}
    actual_trace = {"occurrence_lineage_version": 1, "claims": claims}
    rows = inspect_bullet_trace(resume, actual_trace, career_profile={})["bullets"]
    assert rows[0]["verified"] is True
    assert rows[0]["sources"][0]["field"] == rendered_field

    strong = te.evaluate_strong(resume=resume, cards=evidence, trace=actual_trace, career_profile={},
                                config=te.load_quality_config())
    assert strong.metrics["quant_first_screen"] == expected_ratio
    assert strong.metrics["quant_total"] == expected_ratio
    assert any(item.rule == "R3.2" for item in strong.failures) is (expected_ratio == 0.0)


@pytest.mark.parametrize(("version", "fact_id", "expected_ratio"), [
    (None, "ec_1:results:0", 0.0),
    (1, "", 0.0),
    (1, "ec_1:results:7", 0.0),
    (1, "ec_1:results:0", 1.0),
])
def test_r3_2_requires_exact_result_occurrence_not_legacy_word_match(version, fact_id, expected_ratio):
    sentence = "测试范围 P95 从 200 ms 降至 120 ms"
    resume = f"## 项目经历\n- {sentence}\n<!-- first-screen-end -->\n"
    claim = {"text": sentence, "field": "results", "source_kind": "evidence",
             "evidence_id": "ec_1", "fact_id": fact_id, "render_line": 2}
    provenance = {"claims": [claim]}
    if version is not None:
        provenance["occurrence_lineage_version"] = version
    evidence = reviewed_card_results({"id": "ec_1", "results": [sentence]}, measurement_quotes={0: sentence})
    result = te.evaluate_strong(resume=resume, cards={"ec_1": evidence}, career_profile={},
                                trace=provenance, config=te.load_quality_config())
    assert result.metrics["quant_total"] == expected_ratio
    assert result.metrics["quant_first_screen"] == expected_ratio


@pytest.mark.parametrize("review_kind,expected_result,expected_quant", [
    ("missing", False, 0.0), ("nonquant", True, 0.0), ("measured", True, 1.0), ("stale", False, 0.0),
])
def test_r3_consumes_one_current_result_review_instead_of_judge_or_digits(review_kind, expected_result, expected_quant):
    value = "隔离测试中响应时间减半，生产吞吐目标仍为每秒 100 万次"
    quote = "隔离测试中响应时间减半"
    resume = f"## 项目经历\n- {value}\n<!-- first-screen-end -->\n"
    claim = {"text": value, "source_kind": "evidence", "evidence_id": "ec_1",
             "field": "results", "fact_id": "ec_1:results:0", "render_line": 2}
    reviews = {}
    if review_kind != "missing":
        reviews["ec_1:results:0"] = reviewed_result(
            "ec_1", 0, value if review_kind != "stale" else "另一份结果",
            measurement_quote=quote if review_kind == "measured" else None)
    judgments = judged_payload(r3_1=[{"bullet": 1, "scene": True, "action": True,
        "result": not expected_result, "citations": ["ec_1"], "reason": "独立表达判项不能另授结果信用"}])
    result = te.evaluate_strong(
        resume=resume, cards={"ec_1": {"results": [value], "result_reviews": reviews}}, career_profile={},
        trace={"occurrence_lineage_version": 1, "claims": [claim]},
        config=te.load_quality_config(), judgments=judgments)
    assert any(f.rule == "R3.1" for f in result.failures) is (not expected_result)
    assert result.metrics["quant_total"] == expected_quant


def test_project_mapping_accepts_visible_context_line():
    resume = "## 项目经历\n### 售后服务（2024 ~ 2025）\n场景：多品牌售后履约\n- 设计履约流程\n"
    judged = judged_payload(r2_1=[{"jd_item_id": "d1", "status": "weak", "bullet_ref": "line#3",
                                  "citations": ["line#3"], "reason": "相关业务场景"}])
    semantic = semantic_review(("partial",))
    semantic["requirements"][0]["citations"][0].update(quote="多品牌售后履约", render_lines=[3])
    result = build(resume=resume, semantic=semantic, judgments=judged)
    assert "R2.4" not in rules(result, "fit")


def test_resume_judge_cannot_upgrade_partial_pool_support_to_full_support():
    semantic = semantic_review(statuses=("partial",))
    report = build(semantic=semantic, judgments=judged_payload())
    row = report["tiers"]["fit"]["matrix"][0]
    assert row["status"] == "weak"


def test_verified_result_text_is_an_outcome_without_numeric_metric():
    resume = "## 项目经历\n### 接口对接（2024）\n- 实现用友 NC 接口集成\n"
    claims = [{"text": "实现用友 NC 接口集成", "source_kind": "evidence", "evidence_id": "ec_1",
               "field": "results", "fact_id": "ec_1:results:0", "render_line": 3}]
    judged = judged_payload(r3_1=[{"bullet": 1, "scene": True, "action": True, "result": False,
                                   "citations": ["ec_1"], "reason": "没有量化指标"}])
    evidence = reviewed_card_results({"id": "ec_1", "results": ["实现用友 NC 接口集成"]})
    result = te.evaluate_strong(resume=resume, cards={"ec_1": evidence}, career_profile={},
        trace={"occurrence_lineage_version": 1, "claims": claims},
        config=te.load_quality_config(), judgments=judged)
    assert not any(f.rule == "R3.1" for f in result.failures)
    assert any(f.rule == "R3.2" for f in result.failures)


def test_three_nominations_are_ranked_to_two_not_rejected_as_three_chosen():
    candidates = [{"highlight_id": f"hl_{i}", "bullet": 1, "jd_item_id": f"d{i}",
                   "exceeds": ["scale"], "level": "L1"} for i in range(3)]
    result = te.evaluate_distinct(resume="- 完成平台\n<!-- first-screen-end -->",
                                 candidates=candidates, config=te.load_quality_config())
    assert result.passed and len(result.highlights) == 2


@pytest.fixture
def l8_role_inputs():
    text = "主导接口模块对接，并完成固定样例验收。"
    profile = career_profile()
    profile["career"]["skills"][0]["description"] = text
    return {
        "resume": "## 核心能力\n- " + text,
        "trace": {
            "status": "verified",
            "occurrence_lineage_version": 1,
            "evidence_card_ids": [],
            "claims": [{
                "source_kind": "personal_profile",
                "field": "career.skills.s1.description",
                "fact_id": "personal_profile:career.skills.s1.description:0",
                "evidence_id": "", "text": text, "render_line": 2,
            }],
        },
        "career_profile": profile,
        "cards": {"ec_00000001": card(actions=[text])},
        "semantic_review": None,
        "job_context": job_context(),
        "pdf_check": {"pages": 2, "clipped": False},
        "judgments": None,
    }


@pytest.mark.parametrize("case", ["confirmed-profile", "ordinary-confirmed-profile"])
def test_l8_empty_role_review_set_does_not_require_model(l8_role_inputs, case):
    inputs = l8_role_inputs
    if case == "ordinary-confirmed-profile":
        text = "完成接口模块对接，并记录固定样例验收结果。"
        inputs["resume"] = "## 核心能力\n- " + text
        inputs["career_profile"]["career"]["skills"][0]["description"] = text
        inputs["trace"]["claims"][0]["text"] = text

    report = te.build_quality_report(**inputs)

    assert "R1.4" not in rules(report, "eligible")
    assert "R1.4" not in report["llm_pending"]
    assert set(report["llm_pending"]) == {"R2.1", "R2.3", "R3.1", "R3.5", "R4.1", "R4.4"}
    assert report["auto_pass"] is False


@pytest.mark.parametrize("case", ["evidence", "mixed", "unreviewed", "rewritten", "incomplete-trace"])
def test_l8_profile_bypass_requires_current_verbatim_exclusive_complete_source(l8_role_inputs, case):
    inputs = l8_role_inputs
    claim = inputs["trace"]["claims"][0]
    if case == "evidence":
        claim.update(source_kind="evidence", field="actions", fact_id="ec_00000001:actions:0",
                     evidence_id="ec_00000001")
        inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    elif case in {"mixed", "incomplete-trace"}:
        prefix, suffix = "主导接口模块对接，", "并完成固定样例验收。"
        inputs["career_profile"]["career"]["work"][0]["contributions"] = [prefix]
        claim.update(field="career.work.w1.contributions",
                     fact_id="personal_profile:career.work.w1.contributions:0", text=prefix)
        if case == "mixed":
            inputs["cards"]["ec_00000001"]["actions"] = [suffix]
            inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
            inputs["trace"]["claims"].append({
                "source_kind": "evidence", "field": "actions", "fact_id": "ec_00000001:actions:0",
                "evidence_id": "ec_00000001", "text": suffix, "render_line": 2,
            })
    elif case == "unreviewed":
        inputs["career_profile"]["career_status"]["reviewed"] = False
    elif case == "rewritten":
        inputs["resume"] = "## 核心能力\n- 独立" + claim["text"]

    report = te.build_quality_report(**inputs)

    assert "R1.4" in report["llm_pending"]
    assert "R1.4" not in rules(report, "eligible")
    assert set(report["llm_pending"]) - {"R1.4"} == {"R2.1", "R2.3", "R3.1", "R3.5", "R4.1", "R4.4"}
    assert report["auto_pass"] is False


@pytest.mark.parametrize("level", ["L5", "L3"])
def test_unconfirmed_role_level_needs_semantics_and_keeps_unsupported_failure(l8_role_inputs, level):
    inputs = l8_role_inputs
    claim = inputs["trace"]["claims"][0]
    claim.update(source_kind="evidence", field="actions", fact_id="ec_00000001:actions:0",
                 evidence_id="ec_00000001")
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["cards"]["ec_00000001"]["role_scope_provenance"] = {"level": level, "evidence": []}

    report = te.build_quality_report(**inputs)

    assert "R1.4" not in rules(report, "eligible")
    assert "R1.4" in report["llm_pending"]
    assert set(report["llm_pending"]) - {"R1.4"} == {"R2.1", "R2.3", "R3.1", "R3.5", "R4.1", "R4.4"}
    assert report["auto_pass"] is False

    inputs["judgments"] = judged_payload(
        r1_4=[{"render_line": 2, "status": "unsupported", "citations": ["ec_00000001"],
                "reason": "当前来源未建立本人接口模块主导责任。"}], r2_1=[], r3_1=[], r4_1=[],
    )
    reviewed = te.build_quality_report(**inputs)
    failures = [item for item in reviewed["tiers"]["eligible"]["failures"] if item["rule"] == "R1.4"]
    assert len(failures) == 1
    assert "line#2" in failures[0]["target"] and "ec_00000001" in failures[0]["target"]
    assert reviewed["tiers"]["eligible"]["passed"] is False
    assert "R1.4" not in reviewed["llm_pending"]
    assert reviewed["auto_pass"] is False


def test_l8_confirmed_sourced_l3_still_requires_semantic_review(l8_role_inputs):
    inputs = l8_role_inputs
    claim = inputs["trace"]["claims"][0]
    claim.update(source_kind="evidence", field="actions", fact_id="ec_00000001:actions:0",
                 evidence_id="ec_00000001")
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["cards"]["ec_00000001"]["role_scope_provenance"] = {
        "level": "L3", "confirmed_by_user": True,
        "evidence": [{"material_id": "m", "document_id": "d", "excerpt": claim["text"]}],
    }

    report = te.build_quality_report(**inputs)

    assert "R1.4" not in rules(report, "eligible")
    assert "R1.4" in report["llm_pending"]
    assert set(report["llm_pending"]) - {"R1.4"} == {"R2.1", "R2.3", "R3.1", "R3.5", "R4.1", "R4.4"}
    assert report["auto_pass"] is False


@pytest.mark.parametrize("case", ["missing-second", "false-true", "true-false"])
def test_l8_direct_report_rechecks_role_coverage_and_rejects_duplicate_judgments(l8_role_inputs, case):
    inputs = l8_role_inputs
    first = inputs["trace"]["claims"][0]["text"]
    second = "负责接口错误码映射与回放记录归档。"
    inputs["resume"] = "## 核心能力\n- " + first + "\n- " + second
    inputs["cards"]["ec_00000001"]["actions"] = [first, second]
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["trace"]["claims"] = [
        {"source_kind": "evidence", "field": "actions", "fact_id": f"ec_00000001:actions:{index}",
         "evidence_id": "ec_00000001", "text": text, "render_line": index + 2}
        for index, text in enumerate([first, second])
    ]
    valid_first = {"render_line": 2, "status": "supported", "citations": ["ec_00000001"], "reason": "模块责任有据"}
    valid_second = {"render_line": 3, "status": "supported", "citations": ["ec_00000001"], "reason": "归档责任有据"}
    rejected_first = {**valid_first, "status": "unsupported", "reason": "该职责没有依据"}
    if case == "missing-second":
        rows = [valid_first]
    elif case == "false-true":
        rows = [rejected_first, valid_first, valid_second]
    else:
        rows = [valid_first, rejected_first, valid_second]
    inputs["judgments"] = judged_payload(r1_4=rows, r2_1=[], r3_1=[], r4_1=[])

    report = te.build_quality_report(**inputs)

    assert report["llm_pending"] == ["R1.4"]
    assert report["auto_pass"] is False
    if case != "missing-second":
        reversed_inputs = {**inputs, "judgments": {**inputs["judgments"], "r1_4": list(reversed(rows))}}
        reversed_report = te.build_quality_report(**reversed_inputs)
        assert reversed_report["llm_pending"] == ["R1.4"]
        failures = [item for item in report["tiers"]["eligible"]["failures"] if item["rule"] == "R1.4"]
        reversed_failures = [item for item in reversed_report["tiers"]["eligible"]["failures"] if item["rule"] == "R1.4"]
        assert failures == reversed_failures


def test_verbatim_confirmed_profile_role_does_not_need_duplicate_model_confirmation():
    text = "承担开发负责人职责"
    profile = career_profile()
    profile["career"]["skills"][0]["description"] = text
    claims = [{"text": text, "source_kind": "personal_profile",
               "field": "career.skills.s1.description", "evidence_id": "",
               "fact_id": "personal_profile:career.skills.s1.description:0", "render_line": 2}]
    report = build(resume="## 核心能力\n- " + text, claims=claims, profile=profile,
                   judgments=judged_payload(r1_4=[]))
    assert "R1.4" not in rules(report, "eligible")
    assert "R1.4" not in report["llm_pending"]
    assert "R1.1" not in rules(report, "eligible")
    profile["career"]["skills"][0]["description"] = "参与联调"
    report = build(resume="## 核心能力\n- " + text, claims=claims, profile=profile,
                   judgments=judged_payload(r1_4=[]))
    assert "R1.1" in rules(report, "eligible")
    assert "R1.4" in report["llm_pending"]
    assert report["auto_pass"] is False


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
    positions = {7: 6, 15: 22, 18: 9, 19: 10, 20: 11, 22: 12, 23: 13, 26: 19, 29: 25, 30: 26}
    claims = [
        {**claim, "render_line": positions[claim["render_line"]]}
        for claim in claims_for_resume() if claim["render_line"] in positions
    ]
    claims.append(
        {"text": "覆盖 8 个品牌", "source_kind": "evidence", "field": "results", "evidence_id": "ec_00000001",
         "fact_id": "ec_00000001:results:1", "render_line": 14}
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
    positions = {6: 15, 9: 5, 10: 6, 11: 7, 12: 8, 13: 9, 14: 10, 19: 18, 22: 21, 25: 24, 26: 25}
    return [
        {**claim, "render_line": positions[claim["render_line"]]}
        for claim in first_screen_project_claims()
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
        r1_4=[
            {"render_line": line, "status": status, "citations": [source], "reason": reason}
            for line, status, source, reason in [
                (3, "supported", "personal_profile:career.work.w1.title:0", "当前档案任职支持定位"),
                (9, "not_applicable", "line#9", "项目名称与期间"),
                (10, "supported", "ec_00000001", "卡片支持该项目角色"),
                (11, "not_applicable", "line#11", "系统背景"),
                (12, "supported", "ec_00000001", "原行动为本人活动"),
                (13, "not_applicable", "line#13", "性能变化陈述"),
                (14, "not_applicable", "line#14", "覆盖规模陈述"),
                (19, "supported", "personal_profile:career.work.w1.title:0", "同一当前任职记录"),
                (22, "not_applicable", "line#22", "技术栈列表"),
            ]
        ],
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
        "occurrence_coverage_known": True,
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


def test_exact_later_occurrence_cannot_use_an_equal_first_screen_bullet_or_judge_reference():
    resume = "## 项目经历\n- 完成平台抽象\n<!-- first-screen-end -->\n- 完成平台抽象\n"
    semantic = semantic_review()
    semantic["requirements"][0]["citations"][0]["render_lines"] = [4]
    decision = judged_payload(r2_1=[{"jd_item_id":"d1","status":"supported","bullet_ref":"bullet#1"}])
    result = build(resume=resume, semantic=semantic, judgments=decision)
    row = result["tiers"]["fit"]["matrix"][0]
    assert row["status"] == "supported" and row["bullet_ref"] == "bullet#2"
    assert row["first_screen"] is False
    semantic["requirements"][0]["resume_status"] = "not_present"
    semantic["requirements"][0]["citations"][0].update(in_resume=False, render_lines=[])
    result = build(resume=resume, semantic=semantic, judgments=decision)
    row = result["tiers"]["fit"]["matrix"][0]
    assert row["status"] == "absent" and not row["bullet_ref"] and not row["first_screen"]


def test_one_exact_claim_never_verifies_a_separate_identical_bullet():
    from tools.engines.evaluation.tiers.common import inspect_bullet_trace
    resume = "## 项目经历\n- 完成平台抽象\n- 完成平台抽象\n"
    checks = inspect_bullet_trace(resume, {"occurrence_lineage_version":1,"claims":[
        {"text":"完成平台抽象","source_kind":"evidence","field":"actions",
         "evidence_id":"ec_fixture","fact_id":"ec_fixture:actions:0","render_line":3}
    ]}, career_profile={})
    assert [item["verified"] for item in checks["bullets"]] == [False,True]


@pytest.mark.parametrize("pages,clipped,verified,passed,advice", [
    (2, None, False, False, "apply"),
    (2, False, True, True, "apply"),
    (2, True, True, False, "strengthen"),
    (3, None, False, False, "strengthen"),
    (None, True, False, False, "strengthen"),
])
def test_pdf_checks_require_independent_page_and_clip_evidence(pages, clipped, verified, passed, advice):
    check = {"pages": pages, "clipped": clipped}
    fixture = {"resume": FIRST_SCREEN_PROJECT_RESUME, "claims": first_screen_project_claims(),
               "highlights": first_screen_highlight()}
    for rep in (build(pdf_check=check, **fixture), te.apply_pdf_check(build(pdf_check=None, **fixture), check)):
        tier = rep["tiers"]["eligible"]
        assert tier["metrics"]["pdf_check_state"] == ("verified" if verified else "unverified")
        assert tier["metrics"]["pdf_pages"] == pages
        assert tier["metrics"]["clip_check"] is clipped
        assert tier["passed"] is passed
        assert rep["delivery_advice"]["recommendation"] == advice
        assert te.recompute_auto_pass({"tiers": {**rep["tiers"],
            "fit": {"passed": True}, "strong": {"passed": True}, "distinct": {"passed": True}}}) is passed
        reasons = [f["reason"] for f in tier["failures"] if f["rule"] == "R1.5"]
        assert any("超过" in r for r in reasons) is (pages == 3)
        assert any("存在裁切" in r for r in reasons) is (clipped is True)


@pytest.mark.parametrize("case", [
    "current", "sibling-id", "field", "source-owner", "current-value",
    "no-career", "unconfirmed", "other-physical-line",
])
def test_l10_profile_trace_credit_requires_current_identity_and_line(l8_role_inputs, case):
    inputs = l8_role_inputs
    claim = inputs["trace"]["claims"][0]
    text = claim["text"]
    if case == "sibling-id":
        claim["fact_id"] = "personal_profile:career.skills.s1.description:1"
    elif case == "field":
        inputs["career_profile"]["career"]["summary"] = text
        claim["field"] = "career.summary"
    elif case == "source-owner":
        claim["evidence_id"] = "ec_00000001"
    elif case == "current-value":
        inputs["career_profile"]["career"]["summary"] = text
        inputs["career_profile"]["career"]["skills"][0]["description"] = "参与接口字段整理，不承担验收主导。"
    elif case == "no-career":
        inputs["career_profile"] = {}
    elif case == "unconfirmed":
        inputs["career_profile"]["career_status"]["reviewed"] = False
    elif case == "other-physical-line":
        inputs["resume"] += "\n- " + text
        claim["render_line"] = 3

    report = te.build_quality_report(**inputs)

    metrics = report["tiers"]["eligible"]["metrics"]
    assert metrics["total_bullets"] == (2 if case == "other-physical-line" else 1)
    assert metrics["verified_bullets"] == (1 if case in {"current", "other-physical-line"} else 0)
    assert ("R1.1" in rules(report, "eligible")) is (case != "current")
    assert ("R1.4" in report["llm_pending"]) is (case != "current")
    assert set(report["llm_pending"]) - {"R1.4"} == {"R2.1", "R2.3", "R3.1", "R3.5", "R4.1", "R4.4"}
    assert report["auto_pass"] is False


@pytest.mark.parametrize("layout", [
    "bullet", "role", "duty", "summary", "background", "employment", "position", "body-contact-value",
])
def test_l10_unjudged_responsibility_is_pending_by_actual_line_not_trigger_word(l8_role_inputs, layout):
    inputs = l8_role_inputs
    text = "统筹接口模块的联调方案、边界检查与验收归档。"
    lines = {
        "bullet": ["## 项目经历", "- " + text],
        "role": ["## 项目经历", "角色：" + text],
        "duty": ["## 工作经历", "职责：" + text],
        "summary": ["## 职业概述", text],
        "background": ["## 项目经历", "背景：" + text],
        "employment": ["## 工作经历", "### 合成实验室 · 接口统筹工程师（2024-01 ~ 2025-06）"],
        "position": ["# 合成候选人", "当前定位：接口统筹工程师"],
        "body-contact-value": [
            "## 项目经历", "- 统筹接口异常处置，归档至 owner@example.invalid，追踪编号 12345678。"],
    }[layout]
    inputs["resume"] = "\n".join(lines)
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["cards"]["ec_00000001"]["actions"] = [text]
    if layout in {"employment", "position"}:
        inputs["trace"]["claims"] = [{
            "text": "接口统筹工程师", "source_kind": "personal_profile",
            "field": "current_position", "evidence_id": "",
        }]
    else:
        value = lines[1].removeprefix("- ").removeprefix("角色：").removeprefix("职责：").removeprefix("背景：")
        field = "role_scope" if layout == "role" else "context" if layout == "background" else "actions"
        inputs["cards"]["ec_00000001"][field] = [value] if field == "actions" else value
        inputs["trace"]["claims"] = [{
            "text": value, "source_kind": "evidence", "field": field,
            "fact_id": f"ec_00000001:{field}:0", "evidence_id": "ec_00000001", "render_line": 2,
        }]

    report = te.build_quality_report(**inputs)

    assert "R1.4" in report["llm_pending"]
    assert "R1.4" not in rules(report, "eligible")
    assert report["auto_pass"] is False


@pytest.mark.parametrize("case", [
    "supported", "unsupported", "unknown", "self-citation-only", "other-person", "denied-responsibility",
])
def test_l10_direct_report_uses_semantic_role_status_and_independent_source(l8_role_inputs, case):
    inputs = l8_role_inputs
    text = "统筹接口模块的联调方案、边界检查与验收归档。"
    status = "supported"
    citation = "ec_00000001"
    if case == "unsupported":
        text = "统筹整个平台的总体方案、生产容量规划与发布。"
        status = "unsupported"
        inputs["cards"]["ec_00000001"]["role_scope"] = "仅参与接口字段整理，总体方案与生产发布由平台组承担"
    elif case == "unknown":
        status = "unknown"
    elif case == "self-citation-only":
        citation = "line#2"
    elif case == "other-person":
        text = "平台总体架构由另一团队负责，本条仅说明项目分工。"
        status = "not_applicable"
        citation = "line#2"
    elif case == "denied-responsibility":
        text = "本人未负责该项目的总体架构，也未承担生产发布。"
        status = "not_applicable"
        citation = "line#2"
    inputs["resume"] = "## 项目经历\n- " + text
    inputs["cards"]["ec_00000001"]["actions"] = [text]
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["trace"]["claims"] = [{
        "source_kind": "evidence", "field": "actions", "fact_id": "ec_00000001:actions:0",
        "evidence_id": "ec_00000001", "text": text, "render_line": 2,
    }]
    inputs["judgments"] = judged_payload(
        r1_4=[{"render_line": 2, "status": status, "citations": [citation],
               "reason": "核对完整表达中的本人范围、他人主体及来源限制。"}],
        r2_1=[], r3_1=[], r4_1=[],
    )

    report = te.build_quality_report(**inputs)

    assert ("R1.4" in report["llm_pending"]) is (case in {"unknown", "self-citation-only"})
    assert ("R1.4" in rules(report, "eligible")) is (case == "unsupported")
    assert report["tiers"]["eligible"]["metrics"]["verified_bullets"] == 1
    assert report["auto_pass"] is False


def test_l10_unknown_card_role_does_not_negate_independently_reviewed_result(l8_role_inputs):
    inputs = l8_role_inputs
    text = "本人负责的接口模块已完成联调验收，并交付完整的固定样例记录。"
    inputs["resume"] = "## 项目经历\n- " + text
    inputs["cards"] = {"ec_00000001": reviewed_card_results(
        card(role_scope="", role_scope_provenance={"level": "L5"}, results=[text]),
        measurement_quotes={0: None},
    )}
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["trace"]["claims"] = [{
        "source_kind": "evidence", "field": "results", "fact_id": "ec_00000001:results:0",
        "evidence_id": "ec_00000001", "text": text, "render_line": 2,
    }]

    pending = te.build_quality_report(**inputs)
    assert "R1.4" not in rules(pending, "eligible")
    assert "R1.4" in pending["llm_pending"]
    inputs["judgments"] = judged_payload(
        r1_4=[{"render_line": 2, "status": "supported", "citations": ["ec_00000001"],
               "reason": "该结果有独立的本人范围核定，未宣称整个平台职责。"}],
        r2_1=[], r3_1=[], r4_1=[],
    )
    reviewed = te.build_quality_report(**inputs)
    assert "R1.4" not in rules(reviewed, "eligible")
    assert "R1.4" not in reviewed["llm_pending"]
    assert reviewed["tiers"]["strong"]["metrics"]["quant_total"] == 0


def test_l10_structural_header_has_no_role_target_or_jd_credit(l8_role_inputs):
    inputs = l8_role_inputs
    inputs["resume"] = "# 合成候选人\n13800000000 | synthetic@example.invalid\n求职意向：平台统筹负责人\n## 项目经历\n<!-- first-screen-end -->\n"
    inputs["trace"]["claims"] = []
    inputs["semantic_review"] = {
        "mode": "semantic", "occurrence_coverage_known": True,
        "fit_score": 0, "resume_score": 0,
        "requirements": [{
            "requirement_id": "d1", "kind": "must_have", "text": "平台总体方案统筹",
            "status": "insufficient", "resume_status": "not_present", "citations": [],
        }],
    }
    inputs["judgments"] = judged_payload(
        r1_4=[], r2_1=[{"jd_item_id": "d1", "status": "supported", "bullet_ref": "line#3",
                        "citations": ["line#3"], "reason": "仅有求职意向文字"}],
        r3_1=[], r4_1=[],
    )

    report = te.build_quality_report(**inputs)

    assert "R1.4" not in report["llm_pending"]
    assert "R1.1" in rules(report, "eligible")
    assert report["tiers"]["eligible"]["metrics"]["total_bullets"] == 0
    assert report["tiers"]["fit"]["matrix"][0]["status"] == "absent"
    assert not report["tiers"]["fit"]["matrix"][0]["bullet_ref"]
    assert report["tiers"]["strong"]["metrics"]["quant_total"] == 0
    assert report["auto_pass"] is False


def test_l10_extra_role_lines_do_not_change_bullet_or_result_credit(l8_role_inputs):
    inputs = l8_role_inputs
    action = "实现接口字段映射并完成固定样例回放。"
    result = "在单客户端隔离回放中，耗时由 20 毫秒降至 12 毫秒。"
    role = "统筹 37 个接口的联调组织，不承担平台生产发布。"
    inputs["cards"] = {"ec_00000001": reviewed_card_results(
        card(actions=[action], results=[result], role_scope=role), measurement_quotes={0: result},
    )}
    inputs["resume"] = "## 项目经历\n- " + action + "\n- " + result
    inputs["trace"]["evidence_card_ids"] = ["ec_00000001"]
    inputs["trace"]["claims"] = [
        {"source_kind": "evidence", "field": field, "fact_id": f"ec_00000001:{field}:0",
         "evidence_id": "ec_00000001", "text": value, "render_line": line}
        for field, value, line in (("actions", action, 2), ("results", result, 3))
    ]
    inputs["semantic_review"] = {
        "mode": "semantic", "occurrence_coverage_known": True, "fit_score": 0, "resume_score": 0,
        "requirements": [{"requirement_id": "d1", "kind": "must_have", "text": "平台总体方案统筹",
                          "status": "insufficient", "resume_status": "not_present", "citations": []}],
    }
    original = te.build_quality_report(**inputs)
    inputs["resume"] = "\n".join([
        "# 合成候选人", "当前定位：平台总体方案统筹", "求职意向：平台总体方案统筹",
        "## 项目经历", "角色：" + role, "- " + action, "- " + result,
    ])
    for row in inputs["trace"]["claims"]:
        row["render_line"] += 4
    inputs["trace"]["claims"].append({
        "source_kind": "evidence", "field": "role_scope", "fact_id": "ec_00000001:role_scope:0",
        "evidence_id": "ec_00000001", "text": role, "render_line": 5,
    })
    inputs["judgments"] = judged_payload(
        r1_4=[], r2_1=[{"jd_item_id": "d1", "status": "supported", "bullet_ref": "line#2",
                       "citations": ["line#2"], "reason": "只有头部定位"}],
        r3_1=[], r4_1=[],
    )
    expanded = te.build_quality_report(**inputs)

    for report in (original, expanded):
        assert report["tiers"]["eligible"]["metrics"]["total_bullets"] == 2
        assert report["tiers"]["eligible"]["metrics"]["verified_bullets"] == 2
        assert report["tiers"]["strong"]["metrics"]["quant_total"] == 0.5
        assert report["tiers"]["fit"]["matrix"][0]["status"] == "absent"
        assert not report["tiers"]["fit"]["matrix"][0]["bullet_ref"]


def test_l10_rule_engine_rechecks_profile_identity_before_trace_credit(generation, monkeypatch):
    from dataclasses import replace
    from tests.unit.engines.test_complete_resume import complete_profile
    from tools.domain.models import JobProfile
    from tools.engines.evaluation.rule_evaluator import RuleEvaluationEngine
    from tools.infra.llm import client as llm
    from tools.sidecar.handlers import profile as profile_api

    def unexpected_http(*args, **kwargs):
        pytest.fail("规则评测的来源回归不得调用模型或外部服务")

    monkeypatch.setattr(llm.request, "urlopen", unexpected_http)
    assembler, identity, matching, paths = generation
    basic = complete_profile()
    for work in basic["career"]["work"]:
        work["evidence_ids"] = [identity.id]
    for skill in basic["career"]["skills"]:
        skill["evidence_ids"] = [identity.id]
    monkeypatch.setattr(profile_api, "_PROFILE_PATH", paths["profile"])
    meta = {"correlation_id": "l10-profile-source"}
    current = profile_api.handle_profile_get({"meta": meta})["profile"]
    profile_api.handle_profile_update({
        "meta": meta, "expected_revision": current["revision"], "patch": basic,
    })
    current = profile_api.handle_profile_get({"meta": meta})["profile"]
    profile_api.handle_profile_review({
        "meta": meta, "expected_revision": current["revision"], "confirmed": True,
    })
    assert profile_api.handle_profile_get({"meta": meta})["profile"]["career_status"]["reviewed"]
    before = {name: paths[name].read_bytes() for name in ("card", "profile", "job", "jd")}
    resume = assembler.generate(matching, [identity], "l10-profile-source")
    job = JobProfile(id=matching.job_profile_id, title="工程师", keywords=(), level="")
    engine = RuleEvaluationEngine()
    valid = engine.evaluate(resume, job)
    valid_metrics = valid.quality_report["tiers"]["eligible"]["metrics"]
    assert valid_metrics["verified_bullets"] == valid_metrics["total_bullets"]

    damaged = copy.deepcopy(resume.generation_trace)
    claim, = [row for row in damaged["claims"] if row.get("field") == "career.skills.s1.description"]
    assert claim["fact_id"] == "personal_profile:career.skills.s1.description:0"
    claim["fact_id"] = "personal_profile:career.skills.s1.description:1"
    changed = replace(resume, generation_trace=damaged)
    try:
        invalid = engine.evaluate(changed, job)
    except ValueError as exc:
        assert str(exc) == "generation_trace_invalid"
    else:
        assert invalid.quality_report["tiers"]["eligible"]["metrics"]["verified_bullets"] == valid_metrics["verified_bullets"] - 1
        assert "R1.1" in rules(invalid.quality_report, "eligible")
        assert invalid.dimension_scores["citation"] < valid.dimension_scores["citation"]
    assert changed.content == resume.content
    assert {name: paths[name].read_bytes() for name in before} == before


def test_l10_individually_valid_profile_facts_do_not_confirm_cross_work_relationship(l8_role_inputs):
    inputs = l8_role_inputs
    first = inputs["career_profile"]["career"]["work"][0]
    second = copy.deepcopy(first)
    second.update({
        "id": "w2", "company": "另一合成公司", "title": "接口负责人",
        "start": "2020-01", "end": "2022-12", "current": False,
    })
    inputs["career_profile"]["career"]["work"].append(second)
    inputs["resume"] = "## 工作经历\n### 示例科技 · 接口负责人（2020-01 ~ 2022-12）"
    inputs["trace"]["claims"] = [
        {"source_kind": "personal_profile", "evidence_id": "", "field": f"career.work.{work['id']}.{field}",
         "fact_id": f"personal_profile:career.work.{work['id']}.{field}:0", "text": work[field], "render_line": 2}
        for work, field in ((first, "company"), (second, "title"), (second, "start"), (second, "end"))
    ]

    report = te.build_quality_report(**inputs)

    assert "R1.4" in report["llm_pending"]
    assert "R1.4" not in rules(report, "eligible")
    assert report["tiers"]["eligible"]["metrics"]["total_bullets"] == 0
    assert report["auto_pass"] is False
