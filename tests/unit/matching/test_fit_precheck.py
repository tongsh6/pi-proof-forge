"""岗位适配预检：assessed 优先、规则预检兜底；纯函数、不调用模型。"""
from __future__ import annotations

from tools.engines.matching import fit_precheck as fp

CARDS = [
    {
        "id": "ec_1",
        "title": "电商交易平台核心开发",
        "context": "面向电商交易链路，使用 Spring Boot 微服务架构。",
        "role_scope": "Java 后端开发",
        "stack": ["Java", "Spring Boot", "MySQL", "Redis"],
        "actions": ["重构交易下单链路"],
        "results": ["接口耗时降低 40%"],
        "tags": ["电商"],
    },
    {
        "id": "ec_2",
        "title": "平台研发效能建设",
        "context": "统一 CI/CD 与 Kubernetes 发布流程。",
        "role_scope": "平台负责人",
        "stack": ["Kubernetes", "Docker", "CI/CD"],
        "actions": ["建设发布流水线"],
        "results": [],
        "tags": [],
    },
]


def profile(**overrides):
    value = {
        "target_role": "Java 技术专家",
        "company": "示例公司",
        "keywords": ["Java", "Spring Boot", "MySQL", "Redis"],
        "must_have": ["熟悉 Java 微服务开发"],
        "nice_to_have": ["Kubernetes"],
    }
    value.update(overrides)
    return value


def snapshot(**overrides):
    value = {"fit_state": "unassessed", "fit_failures": 0, "match_score": 0, "advice": None}
    value.update(overrides)
    return value


def test_evidence_corpus_collects_card_signals_and_skips_empty():
    corpus = fp.build_evidence_corpus(CARDS)
    assert corpus["card_count"] == 2
    assert "java" in corpus["text"] and "微服务" in corpus["text"]
    assert fp.build_evidence_corpus([])["card_count"] == 0
    # 只有 id/无文本信号的卡不进入语料。
    assert fp.build_evidence_corpus([{"id": "ec_empty"}])["card_count"] == 0


def test_assessed_snapshot_uses_quick_run_result_first():
    passed = fp.precheck_profile(profile(), snapshot(fit_state="passed", match_score=85), fp.build_evidence_corpus(CARDS))
    assert passed["source"] == "assessed"
    assert passed["state"] == "recommended"
    assert passed["rank"] == 0
    assert passed["basis"] == "assessed_quick_run"
    assert passed["match_score"] == 85

    failed = fp.precheck_profile(profile(), snapshot(fit_state="failed", fit_failures=2, fit_score=85, match_score=80), fp.build_evidence_corpus(CARDS))
    assert failed["state"] == "consider"
    assert failed["rank"] == 1
    assert failed["fit_failures"] == 2
    assert failed["fit_score"] == 85
    assert failed["match_score"] == 80

    many = fp.precheck_profile(profile(), snapshot(fit_state="failed", fit_failures=5, fit_score=56), fp.build_evidence_corpus(CARDS))
    assert many["state"] == "caution"


def test_assessed_advice_overrides_state_when_available():
    corpus = fp.build_evidence_corpus(CARDS)
    for recommendation, state in (
        ("apply", "recommended"),
        ("strengthen", "consider"),
        ("reconsider", "caution"),
        ("fix_facts", "hold"),
    ):
        item = fp.precheck_profile(
            profile(),
            snapshot(fit_state="failed", fit_failures=1, fit_score=None, advice={"recommendation": recommendation}),
            corpus,
        )
        assert item["state"] == state, recommendation


def test_rule_precheck_matches_requirements_and_returns_explainable_terms():
    corpus = fp.build_evidence_corpus(CARDS)
    item = fp.precheck_profile(profile(), None, corpus)
    assert item["source"] == "rule"
    assert item["state"] in {"promising", "caution"}
    assert item["coverage"] is not None and item["coverage"] > 0
    assert item["matched_requirements"] >= 2
    assert "Java" in item["matched_terms"]
    assert item["evidence_hits"] >= 1
    assert item["basis"] == "rule_evidence_overlap"


