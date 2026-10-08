import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from pathlib import Path

import pytest

from tools import run_generation


@pytest.fixture
def generation_inputs(tmp_path):
    profile = tmp_path / "personal_profile.yaml"
    profile.write_text(
        'name: "测试候选人"\nphone: "13800000000"\nemail: "candidate@example.com"\n'
        'city: "上海"\ncurrent_position: "后端工程师"\n', encoding="utf-8",
    )
    job = tmp_path / "job.yaml"
    job.write_text(
        'target_role: "Java技术专家"\ncompany: "目标公司"\n'
        'source_jd: "负责交易服务开发与数据库优化"\nkeywords:\n  - "Java"\n  - "Redis"\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ec-1.yaml").write_text(
        'id: "ec-1"\ntitle: "交易服务重构"\ntime_range: "2024-01 ~ 2024-06"\n'
        'role_scope: "模块负责人"\ncontext: "峰值请求延迟较高"\n'
        'raw_source: "/private/materials/worklog.md"\n'
        'actions:\n  - "使用 Java 重构交易服务"\n'
        'results:\n  - "请求延迟降低 20%"\nstack:\n  - "Java"\n'
        'artifacts:\n  - "性能报告.pdf"\n', encoding="utf-8",
    )
    report = tmp_path / "mr-target.yaml"
    report.write_text('score_total: 85\ntop_cards:\n  - id: "ec-1"\n', encoding="utf-8")
    return profile, job, evidence, report, tmp_path / "resumes"


def run_generation_cli(monkeypatch, inputs, *extra):
    profile, job, evidence, report, output = inputs
    monkeypatch.setattr("sys.argv", [
        "generate", "--matching-report", str(report), "--output-dir", str(output),
        "--evidence-dir", str(evidence), "--personal-profile", str(profile),
        "--job-profile", str(job), *extra,
    ])
    return run_generation._legacy_main()


def test_generation_uses_profile_and_target_without_internal_metadata(monkeypatch, generation_inputs):
    assert run_generation_cli(monkeypatch, generation_inputs) == 0
    output = generation_inputs[-1]
    resume = output / "resume_mr-target_A.md"
    text = resume.read_text()
    for expected in ["测试候选人", "candidate@example.com", "后端工程师", "目标公司", "Java技术专家", "请求延迟降低 20%"]:
        assert expected in text
    for forbidden in ["Resume Version", "Source report", "Evidence trace", "ec-1", "/private/", "性能报告.pdf", "Backend Tech Lead"]:
        assert forbidden not in text
    trace = json.loads(resume.with_suffix(".trace.json").read_text())
    assert trace["evidence_card_ids"] == ["ec-1"]
    assert trace["claims"]
    assert trace["readiness"]["status"] == "NEEDS_EVIDENCE"
    assert trace["readiness"]["missing_career_fields"]
    from tools.sidecar.handlers.resume import _parse_preview_markdown
    preview = _parse_preview_markdown(text)
    assert preview["contact"]["email"] == "candidate@example.com"
    assert preview["skills"] == ["Java"]
    assert preview["experience"][0]["title"] == "模块负责人"


def test_missing_profile_is_explicitly_not_deliverable(monkeypatch, generation_inputs):
    generation_inputs[0].unlink()
    assert run_generation_cli(monkeypatch, generation_inputs) == 0
    trace_path = generation_inputs[-1] / "resume_mr-target_A.trace.json"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text())
    assert trace["readiness"]["status"] == "NEEDS_EVIDENCE"
    assert "name" in trace["readiness"]["missing_profile_fields"]
    assert trace["readiness"]["deliverable"] is False


def test_unknown_selected_evidence_does_not_fall_back(monkeypatch, generation_inputs):
    generation_inputs[3].write_text('top_cards:\n  - id: "ec-unknown"\n', encoding="utf-8")
    assert run_generation_cli(monkeypatch, generation_inputs) != 0
    assert not list(generation_inputs[-1].glob("*.md"))


