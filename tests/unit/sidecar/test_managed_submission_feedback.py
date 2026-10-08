import json
from pathlib import Path
import pytest
from tools.sidecar.handlers import submission as handler
from tests.unit.infra.test_submission_evidence import fixture_submission


@pytest.fixture(params=['platform_default','generated_pdf'])
def managed(tmp_path,monkeypatch,request):
    monkeypatch.chdir(tmp_path)
    log,q,archive=fixture_submission(tmp_path,request.param)
    monkeypatch.setattr(handler,'_SUBMISSIONS_DIR',tmp_path/'outputs/submissions')
    monkeypatch.setattr(handler,'_FEEDBACK_ITERATIONS_DIR',tmp_path/'outputs/feedback_iterations')
    return log,q,archive


def params(log,**extra):
    return {'meta':{'correlation_id':'t'},'source_run_id':log.parent.name,**extra}


def test_real_submission_feedback_is_bound_and_does_not_claim_check_mode(managed):
    log,q,_=managed
    detail=handler.handle_submission_detail({'meta':{'correlation_id':'t'},'submission_id':log.parent.name})['submission']
    assert detail['evidence']['status']=='verified'
    feedback=handler.handle_feedback_list(params(log))
    assert feedback['items'][0]['source_type']=='submission_receipt'
    assert feedback['items'][0]['severity_or_priority']=='info'
    assert feedback['items'][0]['recommended_next_action']=='acknowledge_and_skip'
    assert feedback['source_binding']['resume_version_id']=='version_test'


def test_manual_feedback_survives_readback_and_preserves_originals(managed):
    log,q,archive=managed;before=(log.read_bytes(),archive.read_bytes())
    result=handler.handle_feedback_create_iteration(params(log,selected_actions=['add_or_edit_evidence_card'],
        feedback_source='user_note',user_notes='合成测试：下一轮补充证据，不代表招聘方反馈。'))
    record=result['iteration']
    assert record['source_binding']['job_lead_id']=='lead_test'
    assert record['previous_resume_version_id']=='version_test'
    assert record['feedback_source']=='user_note'
    assert record['new_resume_version_id_or_none']=='' and record['real_submit_disabled']
    listed=handler.handle_feedback_list(params(log))
    assert listed['iterations'][0]['iteration_id']==result['iteration_id']
    assert record['source_snapshot_sha256']
    assert (log.read_bytes(),archive.read_bytes())==before
    assert Path(result['record_path']).stat().st_mode&0o777==0o600


def test_managed_regeneration_records_plan_and_never_copies_a_fake_version(managed):
    log,_,_=managed
    result=handler.handle_feedback_create_iteration(params(log,selected_actions=['regenerate_resume_from_existing_evidence'],
        feedback_source='manual_recruiter',user_notes='合成测试回复'))['iteration']
    assert result['new_resume_version_id_or_none']==''
    assert result['next_recommended_step']=='quick_run'
    assert result['next_quick_run_candidate']['job_profile_id']=='profile_test'
    assert 'new_resume_path' not in result['affected_artifacts']


def test_feedback_cannot_import_another_submission_or_invent_claims(managed):
    log,_,_=managed
    foreign=handler.handle_feedback_list(params(log))['items'];foreign[0]['source_run_id']='another'
    with pytest.raises(ValueError,match='feedback_source_mismatch'):
        handler.handle_feedback_create_iteration(params(log,selected_actions=['acknowledge_and_skip'],user_notes='x',source_feedback_items=foreign))
    with pytest.raises(ValueError,match='feedback_note_required'):
        handler.handle_feedback_create_iteration(params(log,selected_actions=['update_job_target'],feedback_source='manual_recruiter',user_notes=''))
    with pytest.raises(ValueError,match='feedback_claims_require_generation'):
        handler.handle_feedback_create_iteration(params(log,selected_actions=['regenerate_resume_from_existing_evidence'],user_notes='x',new_or_updated_claims=['捏造'],evidence_card_ids_added_or_updated=['fake']))


def test_legacy_record_list_recovers_missing_identity_from_approved_snapshot(managed):
    log,_,_=managed;payload=json.loads(log.read_text())
    for field in ['company','position','resume_version']:payload['input_artifacts'].pop(field,None)
    log.write_text(json.dumps(payload))
    item=handler._submission_item(log)
    assert item['company']=='合成公司' and item['position']=='合成岗位'
