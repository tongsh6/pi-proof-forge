import copy
import hashlib
import json
import pytest
from tools.sidecar.handlers import native_pdf as flow,agent
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore


def sample(tmp_path,monkeypatch):
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs')
    md=b'# candidate';pdf=b'%PDF-1.7\nfixture\n%%EOF'
    p=tmp_path/'outputs/score.md';p.parent.mkdir();p.write_text('score')
    score={'resume_sha256':hashlib.sha256(md).hexdigest(),'expression_score':70,'evaluation_version':'assessment-v3',
           'semantic_review':{'fit_score':65,'resume_score':45,'all_requirements_supported':False},
           'traceability':{'status':'verified'},'gap_tasks':['本人职责未确认']}
    p.with_suffix('.json').write_text(json.dumps(score))
    saved={'artifacts':{'scorecard':str(p)},'resume_readiness':{'content_ready':True,'quality_passed':False}}
    return saved,md,pdf,p


def test_quality_is_bound_to_actual_pdf_and_scorecard(tmp_path,monkeypatch):
    saved,md,pdf,path=sample(tmp_path,monkeypatch)
    q=flow._quality_snapshot(saved,md,pdf)
    assert q['quality_passed'] is False and q['content_ready'] is True
    assert (q['matching_score'],q['resume_score'],q['expression_score'])==(65,45,70)
    assert q['gap_tasks']==['本人职责未确认']
    assert q['pdf_sha256']==hashlib.sha256(pdf).hexdigest()
    score=json.loads(path.with_suffix('.json').read_text());score['resume_sha256']='other';path.with_suffix('.json').write_text(json.dumps(score))
    with pytest.raises(ValueError,match='quality_scorecard'):
        flow._quality_snapshot(saved,md,pdf)


def test_public_quality_cannot_be_replaced_after_snapshot_and_legacy_is_unknown(tmp_path,monkeypatch):
    saved,md,pdf,path=sample(tmp_path,monkeypatch)
    quality=flow._quality_snapshot(saved,md,pdf)
    c={'job_lead_id':'lead','company':'公司','position':'岗位','delivery_kind':'generated_pdf',
       'quality_snapshot':quality,'quality_sha256':flow._quality_digest(quality)}
    store=ReviewSnapshotStore(agent._AGENT_RUN_DIR);c['snapshot']=store.create('run',c,md.decode(),dry_run=False,pdf_content=pdf)
    queue={'run_id':'run','candidates':[c]}
    assert flow._public(queue)['quality']['resume_score']==45
    changed=copy.deepcopy(queue);changed['candidates'][0]['quality_snapshot']['quality_passed']=True
    with pytest.raises(ValueError):flow._public(changed)
    changed['candidates'][0]['quality_sha256']=flow._quality_digest(changed['candidates'][0]['quality_snapshot'])
    with pytest.raises(ValueError):flow._public(changed)
    missing=copy.deepcopy(queue);missing['candidates'][0].pop('quality_snapshot')
    with pytest.raises(ValueError,match='quality_snapshot_changed'):flow._public(missing)
    legacy={k:v for k,v in c.items() if k not in ('quality_snapshot','quality_sha256','snapshot')}
    legacy['snapshot']=store.create('legacy',legacy,md.decode(),dry_run=False,pdf_content=pdf)
    assert flow._public({'run_id':'legacy','candidates':[legacy]})['quality']=={'status':'unrecorded'}


def test_rule_mode_quality_pass_does_not_require_semantic_review(tmp_path,monkeypatch):
    saved,md,pdf,path=sample(tmp_path,monkeypatch)
    score=json.loads(path.with_suffix('.json').read_text());score.update(total_score=95,expression_score=100,semantic_review=None,gap_tasks=[])
    path.with_suffix('.json').write_text(json.dumps(score));saved['resume_readiness']['quality_passed']=True
    quality=flow._quality_snapshot(saved,md,pdf)
    assert quality['quality_passed'] is True
    assert quality['matching_mode']=='rule'


def test_missing_bound_quality_cannot_enter_upload_or_change_queue(tmp_path,monkeypatch):
    saved,md,pdf,path=sample(tmp_path,monkeypatch)
    monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    from tools.sidecar.handlers import daily_delivery
    monkeypatch.setattr(daily_delivery,'check_queue_write',lambda *a:{})
    quality=flow._quality_snapshot(saved,md,pdf)
    c={'job_lead_id':'lead','company':'公司','position':'岗位','status':'pending','delivery_kind':'generated_pdf',
       'quality_snapshot':quality,'quality_sha256':flow._quality_digest(quality)}
    c['snapshot']=ReviewSnapshotStore(agent._AGENT_RUN_DIR).create('run',c,md.decode(),dry_run=False,pdf_content=pdf)
    c.pop('quality_snapshot')
    path=agent._get_queue_file('run');agent._save_queue(path,{'run_id':'run','quick_run_id':'quick','candidates':[c]});before=path.read_bytes()
    with pytest.raises(ValueError,match='quality_snapshot_changed'):
        flow.handle_begin_upload({'meta':{'correlation_id':'t'},'run_id':'run','accept_account_effects':True})
    assert path.read_bytes()==before
