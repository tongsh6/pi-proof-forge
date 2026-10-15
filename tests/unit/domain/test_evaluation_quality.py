"""P0-026：评分依据必须与显示的质量指标一致。"""
import hashlib
import json

import pytest

from tools import run_evaluation
from tools.domain.models import JobProfile, ResumeOutput
from tools.engines.evaluation.rule_evaluator import RuleEvaluationEngine


def evaluate(text, must_have=(), keywords=(), **kwargs):
    return run_evaluation.evaluate_rule(text, list(must_have), list(keywords), "now", "resume.md", "job.yaml", **kwargs)


def test_requirements_are_not_in_keyword_denominator():
    result = evaluate("- 使用 Java 和 Redis 开发接口", ["熟练使用 Java，具备五年开发经验"], ["Java", "Redis", "java", ""])
    coverage = result["keyword_coverage"]
    assert coverage == {"matched": ["Java", "Redis"], "missing": [], "ratio": 1.0}
    review = result["must_have_review"]
    assert review == [{"requirement": "熟练使用 Java，具备五年开发经验", "status": "needs_review", "matched_keywords": ["Java"], "missing_keywords": []}]
    assert "岗位关键词覆盖率: 100% (2/2)" in result["markdown"]
    assert "五年开发经验" in result["markdown"]
    assert any("硬性条件" in task for task in result["gap_tasks"])


@pytest.mark.parametrize("text,expected", [
    ("- 使用 JavaScript、Django 和 GitHub", []),
    ("- 使用Java、Go和Git开发", ["Java", "Go", "Git"]),
])
def test_technical_keywords_have_boundaries(text, expected):
    assert evaluate(text, keywords=["Java", "Go", "Git"])["keyword_coverage"]["matched"] == expected


def test_target_role_does_not_count_as_candidate_experience():
    result = evaluate("求职意向：Java开发专家\n- 使用 Python 开发接口", keywords=["Java", "Python"])
    assert result["keyword_coverage"]["matched"] == ["Python"]


@pytest.mark.parametrize("heading", ["**求职意向：**Java专家", "## 求职意向\nJava工程师\n### 目标说明\nJava"])
def test_markdown_target_role_does_not_count(heading):
    result = evaluate(heading + "\n## 工作经历\n- 使用 Python 开发接口", keywords=["Java", "Python"])
    assert result["keyword_coverage"]["matched"] == ["Python"]


def test_missing_keywords_is_not_full_coverage():
    result = evaluate("- 开发接口", ["本科及以上学历"])
    assert result["keyword_coverage"]["ratio"] is None
    assert "未配置" in result["markdown"]
    assert result["must_have_review"][0]["status"] == "needs_review"


def test_numbers_and_keywords_are_not_citations():
    result = evaluate("- Java 延迟降低 30%", keywords=["Java"])
    assert result["traceability"]["status"] == "unverified"
    assert result["traceability"]["verified_bullets"] == 0
    assert "证据引用检查: 0% (0/1)" in result["markdown"]


def test_activity_dates_and_software_versions_are_not_quantified_outcomes():
    text='- 发布双11投屏需求项目\n- Java 21、Spring Boot 3.4、Vue 3 工程\n- 2026年完成设计\n- 查询P95由34秒降至32ms\n- 覆盖8个品牌、95个模块'
    result=evaluate(text)
    assert result['quantification']['quantified_bullets']==2
    assert result['quantification']['total_bullets']==5
    assert '控制篇幅到 1 页' not in result['markdown']


def test_trace_requires_full_bullet_not_a_supported_substring():
    claims = [
        {"text": "接口开发", "source_kind": "evidence", "evidence_id": "e1", "field": "actions"},
        {"text": "架构", "source_kind": "personal_profile", "field": "career.skills.s.category"},
        {"text": "服务拆分", "source_kind": "personal_profile", "field": "career.skills.s.description"},
        {"text": "Java负责人", "source_kind": "job_profile", "field": "target_role"},
    ]
    result = evaluate("- 接口开发\n- 接口开发，业绩提升 90%\n- 架构：服务拆分\n- Java负责人", verified_claims=claims)
    assert result["traceability"]["verified_bullets"] == 2
    assert [row["verified"] for row in result["traceability"]["bullets"]] == [True, False, True, False]


def test_agent_keyword_coverage_uses_same_boundaries():
    profile = JobProfile("p", "后端", ("Java", "java", "Go", ""), "senior")
    resume = ResumeOutput("a", "p", "- 使用 JavaScript 和 Django", "markdown")
    assert RuleEvaluationEngine().evaluate(resume, profile).dimension_scores["coverage"] == 0.0


def test_plus_separates_stack_names_without_confusing_c_languages():
    result = evaluate("- Java+Spring Boot+MySQL，HTTP+json，C++ 和 C#", keywords=["Java", "Spring Boot", "MySQL", "HTTP", "json", "C", "C++", "C#"])
    assert result["keyword_coverage"]["matched"] == ["Java", "Spring Boot", "MySQL", "HTTP", "json", "C++", "C#"]


def test_agent_empty_keywords_keep_neutral_score():
    profile = JobProfile("p", "后端", ("",), "senior")
    resume = ResumeOutput("a", "p", "- 接口开发", "markdown")
    assert RuleEvaluationEngine().evaluate(resume, profile).dimension_scores["coverage"] == 0.5


def test_cli_validates_trace_inputs_before_awarding_citations(tmp_path, monkeypatch):
    source = tmp_path / "e1.yaml"
    source.write_text('results:\n  - "接口延迟降低 30%"\n')
    resume = tmp_path / "resume.md"
    resume.write_text("- 接口延迟降低 30%\n")
    trace = {
        "schema_version": 1,
        "resume_sha256": hashlib.sha256(resume.read_bytes()).hexdigest(),
        "evidence_card_ids": ["e1"],
        "inputs": {"e1": {"path": str(source), "exists": True, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}},
        "claims": [{"text": "接口延迟降低 30%", "source_kind": "evidence", "evidence_id": "e1", "field": "results"}],
    }
    resume.with_suffix(".trace.json").write_text(json.dumps(trace))
    output = tmp_path / "scorecard.md"
    monkeypatch.setattr("sys.argv", ["evaluate", "--input", str(resume), "--output", str(output)])
    assert run_evaluation._legacy_main() == 0
    result = json.loads(output.with_suffix(".json").read_text())
    assert result["traceability"]["verified_bullets"] == 1
    assert "证据引用检查: 100% (1/1)" in output.read_text()
    source.write_text('results:\n  - "只完成接口开发"\n')
    assert run_evaluation._legacy_main() == 0
    result = json.loads(output.with_suffix(".json").read_text())
    assert result["traceability"]["status"] == "unverified"
    assert result["traceability"]["verified_bullets"] == 0
