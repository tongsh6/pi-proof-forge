"""P0-026：评分依据必须与显示的质量指标一致。"""
import hashlib
import json
from pathlib import Path

import pytest
from tests.unit.engines.test_generation_engines import generation, write_reviewed_result_sources
from tests.unit.sidecar.test_evidence_source_merge import _scoped_review, result_review_model, sample as source_sample

from tools.cli.commands import evaluate as evaluate_cli
from tools.engines.evaluation import quality_report
from tools.engines.evaluation import rule_evaluator
from tools.domain.models import JobProfile, ResumeOutput
from tools.engines.evaluation.rule_evaluator import RuleEvaluationEngine


def evaluate(text, must_have=(), keywords=(), **kwargs):
    return rule_evaluator.evaluate_rule(text, list(must_have), list(keywords), "now", "resume.md", "job.yaml", **kwargs)


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
        {"text": "接口开发", "source_kind": "evidence", "evidence_id": "e1", "field": "actions", "fact_id": "e1:actions:0", "render_line": 1},
        {"text": "架构", "source_kind": "personal_profile", "field": "career.skills.s.category", "fact_id": "personal_profile:career.skills.s.category:0", "render_line": 3},
        {"text": "服务拆分", "source_kind": "personal_profile", "field": "career.skills.s.description", "fact_id": "personal_profile:career.skills.s.description:0", "render_line": 3},
        {"text": "Java负责人", "source_kind": "job_profile", "field": "target_role"},
    ]
    result = evaluate("- 接口开发\n- 接口开发，业绩提升 90%\n- 架构：服务拆分\n- Java负责人", verified_trace={"occurrence_lineage_version": 1, "claims": claims})
    assert result["traceability"]["verified_bullets"] == 2
    assert [row["verified"] for row in result["traceability"]["bullets"]] == [True, False, True, False]


def test_agent_keyword_coverage_uses_same_boundaries():
    profile = JobProfile("p", "后端", ("Java", "java", "Go", ""), "senior")
    resume = ResumeOutput("a", "p", "- 使用 JavaScript 和 Django", "markdown")
    assert RuleEvaluationEngine().evaluate(resume, profile).dimension_scores["coverage"] == 0.0


