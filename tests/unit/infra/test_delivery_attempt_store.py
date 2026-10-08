import concurrent.futures

import pytest


def test_only_one_process_slot_and_restart_blocks_duplicate(tmp_path):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    path = tmp_path / 'attempts.sqlite3'
    def reserve(i):
        return DeliveryAttemptStore(path).reserve('same-job', f'run-{i}', 'pdf-hash')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        slots = list(pool.map(reserve, range(8)))
    assert len([slot for slot in slots if slot]) == 1
    assert DeliveryAttemptStore(path).reserve('same-job', 'another-run', 'changed-pdf') is None


@pytest.mark.parametrize('status', ['success', 'failed', 'unknown'])
def test_terminal_outcomes_never_auto_retry(tmp_path, status):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    store = DeliveryAttemptStore(tmp_path / 'attempts.sqlite3')
    attempt = store.reserve('same-job', 'run', 'pdf')
    store.finish(attempt, status)
    assert store.reserve('same-job', 'new-run', 'new-pdf') is None
    with pytest.raises(ValueError):
        store.finish(attempt, 'success')


def test_broken_journal_is_not_reset(tmp_path):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    path = tmp_path / 'attempts.sqlite3'
    path.write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='delivery_state_unavailable'):
        DeliveryAttemptStore(path).reserve('job', 'run', 'pdf')


def test_authorized_batch_counts_prior_external_application_and_caps_concurrent_attempts(tmp_path):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    path=tmp_path/'attempts.sqlite3'
    store=DeliveryAttemptStore(path)
    old1=store.reserve('prior-external','old-1','resume')
    old2=store.reserve('prior-app','old-2','resume')
    store.finish(old1,'success');store.finish(old2,'success')
    store.authorize_batch('validation-10',10,[old1,old2])
    def reserve(i):
        try: return DeliveryAttemptStore(path).reserve(f'job-{i}',f'run-{i}','pdf' if i%2 else 'default')
        except ValueError as exc:
            assert str(exc)=='delivery_batch_limit_reached'
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        slots=list(pool.map(reserve, range(12)))
    assert sum(bool(slot) for slot in slots)==8
    assert DeliveryAttemptStore(path).active_batch()['remaining']==0
    store.authorize_batch('validation-10',10,[old1,old2])
    assert store.active_batch()['consumed']==10
    with pytest.raises(ValueError):store.authorize_batch('validation-10',11,[old1,old2])
    with pytest.raises(ValueError):store.authorize_batch('replacement',10,[])


def test_unknown_pauses_batch_and_no_send_releases_only_its_own_slot(tmp_path):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    store=DeliveryAttemptStore(tmp_path/'attempts.sqlite3')
    store.authorize_batch('batch',2,[])
    a=store.reserve('a','r','pdf');store.finish(a,'not_submitted')
    assert store.active_batch()['remaining']==2
    a=store.reserve('a','r','pdf');store.finish(a,'unknown')
    with pytest.raises(ValueError,match='delivery_batch_unresolved'):
        store.reserve('b','r2','pdf')
    assert store.active_batch()['remaining']==1
    store.resolve_unknown(a,'r','pdf','success')
    assert store.reserve('b','r2','pdf')


def test_supplementary_pdf_authorization_is_separate_and_cannot_fund_default_resume(tmp_path):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    import sqlite3
    path=tmp_path/'attempts.sqlite3';store=DeliveryAttemptStore(path)
    store.authorize_batch('old',1,[])
    a=store.reserve('old-job','old-run','old-resume');store.finish(a,'success')
    store.authorize_supplementary_batch('pdf-extra','old',1,'generated_pdf','user-explicit-pdf-one')
    current=store.active_batch()
    assert current['authorized_max']==1 and current['consumed']==0
    assert current['allowed_delivery_kind']=='generated_pdf'
    with pytest.raises(ValueError,match='delivery_batch_route_not_authorized'):
        store.reserve('default-job','run','resume',delivery_kind='platform_default')
    assert store.active_batch()['remaining']==1
    b=store.reserve('new-pdf-job','pdf-run','pdf-sha',delivery_kind='generated_pdf')
    store.finish(b,'success')
    with pytest.raises(ValueError,match='delivery_batch_limit_reached'):
        store.reserve('another-pdf-job','pdf-run2','pdf-sha',delivery_kind='generated_pdf')
    store.authorize_supplementary_batch('pdf-extra','old',1,'generated_pdf','user-explicit-pdf-one')
    assert store.active_batch()['remaining']==0
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT authorized_max,active FROM delivery_batches WHERE batch_id='old'").fetchone()==(1,0)
        assert connection.execute("SELECT state,batch_id FROM attempts WHERE attempt_id=?",(a,)).fetchone()==('success','old')
    with pytest.raises(ValueError):
        store.authorize_supplementary_batch('pdf-replacement','pdf-extra',1,'generated_pdf','user-explicit-pdf-one')


def test_supplementary_authorization_cannot_reclassify_unused_or_unknown_old_slots(tmp_path):
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    store=DeliveryAttemptStore(tmp_path/'attempts.sqlite3')
    store.authorize_batch('old',1,[])
    with pytest.raises(ValueError):store.authorize_supplementary_batch('new','old',1,'generated_pdf','grant')
    attempt=store.reserve('job','run','resume');store.finish(attempt,'unknown')
    with pytest.raises(ValueError):store.authorize_supplementary_batch('new','old',1,'generated_pdf','grant')
    assert store.active_batch()['batch_id']=='old'
