"""事实级选材契约：精确岗位支持、稳定无语义输入与共同篇幅预算。"""
from tools.engines.generation.fact_index import Fact, FactIndex, build_fact_index
from tests.unit.engines.test_fact_index import reviewed_card_results
from tools.engines.generation.fact_selector import SelectionBudget, SelectedFacts, select_facts


def card(cid, title, time_range="2024-01 ~ 2024-06", actions=(), results=(), role_scope="主导方案设计"):
    return reviewed_card_results({
        "id": cid,
        "title": title,
        "raw_source": "materials:mat_x",
        "context": f"{title}的业务背景",
        "role_scope": role_scope,
        "time_range": time_range,
        "actions": list(actions),
        "results": list(results),
        "stack": ["Java"],
        "artifacts": ["mat_x"],
        "tags": [],
    })


def career(cards_by_work):
    work = [
        {
            "id": work_id,
            "company": f"公司{work_id}",
            "title": "Tech Lead",
            "start": "2021-03",
            "end": "",
            "current": True,
            "scope": f"{work_id} 的业务范围",
            "contributions": [f"{work_id} 的概括职责"],
            "evidence_ids": list(card_ids),
        }
        for work_id, card_ids in cards_by_work.items()
    ]
    return {
        "summary": "后端与平台建设。",
        "work": work,
        "education_visibility": "omit",
        "education": [],
        "skills": [],
        "extras": [],
    }


def semantic(citations):
    """Explicit independent support tuples: (parent ID, status, exact Fact ID)."""
    return {
        "facts": {},
        "requirements": [{"id": rid, "text": "合成岗位要求 " + rid}
                         for rid in dict.fromkeys(rid for rid, _status, _fid in citations)],
        "assessments": [
            {"requirement_id": rid, "status": status, "citations": [{"fact_id": fid}]}
            for rid, status, fid in citations
        ],
    }


def test_prefers_requirement_cited_facts_over_mere_keyword_density():
    rich = card(
        "ec_rich", "关键词很多的普通项目",
        actions=["使用 Java MySQL Redis Spring Boot 开发系统"], results=["系统上线"],
    )
    cited = card(
        "ec_cited", "MongoDB 存储改造与容量治理",
        actions=["将核心存储从 MySQL/Redis 迁移至 MongoDB"], results=["五类查询 P95 不超过 32ms"],
    )
    report = semantic([("r1", "supported", "ec_cited:results:0")])
    index = build_fact_index(
        [rich, cited], career({"w1": ["ec_rich", "ec_cited"]}), report,
    )
    chosen = select_facts(index, semantic_report=report,
                         budget=SelectionBudget(max_total_facts=12))

    assert next(iter(chosen.projects)) == "ec_cited"
    assert "ec_cited:results:0" in chosen.projects["ec_cited"]


def test_each_work_block_keeps_minimum_facts():
    index = build_fact_index(
        [
            card("ec_a", "项目 A", actions=["实现回执校验", "建立恢复机制"], results=["通过独立验收"]),
            card("ec_b", "项目 B", actions=["建立接口核对"], results=["完成联调验收"]),
        ],
        career({"w1": ["ec_a"], "w2": ["ec_b"]}),
    )
    chosen = select_facts(index, budget=SelectionBudget(min_work_facts=2, max_total_facts=40))

    assert len(chosen.work["w1"]) >= 2
    assert len(chosen.work["w2"]) >= 2
    assert all(fid.startswith(("ec_a", "ec_b", "personal_profile")) for ids in chosen.work.values() for fid in ids)


def test_project_fact_quota_and_project_cap():
    cards = [
        card(f"ec_{i}", f"项目{i}", actions=[f"实现第{i}项外部业务回执核对", f"建立第{i}项故障状态恢复机制", f"完成第{i}项合作接口验收联调"],
             results=[f"第{i}项服务通过独立验收"])
        for i in range(6)
    ]
    index = build_fact_index(cards, career({"w1": [c["id"] for c in cards]}))
    chosen = select_facts(
        index,
        budget=SelectionBudget(max_project_facts=3, max_total_facts=100),
        max_projects=3,
    )

    assert 1 <= len(chosen.projects) <= 3
    for fact_ids in chosen.projects.values():
        assert 2 <= len(fact_ids) <= 3


def test_total_budget_is_respected():
    cards = [
        card(f"ec_{i}", f"项目{i}", actions=[f"实现第{i}项目的第{j}项接口核对" for j in range(5)],
             results=[f"第{i}项目的第{j}项流程通过独立验收" for j in range(3)])
        for i in range(5)
    ]
    index = build_fact_index(cards, career({"w1": [c["id"] for c in cards]}))
    chosen = select_facts(index, budget=SelectionBudget(max_total_facts=10))

    assert 0 < chosen.total <= 10


def test_without_semantic_report_projects_follow_explicit_input_order():
    cards = [
        card("ec_first", "接口验收", actions=["完成合作接口的独立核对"], results=["联调通过验收"],
             role_scope="负责接口对接"),
        card("ec_later", "架构性能治理", actions=["独立主导分布式架构与容量性能治理"],
             results=["服务 100 万个用户"], role_scope="独立负责总体架构"),
    ]
    for ordered in (cards, cards[::-1]):
        chosen = select_facts(build_fact_index(ordered), max_projects=1)
        assert list(chosen.projects) == [ordered[0]["id"]]