def test_agent_trace_credit_stays_on_the_actual_rendered_line(tmp_path):
    from tests.unit.infra.test_review_snapshot import _generated_content

    content, trace, _ = _generated_content(tmp_path)
    statement = trace["claims"][0]["text"]
    content += "- " + statement + "\n"
    trace["resume_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    resume = ResumeOutput("a", "p", content, "markdown", generation_trace=trace)
    profile = JobProfile("p", "后端", (), "senior")
    result = RuleEvaluationEngine().evaluate(resume, profile)
    assert result.dimension_scores["citation"] == 0.5


@pytest.mark.parametrize("mutation", ["missing_occurrence", "wrong_index", "wrong_value", "changed_source"])
def test_agent_evaluation_rejects_unbound_result_trace(tmp_path, mutation):
    from tests.unit.infra.test_review_snapshot import _generated_content

    content, trace, source = _generated_content(tmp_path)
    claim = trace["claims"][0]
    if mutation == "missing_occurrence":
        claim.pop("fact_id")
        claim.pop("render_line")
    elif mutation == "wrong_index":
        claim["fact_id"] = "card-a:results:999"
    elif mutation == "wrong_value":
        replacement = "已完成生产环境验收。"
        content = content.replace(claim["text"], replacement)
        claim["text"] = replacement
        trace["resume_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    else:
        source.write_text("来源结论已被撤回", encoding="utf-8")
    resume = ResumeOutput("a", "p", content, "markdown", generation_trace=trace)
    with pytest.raises(ValueError, match="generation_trace_invalid"):
        RuleEvaluationEngine().evaluate(resume, JobProfile("p", "后端", (), "senior"))



def test_plus_separates_stack_names_without_confusing_c_languages():
    result = evaluate("- Java+Spring Boot+MySQL，HTTP+json，C++ 和 C#", keywords=["Java", "Spring Boot", "MySQL", "HTTP", "json", "C", "C++", "C#"])
    assert result["keyword_coverage"]["matched"] == ["Java", "Spring Boot", "MySQL", "HTTP", "json", "C++", "C#"]


def test_agent_empty_keywords_keep_neutral_score():
    profile = JobProfile("p", "后端", ("",), "senior")
    resume = ResumeOutput("a", "p", "- 接口开发", "markdown")
    assert RuleEvaluationEngine().evaluate(resume, profile).dimension_scores["coverage"] == 0.5


@pytest.mark.parametrize("changed_input", ["card", "material", "resume", "during_trace_read"])
def test_cli_validates_trace_inputs_before_awarding_citations(tmp_path, monkeypatch, changed_input):
    source = tmp_path / "e1.yaml"
    value = "测试环境中接口延迟降低 30%"
    source.write_text("results:\n  - " + json.dumps(value) + "\n")
    sources = write_reviewed_result_sources(source, {0: value}, material_dir=tmp_path / "materials")
    material = next(iter(sources.values()))
    resume = tmp_path / "resume.md"
    resume.write_text(f"## 项目经历\n### 接口服务（2025）\n- {value}\n<!-- first-screen-end -->\n")
    trace = {
        "schema_version": 1,
        "occurrence_lineage_version": 1,
        "generation_strategy": "locked_evidence_fields",
        "resume_sha256": hashlib.sha256(resume.read_bytes()).hexdigest(),
        "evidence_card_ids": ["e1"],
        "inputs": {
            key: {"path": str(path), "exists": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for key, path in (("e1", source), *sources.items())
        },
        "claims": [{
            "text": value, "source_kind": "evidence",
            "evidence_id": "e1", "field": "results", "fact_id": "e1:results:0", "render_line": 3,
        }],
    }
    resume.with_suffix(".trace.json").write_text(json.dumps(trace))
    output = tmp_path / "scorecard.md"
    monkeypatch.setattr("sys.argv", ["evaluate", "--input", str(resume), "--output", str(output)])
    assert evaluate_cli.main() == 0
    result = json.loads(output.with_suffix(".json").read_text())
    assert result["traceability"]["verified_bullets"] == 1
    assert "证据引用检查: 100% (1/1)" in output.read_text()
    report = result["quality_report"]
    assert not any(f["rule"] == "R1.1" for f in report["tiers"]["eligible"]["failures"])
    assert report["tiers"]["strong"]["metrics"]["quant_first_screen"] == 1.0
    assert report["tiers"]["strong"]["metrics"]["quant_total"] == 1.0
    assert report["auto_pass"] is False

    # 保持结果原句、Fact ID 和呈现行不变，仅改变已绑定输入/正文版本。
    if changed_input == "during_trace_read":
        from tools.orchestration import evaluation_flow
        original_read = evaluation_flow.read_generation_trace
        def replace_body_and_trace(path):
            path.write_text(path.read_text() + "\n# 正文新版本\n")
            trace["resume_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_suffix(".trace.json").write_text(json.dumps(trace))
            return original_read(path)
        monkeypatch.setattr(evaluation_flow, "read_generation_trace", replace_body_and_trace)
    else:
        changed = {"card": source, "material": material, "resume": resume}[changed_input]
        changed.write_text(changed.read_text() + "\n# 来源或正文版本已更新\n")
    assert evaluate_cli.main() == 0
    result = json.loads(output.with_suffix(".json").read_text())
    assert result["traceability"]["status"] == "unverified"
    assert result["traceability"]["verified_bullets"] == 0
    report = result["quality_report"]
    assert report["tiers"]["strong"]["metrics"]["quant_first_screen"] == 0.0
    assert report["tiers"]["strong"]["metrics"]["quant_total"] == 0.0
    assert any(f["rule"] == "R1.1" for f in report["tiers"]["eligible"]["failures"])
    assert report["auto_pass"] is False


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
    assert evaluate_cli.main() == 0
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
    advice = report["delivery_advice"]
    assert advice["advisory_only"] is True
    assert advice["recommendation"] in {"strengthen", "reconsider", "fix_facts", "apply"}
    assert "## 投递建议" in markdown
    assert "仅供参考" in markdown
    for reason in advice["reasons"]:
        assert reason in markdown
    for action in advice["next_actions"]:
        assert action in markdown


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
    return resume, semantic, json.dumps(payload, ensure_ascii=False), {"ec_1": {"title": "统一平台"}}


@pytest.mark.parametrize(
    "provider,base_url,environment,expected_protocol",
    [
        ("openai_compatible", "https://api.example.test/proxy/localhost/v1", "default", {}),
        ("openai_compatible", "http://127.0.0.1:9000/v1", "default", {}),
        ("deepseek", "http://127.0.0.1:9000/v1", "off", {"thinking": {"type": "disabled"}}),
        ("openai_compatible", "http://127.0.0.1:8000/v1", "off", {"reasoning_effort": "none"}),
        ("strata", "http://127.0.0.1:47831/v1", "off", {"reasoning_effort": "none"}),
    ],
    ids=["remote-path-localhost", "unknown-loopback", "deepseek-off-loopback", "splash-explicit-off", "strata-off"],
)
def test_quality_judge_request_uses_shared_provider_adapter(tmp_path, monkeypatch, provider, base_url, environment, expected_protocol):
    import io

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_THINKING", environment)
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    requests = []

    def open_response(request, **kwargs):
        requests.append(request)
        response = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", open_response)
    judgments, meta, _decisions = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="synthetic-model", api_key="synthetic", base_url=base_url,
    )
    assert judgments is not None and meta["cache"] == "miss"
    assert meta["model_calls"] == 1 and meta["repair_calls"] == 0
    assert len(requests) == 1
    assert requests[0].full_url == base_url + "/chat/completions"
    payload = json.loads(requests[0].data)
    assert payload["response_format"] == {"type": "json_object"}
    actual_protocol = {key: payload[key] for key in ("reasoning_effort", "thinking") if key in payload}
    assert actual_protocol == expected_protocol


def test_quality_judge_cache_hit_avoids_second_model_call(tmp_path, monkeypatch):
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient(content)
    first, meta_first, _decisions = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert first is not None and meta_first["cache"] == "miss" and client.calls == 1
    assert "遵守" not in meta_first.get("error", "")
    second, meta_second, _ = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert second == first
    assert meta_second["cache"] == "hit"
    assert client.calls == 1, "缓存命中不应再次调用模型"


def test_quality_judge_invalid_response_keeps_pending_and_is_not_cached(tmp_path, monkeypatch):
    resume, semantic, _content, cards = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient("not-json")
    judgments, meta, _ = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert judgments is None
    assert meta["cache"] == "miss" and meta.get("error") == "invalid_judge_response"
    _judgments2, meta2, _ = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert meta2["cache"] == "miss"
    assert client.calls == 4, "每次最多纠错一次，无效结果不得写入缓存"


class _SequencedJudgeClient:
    chat_completions_url = "http://fake/v1/chat/completions"

    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0
        self.prompts = []

    def post_json(self, url, payload):
        self.calls += 1
        self.prompts.append(payload["messages"][-1]["content"])
        content = self.contents.pop(0) if self.contents else "{}"
        return {"choices": [{"message": {"content": content}}]}

    @staticmethod
    def extract_content(response):
        return response["choices"][0]["message"]["content"]


def test_quality_judge_retries_only_missing_sections_in_second_call(tmp_path, monkeypatch):
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    payload = json.loads(content)
    first = json.dumps({"r1_4": payload["r1_4"]}, ensure_ascii=False)
    second = json.dumps({key: payload[key] for key in ("r2_1", "r3_1", "r3_5", "r4_1")}, ensure_ascii=False)
    client = _SequencedJudgeClient([first, second])
    judgments, meta, _ = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: client,
    )
    assert judgments is not None
    assert set(judgments["judged_sections"]) == {"r1_4", "r2_1", "r3_1", "r3_5", "r4_1"}
    assert meta["model_calls"] == 2 and meta["repair_calls"] == 1
    assert client.calls == 2
    assert "EXACTLY these keys: r2_1, r3_1, r3_5, r4_1" in client.prompts[1]


def test_quality_judge_disabled_without_llm_or_semantic_review(tmp_path, monkeypatch):
    resume, semantic, _content, cards = _judge_fixture(tmp_path, monkeypatch)
    judgments, meta, decisions = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=None, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: _FakeJudgeClient("{}"),
    )
    assert judgments is None and meta["cache"] == "disabled"
    assert decisions == {"rejected": [], "selected": []}
    judgments, meta, _ = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=False, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: _FakeJudgeClient("{}"),
    )
    assert judgments is None and meta["cache"] == "disabled"


