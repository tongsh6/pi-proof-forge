import hashlib
import json
import pytest
from tools.sidecar.handlers import evidence, materials
from tools.infra.persistence.yaml_io import parse_simple_yaml

META = {'correlation_id': 'source-merge-test'}


@pytest.fixture
def result_review_model(monkeypatch):
    """Transport-only substitute; expected semantic verdicts are declared by each test."""
    from types import SimpleNamespace
    from tools.infra.llm.client import LLMClient
    from tools.sidecar.handlers import evidence_draft

    state = {"calls": [], "reply": {"outcome": "unknown", "measurement_quote": None,
             "rationale": "本测试未核定结果语义。"}, "during_call": None}

    def post_json(url, payload):
        state["calls"].append((url, payload))
        if state["during_call"]:
            state["during_call"]()
        reply = state["reply"]
        if callable(reply):
            reply = reply(payload)
        elif isinstance(reply, dict):
            request = json.loads(payload["messages"][-1]["content"])
            reply = {"reviews": [{"review_index": scope["review_index"], **reply}
                                 for scope in request["scopes"]]}
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return {"choices": [{"message": {"content": content}}]}

    client = SimpleNamespace(chat_completions_url="http://127.0.0.1:8000/v1/chat/completions",
                             post_json=post_json, extract_content=LLMClient.extract_content)
    monkeypatch.setattr(evidence, "LLMClient", lambda **kwargs: client)
    monkeypatch.setattr(evidence_draft, "load_llm_config", lambda: {
        "provider": "openai_compatible", "model": "synthetic-result-review",
        "base_url": "http://127.0.0.1:8000/v1", "api_key_for_request": "",
        "timeout": 20, "temperature": 0, "thinking_enabled": False,
    })
    return state


@pytest.fixture
def sample(tmp_path, monkeypatch, request, result_review_model):
    root = tmp_path / 'materials'; root.mkdir(exist_ok=True)
    cards = tmp_path / 'evidence_cards'
    monkeypatch.setattr(materials, '_MATERIALS_DIR', root)
    monkeypatch.setattr(evidence, '_EVIDENCE_DIR', cards)
    actions, results = getattr(request, 'param', (['平台复用预约能力。'], ['模块验收通过。']))
    texts = {'m1': '# Source: 统一平台/设计.md\n' + '\n'.join([*actions, *results]),
             'm2': '# Source: 职业底稿.md\n统一平台\n服务周期：2022 – 至今\n角色：Tech Lead，平台架构设计与核心开发\n个人建立 Feature 交付机制。'}
    refs = []
    for mid, text in texts.items():
        (root / f'{mid}.txt').write_text(text)
        (root / f'{mid}.meta.yaml').write_text(f'material_id: "{mid}"\nfilename: "{mid}.txt"\nextension: ".txt"\nlabel: "{mid}"\n')
        d = evidence.handle_list_material_documents({'material_id': mid})['items'][0]
        refs.append({'material_id': mid, **{k: d[k] for k in ('document_id', 'sha256', 'label')}})
    draft = {'source_material_ids': ['m1'], 'source_documents': refs[:1], 'title': '统一平台', 'time_range': '',
             'context': '统一预约平台', 'role_scope': '', 'actions': actions, 'results': results,
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


@pytest.mark.parametrize("sample", [(["完成统一预约平台复用能力的接口设计与联调。"], ["模块验收通过。"])], indirect=True)
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


def test_semantic_report_binds_merged_sources_before_model_calls(sample, monkeypatch):
    import io

    from tools.infra.llm.client import LLMClient
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    from tools.engines.matching.semantic_matching import run_semantic_matching, validate_inputs
    job = root.parent / 'job.yaml'; job.write_text('target_role: "平台"\nmust_have:\n  - "模块验收"\n')
    cite = {'fact_id': path.stem + ':results:0', 'quote': '模块验收通过。'}
    calls = []

    def open_response(request, **kwargs):
        calls.append(request)
        body = json.loads(request.data)
        stage = json.loads(body['messages'][1]['content'])['stage']
        response = ({'cards': [{'id': path.stem, 'score': 80, 'reason': '验收有记录', 'requirement_ids': ['r1'], 'citations': [cite]}]}
                    if stage == 'recall' else {'assessments': [{'requirement_id': 'r1', 'status': 'supported', 'reason': '验收有记录', 'citations': [cite]}]})
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(response)}}]}).encode())

    monkeypatch.setattr('tools.infra.llm.client.request.urlopen', open_response)
    client = LLMClient('http://localhost/v1', '', provider='openai_compatible')
    args = dict(job_path=job, evidence_files=[path], personal_profile=None, client=client, model='test', cache_dir=root.parent/'cache')
    report = run_semantic_matching(**args)
    assert str((root/'m2.txt').resolve()) in [v['path'] for v in report['inputs'].values()]
    (root/'m2.txt').write_text('材料变更'); previous_calls = len(calls)
    with pytest.raises(ValueError): validate_inputs(report['inputs'])
    with pytest.raises(ValueError): run_semantic_matching(**args)
    assert len(calls) == previous_calls


def _scoped_review(sample, *, field="actions", index=0):
    root, path, params = sample
    evidence.handle_evidence_save_draft(params)
    params['review'].pop('merge_sources')
    params['expected_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    m1 = params['draft']['source_documents'][0]
    val = params['draft'][field][index]
    source = {k:m1[k] for k in ('material_id','document_id','sha256')}
    params['draft']['field_sources'].append({'field':field,'value':val,'quote':val,
                                          'material_id':m1['material_id'],'document_id':m1['document_id']})
    directive={'kind':'adopt','field':field,'index':index,'value':val,'source':{**source,'quote':val},
               'attribution':'self','target':'预约能力','environment':'test','implementation':'implemented','release':'not_released'}
    return root,path,params,directive



def _review_input_snapshot(path, material_dir, *other_paths):
    from tools.infra.evidence_sources import validated_source_inputs

    sources = validated_source_inputs(parse_simple_yaml(path.read_text()), material_dir)
    return {**{str(item.resolve()): hashlib.sha256(item.read_bytes()).hexdigest() for item in (path, *other_paths)},
            **{str(source.resolve()): digest for source, digest in sources.snapshots.values()}}


def test_result_review_fingerprint_aba_cannot_write_a_new_hash_for_old_evidence(
        sample, result_review_model, monkeypatch):
    from tools.sidecar.handlers import evidence_draft

    root, path, params, scope = _scoped_review(sample, field="results")
    params["review"]["fact_scope"] = scope
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "完整交付已经发生。"}
    source = root / "m1.txt"
    before_source, before_card = source.read_bytes(), path.read_bytes()
    fingerprints = evidence_draft.source_fingerprints

    def changed_during_fingerprint(records):
        if not result_review_model["calls"]:
            return fingerprints(records)
        source.write_bytes(before_source + b"\ntransient source bytes\n")
        try:
            return fingerprints(records)
        finally:
            source.write_bytes(before_source)

    monkeypatch.setattr(evidence_draft, "source_fingerprints", changed_during_fingerprint)
    with pytest.raises(ValueError, match="material_source_changed"):
        evidence.handle_evidence_save_draft(params)
    assert source.read_bytes() == before_source
    assert path.read_bytes() == before_card


@pytest.mark.parametrize("sample", [(
    ["预测章节：\n测试环境固定输入下响应时间减半。", "验收章节："],
    ["测试环境固定输入下响应时间减半。"],
)], indirect=True)
@pytest.mark.parametrize("wide_quote", [False, True])
def test_result_review_locates_value_within_its_quote_not_the_whole_document(
        sample, result_review_model, wide_quote):
    root, path, params, scope = _scoped_review(sample, field="results")
    source = evidence.handle_read_material_document({
        "material_id": scope["source"]["material_id"], "document_id": scope["source"]["document_id"]})["text"]
    assert source.count(scope["value"]) == 2
    quote = source if wide_quote else "验收章节：\n" + scope["value"]
    scope["source"]["quote"] = quote
    params["draft"]["field_sources"][-1]["quote"] = quote
    params["review"]["fact_scope"] = scope
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "定位后的完整已发生结果。"}
    before = path.read_bytes()
    if wide_quote:
        with pytest.raises(ValueError, match="result_review_ambiguous_source"):
            evidence.handle_evidence_save_draft(params)
        assert path.read_bytes() == before
    else:
        evidence.handle_evidence_save_draft(params)
        assert _live_scope(path)[0]["sources"][0]["result_review"]["outcome"] == "established"