def test_records_excluded_facts_with_reason():
    index = build_fact_index(
        [card("ec_a", "项目 A", actions=["实现回执校验", "建立恢复机制"], results=["通过独立验收"])],
        career({"w1": ["ec_a"]}),
    )
    chosen = select_facts(index, budget=SelectionBudget(max_total_facts=3))

    assert isinstance(chosen, SelectedFacts)
    assert chosen.excluded
    assert all(reason for reason in chosen.excluded.values())


def test_empty_index_returns_empty_selection():
    chosen = select_facts(build_fact_index([], {}))
    assert chosen.total == 0 and chosen.projects == {} and chosen.work == {}


def test_uncited_words_and_scale_do_not_override_stable_fact_order():
    facts = (
        Fact("ec_a:actions:0", "ec_a", "actions", "完成合作接口的独立核对", "evidence", order=0),
        Fact("ec_a:actions:1", "ec_a", "actions", "主导 100 个系统的架构性能存储分布式治理", "evidence", order=1),
    )
    index = FactIndex(facts, {fact.fact_id: fact for fact in facts})
    chosen = select_facts(index, budget=SelectionBudget(
        min_work_facts=0, max_project_facts=1, max_total_facts=1,
    ))
    assert chosen.projects["ec_a"] == ("ec_a:actions:0",)
    assert all(fact.requirement_ids == () and fact.support_weight == 0 for fact in facts)


def test_audit_only_and_candidate_limited_citations_do_not_count_as_positive_coverage():
    cards = [
        card("ec_a", "审计背景项目", actions=["完成隔离环境中的合作接口联调"], results=["通过隔离环境验收"]),
        card("ec_b", "个人核对项目", actions=["完成外部结算回执的独立核对"], results=["通过独立核对验收"]),
    ]
    report = semantic([
        ("r1", "conflict", "ec_a:results:0"),
        ("r2", "supported", "ec_a:actions:0"),
        ("r3", "partial", "ec_b:actions:0"),
    ])
    report["assessments"][1]["citations"][0]["candidate_support"] = False
    index = build_fact_index(cards, {}, report)
    chosen = select_facts(index, semantic_report=report, max_projects=1)

    assert list(chosen.projects) == ["ec_b"]
    assert "ec_b:actions:0" in chosen.projects["ec_b"]
    assert index.get("ec_a:results:0").support_weight == 0
    assert index.get("ec_a:actions:0").support_weight == 0


def test_global_budget_preserves_exact_coverage_through_actual_plan_and_claims():
    from tools.engines.generation.resume_plan import build_resume_plan
    from tools.engines.generation.plan_renderer import render_plan
    from tools.engines.matching.semantic_review import resume_assessment

    cards = [
        card("ec_a", "回执核对", actions=["整理接口交付文档", "实现业务回执的独立核对"], results=["核对验收完成"]),
        card("ec_b", "恢复验证", actions=["实现恢复边界的隔离验证"], results=["恢复验收完成"]),
    ]
    report = semantic([
        ("r1", "supported", "ec_a:actions:1"),
        ("r2", "partial", "ec_b:actions:0"),
    ])
    index = build_fact_index(cards, {}, report)
    report["facts"] = {fact.fact_id: {"source_id": fact.source_id, "field": fact.field, "text": fact.text}
                       for fact in index.facts}
    selected = select_facts(index, semantic_report=report, budget=SelectionBudget(
        min_work_facts=0, max_project_facts=3, max_total_facts=2,
    ))
    expected = {"ec_a:actions:1", "ec_b:actions:0"}
    assert selected.total == 2
    assert {fid for fact_ids in selected.projects.values() for fid in fact_ids} == expected
    plan = build_resume_plan(index, selected, {})
    claims = []
    markdown = render_plan(plan, index, profile={}, job_context={}, claims=claims)
    actual = [claim for claim in claims if claim.get("fact_id") in expected]
    assert {claim["fact_id"] for claim in actual} == expected
    assert all(claim["text"] in markdown.splitlines()[claim["render_line"] - 1] for claim in actual)
    assessment = resume_assessment(report, claims, occurrence_coverage_known=True)
    assert [row["resume_status"] for row in assessment["requirements"]] == ["supported", "partial"]

def test_first_screen_display_priority_does_not_change_selected_fact_set():
    from dataclasses import replace
    from tools.engines.generation.resume_plan import build_resume_plan
    from tools.engines.generation.plan_renderer import render_plan

    first, later = "ec_screen:actions:0", "ec_screen:actions:1"
    report = semantic([
        ("r1", "supported", first),
        ("r2", "supported", later),
    ])
    index = build_fact_index([
        card("ec_screen", "已确认接口项目", actions=[
            "实现业务回执的独立核对", "建立故障恢复的隔离验证",
        ]),
    ], {}, report)
    index = replace(index, first_screen_priority={later: 0})

    limited = select_facts(index, semantic_report=report, budget=SelectionBudget(
        min_work_facts=0, max_project_facts=1, max_total_facts=1,
    ))
    assert limited.projects["ec_screen"] == (first,)
    assert limited.total == 1

    expanded = select_facts(index, semantic_report=report, budget=SelectionBudget(
        min_work_facts=0, max_project_facts=2, max_total_facts=2,
    ))
    assert expanded.projects["ec_screen"] == (first, later)
    plan = build_resume_plan(index, expanded, {})
    claims = []
    markdown = render_plan(plan, index, profile={}, job_context={}, claims=claims)
    displayed = [claim for claim in claims if claim.get("field") == "actions"]
    assert [claim["fact_id"] for claim in displayed] == [later, first]
    assert all(claim["text"] in markdown.splitlines()[claim["render_line"] - 1]
               for claim in displayed)
