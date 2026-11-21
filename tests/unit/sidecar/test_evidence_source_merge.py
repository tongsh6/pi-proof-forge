import hashlib
import json
import pytest
from tools.sidecar.handlers import evidence, materials
from tools.infra.persistence.yaml_io import parse_simple_yaml

META = {'correlation_id': 'source-merge-test'}


@pytest.fixture
def sample(tmp_path, monkeypatch, request):
    root = tmp_path / 'materials'; root.mkdir()
    cards = tmp_path / 'evidence_cards'
    monkeypatch.setattr(materials, '_MATERIALS_DIR', root)
    monkeypatch.setattr(evidence, '_EVIDENCE_DIR', cards)
    action, result = getattr(request, 'param', ('平台复用预约能力。', '模块验收通过。'))
    texts = {'m1': f'# Source: 统一平台/设计.md\n{action}\n{result}',
             'm2': '# Source: 职业底稿.md\n统一平台\n服务周期：2022 – 至今\n角色：Tech Lead，平台架构设计与核心开发\n个人建立 Feature 交付机制。'}
    refs = []
    for mid, text in texts.items():
        (root / f'{mid}.txt').write_text(text)
        (root / f'{mid}.meta.yaml').write_text(f'material_id: "{mid}"\nfilename: "{mid}.txt"\nextension: ".txt"\nlabel: "{mid}"\n')
        d = evidence.handle_list_material_documents({'material_id': mid})['items'][0]
        refs.append({'material_id': mid, **{k: d[k] for k in ('document_id', 'sha256', 'label')}})
    draft = {'source_material_ids': ['m1'], 'source_documents': refs[:1], 'title': '统一平台', 'time_range': '',
             'context': '统一预约平台', 'role_scope': '', 'actions': action, 'results': result,
             'stack': ['Java'], 'tags': [], 'artifacts': [{'type': 'text_document', 'ref': 'm1', 'label': '设计'}]}
    params = {'meta': META, 'review': {'decision': 'approved'}, 'save_mode': 'eligible'}
    eid = evidence.handle_evidence_save_draft({**params, 'draft': draft})['evidence_id']
    path = cards / f'{eid}.yaml'
    draft = {**draft, 'source_material_ids': ['m1', 'm2'], 'source_documents': refs,
             'time_range': '2022 – 至今', 'role_scope': 'Tech Lead，平台架构设计与核心开发',
             'field_sources': [{'field': field, 'value': value, 'quote': value, 'material_id': 'm2', 'document_id': refs[1]['document_id']}
                              for field, value in [('time_range', '2022 – 至今'), ('role_scope', 'Tech Lead，平台架构设计与核心开发')]]}
    merged = {**params, 'evidence_id': eid, 'expected_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'review': {'decision': 'approved', 'merge_sources': True}, 'draft': draft}
    return root, path, merged


def test_rereview_appends_sources_and_reads_field_provenance(sample):
    root, path, params = sample
    before = parse_simple_yaml(path.read_text())['scalars']['created_at']
    evidence.handle_evidence_save_draft(params)
    detail = evidence.handle_evidence_get({'meta': META, 'evidence_id': path.stem})['evidence']
    assert detail['source_documents'] == params['draft']['source_documents']
    assert detail['field_sources'] == params['draft']['field_sources']
    assert detail['time_range'] == '2022 – 至今'
    assert detail['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert parse_simple_yaml(path.read_text())['scalars']['created_at'] == before
    # 再次普通复审和编辑不能因多个来源失效，也不能丢失字段依据。
    params['expected_sha256'] = detail['source_sha256']; params['review'].pop('merge_sources')
    evidence.handle_evidence_save_draft(params)
    evidence.handle_evidence_update({'meta': META, 'evidence_id': path.stem, 'patch': {'title': '统一平台架构'}})
    saved = evidence.handle_evidence_get({'meta': META, 'evidence_id': path.stem})['evidence']
    assert saved['field_sources'] == detail['field_sources']
    assert saved['candidate_pool_eligible'] is False


@pytest.mark.parametrize('change,error', [
    ('stale', 'evidence_review_changed'), ('quote', 'field_source'), ('missing', 'field_source'),
    ('role', 'field_source'), ('drop', 'evidence_review_source_mismatch'), ('source', 'material_document_changed'),
])
def test_invalid_merge_does_not_write(sample, change, error):
    root, path, params = sample; before = path.read_bytes()
    if change == 'stale': params['expected_sha256'] = 'old'
    elif change == 'quote': params['draft']['field_sources'][0]['quote'] = '虚构履历'
    elif change == 'missing': params['draft']['field_sources'] = []
    elif change == 'role': params['draft']['role_scope'] = '独立负责所有前端与后端'
    elif change == 'drop': params['draft']['source_documents'] = params['draft']['source_documents'][1:]
    elif change == 'source': (root / 'm2.txt').write_text('已变更材料')
    with pytest.raises(ValueError, match=error): evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before


def test_source_change_revokes_new_merged_card_eligibility(sample):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    (root / 'm2.txt').write_text('已变更材料')
    row = evidence.handle_evidence_list({'meta': META})['items'][0]
    assert row['candidate_pool_eligible'] is False
    from tools.infra.career_profile import eligible_cards_for_linking
    assert eligible_cards_for_linking(path.parent) == []


def test_ordinary_edit_cannot_launder_unbound_facts_on_rereview(sample):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    invented = '拥有未经材料证实的大规模金融核心平台'
    evidence.handle_evidence_update({'meta': META, 'evidence_id': path.stem, 'patch': {'context': invented}})
    params['draft']['context'] = invented
    params['expected_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    before = path.read_bytes()
    with pytest.raises(ValueError, match='field_source_required'):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before


@pytest.mark.parametrize('already_merged', [False, True])
def test_review_baseline_survives_first_edit_and_removal_of_all_bindings(sample, already_merged):
    root,path,params=sample
    if already_merged:
        evidence.handle_evidence_save_draft(params)
        params['draft'].update(role_scope='',time_range='',field_sources=[])
        params['expected_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        evidence.handle_evidence_save_draft(params)
        params['review'].pop('merge_sources')
    invented='没有来源的个人交付业绩'
    evidence.handle_evidence_update({'meta':META,'evidence_id':path.stem,'patch':{'context':invented}})
    params['draft']['context']=invented
    params['expected_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='field_source_required'):
        evidence.handle_evidence_save_draft(params)


def test_adding_precise_quote_keeps_old_whole_material_result_scope(sample):
    root, path, params = sample
    # 旧卡成果来自同材料另一文档；补角色不能缩窄它原有的整份来源。
    combined = (root/'m1.txt').read_text() + '\n# Source: 统一平台/角色.md\n本人负责核心架构。'
    (root/'m1.txt').write_text(combined)
    draft = {**params['draft'], 'source_material_ids':['m1'], 'source_documents':[], 'field_sources':[], 'role_scope':'', 'time_range':''}
    eid = evidence.handle_evidence_save_draft({'meta':META,'draft':draft,'review':{'decision':'approved'},'save_mode':'eligible'})['evidence_id']
    target = path.parent/(eid+'.yaml')
    d = evidence.handle_list_material_documents({'material_id':'m1','query':'角色'})['items'][0]
    ref = {'material_id':'m1',**{k:d[k] for k in ('document_id','sha256','label')}}
    draft.update(source_documents=[ref],role_scope='本人负责核心架构。',field_sources=[{'field':'role_scope','value':'本人负责核心架构。','quote':'本人负责核心架构。','material_id':'m1','document_id':d['document_id']}])
    p = {'meta':META,'draft':draft,'evidence_id':eid,'expected_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'review':{'decision':'approved','merge_sources':True},'save_mode':'eligible'}
    evidence.handle_evidence_save_draft(p)
    p['expected_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(p)
    assert evidence.handle_evidence_get({'meta':META,'evidence_id':eid})['evidence']['candidate_pool_eligible']
    doc=parse_simple_yaml(target.read_text())
    text,_=evidence._reconcile_source_text(doc['scalars'],doc['lists'],evidence._reconcile_material_documents())
    assert '模块验收通过。' in text


def test_source_fingerprints_invalidate_confirmed_career(sample):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    from tools.infra.career_profile import inspect_career
    career = {'schema_version': 1, 'education_visibility': 'omit', 'education': [], 'extras': [],
              'work': [{'id': 'w', 'company': '测试公司', 'title': 'Tech Lead', 'start': '2021-03', 'current': True,
                        'scope': '统一平台', 'contributions': ['核心开发'], 'evidence_ids': [path.stem]}],
              'skills': [{'id': 's', 'category': '平台', 'description': '架构', 'evidence_ids': [path.stem]}]}
    fields = {k: 'test' for k in ['name', 'phone', 'email', 'city', 'current_position']}
    fields['career_json'] = json.dumps(career)
    old = inspect_career(fields, path.parent)
    fields['career_review_json'] = json.dumps({'revision': old['revision']})
    assert inspect_career(fields, path.parent)['career_status']['reviewed']
    (root / 'm2.txt').write_text('已变更材料')
    current = inspect_career(fields, path.parent)
    assert not current['career_status']['reviewed']
    assert current['revision'] != old['revision']


def test_generation_trace_binds_original_materials_for_staged_cards(sample, monkeypatch):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    from tools.cli.commands import generate as generate_cli
    from tools.infra.persistence.review_snapshot import read_generation_trace
    output = root.parent / 'generated'; staged = root.parent / 'staged'; staged.mkdir()
    (staged / path.name).write_bytes(path.read_bytes())
    profile = root.parent / 'personal_profile.yaml'; profile.write_text('name: "测试"\n')
    report = root.parent / 'matching.yaml'; report.write_text(f'top_cards:\n  - id: "{path.stem}"\n')
    monkeypatch.setattr('sys.argv', ['generate', '--matching-report', str(report), '--evidence-dir', str(staged),
                                   '--personal-profile', str(profile), '--output-dir', str(output)])
    assert generate_cli.main() == 0
    md = output / 'resume_matching_A.md'
    trace, valid = read_generation_trace(md)
    assert valid
    assert str((root / 'm2.txt').resolve()) in [v['path'] for v in trace['inputs'].values()]
    (root / 'm2.txt').write_text('材料已变更')
    assert read_generation_trace(md)[1] is False
    assert generate_cli.main() != 0


def test_quick_run_rejects_merged_card_when_material_changed(sample):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    from tools.sidecar.handlers.agent import _load_eligible_evidence_card
    assert _load_eligible_evidence_card(path)['evidence_id'] == path.stem
    (root / 'm2.txt').write_text('材料已变更')
    with pytest.raises(ValueError, match='material_source'):
        _load_eligible_evidence_card(path)


def test_semantic_report_binds_merged_sources_before_model_calls(sample):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    from tools.engines.matching.semantic_matching import run_semantic_matching, validate_inputs
    job = root.parent / 'job.yaml'; job.write_text('target_role: "平台"\nmust_have:\n  - "模块验收"\n')
    cite = {'fact_id': path.stem + ':results:0', 'quote': '模块验收通过。'}
    class Client:
        chat_completions_url = 'http://localhost/unused'
        calls = 0
        def post_json(self, url, body, **kwargs):
            self.calls += 1
            stage = json.loads(body['messages'][-1]['content'])['stage']
            return ({'cards': [{'id': path.stem, 'score': 80, 'reason': '验收有记录', 'requirement_ids': ['r1'], 'citations': [cite]}]}
                    if stage == 'recall' else {'assessments': [{'requirement_id': 'r1', 'status': 'supported', 'reason': '验收有记录', 'citations': [cite]}]})
        def extract_content(self, response): return json.dumps(response)
    client = Client()
    args = dict(job_path=job, evidence_files=[path], personal_profile=None, client=client, model='test', cache_dir=root.parent/'cache')
    report = run_semantic_matching(**args)
    assert str((root/'m2.txt').resolve()) in [v['path'] for v in report['inputs'].values()]
    (root/'m2.txt').write_text('材料变更'); calls = client.calls
    with pytest.raises(ValueError): validate_inputs(report['inputs'])
    with pytest.raises(ValueError): run_semantic_matching(**args)
    assert client.calls == calls


def _scoped_review(sample):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    params['review'].pop('merge_sources')
    params['expected_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    m1 = params['draft']['source_documents'][0]
    val = params['draft']['actions']
    source = {k:m1[k] for k in ('material_id','document_id','sha256')}
    params['draft']['field_sources'].append({'field':'actions','value':val,'quote':val,
                                          'material_id':m1['material_id'],'document_id':m1['document_id']})
    directive={'kind':'adopt','field':'actions','index':0,'value':val,'source':{**source,'quote':val},
               'attribution':'self','target':'预约能力','environment':'test','implementation':'implemented','release':'not_released'}
    return root,path,params,directive


def _live_scope(path):
    return evidence.handle_evidence_get({'meta': META,'evidence_id':path.stem})['evidence']['fact_scope_review']


@pytest.fixture
def repeated_scope(sample):
    root, path, params = sample
    value = "P95 从 200 ms 降至 120 ms。"
    params["draft"]["actions"] = value
    ref = params["draft"]["source_documents"][0]
    params["draft"]["field_sources"].append({
        "field": "actions", "value": value, "quote": value,
        "material_id": ref["material_id"], "document_id": ref["document_id"],
    })
    return _scoped_review(sample)


@pytest.mark.parametrize("sample", [
    ("容量规划：预计 P95 从 200 ms 降至 120 ms。", "测试环境实测：P95 从 200 ms 降至 120 ms。"),
], indirect=True)
def test_scope_requires_unique_source_context_without_rejecting_ordinary_binding(repeated_scope):
    _, path, params, scope = repeated_scope
    # 普通摘录仍可保存；它没有授予某一具体语境的状态。
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path) == []
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    params["review"]["fact_scope"] = scope
    before = path.read_bytes()
    with pytest.raises(ValueError, match="fact_scope_source_not_unique"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before

    # 唯一的原文上下文只解决定位，不把既有 scope 解释成测量核定。
    quote = params["draft"]["results"]
    for binding in params["draft"]["field_sources"]:
        if binding["field"] == "actions":
            binding["quote"] = quote
    scope["source"]["quote"] = quote
    evidence.handle_evidence_save_draft(params)
    stored, = _live_scope(path)
    assert stored["sources"][0]["quote"] == quote
    assert stored["environment"] == "test"
    assert stored["release"] == "not_released"

    # 两份文档各有唯一相同原句，不应跨文档误判为重复。
    root = path.parent.parent / "materials"
    (root / "m3.txt").write_text(quote)
    (root / "m3.meta.yaml").write_text('material_id: "m3"\nfilename: "m3.txt"\nextension: ".txt"\nlabel: "独立核验"\n')
    document, = evidence.handle_list_material_documents({"material_id": "m3"})["items"]
    ref = {"material_id": "m3", **{k: document[k] for k in ("document_id", "sha256", "label")}}
    params["draft"]["source_material_ids"].append("m3")
    params["draft"]["source_documents"].append(ref)
    params["draft"]["artifacts"].append({"type": "text_document", "ref": "m3", "label": "独立核验"})
    params["draft"]["field_sources"].append({
        "field": "actions", "value": scope["value"], "quote": quote,
        "material_id": "m3", "document_id": ref["document_id"],
    })
    params["review"] = {"decision": "approved", "merge_sources": True}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    params["review"] = {"decision": "approved", "fact_scope": {
        **scope, "source": {**{k: ref[k] for k in ("material_id", "document_id", "sha256")}, "quote": quote},
    }}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    stored, = _live_scope(path)
    assert {source["material_id"] for source in stored["sources"]} == {"m1", "m3"}


@pytest.mark.parametrize("sample", [
    ("容量规划：预计 P95 从 200 ms 降至 120 ms。", "测试环境实测：P95 从 200 ms 降至 120 ms。"),
], indirect=True)
@pytest.mark.parametrize("resolution", ["revoke", "adopt"])
def test_ambiguous_saved_scope_requires_explicit_recovery_without_losing_sibling(repeated_scope, resolution):
    from tools.engines.generation.resume_renderer import load_cards, load_all_cards
    from tools.infra.evidence_fact_scope import nonpersonal_reviewed_fact_ids, personal_claim_exclusions
    from tools.infra.evidence_sources import validated_source_inputs
    from tools.infra.persistence.yaml_io import dump_yaml

    root, path, params, scope = repeated_scope
    quote = params["draft"]["results"]
    params["draft"]["field_sources"].append({
        "field": "results", "value": quote, "quote": quote,
        **{k: scope["source"][k] for k in ("material_id", "document_id")},
    })
    evidence.handle_evidence_save_draft(params)
    # 复现旧版本留下的含糊范围，另保留同卡独立、唯一的兄弟范围。
    doc = parse_simple_yaml(path.read_text())
    snapshot = json.loads(doc["scalars"]["reviewed_facts_json"])
    old = {k: v for k, v in scope.items() if k != "kind"}
    sibling = {**old, "field": "results", "value": quote, "target": "测试指标",
               "source": {**old["source"], "quote": quote}, "attribution": "teammate"}
    snapshot["fact_scope_v1"] = [old, sibling]
    doc["scalars"]["reviewed_facts_json"] = json.dumps(snapshot, ensure_ascii=False)
    path.write_text(dump_yaml(doc["scalars"], doc["lists"]))
    before = path.read_bytes()
    params["expected_sha256"] = hashlib.sha256(before).hexdigest()

    detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert detail["source_error"] == "fact_scope_source_not_unique"
    assert detail["fact_scope_review"] == []
    assert detail["candidate_pool_eligible"] is False
    for load in (lambda: load_cards(path.parent, [path.stem], root),
                 lambda: load_all_cards(path.parent, root),
                 lambda: personal_claim_exclusions(doc, root, card_id=path.stem),
                 lambda: nonpersonal_reviewed_fact_ids(doc, root, card_id=path.stem,
                     validated_sources=validated_source_inputs(doc, root))):
        with pytest.raises(ValueError, match="fact_scope_source_not_unique"):
            load()
    with pytest.raises(ValueError, match="fact_scope_source_not_unique"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before

    if resolution == "revoke":
        params["review"]["fact_scope"] = {
            "kind": "revoke", **{k: scope[k] for k in ("field", "index", "value")},
        }
    else:
        for binding in params["draft"]["field_sources"]:
            if binding["field"] == "actions":
                binding["quote"] = quote
        # 换成较长引文不能借普通复审静默清除原范围。
        with pytest.raises(ValueError, match="fact_scope_unverifiable"):
            evidence.handle_evidence_save_draft(params)
        assert path.read_bytes() == before
        params["review"]["fact_scope"] = {**scope, "source": {**scope["source"], "quote": quote}}
    evidence.handle_evidence_save_draft(params)
    rows = _live_scope(path)
    assert any(row["field"] == "results" and row["attribution"] == "teammate" for row in rows)
    assert len(rows) == (1 if resolution == "revoke" else 2)


def test_exact_source_scope_requires_explicit_review_and_supports_revoke(sample):
    root,path,params,scope = _scoped_review(sample)
    params['draft']['field_sources'][-1]['fake_scope'] = scope
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path) == []
    params['expected_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    params['review']['fact_scope'] = scope
    evidence.handle_evidence_save_draft(params)
    stored, = _live_scope(path)
    assert stored['fact_id'] == f'{path.stem}:actions:0'
    assert stored['attribution'] == 'self' and 'subject' not in stored
    assert stored['implementation']=='implemented' and stored['release']=='not_released' and stored['environment']=='test'
    params['expected_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    params['review']['fact_scope'] = {k:scope[k] for k in ('field','index','value')} | {'kind':'revoke'}
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path) == []
    assert evidence.handle_evidence_get({'meta':META,'evidence_id':path.stem})['evidence']['field_sources']


@pytest.mark.parametrize("fault", ["missing_revision","stale","unbound","duplicate","contradictory","unknown_release_environment","draft_injection","source_drift","missing_attribution","invalid_attribution","free_text_subject"])
def test_invalid_fact_scope_review_changes_no_evidence(sample,fault):
    root,path,params,scope = _scoped_review(sample)
    params['review']['fact_scope']=scope
    if fault=="missing_revision":del params['expected_sha256']
    if fault=="stale":params['expected_sha256']='invalid'
    if fault=="unbound":scope['source']['sha256']='1'*64
    if fault=="duplicate":params['draft']['actions']+='\n'+scope['value']
    if fault=="contradictory":scope.update(implementation='planned',release='released')
    if fault=="unknown_release_environment":scope["environment"]="unknown"
    if fault=="draft_injection":params['draft']['fact_scope']=params['review'].pop('fact_scope')
    if fault=="source_drift":(root/'m1.txt').write_text('different')
    if fault=="missing_attribution":scope.pop('attribution')
    if fault=="invalid_attribution":scope['attribution']='本人'
    if fault=="free_text_subject":scope['subject']=scope.pop('attribution')
    before=path.read_bytes()
    with pytest.raises(ValueError):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes()==before


def test_scope_conflict_keeps_both_sources_and_revoke_keeps_sibling(sample):
    root,path,params,adopt = _scoped_review(sample)
    m1=params['draft']['source_documents'][0]
    v=adopt['value']; sibling='模块验收通过。'
    def existing_source(mid, implementation):
        quote=f'测试环境：本人负责复用预约能力。{v}实施状态：{implementation}。'
        (root/f'{mid}.txt').write_text(quote)
        (root/f'{mid}.meta.yaml').write_text(f'material_id: "{mid}"\nfilename: "{mid}.txt"\nextension: ".txt"\nlabel: "{mid}"\n')
        doc,=evidence.handle_list_material_documents({'material_id':mid})['items']
        ref={'material_id':mid,**{k:doc[k] for k in ('document_id','sha256','label')}}
        params['draft']['source_documents'].append(ref)
        params['draft']['source_material_ids'].append(mid)
        params['draft']['artifacts'].append({'type':'text_document','ref':mid,'label':mid})
        params['draft']['field_sources'].append({'field':'actions','value':v,'quote':quote,
                                                 'material_id':mid,'document_id':ref['document_id']})
        return {k:ref[k] for k in ('material_id','document_id','sha256')} | {'quote':quote}
    yes=existing_source('m3','已实现')
    no=existing_source('m4','明确未实现')
    params['draft']['field_sources'].append({'field':'results','value':sibling,'quote':sibling,
                                             'material_id':m1['material_id'],'document_id':m1['document_id']})
    params['review']['merge_sources']=True
    evidence.handle_evidence_save_draft(params)
    params['review'].pop('merge_sources')
    def save_scope(proposal):
        params['expected_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        params['review']['fact_scope'] = proposal
        evidence.handle_evidence_save_draft(params)
    adopt['attribution'] = 'team_lead'
    save_scope({**adopt, 'source':yes})
    save_scope({**adopt, 'source':no, 'implementation':'not_implemented','release':'unknown'})
    save_scope({**adopt,'field':'results','index':0,'value':sibling,
                'source':{**adopt['source'],'quote':sibling},'target':'模块验收','attribution':'teammate','environment':'test',
                'implementation':'implemented','release':'unknown'})
    conflict,peer = _live_scope(path)
    assert conflict['attribution']=='team_lead'
    assert conflict['implementation']=='conflict' and len(conflict['sources'])==2
    assert {r['implementation'] for r in conflict['sources']} == {'implemented','not_implemented'}
    assert peer['attribution']=='teammate' and peer['release']=='unknown'
    # The same implementation slot cannot positively present both candidate and teammate.
    # Independent overall leadership and the teammate's other result are not conflicting.
    save_scope({**adopt, 'source':yes, 'attribution':'self'})
    save_scope({**adopt, 'source':no, 'attribution':'teammate'})
    from tools.infra.evidence_fact_scope import nonpersonal_reviewed_fact_ids
    from tools.infra.evidence_sources import validated_source_inputs

    def match_limits():
        doc = parse_simple_yaml(path.read_text())
        return nonpersonal_reviewed_fact_ids(doc, root, card_id=path.stem,
            validated_sources=validated_source_inputs(doc, root))

    assert match_limits() == {f"{path.stem}:actions:0", f"{path.stem}:results:0"}
    save_scope({**adopt, 'attribution':'team_lead', 'implementation':'unknown','release':'unknown'})
    rows = _live_scope(path)
    opposed, = [row for row in rows if row['attribution']=='conflict']
    assert {r['attribution'] for r in opposed['sources']} == {'self','teammate'}
    # A valid separately reviewed lead scope keeps the action from receiving
    # a global negative label; the exact teammate-only sibling stays restricted.
    assert match_limits() == {f"{path.stem}:results:0"}
    assert opposed['implementation'] == opposed['release'] == 'unknown'
    assert any(row['attribution']=='team_lead' and row['field']=='actions' for row in rows)
    assert any(row==peer for row in rows)
    save_scope({'kind':'revoke','field':'actions','index':0,'value':v})
    kept, = _live_scope(path)
    assert kept == peer
    assert match_limits() == {f"{path.stem}:results:0"}
    (root/'m1.txt').write_text('source-mutation')
    assert _live_scope(path) == []


def test_generic_edit_pending_scope_does_not_resurface_in_ordinary_reapproval(sample):
    _,path,params,scope = _scoped_review(sample)
    params['review']['fact_scope']=scope
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path)
    evidence.handle_evidence_update({'meta':META,'evidence_id':path.stem,'patch':{'title':'已修改标题'}})
    assert _live_scope(path)==[]
    params['expected_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    del params['review']['fact_scope']
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path)==[]


@pytest.mark.parametrize('sample', [('实现会员时间轴页面并接入平台已有接口。','完成预约能力的测试验收，覆盖改期流程。')], indirect=True)
def test_reviewed_page_does_not_inherit_project_role_in_plan_or_preview(sample):
    from tools.engines.generation.fact_index import build_fact_index
    from tools.engines.generation.fact_selector import select_facts
    from tools.engines.generation.resume_plan import build_resume_plan
    from tools.engines.generation.resume_renderer import load_cards, load_all_cards
    from tools.engines.matching.semantic_matching import _facts
    from tools.engines.matching.semantic_review import job_requirements, requirement_checks, aggregate_assessments
    from tools.sidecar.handlers import preparation_preview as preview

    root,path,params,scope = _scoped_review(sample)
    unsigned = build_fact_index(load_cards(path.parent, [path.stem], root))
    assert path.stem + ':actions:0' in build_resume_plan(unsigned, select_facts(unsigned), {}).fact_ids
    scope = {**scope, 'attribution':'teammate'}
    params['review']['fact_scope'] = scope
    evidence.handle_evidence_save_draft(params)
    action_id = path.stem + ':actions:0'
    result_id = path.stem + ':results:0'
    for cards in (load_cards(path.parent, [path.stem], root), load_all_cards(path.parent, root)):
        index = build_fact_index(cards)
        selection = select_facts(index)
        plan = build_resume_plan(index, selection, {})
        assert index.get(action_id) is None, 'scoped quote inherited the project role'
        assert index.get(result_id) is not None
        assert action_id not in plan.fact_ids

    job = root.parent/'jp_test.yaml'
    job.write_text('company: TestCo\ntarget_role: Engineer\n')
    facts = _facts(path.stem, parse_simple_yaml(path.read_text()))
    requirements = job_requirements(['平台开发'])
    checks = requirement_checks(requirements)
    assessed = [{"requirement_id":checks[0]["id"],"status":"supported","reason":"有引文",
                 "citations":[{"fact_id":fid,"quote":facts[fid]["text"]} for fid in (action_id,result_id)]}]
    raw = {"job_profile_id":"jp_test","method":preview.VERSION,"advisory_scope":True,
           "requirements":requirements,"requirement_checks":checks,"criterion_assessments":assessed,
           "assessments":aggregate_assessments(requirements,checks,assessed),"completed_check_ids":[checks[0]["id"]],
           "facts":facts}
    inputs = {"evidence_files":[path],"personal_profile":root.parent/'personal.yaml',"job_path":job,
              "direction":{"status":"needs_review"},"pool":{}}
    excerpt = preview.render_reviewed_excerpt('jp_test',inputs,raw)
    assert action_id not in [c["fact_id"] for c in excerpt["claims"]]
    assert result_id in [c["fact_id"] for c in excerpt["claims"]]
    assert action_id in raw["facts"]
    original = path.read_text()
    path.write_text(original.replace(f'id: "{path.stem}"', 'id: "ec_other"', 1))
    assert parse_simple_yaml(path.read_text())['scalars']['id'] == 'ec_other'
    with pytest.raises(ValueError, match='fact_scope_card_identity_mismatch'):
        load_cards(path.parent, [path.stem], root)
    path.write_text(original)
    (root/'m1.txt').write_text('材料变更')
    with pytest.raises(ValueError, match='material_document_changed|material_source_changed'):
        preview.render_reviewed_excerpt('jp_test',inputs,raw)


def test_unclassified_prior_scope_keeps_exact_veto_until_explicit_review(sample):
    from tools.engines.generation.fact_index import build_fact_index
    from tools.engines.generation.resume_renderer import load_cards
    from tools.infra.persistence.yaml_io import dump_yaml

    root, path, params, typed = _scoped_review(sample)
    params['review']['fact_scope'] = typed
    evidence.handle_evidence_save_draft(params)

    # Emulate the preceding release's stored snapshot, not a public authoring route.
    doc = parse_simple_yaml(path.read_text())
    scalars = doc['scalars']
    snapshot = json.loads(scalars['reviewed_facts_json'])
    old, = snapshot['fact_scope_v1']
    old.pop('attribution')
    old['subject'] = '同组同事'
    # The same exact occurrence is otherwise all teammate-only across environments.
    # An older unclassified source-bound row must not be mistaken as reviewed attribution.
    valid_peer_rows = [{k:v for k,v in old.items() if k != 'subject'} |
                       {'attribution':'teammate', 'environment':env} for env in ('test','production')]
    scalars['reviewed_facts_json'] = json.dumps(snapshot, ensure_ascii=False)
    path.write_text(dump_yaml(scalars, doc['lists']))
    legacy = path.read_bytes()
    fid = f'{path.stem}:actions:0'

    def projection():
        index = build_fact_index(load_cards(path.parent, [path.stem], root))
        return index.get(fid)

    assert _live_scope(path) == []
    assert projection() is None
    assert path.read_bytes() == legacy
    from tools.infra.evidence_fact_scope import nonpersonal_reviewed_fact_ids
    from tools.infra.evidence_sources import validated_source_inputs
    mixed = {**doc, 'scalars':{**scalars, 'reviewed_facts_json':json.dumps(
        {**snapshot,'fact_scope_v1':[old,*valid_peer_rows]}, ensure_ascii=False)}}
    assert not nonpersonal_reviewed_fact_ids(mixed, root, card_id=path.stem,
        validated_sources=validated_source_inputs(mixed, root))
    assert path.read_bytes() == legacy
    params['expected_sha256'] = hashlib.sha256(legacy).hexdigest()
    del params['review']['fact_scope']
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path) == []
    assert projection() is None  # ordinary card review cannot silently lift the existing veto

    params['expected_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    params['review']['fact_scope'] = {**typed, 'attribution':'team_lead',
                                     'environment':'unknown','implementation':'unknown','release':'unknown'}
    evidence.handle_evidence_save_draft(params)
    confirmed, = _live_scope(path)
    assert confirmed['attribution'] == 'team_lead'
    assert confirmed['implementation'] == confirmed['release'] == 'unknown'
    assert projection() is None  # typed attribution is representation only, not generator admission
    current = parse_simple_yaml(path.read_text())
    persisted, = json.loads(current['scalars']['reviewed_facts_json'])['fact_scope_v1']
    assert persisted['attribution'] == 'team_lead' and 'subject' not in persisted
    params['expected_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    params['review']['fact_scope']['attribution'] = 'contributor'
    evidence.handle_evidence_save_draft(params)
    corrected, = _live_scope(path)
    assert corrected['attribution'] == 'contributor'
    assert projection() is None


@pytest.mark.parametrize("sample", [
    ("实现预约接口的幂等重试。", "完成预约能力的测试验收，覆盖改期流程。"),
], indirect=True)
@pytest.mark.parametrize("relation,other,mixed,advisory,negative,expected", [
    ("teammate", None, False, False, True, "insufficient"),
    ("teammate", None, True, True, True, "partial"),
    ("team_lead", None, False, False, False, "supported"),
    ("self", None, False, True, False, "supported"),
    ("teammate", "teammate", False, False, True, "insufficient"),
    ("teammate", "teammate", True, True, True, "partial"),
    ("self", "teammate", False, True, False, "supported"),
    ("teammate", "unknown", False, True, False, "supported"),
])
def test_matching_never_credits_teammate_only_occurrence(sample, monkeypatch, relation, other, mixed, advisory, negative, expected):
    import io
    from tools.domain.assessment_support import positive_citations
    from tools.engines.matching import semantic_matching as engine
    from tools.engines.matching.semantic_review import resume_assessment
    from tools.infra.llm.bounded_local import BoundedLocalClient
    from tools.sidecar.handlers import preparation_semantic as semantic

    root,path,params,scope = _scoped_review(sample)
    params["review"]["fact_scope"] = {**scope, "attribution": relation}
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path)[0]["attribution"] == relation
    if other:
        params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        params["review"]["fact_scope"] = {**scope, "attribution": other,
            "environment": "production", "release": "unknown" if other == "unknown" else "released"}
        evidence.handle_evidence_save_draft(params)
        assert {(row["attribution"],row["environment"]) for row in _live_scope(path)} == {
            (relation,"test"),(other,"production")}
    fid, sibling = f"{path.stem}:actions:0", f"{path.stem}:results:0"
    job = root.parent/"job.yaml"
    job.write_text('target_role: "Engineer"\nmust_have:\n  - "平台开发"\n')
    replies = []
    client = BoundedLocalClient(model="synthetic", api_key="")
    class FixedTransport:
        def open(self, req, **kwargs):
            data = json.loads(json.loads(req.data)["messages"][1]["content"])
            replies.append((data["stage"], data["facts"][fid].get("candidate_support")))
            if data["stage"] == "recall":
                result = {"cards":[{"id":path.stem,"score":70,"reason":"项目语境相关",
                                    "requirement_ids":["r1"],"citations":[{"fact_id":fid}]}]}
            else:
                ids = [fid,sibling] if mixed else [fid]
                result = {"assessments":[{"requirement_id":r["id"],"status":"supported","reason":"有证据",
                                          "citations":[{"fact_id":k,"candidate_support":k==fid and negative} for k in ids]}
                                         for r in data["requirements"]]}
            return io.BytesIO(json.dumps({"choices":[{"message":{"content":json.dumps(result)},"finish_reason":"stop"}]}).encode())
    client._opener = FixedTransport()
    report = engine.run_semantic_matching(job_path=job, evidence_files=[path], personal_profile=None,
               client=client, model="synthetic", cache_dir=root.parent/"cache", advisory=advisory)
    assert [stage for stage,_ in replies] == ["recall","assess"]
    repeated = engine.run_semantic_matching(job_path=job, evidence_files=[path], personal_profile=None,
               client=client, model="synthetic", cache_dir=root.parent/"cache", advisory=advisory)
    assert repeated["criterion_assessments"] == report["criterion_assessments"]
    assert len(replies) == 2

    assert replies[-1][1] is (False if negative else None)
    if not advisory:
        output = root.parent/"report.yaml"
        engine.write_semantic_report(output,report)
        report = engine.load_semantic_report(output)
    row, = report["assessments"]
    assert row["status"] == expected
    cited = {k["fact_id"]:k for k in row["checks"][0]["citations"]}
    assert cited[fid].get("candidate_support") is (False if negative else None)
    assert [c["fact_id"] for c,_ in positive_citations(row)] == (
        [sibling] if mixed else [] if negative else [fid])
    if advisory:
        from tools.sidecar.handlers.preparation_preview import render_reviewed_excerpt

        profile = root.parent/"personal_profile.yaml"
        inputs = {"direction":{}, "evidence_files":[path], "pool":{}, "personal_profile":profile, "job_path":job}
        projected = semantic._safe_summary(job.stem,inputs,client,report,"")
        audit = root.parent/"audit.json"
        monkeypatch.setattr(semantic, "_audit_path", lambda _: audit)
        semantic._save_audit(audit, {"schema_version":1, "summary":projected, "result":report})
        report = semantic._read_audit_record(job.stem)["result"]
        if mixed:
            excerpt = render_reviewed_excerpt(job.stem,inputs,report)
            assert [c["fact_id"] for c in excerpt["claims"] if c["usage"]=="supported_excerpt"] == [sibling]
        assert next(c for c in projected["assessments"][0]["citations"] if c["fact_id"]==fid).get("candidate_support") == cited[fid].get("candidate_support")
    if mixed:
        from tools.domain.quality_text import render_fact_text
        fact=report["facts"][sibling]
        claim={"fact_id":sibling,"source_kind":"evidence","evidence_id":fact["source_id"],
               "field":fact["field"],"text":render_fact_text(fact["text"]),"render_line":1}
        assert resume_assessment(report,[claim])["requirements"][0]["resume_status"]=="partial"

    if not advisory:
        old = root.parent/"historical.yaml"
        engine.write_semantic_report(old,{**report, "method":"evidence-semantic-v5"})
        with pytest.raises(ValueError, match="semantic_report_changed"):
            engine.load_semantic_report(old)
        path.write_text(path.read_text() + "\n")
        with pytest.raises(ValueError, match="semantic_input_changed"):
            engine.load_semantic_report(output)
