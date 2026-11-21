"""简历计划契约：把选中的事实装配成"背景—关键工作—成果"章节结构。

计划层只做分组与取舍，不生成新句子；每条 `fact_ids` 都必须能回到 FactIndex。
"""
from tools.engines.generation.fact_index import build_fact_index
from tests.unit.engines.test_fact_index import reviewed_card_results
from tools.engines.generation.fact_selector import SelectionBudget, select_facts
from tools.engines.generation.resume_plan import (
    ProjectBlock,
    ResumePlan,
    WorkBlock,
    build_resume_plan,
)


def card(**over):
    base = {
        "id": "ec_a",
        "title": "门店预约与排队系统",
        "raw_source": "materials:mat_x",
        "context": "门店高峰预约排队场景，需要控制并发与配额",
        "role_scope": "主导方案设计与核心开发",
        "time_range": "2024-01 ~ 2024-06",
        "actions": ["引入 8 个分布式锁键控制并发", "设计 16+ 参数的后台查询"],
        "results": ["核心查询从 2–3 秒降至 300–400 毫秒"],
        "stack": ["Java", "Redis"],
        "artifacts": ["mat_x"],
        "tags": ["预约"],
    }
    base.update(over)
    return reviewed_card_results(base)


def career(**over):
    base = {
        "summary": "后端与平台建设。",
        "work": [
            {
                "id": "w1",
                "company": "公司A",
                "title": "Tech Lead",
                "start": "2021-03",
                "end": "",
                "current": True,
                "scope": "门店数字化平台建设",
                "contributions": ["负责预约平台架构与交付"],
                "evidence_ids": ["ec_a"],
            }
        ],
        "education_visibility": "show",
        "education": [
            {"id": "e1", "school": "某大学", "major": "软件工程", "degree": "本科", "start": "2018-09", "end": "2022-06"}
        ],
        "skills": [{"id": "s1", "category": "后端与存储", "description": "Java 服务与索引治理", "evidence_ids": ["ec_a"]}],
        "extras": [{"id": "x1", "title": "个人项目", "description": "验证闭环", "url": "https://example.com"}],
    }
    base.update(over)
    return base


def plan_for(cards=None, career_data=None, variant="A", weights=None, budget=None):
    from tools.engines.generation.fact_selector import TECHNICAL_DEPTH

    cards = cards or [card()]
    career_data = career_data or career()
    index = build_fact_index(cards, career_data)
    selected = select_facts(index, weights=weights or TECHNICAL_DEPTH, budget=budget or SelectionBudget())
    return build_resume_plan(
        index,
        selected,
        career_data,
        job_context={"target_role": "Java 技术专家", "company": "目标公司", "keywords": ["Java", "Redis"]},
        variant=variant,
    )


def test_plan_contains_all_sections():
    plan = plan_for()

    assert isinstance(plan, ResumePlan)
    assert plan.summary
    assert plan.work and isinstance(plan.work[0], WorkBlock)
    assert plan.projects and isinstance(plan.projects[0], ProjectBlock)
    assert plan.education
    assert plan.extras


def test_work_block_has_scope_and_duties():
    plan = plan_for()

    block = plan.work[0]
    assert block.company == "公司A" and block.period == "2021-03 ~ 至今"
    assert block.scope == "门店数字化平台建设"
    assert block.duties, "工作经历必须有具体职责"
    # 同一事实不在工作经历与项目经历重复呈现：本夹具唯一成果已进入项目块。
    assert block.achievements == ()


def test_project_and_work_do_not_repeat_same_fact():
    plan = plan_for()

    work_texts = {item.text for item in (*plan.work[0].duties,*plan.work[0].achievements)}
    project = plan.projects[0]
    project_texts = {item.text for item in (*project.key_work,*project.outcomes)}
    assert not (work_texts & project_texts), "同一事实不得在工作经历与项目经历重复"
    assert any("毫秒" in item.text for item in project.outcomes)