def _live_scope(path):
    return evidence.handle_evidence_get({'meta': META,'evidence_id':path.stem})['evidence']['fact_scope_review']

@pytest.mark.parametrize("sample, outcome, measurement_quote", [
    ((["整理测试记录。"], ["在隔离测试环境的固定输入下，接口响应时间减半。"]),
     "established", "在隔离测试环境的固定输入下，接口响应时间减半。"),
    ((["记录验收过程。"], ["已交付并被团队采用的故障排查手册。"]),
     "established", None),
    ((["整理评估材料。"], ["已交付容量评估报告；下一阶段目标为每秒 120 次。"]),
     "established", None),
    ((["整理规划。"], ["预计每秒处理 120 次，尚未验证。"]),
     "not_established", None),
    ((["保存记录。"], ["P95 从 200 ms 降至 120 ms。"]),
     "unknown", None),
], indirect=["sample"])
def test_result_review_save_uses_independent_source_and_persists_verdict(
        sample, result_review_model, outcome, measurement_quote):
    from tools.infra import evidence_fact_scope

    root, path, params, scope = _scoped_review(sample, field="results")
    reply = {"outcome": outcome, "measurement_quote": measurement_quote,
             "rationale": "固定测试判定；真实模型能力另走合成 App 验收。"}
    result_review_model["reply"] = reply
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)

    assert len(result_review_model["calls"]) == 1
    _, payload = result_review_model["calls"][0]
    request = json.loads(payload["messages"][-1]["content"])
    assert request["fact"] == {"card_id": path.stem, "field": "results", "index": 0, "value": scope["value"]}
    reviewed_scope, = request["scopes"]
    assert reviewed_scope["source"] == scope["source"] and reviewed_scope["review_index"] == 0
    source_document, = request["documents"]
    assert scope["value"] in source_document["text"]
    assert params["draft"]["actions"][0] in source_document["text"]
    expected_review = {**reply, "basis_sha256": evidence_fact_scope.result_review_basis(request)}
    doc = parse_simple_yaml(path.read_text())
    row, = json.loads(doc["scalars"]["reviewed_facts_json"])["fact_scope_v1"]
    assert row["result_review"] == expected_review
    assert row["value"] == scope["value"]
    assert row["source"] == scope["source"]
    assert _live_scope(path)[0]["sources"][0]["result_review"] == expected_review
    current = evidence_fact_scope.current_result_reviews(doc, root, card_id=path.stem)
    assert bool(current) is (outcome == "established")
    if current:
        assert current[f"{path.stem}:results:0"] == row


@pytest.mark.parametrize("location", ["params", "draft", "review", "scope", "source", "binding", "document"])
@pytest.mark.parametrize("server_field", ["result_review", "basis_sha256"])
def test_result_review_save_rejects_caller_supplied_verdict_without_write(
        sample, result_review_model, location, server_field):
    _, path, params, scope = _scoped_review(sample, field="results")
    params["review"]["fact_scope"] = scope
    target = {"params": params, "draft": params["draft"], "review": params["review"], "scope": scope,
              "source": scope["source"], "binding": params["draft"]["field_sources"][-1],
              "document": params["draft"]["source_documents"][0]}[location]
    target[server_field] = ("0" * 64 if server_field == "basis_sha256" else
                            {"outcome": "established", "measurement_quote": scope["value"],
                             "rationale": "调用者自报"})
    before = path.read_bytes()
    with pytest.raises(ValueError, match="result_review|fact_scope"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before
    assert result_review_model["calls"] == []


@pytest.mark.parametrize("sample", [(
    ["整理字段说明。"],
    ["已交付字段 basis_sha256 与 result_review 的说明手册。"],
)], indirect=True)
def test_result_review_server_field_names_in_source_text_are_ordinary_data(sample, result_review_model):
    _, path, params, scope = _scoped_review(sample, field="results")
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "完整原文记录了说明手册交付。"}
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    assert len(result_review_model["calls"]) == 1
    source, = _live_scope(path)[0]["sources"]
    assert source["quote"] == scope["value"]
    assert source["result_review"]["outcome"] == "established"
    assert len(source["result_review"]["basis_sha256"]) == 64


@pytest.mark.parametrize("failure", [
    "transport", "invalid_json", "duplicate_key", "extra_field", "foreign_quote", "unknown_with_measurement",
    "source_changed", "card_changed",
])
def test_result_review_save_failure_cannot_partially_write(sample, result_review_model, failure):
    root, path, params, scope = _scoped_review(sample, field="results")
    params["review"]["fact_scope"] = scope
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "完整交付成立，但没有已核量化。"}
    if failure == "transport":
        result_review_model["reply"] = TimeoutError("synthetic timeout")
    elif failure == "invalid_json":
        result_review_model["reply"] = "not JSON"
    elif failure == "duplicate_key":
        result_review_model["reply"] = '{"reviews":[{"review_index":0,"outcome":"not_established","outcome":"established","measurement_quote":null,"rationale":"相反重复键"}]}'
    elif failure == "extra_field":
        result_review_model["reply"]["measured"] = True
    elif failure == "foreign_quote":
        result_review_model["reply"]["measurement_quote"] = "另一条结果实测 120。"
    elif failure == "unknown_with_measurement":
        result_review_model["reply"].update(outcome="unknown", measurement_quote=scope["value"])
    before = path.read_bytes()
    if failure == "source_changed":
        source = root / "m1.txt"
        result_review_model["during_call"] = lambda: source.write_text(source.read_text() + "\n源文已修订。")
    elif failure == "card_changed":
        result_review_model["during_call"] = lambda: path.write_bytes(before + b"\n# concurrent edit\n")
    with pytest.raises(ValueError, match="result_review|material_source_changed|evidence_review_changed"):
        evidence.handle_evidence_save_draft(params)
    expected = before + b"\n# concurrent edit\n" if failure == "card_changed" else before
    assert path.read_bytes() == expected

def test_result_review_lifecycle_preserves_only_current_server_authority(sample, result_review_model):
    from tools.infra.evidence_fact_scope import current_result_reviews, personal_claim_exclusions

    root, path, params, scope = _scoped_review(sample, field="results")
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "已完成的非量化交付。"}
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    fid = f"{path.stem}:results:0"

    def current():
        return current_result_reviews(parse_simple_yaml(path.read_text()), root, card_id=path.stem)

    accepted = current()[fid]
    evidence.handle_evidence_update({"meta": META, "evidence_id": path.stem, "patch": {"title": "更清晰的标题"}})
    assert current() == {}
    params["draft"]["title"] = "更清晰的标题"
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    params["review"].pop("fact_scope")
    evidence.handle_evidence_save_draft(params)
    assert current()[fid] == accepted
    assert len(result_review_model["calls"]) == 1

    action = params["draft"]["actions"][0]
    ref = scope["source"]
    params["draft"]["field_sources"].append({"field": "actions", "value": action, "quote": action,
        "material_id": ref["material_id"], "document_id": ref["document_id"]})
    params["review"]["fact_scope"] = {**scope, "field": "actions", "value": action,
                                      "source": {**ref, "quote": action}}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    doc = parse_simple_yaml(path.read_text())
    assert personal_claim_exclusions(doc, root, card_id=path.stem) == {f"{path.stem}:actions:0"}
    assert current()[fid] == accepted and len(result_review_model["calls"]) == 1

    params["review"]["fact_scope"] = {"kind": "revoke", "field": "results", "index": 0, "value": scope["value"]}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    assert current() == {}
    assert any(binding["field"] == "results" for binding in
               json.loads(parse_simple_yaml(path.read_text())["scalars"]["field_sources_json"]))
    params["review"].pop("fact_scope")
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    assert current() == {} and len(result_review_model["calls"]) == 1


