import hashlib
import json
from pathlib import Path

import pytest


def candidate():
    return {'job_lead_id': 'lead-1', 'job_url': 'https://www.liepin.com/job/123.shtml',
            'company': '测试公司', 'position': '测试岗位', 'resume_version': 'v1',
            'platform': 'liepin', 'platform_job_id': '123', 'platform_job_type': '2',
            'source': 'liepin_official', 'job_profile_id': 'profile-1',
            'jd_status': 'complete_reviewed', 'source_jd_sha256': 'jd-hash'}


@pytest.fixture
def snapshots(tmp_path, monkeypatch):
    from tools.infra.persistence import review_snapshot as module
    monkeypatch.setattr(module, '_render_pdf', lambda src, dst: dst.write_bytes(b'%PDF-test-only'))
    return module.ReviewSnapshotStore(tmp_path / 'runs')


def test_snapshot_survives_new_store_and_binds_exact_target(snapshots):
    c = candidate()
    ref = snapshots.create('run-1', c, '# 已有证据简历', dry_run=True)
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    restored = ReviewSnapshotStore(snapshots.root).load('run-1', {**c, 'snapshot': ref})
    assert restored['resume_markdown'] == '# 已有证据简历'
    assert restored['dry_run'] is True
    assert Path(restored['resume_path']).read_bytes().startswith(b'%PDF-')
    assert '已有证据简历' not in json.dumps(ref, ensure_ascii=False)


@pytest.mark.parametrize('mutation', ['body', 'pdf', 'target', 'version', 'manifest', 'reference', 'filename'])
def test_snapshot_mutation_fails_closed(snapshots, mutation):
    c = candidate()
    c['pdf_filename']='张三-公司-岗-20261008.1.PDF'
    ref = snapshots.create('run-1', c, '# 已批准内容', dry_run=False)
    data = snapshots.load('run-1', {**c, 'snapshot': ref})
    if mutation in ('body', 'pdf', 'manifest'):
        path = Path(data['resume_path']).parent / {'body':'resume.md','pdf':'resume.pdf','manifest':'manifest.json'}[mutation]
        path.chmod(0o600)
        path.write_text('changed')
    elif mutation == 'target':
        c['platform_job_id'] = 'other'
    elif mutation == 'version':
        c['resume_version'] = 'v2'
    elif mutation == 'filename':
        c['pdf_filename']='李四-公司-岗-20261008.1.PDF'
    else:
        ref['id'] = '../../outside'
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.load('run-1', {**c, 'snapshot': ref})


def test_snapshot_requires_reference_and_safe_run(snapshots):
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.load('run-1', candidate())
    with pytest.raises(ValueError):
        snapshots.create('../outside', candidate(), '# 内容', dry_run=True)


def test_export_failure_does_not_create_reviewable_snapshot(snapshots, monkeypatch):
    from tools.infra.persistence import review_snapshot
    def fail(*args):
        raise RuntimeError('renderer failed')
    monkeypatch.setattr(review_snapshot, '_render_pdf', fail)
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', candidate(), '# 内容', dry_run=False)
    assert not list(snapshots.root.rglob('manifest.json'))


def test_platform_default_snapshot_is_text_not_a_sent_pdf(snapshots, monkeypatch):
    import hashlib
    from tools.infra.persistence import review_snapshot
    text = '平台当前简历合成样本'
    c = {**candidate(), 'delivery_kind':'platform_default',
         'platform_resume_sha256':hashlib.sha256(text.encode()).hexdigest()}
    monkeypatch.setattr(review_snapshot, '_render_pdf', lambda *_: pytest.fail('默认简历不生成伪附件'))
    ref = snapshots.create('run-1', c, text, dry_run=False)
    loaded = snapshots.load('run-1', {**c,'snapshot':ref})
    assert loaded['resume_path'] == ''
    assert loaded['pdf_sha256'] == ''
    assert loaded['resume_markdown'] == text
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.load('run-1', {**c,'delivery_kind':'generated_pdf','snapshot':ref})


