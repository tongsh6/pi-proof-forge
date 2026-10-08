import json
from pathlib import Path
import pytest
from tools.acceptance import external_l3
from tools.sidecar.handlers import submission
from tests.unit.infra.test_submission_evidence import fixture_submission


def saved_case(root,monkeypatch):
    runbook=root/'docs/runbooks/external-l3-live-run.md';runbook.parent.mkdir(parents=True)
    runbook.write_text((Path(__file__).resolve().parents[2]/'docs/runbooks/external-l3-live-run.md').read_text())
    log,_,archive=fixture_submission(root)
    monkeypatch.setattr(submission,'_SUBMISSIONS_DIR',root/'outputs/submissions')
    monkeypatch.setattr(submission,'_FEEDBACK_ITERATIONS_DIR',root/'outputs/feedback_iterations')
    feedback=submission.handle_feedback_create_iteration({'meta':{'correlation_id':'test'},'source_run_id':log.parent.name,
        'selected_actions':['acknowledge_and_skip'],'feedback_source':'user_note','user_notes':'合成验收样例'})
    page=root/'outputs/acceptance/synthetic/page.json';page.parent.mkdir(parents=True)
    page.write_text(json.dumps({'status':'completed','observed_submission_ids':[log.parent.name],
        'native_page_acceptance':{'surface':'tauri_desktop_app','actions':['select_submission','view_evidence','save_personal_feedback','restart_app','read_saved_feedback'],
        'feedback_records':{log.parent.name:[feedback['iteration_id']]},
        'restart_verified':True,'feedback_readback_verified':True}}))
    return log,archive,page


def build(root,sid,page):
    return external_l3.build_saved_app_validation(root=root,run_id='saved_test',generated_at='test',submission_ids=[sid],page_evidence=[page])


def test_saved_acceptance_reuses_protected_evidence_without_sending_or_rewriting(tmp_path,monkeypatch):
    log,archive,page=saved_case(tmp_path,monkeypatch);before=(log.read_bytes(),archive.read_bytes())
    monkeypatch.setattr(external_l3.subprocess,'run',lambda *a,**k:pytest.fail('不得启动发送'))
    monkeypatch.setenv('PIPF_EXTERNAL_L3_AUTHORIZED','true')
    result=build(tmp_path,log.parent.name,page)
    assert result['status']=='external_validated' and result['validation_mode']=='saved_app_records'
    assert result['external_submission_attempted'] is False
    assert result['submissions'][0]['feedback_records']
    assert result['submissions'][0]['evidence']['status']=='verified'
    paths=external_l3.write_external_l3_validation(root=tmp_path,run_id='saved_test',validation=result)
    assert all(p.is_file() for p in paths)
    assert '合成验收样例' not in paths[0].read_text()
    assert '只读' in paths[1].read_text()
    assert (log.read_bytes(),archive.read_bytes())==before


@pytest.mark.parametrize('failure',['receipt','page','feedback','duplicate','outside','surface','actions','feedback_identity'])
def test_saved_validation_cannot_treat_missing_or_tampered_records_as_complete(tmp_path,monkeypatch,failure):
    log,archive,page=saved_case(tmp_path,monkeypatch)
    if failure=='receipt':archive.write_text('{}')
    if failure=='page':page.write_text('{}')
    if failure=='feedback':
        record=next((tmp_path/'outputs/feedback_iterations').glob('*/iteration_record.json'))
        data=json.loads(record.read_text());data['source_snapshot_sha256']='bad';record.write_text(json.dumps(data))
    if failure=='duplicate':
        with pytest.raises(ValueError,match='invalid_saved_submission_ids'):
            external_l3.build_saved_app_validation(root=tmp_path,run_id='t',generated_at='test',submission_ids=[log.parent.name]*2,page_evidence=[page])
        return
    if failure in {'surface','actions','feedback_identity'}:
        payload=json.loads(page.read_text());native=payload['native_page_acceptance']
        if failure=='surface':native['surface']='handler_only'
        if failure=='actions':native['actions']=['unrelated_action']
        if failure=='feedback_identity':native['feedback_records']={log.parent.name:['another']}
        page.write_text(json.dumps(payload))
    if failure=='outside':page=tmp_path/'outside.json';page.write_text('{}')
    result=build(tmp_path,log.parent.name,page)
    assert result['status']=='saved_evidence_incomplete'
    assert result['p0_017_completion_gate']['p0_017_complete'] is False
    assert result['external_submission_attempted'] is False


def test_historical_unknown_feedback_does_not_block_current_verified_feedback(tmp_path,monkeypatch):
    log,archive,page=saved_case(tmp_path,monkeypatch)
    success=log.read_bytes();payload=json.loads(success);payload['status']='unknown';log.write_text(json.dumps(payload))
    historical=submission.handle_feedback_create_iteration({'meta':{'correlation_id':'history'},'source_run_id':log.parent.name,
        'selected_actions':['acknowledge_and_skip'],'feedback_source':'user_note','user_notes':'合成未知状态复盘'})
    log.write_bytes(success)
    result=build(tmp_path,log.parent.name,page)
    assert result['status']=='external_validated',result['p0_017_completion_gate']
    records=result['submissions'][0]['feedback_records']
    assert next(r for r in records if r['iteration_id']==historical['iteration_id'])['historical'] is True


def test_saved_validation_requires_current_runbook_contract(tmp_path,monkeypatch):
    log,_,page=saved_case(tmp_path,monkeypatch)
    (tmp_path/'docs/runbooks/external-l3-live-run.md').unlink()
    result=build(tmp_path,log.parent.name,page)
    assert result['status']=='saved_evidence_incomplete'
    assert 'saved_app_runbook_unavailable' in result['p0_017_completion_gate']['completion_blockers']
