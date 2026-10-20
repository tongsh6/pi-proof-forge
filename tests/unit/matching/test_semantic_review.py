"""语义评审必须遍历全部卡片并拒绝无来源的结论。"""
import copy
import importlib
import json

import pytest


def engine():
    return importlib.import_module('tools.engines.matching.semantic_review')


def fixtures():
    cards = [{'id': 'e1', 'facts': ['e1:results:0']}, {'id': 'e2', 'facts': ['e2:actions:0']}]
    facts = {
        'e1:results:0': {'source_id': 'e1', 'field': 'results', 'text': '实现多实例任务抢占与故障恢复'},
        'e2:actions:0': {'source_id': 'e2', 'field': 'actions', 'text': '编写接口开发文档'},
    }
    requirements = [{'id': 'r1', 'text': 'Distributed system reliability', 'kind': 'must_have'}]
    return cards, facts, requirements


def citation():
    return {'fact_id': 'e1:results:0', 'quote': '实现多实例任务抢占与故障恢复'}


def replies(cards):
    return {'cards': [{'id': c['id'], 'score': 90 if c['id'] == 'e1' else 0,
                      'reason': '有可靠性实践' if c['id'] == 'e1' else '未见相关证据',
                      'requirement_ids': ['r1'] if c['id'] == 'e1' else [],
                      'citations': [citation()] if c['id'] == 'e1' else []} for c in cards]}


def test_semantic_card_can_match_without_literal_keyword():
    cards, facts, requirements = fixtures()
    rows = engine().validate_cards(replies(cards), cards, facts, requirements)
    assert rows[0]['score'] == 90


def test_missing_citation_diagnostic_identifies_all_positive_cards_and_requirements():
    cards,facts,requirements=fixtures()
    response=replies(cards)
    for row in response["cards"]:
        row.update(score=20,requirement_ids=["r1"],citations=[])
    with pytest.raises(ValueError,match="semantic_support_requires_citation:cards=e1,e2"):
        engine().validate_cards(response,cards,facts,requirements)
    requirements.append({"id":"r2","text":"接口开发","kind":"must_have"})
    assessments={"assessments":[{"requirement_id":r["id"],"status":"partial","reason":"部分相关","citations":[]}
                                for r in requirements]}
    with pytest.raises(ValueError,match="semantic_support_requires_citation:requirements=r1,r2"):
        engine().validate_assessments(assessments,facts,requirements)

@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'unknown', 'wrong_card', 'fabricated_quote', 'unknown_requirement', 'bad_score'])
def test_recall_rejects_invalid_or_incomplete_model_response(fault):
    cards, facts, requirements = fixtures()
    response = replies(cards)
    if fault == 'missing': response['cards'].pop()
    if fault == 'duplicate': response['cards'][1] = copy.deepcopy(response['cards'][0])
    if fault == 'unknown': response['cards'][0]['id'] = 'unknown'
    if fault == 'wrong_card': response['cards'][0]['citations'] = [{'fact_id': 'e2:actions:0', 'quote': '编写接口开发文档'}]
    if fault == 'fabricated_quote': response['cards'][0]['citations'][0]['quote'] = '领导 500 人团队'
    if fault == 'unknown_requirement': response['cards'][0]['requirement_ids'] = ['r9']
    if fault == 'bad_score': response['cards'][0]['score'] = True
    with pytest.raises(ValueError): engine().validate_cards(response, cards, facts, requirements)


def test_requirement_judgment_needs_real_citation_and_complete_coverage():
    _, facts, requirements = fixtures()
    good = {'assessments': [{'requirement_id': 'r1', 'status': 'supported', 'reason': '存在故障恢复实践', 'citations': [citation()]}]}
    assert engine().validate_assessments(good, facts, requirements)[0]['status'] == 'supported'
    for bad in [{'assessments': []}, {'assessments': [{**good['assessments'][0], 'citations': []}]},
                {'assessments': [{**good['assessments'][0], 'status': 'qualified'}]}]:
        with pytest.raises(ValueError): engine().validate_assessments(bad, facts, requirements)