@pytest.mark.parametrize("basis_state", ["missing", "stale"])
def test_result_review_old_basis_survives_as_scope_without_credit_until_current_batch(
        sample, result_review_model, basis_state):
    from tools.engines.generation.fact_index import build_fact_index
    from tools.engines.generation.resume_renderer import load_cards
    from tools.infra.evidence_fact_scope import current_result_reviews, result_review_basis
    from tools.infra.persistence.yaml_io import dump_yaml

    root, path, params, first = _scoped_review(sample, field="results")
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "主来源完整记录已完成验收。"}
    params["review"]["fact_scope"] = first
    evidence.handle_evidence_save_draft(params)
    fid = f"{path.stem}:results:0"
    doc = parse_simple_yaml(path.read_text())
    snapshot = json.loads(doc["scalars"]["reviewed_facts_json"])
    original_row, = snapshot["fact_scope_v1"]
    if basis_state == "missing":
        original_row["result_review"].pop("basis_sha256")
    else:
        original_row["result_review"]["basis_sha256"] = "0" * 64
    doc["scalars"]["reviewed_facts_json"] = json.dumps(snapshot, ensure_ascii=False)
    path.write_text(dump_yaml(doc["scalars"], doc["lists"]))

    def assert_no_current_credit():
        current = parse_simple_yaml(path.read_text())
        assert current_result_reviews(current, root, card_id=path.stem) == {}
        visible, = _live_scope(path)
        source, = visible["sources"]
        assert visible["value"] == first["value"] and source["quote"] == first["source"]["quote"]
        assert "result_review" not in source
        index = build_fact_index(load_cards(path.parent, [path.stem], root))
        assert index.get(fid) is None
        assert index.get(f"{path.stem}:actions:0") is not None

    assert_no_current_credit()
    evidence.handle_evidence_update({"meta": META, "evidence_id": path.stem,
                                     "patch": {"title": "保留原事实的新标题"}})
    params["draft"]["title"] = "保留原事实的新标题"
    params["review"] = {"decision": "approved"}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    assert_no_current_credit()
    assert len(result_review_model["calls"]) == 1

    source_text = evidence.handle_read_material_document({
        "material_id": first["source"]["material_id"],
        "document_id": first["source"]["document_id"],
    })["text"]
    second = {**first, "source": {**first["source"], "quote": source_text}}
    params["draft"]["field_sources"].append({
        "field": "results", "value": first["value"], "quote": source_text,
        "material_id": first["source"]["material_id"], "document_id": first["source"]["document_id"],
    })
    params["review"] = {"decision": "approved", "fact_scope": second}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    assert len(result_review_model["calls"]) == 2
    request = json.loads(result_review_model["calls"][-1][1]["messages"][-1]["content"])
    assert len(request["scopes"]) == 2
    assert {row["source"]["quote"] for row in request["scopes"]} == {first["source"]["quote"], source_text}
    assert all("result_review" not in row for row in request["scopes"])
    current_doc = parse_simple_yaml(path.read_text())
    rows = json.loads(current_doc["scalars"]["reviewed_facts_json"])["fact_scope_v1"]
    assert len(rows) == 2 and all(row["result_review"]["basis_sha256"] == result_review_basis(request) for row in rows)
    current = current_result_reviews(current_doc, root, card_id=path.stem)
    assert current[fid]["source"] == first["source"]
    assert current[fid]["result_review"]["outcome"] == "established"


@pytest.mark.parametrize("failure", ["missing_second", "invalid_second"])
def test_result_review_batch_failure_keeps_first_row_and_entire_card_unchanged(
        sample, result_review_model, failure):
    from tools.infra.evidence_fact_scope import current_result_reviews

    root, path, params, first = _scoped_review(sample, field="results")
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "主来源独立支持完整已完成交付。"}
    params["review"]["fact_scope"] = first
    evidence.handle_evidence_save_draft(params)
    before = path.read_bytes()
    previous = current_result_reviews(parse_simple_yaml(path.read_text()), root, card_id=path.stem)
    source_text = evidence.handle_read_material_document({
        "material_id": first["source"]["material_id"],
        "document_id": first["source"]["document_id"],
    })["text"]
    second = {**first, "source": {**first["source"], "quote": source_text}}
    params["draft"]["field_sources"].append({
        "field": "results", "value": first["value"], "quote": source_text,
        "material_id": first["source"]["material_id"], "document_id": first["source"]["document_id"],
    })
    params["review"] = {"decision": "approved", "fact_scope": second}
    params["expected_sha256"] = hashlib.sha256(before).hexdigest()

    def incomplete_batch(payload):
        request = json.loads(payload["messages"][-1]["content"])
        assert len(request["scopes"]) == 2
        first_row, second_row = request["scopes"]
        answers = [{"review_index": first_row["review_index"], "outcome": "unknown",
                    "measurement_quote": None, "rationale": "本次第一行拟更新为缺证。"}]
        if failure == "invalid_second":
            answers.append({"review_index": second_row["review_index"], "outcome": "established",
                            "measurement_quote": "其他来源的实测指标。", "rationale": "第二行非法借用测量。"})
        return {"reviews": answers}

    result_review_model["reply"] = incomplete_batch
    with pytest.raises(ValueError, match="result_review"):
        evidence.handle_evidence_save_draft(params)
    assert len(result_review_model["calls"]) == 2
    assert path.read_bytes() == before
    assert current_result_reviews(parse_simple_yaml(path.read_text()), root, card_id=path.stem) == previous
    assert len(_live_scope(path)[0]["sources"]) == 1


@pytest.mark.parametrize("sample", [(
    ["本人完成预约能力的固定输入验收，并保存完整测试记录。"],
    ["测试环境固定输入下，响应时间减半；测试环境固定输入下，错误率降至千分之三。"],
)], indirect=True)
@pytest.mark.parametrize("case", ["different_measurements", "one_nonquant", "unrelated_unknown",
                                   "opposite_attribution", "opposite_outcome"])