def _generated_content(tmp_path):
    import hashlib

    statement = '在隔离测试环境完成验证；生产环境尚未验证。'
    source = tmp_path / 'source.md'
    source.write_text(statement, encoding='utf-8')
    card = tmp_path / 'card.yaml'
    card.write_text('results:\n  - ' + json.dumps(statement, ensure_ascii=False) + '\n', encoding='utf-8')
    content = '# 合成候选人\n\n- ' + statement + '\n'
    trace = {
        'schema_version': 1,
        'occurrence_lineage_version': 1,
        'resume_sha256': hashlib.sha256(content.encode()).hexdigest(),
        'evidence_card_ids': ['card-a'],
        'inputs': {
            key: {'path': str(path), 'exists': True, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for key, path in [('card-a', card), ('material:source', source)]
        },
        'claims': [{'text': statement, 'source_kind': 'evidence', 'evidence_id': 'card-a',
                    'field': 'results', 'fact_id': 'card-a:results:0', 'render_line': 3}],
    }
    return content, trace, source


def test_generated_snapshot_carries_same_trace_and_revokes_when_source_changes(snapshots, tmp_path):
    from tools.infra.persistence.review_snapshot import read_generation_trace

    content, trace, source = _generated_content(tmp_path)
    c = candidate()
    c['snapshot'] = snapshots.create('run-1', c, content, dry_run=True, generation_trace=trace)
    loaded = snapshots.load('run-1', c)
    restored_trace, valid = read_generation_trace(Path(loaded['resume_markdown_path']))
    assert valid
    assert restored_trace == trace
    assert loaded['generation_trace_sha256']
    source.write_text('来源版本已经撤回原结论', encoding='utf-8')
    with pytest.raises(ValueError, match='review_snapshot_invalid'):
        snapshots.load('run-1', c)


def test_generated_snapshot_rejects_trace_changed_after_sealing(snapshots, tmp_path):
    content, trace, _ = _generated_content(tmp_path)
    c = candidate()
    c['snapshot'] = snapshots.create('run-1', c, content, dry_run=True, generation_trace=trace)
    loaded = snapshots.load('run-1', c)
    path = Path(loaded['resume_markdown_path']).with_suffix('.trace.json')
    path.chmod(0o600)
    path.write_text(json.dumps({**trace, 'claims': []}), encoding='utf-8')
    with pytest.raises(ValueError, match='review_snapshot_invalid'):
        snapshots.load('run-1', c)


@pytest.mark.parametrize('mutation', ['source', 'body', 'trace'])
def test_source_change_during_pdf_export_cannot_publish_generated_snapshot(snapshots, tmp_path, monkeypatch, mutation):
    from tools.infra.persistence import review_snapshot

    content, trace, source = _generated_content(tmp_path)
    def export_and_change_source(md, pdf):
        pdf.write_bytes(b'%PDF-test-only')
        changed = {'source': source, 'body': md, 'trace': md.with_suffix('.trace.json')}[mutation]
        changed.write_text('导出期间输入或产物已变更', encoding='utf-8')
    monkeypatch.setattr(review_snapshot, '_render_pdf', export_and_change_source)
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', candidate(), content, dry_run=True, generation_trace=trace)
    assert not list(snapshots.root.rglob('manifest.json'))


def test_supplied_invalid_generation_trace_never_falls_back_to_bare_content(snapshots, tmp_path):
    content, trace, _ = _generated_content(tmp_path)
    trace['resume_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', candidate(), content, dry_run=True, generation_trace=trace)
    assert not list(snapshots.root.rglob('manifest.json'))

def quality_candidate(content='# 仅使用已有事实', pdf=b'%PDF-test-only'):
    """真实四层构建器给出未判报告；此夹具不制造通过结论。"""
    from tools.engines.evaluation.tiered_evaluator import build_quality_report
    from tools.infra.persistence.review_snapshot import quality_digest

    item = candidate()
    body_sha = hashlib.sha256(content.encode('utf-8')).hexdigest()
    report = build_quality_report(
        resume=content, trace={}, career_profile={}, cards={},
        semantic_review=None, job_context={}, resume_version=body_sha,
        job_profile_id=item['job_profile_id'],
        legacy_scores={'rule_total': 99, 'llm_expression': None},
    )
    item['quality_snapshot'] = {
        'status': 'bound', 'resume_sha256': body_sha,
        'pdf_sha256': hashlib.sha256(pdf).hexdigest(),
        'auto_pass': report['auto_pass'], 'quality_report': report,
        'legacy_scores': report['legacy_scores'], 'gap_tasks': report['gap_tasks'],
    }
    item['quality_sha256'] = quality_digest(item['quality_snapshot'])
    return item


def test_m1_quality_snapshot_reopens_same_report_and_real_artifacts(snapshots):
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore

    text = '# 仅使用已有事实'
    item = quality_candidate(text)
    report = item['quality_snapshot']['quality_report']
    assert report['resume_version'] != item['resume_version']
    assert report['auto_pass'] is False and report['llm_pending']
    item['snapshot'] = snapshots.create('run-1', item, text, dry_run=True)
    loaded = ReviewSnapshotStore(snapshots.root).load('run-1', item)
    assert loaded['candidate']['quality_sha256'] == item['quality_sha256']
    assert loaded['markdown_sha256'] == report['resume_version']
    assert loaded['pdf_sha256'] == item['quality_snapshot']['pdf_sha256']
    assert item['quality_snapshot']['quality_report'] == report
    assert item['quality_snapshot']['legacy_scores']['rule_total'] == 99


@pytest.mark.parametrize('mutation', [
    'payload', 'digest', 'report_body', 'snapshot_body', 'report_job', 'pdf',
])
def test_m1_quality_snapshot_rejects_wrong_binding_before_publication(snapshots, mutation):
    from tools.infra.persistence.review_snapshot import quality_digest

    text = '# 仅使用已有事实'
    item = quality_candidate(text)
    quality = item['quality_snapshot']
    if mutation == 'payload':
        quality['quality_report']['gap_tasks'].append('未经本次评测新增的结论')
    elif mutation == 'digest':
        item['quality_sha256'] = '0' * 64
    elif mutation == 'report_body':
        quality['quality_report']['resume_version'] = '1' * 64
    elif mutation == 'snapshot_body':
        quality['resume_sha256'] = '2' * 64
    elif mutation == 'report_job':
        quality['quality_report']['job_profile_id'] = 'another-profile'
    else:
        quality['pdf_sha256'] = '3' * 64
    if mutation not in ('payload', 'digest'):
        item['quality_sha256'] = quality_digest(quality)
    before = json.dumps(item, ensure_ascii=False, sort_keys=True)
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', item, text, dry_run=True)
    assert json.dumps(item, ensure_ascii=False, sort_keys=True) == before
    assert not list(snapshots.root.rglob('manifest.json'))


@pytest.mark.parametrize('mutation', ['payload_only', 'remove_payload', 'payload_and_digest'])
def test_m1_quality_snapshot_rejects_report_tamper_with_body_and_pdf_unchanged(snapshots, mutation):
    from tools.infra.persistence.review_snapshot import quality_digest

    item = quality_candidate()
    item['snapshot'] = snapshots.create('run-1', item, '# 仅使用已有事实', dry_run=True)
    sealed = snapshots.load('run-1', item)
    md = Path(sealed['resume_markdown_path'])
    pdf = Path(sealed['resume_path'])
    original_md, original_pdf = md.read_bytes(), pdf.read_bytes()
    if mutation == 'remove_payload':
        del item['quality_snapshot']
    else:
        item['quality_snapshot']['quality_report']['gap_tasks'].append('替换后的审核依据')
        if mutation == 'payload_and_digest':
            item['quality_sha256'] = quality_digest(item['quality_snapshot'])
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.load('run-1', item)
    assert md.read_bytes() == original_md
    assert pdf.read_bytes() == original_pdf

def guided_scorecard(content='# 仅使用已有事实'):
    from tools.domain.models import Scorecard

    item = quality_candidate(content)
    return Scorecard(
        resume_version=item['resume_version'], job_profile_id=item['job_profile_id'],
        total_score=.99, dimension_scores={},
        quality_report=item['quality_snapshot']['quality_report'],
    )


def test_m1_scorecard_capture_is_bound_after_one_pdf_export(snapshots, monkeypatch):
    from tools.infra.persistence import review_snapshot

    text = '# 仅使用已有事实'
    item, scorecard = candidate(), guided_scorecard(text)
    expected = json.loads(json.dumps(scorecard.quality_report))
    exports = []
    def export(md, pdf):
        exports.append(md.read_text())
        assert 'quality_snapshot' not in item and 'quality_sha256' not in item
        scorecard.quality_report['gap_tasks'].append('导出后改写的非原报告内容')
        pdf.write_bytes(b'%PDF-test-only')
    monkeypatch.setattr(review_snapshot, '_render_pdf', export)
    monkeypatch.setattr('urllib.request.urlopen', lambda *_a, **_k: pytest.fail('固定报告不调用模型'))
    item['snapshot'] = snapshots.create('run-1', item, text, dry_run=True, scorecard=scorecard)
    assert exports == [text]
    assert item['quality_snapshot']['quality_report'] == expected
    assert scorecard.quality_report != expected
    restored = snapshots.load('run-1', item)
    assert restored['candidate']['quality_sha256'] == item['quality_sha256']
    assert item['quality_snapshot']['resume_sha256'] == restored['markdown_sha256']
    assert item['quality_snapshot']['pdf_sha256'] == restored['pdf_sha256']


@pytest.mark.parametrize('failure', ['export', 'manifest'])
def test_m1_scorecard_snapshot_failure_does_not_publish_or_mutate_candidate(snapshots, monkeypatch, failure):
    from tools.infra.persistence import review_snapshot

    item, scorecard = candidate(), guided_scorecard()
    before = json.loads(json.dumps(item))
    if failure == 'export':
        def fail(*_args):
            raise RuntimeError('synthetic export failure')
        monkeypatch.setattr(review_snapshot, '_render_pdf', fail)
    else:
        write = Path.write_bytes
        def fail_manifest(path, data):
            if path.name == 'manifest.json':
                raise OSError('synthetic manifest failure')
            return write(path, data)
        monkeypatch.setattr(Path, 'write_bytes', fail_manifest)
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', item, '# 仅使用已有事实', dry_run=True, scorecard=scorecard)
    assert item == before
    assert not list(snapshots.root.rglob('manifest.json'))


@pytest.mark.parametrize('mutation', ['version', 'job', 'missing_report', 'invalid_report'])
def test_m1_scorecard_identity_and_report_required_before_export(snapshots, monkeypatch, mutation):
    from dataclasses import replace
    from tools.infra.persistence import review_snapshot

    scorecard = guided_scorecard()
    changes = {
        'version': {'resume_version': 'another-version'},
        'job': {'job_profile_id': 'another-profile'},
        'missing_report': {'quality_report': None},
        'invalid_report': {'quality_report': ['not a report']},
    }
    scorecard = replace(scorecard, **changes[mutation])
    item = candidate()
    monkeypatch.setattr(review_snapshot, '_render_pdf', lambda *_: pytest.fail('身份不符不能先导出'))
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', item, '# 仅使用已有事实', dry_run=True, scorecard=scorecard)
    assert 'quality_snapshot' not in item and 'quality_sha256' not in item
    assert not list(snapshots.root.rglob('manifest.json'))


def test_m1_scorecard_cannot_overwrite_conflicting_bound_quality(snapshots):
    from tools.infra.persistence.review_snapshot import quality_digest

    item = quality_candidate()
    item['quality_snapshot']['pdf_sha256'] = '0' * 64
    item['quality_sha256'] = quality_digest(item['quality_snapshot'])
    before = json.loads(json.dumps(item))
    with pytest.raises(ValueError, match='review_snapshot'):
        snapshots.create('run-1', item, '# 仅使用已有事实', dry_run=True, scorecard=guided_scorecard())
    assert item == before
    assert not list(snapshots.root.rglob('manifest.json'))
