import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from pathlib import Path

import pytest
from tests.unit.engines.test_fact_index import reviewed_card_results
from tests.unit.engines.test_generation_engines import write_reviewed_result_sources

from tools.cli.commands import generate as generate_cli
from tools.engines.generation.resume_renderer import build_template_resume, load_generation_context


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
    write_reviewed_result_sources(evidence / "ec-1.yaml", {0: "请求延迟降低 20%"}, material_dir=tmp_path / "materials")
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
    return generate_cli.main()


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
    assert run_generation_cli(monkeypatch, generation_inputs) == 1
    assert not list(generation_inputs[-1].glob("*.md"))
    assert not list(generation_inputs[-1].glob("*.trace.json"))


def test_unknown_selected_evidence_does_not_fall_back(monkeypatch, generation_inputs):
    generation_inputs[3].write_text('top_cards:\n  - id: "ec-unknown"\n', encoding="utf-8")
    assert run_generation_cli(monkeypatch, generation_inputs) != 0
    assert not list(generation_inputs[-1].glob("*.md"))


@pytest.mark.parametrize("response", [
    "我管理过 500 人团队，节省 9900 万美元。",
    json.dumps({"evidence_ids": ["ec-invented"]}),
])
def test_required_llm_rejects_unverifiable_output(monkeypatch, generation_inputs, response):
    monkeypatch.setattr("tools.infra.llm.client.LLMClient.post_json", lambda *a: {
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
    _, target = load_generation_context(profile, job)
    assert target["jd_text"] == jd
    assert target["keywords"] == ["Java", "Redis", "Kafka"]


def test_high_score_with_pdf_clip_check_pending_still_allows_manual_review(monkeypatch, generation_inputs):
    from tools.cli.commands import evaluate as evaluate_cli
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
    assert evaluate_cli.main() == 0
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
    # 实际导出仍只计页，不能因高分和预置判项全过而声称无裁切。
    assert result["resume_pdf"]
    assert result["resume_readiness"]["auto_pass"] is False
    quality = result["resume_readiness"]["quality_report"]
    assert quality["auto_pass"] is False
    pdf_metrics = quality["tiers"]["eligible"]["metrics"]
    assert pdf_metrics["pdf_pages"] == 1 and pdf_metrics["clip_check"] is None
    assert pdf_metrics["pdf_check_state"] == "unverified"
    assert "evaluation_reference_score" not in result["resume_readiness"]
    assert result["resume_readiness"]["quality_passed"] is False
    assert result["resume_readiness"]["manual_override_allowed"] is True
    assert result["resume_readiness"]["quality_gate_blocking"] is False
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
    card={'id':'ec-1','title':'交易服务','raw_source':'材料','time_range':'2024-2025','context':'高峰期交易订单查询延迟较高','role_scope':'模块负责人',
          'actions':['整理接口文档','使用 Redis 缓存订单查询','通过压测分析数据库瓶颈','设置灰度回滚流程'],
          'results':['请求延迟降低 20%'],'stack':['Redis'],'artifacts':['材料']}
    claims=[]
    text=build_template_resume('A', [card],personal_profile={'name':'测试候选人'},job_context={'keywords':['Redis']},claims=claims)
    assert '背景：高峰期交易订单查询延迟较高' in text
    assert '使用 Redis 缓存订单查询' in text
    assert any(c['field']=='context' and c['text']=='高峰期交易订单查询延迟较高' for c in claims)
    assert 'C++' not in text


def test_generation_prioritizes_semantically_cited_action_over_literal_keyword_order():
    card={'id':'ec-1','title':'交易服务','raw_source':'材料','time_range':'2024-2025','context':'查询慢','role_scope':'负责人',
          'actions':['Java交易接口开发与联调','Java交易文档整理与交付','Java交易服务单元测试','实现幂等去重与故障恢复'],
          'results':['成功率99%'],'stack':['Java'],'artifacts':['报告']}
    claims=[]
    text=build_template_resume('A', [card],job_context={'keywords':['Java']},claims=claims,
        semantic_report={'requirements':[{'id':'r1','text':'实现幂等去重与故障恢复'}],
            'assessments':[{'requirement_id':'r1','status':'supported',
                            'citations':[{'fact_id':'ec-1:actions:3'}]}]})
    assert '实现幂等去重与故障恢复' in text
    assert text.index('实现幂等去重与故障恢复') < text.index('Java交易接口开发与联调')
    assert any(c.get('fact_id') == 'ec-1:actions:3' for c in claims)


def test_actions_without_lexical_result_match_are_not_paired_as_bullets():
    from tools.engines.evaluation.tiered_evaluator import inspect_bullet_trace
    card = {'id': 'ec-1', 'title': '交易平台', 'time_range': '2024 ~ 2025', 'role_scope': '负责人',
            'context': '多端交易交付。', 'actions': ['实现消费端接口与回调联调', '构建发布核对及回滚流程', '完成监控告警与指标接入', '主导前后端接口方案设计'],
            'results': ['完成 15 个业务系统的联调验收', '交付服务于 6 个品牌的订阅能力', '查询耗时从 2 秒降至 300 毫秒'],
            'stack': ['Java'], 'artifacts': ['报告']}
    profile = {'career': {'skills': [{'id': 's1', 'category': '技术', 'description': '后端开发'}]}}
    claims = []
    card = reviewed_card_results(card, measurement_quotes={2: card['results'][2]})
    text = build_template_resume('A', [card],
             personal_profile=profile, claims=claims)
    bullets = [line for line in text.splitlines() if line.startswith('- ')]
    assert not any(any(a in line for a in card['actions']) and any(r in line for r in card['results']) for line in bullets)
    assert '- ' + card['actions'][0] in text
    assert '- ' + card['results'][0] in text
    for value in (card['actions'][0], card['results'][0]):
        assert value in text
    checked = inspect_bullet_trace(text, {'claims': claims, 'occurrence_lineage_version': 1})
    assert checked['verified_bullets'] == checked['total_bullets']


def test_targeted_generation_keeps_cited_measured_and_nonquant_results_within_budget():
    card = {'id': 'ec-1', 'title': '平台', 'time_range': '2024', 'role_scope': '负责人', 'context': '多品牌',
            'actions': ['开发工具'],
            'results': ['交付 15 个系统', '服务 6 个品牌', '隔离测试中查询从 2 秒降至 300 毫秒'],
            'stack': [], 'artifacts': ['报告']}
    card = reviewed_card_results(card, measurement_quotes={2: card['results'][2]})
    claims = []
    text = build_template_resume('A', [card], claims=claims, semantic_report={
        'requirements': [{'id': 'r1'}], 'assessments': [{
            'requirement_id': 'r1', 'status': 'supported', 'citations': [
                {'fact_id': 'ec-1:results:1'}, {'fact_id': 'ec-1:results:2'},
            ],
        }],
    })
    assert card['results'][1] in text and card['results'][2] in text
    assert card['results'][0] not in text
    assert {claim['fact_id'] for claim in claims if claim.get('field') == 'results'} == {
        'ec-1:results:1', 'ec-1:results:2',
    }


def test_untimed_evidence_cannot_publish_a_complete_resume(monkeypatch, generation_inputs):
    path = generation_inputs[2] / "ec-1.yaml"
    path.write_text(path.read_text().replace('time_range: "2024-01 ~ 2024-06"', 'time_range: ""'))
    assert run_generation_cli(monkeypatch, generation_inputs) == 1
    assert not list(generation_inputs[-1].glob("*.md"))
    assert not list(generation_inputs[-1].glob("*.trace.json"))


@pytest.mark.parametrize('placeholder', ['[]', '{}', 'null', 'None'])
def test_empty_role_placeholder_is_not_a_personal_responsibility(monkeypatch, generation_inputs, placeholder):
    path = generation_inputs[2] / 'ec-1.yaml'
    path.write_text(path.read_text().replace('role_scope: "模块负责人"', 'role_scope: "' + placeholder + '"'))
    assert run_generation_cli(monkeypatch, generation_inputs) == 0
    resume = generation_inputs[-1] / 'resume_mr-target_A.md'
    trace = json.loads(resume.with_suffix('.trace.json').read_text())
    assert 'ec-1.role_scope' in trace['readiness']['missing_soft_fields']
    assert '角色：' + placeholder not in resume.read_text()


def test_generation_and_evaluation_reuse_verified_semantic_selection(monkeypatch, generation_inputs):
    from tools.engines.matching.semantic_matching import run_semantic_matching, write_semantic_report
    from tools.cli.commands import evaluate as evaluate_cli
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
    monkeypatch.setattr('tools.infra.llm.client.LLMClient.post_json', lambda *args, **kwargs: pytest.fail('不得重复调用模型选材/解释'))
    assert run_generation_cli(monkeypatch, generation_inputs, '--use-llm', '--require-llm') == 0
    resume = output/'resume_mr-target_A.md'
    trace = json.loads(resume.with_suffix('.trace.json').read_text())
    assert trace['generation_strategy'] == 'semantic_selection_locked_evidence_fields'
    assert 'semantic_matching' in trace['inputs']
    monkeypatch.setattr('sys.argv', ['evaluate', '--input', str(resume), '--output', str(output/'score.md'), '--job-profile', str(job), '--use-llm', '--require-llm'])
    assert evaluate_cli.main() == 0
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
    monkeypatch.setattr('tools.infra.llm.client.LLMClient.post_json', lambda *args, **kwargs: {'choices': [{'message': {'content': '旧解释不能替代丢失的语义结果'}}]})
    monkeypatch.setattr('sys.argv', ['evaluate', '--input', str(resume), '--output', str(output/'invalid.md'), '--job-profile', str(job), '--use-llm', '--require-llm', '--model', 'test', '--api-key', 'local'])
    assert evaluate_cli.main() == 1
    assert not (output/'invalid.md').exists()


def test_same_project_action_order_follows_explicit_jd_responsibility_rank(monkeypatch, generation_inputs):
    from tools.engines.matching.semantic_matching import run_semantic_matching, write_semantic_report

    profile, job, evidence, report, output = generation_inputs
    responsibilities = ("负责库存异常恢复", "负责交易一致性复核", "负责供应商账单审核", "负责通知失败处理")
    actions = ("实现库存事件的断点续跑", "构建通知失败后的幂等补发")
    fact_ids = ("ec-1:actions:0", "ec-1:actions:1")
    binding = {responsibilities[0]: dict(fact_id=fact_ids[0], quote=actions[0]),
               responsibilities[3]: dict(fact_id=fact_ids[1], quote=actions[1])}
    card = evidence / "ec-1.yaml"
    card.write_text(card.read_text().replace(
        '  - "使用 Java 重构交易服务"',
        ''.join(f'  - "{action}"\n' for action in actions).rstrip(),
    ))
    jd = job.with_suffix(".txt")
    job.write_text('target_role: "后端工程师"\ncompany: "目标公司"\nsource_jd: "job.txt"\n')

    class Transport:
        chat_completions_url = "http://localhost/v1/chat/completions"

        def post_json(self, url, payload, **kwargs):
            data = json.loads(payload["messages"][1]["content"])
            if data["stage"] == "recall":
                return self.wrap({"cards": [{"id": "ec-1", "score": 90, "reason": "两条工作证据",
                    "requirement_ids": ["d1", "d4"], "citations": list(binding.values())}]})
            assessments = []
            for req in data["requirements"]:
                cite = binding.get(req["text"].split(". ", 1)[-1])
                assessments.append({"requirement_id": req["id"],
                    "status": "supported" if cite else "insufficient", "reason": "按测试事实逐一核对",
                    "citations": [cite] if cite else []})
            return self.wrap({"assessments": assessments})

        @staticmethod
        def wrap(body):
            return {"choices": [{"message": {"content": json.dumps(body)}}]}

        @staticmethod
        def extract_content(response):
            return response["choices"][0]["message"]["content"]

    monkeypatch.setattr("tools.infra.llm.client.LLMClient.post_json",
                        lambda *args, **kwargs: pytest.fail("unexpected real model call"))
    # Swap only duties #1 and #4. The two unsupported middle duties remain untouched.
    swapped = (responsibilities[3], *responsibilities[1:3], responsibilities[0])
    for ordered, expected in ((responsibilities, fact_ids), (swapped, fact_ids[::-1])):
        jd.write_text("工作职责\n" + "\n".join(f"{n}. {duty}" for n, duty in enumerate(ordered, 1)) + "\n")
        current = run_semantic_matching(job_path=job, evidence_files=[card], personal_profile=profile,
                                        client=Transport(), model="test", cache_dir=output.parent / "cache")
        positive = {row["requirement_id"]: [cite["fact_id"] for cite in row["citations"]]
                    for row in current["assessments"] if row["status"] == "supported"}
        assert positive == {"d1": [expected[0]], "d4": [expected[1]]}
        write_semantic_report(report, current)
        assert run_generation_cli(monkeypatch, generation_inputs, "--use-llm", "--require-llm") == 0
        resume = output / "resume_mr-target_A.md"
        markdown = resume.read_text()
        lines = markdown.splitlines()
        trace = json.loads(resume.with_suffix(".trace.json").read_text())
        by_line = sorted((claim["render_line"], claim["fact_id"], claim["text"]) for claim in trace["claims"]
                         if claim.get("fact_id") in fact_ids)
        assert [item[1] for item in by_line] == list(expected)
        assert "## 项目经历" in lines[:by_line[0][0]]
        assert not any(line.startswith("#") for line in lines[by_line[0][0]:by_line[1][0]])
        for line, fact_id, word in by_line:
            assert word == actions[fact_ids.index(fact_id)] and word in lines[line - 1] and markdown.count(word) == 1

@pytest.mark.parametrize("changed", ["profile", "job", "card"])
def test_semantic_binding_uses_consumed_input_version(monkeypatch, generation_inputs, changed):
    from tools.engines.generation import resume_renderer
    from tools.engines.matching.semantic_matching import run_semantic_matching, write_semantic_report

    profile, job, evidence, report, output = generation_inputs

    class Client:
        chat_completions_url = "http://localhost/v1/chat/completions"

        def post_json(self, url, payload, **kwargs):
            data = json.loads(payload["messages"][1]["content"])
            cite = {"fact_id": "ec-1:actions:0", "quote": "使用 Java 重构交易服务"}
            if data["stage"] == "recall":
                body = {"cards": [{"id": "ec-1", "score": 90, "reason": "合成事实",
                                  "requirement_ids": ["r1"], "citations": [cite]}]}
            else:
                body = {"assessments": [{"requirement_id": row["id"], "status": "supported",
                                        "reason": "合成引文", "citations": [cite]}
                                       for row in data["requirements"]]}
            return {"choices": [{"message": {"content": json.dumps(body)}}]}

        @staticmethod
        def extract_content(response):
            return response["choices"][0]["message"]["content"]

    semantic = run_semantic_matching(
        job_path=job, evidence_files=list(evidence.glob("*.yaml")), personal_profile=profile,
        client=Client(), model="fixture", cache_dir=output.parent / "cache")
    write_semantic_report(report, semantic)
    hook = "load_all_cards" if changed == "card" else "load_generation_context"
    original = getattr(resume_renderer, hook)

    def change_after_initial_binding(*args, **kwargs):
        path = {"profile": profile, "job": job, "card": evidence / "ec-1.yaml"}[changed]
        before = path.read_text()
        path.write_text(before.replace("测试候选人", "修改后的候选人")
                       if changed == "profile" else before.replace("目标公司", "修改后的公司")
                       if changed == "job" else before.replace("重构交易服务", "重构库存服务"))
        return original(*args, **kwargs)

    monkeypatch.setattr(resume_renderer, hook, change_after_initial_binding)
    assert run_generation_cli(monkeypatch, generation_inputs, "--use-llm", "--require-llm") == 1
    assert not list(output.glob("*.md"))


def _selection_project(card_id, *, actions=(), results=(), measurement_quotes=None):
    """Explicit established synthetic facts; no reviewer or matching model is stubbed."""
    return reviewed_card_results({
        "id": card_id, "title": "合成项目 " + card_id.removeprefix("ec-").replace("-", " "),
        "time_range": "2024-01 ~ 2024-06", "role_scope": "负责接口联调",
        "context": "隔离环境中的合成业务流程验收",
        "actions": list(actions),
        "results": list(results) or ["在隔离环境中完成合成流程验收"],
        "stack": [], "artifacts": ["合成验收报告"],
    }, measurement_quotes=measurement_quotes)


def _selection_sources(tmp_path, cards):
    """Use J's actual source/basis fixture, then the production card loader."""
    from tools.engines.generation.resume_renderer import load_cards
    from tools.engines.matching.semantic_matching import _facts
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    evidence = tmp_path / "selection-evidence"
    evidence.mkdir()
    for card in cards:
        path = evidence / (card["id"] + ".yaml")
        lines = []
        for key, value in card.items():
            if key == "result_reviews":
                continue
            if isinstance(value, list):
                lines.append(key + ":")
                lines.extend("  - " + json.dumps(item, ensure_ascii=False) for item in value)
            else:
                lines.append(key + ": " + json.dumps(value, ensure_ascii=False))
        path.write_text("\n".join(lines) + "\n")
        measurements = {
            row["index"]: row["result_review"]["measurement_quote"]
            for row in card["result_reviews"].values()
        }
        write_reviewed_result_sources(path, measurements, material_dir=tmp_path / "materials")
    views = load_cards(evidence, [card["id"] for card in cards], tmp_path / "materials",
                       require_saved_eligible=True)
    facts = {}
    inputs = {}
    for view in views:
        path = evidence / (view["id"] + ".yaml")
        facts.update(_facts(view["id"], parse_simple_yaml(path.read_text())))
        inputs[view["id"]] = {"path": str(path), "sha256": view["source_sha256"]}
    return views, {"facts": facts, "inputs": inputs, "advisory_scope": False}


def _selection_report(base, assessments, *, preferred=()):
    """Declare support independently; fill exact quotes from captured synthetic sources."""
    from copy import deepcopy

    rows = deepcopy(assessments)
    for parent in rows:
        children = parent.get("checks", [parent])
        for child in children:
            for citation in child["citations"]:
                citation["quote"] = base["facts"][citation["fact_id"]]["text"]
        if "checks" in parent:
            parent["citations"] = [citation for child in children for citation in child["citations"]]
    return {**base,
        "requirements": [{"id": row["requirement_id"], "kind": "must_have",
                          "text": "合成岗位要求 " + row["requirement_id"]} for row in rows],
        "assessments": rows, "selected_card_ids": list(preferred)}


def _render_selection(views, report):
    from tools.engines.matching.semantic_review import resume_assessment

    claims = []
    markdown = build_template_resume("A", views, semantic_report=report, claims=claims)
    lines = markdown.splitlines()
    for claim in claims:
        if claim.get("fact_id"):
            assert claim["text"] in lines[claim["render_line"] - 1]
    assessment = resume_assessment(report, claims, occurrence_coverage_known=True)
    return markdown, claims, assessment


def _claimed_projects(claims):
    return list(dict.fromkeys(
        claim["evidence_id"] for claim in claims
        if claim.get("source_kind") == "evidence" and claim.get("field") in {"actions", "results"}
    ))


def test_semantic_budget_keeps_cited_nonquant_result_after_final_quant_order(tmp_path):
    actions = [
        "实现交易事件的断点恢复", "建立接口错误的幂等处理",
        "构建发布失败后的回滚流程", "完成跨系统一致性核对",
    ]
    results = [
        "隔离测试中请求延迟降低 20%", "隔离测试中恢复耗时降低 30%",
        "隔离测试中回滚耗时降低 40%", "跨系统数据核对已经通过独立验收",
    ]
    source = _selection_project("ec-budget", actions=actions, results=results,
                                measurement_quotes={i: results[i] for i in range(3)})
    views, base = _selection_sources(tmp_path, [source])
    report = _selection_report(base, [
        {"requirement_id": "r-action", "status": "supported",
         "citations": [{"fact_id": "ec-budget:actions:3"}]},
        {"requirement_id": "r-result", "status": "supported",
         "citations": [{"fact_id": "ec-budget:results:3"}]},
    ], preferred=["ec-budget"])

    markdown, claims, assessment = _render_selection(views, report)
    statuses = {row["requirement_id"]: row["resume_status"] for row in assessment["requirements"]}
    assert statuses == {"r-action": "supported", "r-result": "supported"}
    assert results[3] in markdown
    action_claims = [c for c in claims if c.get("fact_id", "").startswith("ec-budget:actions:")]
    result_claims = [c for c in claims if c.get("fact_id", "").startswith("ec-budget:results:")]
    assert len(action_claims) <= 3
    assert len(result_claims) <= 2
    assert any(c["fact_id"] == "ec-budget:results:3" and c["text"] == results[3] for c in result_claims)


def test_semantic_selection_does_not_lock_to_initial_cards_or_fill_background_slots(tmp_path):
    preferred = ["ec-early-a", "ec-early-b", "ec-early-c"]
    cards = [_selection_project(card_id, actions=[
        "设计并发事务的处理边界", "构建分布式状态恢复机制", "建立容量测试与性能复核流程",
    ]) for card_id in preferred]
    exact = "实现外部结算回执的独立核对"
    cards.append(_selection_project("ec-later", actions=[exact]))
    views, base = _selection_sources(tmp_path, cards)
    report = _selection_report(base, [
        {"requirement_id": "r1", "status": "supported",
         "citations": [{"fact_id": "ec-later:actions:0"}]},
    ], preferred=preferred)

    markdown, claims, assessment = _render_selection(views, report)
    assert assessment["requirements"][0]["resume_status"] == "supported"
    assert _claimed_projects(claims)[0] == "ec-later"
    assert len(_claimed_projects(claims)) <= 2  # One cited project and at most one background.
    assert markdown.count("\n### ") <= 3
    exact_claim, = [c for c in claims if c.get("fact_id") == "ec-later:actions:0"]
    assert exact_claim["text"] == exact


@pytest.mark.parametrize("same_check", [False, True], ids=["different-children", "joint-citations"])
def test_semantic_selection_keeps_required_fact_complements(tmp_path, same_check):
    values = ["在隔离环境中完成恢复机制验收", "在隔离环境中完成一致性核对验收"]
    cards = [_selection_project(card_id, results=[value])
             for card_id, value in zip(("ec-left", "ec-right"), values)]
    views, base = _selection_sources(tmp_path, cards)
    citations = [{"fact_id": "ec-left:results:0"}, {"fact_id": "ec-right:results:0"}]
    checks = ([{"requirement_id": "r1.c1", "status": "supported", "citations": citations}]
              if same_check else [
                  {"requirement_id": "r1.c1", "status": "supported", "citations": citations[:1]},
                  {"requirement_id": "r1.c2", "status": "supported", "citations": citations[1:]},
              ])
    report = _selection_report(base, [
        {"requirement_id": "r1", "status": "supported", "checks": checks},
    ])

    markdown, claims, assessment = _render_selection(views, report)
    assert assessment["requirements"][0]["resume_status"] == "supported"
    assert all(row["resume_status"] == "supported" for row in assessment["requirements"][0]["checks"])
    assert set(_claimed_projects(claims)) == {"ec-left", "ec-right"}
    for citation, value in zip(citations, values):
        assert value in markdown
        assert any(c.get("fact_id") == citation["fact_id"] and c["text"] == value for c in claims)

def test_semantic_selection_caps_each_parent_despite_distinct_child_references(tmp_path):
    dense = _selection_project("ec-dense", actions=[
        "实现事务事件的恢复机制", "建立异常状态的一致性校验",
    ])
    broad = _selection_project("ec-broad", actions=[
        "完成结算回执的独立核对", "建立跨系统验收的交付流程",
    ])
    views, base = _selection_sources(tmp_path, [dense, broad])
    report = _selection_report(base, [
        {"requirement_id": "r1", "status": "supported", "checks": [
            {"requirement_id": "r1.c1", "status": "supported",
             "citations": [{"fact_id": "ec-dense:actions:0"}]},
            {"requirement_id": "r1.c2", "status": "supported",
             "citations": [{"fact_id": "ec-dense:actions:1"}]},
        ]},
        {"requirement_id": "r2", "status": "supported",
         "citations": [{"fact_id": "ec-broad:actions:0"}]},
        {"requirement_id": "r3", "status": "supported",
         "citations": [{"fact_id": "ec-broad:actions:1"}]},
    ])

    _, claims, assessment = _render_selection(views, report)
    assert _claimed_projects(claims)[0] == "ec-broad"  # Two parents contribute 2 + 2; r1 contributes at most 2.
    assert assessment["all_requirements_supported"] is True


def test_semantic_selection_uses_each_parent_strength_not_fact_global_maximum(tmp_path):
    text = "实现业务回执的独立核对机制"
    views, base = _selection_sources(tmp_path, [
        _selection_project("ec-mixed", actions=[text]),
        _selection_project("ec-full", actions=[text]),
    ])
    report = _selection_report(base, [
        {"requirement_id": "r1", "status": "supported", "citations": [{"fact_id": "ec-mixed:actions:0"}]},
        {"requirement_id": "r2", "status": "partial", "citations": [{"fact_id": "ec-mixed:actions:0"}]},
        {"requirement_id": "r3", "status": "supported", "citations": [{"fact_id": "ec-full:actions:0"}]},
        {"requirement_id": "r4", "status": "supported", "citations": [{"fact_id": "ec-full:actions:0"}]},
    ])

    _, claims, assessment = _render_selection(views, report)
    assert _claimed_projects(claims)[0] == "ec-full"  # 2 + 2 outranks 2 + 1, despite equal Fact maxima.
    assert {row["requirement_id"]: row["resume_status"] for row in assessment["requirements"]} == {
        "r1": "supported", "r2": "partial", "r3": "supported", "r4": "supported",
    }


def test_semantic_selection_limits_projects_without_claiming_omitted_requirement(tmp_path):
    card_ids = ["ec-first", "ec-second", "ec-third", "ec-fourth"]
    views, base = _selection_sources(tmp_path, [
        _selection_project(card_id, actions=[text]) for card_id, text in zip(card_ids, [
            "实现事件恢复的处理流程", "建立异常回执的核对机制",
            "完成发布状态的独立验收", "构建跨系统交付的复核流程",
        ])
    ])
    report = _selection_report(base, [
        {"requirement_id": f"r{index}", "status": "supported",
         "citations": [{"fact_id": card_id + ":actions:0"}]}
        for index, card_id in enumerate(card_ids)
    ])

    markdown, claims, assessment = _render_selection(views, report)
    assert _claimed_projects(claims) == card_ids[:3]
    assert markdown.count("\n### ") == 3
    assert [row["resume_status"] for row in assessment["requirements"]] == [
        "supported", "supported", "supported", "not_present",
    ]


@pytest.mark.parametrize("both_required", [False, True], ids=["cited-identity", "missing-joint-proof"])
def test_semantic_selection_deduplicates_text_without_borrowing_occurrence_credit(tmp_path, both_required):
    text = "实现外部回执的独立核对流程"
    cards = [_selection_project(card_id, actions=[text]) for card_id in ("ec-source-a", "ec-source-b")]
    for card in cards:
        card["project_key"] = "共同验证项目"
    views, base = _selection_sources(tmp_path, cards)
    required = (["ec-source-a:actions:0", "ec-source-b:actions:0"]
                if both_required else ["ec-source-b:actions:0"])
    report = _selection_report(base, [
        {"requirement_id": "r1", "status": "supported", "checks": [
            {"requirement_id": "r1.c1", "status": "supported",
             "citations": [{"fact_id": fact_id} for fact_id in required]},
        ]},
    ])

    markdown, claims, assessment = _render_selection(views, report)
    actual = [claim for claim in claims if claim.get("field") == "actions"]
    assert len(actual) == 1
    assert actual[0]["text"] == text
    assert text in markdown.splitlines()[actual[0]["render_line"] - 1]
    if both_required:
        assert actual[0]["fact_id"] in required
        assert assessment["requirements"][0]["resume_status"] == "not_present"
    else:
        assert actual[0]["fact_id"] == "ec-source-b:actions:0"
        assert assessment["requirements"][0]["resume_status"] == "supported"


def test_semantic_action_budget_keeps_new_parent_before_more_same_parent_quotes(tmp_path):
    actions = [
        "实现事件恢复的处理流程", "建立异常状态的校验机制",
        "构建回执重试的隔离流程", "完成跨系统验收的独立核对",
    ]
    views, base = _selection_sources(tmp_path, [_selection_project("ec-parent-budget", actions=actions)])
    report = _selection_report(base, [
        {"requirement_id": "r1", "status": "supported", "checks": [
            {"requirement_id": f"r1.c{index}", "status": "supported",
             "citations": [{"fact_id": f"ec-parent-budget:actions:{index}"}]}
            for index in range(3)
        ]},
        {"requirement_id": "r2", "status": "partial",
         "citations": [{"fact_id": "ec-parent-budget:actions:3"}]},
    ])

    _, claims, assessment = _render_selection(views, report)
    chosen = {claim["fact_id"] for claim in claims if claim.get("field") == "actions"}
    assert chosen == {"ec-parent-budget:actions:0", "ec-parent-budget:actions:1", "ec-parent-budget:actions:3"}
    assert {row["requirement_id"]: row["resume_status"] for row in assessment["requirements"]} == {
        "r1": "partial", "r2": "partial",
    }
    assert [check["resume_status"] for check in assessment["requirements"][0]["checks"]] == [
        "supported", "supported", "not_present",
    ]