def test_result_review_projects_one_complete_supporting_row(sample, result_review_model, case):
    from tools.infra.evidence_fact_scope import current_result_reviews, result_review_basis

    root, path, params, first = _scoped_review(sample, field="results")
    first_reply = {"outcome": "established", "measurement_quote": "测试环境固定输入下，响应时间减半",
                   "rationale": "第一条独立支持完整结果。"}
    result_review_model["reply"] = first_reply
    params["review"]["fact_scope"] = first
    evidence.handle_evidence_save_draft(params)

    full_source = evidence.handle_read_material_document({
        "material_id": first["source"]["material_id"], "document_id": first["source"]["document_id"]})["text"]
    second = {**first, "source": {**first["source"], "quote": full_source}}
    second_reply = {"outcome": "established", "measurement_quote": "测试环境固定输入下，错误率降至千分之三。",
                    "rationale": "第二条也独立支持完整结果。"}
    correction_text = None
    if case.startswith("opposite"):
        correction = ("此处记录的验收与测量实际均由同事完成，本人只整理报告，原本人验收归属有误。"
                      if case == "opposite_attribution" else
                      "此处两项数字实际都是预设验收目标，测试尚未执行，原实测记录有误。")
        correction_text = "针对同一预约能力验收的正式更正：\n" + first["value"] + "\n" + correction
        (root / "m3.txt").write_text(correction_text)
        (root / "m3.meta.yaml").write_text(
            'material_id: "m3"\nfilename: "m3.txt"\nextension: ".txt"\nlabel: "更正"\n')
        document, = evidence.handle_list_material_documents({"material_id": "m3"})["items"]
        reference = {"material_id": "m3", **{key: document[key] for key in ("document_id", "sha256", "label")}}
        correction_text = evidence.handle_read_material_document({
            "material_id": "m3", "document_id": reference["document_id"]})["text"]
        second["source"] = {**{key: reference[key] for key in ("material_id", "document_id", "sha256")},
                            "quote": correction_text}
        params["draft"]["source_material_ids"].append("m3")
        params["draft"]["source_documents"].append(reference)
        params["draft"]["artifacts"].append({"type": "text_document", "ref": "m3", "label": "更正"})
        if case == "opposite_attribution":
            second["attribution"] = "teammate"
            second_reply.update(measurement_quote=None, rationale="更正原文保留了同事的真实验收。")
        else:
            second["implementation"] = "planned"
            second_reply.update(outcome="not_established", measurement_quote=None,
                                rationale="当前更正原文明确说明原实测记录尚未发生。")
    elif case == "one_nonquant":
        second_reply["measurement_quote"] = None
    elif case == "unrelated_unknown":
        second["target"] = "另一个独立适用对象"
        second_reply.update(outcome="unknown", measurement_quote=None)
    params["draft"]["field_sources"].append({
        "field": "results", "value": first["value"], "quote": second["source"]["quote"],
        "material_id": second["source"]["material_id"], "document_id": second["source"]["document_id"],
    })
    if correction_text is not None:
        params["review"] = {"decision": "approved", "merge_sources": True}
        params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        evidence.handle_evidence_save_draft(params)

    def batch_review(payload):
        request = json.loads(payload["messages"][-1]["content"])
        received = [document["text"] for document in request["documents"]]
        has_correction = correction_text is not None and correction_text in received and full_source in received
        replies = []
        for scope in request["scopes"]:
            if has_correction and scope["source"] == first["source"]:
                verdict = {"outcome": "not_established", "measurement_quote": None,
                           "rationale": "实际收到的同次验收更正否定了原记录在本人范围下的断言。"}
            else:
                verdict = first_reply if scope["source"] == first["source"] else second_reply
            replies.append({"review_index": scope["review_index"], **verdict})
        return {"reviews": replies}

    result_review_model["reply"] = batch_review
    params["review"] = {"decision": "approved", "fact_scope": second}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    doc = parse_simple_yaml(path.read_text())
    stored = json.loads(doc["scalars"]["reviewed_facts_json"])["fact_scope_v1"]
    current = current_result_reviews(doc, root, card_id=path.stem)
    if case.startswith("opposite"):
        assert current == {}
    else:
        selected = current[f"{path.stem}:results:0"]
        assert selected in stored
        request = json.loads(result_review_model["calls"][-1][1]["messages"][-1]["content"])
        assert selected["result_review"] == {**first_reply, "basis_sha256": result_review_basis(request)}
        assert selected["source"] == first["source"]
    assert len(result_review_model["calls"]) == 2