def test_quality_judge_loads_user_highlight_decisions(tmp_path, monkeypatch):
    from tools.infra import quality_judge_cache
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    resume_sha = hashlib.sha256(resume.encode("utf-8")).hexdigest()
    quality_judge_cache.save_highlight_decision(Path.cwd(), resume_sha, "hl_b1_d1", "reject")
    _judgments, _meta, decisions = quality_report._run_quality_judge(
        resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
        use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
        client_factory=lambda: _FakeJudgeClient(content),
    )
    assert decisions == {"rejected": ["hl_b1_d1"], "selected": []}


def test_quality_cache_invalidates_when_same_job_content_changes(tmp_path, monkeypatch):
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient(content)
    args = dict(resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
                use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
                client_factory=lambda: client)
    quality_report._run_quality_judge(**args)
    semantic["requirements"][0]["text"] = "负责数据平台交付"
    quality_report._run_quality_judge(**args)
    assert client.calls == 2


def test_quality_missing_jd_coverage_repairs_once_and_does_not_cache_pending(tmp_path, monkeypatch):
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    payload = json.loads(content)
    payload["r2_1"] = []
    client = _FakeJudgeClient(json.dumps(payload))
    args = dict(resume_text=resume, trace={}, cards=cards, semantic_review=semantic, job_profile_path="job.yaml",
                use_llm=True, model="fake-model", api_key="k", base_url="http://fake/v1",
                client_factory=lambda: client)
    judgments, meta, _ = quality_report._run_quality_judge(**args)
    assert client.calls == 2 and "r2_1" not in judgments["judged_sections"]
    assert meta["repair_calls"] == 1
    assert not list((tmp_path / "judge-cache").glob("*.json"))


def test_quality_judge_uses_configured_provider_adapter(tmp_path, monkeypatch):
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    client = _FakeJudgeClient(content)
    created = []
    monkeypatch.setenv("LLM_PROVIDER", "lm_studio")
    monkeypatch.setattr(quality_report, "LLMClient", lambda **kwargs: created.append(kwargs) or client)
    quality_report._run_quality_judge(resume_text=resume, trace={}, cards=cards, semantic_review=semantic,
        job_profile_path="job.yaml", use_llm=True, model="m", api_key="k", base_url="http://localhost/v1")
    assert created[0]["provider"] == "lm_studio"


def test_quality_judge_only_receives_evidence_used_in_actual_resume(tmp_path, monkeypatch):
    resume, semantic, content, cards = _judge_fixture(tmp_path, monkeypatch)
    cards = {**cards, "unused": {"results": ["未呈现的百万级成果"]}}
    client = _FakeJudgeClient(content)
    quality_report._run_quality_judge(resume_text=resume, cards=cards,
        trace={"claims": [{"evidence_id": "ec_1", "text": "负责完成平台抽象"}]},
        semantic_review=semantic, job_profile_path="job.yaml", use_llm=True, model="m", api_key="k",
        base_url="http://fake/v1", client_factory=lambda: client)
    data = json.loads(client.last_prompt.split("INPUT JSON:\n", 1)[1])
    assert [card["id"] for card in data["cards"]] == ["ec_1"]