def test_rule_precheck_high_coverage_is_promising():
    corpus = fp.build_evidence_corpus(CARDS)
    enriched = profile(
        keywords=["Java", "Spring Boot", "MySQL", "Redis", "微服务", "电商"],
        must_have=["熟悉 Java 微服务开发"],
        nice_to_have=[],
    )
    item = fp.precheck_profile(enriched, None, corpus)
    assert item["coverage"] >= fp.PROMISING_COVERAGE
    assert item["state"] == "promising"
    assert item["rank"] == 2


def test_rule_precheck_unrelated_target_is_low():
    corpus = fp.build_evidence_corpus(CARDS)
    unrelated = profile(
        keywords=["LDO", "Bandgap", "CMOS", "模拟IC设计"],
        must_have=["熟悉 CMOS / BCD 工艺器件"],
        nice_to_have=[],
    )
    item = fp.precheck_profile(unrelated, None, corpus)
    assert item["state"] == "low"
    assert item["coverage"] < fp.CAUTION_COVERAGE
    assert item["missing_terms"], "低匹配要能说明缺什么"


def test_rule_precheck_does_not_count_substring_shorthand_as_match():
    corpus = fp.build_evidence_corpus(
        [{"id": "ec_x", "title": "前端开发", "stack": ["JavaScript"], "context": "", "actions": [], "results": [], "tags": []}]
    )
    item = fp.precheck_profile(
        profile(keywords=["Java"], must_have=[], nice_to_have=[]),
        None,
        corpus,
    )
    assert item["state"] == "low", item
    assert "Java" not in item["matched_terms"]


def test_rule_precheck_skips_unverifiable_years_and_degree_requirements():
    corpus = fp.build_evidence_corpus(CARDS)
    item = fp.precheck_profile(
        profile(
            keywords=["Java"],
            must_have=["5年以上Java后端开发经验", "本科及以上学历，计算机相关专业"],
            nice_to_have=[],
        ),
        None,
        corpus,
    )
    # 年限/学历不可由证据卡验证，不应把规则预检结果拉低或伪装成已覆盖。
    assert item["total_requirements"] == 1
    assert item["matched_requirements"] == 1
    assert item["state"] == "promising"


def test_rule_precheck_reports_insufficient_when_no_requirements_or_evidence():
    empty_profile = profile(keywords=[], must_have=[], nice_to_have=[])
    item = fp.precheck_profile(empty_profile, None, fp.build_evidence_corpus(CARDS))
    assert item["source"] == "insufficient"
    assert item["state"] == "unknown"
    assert item["basis"] == "insufficient_requirements"

    no_evidence = fp.precheck_profile(profile(), None, fp.build_evidence_corpus([]))
    assert no_evidence["source"] == "insufficient"
    assert no_evidence["state"] == "unknown"
    assert no_evidence["basis"] == "insufficient_evidence"


def test_precheck_rank_orders_states_and_tolerates_missing_fields():
    assert fp.precheck_rank({"state": "recommended"}) == 0
    assert fp.precheck_rank({"state": "low"}) == 6
    assert fp.precheck_rank({}) == fp.RANK_BY_STATE["unknown"]
    ranking = [fp.precheck_rank({"state": state}) for state in (
        "recommended", "consider", "promising", "caution", "hold", "unknown", "low",
    )]
    assert ranking == sorted(ranking)


def test_precheck_is_deterministic_and_does_not_mutate_inputs():
    corpus = fp.build_evidence_corpus(CARDS)
    source = profile()
    before = repr(source)
    first = fp.precheck_profile(source, None, corpus)
    second = fp.precheck_profile(source, None, corpus)
    assert first == second
    assert repr(source) == before


