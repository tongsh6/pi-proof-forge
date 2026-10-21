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
    assert trace["field_provenance"]["ec-1"]["time_range_level"] == "L1"
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
        assert request["messages"][0]["role"] == "system"
        assert "PiProofForge" in request["messages"][0]["content"]
        prompt = next(message["content"] for message in request["messages"] if message["role"] == "user")
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
    # Phase A 尚未接入 LLM 判项，这里预置一份四层全通过的 quality_report，
    # 验证审批门禁只消费 auto_pass，而不是旧版 78 参考线。
    score_data = json.loads(scorecard.with_suffix(".json").read_text())
    score_data["quality_report"] = {
        "schema_version": 1,
        "auto_pass": True,
        "llm_pending": [],
        "tiers": {name: {"passed": True, "failures": []} for name in ("eligible", "fit", "strong", "distinct")},
        "gap_tasks": [],
        "legacy_scores": {"rule_total": score_data.get("total_score"), "llm_expression": score_data.get("expression_score")},
    }
    scorecard.with_suffix(".json").write_text(json.dumps(score_data), encoding="utf-8")
    summary = output.parent / "outputs/agent_runs/target/summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({"artifacts": {
        "matching": str(report), "evidence": str(evidence), "resume_dir": str(output),
        "scorecard": str(scorecard),
    }}), encoding="utf-8")
    monkeypatch.setattr(agent, "_PROJECT_ROOT", output.parent)
    result = agent._quick_run_result_details("target", "", "", selected_evidence_card_ids=["ec-1"])
    assert result["resume_readiness"]["evaluation_score"] >= 78
    # 工作职责改为非 bullet 后，旧版量化启发式可能留下“核对量化依据”建议；
    # 四层门禁只消费 quality_report/auto_pass，这里确认不会伪造成阻断。
    assert result["resume_readiness"]["auto_pass"] is True
    assert result["resume_readiness"]["quality_report"]["auto_pass"] is True
    assert "evaluation_reference_score" not in result["resume_readiness"]
    assert result["resume_readiness"]["quality_passed"] is True
    assert result["resume_readiness"]["status"] == "NEEDS_REVIEW"
    assert result["resume_readiness"]["deliverable"] is False

    # 规则分很高也不能覆盖语义判断中的证据不足。
    score = json.loads(scorecard.with_suffix('.json').read_text())
    score['expression_score'] = 95
    score['semantic_review'] = {'mode': 'semantic', 'fit_score': 0, 'resume_score': 0,
                                'all_requirements_supported': False, 'requirements': []}
    scorecard.with_suffix('.json').write_text(json.dumps(score))
    result = agent._quick_run_result_details('target', '', '', selected_evidence_card_ids=['ec-1'])
    assert result['resume_readiness']['quality_passed'] is False
    assert result['resume_readiness']['evaluation_score'] == 95
    assert result['semantic_review']['fit_score'] == 0


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


def test_generation_prioritizes_semantically_cited_action_over_literal_keyword_order():
    card={'id':'ec-1','title':'交易服务','raw_source':'材料','time_range':'2024-2025','context':'查询慢','role_scope':'负责人',
          'actions':['Java接口开发','Java文档整理','Java单元测试','实现幂等去重与故障恢复'],
          'results':['成功率99%'],'stack':['Java'],'artifacts':['报告']}
    claims=[]
    text=run_generation.build_template_resume('A','r',80,'now',[card],job_context={'keywords':['Java']},claims=claims,
        preferred_facts=[{'source_id':'ec-1','field':'actions','text':'实现幂等去重与故障恢复'}])
    assert '实现幂等去重与故障恢复' in text
    assert text.index('实现幂等去重与故障恢复') < text.index('Java接口开发')
    assert len([c for c in claims if c['field']=='actions']) == 3


def test_actions_without_lexical_result_match_are_not_paired_as_bullets():
    from tools.engines.evaluation.tiered_evaluator import inspect_bullet_trace
    card = {'id': 'ec-1', 'title': '交易平台', 'time_range': '2024 ~ 2025', 'role_scope': '负责人',
            'context': '多端交易交付。', 'actions': ['接口开发', '发布治理', '监控改进', '主导前后端方案设计'],
            'results': ['完成 15 个系统', '服务 6 个品牌', '查询耗时从 2 秒降至 300 毫秒'],
            'stack': ['Java'], 'artifacts': ['报告']}
    profile = {'career': {'skills': [{'id': 's1', 'category': '技术', 'description': '后端开发'}]}}
    claims = []
    text = run_generation.build_template_resume('A', 'r', 50, 'now', [card],
             personal_profile=profile, claims=claims)
    bullets = [line for line in text.splitlines() if line.startswith('- ')]
    assert not any(any(a in line for a in card['actions']) and any(r in line for r in card['results']) for line in bullets)
    for value in (card['actions'][0], card['results'][0]):
        assert value in text
    checked = inspect_bullet_trace(text, {'claims': claims})
    assert checked['verified_bullets'] == checked['total_bullets']


def test_targeted_generation_preserves_measured_improvement_over_repeated_scale():
    card = {'id': 'ec-1', 'title': '平台', 'time_range': '2024', 'role_scope': '负责人', 'context': '多品牌',
            'actions': ['开发工具'], 'results': ['交付 15 个系统', '服务 6 个品牌', '查询从 2 秒降至 300 毫秒'],
            'stack': [], 'artifacts': ['报告']}
    refs = [{'source_id': 'ec-1', 'field': 'results', 'text': r, 'requirement_id': 'r1', 'support_weight': 2}
            for r in card['results'][:2]]
    text = run_generation.build_template_resume('A', 'r', 50, 'now', [card], preferred_facts=refs)
    assert card['results'][2] in text


