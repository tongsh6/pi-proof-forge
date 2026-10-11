"""猎聘投递进展只读同步：匹配、归一化、历史追加、不改回执、不编造。"""
import json
from pathlib import Path
import pytest
from tools.sidecar.handlers import submission as handler
from tools.sidecar.handlers import platform_feedback as pf
from tests.unit.infra.test_submission_evidence import fixture_submission


@pytest.fixture(params=['platform_default','generated_pdf'])
def managed(tmp_path,monkeypatch,request):
    monkeypatch.chdir(tmp_path)
    log,q,archive=fixture_submission(tmp_path,request.param)
    monkeypatch.setattr(handler,'_SUBMISSIONS_DIR',tmp_path/'outputs/submissions')
    monkeypatch.setattr(handler,'_JOB_LEAD_DIR',tmp_path/'job_leads')
    monkeypatch.setattr(handler,'_FEEDBACK_ITERATIONS_DIR',tmp_path/'outputs/feedback_iterations')
    leads=tmp_path/'job_leads';leads.mkdir(exist_ok=True)
    (leads/'lead_test.yaml').write_text('id: "lead_test"\nplatform_job_id: "123"\nurl: "https://www.liepin.com/job/19123.shtml?mscid=x"\ncompany: "合成公司"\nposition: "合成岗位"\n',encoding='utf-8')
    return log,q,archive


def meta(**extra):return {'meta':{'correlation_id':'t'},**extra}


def observation(rows,status='records',page='https://c.liepin.com/resume/apply-record?x=1'):
    return {'status':status,'page_url':page,'discovery':{'links':[{'label':'我的投递','url':'https://c.liepin.com/resume/apply-record?token=abc'}]},'rows':rows}


def test_sync_packet_lists_managed_submissions_with_job_identity(managed):
    log,_,_=managed
    packet=pf.handle_sync_packet(meta())
    assert packet['discovery']['start_url']=='https://c.liepin.com/' and '投递' in packet['discovery']['link_keywords']
    [item]=packet['submissions']
    assert item['submission_id']==log.parent.name and item['platform_job_id']=='123'
    assert item['job_url']=='https://www.liepin.com/job/19123.shtml' and item['company']=='合成公司' and item['position']=='合成岗位'


def test_record_matches_by_job_id_normalizes_and_keeps_history(managed):
    log,_,archive=managed;before=(log.read_bytes(),archive.read_bytes())
    first=pf.handle_record_platform_status(meta(observation=observation([{'job_url':'https://www.liepin.com/job/19123.shtml?sid=1','company':'合成公司','position':'合成岗位','status_label':'已查看','time_label':'10-10','excerpt':'合成公司 合成岗位 已查看'}])))
    assert first['status']=='records' and first['matched'][0]['normalized_status']=='viewed' and first['unmatched_rows']==0
    saved=json.loads((log.parent/'platform_feedback.json').read_text(encoding='utf-8'))
    assert saved['latest']['normalized_status']=='viewed' and saved['latest']['match_basis']=='job_id'
    assert saved['latest']['page_url']=='https://c.liepin.com/resume/apply-record'
    pf.handle_record_platform_status(meta(observation=observation([{'job_id':'19123','company':'合成公司','position':'合成岗位','status_label':'不合适'}])))
    saved=json.loads((log.parent/'platform_feedback.json').read_text(encoding='utf-8'))
    assert len(saved['history'])==2 and saved['latest']['normalized_status']=='rejected'
    assert (log.read_bytes(),archive.read_bytes())==before
    listed=handler.handle_submission_list(meta(cursor=None,page_size=20,sort={'field':'submitted_at','order':'desc'},filters={}))['items']
    assert listed[0]['platform_feedback']['status']=='rejected' and listed[0]['platform_feedback']['label']=='不合适'
    items=handler.handle_feedback_list(meta(source_run_id=log.parent.name))['items']
    [platform]=[i for i in items if i['source_type']=='platform_delivery_status']
    assert platform['recommended_next_action']=='update_job_target' and platform['severity_or_priority']=='high'


def test_company_position_fallback_and_unmatched_rows_do_not_write(managed):
    log,_,_=managed
    result=pf.handle_record_platform_status(meta(observation=observation([
        {'company':'合成公司','position':'合成岗位','status_label':'面试邀约'},
        {'company':'别家公司','position':'别的岗位','status_label':'已查看'}])))
    assert result['matched'][0]['normalized_status']=='interview' and result['unmatched_rows']==1
    saved=json.loads((log.parent/'platform_feedback.json').read_text(encoding='utf-8'))
    assert saved['latest']['match_basis']=='company_position'
    sync=json.loads((log.parent.parent/'platform_feedback_sync.json').read_text(encoding='utf-8'))
    assert sync['unmatched_rows'][0]['company']=='别家公司'


def test_unknown_labels_and_discovery_failure_never_fabricate(managed):
    log,_,_=managed
    result=pf.handle_record_platform_status(meta(observation=observation([{'job_id':'19123','company':'合成公司','position':'合成岗位','status_label':'神秘状态'}])))
    assert result['matched'][0]['normalized_status']=='unknown'
    failure=pf.handle_record_platform_status(meta(observation=observation([],status='records_page_not_found')))
    assert failure['status']=='records_page_not_found' and failure['matched']==[]
    sync=json.loads((log.parent.parent/'platform_feedback_sync.json').read_text(encoding='utf-8'))
    assert sync['status']=='records_page_not_found' and sync['discovery_links'][0]['url']=='https://c.liepin.com/resume/apply-record'
    saved=json.loads((log.parent/'platform_feedback.json').read_text(encoding='utf-8'))
    assert saved['latest']['normalized_status']=='unknown' and len(saved['history'])==1


def test_invalid_or_oversized_observation_rejected(managed):
    with pytest.raises(ValueError,match='invalid_feedback_observation'):
        pf.handle_record_platform_status(meta(observation='x'))
    with pytest.raises(ValueError,match='invalid_feedback_observation'):
        pf.handle_record_platform_status(meta(observation=observation([{'excerpt':'y'*70000}])))


def test_overview_funnel_counts_latest_status(managed):
    from tools.sidecar.handlers.overview import handle_overview_get
    assert pf.feedback_funnel()['unsynced']==1
    pf.handle_record_platform_status(meta(observation=observation([{'job_id':'19123','company':'合成公司','position':'合成岗位','status_label':'已查看'}])))
    funnel=pf.feedback_funnel();assert funnel['viewed']==1 and funnel['unsynced']==0
    assert handle_overview_get(meta())['metrics']['feedback_funnel']['viewed']==1