def _review_request_values(payload):
    request = json.loads(payload["messages"][-1]["content"])

    def walk(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    return request, list(walk(request))


def _save_result_with_peer_source(sample, result_review_model, case, *, adopt_peer=True, peer_field="results"):
    """Exercise source merge and both real adopts; the stub sees only request data."""
    from tools.infra.evidence_fact_scope import current_result_reviews

    root, path, params, first = _scoped_review(sample, field="results")
    value = first["value"]
    first["target"] = "平台联合交付" if case == "split_responsibility" else "统一平台缓存"
    first_text = evidence.handle_read_material_document({
        "material_id": first["source"]["material_id"],
        "document_id": first["source"]["document_id"],
    })["text"]
    peer_text, peer_scope, peer_review = {
        "alias_correction": (
            "2024 年 6 月 20 日归属更正。\n"
            "接入中枢就是初版所称的统一平台缓存；以下更正针对同一次 6 月 18 日改造和验收。\n"
            f"初版写道：『{value}』\n"
            "上述本人主导记载有误；实际缓存改造及测量由同事完成，本人只负责日志对接。",
            {"target": "接入中枢", "attribution": "teammate"},
            {"outcome": "not_established", "measurement_quote": None,
             "rationale": "此更正记录明确否认初版的本人主导归属。"},
        ),
        "earlier_prediction": (
            "2024 年 5 月 2 日计划稿，当日尚未实施，也未采样。\n"
            f"约定未来完成后才可使用的验收陈述是：『{value}』\n"
            "这份记录只描述 5 月 2 日的计划，不否定以后发生的验收。",
            {"implementation": "planned"},
            {"outcome": "not_established", "measurement_quote": None,
             "rationale": "该早期计划本身尚不能证明后来已经发生的测量。"},
        ),
        "split_responsibility": (
            "2024 年 6 月 18 日平台联合交付的职责确认。\n"
            f"{value}\n"
            "本来源的同事归属仅指乙模块的缓存改造及测量；本人完成甲模块日志对接的记录无误。",
            {"attribution": "teammate"},
            {"outcome": "established", "measurement_quote": None,
             "rationale": "完整句分别保留本人和同事的职责，没有把同事的测量归给本人。"},
        ),
        "unrelated_unknown": (
            "另一项校园预约平台的资料缺口记录，与统一平台缓存改造不是同一对象或验收事件。\n"
            f"仅用于说明待补资料格式的引文：『{value}』\n"
            "本资料没有统一平台验收的证据，也没有否认该事件。",
            {"target": "校园预约平台", "attribution": "unknown", "implementation": "planned"},
            {"outcome": "unknown", "measurement_quote": None,
             "rationale": "独立校园项目的资料不足，不能判断另一个项目的验收。"},
        ),
    }[case]
    peer_value = params["draft"][peer_field][0]
    if peer_field == "actions":
        peer_text = "独立校园项目资料整理记录：\n" + peer_value + "\n本记录仅涉及这项资料整理。"
    (root / "m3.txt").write_text(peer_text)
    (root / "m3.meta.yaml").write_text(
        'material_id: "m3"\nfilename: "m3.txt"\nextension: ".txt"\nlabel: "peer"\n')
    document, = evidence.handle_list_material_documents({"material_id": "m3"})["items"]
    reference = {"material_id": "m3", **{key: document[key] for key in ("document_id", "sha256", "label")}}
    peer_text = evidence.handle_read_material_document({
        "material_id": "m3", "document_id": reference["document_id"],
    })["text"]
    peer = {**first, **peer_scope, "field": peer_field, "value": peer_value, "source": {
        **{key: reference[key] for key in ("material_id", "document_id", "sha256")},
        "quote": peer_text,
    }}
    first_review = {
        "outcome": "established",
        "measurement_quote": None if case == "split_responsibility" else value,
        "rationale": "完整验收原文支持本人已完成的贡献；归属和测试条件均保留。",
    }

    def review_from_received_sources(payload):
        request, values = _review_request_values(payload)
        strings = [item for item in values if isinstance(item, str)]
        sees_first = any(first_text in item for item in strings)
        sees_peer = any(peer_text in item for item in strings)
        replies = []
        for scope in request["scopes"]:
            own_source = scope["source"]["material_id"]
            if case == "alias_correction" and sees_first and sees_peer:
                verdict = peer_review
            elif own_source == first["source"]["material_id"] and sees_first:
                verdict = first_review
            elif own_source == "m3" and sees_peer:
                verdict = peer_review
            else:
                verdict = {"outcome": "unknown", "measurement_quote": None,
                           "rationale": "请求未提供本次核验所需的原文，不能推知其他来源结论。"}
            replies.append({"review_index": scope["review_index"], **verdict})
        return {"reviews": replies}

    result_review_model["reply"] = review_from_received_sources
    params["review"]["fact_scope"] = first
    evidence.handle_evidence_save_draft(params)
    fid = f"{path.stem}:results:0"
    baseline = current_result_reviews(parse_simple_yaml(path.read_text()), root, card_id=path.stem)
    from tools.infra.evidence_fact_scope import result_review_basis
    first_request = json.loads(result_review_model["calls"][-1][1]["messages"][-1]["content"])
    assert baseline[fid]["result_review"] == {**first_review, "basis_sha256": result_review_basis(first_request)}
    peer_call_start = len(result_review_model["calls"])

    params["draft"]["source_material_ids"].append("m3")
    params["draft"]["source_documents"].append(reference)
    params["draft"]["artifacts"].append({"type": "text_document", "ref": "m3", "label": "peer"})
    params["draft"]["field_sources"].append({
        "field": peer_field, "value": peer_value, "quote": peer_text,
        "material_id": "m3", "document_id": reference["document_id"],
    })
    params["review"] = {"decision": "approved", "merge_sources": True}
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    if adopt_peer:
        params["review"] = {"decision": "approved", "fact_scope": peer}
        params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        evidence.handle_evidence_save_draft(params)

    detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert detail["results"] == [value]
    assert detail["actions"] == params["draft"]["actions"]
    visible_sources = [source for row in detail["fact_scope_review"] if row["fact_id"] == fid
                       for source in row["sources"]]
    expected_sources = {"m1", "m3"} if adopt_peer and peer_field == "results" else {"m1"}
    assert {source["material_id"] for source in visible_sources} == expected_sources
    return (root, path, first, peer, first_text, peer_text,
            result_review_model["calls"][peer_call_start:])


@pytest.mark.parametrize("sample,case,expected", [
    ((["2024 年 6 月 18 日初版验收记录：统一平台缓存改造由本人主导。"],
      ["本人主导统一平台缓存改造，2024 年 6 月 18 日在隔离测试环境、固定一千请求下响应时间减半。"]),
     "alias_correction", False),
    ((["2024 年 6 月 18 日完成实施和固定负载验收，以下为当日实测记录。"],
      ["本人主导统一平台缓存改造，2024 年 6 月 18 日在隔离测试环境、固定一千请求下响应时间减半。"]),
     "earlier_prediction", True),
    ((["2024 年 6 月 18 日联合交付记录分别确认本人和同事的职责。"],
      ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造，测试环境下固定负载的响应时间减半。"]),
     "split_responsibility", True),
    ((["2024 年 6 月 18 日完成实施和固定负载验收，以下为当日实测记录。"],
      ["本人主导统一平台缓存改造，2024 年 6 月 18 日在隔离测试环境、固定一千请求下响应时间减半。"]),
     "unrelated_unknown", True),
], indirect=["sample"], ids=["alias-correction", "later-measurement", "split-responsibility", "unrelated-unknown"])
def test_result_review_cross_source_whole_fact_uses_actual_context(sample, result_review_model, case, expected):
    from tools.infra.evidence_fact_scope import current_result_reviews

    root, path, first, _peer, _first_text, _peer_text, _calls = _save_result_with_peer_source(
        sample, result_review_model, case)
    doc = parse_simple_yaml(path.read_text())
    current = current_result_reviews(doc, root, card_id=path.stem)
    assert bool(current) is expected
    if expected:
        chosen = current[f"{path.stem}:results:0"]
        stored = json.loads(doc["scalars"]["reviewed_facts_json"])["fact_scope_v1"]
        assert chosen in stored and chosen["source"] == first["source"]
        assert chosen["value"] == first["value"]
        assert chosen["result_review"]["measurement_quote"] == (
            None if case == "split_responsibility" else first["value"])


@pytest.mark.parametrize("sample", [(
    ["2024 年 6 月 18 日初版验收记录：统一平台缓存改造由本人主导。"],
    ["本人主导统一平台缓存改造，2024 年 6 月 18 日在隔离测试环境、固定一千请求下响应时间减半。"],
)], indirect=True)
def test_result_review_save_supplies_same_occurrence_sources_to_independent_reviewer(sample, result_review_model):
    _root, _path, first, peer, first_text, peer_text, calls = _save_result_with_peer_source(
        sample, result_review_model, "alias_correction")
    assert calls
    requests = [_review_request_values(payload)[1] for _url, payload in calls]
    complete = []
    for values in requests:
        strings = [item for item in values if isinstance(item, str)]
        objects = [item for item in values if isinstance(item, dict)]
        texts_bound = all(any(text in item for item in strings) for text in (first_text, peer_text))
        identities_bound = all(any(all(item.get(key) == source[key]
                                       for key in ("material_id", "document_id", "sha256"))
                                   for item in objects)
                               for source in (first["source"], peer["source"]))
        complete.append(texts_bound and identities_bound)
    assert any(complete), "independent review never received both current sources for this exact Fact"


@pytest.mark.parametrize("sample", [(
    ["2024 年 6 月 18 日完成实施和固定负载验收，以下为当日实测记录。"],
    ["本人主导统一平台缓存改造，2024 年 6 月 18 日在隔离测试环境、固定一千请求下响应时间减半。"],
)], indirect=True)
@pytest.mark.parametrize("case", ["alias_correction", "unrelated_unknown"])
def test_result_review_new_same_fact_binding_pauses_old_authority_before_adopt(
        sample, result_review_model, case):
    from tools.infra.evidence_fact_scope import current_result_reviews

    root, path, first, _peer, _first_text, _peer_text, calls = _save_result_with_peer_source(
        sample, result_review_model, case, adopt_peer=False)
    doc = parse_simple_yaml(path.read_text())
    bindings = json.loads(doc["scalars"]["field_sources_json"])
    assert {row["material_id"] for row in bindings
            if row["field"] == "results" and row["value"] == first["value"]} == {"m1", "m3"}
    stored = json.loads(doc["scalars"]["reviewed_facts_json"])["fact_scope_v1"]
    assert len(stored) == 1 and stored[0]["source"] == first["source"]
    assert calls == [], "a source binding alone has not performed the explicit result review"
    assert current_result_reviews(doc, root, card_id=path.stem) == {}


@pytest.mark.parametrize("sample", [(
    ["为独立校园项目整理非功能测试资料。"],
    ["本人主导统一平台缓存改造，2024 年 6 月 18 日在隔离测试环境、固定一千请求下响应时间减半。"],
)], indirect=True)
def test_result_review_other_fact_binding_does_not_change_current_result_basis(sample, result_review_model):
    from tools.infra.evidence_fact_scope import current_result_reviews

    root, path, first, peer, _first_text, peer_text, calls = _save_result_with_peer_source(
        sample, result_review_model, "unrelated_unknown", adopt_peer=False, peer_field="actions")
    doc = parse_simple_yaml(path.read_text())
    bindings = json.loads(doc["scalars"]["field_sources_json"])
    assert {row["material_id"] for row in bindings
            if row["field"] == "results" and row["value"] == first["value"]} == {"m1"}
    assert any(row["field"] == "actions" and row["value"] == peer["value"]
               and row["material_id"] == "m3" for row in bindings)
    assert first["value"] not in peer_text
    assert calls == [], "an unrelated Fact binding does not require reviewing this result again"
    current = current_result_reviews(doc, root, card_id=path.stem)
    chosen = current[f"{path.stem}:results:0"]
    assert chosen["source"] == first["source"] and chosen["value"] == first["value"]
    assert chosen["result_review"]["measurement_quote"] == first["value"]


def test_result_review_source_aba_is_rejected_by_selected_document_sha(sample, result_review_model, monkeypatch):
    from tools.sidecar.handlers import evidence_draft

    root, path, params, scope = _scoped_review(sample, field="results")
    params["review"]["fact_scope"] = scope
    source = root / "m1.txt"
    original_source = source.read_bytes()
    original_card = path.read_bytes()
    read_documents = evidence_draft.read_source_documents

    def changed_during_read(*args, **kwargs):
        source.write_bytes(original_source + "\n临时替换的原文。".encode())
        try:
            return read_documents(*args, **kwargs)
        finally:
            source.write_bytes(original_source)

    monkeypatch.setattr(evidence_draft, "read_source_documents", changed_during_read)
    with pytest.raises(ValueError, match="material_document_changed_or_missing"):
        evidence.handle_evidence_save_draft(params)
    assert source.read_bytes() == original_source
    assert path.read_bytes() == original_card
    assert result_review_model["calls"] == []





@pytest.mark.parametrize("sample", [(
    ["合成行动\n其完整实施条件。"],
    ["独立兄弟结果。", "合成测试条件：\n完整结果及其边界。"],
)], indirect=True)
def test_multiline_fact_array_keeps_scope_identity_through_title_review(sample):
    _, path, params, action_scope = _scoped_review(sample)
    value = params["draft"]["results"][1]
    ref = params["draft"]["source_documents"][0]
    params["draft"]["field_sources"].append({
        "field": "results", "value": value, "quote": value,
        "material_id": ref["material_id"], "document_id": ref["document_id"],
    })
    params["review"]["fact_scope"] = {
        **action_scope, "field": "results", "index": 1, "value": value,
        "source": {**action_scope["source"], "quote": value}, "attribution": "teammate",
    }
    evidence.handle_evidence_save_draft(params)
    before = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    scope, = before["fact_scope_review"]
    assert scope["fact_id"] == f"{path.stem}:results:1"
    assert scope["value"] == value and scope["attribution"] == "teammate"

    evidence.handle_evidence_update({"meta": META, "evidence_id": path.stem,
                                     "patch": {"title": "合成标题修正"}})
    pending = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert pending["fact_scope_review"] == []
    assert pending["actions"] == before["actions"] and pending["results"] == before["results"]
    assert pending["field_sources"] == before["field_sources"]
    params["draft"]["title"] = pending["title"]
    params["expected_sha256"] = pending["source_sha256"]
    params["review"].pop("fact_scope")
    evidence.handle_evidence_save_draft(params)
    approved = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert approved["fact_scope_review"] == [scope]
    assert approved["actions"] == before["actions"] and approved["results"] == before["results"]
    assert approved["field_sources"] == before["field_sources"]


@pytest.mark.parametrize("field", ["actions", "results"])
@pytest.mark.parametrize("invalid", ["old string API", None, {}, [1], ["  \n\t"]])
def test_fact_array_save_rejects_invalid_items_without_write(sample, field, invalid):
    _, path, params = sample
    params["draft"][field] = invalid
    before = path.read_bytes()
    with pytest.raises(ValueError, match=field):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before


def test_fact_array_result_guard_requires_the_complete_item(sample):
    _, path, params = sample
    # 两段各自出现在原文，组合后的完整事实不存在，不能逐行借证。
    params["draft"]["results"] = [params["draft"]["actions"][0] + "\n\n" + params["draft"]["results"][0]]
    before = path.read_bytes()
    with pytest.raises(ValueError, match="no_fabrication_guard"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before


@pytest.mark.parametrize("operation", ["save", "update"])
def test_fact_array_result_cannot_span_distinct_source_documents(sample, operation):
    _, path, params = sample
    if operation == "update":
        evidence.handle_evidence_save_draft(params)
    draft = {key: value for key, value in params["draft"].items() if key != "field_sources"}
    documents = [
        evidence.handle_read_material_document({
            "material_id": ref["material_id"], "document_id": ref["document_id"],
        })["text"]
        for ref in draft["source_documents"]
    ]
    result = documents[0].splitlines()[-1] + "\n\n" + documents[1].splitlines()[0]
    assert result in "\n\n".join(documents)
    assert all(result not in document for document in documents)
    draft["results"] = [result]
    before = {card.name: card.read_bytes() for card in path.parent.glob("*.yaml")}
    with pytest.raises(ValueError, match="no_fabrication_guard"):
        if operation == "save":
            evidence.handle_evidence_save_draft({
                "meta": META, "draft": draft, "review": {"decision": "approved"}, "save_mode": "eligible",
            })
        else:
            evidence.handle_evidence_update({
                "meta": META, "evidence_id": path.stem, "patch": {"results": [result]},
            })
    assert {card.name: card.read_bytes() for card in path.parent.glob("*.yaml")} == before


@pytest.fixture
def repeated_scope(sample):
    root, path, params = sample
    value = "P95 从 200 ms 降至 120 ms。"
    params["draft"]["actions"] = [value]
    ref = params["draft"]["source_documents"][0]
    params["draft"]["field_sources"].append({
        "field": "actions", "value": value, "quote": value,
        "material_id": ref["material_id"], "document_id": ref["document_id"],
    })
    return _scoped_review(sample)


@pytest.mark.parametrize("sample", [
    (["容量规划：预计 P95 从 200 ms 降至 120 ms。"], ["测试环境实测：P95 从 200 ms 降至 120 ms。"]),
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
    quote = params["draft"]["results"][0]
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
    (["容量规划：预计 P95 从 200 ms 降至 120 ms。"], ["测试环境实测：P95 从 200 ms 降至 120 ms。"]),
], indirect=True)
@pytest.mark.parametrize("resolution", ["revoke", "adopt"])
def test_ambiguous_saved_scope_requires_explicit_recovery_without_losing_sibling(repeated_scope, resolution):
    from tools.engines.generation.resume_renderer import load_cards, load_all_cards
    from tools.infra.evidence_fact_scope import nonpersonal_reviewed_fact_ids, personal_claim_exclusions
    from tools.infra.evidence_sources import validated_source_inputs
    from tools.infra.persistence.yaml_io import dump_yaml

    root, path, params, scope = repeated_scope
    quote = params["draft"]["results"][0]
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


@pytest.mark.parametrize("sample", [(
    ["规划：预计 P95 从 200 ms 降至 120 ms。"],
    ["测试环境固定 1000 个请求，采样窗口 5 分钟：", "P95 从 200 ms 降至 120 ms。"],
)], indirect=True)
@pytest.mark.parametrize("case", ["reference_only", "adopt", "stale_card_revision", "source_changed", "scope_quote_mismatch"])
def test_ui_expanded_quote_reaches_existing_review_atomically(sample, case):
    import copy
    import subprocess
    from pathlib import Path
    from tools.infra.persistence.yaml_io import dump_yaml

    root, path, params, sibling = _scoped_review(sample)
    value = "P95 从 200 ms 降至 120 ms。"
    ref = params["draft"]["source_documents"][0]
    binding = {"field": "results", "value": value, "quote": value,
               "material_id": ref["material_id"], "document_id": ref["document_id"]}
    params["draft"]["field_sources"].append(binding)
    evidence.handle_evidence_save_draft(params)
    position = {"field": "results", "index": 1, "value": value}
    old = {**position, "source": {**{key: ref[key] for key in ("material_id", "document_id", "sha256")}, "quote": value},
           "attribution": "self", "target": "测试延迟", "environment": "test",
           "implementation": "implemented", "release": "not_released"}
    sibling = {key: item for key, item in sibling.items() if key != "kind"}
    sibling.update(attribution="teammate", implementation="planned", release="unknown")

    # 复现旧卡留下的含糊指标范围，并保留独立的合法兄弟范围。
    doc = parse_simple_yaml(path.read_text())
    snapshot = json.loads(doc["scalars"]["reviewed_facts_json"])
    snapshot["fact_scope_v1"] = [sibling] if case == "reference_only" else [sibling, old]
    doc["scalars"]["reviewed_facts_json"] = json.dumps(snapshot, ensure_ascii=False)
    path.write_text(dump_yaml(doc["scalars"], doc["lists"]))
    before = path.read_bytes()
    detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    if case == "reference_only":
        assert not detail.get("source_error")
    else:
        assert detail["source_error"] == "fact_scope_source_not_unique"
    quote = "\n".join(params["draft"]["results"])
    read = evidence.handle_read_material_document({"material_id": ref["material_id"], "document_id": ref["document_id"]})
    assert read["sha256"] == ref["sha256"]
    original_draft = copy.deepcopy(params["draft"])

    # 使用应用真正的 TypeScript 草稿操作；将其输出交给真实保存处理器。
    script = r"""
const fs = require('node:fs'), ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const code = ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021
}}).outputText;
const module = {exports: {}};
new Function('exports', 'module', code)(module.exports, module);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = module.exports.extendSourceQuote(input.draft, input.position, input.binding,
  input.document, input.sourceText, input.quote);
process.stdout.write(JSON.stringify(result));
"""
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["node", "-e", script, str(repo / "ui/src/pages/evidence/source-merge.ts")],
        cwd=repo / "ui", input=json.dumps({
            "draft": original_draft, "position": position, "binding": binding,
            "document": ref, "sourceText": read["text"], "quote": quote,
        }, ensure_ascii=False), capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    params["draft"] = json.loads(result.stdout)
    expected_draft = copy.deepcopy(original_draft)
    expected_draft["field_sources"][-1]["quote"] = quote
    assert params["draft"] == expected_draft

    params["expected_sha256"] = hashlib.sha256(before).hexdigest()
    if case == "reference_only":
        # 引用补全不要求凭空建立状态范围，已有兄弟范围照常保留。
        evidence.handle_evidence_save_draft(params)
        detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
        assert detail["field_sources"] == expected_draft["field_sources"]
        row, = detail["fact_scope_review"]
        assert row["field"] == "actions" and row["attribution"] == "teammate"
        assert "fact_scope" not in params["review"]
        return

    # 更长引文不能通过普通保存清除旧范围，必须显式采纳精确目标。
    with pytest.raises(ValueError, match="fact_scope_unverifiable"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before
    params["review"]["fact_scope"] = {**old, "kind": "adopt", "source": {**old["source"], "quote": quote}}
    errors = {"stale_card_revision": "evidence_review_changed",
              "source_changed": "material_.*changed",
              "scope_quote_mismatch": "fact_scope_unbound"}
    if case == "stale_card_revision":
        params["expected_sha256"] = "stale-card-revision"
    elif case == "source_changed":
        (root / "m1.txt").write_text((root / "m1.txt").read_text() + "\n来源已修订。")
    elif case == "scope_quote_mismatch":
        params["review"]["fact_scope"]["source"]["quote"] = value
    if case != "adopt":
        with pytest.raises(ValueError, match=errors[case]):
            evidence.handle_evidence_save_draft(params)
        assert path.read_bytes() == before
        return

    evidence.handle_evidence_save_draft(params)
    saved = parse_simple_yaml(path.read_text())
    assert saved["lists"]["actions"] == doc["lists"]["actions"]
    assert saved["lists"]["results"] == doc["lists"]["results"]
    scopes = json.loads(saved["scalars"]["reviewed_facts_json"])["fact_scope_v1"]
    assert sibling in scopes and len(scopes) == 2
    detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert detail["field_sources"] == expected_draft["field_sources"]
    target, = [row for row in detail["fact_scope_review"] if row["field"] == "results"]
    assert target["fact_id"] == f"{path.stem}:results:1"
    assert target["value"] == value
    assert target["sources"][0]["quote"] == quote
    assert target["environment"] == "test" and target["release"] == "not_released"


def test_incomplete_save_preserves_scope_without_granting_authority(sample):
    _, path, params, scope = _scoped_review(sample)
    scope["attribution"] = "teammate"
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    accepted = json.loads(parse_simple_yaml(path.read_text())["scalars"]["reviewed_facts_json"])["fact_scope_v1"]

    # 暂存为不完整不能撤销已核定范围，也不能让它继续充当候选事实。
    params["review"].pop("fact_scope")
    params["save_mode"] = "incomplete"
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    saved = evidence.handle_evidence_save_draft(params)
    assert saved["candidate_pool_eligible"] is False
    detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert detail["fact_scope_review"] == []
    pending = json.loads(parse_simple_yaml(path.read_text())["scalars"]["reviewed_facts_json"])
    assert pending["fact_scope_v1"] == accepted

    # 再次普通复审仍须保留同事范围，不能借状态往返恢复整卡归功。
    params["save_mode"] = "eligible"
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    row, = _live_scope(path)
    assert row["fact_id"] == f"{path.stem}:actions:0"
    assert row["attribution"] == "teammate"


@pytest.mark.parametrize("save_mode", ["incomplete", "eligible"])
def test_incomplete_review_cannot_silently_replace_scope_binding(sample, save_mode):
    _, path, params, scope = _scoped_review(sample)
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    params["review"].pop("fact_scope")
    params["save_mode"] = "incomplete"
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)

    ref = params["draft"]["source_documents"][0]
    quote = evidence.handle_read_material_document({"material_id": ref["material_id"], "document_id": ref["document_id"]})["text"]
    params["draft"]["field_sources"][-1]["quote"] = quote
    params["save_mode"] = save_mode
    before = path.read_bytes()
    params["expected_sha256"] = hashlib.sha256(before).hexdigest()
    with pytest.raises(ValueError, match="fact_scope_unverifiable"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before

    # 仍沿原有显式采纳修复精确目标，不需要另建恢复记录。
    params["save_mode"] = "eligible"
    params["review"]["fact_scope"] = {**scope, "source": {**scope["source"], "quote": quote}}
    evidence.handle_evidence_save_draft(params)
    row, = _live_scope(path)
    assert row["sources"][0]["quote"] == quote


def test_ordinary_title_edit_keeps_scope_through_pending_review(sample):
    _, path, params, scope = _scoped_review(sample)
    scope["attribution"] = "teammate"
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    evidence.handle_evidence_update({"meta": META, "evidence_id": path.stem, "patch": {"title": "合成平台架构"}})
    detail = evidence.handle_evidence_get({"meta": META, "evidence_id": path.stem})["evidence"]
    assert detail["candidate_pool_eligible"] is False
    assert detail["fact_scope_review"] == []

    params["draft"]["title"] = "合成平台架构"
    params["review"].pop("fact_scope")
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.handle_evidence_save_draft(params)
    row, = _live_scope(path)
    assert row["attribution"] == "teammate"
    assert row["fact_id"] == f"{path.stem}:actions:0"


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
    if fault=="duplicate":params['draft']['actions'].append(scope['value'])
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
    from tools.infra.evidence_fact_scope import nonpersonal_reviewed_fact_ids, personal_claim_exclusions
    from tools.infra.evidence_sources import validated_source_inputs

    def match_limits():
        doc = parse_simple_yaml(path.read_text())
        sources = validated_source_inputs(doc, root)
        # The sibling result remains unavailable as personal support, without being
        # labelled wholly nonpersonal by the action-attribution helper.
        assert f"{path.stem}:results:0" in personal_claim_exclusions(
            doc, root, card_id=path.stem, validated_sources=sources)
        return nonpersonal_reviewed_fact_ids(doc, root, card_id=path.stem,
            validated_sources=sources)

    assert match_limits() == {f"{path.stem}:actions:0"}
    save_scope({**adopt, 'attribution':'team_lead', 'implementation':'unknown','release':'unknown'})
    rows = _live_scope(path)
    opposed, = [row for row in rows if row['attribution']=='conflict']
    assert {r['attribution'] for r in opposed['sources']} == {'self','teammate'}
    # A valid separately reviewed lead scope keeps the action from receiving
    # a global negative label; the exact teammate-only sibling stays restricted.
    assert match_limits() == set()
    assert opposed['implementation'] == opposed['release'] == 'unknown'
    assert any(row['attribution']=='team_lead' and row['field']=='actions' for row in rows)
    assert any(row==peer for row in rows)
    save_scope({'kind':'revoke','field':'actions','index':0,'value':v})
    kept, = _live_scope(path)
    assert kept == peer
    assert match_limits() == set()
    (root/'m1.txt').write_text('source-mutation')
    assert _live_scope(path) == []


def test_changed_fact_pending_scope_cannot_resurface_or_disappear_on_ordinary_reapproval(sample):
    _, path, params, scope = _scoped_review(sample)
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    assert _live_scope(path)
    replacement = params["draft"]["results"][0]
    evidence.handle_evidence_update({"meta": META, "evidence_id": path.stem, "patch": {"actions": [replacement]}})
    assert _live_scope(path) == []
    params["draft"]["actions"] = [replacement]
    params["draft"]["field_sources"][-1].update(value=replacement, quote=replacement)
    params["review"].pop("fact_scope")
    before = path.read_bytes()
    params["expected_sha256"] = hashlib.sha256(before).hexdigest()
    # 已改事实不能借普通复审复活旧范围，也不能把旧约束当作不存在。
    with pytest.raises(ValueError, match="fact_scope_unverifiable"):
        evidence.handle_evidence_save_draft(params)
    assert path.read_bytes() == before


@pytest.mark.parametrize('sample', [
    (['实现会员时间轴页面并接入平台已有接口。'], ['完成预约能力的测试验收，覆盖改期流程。']),
    (['实现会员时间轴页面，\n并接入平台已有接口。'], ['完成预约能力的测试验收，\n覆盖改期流程；本次仅验证测试环境。']),
], indirect=True)
def test_reviewed_page_does_not_inherit_project_role_in_plan_or_preview(sample, result_review_model):
    from tools.domain.quality_text import render_fact_text
    from tools.engines.generation.plan_renderer import render_plan
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
    value = params["draft"]["results"][0]
    source = scope["source"]
    params["draft"]["field_sources"].append({"field": "results", "value": value, "quote": value,
        "material_id": source["material_id"], "document_id": source["document_id"]})
    params["review"]["fact_scope"] = {**scope, "field": "results", "value": value,
                                      "source": {**source, "quote": value}}
    result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                    "rationale": "已完成的测试验收；不扩大为生产。"}
    evidence.handle_evidence_save_draft(params)
    params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    scope = {**scope, 'attribution':'teammate'}
    params['review']['fact_scope'] = scope
    evidence.handle_evidence_save_draft(params)
    action_id = path.stem + ':actions:0'
    result_id = path.stem + ':results:0'
    complete_result = render_fact_text(params['draft']['results'][0])
    for cards in (load_cards(path.parent, [path.stem], root), load_all_cards(path.parent, root)):
        index = build_fact_index(cards)
        selection = select_facts(index)
        plan = build_resume_plan(index, selection, {})
        assert index.get(action_id) is None, 'scoped quote inherited the project role'
        assert index.get(result_id) is not None
        assert action_id not in plan.fact_ids
        claims = []
        markdown = render_plan(plan, index, profile={}, job_context={}, claims=claims)
        assert complete_result in markdown
        result_claims = [claim for claim in claims if claim.get('fact_id') == result_id]
        assert len(result_claims) == 1 and result_claims[0]['text'] == complete_result

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
              "direction":{"status":"needs_review"},"pool":{}, "snapshot": _review_input_snapshot(path, root, job)}
    excerpt = preview.render_reviewed_excerpt('jp_test',inputs,raw)
    assert action_id not in [c["fact_id"] for c in excerpt["claims"]]
    assert result_id in [c["fact_id"] for c in excerpt["claims"]]
    result_claims = [claim for claim in excerpt['claims'] if claim['fact_id'] == result_id]
    assert len(result_claims) == 1 and result_claims[0]['quote'] == params['draft']['results'][0]
    assert complete_result in excerpt['markdown']
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


@pytest.mark.parametrize("sample,review_state,positive", [
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "missing", False),
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "old_basis", False),
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "stale_basis", False),
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "unknown", False),
    ((["核对项目分工记录。"], ["同事完成乙模块的缓存改造。"]), "pure_teammate", False),
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "mixed_teammate", False),
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "mixed_personal", True),
    ((["核对项目分工记录。"], ["本人完成甲模块的日志对接；同事完成乙模块的缓存改造。"]), "unscoped", True),
], indirect=["sample"])
def test_matching_scoped_result_requires_current_personal_review_without_inventing_conflict(
        sample, result_review_model, review_state, positive):
    import io
    from tools.domain.assessment_support import positive_citations
    from tools.engines.matching import semantic_matching
    from tools.infra.evidence_fact_scope import nonpersonal_reviewed_fact_ids
    from tools.infra.evidence_sources import validated_source_inputs
    from tools.infra.llm.bounded_local import BoundedLocalClient
    from tools.infra.persistence.yaml_io import dump_yaml

    if review_state == "mixed_personal":
        root, path, *_ = _save_result_with_peer_source(sample, result_review_model, "split_responsibility")
    else:
        root, path, params, scope = _scoped_review(sample, field="results")
        if review_state != "unscoped":
            params["review"]["fact_scope"] = {**scope, "attribution": "teammate"}
            result_review_model["reply"] = {
                "outcome": "unknown" if review_state == "unknown" else "established",
                "measurement_quote": None,
                "rationale": "此处完整分工可忠实呈现；该条范围不能把整句断言成纯同事成果。",
            }
            evidence.handle_evidence_save_draft(params)
            if review_state in {"missing", "old_basis", "stale_basis"}:
                doc = parse_simple_yaml(path.read_text())
                snapshot = json.loads(doc["scalars"]["reviewed_facts_json"])
                row, = snapshot["fact_scope_v1"]
                if review_state == "missing":
                    row.pop("result_review")
                elif review_state == "old_basis":
                    row["result_review"].pop("basis_sha256")
                else:
                    row["result_review"]["basis_sha256"] = "0" * 64
                doc["scalars"]["reviewed_facts_json"] = json.dumps(snapshot, ensure_ascii=False)
                path.write_text(dump_yaml(doc["scalars"], doc["lists"]))
    doc = parse_simple_yaml(path.read_text())
    fid = f"{path.stem}:results:0"
    value = doc["lists"]["results"][0]
    assert fid not in nonpersonal_reviewed_fact_ids(
        doc, root, card_id=path.stem, validated_sources=validated_source_inputs(doc, root))
    job = root.parent / "matching-result.yaml"
    job.write_text('target_role: "平台工程师"\nmust_have:\n  - "平台功能交付"\n')
    requests = []
    client = BoundedLocalClient(model="synthetic", api_key="")

    class FixedTransport:
        def open(self, request, **kwargs):
            data = json.loads(json.loads(request.data)["messages"][1]["content"])
            requests.append(data)
            if data["stage"] == "recall":
                answer = {"cards": [{"id": path.stem, "score": 70, "reason": "完整分工相关",
                                     "requirement_ids": ["r1"], "citations": [{"fact_id": fid}]}]}
            else:
                answer = {"assessments": [{
                    "requirement_id": requirement["id"],
                    "status": "supported" if positive else "conflict",
                    "reason": "模型对当前引用的提名仍需应用校准。",
                    "citations": [{"fact_id": fid, "candidate_support": True}],
                } for requirement in data["requirements"]]}
            return io.BytesIO(json.dumps({"choices": [{
                "message": {"content": json.dumps(answer)}, "finish_reason": "stop",
            }]}).encode())

    client._opener = FixedTransport()
    report = semantic_matching.run_semantic_matching(
        job_path=job, evidence_files=[path], personal_profile=None, client=client,
        model="synthetic", cache_dir=root.parent / "matching-cache", advisory=True)
    assert [request["stage"] for request in requests] == ["recall", "assess"]
    for request in requests:
        fact = request["facts"][fid]
        assert fact["text"] == value
        if not positive:
            assert "source_role" not in fact
        if request["stage"] == "assess":
            assert fact.get("candidate_support") is (None if positive else False)
    assessment, = report["assessments"]
    assert assessment["status"] == ("supported" if positive else "insufficient")
    citation, = assessment["checks"][0]["citations"]
    assert citation["fact_id"] == fid
    assert citation.get("candidate_support") is (None if positive else False)
    assert [item["fact_id"] for item, _ in positive_citations(assessment)] == ([fid] if positive else [])


@pytest.mark.parametrize("sample", [
    (["实现预约接口的幂等重试。"], ["完成预约能力的测试验收，覆盖改期流程。"]),
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
def test_matching_never_credits_teammate_only_occurrence(sample, result_review_model, monkeypatch, relation, other, mixed, advisory, negative, expected):
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
    if mixed:
        value = params["draft"]["results"][0]
        source = scope["source"]
        params["draft"]["field_sources"].append({"field": "results", "value": value, "quote": value,
            "material_id": source["material_id"], "document_id": source["document_id"]})
        params["review"]["fact_scope"] = {**scope, "field": "results", "value": value,
                                          "source": {**source, "quote": value}}
        params["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        result_review_model["reply"] = {"outcome": "established", "measurement_quote": None,
                                        "rationale": "独立兄弟验收结果成立，且保留测试条件。"}
        evidence.handle_evidence_save_draft(params)
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
        inputs = {"direction":{}, "evidence_files":[path], "pool":{}, "personal_profile":profile, "job_path":job,
                  "snapshot": _review_input_snapshot(path, root, job)}
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
