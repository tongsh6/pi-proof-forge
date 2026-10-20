"""P0-026：评分依据必须与显示的质量指标一致。"""
import hashlib
import json
from pathlib import Path

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


def _quality_fixture(tmp_path):
    card = tmp_path / "ec-1.yaml"
    card.write_text(
        'id: "ec-1"\ntitle: "交易服务重构"\ntime_range: "2022-03 ~ 2023-09"\n'
        'role_scope: "模块负责人"\ncontext: "峰值延迟高"\n'
        'results:\n  - "请求延迟降低 20%"\nstack:\n  - "Java"\n'
        'artifacts:\n  - "报告.pdf"\n',
        encoding="utf-8",
    )
    profile = tmp_path / "personal_profile.yaml"
    profile.write_text('name: "测试候选人"\nphone: "13800000000"\n', encoding="utf-8")
    job = tmp_path / "job.yaml"
    job.write_text(
        'target_role: "平台负责人"\ncompany: "示例科技"\neducation: "本科"\nwork_years: "1-3年"\n'
        'keywords:\n  - "Java"\nmust_have:\n  - "本科及以上学历"\n',
        encoding="utf-8",
    )
    resume = tmp_path / "resume_mr-test_A.md"
    resume.write_text(
        "# 测试候选人\n13800000000 | candidate@example.com | 上海\n当前定位：平台负责人\n\n"
        "## 职业概述\n负责平台架构与交付。\n\n<!-- first-screen-end -->\n\n"
        "## 核心技能\nJava\n\n## 项目经历\n### 交易服务重构（2022-03 ~ 2023-09）\n"
        "角色：模块负责人\n- 请求延迟降低 20%\n\n"
        "## 工作经历\n### 示例科技 · 平台负责人（2021-03 ~ 至今）\n\n"
        "## 教育经历\n### 示例大学（2010-09 ~ 2014-06）\n软件工程 · 本科\n",
        encoding="utf-8",
    )
    claims = [
        {"text": "测试候选人", "source_kind": "personal_profile", "field": "name", "evidence_id": ""},
        {"text": "负责平台架构与交付。", "source_kind": "personal_profile", "field": "career.summary", "evidence_id": ""},
        {"text": "交易服务重构", "source_kind": "evidence", "field": "title", "evidence_id": "ec-1"},
        {"text": "2022-03 ~ 2023-09", "source_kind": "evidence", "field": "time_range", "evidence_id": "ec-1"},
        {"text": "模块负责人", "source_kind": "evidence", "field": "role_scope", "evidence_id": "ec-1"},
        {"text": "请求延迟降低 20%", "source_kind": "evidence", "field": "results", "evidence_id": "ec-1"},
        {"text": "示例科技", "source_kind": "personal_profile", "field": "career.work.w1.company", "evidence_id": ""},
        {"text": "平台负责人", "source_kind": "personal_profile", "field": "career.work.w1.title", "evidence_id": ""},
    ]
    trace = {
        "schema_version": 1,
        "resume_sha256": hashlib.sha256(resume.read_bytes()).hexdigest(),
        "evidence_card_ids": ["ec-1"],
        "inputs": {
            "personal_profile": {"path": str(profile), "exists": True, "sha256": ""},
            "job_profile": {"path": str(job), "exists": True, "sha256": ""},
            "ec-1": {"path": str(card), "exists": True, "sha256": ""},
        },
        "claims": claims,
    }
    resume.with_suffix(".trace.json").write_text(json.dumps(trace))
    return resume, job, tmp_path / "scorecard.md"


def test_cli_writes_four_tier_quality_report_and_legacy_scores(tmp_path, monkeypatch):
    resume, job, output = _quality_fixture(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate", "--input", str(resume), "--output", str(output), "--job-profile", str(job)],
    )
    assert run_evaluation._legacy_main() == 0
    result = json.loads(output.with_suffix(".json").read_text())
    report = result["quality_report"]
    assert set(report["tiers"]) == {"eligible", "fit", "strong", "distinct"}
    assert report["thresholds_version"] == 1
    assert report["llm_pending"]
    assert report["auto_pass"] is False
    assert result["legacy_scores"]["rule_total"] == result["total_score"]
    assert result["legacy_scores"]["llm_expression"] == result["expression_score"]
    markdown = output.read_text()
    assert "## 质量报告（四层，规则部分）" in markdown
    assert "LLM 判项未完成或覆盖不足" in markdown
    # 评估阶段还没有 PDF，R1.5 必须显式记录未校验，不能假装通过。
    rules = [failure["rule"] for failure in report["tiers"]["eligible"]["failures"]]
    assert "R1.5" in rules


class _FakeJudgeClient:
    chat_completions_url = "http://fake/v1/chat/completions"

    def __init__(self, content):
        self.calls = 0
        self.content = content

    def post_json(self, url, payload):
        self.calls += 1
        self.last_prompt = payload["messages"][-1]["content"]
        return {"choices": [{"message": {"content": self.content}}]}

    @staticmethod
    def extract_content(response):
        return response["choices"][0]["message"]["content"]


