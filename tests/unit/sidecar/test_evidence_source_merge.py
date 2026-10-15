import hashlib
import json
import pytest
from tools.sidecar.handlers import evidence, materials
from tools.infra.persistence.yaml_io import parse_simple_yaml

META = {'correlation_id': 'source-merge-test'}


@pytest.fixture
def sample(tmp_path, monkeypatch):
    root = tmp_path / 'materials'; root.mkdir()
    cards = tmp_path / 'evidence_cards'
    monkeypatch.setattr(materials, '_MATERIALS_DIR', root)
    monkeypatch.setattr(evidence, '_EVIDENCE_DIR', cards)
    texts = {'m1': '# Source: 统一平台/设计.md\n平台复用预约能力。\n模块验收通过。',
             'm2': '# Source: 职业底稿.md\n统一平台\n服务周期：2022 – 至今\n角色：Tech Lead，平台架构设计与核心开发\n个人建立 Feature 交付机制。'}
    refs = []
    for mid, text in texts.items():
        (root / f'{mid}.txt').write_text(text)
        (root / f'{mid}.meta.yaml').write_text(f'material_id: "{mid}"\nfilename: "{mid}.txt"\nextension: ".txt"\nlabel: "{mid}"\n')
        d = evidence.handle_list_material_documents({'material_id': mid})['items'][0]
        refs.append({'material_id': mid, **{k: d[k] for k in ('document_id', 'sha256', 'label')}})
    draft = {'source_material_ids': ['m1'], 'source_documents': refs[:1], 'title': '统一平台', 'time_range': '',
             'context': '统一预约平台', 'role_scope': '', 'actions': '平台复用预约能力。', 'results': '模块验收通过。',
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
    from tools import run_generation
    from tools.infra.persistence.review_snapshot import read_generation_trace
    output = root.parent / 'generated'; staged = root.parent / 'staged'; staged.mkdir()
    (staged / path.name).write_bytes(path.read_bytes())
    profile = root.parent / 'personal_profile.yaml'; profile.write_text('name: "测试"\n')
    report = root.parent / 'matching.yaml'; report.write_text(f'top_cards:\n  - id: "{path.stem}"\n')
    monkeypatch.setattr('sys.argv', ['generate', '--matching-report', str(report), '--evidence-dir', str(staged),
                                   '--personal-profile', str(profile), '--output-dir', str(output)])
    assert run_generation._legacy_main() == 0
    md = output / 'resume_matching_A.md'
    trace, valid = read_generation_trace(md)
    assert valid
    assert str((root / 'm2.txt').resolve()) in [v['path'] for v in trace['inputs'].values()]
    (root / 'm2.txt').write_text('材料已变更')
    assert read_generation_trace(md)[1] is False
    assert run_generation._legacy_main() != 0


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
    from tools.infra.semantic_matching import run_semantic_matching, validate_inputs
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