def test_invalid_quote_diagnostic_identifies_the_fact_for_bounded_repair():
    _, facts, _ = fixtures()
    with pytest.raises(ValueError, match='semantic_quote_not_in_source:e1:results:0'):
        engine().validate_citations([{'fact_id':'e1:results:0','quote':'编造的业绩结果'}], facts)
    with pytest.raises(ValueError, match='semantic_quote_too_short:e1:results:0'):
        engine().validate_citations([{'fact_id':'e1:results:0','quote':'故障恢复'}], facts)


def test_unknown_fact_diagnostic_identifies_mistyped_id_for_bounded_repair():
    with pytest.raises(ValueError, match=r'^semantic_unknown_fact:mistyped-card:results:0$'):
        engine().validate_citations([{'fact_id':'mistyped-card:results:0','quote':'实现多实例任务抢占与故障恢复'}], {})


def test_wrong_source_diagnostic_identifies_fact_and_expected_card_for_repair():
    _, facts, _ = fixtures()
    with pytest.raises(ValueError, match=r'^semantic_wrong_source:e2:actions:0:expected=e1$'):
        engine().validate_citations([{'fact_id':'e2:actions:0','quote':'编写接口开发文档'}], facts, 'e1')


def test_pool_support_does_not_imply_resume_contains_the_fact():
    _, facts, requirements = fixtures()
    review = {'facts': facts, 'requirements': requirements,
              'assessments': [{'requirement_id': 'r1', 'status': 'supported', 'reason': '可靠性实践', 'citations': [citation()]}]}
    claims = [{'source_kind': 'evidence', 'evidence_id': 'e2', 'field': 'actions', 'text': '编写接口开发文档'}]
    result = engine().resume_assessment(review, claims)
    assert result['requirements'][0]['resume_status'] == 'not_present'
    assert result['fit_score'] == 100 and result['resume_score'] == 0
    claims.append({'source_kind': 'evidence', 'evidence_id': 'e1', 'field': 'results', 'text': facts['e1:results:0']['text']})
    assert engine().resume_assessment(review, claims)['resume_score'] == 100


def test_resume_presentation_preserves_whitespace_normalized_source_quote():
    _, facts, requirements = fixtures()
    facts['e1:results:0']['text'] = '实现多实例任务抢占\n与故障恢复'
    review = {'facts': facts, 'requirements': requirements, 'assessments': [{'requirement_id': 'r1', 'status': 'supported',
               'reason': '恢复实践', 'citations': [{'fact_id': 'e1:results:0', 'quote': facts['e1:results:0']['text']}]}]}
    claims = [{'source_kind': 'evidence', 'evidence_id': 'e1', 'field': 'results', 'text': '实现多实例任务抢占 与故障恢复'}]
    assert engine().resume_assessment(review, claims)['resume_score'] == 100


def test_selected_cards_prioritize_the_actual_requirement_citations():
    reviews = [{'id': f'e{i}', 'score': 100-i} for i in range(5)]
    facts = {'e4:results:0': {'source_id': 'e4', 'field': 'results', 'text': '实现恢复'}}
    assessments = [{'status': 'supported', 'citations': [{'fact_id': 'e4:results:0', 'quote': '实现恢复'}]}]
    assert engine().select_cards(reviews, assessments, facts)[0] == 'e4'


def test_final_selection_does_not_fill_three_slots_with_uncited_projects():
    reviews=[{'id':'current','score':75},{'id':'old','score':30},{'id':'older','score':20}]
    facts={'f':{'source_id':'current','field':'results','text':'平台复用有记录'}}
    assessments=[{'requirement_id':'r1','status':'supported','citations':[{'fact_id':'f','quote':'平台复用有记录'}]}]
    assert engine().select_cards(reviews,assessments,facts)==['current']


