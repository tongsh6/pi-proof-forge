import json
import pytest
from tools.sidecar.handlers import agent,native_pdf,daily_delivery
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore


def old_queue(tmp_path,monkeypatch):
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path);monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs');monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    candidate={'job_lead_id':'lead','company':'公司','position':'职位','delivery_kind':'generated_pdf','platform':'liepin','status':'pending','jd_status':'complete_reviewed','job_url':'https://www.liepin.com/job/123.shtml','platform_job_id':'123','platform_job_type':'2'}
    candidate['snapshot']=ReviewSnapshotStore(agent._AGENT_RUN_DIR).create('run',candidate,'# 不完整旧稿',dry_run=False,pdf_content=b'%PDF-1.7\nold\n%%EOF')
    q={'run_id':'run','quick_run_id':'quick','candidates':[candidate]};path=agent._get_queue_file('run');agent._save_queue(path,q)
    return path,q


def test_old_pending_pdf_cannot_upload_without_full_content_review(tmp_path,monkeypatch):
    path,q=old_queue(tmp_path,monkeypatch)
    with pytest.raises(ValueError):native_pdf.handle_begin_upload({'meta':{'correlation_id':'test'},'run_id':'run','accept_account_effects':True})
    assert 'pdf_upload' not in agent._load_queue(path)


def test_daily_inventory_does_not_authorize_legacy_unreviewed_content(tmp_path,monkeypatch):
    path,q=old_queue(tmp_path,monkeypatch)
    assert daily_delivery.handle_status({})['candidates']==[]


def test_content_failure_never_sets_final_send_flag(tmp_path,monkeypatch):
    path,q=old_queue(tmp_path,monkeypatch);sealed=ReviewSnapshotStore(agent._AGENT_RUN_DIR).load('run',q['candidates'][0])
    q['attachment_binding']={'pdf_sha256':sealed['pdf_sha256'],'file_id':'file','filename':'cv.pdf','attachment_id':'attachment'}
    q['pdf_delivery']={'state':'resume_interaction_pending','attempt_id':'attempt'};agent._save_queue(path,q)
    from types import SimpleNamespace
    monkeypatch.setattr(daily_delivery,'store',lambda:SimpleNamespace(write_permit=lambda *a,**k:{}))
    monkeypatch.setattr(native_pdf,'_confirmation_matches',lambda _:True)
    with pytest.raises(ValueError):native_pdf.handle_pdf_interaction_packet({'meta':{},'run_id':'run','action':'send'})
    assert not agent._load_queue(path)['pdf_delivery'].get('final_send_started')
