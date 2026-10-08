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