def test_project_block_uses_three_part_structure():
    plan = plan_for()

    project = plan.projects[0]
    assert project.title == "门店预约与排队系统"
    assert project.background and len(project.background) <= 120
    assert len(project.key_work) >= 1
    assert any("毫秒" in item.text for item in project.outcomes)


def test_internal_plan_represents_untimed_facts_without_granting_resume_eligibility():
    # This is a plan representation, not the public complete-resume builder.
    untimed = card(id="ec_untimed", title="无时间项目", time_range="")
    plan = plan_for(cards=[untimed])

    project = plan.projects[0]
    assert project.title == "无时间项目"
    assert project.period == ""
    assert project.key_work, "无时间的项目仍应呈现事实，只是不显示时间"
    assert plan.untimed_projects == ("ec_untimed",)


def test_every_block_fact_id_resolves_back_to_index():
    cards = [card(), card(id="ec_b", title="第二个项目", actions=["动作 B"], results=["结果 B"])]
    career_data = career()
    career_data["work"][0]["evidence_ids"] = ["ec_a", "ec_b"]
    index = build_fact_index(cards, career_data)
    selected = select_facts(index, budget=SelectionBudget())
    plan = build_resume_plan(index, selected, career_data, job_context={}, variant="A")

    for block in plan.projects:
        for fact_id in block.fact_ids:
            assert index.get(fact_id) is not None
    for block in plan.work:
        for fact_id in block.fact_ids:
            assert index.get(fact_id) is not None


def test_variants_change_project_order_or_selection():
    cards = [
        card(id="ec_tech", title="存储架构改造", actions=["重构查询链路并建立索引边界"], results=["查询 P95 降至 32ms"]),
        card(id="ec_team", title="跨品牌交付治理", actions=["带领 5–8 人团队按品牌线交付", "建立交付机制覆盖 57 个 Feature"], results=["服务 6+ 品牌持续迭代"]),
    ]
    career_data = career()
    career_data["work"][0]["evidence_ids"] = ["ec_tech", "ec_team"]

    from tools.engines.generation.fact_selector import DELIVERY_OWNER, TECHNICAL_DEPTH

    plan_a = plan_for(cards=cards, career_data=career_data, weights=TECHNICAL_DEPTH)
    plan_b = plan_for(cards=cards, career_data=career_data, weights=DELIVERY_OWNER)

    assert [p.card_id for p in plan_a.projects] != [p.card_id for p in plan_b.projects] or (
        [p.fact_ids for p in plan_a.projects] != [p.fact_ids for p in plan_b.projects]
    )


def test_rendered_project_occurrences_not_inferred_from_sibling_or_merged_heading():
    from tools.engines.generation.fact_index import Fact, FactIndex
    from tools.engines.generation.fact_selector import SelectedFacts
    from tools.engines.generation.plan_renderer import render_plan
    from tools.engines.generation.resume_plan import build_resume_plan
    from tools.engines.matching.semantic_review import resume_assessment

    hidden="实现异步提交的断点续跑并恢复尚未落库的指令"
    visible="实现异步提交的断点续跑并导出已落库的日志"
    duplicate="设计服务端回调和排队机制"
    c1="ec_a"
    c2="ec_b"
    # Selected provenance does not include the withheld action; an identical occurrence
    # on the other card is not the publisher of the one surviving deduplication.
    rows=[Fact(c1+":title:0",c1,"title","甲","evidence"),
          Fact(c1+":actions:1",c1,"actions",visible,"evidence"),
          Fact(c1+":actions:2",c1,"actions",duplicate,"evidence"),
          Fact(c2+":actions:0",c2,"actions",duplicate,"evidence"),
          Fact(c2+":results:0",c2,"results","降低事故误报 25%", "evidence")]
    index=FactIndex(tuple(rows))
    plan=build_resume_plan(index,SelectedFacts(projects={"共同项目":tuple(x.fact_id for x in rows)}),
                           {},project_groups={c1:"共同项目",c2:"共同项目"})
    claims=[]
    doc=render_plan(plan,index,profile={},job_context={},claims=claims)
    source={x.fact_id:{"source_id":x.source_id,"field":x.field,"text":x.text} for x in rows}
    source[c1+":actions:0"]={"source_id":c1,"field":"actions","text":hidden}
    targets=[c1+":actions:0",c1+":actions:1",c2+":actions:0",c2+":results:0"]
    requests=[{"id":str(i),"kind":"responsibility","text":"合成职责"} for i,_ in enumerate(targets)]
    decisions=[{"requirement_id":str(i),"status":"supported","reason":"fixture",
                "citations":[{"fact_id":target,"quote":source[target]["text"]}]}
               for i,target in enumerate(targets)]
    result=resume_assessment({"facts":source,"requirements":requests,"assessments":decisions},claims)
    assert [r["resume_status"] for r in result["requirements"]]==["not_present","supported","not_present","supported"]
    assert hidden not in doc and doc.count(duplicate)==1
    emitted={c["fact_id"]:c for c in claims if "fact_id" in c}
    assert emitted[c2+":results:0"]["evidence_id"]==c2
    for c in emitted.values():
        assert c["text"] in doc.splitlines()[c["render_line"]-1]