@pytest.mark.parametrize("response", [
    "我管理过 500 人团队，节省 9900 万美元。",
    json.dumps({"evidence_ids": ["ec-invented"]}),
])
def test_required_llm_rejects_unverifiable_output(monkeypatch, generation_inputs, response):
    monkeypatch.setattr(run_generation.LLMClient, "post_json", lambda *a: {
        "choices": [{"message": {"content": response}}],
    })
    assert run_generation_cli(
        monkeypatch, generation_inputs, "--use-llm", "--require-llm",
        "--model", "test-model", "--api-key", "test-key",
    ) != 0
    assert not list(generation_inputs[-1].glob("*.md"))


def test_job_description_file_is_resolved_relative_to_profile(monkeypatch, generation_inputs):
    job = generation_inputs[1]
    job.write_text('target_role: "Java专家"\ncompany: "目标公司"\nsource_jd: "description.txt"\n', encoding="utf-8")
    (job.parent / "description.txt").write_text("负责交易链路与缓存治理", encoding="utf-8")
    assert run_generation_cli(monkeypatch, generation_inputs) == 0
    trace = json.loads((generation_inputs[-1] / "resume_mr-target_A.trace.json").read_text())
    assert trace["target"]["jd_text"] == "负责交易链路与缓存治理"
    assert trace["readiness"]["missing_target_fields"] == []