def _bound_quality_fixture(tmp_path):
    """真实文件与精确 trace；各测试只操纵评测期间发生的版本变化。"""
    from tools.infra.persistence.review_snapshot import read_generation_trace
    from tools.orchestration.evaluation_flow import EvaluationFlowConfig

    resume, job, output = _quality_fixture(tmp_path)
    jd = tmp_path / "job.txt"
    jd.write_text("负责平台交付与接口性能验证。")
    job.write_text(job.read_text() + 'source_jd: "job.txt"\n')
    trace_path = resume.with_suffix(".trace.json")
    trace = json.loads(trace_path.read_text())
    trace["occurrence_lineage_version"] = 1
    trace["inputs"]["job_description"] = {"path": str(jd), "exists": True}
    sources = write_reviewed_result_sources(Path(trace["inputs"]["ec-1"]["path"]),
                                            {0: "请求延迟降低 20%"}, material_dir=tmp_path / "materials")
    trace["inputs"].update({key: {"path": str(path), "exists": True, "sha256": digest}
                           for key, (path, digest) in sources.snapshots.items()})
    for meta in trace["inputs"].values():
        meta["sha256"] = hashlib.sha256(Path(meta["path"]).read_bytes()).hexdigest()
    for claim in trace["claims"]:
        if claim["source_kind"] == "evidence":
            claim["fact_id"] = f'{claim["evidence_id"]}:{claim["field"]}:0'
            claim["render_line"] = next(
                number for number, line in enumerate(resume.read_text().splitlines(), 1)
                if claim["text"] in line)
    trace_path.write_text(json.dumps(trace))
    assert read_generation_trace(resume)[1]
    return EvaluationFlowConfig(input_path=resume, output_path=output, job_profile_path=job), trace


@pytest.mark.parametrize("input_key", ["ec-1", "personal_profile", "job_profile"])
def test_evaluation_rejects_different_bytes_consumed_then_restored(tmp_path, monkeypatch, input_key):
    from tools.orchestration import evaluation_flow

    config, trace = _bound_quality_fixture(tmp_path)
    target = Path(trace["inputs"][input_key]["path"])
    before_md, before_json = b"existing report\n", b'{"existing": true}\n'
    config.output_path.write_bytes(before_md)
    config.output_path.with_suffix(".json").write_bytes(before_json)
    read_bytes, read_text = Path.read_bytes, Path.read_text
    original = read_bytes(target)
    replacements = {
        "ec-1": ("模块负责人", "总体生产负责人"),
        "personal_profile": ("测试候选人", "另一候选人"),
        "job_profile": ("本科", "博士"),
    }
    old, new = replacements[input_key]
    changed = original.decode().replace(old, new).encode()
    assert changed != original
    state = {"armed": False, "consumed": False}
    read_trace = evaluation_flow.read_generation_trace

    def verified_then_arm(path):
        result = read_trace(path)
        assert result[1]
        state["armed"] = True
        return result

    def consume(method):
        def read(path, *args, **kwargs):
            if state["armed"] and not state["consumed"] and path == target:
                state["consumed"] = True
                path.write_bytes(changed)
                try:
                    return method(path, *args, **kwargs)
                finally:
                    path.write_bytes(original)
            return method(path, *args, **kwargs)
        return read

    monkeypatch.setattr(evaluation_flow, "read_generation_trace", verified_then_arm)
    monkeypatch.setattr(Path, "read_bytes", consume(read_bytes))
    monkeypatch.setattr(Path, "read_text", consume(read_text))
    assert evaluation_flow.run_evaluation_flow(config) == 1
    assert state["consumed"] and read_bytes(target) == original
    assert config.output_path.read_bytes() == before_md
    assert config.output_path.with_suffix(".json").read_bytes() == before_json


@pytest.mark.parametrize("input_key", ["ec-1", "personal_profile", "job_profile", "job_description"])
def test_evaluation_source_change_during_judge_keeps_existing_report(tmp_path, monkeypatch, input_key):
    from tools.orchestration import evaluation_flow

    config, trace = _bound_quality_fixture(tmp_path)
    target = Path(trace["inputs"][input_key]["path"])
    before_md, before_json = b"existing report\n", b'{"existing": true}\n'
    config.output_path.write_bytes(before_md)
    config.output_path.with_suffix(".json").write_bytes(before_json)
    run_judge = quality_report._run_quality_judge

    def judge_then_change(**kwargs):
        result = run_judge(**kwargs)
        target.write_bytes(target.read_bytes() + b"\n# changed during judgment\n")
        return result

    monkeypatch.setattr(quality_report, "_run_quality_judge", judge_then_change)
    assert evaluation_flow.run_evaluation_flow(config) == 1
    assert config.output_path.read_bytes() == before_md
    assert config.output_path.with_suffix(".json").read_bytes() == before_json