def test_thin_evidence_generates_explicit_missing_fields(monkeypatch,generation_inputs):
    path=generation_inputs[2]/'ec-1.yaml';s=path.read_text();s=s.replace('role_scope: "模块负责人"','role_scope: ""').replace('time_range: "2024-01 ~ 2024-06"','time_range: ""').replace('  - "Java"\n','')
    path.write_text(s)
    assert run_generation_cli(monkeypatch,generation_inputs)==0
    trace=json.loads((generation_inputs[-1]/'resume_mr-target_A.trace.json').read_text())
    assert trace['readiness']['status']=='NEEDS_EVIDENCE'
    assert {'ec-1.role_scope','ec-1.time_range','skills'}<=set(trace['readiness']['missing_evidence_fields'])
    assert trace['readiness']['deliverable'] is False


@pytest.mark.parametrize('placeholder', ['[]', '{}', 'null', 'None'])
def test_empty_role_placeholder_is_not_a_personal_responsibility(monkeypatch, generation_inputs, placeholder):
    path = generation_inputs[2] / 'ec-1.yaml'
    path.write_text(path.read_text().replace('role_scope: "模块负责人"', 'role_scope: "' + placeholder + '"'))
    assert run_generation_cli(monkeypatch, generation_inputs) == 0
    resume = generation_inputs[-1] / 'resume_mr-target_A.md'
    trace = json.loads(resume.with_suffix('.trace.json').read_text())
    assert 'ec-1.role_scope' in trace['readiness']['missing_evidence_fields']
    assert '角色：' + placeholder not in resume.read_text()


def test_generation_and_evaluation_reuse_verified_semantic_selection(monkeypatch, generation_inputs):
    from tools.infra.semantic_matching import run_semantic_matching, write_semantic_report
    from tools import run_evaluation
    profile, job, evidence, report, output = generation_inputs
    class Client:
        chat_completions_url = 'http://localhost/v1/chat/completions'
        def post_json(self, url, payload, **kwargs):
            data = json.loads(payload['messages'][1]['content'])
            cite = {'fact_id': 'ec-1:actions:0', 'quote': '使用 Java 重构交易服务'}
            if data['stage'] == 'recall':
                response = {'cards': [{'id': 'ec-1', 'score': 90, 'reason': '交易开发实践', 'requirement_ids': ['r1'], 'citations': [cite]}]}
            else:
                response = {'assessments': [{'requirement_id': r['id'], 'status': 'supported' if r['text'] == 'Java' else 'insufficient',
                                            'reason': '按原文核对', 'citations': [cite] if r['text'] == 'Java' else []} for r in data['requirements']]}
            return {'choices': [{'message': {'content': json.dumps(response)}}]}
        @staticmethod
        def extract_content(response): return response['choices'][0]['message']['content']
    review = run_semantic_matching(job_path=job, evidence_files=list(evidence.glob('*.yaml')), personal_profile=profile,
                                   client=Client(), model='test', cache_dir=output.parent/'cache')
    write_semantic_report(report, review)
    monkeypatch.setattr(run_generation.LLMClient, 'post_json', lambda *args, **kwargs: pytest.fail('不得重复调用模型选材/解释'))
    assert run_generation_cli(monkeypatch, generation_inputs, '--use-llm', '--require-llm') == 0
    resume = output/'resume_mr-target_A.md'
    trace = json.loads(resume.with_suffix('.trace.json').read_text())
    assert trace['generation_strategy'] == 'semantic_selection_locked_evidence_fields'
    assert 'semantic_matching' in trace['inputs']
    monkeypatch.setattr('sys.argv', ['evaluate', '--input', str(resume), '--output', str(output/'score.md'), '--job-profile', str(job), '--use-llm', '--require-llm'])
    assert run_evaluation._legacy_main() == 0
    score = json.loads((output/'score.json').read_text())
    assert score['semantic_review']['mode'] == 'semantic'
    assert score['semantic_review']['requirements'][0]['resume_status'] == 'supported'
    assert score['semantic_review']['requirements'][1]['resume_status'] == 'insufficient'
    assert any('Redis' in task for task in score['gap_tasks'])
    assert '## 硬性条件待核对' not in (output/'score.md').read_text()
    assert '## 当前待处理缺口' in (output/'score.md').read_text()
    alternative = output.parent/'alternative'
    alternative.mkdir()
    (alternative/'ec-1.yaml').write_text((evidence/'ec-1.yaml').read_text().replace('请求延迟降低 20%', '请求延迟降低 90%'))
    assert run_generation_cli(monkeypatch, (profile, job, alternative, report, output/'changed'), '--use-llm', '--require-llm') == 1
    other_profile = output.parent/'other-profile.yaml'
    other_profile.write_text(profile.read_text().replace('测试候选人', '另一候选人'))
    assert run_generation_cli(monkeypatch, (other_profile, job, evidence, report, output/'changed-profile'), '--use-llm', '--require-llm') == 1
    report.unlink()
    monkeypatch.setattr(run_generation.LLMClient, 'post_json', lambda *args, **kwargs: {'choices': [{'message': {'content': '旧解释不能替代丢失的语义结果'}}]})
    monkeypatch.setattr('sys.argv', ['evaluate', '--input', str(resume), '--output', str(output/'invalid.md'), '--job-profile', str(job), '--use-llm', '--require-llm', '--model', 'test', '--api-key', 'local'])
    assert run_evaluation._legacy_main() == 1
    assert not (output/'invalid.md').exists()
