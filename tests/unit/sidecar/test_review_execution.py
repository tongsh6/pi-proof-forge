import json

import pytest

from tools.sidecar.handlers import agent
from tests.unit.infra.test_review_snapshot import candidate


@pytest.fixture
def review(tmp_path, monkeypatch):
    from tools.infra.persistence import review_snapshot
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent, '_PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(agent, '_AGENT_RUN_DIR', tmp_path / 'outputs/agent_runs')
    monkeypatch.setattr(agent, '_REVIEW_QUEUE_DIR', tmp_path / 'outputs/review_queue')
    monkeypatch.setattr(review_snapshot, '_render_pdf', lambda src, dst: dst.write_bytes(b'%PDF-test-only'))
    def create(*, dry_run=True, snapshot=True):
        item = {**candidate(), 'status': 'pending', 'round_index': 0}
        if snapshot:
            item['snapshot'] = review_snapshot.ReviewSnapshotStore(agent._AGENT_RUN_DIR).create(
                'run-1', item, '# 仅使用已有事实', dry_run=dry_run)
        queue = agent._get_queue_file('run-1')
        agent._save_queue(queue, {'run_id':'run-1', 'candidates':[item]})
        agent._save_agent_run(agent._get_agent_run_file('run-1'), {'run':{'run_id':'run-1','status':'REVIEW_PENDING'},'events':[]})
        return queue
    return create


def decide(action='approve', **extra):
    return agent.handle_submit_review({'meta':{'correlation_id':'test'}, 'run_id':'run-1',
        'decisions':[{'job_lead_id':'lead-1','action':action}], **extra})


def test_check_approval_resumes_exact_snapshot_without_submission(review, monkeypatch):
    queue = review()
    monkeypatch.setattr('tools.channels.liepin.LiepinChannel.deliver', lambda *_: pytest.fail('检查不能进入渠道'))
    pending = agent.handle_get_pending_review({'meta':{'correlation_id':'test'},'run_id':'run-1'})['candidates'][0]
    assert pending['snapshot_status'] == 'ready'
    assert pending['resume_preview'] == '# 仅使用已有事实'
    result = decide()
    assert result['accepted'] == 1
    assert result['delivery_results'][0]['code'] == 'checked_not_submitted'
    assert result['delivery_results'][0]['success'] is False
    assert json.loads(queue.read_text())['candidates'][0]['status'] == 'approved'
    repeat = decide()
    assert repeat['accepted'] == 0
    assert repeat['delivery_results'] == result['delivery_results']
    assert agent.handle_agent_get({'meta':{'correlation_id':'test'},'run_id':'run-1'})['run']['status'] == 'REVIEWED_CHECK_ONLY'


def test_official_approval_still_blocks_unverified_send_contract(review, monkeypatch):
    review(dry_run=False)
    monkeypatch.setattr('tools.channels.liepin.LiepinChannel.deliver', lambda *_: pytest.fail('禁止退回旧浏览器渠道'))
    result = decide()
    assert result['delivery_results'][0]['code'] == 'official_delivery_contract_unverified'
    assert result['delivery_results'][0]['success'] is False
    assert agent.handle_agent_get({'meta':{'correlation_id':'test'},'run_id':'run-1'})['run']['status'] == 'DELIVERY_BLOCKED'


def test_missing_or_tampered_snapshot_cannot_be_approved(review):
    queue = review(snapshot=False)
    with pytest.raises(ValueError, match='review_snapshot'):
        decide()
    assert json.loads(queue.read_text())['candidates'][0]['status'] == 'pending'
    assert decide('reject')['accepted'] == 0


def test_decision_validation_is_all_or_nothing(review):
    queue = review()
    with pytest.raises(ValueError):
        decide(decisions=[{'job_lead_id':'lead-1','action':'approve'},
                          {'job_lead_id':'unknown','action':'approve'}])
    assert json.loads(queue.read_text())['candidates'][0]['status'] == 'pending'


def test_rejected_candidate_cannot_be_reapproved_and_run_path_is_validated(review):
    review()
    decide('reject')
    with pytest.raises(ValueError):
        decide('approve')
    with pytest.raises(ValueError):
        agent.handle_submit_review({'meta':{'correlation_id':'test'},'run_id':'../outside','decisions':[]})


def test_new_exclusion_before_approval_blocks_resumption(review):
    review()
    (agent._PROJECT_ROOT / 'policy.yaml').write_text('exclusion_list:\n  - "exact:测试公司"\n')
    result = decide()
    assert result['delivery_results'][0]['code'] == 'excluded_company'
    assert result['delivery_results'][0]['success'] is False


def test_unknown_delivery_pauses_remaining_approved_batch(review, monkeypatch):
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    path = review(dry_run=False)
    queue = json.loads(path.read_text())
    second = {**queue['candidates'][0], 'job_lead_id':'lead-2'}
    second['snapshot'] = ReviewSnapshotStore(agent._AGENT_RUN_DIR).create('run-1', second, '# 第二份', dry_run=False)
    queue['candidates'].append(second)
    agent._save_queue(path, queue)
    calls = []
    def unknown(run, item, root):
        calls.append(item['job_lead_id'])
        return {'job_lead_id':item['job_lead_id'],'success':False,'submission_id':'','status':'unknown','code':'delivery_result_unknown'}
    monkeypatch.setattr('tools.orchestration.approved_delivery.resume_approved_candidate', unknown)
    decide(decisions=[{'job_lead_id':'lead-1','action':'approve'},{'job_lead_id':'lead-2','action':'approve'}])
    assert calls == ['lead-1']
    pending = agent.handle_get_pending_review({'meta':{'correlation_id':'test'},'run_id':'run-1'})['candidates']
    assert [c['job_lead_id'] for c in pending] == ['lead-2']
    with pytest.raises(ValueError, match='unresolved'):
        decide(decisions=[{'job_lead_id':'lead-2','action':'approve'}])