def test_all_cards_batched_and_cached_without_rule_prefilter(tmp_path,monkeypatch):
    infra = importlib.import_module('tools.infra.semantic_matching')
    job = tmp_path / 'jp.yaml'
    job.write_text('target_role: "后端"\nmust_have:\n  - "Distributed system reliability"\nkeywords:\n  - "Distributed"\n')
    paths = []
    for index in range(5):
        p = tmp_path / f'e{index}.yaml'
        p.write_text(f'id: "e{index}"\ntitle: "恢复方案"\nrole_scope: "核心开发者"\nresults:\n  - "实现多实例任务抢占与故障恢复"\nartifacts:\n  - "报告"\n')
        paths.append(p)

    class Client:
        chat_completions_url = 'http://localhost/v1/chat/completions'
        calls = []
        requests = []

        def post_json(self, url, payload, **kwargs):
            data = json.loads(payload['messages'][1]['content'])
            self.requests.append(payload)
            key = 'cards' if data['stage'] == 'recall' else 'assessments'
            expected_count = len(data['cards'] if key == 'cards' else data['requirements'])
            assert kwargs['response_schema']['properties'][key]['minItems'] == expected_count
            assert kwargs['response_schema']['properties'][key]['maxItems'] == expected_count
            assert payload['max_tokens'] <= 6144
            self.calls.append(data)
            if data['stage'] == 'recall':
                response = {'cards': []}
                for card in data['cards']:
                    fact_id = next(k for k in card['facts'] if ':results:' in k)
                    response['cards'].append({'id': card['id'], 'score': 90, 'reason': '可靠性相关', 'requirement_ids': ['r1'],
                                              'citations': [{'fact_id': fact_id, 'quote': data['facts'][fact_id]['text']}]})
                    if getattr(self, 'zero_ready', False) and card['id'] == 'e4':
                        response['cards'][-1].update(score=0, reason='不满足其他岗位要求', requirement_ids=[], citations=[])
            else:
                if getattr(self,'expected_preferred',None):
                    assert data['preferred_source_ids']==self.expected_preferred
                    assert data['facts']['e4:role_scope:0']['text']=='核心开发者'
                fact_id = 'e4:results:0' if getattr(self, 'zero_ready', False) else next(k for k in data['facts'] if ':results:' in k)
                response = {'assessments': [{'requirement_id': 'r1', 'status': 'supported', 'reason': '存在恢复实践',
                                             'citations': [{'fact_id': fact_id, 'quote': data['facts'][fact_id]['text']}]}]}
            return {'choices': [{'message': {'content': json.dumps(response)}}]}

        @staticmethod
        def extract_content(response): return response['choices'][0]['message']['content']

    client = Client()
    options = dict(job_path=job, evidence_files=paths, personal_profile=None, client=client, model='test',
                   cache_dir=tmp_path / 'cache', batch_size=2)
    result = infra.run_semantic_matching(**options)
    assert result['reviewed_card_ids'] == [f'e{i}' for i in range(5)]
    assert len(client.calls) == 4
    assert len([c for d in client.calls if d['stage'] == 'recall' for c in d['cards']]) == 5
    report = tmp_path / 'matching.yaml'
    infra.write_semantic_report(report, result)
    assert infra.load_semantic_report(report)['fit_score'] == 100
    original_report = report.read_text()
    report.write_text(original_report.replace('matching_mode: "semantic"', 'matching_mode: "rule"'))
    with pytest.raises(ValueError, match='semantic_report_changed'):
        infra.load_semantic_report(report)
    report.write_text(original_report)
    # 已有全输入指纹缓存按相同旧输入校验后迁移，无需重新调用。
    from tools.prompts.context import context_fingerprint
    first_cache = next(p for p in (tmp_path / 'cache').glob('*.json')
                       if json.loads(p.read_text()).get('cards', [{}])[0].get('id') == 'e0')
    legacy_key = infra._sha(infra._json({'version': infra.VERSION, 'task_context': context_fingerprint(),
        'url': client.chat_completions_url, 'request': client.requests[0],
        'input_fingerprints': {key: value['sha256'] for key, value in result['inputs'].items()}}).encode())
    (tmp_path / 'cache' / f'{legacy_key}.json').write_text(first_cache.read_text())
    first_cache.unlink()
    repeated = infra.run_semantic_matching(**options)
    assert len(client.calls) == 4 and repeated['statistics']['cache_hits'] == 4
    assert first_cache.exists()
    paths[0].write_text(paths[0].read_text().replace('报告', '新报告'))
    infra.run_semantic_matching(**options)
    assert len(client.calls) == 6  # 变更卡所在粗筛批次和逐项评审失效，其余两批复用。
    job.write_text(job.read_text().replace('reliability', 'reliability and scale'))
    with pytest.raises(ValueError, match='semantic_input_changed'):
        infra.load_semantic_report(report)
    infra.run_semantic_matching(**options)
    assert len(client.calls) == 10

    # App 使用已确认档案时仍评审全部卡，但只选可完整归属的代表项目。
    from tools.infra.career_profile import empty_career, inspect_career
    pool=tmp_path/'evidence_cards';pool.mkdir()
    paths[-1].write_text(paths[-1].read_text()+'context: "恢复方案开发"\nrole_scope: "核心开发者"\ntime_range: "2021-02 ~ 2021-03"\nactions:\n  - "实现故障恢复"\n')
    for path in paths:
        raw=path.read_text()
        if path!=paths[-1]:raw=raw.replace('role_scope: "核心开发者"\n','')
        (pool/path.name).write_text(raw+'status: "saved_eligible"\ncandidate_pool_eligible: "true"\n')
    career=empty_career();career.update(education_visibility='omit',work=[{'id':'w','company':'任职公司','title':'工程师','start':'2020-01','end':'2022-01','current':False,'scope':'系统开发','contributions':['恢复方案'],'evidence_ids':[path.stem for path in paths]}],skills=[{'id':'s','category':'恢复','description':'故障恢复','evidence_ids':[paths[-1].stem]}])
    fields={'name':'测试','phone':'123','email':'test@example.com','city':'上海','current_position':'工程师','career_json':json.dumps(career)}
    checked=inspect_career(fields,pool);fields['career_review_json']=json.dumps({'revision':checked['revision']})
    profile=tmp_path/'personal_profile.yaml';profile.write_text('\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in fields.items()))
    client.expected_preferred=['e4']
    app_result=infra.run_semantic_matching(**{**options,'personal_profile':profile,'evidence_files':sorted(pool.glob('*.yaml'))})
    assert len(app_result['reviewed_card_ids'])==5
    assert app_result['selected_card_ids']==['e4']
    assert '待补本人职责' in app_result['presentation_exclusions']['e0']
    calls_before_profile_change = len(client.calls)
    profile.write_text(profile.read_text() + '\n')
    profile_updated = infra.run_semantic_matching(**{**options, 'personal_profile': profile,
                                                     'evidence_files': sorted(pool.glob('*.yaml'))})
    assert len(client.calls) - calls_before_profile_change == 1
    assert profile_updated['statistics']['cache_hits'] == 3
    from tools.prompts import context
    monkeypatch.setattr(context,"JOB_SEARCH_CONTEXT",context.JOB_SEARCH_CONTEXT+"\n更新产品语境")
    updated=infra.run_semantic_matching(**{**options,'personal_profile':profile,'evidence_files':sorted(pool.glob('*.yaml'))})
    assert updated['statistics']['model_calls']==4
    assert updated['statistics']['cache_hits']==0
    client.zero_ready = True
    client.expected_preferred = None
    recovered = infra.run_semantic_matching(**{**options, 'model': 'zero-recall', 'personal_profile': profile,
                                               'evidence_files': sorted(pool.glob('*.yaml'))})
    assert recovered['selected_card_ids'] == ['e4']
    assert next(row for row in recovered['card_reviews'] if row['id'] == 'e4')['score'] == 0


def test_required_llm_invalid_semantic_output_does_not_publish_success(tmp_path, monkeypatch):
    from tools import run_matching_scoring
    from tools.infra.llm.client import LLMClient
    job = tmp_path / 'job.yaml'
    job.write_text('target_role: "后端"\ncompany: "Test"\nkeywords:\n  - "恢复能力"\n')
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    (evidence / 'e1.yaml').write_text('title: "恢复"\nresults:\n  - "完成恢复方案"\nartifacts:\n  - "报告"\n')
    output = tmp_path / 'report.yaml'
    monkeypatch.setattr(LLMClient, 'post_json', lambda *args, **kwargs: {'choices': [{'message': {'content': '{"cards":[]}'}}]})
    monkeypatch.setattr('sys.argv', ['match', '--job-profile', str(job), '--evidence-dir', str(evidence), '--output', str(output),
                                   '--use-llm', '--require-llm', '--model', 'test', '--api-key', 'local'])
    assert run_matching_scoring._legacy_main() == 1
    assert not output.exists()


@pytest.mark.parametrize('always_invalid', [False, True])
@pytest.mark.parametrize('fault', ['invalid_quote','missing_citations'])
def test_invalid_quote_gets_only_one_validated_repair(tmp_path, always_invalid, fault):
    infra = importlib.import_module('tools.infra.semantic_matching')
    job = tmp_path/'job.yaml'
    job.write_text('target_role: "恢复能力"\nkeywords:\n  - "故障恢复"\n')
    evidence = tmp_path/'e1.yaml'
    evidence.write_text('title: "恢复实践"\nresults:\n  - "实现多实例任务抢占与故障恢复"\nartifacts:\n  - "报告"\n')
    class Client:
        chat_completions_url = 'http://localhost/v1/chat/completions'
        calls = 0
        def post_json(self, url, payload, **kwargs):
            self.calls += 1
            data = json.loads(payload['messages'][1]['content'])
            bad=always_invalid or self.calls==1
            cite = {'fact_id':'e1:results:0','quote': '不存在的结果' if bad and fault=='invalid_quote' else '实现多实例任务抢占与故障恢复'}
            citations=[] if bad and fault=='missing_citations' else [cite]
            if self.calls==2 and fault=='missing_citations':
                assert 'cards=e1' in payload['messages'][-1]['content']
                assert 'score=0' in payload['messages'][-1]['content']
            if data['stage'] == 'recall':
                response={'cards':[{'id':'e1','score':90,'reason':'故障恢复','requirement_ids':['r1'],'citations':citations}]}
            else:
                response={'assessments':[{'requirement_id':'r1','status':'supported','reason':'故障恢复','citations':citations}]}
            return {'choices':[{'message':{'content':json.dumps(response)}}]}
        @staticmethod
        def extract_content(response): return response['choices'][0]['message']['content']
    client=Client()
    options=dict(job_path=job,evidence_files=[evidence],personal_profile=None,client=client,model='test',cache_dir=tmp_path/'cache')
    if always_invalid:
        code='semantic_quote_not_in_source' if fault=='invalid_quote' else 'semantic_support_requires_citation'
        with pytest.raises(ValueError, match=code):
            infra.run_semantic_matching(**options)
        assert client.calls == 2
        assert not list((tmp_path/'cache').glob('*.json'))
    else:
        result=infra.run_semantic_matching(**options)
        assert client.calls == 3
        assert result['statistics']['repair_calls'] == 1


def test_presentation_prefers_complete_facts_without_changing_pool_assessment():
    reviews=[{'id':'incomplete','score':98},{'id':'ready','score':80},{'id':'unrelated','score':0}]
    facts={'incomplete:results:0':{'source_id':'incomplete','field':'results','text':'发布治理规则'}}
    assessments=[{'status':'supported','citations':[{'fact_id':'incomplete:results:0','quote':'发布治理规则'}]}]
    selected=engine().select_cards(reviews,assessments,facts,eligible_ids={'ready','unrelated'})
    assert selected==['ready']
    assert assessments[0]['status']=='supported'
    assert engine().resume_assessment({'facts':facts,'requirements':[{'id':'r1','text':'发布治理'}],
        'assessments':[{'requirement_id':'r1',**assessments[0]}]},[])['requirements'][0]['resume_status']=='not_present'


def test_positive_requirement_evidence_can_recover_zero_recall_card():
    facts = {'zero:results:0': {'source_id': 'zero', 'field': 'results', 'text': '已完成故障恢复'}}
    reviews = [{'id': 'zero', 'score': 0}, {'id': 'irrelevant', 'score': 0}]
    assessed = [{'status': 'partial', 'citations': [{'fact_id': 'zero:results:0', 'quote': '已完成故障恢复'}]}]
    assert engine().select_cards(reviews, assessed, facts, eligible_ids={'zero', 'irrelevant'}) == ['zero']
    assert engine().select_cards(reviews, assessed, facts, eligible_ids={'irrelevant'}) == []


def test_confirmed_personal_achievements_are_facts_without_employer_attribution(tmp_path,monkeypatch):
    infra=importlib.import_module('tools.infra.semantic_matching')
    from tools.infra.career_profile import empty_career
    profile=tmp_path/'personal_profile.yaml'
    # 本测试仅隔离档案加载；确认状态与成果内容通过原有接口进入事实表。
    career=empty_career();career['extras']=[{'id':'dsh','title':'个人开源 Harness','description':'个人独立开发验证循环，不代表公司生产使用','url':'https://example.com/project'}]
    data={'career':career,'career_status':{'reviewed':True}}
    profile.write_text('name: "测试"')
    monkeypatch.setattr(infra,'load_career_profile',lambda _:data)
    facts=infra._profile_facts(profile)
    key='personal_profile:career.extras.dsh.description:0'
    assert facts[key]['text']=='个人独立开发验证循环，不代表公司生产使用'
    assert not any('career.work' in k for k in facts)
    assert facts[key]['field']=='career.extras.dsh.description'
    data['career_status']['reviewed']=False
    assert infra._profile_facts(profile)=={}


@pytest.mark.parametrize('requirement,reason',[
 ('本科及以上学历，软件工程相关专业','本科满足学历，但约12年，未达10年硬门槛。'),
 ('10年以上研发，其中3年以上负责人经验','研发12年，负责人4年，未达3年要求。'),
 ('有真实 Agent 项目实践','有个人Agent项目，但缺乏企业级真实生产项目经验。'),
])
def test_assessment_rejects_contradictory_numbers_or_invented_production_gate(requirement,reason):
    _,facts,_=fixtures()
    response={'assessments':[{'requirement_id':'r1','status':'partial','reason':reason,'citations':[citation()]}]}
    with pytest.raises(ValueError,match='semantic_(numeric_contradiction|added_requirement)'):
        engine().validate_assessments(response,facts,[{'id':'r1','text':requirement}])


def test_assessment_allows_real_shortfall_and_explicit_production_requirement():
    _,facts,_=fixtures()
    for requirement,reason in [('3年以上负责人经验','研发12年，负责人2年，不足3年要求。'),
                               ('具备企业级生产系统经验','个人项目，但缺乏企业级真实生产项目经验。')]:
        response={'assessments':[{'requirement_id':'r1','status':'partial','reason':reason,'citations':[citation()]}]}
        assert engine().validate_assessments(response,facts,[{'id':'r1','text':requirement}])[0]['status']=='partial'


def test_reuse_revalidates_previously_published_invalid_assessment(tmp_path):
    infra=importlib.import_module('tools.infra.semantic_matching')
    _,facts,_=fixtures()
    result={'method':infra.VERSION,'inputs':{},'job_profile_id':'job','fit_score':50,'facts':facts,
        'requirements':[{'id':'r1','text':'3年以上负责人经验'}],
        'assessments':[{'requirement_id':'r1','status':'partial','reason':'负责人4年，未达3年要求。','citations':[citation()]}],
        'reviewed_card_ids':[],'selected_card_ids':[],'card_reviews':[]}
    report=tmp_path/'report.yaml';infra.write_semantic_report(report,result)
    with pytest.raises(ValueError,match='semantic_numeric_contradiction'):infra.load_semantic_report(report)


@pytest.mark.parametrize('requirement,reason',[
 ('10年以上研发且3年以上负责人经验','研发12年，负责人经验不足3年。'),
 ('有真实Agent项目与团队管理经验','缺少团队管理证据，但个人项目已用于生产。'),
 ('三年以上负责人经验','负责人2年，不足3年要求。'),
])
def test_assessment_guard_does_not_cross_subjects_clauses_or_guess_chinese_threshold(requirement,reason):
    _,facts,_=fixtures()
    response={'assessments':[{'requirement_id':'r1','status':'partial','reason':reason,'citations':[citation()]}]}
    assert engine().validate_assessments(response,facts,[{'id':'r1','text':requirement}])[0]['status']=='partial'


def test_missing_assessment_status_uses_repairable_value_error():
    _,facts,requirements=fixtures()
    with pytest.raises(ValueError,match='semantic_invalid_status'):
        engine().validate_assessments({'assessments':[{'requirement_id':'r1','reason':'待核对','citations':[citation()]}]},facts,requirements)
