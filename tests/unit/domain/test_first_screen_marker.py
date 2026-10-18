"""首屏切分标记：模板写入、评估器消费、渲染层忽略。"""
from __future__ import annotations

from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.evaluation import tiered_evaluator as te
from tools.infra.export.resume_html import parse_resume_markdown, render_resume_html
from tools.run_generation import build_template_resume


CARD = {
    "id": "ec-1",
    "title": "交易服务重构",
    "time_range": "2024-01 ~ 2024-06",
    "role_scope": "模块负责人",
    "context": "峰值请求延迟较高",
    "results": ["请求延迟降低 20%"],
    "actions": ["使用 Java 重构交易服务"],
    "stack": ["Java"],
}


def build_resume():
    claims: list[dict[str, str]] = []
    content = build_template_resume(
        "A",
        "mr-test",
        85,
        "2026-10-18 10:00:00",
        [CARD],
        personal_profile={
            "name": "测试候选人",
            "phone": "13800000000",
            "email": "candidate@example.com",
            "city": "上海",
            "current_position": "后端工程师",
            "career": {
                "summary": "负责交易平台交付。",
                "work": [],
                "education": [],
                "education_visibility": "omit",
                "skills": [],
                "extras": [],
            },
        },
        job_context={"target_role": "Java技术专家", "company": "目标公司"},
        claims=claims,
    )
    return content, claims


def test_template_writes_exactly_one_first_screen_marker():
    content, _claims = build_resume()
    assert content.count(FIRST_SCREEN_MARKER) == 1
    first, rest = te.split_first_screen(content)
    assert "职业概述" in first
    assert "项目经历" in first
    # D3：第一条经历（含 JD 相关 bullet）必须在首屏内，标记后才能进入其余经历。
    assert "交易服务重构" in first
    assert "请求延迟降低 20%" not in rest


def test_rendered_html_and_parsed_resume_ignore_marker():
    content, _claims = build_resume()
    html = render_resume_html(content)
    assert FIRST_SCREEN_MARKER not in html
    assert "first-screen-end" not in html
    parsed = parse_resume_markdown(content)
    assert "<" not in parsed["name"]
    assert all("first-screen-end" not in str(section) for section in parsed.get("extra_sections", []))