def test_failed_assessment_with_low_fit_score_is_ranked_low():
    corpus = fp.build_evidence_corpus(CARDS)
    item = fp.precheck_profile(
        profile(),
        snapshot(fit_state="failed", fit_failures=2, fit_score=25),
        corpus,
    )
    assert item["source"] == "assessed"
    assert item["state"] == "low"
    assert item["fit_score"] == 25


def test_failed_assessment_with_high_fit_score_is_consider():
    corpus = fp.build_evidence_corpus(CARDS)
    item = fp.precheck_profile(
        profile(),
        snapshot(fit_state="failed", fit_failures=2, fit_score=85),
        corpus,
    )
    assert item["state"] == "consider"
    assert item["rank"] == 1


def test_legacy_failed_assessment_without_gaps_falls_back_to_rule_precheck():
    corpus = fp.build_evidence_corpus(CARDS)
    legacy = snapshot(fit_state="failed", fit_failures=0, fit_score=None, match_score=50)
    assert fp.assessment_usable(legacy) is False
    item = fp.precheck_profile(profile(), legacy, corpus)
    assert item["source"] == "rule"
    assert item["basis"] == "rule_evidence_overlap"


def test_passed_assessment_is_usable_without_detail_scores():
    passed = snapshot(fit_state="passed", fit_failures=0, fit_score=None)
    assert fp.assessment_usable(passed) is True
    item = fp.precheck_profile(profile(), passed, fp.build_evidence_corpus(CARDS))
    assert item["state"] == "recommended"


def test_four_tier_report_without_semantic_score_or_advice_falls_back_to_rule():
    """四层报告只说明做了对位层；缺语义评审分/建议时不能当 assessed 依据。"""
    legacy_four_tier = snapshot(fit_state="failed", fit_failures=1, fit_score=None, match_score=80, advice=None)
    assert fp.assessment_usable(legacy_four_tier) is False
    item = fp.precheck_profile(profile(), legacy_four_tier, fp.build_evidence_corpus(CARDS))
    assert item["source"] == "rule"
    assert item["basis"] == "rule_evidence_overlap"
    assert item["fit_score"] is None


def test_assessed_mapping_is_monotonic_in_failure_count():
    corpus = fp.build_evidence_corpus(CARDS)
    fewer = fp.precheck_profile(profile(), snapshot(fit_state="failed", fit_failures=1, fit_score=75), corpus)
    more = fp.precheck_profile(profile(), snapshot(fit_state="failed", fit_failures=4, fit_score=75), corpus)
    assert fewer["state"] == "consider"
    assert more["state"] == "caution"
    assert fewer["rank"] < more["rank"], "缺口更少不能排得更差"


def test_english_generic_words_are_filtered_before_matching():
    """proficient/with 等通用英文词不进入匹配项，否则 “proficient with Java” 会被判未覆盖。"""
    corpus = fp.build_evidence_corpus(
        [{"id": "ec_java", "title": "Java 服务", "stack": ["Java"], "context": "", "actions": [], "results": [], "tags": []}]
    )
    item = fp.precheck_profile(
        profile(keywords=["proficient with Java"], must_have=[], nice_to_have=[]),
        None,
        corpus,
    )
    assert item["matched_requirements"] == 1, item
    assert item["state"] == "promising"


def test_semantic_fit_score_zero_is_valid_and_ranked_low():
    """0 是合法的语义适配分（所有要求 unsupported），不能当成缺失后退回规则预检。"""
    zero = snapshot(fit_state="failed", fit_failures=3, fit_score=0, match_score=90)
    assert fp.assessment_usable(zero) is True
    item = fp.precheck_profile(profile(), zero, fp.build_evidence_corpus(CARDS))
    assert item["source"] == "assessed"
    assert item["fit_score"] == 0
    assert item["state"] == "low"


def test_empty_advice_without_score_is_not_trusted():
    empty = snapshot(fit_state="failed", fit_failures=2, fit_score=None, advice={})
    assert fp.assessment_usable(empty) is False
    item = fp.precheck_profile(profile(), empty, fp.build_evidence_corpus(CARDS))
    assert item["source"] == "rule"