def test_work_duty_supplement_and_degree_use_their_actual_current_occurrences():
    from tools.engines.generation.fact_index import Fact, FactIndex
    from tools.engines.generation.fact_selector import SelectedFacts
    from tools.engines.generation.plan_renderer import render_plan
    row_id = "w1"
    ordinary = Fact("ec_a:actions:0", "ec_a", "actions", "负责设计服务端回调与告警恢复机制", "evidence", work_id=row_id)
    profile = Fact("personal_profile:career.work.w1.contributions:0", "personal_profile",
                   "career.work.w1.contributions", "承担接口开发", "profile", work_id=row_id)
    degree = Fact("personal_profile:career.education.e1.degree:0", "personal_profile",
                  "career.education.e1.degree", "本科", "profile")
    edu = Fact("personal_profile:career.education.e1.school:0", "personal_profile",
               "career.education.e1.school", "示例大学", "profile")
    summary = Fact("personal_profile:career.summary:0", "personal_profile", "career.summary", "后端服务开发。", "profile")
    index = FactIndex((ordinary, profile, degree, edu, summary))
    data = {"summary":"后端服务开发。","work":[{"id":row_id,"company":"示例公司","title":"工程师"}],
            "education":[{"id":"e1","school":"示例大学","degree":"本科"}]}
    p = build_resume_plan(index, SelectedFacts(work={row_id:(ordinary.fact_id,)}), data)
    claims=[]
    text = render_plan(p, index, profile={}, job_context={}, claims=claims)
    c = {r["fact_id"]:r for r in claims if "fact_id" in r}
    assert c[ordinary.fact_id]["source_kind"] == "evidence" and c[ordinary.fact_id]["evidence_id"] == "ec_a"
    assert c[profile.fact_id]["source_kind"] == c[degree.fact_id]["source_kind"] == "personal_profile"
    assert c[summary.fact_id]["text"] == summary.text
    for fact_id in c:
        assert c[fact_id]["text"] in text.splitlines()[c[fact_id]["render_line"]-1]


