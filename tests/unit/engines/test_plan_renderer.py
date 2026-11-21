"""计划渲染契约：章节顺序、逐条 claim 可追溯、无时间项目不伪造时间。"""
import pytest
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.generation.fact_index import build_fact_index
from tools.engines.generation.fact_selector import SelectionBudget, select_facts
from tools.engines.generation.plan_renderer import render_plan
from tools.engines.generation.resume_plan import build_resume_plan


def card(**over):
    base = {
        "id": "ec_a",
        "title": "门店预约与排队系统",
        "raw_source": "materials:mat_x",
        "context": "门店高峰预约排队场景",
        "role_scope": "主导方案设计与核心开发",
        "time_range": "2024-01 ~ 2024-06",
        "actions": ["引入 8 个分布式锁键控制并发"],
        "results": ["核心查询从 2–3 秒降至 300–400 毫秒"],
        "stack": ["Java", "mongodb"],
        "artifacts": ["mat_x"],
        "tags": [],
    }
    base.update(over)
    return base


def career():
    return {
        "summary": "后端与平台建设，负责门店数字化平台。",
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
        "education": [{"id": "e1", "school": "某大学", "major": "软件工程", "degree": "本科", "start": "2018-09", "end": "2022-06"}],
        "skills": [{"id": "s1", "category": "后端与存储", "description": "Java 服务与索引治理", "evidence_ids": ["ec_a"]}],
        "extras": [{"id": "x1", "title": "个人项目", "description": "验证闭环", "url": "https://example.com"}],
    }


def render(cards=None, career_data=None):
    cards = cards or [card()]
    career_data = career_data or career()
    index = build_fact_index(cards, career_data)
    selected = select_facts(index, budget=SelectionBudget())
    plan = build_resume_plan(index, selected, career_data, job_context={"target_role": "Java 技术专家", "company": "目标公司"})
    claims: list[dict] = []
    text = render_plan(
        plan,
        index,
        profile={"name": "候选人", "phone": "13800000000", "email": "a@b.com", "city": "上海", "current_position": "Tech Lead"},
        job_context={"target_role": "Java 技术专家", "company": "目标公司"},
        claims=claims,
    )
    return text, claims


def test_sections_and_order():
    text, _claims = render()

    sections = ["职业概述", "核心能力", "工作经历", "项目经历", "核心技能", "教育经历", "补充成果"]
    assert all(f"## {name}" in text for name in sections)
    positions = [text.index(f"## {name}") for name in sections]
    assert positions == sorted(positions)
    assert FIRST_SCREEN_MARKER in text


def test_work_block_renders_scope_duties_and_achievements():
    text, _claims = render()

    assert "### 公司A · Tech Lead（2021-03 ~ 至今）" in text
    assert "场景：门店数字化平台建设" in text
    assert "职责：负责预约平台架构与交付" in text
    assert "- 核心查询从 2–3 秒降至 300–400 毫秒" in text


def test_project_block_renders_background_work_and_outcomes():
    text, _claims = render()

    assert "### 门店预约与排队系统（2024-01 ~ 2024-06）" in text
    assert "角色：主导方案设计与核心开发" in text
    assert "背景：门店高峰预约排队场景" in text
    assert "- 引入 8 个分布式锁键控制并发" in text
    assert "- 核心查询从 2–3 秒降至 300–400 毫秒" in text


def test_internal_plan_can_render_untimed_facts_without_inventing_dates():
    # The complete-resume builder rejects this card before selection; internal excerpts can represent it.
    text, _claims = render(cards=[card(id="ec_untimed", title="无时间项目", time_range="")])

    assert "### 无时间项目" in text
    assert "### 无时间项目（" not in text
    assert "引入 8 个分布式锁键控制并发" in text


def test_every_claim_text_appears_in_body():
    text, claims = render()

    assert claims
    for claim in claims:
        assert claim["text"] in text, claim


@pytest.mark.parametrize(("excluded_field", "rendered_field", "counts_quant"), [
    ("results", "actions", False),
    ("actions", "results", True),
])
def test_same_text_action_and_result_are_scored_by_rendered_fact(excluded_field, rendered_field, counts_quant):
    # 从现有字段级排除 → FactIndex → 正式 Markdown/trace → R3.2，验证无卡级借证。
    from tools.engines.evaluation.tiered_evaluator import evaluate_strong, load_quality_config

    sentence = "P95 从 200 ms 降至 120 ms"
    item = card(actions=[sentence], results=[sentence],
                personal_claim_exclusions=[f"ec_a:{excluded_field}:0"])
    text, claims = render(cards=[item])
    occurrences = [claim for claim in claims if claim.get("text") == sentence
                   and claim.get("field") in {"actions", "results"}]
    assert len(occurrences) == 1
    assert occurrences[0]["fact_id"] == f"ec_a:{rendered_field}:0"
    assert occurrences[0]["render_line"] > 0
    assert text.splitlines()[occurrences[0]["render_line"] - 1] == f"- {sentence}"

    quality = evaluate_strong(resume=text, cards={"ec_a": item},
        trace={"occurrence_lineage_version": 1, "claims": claims}, config=load_quality_config())
    assert (quality.metrics["quant_first_screen"] > 0) is counts_quant
    assert (quality.metrics["quant_total"] > 0) is counts_quant


def test_internal_paths_are_filtered_before_render():
    # 内部路径在事实闸门阶段被拒绝（url_path），不会进入正文；
    # render_plan 的 _INTERNAL_RE 仍作为最后一道防御。
    text, claims = render(cards=[card(results=["参见 /Users/example/private.txt 中的压测报告"])])

    assert "/Users/" not in text
    assert all("/Users/" not in claim["text"] for claim in claims)