def test_restore_uses_latest_updated_queue_not_lexical_name(review):
    import os
    queue = review()
    old = queue.parent / 'zzz-older.json'
    old.write_text(json.dumps({'run_id':'zzz-older','candidates':[]}))
    os.utime(old, (1,1))
    result = agent.handle_get_pending_review({'meta':{'correlation_id':'test'}})
    assert result['run_id'] == 'run-1'


def test_existing_review_queue_cannot_be_replaced_by_new_candidates(review):
    queue = review()
    before = queue.read_bytes()
    with pytest.raises(ValueError, match='review_queue_already_exists'):
        agent.handle_create_review_candidates({'meta':{'correlation_id':'test'},'run_id':'run-1','candidates':[]})
    assert queue.read_bytes() == before


def test_pipeline_cannot_overwrite_existing_approval_queue(review):
    from tools.orchestration.agent_loop import _write_review_queue
    queue = review()
    before = queue.read_bytes()
    with pytest.raises(ValueError, match='review_queue_already_exists'):
        _write_review_queue('run-1', [])
    assert queue.read_bytes() == before


def test_external_confirmation_is_not_app_verified_completion(review):
    path = review(dry_run=False)
    queue = json.loads(path.read_text())
    item = queue['candidates'][0]
    item.update(status='approved',delivery={'job_lead_id':'lead-1','success':True,'status':'success',
                 'code':'submitted','submission_id':'api-1','receipt_source':'website_history'})
    agent._save_queue(path,queue)
    agent._sync_review_run('run-1',queue,[item['delivery']])
    fetched = agent.handle_agent_get({'meta':{'correlation_id':'test'},'run_id':'run-1'})['run']
    assert fetched['deliveries_completed'] == 1  # 保留真实发生的投递事实/额度。
    assert fetched['app_verified_deliveries'] == 0
    assert fetched['externally_confirmed_deliveries'] == 1
    assert fetched['status'] == 'EXTERNAL_CONFIRMATION_ONLY'
    result = agent.handle_get_pending_review({'meta':{'correlation_id':'test'},'run_id':'run-1'})['delivery_results'][0]
    assert result['code'] == 'external_observation_confirmed'
    assert result['app_verified'] is False


@pytest.mark.parametrize('source,verified,external,status', [
    ('app_api', 1, 0, 'DONE'), ('website_history', 0, 1, 'EXTERNAL_CONFIRMATION_ONLY'),
    ('', 0, 0, 'DELIVERY_BLOCKED')])
def test_legacy_readback_classifies_provenance_without_changing_history(review, source, verified, external, status):
    review()
    result = {'job_lead_id':'lead-1','success':True,'status':'success','code':'submitted',
              'submission_id':'receipt','receipt_source':source}
    path = agent._get_agent_run_file('run-1')
    payload = {'run':{'run_id':'run-1','status':'DONE','delivery_results':[result]},'events':[]}
    agent._save_agent_run(path, payload)
    before = path.read_bytes()
    run = agent.handle_agent_get({'meta':{'correlation_id':'x'},'run_id':'run-1'})['run']
    assert (run['app_verified_deliveries'], run['externally_confirmed_deliveries'], run['status']) == (verified, external, status)
    assert path.read_bytes() == before



def test_explicit_run_readback_rejects_path_traversal(review):
    review()
    with pytest.raises(ValueError):
        agent.handle_agent_get({'meta':{'correlation_id':'x'},'run_id':'../other'})


def test_batch_status_includes_prior_runs_and_external_confirmation(review):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    review()
    store=DeliveryAttemptStore()
    old=[store.reserve(f'old-{i}',f'prior-{i}','resume') for i in range(2)]
    for item in old:store.finish(item,'success')
    store.authorize_batch('ten-total',10,old)
    result=agent.handle_agent_get({'meta':{'correlation_id':'x'},'run_id':'run-1'})
    assert result['delivery_batch']['authorized_max']==10
    assert result['delivery_batch']['consumed']==2
    assert result['delivery_batch']['remaining']==8


@pytest.mark.parametrize('action',['approve','reject','skip'])
def test_native_pdf_queue_cannot_use_generic_review(review,action):
    path=review();queue=json.loads(path.read_text());queue['quick_run_id']='qr_native'
    agent._save_queue(path,queue);before=path.read_bytes()
    with pytest.raises(ValueError,match='native_pdf_review_required'):
        decide(action)
    assert path.read_bytes()==before


def test_native_pdf_pending_review_returns_original_route(review):
    path=review();queue=json.loads(path.read_text());queue['quick_run_id']='qr_native'
    agent._save_queue(path,queue)
    result=agent.handle_get_pending_review({'meta':{'correlation_id':'t'},'run_id':'run-1'})
    assert result['native_pdf_quick_run_id']=='qr_native'