def _targeted_priority_fixture(mode):
    skill_text = "设计并实施异步对账回放"
    card_text = "实现预约接口的幂等重试"
    career_data = career(skills=[
        {"id": "other", "category": "通用", "description": "Java 技术文档"},
        {"id": "echo", "category": "同文异源", "description": skill_text},
        {"id": "direct", "category": "定向", "description": skill_text},
    ])
    cards = [card(actions=["设计服务回归的监控与异常补偿流程", card_text, "独自实现同事页面"],
                  personal_claim_exclusions=("ec_a:actions:2",), source_sha256="a"*64)]
    refs = {"skill": ("personal_profile:career.skills.direct.description:0",
                      "personal_profile", "career.skills.direct.description", skill_text),
            "project": ("ec_a:actions:1", "ec_a", "actions", card_text),
            "excluded": ("ec_a:actions:2", "ec_a", "actions", "独自实现同事页面")}
    targets = {"skill": ["skill"], "project": ["project"], "mixed": ["project", "skill"],
               "partial": ["project"], "stale": ["skill"], "drift": ["project"], "excluded": ["excluded"]}[mode]
    report = {"advisory_scope": False, "inputs": {"personal_profile": {"sha256": "b"*64},
                                                      "ec_a": {"sha256": ("c" if mode == "drift" else "a")*64}},
              "requirements": [], "facts": {}, "assessments": []}
    for n, target in enumerate(targets):
        fid, owner, field, value = refs[target]
        rid = f"d{n+1}"
        report["requirements"].append({"id": rid, "kind": "responsibility", "text": f"职责 {n+1}"})
        report["facts"][fid] = {"source_id": owner, "field": field,
                               "text": value if mode != "stale" else "过期职业字段原文"}
        citation = {"fact_id": fid, "quote": value}
        report["assessments"].append({
            "requirement_id": rid, "status": "partial" if mode == "partial" else "supported",
            "checks": [{"status": "supported", "citations": [citation]}],
        })
    index = build_fact_index(cards, career_data, report)
    selected = select_facts(index)
    return index, selected, career_data


def test_exact_skill_precedes_keyword_and_same_text_other_source():
    idx, selected, data = _targeted_priority_fixture("skill")
    plan = build_resume_plan(idx, selected, data, job_context={"keywords": ["Java"]})
    assert plan.capabilities[0].category == "定向"


def test_optional_capabilities_do_not_move_without_relative_support():
    from tools.engines.generation.plan_renderer import render_plan
    for case in ("skill", "project", "mixed", "partial", "stale", "drift", "excluded"):
        idx, selected, data = _targeted_priority_fixture(case)
        if case in ("partial", "stale", "drift", "excluded"):
            assert not idx.first_screen_priority
        plan = build_resume_plan(idx, selected, data, job_context={"keywords": ["Java"]})
        claims = []
        md = render_plan(plan, idx, profile={}, job_context={}, claims=claims, version="A")
        assert md.index("## 工作经历") < md.index("## 项目经历")
        assert md.index("## 核心能力") < md.index("## 工作经历")
        if case in ("skill", "mixed"):
            assert md.index("定向：") < md.index("同文异源：")
        elif case != "project":
            assert md.index("通用：") < md.index("定向：")
        assert "独自实现同事页面" not in md
        for row in claims:
            if row.get("fact_id"):
                assert row["text"] in md.splitlines()[row["render_line"] - 1]


def test_exact_supported_facts_reorder_inside_selected_existing_work_and_project():
    from dataclasses import replace
    idx, selected, data = _targeted_priority_fixture("project")
    # Keep the selected occurrence set and a deliberately earlier distractor,
    # as can happen with preferred-card/current weighted selection.
    ids = tuple(f.fact_id for f in idx.by_card("ec_a"))
    chosen = replace(selected, projects={"ec_a": ids})
    plan = build_resume_plan(idx, chosen, data)
    assert [f.fact_id for f in plan.projects[0].key_work] == ["ec_a:actions:1", "ec_a:actions:0"]

    data = dict(data, work=[dict(data["work"][0], contributions=["维护普通文档", "主持岗位所需质量评审"])])
    exact = "personal_profile:career.work.w1.contributions:1"
    fact = {"source_id": "personal_profile", "field": "career.work.w1.contributions", "text": "主持岗位所需质量评审"}
    report = {"advisory_scope": False, "inputs": {"personal_profile": {"sha256": "b"*64}}, "facts": {exact: fact},
              "requirements": [{"id": "d1", "kind": "responsibility", "text": "主持评审"}],
              "assessments": [{"requirement_id": "d1", "status": "supported",
                              "citations": [{"fact_id": exact, "quote": fact["text"]}]}]}
    idx = build_fact_index([card()], data, report)
    plan = build_resume_plan(idx, select_facts(idx), data)
    assert [f.fact_id for f in plan.work[0].duties][:2] == [exact, exact[:-1] + "0"]