def test_required_llm_selection_uses_real_http_protocol(monkeypatch, generation_inputs):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            data = json.dumps({"choices": [{"message": {"content": '{"evidence_ids":["ec-1"]}'}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    try:
        assert run_generation_cli(
            monkeypatch, generation_inputs, "--use-llm", "--require-llm",
            "--model", "test-model", "--api-key", "test-key",
            "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
        ) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert len(requests) == 2
    for request in requests:
        prompt = request["messages"][0]["content"]
        assert "目标公司" in prompt
        assert "负责交易服务开发与数据库优化" in prompt
        assert "后端工程师" in prompt
        assert "candidate@example.com" not in prompt
    trace = json.loads((generation_inputs[-1] / "resume_mr-target_A.trace.json").read_text())
    assert trace["generation_strategy"] == "llm_selection_locked_evidence_fields"


def test_gui_multiline_jd_round_trips_into_generation(generation_inputs):
    from tools.sidecar.handlers.jobs import _write_job_profile_file
    profile, job, *_ = generation_inputs
    jd = '招聘 "Java" 专家\n职责：负责订单平台和性能优化\n要求：熟悉 Redis 与 Kafka'
    _write_job_profile_file(job, {
        "target_role": "Java专家", "company": "目标公司", "source_jd": jd,
        "keywords": ["Java", "Redis", "Kafka"], "status": "active",
    })
    _, target = run_generation.load_generation_context(profile, job)
    assert target["jd_text"] == jd
    assert target["keywords"] == ["Java", "Redis", "Kafka"]


def test_high_score_without_real_gaps_is_quality_passed_but_needs_review(monkeypatch, generation_inputs):
    from tools import run_evaluation
    from tools.sidecar.handlers import agent

    profile, job, evidence, report, output = generation_inputs
    job.write_text(job.read_text().replace('  - "Redis"\n', ''), encoding="utf-8")
    report.write_text(
        'score_total: 90\nevidence_card_ids:\n  - "ec-1"\ntop_cards:\n  - id: "ec-1"\n'
        'gaps:\n  - "暂无明显缺口"\ngap_tasks:\n  - "保持当前证据完整度，按新 JD 微调关键词"\n',
        encoding="utf-8",
    )
    # 高分用例补齐已确认职业档案；五个基本字段不再足以通过完整内容要求。
    from tools.infra.career_profile import inspect_career
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    root_evidence=profile.parent/'evidence_cards';root_evidence.mkdir()
    (evidence/'ec-1.yaml').write_text((evidence/'ec-1.yaml').read_text()+'status: "saved_eligible"\ncandidate_pool_eligible: "true"\n')
    (root_evidence/'ec-1.yaml').write_bytes((evidence/'ec-1.yaml').read_bytes())
    career={'schema_version':1,'summary':'Java交易服务开发。','work':[{'id':'w','company':'测试任职公司','title':'工程师','department':'研发','start':'2020-01','end':'2025-01','current':False,'scope':'订单平台','contributions':['Java 服务开发，请求延迟降低 20%'],'evidence_ids':['ec-1']}],'education_visibility':'omit','education':[], 'skills':[{'id':'s','category':'服务开发','description':'Java 交易接口实践','evidence_ids':['ec-1']}],'extras':[]}
    fields=dict(parse_simple_yaml(profile.read_text())['scalars']);fields['career_json']=json.dumps(career,ensure_ascii=False)
    state=inspect_career(fields,root_evidence);fields['career_review_json']=json.dumps({'revision':state['revision']})
    profile.write_text('\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in fields.items())+'\n')
    assert run_generation_cli(monkeypatch, generation_inputs) == 0
    resume = output / "resume_mr-target_A.md"
    scorecard = output / "scorecard.md"
    monkeypatch.setattr("sys.argv", ["evaluate", "--input", str(resume), "--output", str(scorecard), "--job-profile", str(job)])
    assert run_evaluation._legacy_main() == 0
    summary = output.parent / "outputs/agent_runs/target/summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({"artifacts": {
        "matching": str(report), "evidence": str(evidence), "resume_dir": str(output),
        "scorecard": str(scorecard),
    }}), encoding="utf-8")
    monkeypatch.setattr(agent, "_PROJECT_ROOT", output.parent)
    result = agent._quick_run_result_details("target", "", "", selected_evidence_card_ids=["ec-1"])
    assert result["resume_readiness"]["evaluation_score"] >= 78
    assert result["resume_readiness"]["gap_tasks"] == []
    assert result["resume_readiness"]["quality_passed"] is True
    assert result["resume_readiness"]["status"] == "NEEDS_REVIEW"
    assert result["resume_readiness"]["deliverable"] is False


def test_generation_keeps_context_and_prioritizes_relevant_actions_without_inventing():
    card={'id':'ec-1','title':'交易服务','raw_source':'材料','time_range':'2024-2025','context':'高峰期订单查询慢','role_scope':'模块负责人',
          'actions':['整理接口文档','使用 Redis 缓存订单查询','通过压测分析数据库瓶颈','设置灰度回滚流程'],
          'results':['请求延迟降低 20%'],'stack':['Redis'],'artifacts':['材料']}
    claims=[]
    text=run_generation.build_template_resume('A','report',80,'now',[card],personal_profile={'name':'测试候选人'},job_context={'keywords':['Redis']},claims=claims)
    assert '场景：高峰期订单查询慢' in text
    assert text.index('使用 Redis 缓存订单查询')<text.index('整理接口文档')
    assert any(c['field']=='context' and c['text']=='高峰期订单查询慢' for c in claims)
    assert 'C++' not in text


def test_thin_evidence_generates_explicit_missing_fields(monkeypatch,generation_inputs):
    path=generation_inputs[2]/'ec-1.yaml';s=path.read_text();s=s.replace('role_scope: "模块负责人"','role_scope: ""').replace('time_range: "2024-01 ~ 2024-06"','time_range: ""').replace('  - "Java"\n','')
    path.write_text(s)
    assert run_generation_cli(monkeypatch,generation_inputs)==0
    trace=json.loads((generation_inputs[-1]/'resume_mr-target_A.trace.json').read_text())
    assert trace['readiness']['status']=='NEEDS_EVIDENCE'
    assert {'ec-1.role_scope','ec-1.time_range','skills'}<=set(trace['readiness']['missing_evidence_fields'])
    assert trace['readiness']['deliverable'] is False