def test_evaluation_stable_bound_inputs_preserve_quality_and_trace_credit(tmp_path):
    from tools.orchestration.evaluation_flow import run_evaluation_flow

    config, _trace = _bound_quality_fixture(tmp_path)
    assert run_evaluation_flow(config) == 0
    result = json.loads(config.output_path.with_suffix(".json").read_text())
    assert result["traceability"]["verified_bullets"] == 1
    assert result["quality_report"]["tiers"]["strong"]["metrics"]["quant_total"] == 1.0
    assert result["quality_report"]["auto_pass"] is False


def test_evaluation_rejects_different_job_path_with_same_bytes(tmp_path):
    from dataclasses import replace
    from tools.orchestration.evaluation_flow import run_evaluation_flow

    config, _trace = _bound_quality_fixture(tmp_path)
    duplicate = tmp_path / "another-job.yaml"
    duplicate.write_bytes(config.job_profile_path.read_bytes())
    assert run_evaluation_flow(replace(config, job_profile_path=duplicate)) == 1
    assert not config.output_path.exists()
    assert not config.output_path.with_suffix(".json").exists()


def _bind_quality_career_card(config, trace, card_id, raw, *, measurement_quotes=None):
    from tools.infra.persistence.review_snapshot import read_generation_trace

    profile = Path(trace["inputs"]["personal_profile"]["path"])
    evidence_dir = profile.parent / "evidence_cards"
    evidence_dir.mkdir(exist_ok=True)
    card = evidence_dir / (card_id + ".yaml")
    card.write_bytes(raw)
    if measurement_quotes is not None:
        sources = write_reviewed_result_sources(card, measurement_quotes, material_dir=profile.parent / "materials")
        trace["inputs"].update({key: {"path": str(path), "exists": True, "sha256": digest}
                               for key, (path, digest) in sources.snapshots.items()})
        raw = card.read_bytes()
    career = {"schema_version": 1, "education_visibility": "omit",
              "skills": [{"id": "linked", "category": "接口开发", "description": "已关联事实",
                          "evidence_ids": [card_id]}]}
    profile.write_text(profile.read_text() + "career_json: " +
                       json.dumps(json.dumps(career, ensure_ascii=False), ensure_ascii=False) + "\n")
    trace["inputs"]["personal_profile"]["sha256"] = hashlib.sha256(profile.read_bytes()).hexdigest()
    trace["inputs"]["career_evidence:" + card_id] = {
        "path": str(card), "exists": True, "sha256": hashlib.sha256(raw).hexdigest()}
    config.input_path.with_suffix(".trace.json").write_text(json.dumps(trace))
    assert read_generation_trace(config.input_path)[1]
    return card


@pytest.mark.parametrize("same_bytes", [False, True])
def test_evaluation_uses_direct_card_version_instead_of_same_id_career_card(tmp_path, same_bytes):
    from tools.orchestration.evaluation_flow import run_evaluation_flow

    config, trace = _bound_quality_fixture(tmp_path)
    direct = Path(trace["inputs"]["ec-1"]["path"]).read_bytes()
    career = direct if same_bytes else direct.replace("请求延迟降低 20%".encode(), "完成接口验收".encode())
    _bind_quality_career_card(config, trace, "ec-1", career,
                             measurement_quotes=None if same_bytes else {0: None})
    assert run_evaluation_flow(config) == 0
    result = json.loads(config.output_path.with_suffix(".json").read_text())
    assert result["traceability"]["verified_bullets"] == 1
    assert result["quality_report"]["tiers"]["strong"]["metrics"]["quant_total"] == 1.0


def test_evaluation_checks_bytes_read_inside_career_inspection(tmp_path, monkeypatch):
    from tools.infra import career_profile
    from tools.orchestration.evaluation_flow import run_evaluation_flow

    config, trace = _bound_quality_fixture(tmp_path)
    card = _bind_quality_career_card(config, trace, "ec-indirect",
        b'id: "ec-indirect"\nstatus: "saved_eligible"\ncandidate_pool_eligible: "true"\n'
        b'results:\n  - "completed delivery"\nartifacts:\n  - "report"\n')
    original = card.read_bytes()
    changed = original.replace(b"completed delivery", b"planned delivery")
    read_bytes = Path.read_bytes
    inspect = career_profile.inspect_career
    state = {"inspecting": False, "consumed": False}

    def inspect_then_restore(*args, **kwargs):
        state["inspecting"] = True
        try:
            return inspect(*args, **kwargs)
        finally:
            state["inspecting"] = False

    def consume_changed_bytes(path):
        if state["inspecting"] and path == card and not state["consumed"]:
            state["consumed"] = True
            path.write_bytes(changed)
            try:
                return read_bytes(path)
            finally:
                path.write_bytes(original)
        return read_bytes(path)

    monkeypatch.setattr(career_profile, "inspect_career", inspect_then_restore)
    monkeypatch.setattr(Path, "read_bytes", consume_changed_bytes)
    assert run_evaluation_flow(config) == 1
    assert state["consumed"] and card.read_bytes() == original
    assert not config.output_path.exists()
    assert not config.output_path.with_suffix(".json").exists()