def _judge_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("PPF_QUALITY_JUDGE_CACHE_DIR", str(tmp_path / "judge-cache"))
    monkeypatch.setattr(run_evaluation, "_load_quality_cards", lambda trace: {"ec_1": {"title": "统一平台"}})
    resume = (
        "# 张三\n13800000000 | a@b.com | 上海\n当前定位：平台负责人\n\n"
        "## 职业概述\n负责平台架构与交付。\n\n<!-- first-screen-end -->\n\n"
        "## 项目经历\n### 统一平台（2022-03 ~ 2023-09）\n- 负责完成平台抽象\n"
    )
    semantic = {
        "mode": "semantic",
        "requirements": [
            {"requirement_id": "d1", "kind": "responsibility", "text": "负责核心平台交付"},
        ],
    }
    payload = {
        "r1_4": [{"bullet": 1, "supported": True, "citations": ["ec_1"], "reason": "卡中明确本人负责"}],
        "r2_1": [{"jd_item_id": "d1", "status": "supported", "bullet_ref": "bullet#1",
                  "citations": ["ec_1"], "reason": ""}],
        "r3_1": [{"bullet": 1, "scene": True, "action": True, "result": True,
                  "citations": ["ec_1"], "reason": ""}],
        "r3_5": {"summary_lines": 2, "role_scale_match": True, "generic_adjectives": [],
                 "citations": ["bullet#1"], "reason": ""},
        "r4_1": [{"bullet": 1, "jd_item_id": "d1", "exceeds": ["scale"], "level": "L1",
                  "citations": ["ec_1"], "reason": "规模"}],
    }
    return resume, semantic, json.dumps(payload, ensure_ascii=False)


def test_quality_judge_cache_hit_avoids_second_model_call(tmp_path, monkeypatch):
    resume, semantic, content = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient(content)
    first, meta_first, _decisions = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert first is not None and meta_first["cache"] == "miss" and client.calls == 1
    assert "遵守" not in meta_first.get("error", "")
    second, meta_second, _ = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert second == first
    assert meta_second["cache"] == "hit"
    assert client.calls == 1, "缓存命中不应再次调用模型"


def test_quality_judge_invalid_response_keeps_pending_and_is_not_cached(tmp_path, monkeypatch):
    resume, semantic, _content = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient("not-json")
    judgments, meta, _ = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert judgments is None
    assert meta["cache"] == "miss" and meta.get("error") == "invalid_judge_response"
    _judgments2, meta2, _ = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert meta2["cache"] == "miss"
    assert client.calls == 4, "每次最多纠错一次，无效结果不得写入缓存"


def test_quality_judge_disabled_without_llm_or_semantic_review(tmp_path, monkeypatch):
    resume, semantic, _content = _judge_fixture(tmp_path, monkeypatch)
    judgments, meta, decisions = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=None, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: _FakeJudgeClient("{}"),
    )
    assert judgments is None and meta["cache"] == "disabled"
    assert decisions == {"rejected": [], "selected": []}
    judgments, meta, _ = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=False, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: _FakeJudgeClient("{}"),
    )
    assert judgments is None and meta["cache"] == "disabled"


def test_quality_judge_loads_user_highlight_decisions(tmp_path, monkeypatch):
    from tools.infra import quality_judge_cache
    resume, semantic, content = _judge_fixture(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    resume_sha = hashlib.sha256(resume.encode("utf-8")).hexdigest()
    quality_judge_cache.save_highlight_decision(Path.cwd(), resume_sha, "hl_b1_d1", "reject")
    _judgments, _meta, decisions = run_evaluation._run_quality_judge(
        resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: _FakeJudgeClient(content),
    )
    assert decisions == {"rejected": ["hl_b1_d1"], "selected": []}


def test_quality_cache_invalidates_when_same_job_content_changes(tmp_path, monkeypatch):
    resume, semantic, content = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient(content)
    args = dict(resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
                use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
                client_factory=lambda: client)
    run_evaluation._run_quality_judge(**args)
    semantic["requirements"][0]["text"] = "负责数据平台交付"
    run_evaluation._run_quality_judge(**args)
    assert client.calls == 2


def test_quality_missing_jd_coverage_repairs_once_and_does_not_cache_pending(tmp_path, monkeypatch):
    resume, semantic, content = _judge_fixture(tmp_path, monkeypatch)
    payload = json.loads(content)
    payload["r2_1"] = []
    client = _FakeJudgeClient(json.dumps(payload))
    args = dict(resume_text=resume, trace={}, semantic_review=semantic, job_profile_path="job.yaml",
                use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
                client_factory=lambda: client)
    judgments, meta, _ = run_evaluation._run_quality_judge(**args)
    assert client.calls == 2 and "r2_1" not in judgments["judged_sections"]
    assert meta["repair_calls"] == 1
    assert not list((tmp_path / "judge-cache").glob("*.json"))


def test_quality_judge_uses_configured_provider_adapter(tmp_path, monkeypatch):
    resume, semantic, content = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient(content)
    created = []
    monkeypatch.setenv("LLM_PROVIDER", "lm_studio")
    monkeypatch.setattr(run_evaluation, "LLMClient", lambda **kwargs: created.append(kwargs) or client)
    run_evaluation._run_quality_judge(resume_text=resume, trace={}, semantic_review=semantic,
        job_profile_path="job.yaml", use_llm=True, model="m", api_key="k", base_url="http://localhost/v1")
    assert created[0]["provider"] == "lm_studio"


def test_quality_judge_only_receives_evidence_used_in_actual_resume(tmp_path, monkeypatch):
    resume, semantic, content = _judge_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(run_evaluation, "_load_quality_cards",
                        lambda _: {"ec_1": {"title": "统一平台"}, "unused": {"results": ["未呈现的百万级成果"]}})
    client = _FakeJudgeClient(content)
    run_evaluation._run_quality_judge(resume_text=resume,
        trace={"claims": [{"evidence_id": "ec_1", "text": "负责完成平台抽象"}]},
        semantic_review=semantic, job_profile_path="job.yaml", use_llm=True, model="m", api_key="k",
        base_url="http://fake/v1", client_factory=lambda: client)
    data = json.loads(client.last_prompt.split("INPUT JSON:\n", 1)[1])
    assert [card["id"] for card in data["cards"]] == ["ec_1"]
