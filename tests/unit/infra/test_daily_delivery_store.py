"""真实 SQLite 上验证授权、并发、上海日界与历史防重。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore


def setup_store(tmp_path):
    from tools.infra.persistence.daily_delivery import DailyDeliveryStore
    clock = [datetime(2026, 10, 5, 1, tzinfo=timezone.utc)]
    store = DailyDeliveryStore(tmp_path/'attempts.sqlite3', clock=lambda: clock[0])
    scope = [dict(run_id=f'r{i}', job_key=f'j{i}', pdf_sha256=str(i)*64, channel='liepin', delivery_kind='generated_pdf', company='公司', position=f'岗位{i}') for i in range(8)]
    return store, clock, scope


def authorize(store, scope, maximum=3):
    draft=store.save_draft(scope, maximum, '09:00', '2026-10-08T16:00:00Z')
    return store.set_status(draft['id'], 'active', confirmed=True)


def test_draft_is_inert_and_active_scope_is_immutable(tmp_path):
    s,_,scope=setup_store(tmp_path)
    d=s.save_draft(scope,3,'09:00','2026-10-08T16:00:00Z')
    assert s.claim()['reason']=='daily_not_active'
    with pytest.raises(ValueError,match='daily_confirmation_required'):s.set_status(d['id'],'active')
    s.set_status(d['id'],'active',confirmed=True)
    with pytest.raises(ValueError,match='daily_authorization_immutable'):s.save_draft(scope[:1],1,'10:00','2026-10-09T16:00:00Z')
    with pytest.raises(ValueError):s.set_status(d['id'],'revoked');s.set_status(d['id'],'active',confirmed=True)


def test_single_daily_claim_across_connections_and_restart(tmp_path):
    s,_,scope=setup_store(tmp_path);authorize(s,scope)
    def claim(_):
        from tools.infra.persistence.daily_delivery import DailyDeliveryStore
        return DailyDeliveryStore(s.path,clock=s.clock).claim()
    with ThreadPoolExecutor(max_workers=6) as p:results=list(p.map(claim,range(6)))
    assert sum(r.get('claimed',False) for r in results)==1
    assert s.claim()['reason']=='daily_already_run'
    assert len(s.status()['history'])==1


def test_pause_revoke_expiry_and_midnight_checked_before_next_write(tmp_path):
    s,clock,scope=setup_store(tmp_path);grant=authorize(s,scope);run=s.claim();s.check_write(run['id'],'r0','0'*64)
    s.set_status(grant['id'],'paused')
    with pytest.raises(ValueError,match='daily_not_active'):s.check_write(run['id'],'r0','0'*64)
    s.set_status(grant['id'],'active',confirmed=True)
    with pytest.raises(ValueError,match='daily_scope_mismatch'):s.check_write(run['id'],'r0','wrong')
    clock[0]=datetime(2026,10,5,16,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='daily_date_changed'):s.check_write(run['id'],'r0','0'*64)
    clock[0]=datetime(2026,10,9,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='daily_expired'):s.check_write(run['id'],'r0','0'*64)


def test_daily_cap_and_unknown_block_across_days_and_channels(tmp_path):
    s,clock,scope=setup_store(tmp_path);authorize(s,scope);run=s.claim()
    for i in range(3):
        a=s.reserve_daily(run['id'],f'r{i}',f'j{i}',str(i)*64);s.finish(a,'success')
    assert s.status()['today']['confirmed']==3
    with pytest.raises(ValueError,match='daily_scope_mismatch'):s.reserve_daily(run['id'],'r3','j3','3'*64)
    with pytest.raises(ValueError,match='daily_limit_reached'):DeliveryAttemptStore(s.path,clock=s.clock).reserve('other','manual','sha')
    s.finish_cycle(run['id'],'completed')
    clock[0]=datetime(2026,10,5,16,tzinfo=timezone.utc);new=s.claim(force=True)
    assert new['claimed'];assert s.has_attempt('j0')
    assert 'r0' not in [i['run_id'] for i in new['items']]
    a=s.reserve_daily(new['id'],'r3','j3','3'*64);s.finish(a,'unknown');s.finish_cycle(new['id'],'receipt_unknown')
    clock[0]=datetime(2026,10,6,16,tzinfo=timezone.utc)
    assert s.claim(force=True)['reason']=='daily_unresolved'
    assert s.status()['today']['confirmed']==0


def test_missed_days_not_replayed_and_empty_pool_records_shortfall(tmp_path):
    s,clock,scope=setup_store(tmp_path);authorize(s,scope[:1]);run=s.claim();a=s.reserve_daily(run['id'],'r0','j0','0'*64);s.finish(a,'success');s.finish_cycle(run['id'],'candidate_shortfall')
    clock[0]=datetime(2026,10,7,1,tzinfo=timezone.utc);new=s.claim()
    assert new['claimed'] and new['items']==[]
    s.finish_cycle(new['id'],'candidate_shortfall')
    assert {h['day'] for h in s.status()['history']}=={'2026-10-05','2026-10-07'}


def test_manual_concurrency_cannot_exceed_shared_daily_cap(tmp_path):
    s,_,scope=setup_store(tmp_path);authorize(s,scope)
    def reserve(i):
        try:return s.reserve(f'other{i}','manual','sha')
        except ValueError as e:assert str(e) in {'daily_unresolved','daily_limit_reached'}
    with ThreadPoolExecutor(max_workers=6) as p:slots=list(p.map(reserve,range(6)))
    assert 1<=sum(bool(v) for v in slots)<=3
    assert s.status()['today']['occupied']<=3


def test_no_send_release_does_not_remove_global_job_dedup_for_unknown(tmp_path):
    s,_,scope=setup_store(tmp_path);authorize(s,scope);run=s.claim();a=s.reserve_daily(run['id'],'r0','j0','0'*64)
    s.finish(a,'unknown');s.finish_cycle(run['id'],'receipt_unknown')
    assert s.claim()['reason'] in {'daily_already_run','daily_unresolved'}
    assert s.has_attempt('j0')


def test_single_submission_final_write_cannot_use_yesterdays_slot(tmp_path):
    s,clock,scope=setup_store(tmp_path);authorize(s,scope)
    attempt=s.reserve('manual','manual-run','sha')
    clock[0]=datetime(2026,10,5,16,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='daily_date_changed'):s.write_permit(None,'manual-run','sha',attempt_id=attempt)


def test_history_retains_batch_scope_and_observed_counts_after_restart(tmp_path):
    from tools.infra.persistence.daily_delivery import DailyDeliveryStore
    s,clock,scope=setup_store(tmp_path);authorize(s,scope[:3]);run=s.claim()
    one=s.reserve_daily(run['id'],'r0','j0','0'*64);s.finish(one,'success')
    two=s.reserve_daily(run['id'],'r1','j1','1'*64);s.finish(two,'unknown')
    s.finish_cycle(run['id'],'daily_receipt_unknown')
    restored=DailyDeliveryStore(s.path,clock=lambda:clock[0]).status()['history'][0]
    assert restored['items']==scope[:3]
    assert restored['maximum']==3 and restored['confirmed']==1 and restored['unresolved']==1
    assert restored['started_at'] and restored['finished_at']