def _semantic_quality_fixture(tmp_path, monkeypatch):
    import io

    from tools.infra.llm.client import LLMClient
    from tools.engines.matching.semantic_matching import run_semantic_matching, write_semantic_report
    from tools.infra.persistence.review_snapshot import read_generation_trace

    config, trace = _bound_quality_fixture(tmp_path)

    def open_response(request, **kwargs):
        payload = json.loads(request.data)
        data = json.loads(payload["messages"][1]["content"])
        cite = {"fact_id": "ec-1:results:0", "quote": "请求延迟降低 20%"}
        if data["stage"] == "recall":
            response = {"cards": [{"id": "ec-1", "score": 90, "reason": "接口性能验证",
                                  "requirement_ids": ["r1"], "citations": [cite]}]}
        else:
            response = {"assessments": [
                {"requirement_id": row["id"],
                 "status": "supported" if row["text"] == "Java" else "insufficient",
                 "reason": "基于本次固定原文判读",
                 "citations": [cite] if row["text"] == "Java" else []}
                for row in data["requirements"]]}
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(response)}}]}).encode())

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", open_response)
    client = LLMClient("http://localhost/v1", "", provider="openai_compatible")

    report = tmp_path / "matching.yaml"
    semantic = run_semantic_matching(
        job_path=config.job_profile_path,
        evidence_files=[Path(trace["inputs"]["ec-1"]["path"])],
        personal_profile=Path(trace["inputs"]["personal_profile"]["path"]),
        client=client, model="test", cache_dir=tmp_path / "cache")
    write_semantic_report(report, semantic)
    trace["generation_strategy"] = "semantic_selection_locked_evidence_fields"
    for key, path in (("matching_report", report), ("semantic_matching", report.with_suffix(".semantic.json"))):
        trace["inputs"][key] = {"path": str(path), "exists": True,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    config.input_path.with_suffix(".trace.json").write_text(json.dumps(trace))
    assert read_generation_trace(config.input_path)[1]
    return config, report, semantic


@pytest.mark.parametrize("change_during_load", [False, True])
def test_evaluation_binds_semantic_object_to_consumed_trace_version(tmp_path, monkeypatch, change_during_load):
    from tools.engines.matching.semantic_matching import write_semantic_report
    from tools.engines.matching.semantic_review import aggregate_assessments
    from tools.orchestration import evaluation_flow as flow

    config, report, semantic = _semantic_quality_fixture(tmp_path, monkeypatch)
    paths = (report, report.with_suffix(".semantic.json"))
    original = {path: path.read_bytes() for path in paths}
    changed = json.loads(json.dumps(semantic))
    for assessment in changed["criterion_assessments"]:
        assessment["reason"] = "另一版本的判读理由"
    changed["assessments"] = aggregate_assessments(
        changed["requirements"], changed["requirement_checks"], changed["criterion_assessments"])
    write_semantic_report(report, changed)
    replacement = {path: path.read_bytes() for path in paths}
    for path, raw in original.items():
        path.write_bytes(raw)
    load = flow.load_semantic_report
    state = {"consumed": False}

    def load_then_restore(path):
        if not change_during_load:
            return load(path)
        for source, raw in replacement.items():
            source.write_bytes(raw)
        try:
            result = load(path)
            assert all(row["reason"] == "另一版本的判读理由" for row in result["criterion_assessments"])
            state["consumed"] = True
            return result
        finally:
            for source, raw in original.items():
                source.write_bytes(raw)

    monkeypatch.setattr(flow, "load_semantic_report", load_then_restore)
    config.output_path.write_text("existing markdown")
    config.output_path.with_suffix(".json").write_text("existing json")
    assert flow.run_evaluation_flow(config) == (1 if change_during_load else 0)
    assert state["consumed"] is change_during_load
    assert all(path.read_bytes() == raw for path, raw in original.items())
    if change_during_load:
        assert config.output_path.read_text() == "existing markdown"
        assert config.output_path.with_suffix(".json").read_text() == "existing json"
    else:
        result = json.loads(config.output_path.with_suffix(".json").read_text())
        assert result["semantic_review"]["mode"] == "semantic"
        assert all("基于本次固定原文判读" in row["reason"] for row in result["semantic_review"]["requirements"])
        assert result["traceability"]["verified_bullets"] == 1


def _generated_agent_input(generation):
    assembler, identity, matching, paths = generation
    resume = assembler.generate(matching, [identity], "guided-v1")
    profile = JobProfile(matching.job_profile_id, "工程师", (), "")
    from tools.infra.persistence.review_snapshot import validate_generation_trace
    assert validate_generation_trace(resume.content, resume.generation_trace)
    return resume, profile, paths


def test_agent_four_layer_report_uses_actual_body_and_current_sources(generation, monkeypatch):
    resume, profile, _paths = _generated_agent_input(generation)
    calls = []

    def unexpected_http(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("guided rule evaluation must not call a model")

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", unexpected_http)
    score = RuleEvaluationEngine().evaluate(resume, profile)
    assert calls == []
    assert score.resume_version == "guided-v1"
    assert score.job_profile_id == profile.id
    report = score.quality_report
    assert isinstance(report, dict), "the actual Agent evaluator must return its four-layer report"
    assert set(report["tiers"]) == {"eligible", "fit", "strong", "distinct"}
    assert report["resume_version"] == hashlib.sha256(resume.content.encode()).hexdigest()
    assert report["job_profile_id"] == profile.id
    assert report["tiers"]["strong"]["metrics"]["quant_total"] == 0.5
    assert report["llm_pending"] and report["auto_pass"] is False
    assert any(row["rule"] == "R1.5" for row in report["tiers"]["eligible"]["failures"])
    fit_rules = {row["rule"] for row in report["tiers"]["fit"]["failures"]}
    assert "R2.1" in fit_rules
    assert "R2.4" not in fit_rules


@pytest.mark.parametrize("mismatch", ["resume", "profile", "both"])
def test_agent_four_layer_rejects_target_identity_mismatch(generation, mismatch):
    from dataclasses import replace
    resume, profile, _paths = _generated_agent_input(generation)
    if mismatch in {"resume", "both"}:
        resume = replace(resume, job_profile_id="jp-other")
    if mismatch in {"profile", "both"}:
        profile = replace(profile, id="jp-other")
    with pytest.raises(ValueError):
        RuleEvaluationEngine().evaluate(resume, profile)


@pytest.mark.parametrize("changed_after_evaluation", [False, True])
def test_agent_revalidates_bound_source_after_evaluation_returns(generation, changed_after_evaluation):
    from tools.config.fragments import PolicyConfig
    from tools.orchestration.agent_loop import AgentLoop

    resume, profile, paths = _generated_agent_input(generation)
    original = paths["card"].read_bytes()

    class EvaluateThenChange:
        def evaluate(self, value, target):
            score = RuleEvaluationEngine().evaluate(value, target)
            if changed_after_evaluation:
                paths["card"].write_bytes(original + b"\n# changed after engine returned\n")
            return score

    policy = PolicyConfig(1, 0.01, 0.01, 1, "standard", "manual", True, (), ())
    loop = AgentLoop(policy, "ar-quality-source", dry_run=True,
                     evaluation_engine=EvaluateThenChange(), job_profile=profile)
    if changed_after_evaluation:
        with pytest.raises(ValueError, match="generation_trace"):
            loop._run_evaluation(resume)
        assert paths["card"].read_bytes() != original
    else:
        score = loop._run_evaluation(resume)
        assert score.resume_version == resume.version
        assert paths["card"].read_bytes() == original


@pytest.mark.parametrize("semantic", [
    None,
    {"mode": "rule", "occurrence_coverage_known": True, "requirements": []},
    {"mode": "semantic", "occurrence_coverage_known": False, "requirements": []},
    {"mode": "semantic", "occurrence_coverage_known": True, "requirements": []},
])
def test_agent_unassessed_projects_are_not_declared_irrelevant(generation, semantic):
    from tools.engines.evaluation import tiered_evaluator
    resume, _profile, _paths = _generated_agent_input(generation)
    result = tiered_evaluator.evaluate_fit(
        resume=resume.content, semantic_review=semantic, job_context={},
        config=tiered_evaluator.load_quality_config())
    assert result.passed is False
    assert "R2.4" not in {failure.rule for failure in result.failures}


@pytest.mark.parametrize("mapped", [False, True])
def test_agent_valid_current_mapping_preserves_irrelevance_control(generation, mapped):
    from tools.engines.evaluation import tiered_evaluator
    resume, _profile, _paths = _generated_agent_input(generation)
    action = next(claim for claim in resume.generation_trace["claims"]
                  if claim.get("fact_id") == "ec-engine:actions:0")
    semantic = {
        "mode": "semantic", "occurrence_coverage_known": True,
        "requirements": [{
            "requirement_id": "r1", "kind": "responsibility", "text": "负责队列处理与测试联调",
            "status": "supported" if mapped else "insufficient",
            "resume_status": "supported" if mapped else "not_present",
            "citations": [{
                "fact_id": action["fact_id"], "in_resume": True,
                "render_lines": [action["render_line"]],
            }] if mapped else [],
        }],
    }
    result = tiered_evaluator.evaluate_fit(
        resume=resume.content, semantic_review=semantic, job_context={},
        config=tiered_evaluator.load_quality_config())
    failures = [failure for failure in result.failures if failure.rule == "R2.4"]
    assert bool(failures) is (not mapped)


@pytest.mark.parametrize("source_sample", [(
    ["完成队列处理接口的联调与回放验收。"],
    ["在隔离测试环境中，固定负载下队列延迟降低 37%。"],
)], indirect=True)
@pytest.mark.parametrize("attribution, expected_quant", [("teammate", 0.0), ("self", 0.5)])
def test_agent_quantification_uses_rendered_result_occurrence(
        source_sample, result_review_model, attribution, expected_quant):
    from tools.domain.models import EvidenceCard, MatchingReport
    from tools.engines.generation.template_assembler import TemplateAssembler
    from tools.infra.persistence.review_snapshot import validate_generation_trace
    from tools.sidecar.handlers import evidence

    material_dir, card, params, scope = _scoped_review(source_sample, field="results")
    value = scope["value"]
    # One source occurrence may be adopted as action and result; the rendered identity matters.
    params["draft"]["actions"] = [value]
    params["draft"]["field_sources"].append({
        "field": "actions", "value": value, "quote": scope["source"]["quote"],
        "material_id": scope["source"]["material_id"],
        "document_id": scope["source"]["document_id"],
    })
    params["review"]["fact_scope"] = {**scope, "attribution": attribution}
    result_review_model["reply"] = {
        "outcome": "established", "measurement_quote": value,
        "rationale": "合成已核结果；归属由本条原范围明确限定。"}
    evidence.handle_evidence_save_draft(params)
    profile_path = material_dir.parent / "personal_profile.yaml"
    profile_path.write_text('name: "合成评估候选人"\ncurrent_position: "工程师"\n')
    job = material_dir.parent / "jp-agent-quality.yaml"
    job.write_text('target_role: "工程师"\ncompany: "合成公司"\nsource_jd: "负责队列接口与回放"\n')
    assembler = TemplateAssembler(
        evidence_dir=card.parent, personal_profile_path=profile_path, job_profile_path=job)
    resume = assembler.generate(
        MatchingReport(job.stem, (card.stem,), {}, ()),
        [EvidenceCard(card.stem, "选择身份", "", ("不得借用 DTO 的结果 99%",), ("原文",))],
        "numeric-identity")
    assert validate_generation_trace(resume.content, resume.generation_trace)
    rendered = {claim.get("fact_id") for claim in resume.generation_trace["claims"]}
    assert card.stem + ":actions:0" in rendered
    assert (card.stem + ":results:0" in rendered) is (attribution == "self")
    assert value in resume.content
    assert "99%" not in resume.content
    score = RuleEvaluationEngine().evaluate(resume, JobProfile(job.stem, "工程师", (), ""))
    report = score.quality_report
    assert isinstance(report, dict)
    assert report["tiers"]["strong"]["metrics"]["quant_total"] == expected_quant
    assert report["auto_pass"] is False and report["llm_pending"]


@pytest.mark.parametrize("input_key", ["ec-engine", "personal_profile", "job_profile"])
def test_agent_four_layer_consumed_bytes_cannot_be_restored_into_authority(
        generation, monkeypatch, input_key):
    resume, profile, _paths = _generated_agent_input(generation)
    target = Path(resume.generation_trace["inputs"][input_key]["path"])
    original = target.read_bytes()
    read_input = quality_report._read_quality_input
    state = {"consumed": False}

    def changed_bytes_then_restore(meta):
        if Path(meta["path"]) == target and not state["consumed"]:
            state["consumed"] = True
            target.write_bytes(original + b"\n# changed only while actually read\n")
            try:
                return read_input(meta)
            finally:
                target.write_bytes(original)
        return read_input(meta)

    monkeypatch.setattr(quality_report, "_read_quality_input", changed_bytes_then_restore)
    with pytest.raises(ValueError, match="quality_input_changed"):
        RuleEvaluationEngine().evaluate(resume, profile)
    assert state["consumed"] and target.read_bytes() == original


def test_agent_four_layer_source_change_during_report_rejects_result(generation, monkeypatch):
    from tools.engines.evaluation import tiered_evaluator

    resume, profile, paths = _generated_agent_input(generation)
    original = paths["card"].read_bytes()
    build_report = tiered_evaluator.build_quality_report
    state = {"evaluated": False}

    def report_then_change(**kwargs):
        report = build_report(**kwargs)
        state["evaluated"] = True
        paths["card"].write_bytes(original + b"\n# changed during four-layer calculation\n")
        return report

    monkeypatch.setattr(tiered_evaluator, "build_quality_report", report_then_change)
    with pytest.raises(ValueError):
        RuleEvaluationEngine().evaluate(resume, profile)
    assert state["evaluated"]
    assert paths["card"].read_bytes() != original


def test_agent_explicit_llm_keeps_the_source_bound_four_layer_report(generation, monkeypatch):
    import io
    from tools.engines.evaluation.llm_evaluator import LLMEvaluationEngine
    from tools.infra.llm.client import LLMClient

    resume, profile, _paths = _generated_agent_input(generation)
    expected = RuleEvaluationEngine().evaluate(resume, profile).quality_report
    assert isinstance(expected, dict) and expected["llm_pending"]
    calls = []

    def respond(request, **kwargs):
        assert request.full_url == "http://127.0.0.1:8000/v1/chat/completions"
        payload = json.loads(request.data)
        calls.append(payload)
        assert resume.content in payload["messages"][-1]["content"]
        answer = {
            "semantic_coverage": 1.0, "fabrication_risk": 0.0,
            "keyword_gaps": [], "strengths": ["合成显式模型参考评价"], "improvements": [],
        }
        return io.BytesIO(json.dumps({
            "choices": [{"message": {"content": json.dumps(answer)}}]
        }).encode())

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", respond)
    client = LLMClient("http://127.0.0.1:8000/v1", "", provider="openai_compatible",
                       thinking_enabled=None)
    score = LLMEvaluationEngine(client, "synthetic-reference-model").evaluate(resume, profile)
    assert len(calls) == 1
    assert score.dimension_scores["llm_semantic_coverage"] == 1.0
    assert score.quality_report == expected
    assert score.quality_report["auto_pass"] is False
    assert score.quality_report["resume_version"] == hashlib.sha256(resume.content.encode()).hexdigest()
    assert score.quality_report["job_profile_id"] == profile.id
