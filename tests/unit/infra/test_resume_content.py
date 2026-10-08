import hashlib,json,sys
from pathlib import Path
import pytest
from tools import run_generation
from tools.infra.career_profile import inspect_career


def ready_run(root,monkeypatch):
    run='qr_complete';source=root/'evidence_cards';source.mkdir(parents=True)
    card='id: "ec1"\ntitle: "交易服务"\ncontext: "订单查询慢"\nrole_scope: "模块开发"\ntime_range: "2024-01 ~ 2024-06"\nstatus: "saved_eligible"\ncandidate_pool_eligible: "true"\nactions:\n  - "实现 Java 接口与 Redis 缓存"\nresults:\n  - "回归验证通过"\nstack:\n  - "Java"\nartifacts:\n  - "报告"\n'
    (source/'ec1.yaml').write_text(card)
    stage=root/f'outputs/quick_runs/{run}/evidence_cards';stage.mkdir(parents=True);(stage/'ec1.yaml').write_text(card)
    career={'schema_version':1,'summary':'交易服务开发。','work':[{'id':'w1','company':'合成公司','department':'研发','title':'工程师','start':'2022-01','end':'2025-01','current':False,'scope':'订单服务','contributions':['承担接口开发'],'evidence_ids':['ec1']}],'education_visibility':'omit','education':[],'skills':[{'id':'s1','category':'服务开发','description':'Java 接口与缓存设计','evidence_ids':['ec1']}],'extras':[]}
    fields={'name':'测试人','phone':'13800000000','email':'test@example.com','city':'上海','current_position':'工程师','career_json':json.dumps(career,ensure_ascii=False)}
    state=inspect_career(fields,source);fields['career_review_json']=json.dumps({'revision':state['revision']})
    profile=root/'personal_profile.yaml';profile.write_text('\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in fields.items())+'\n')
    job=root/'job.yaml';job.write_text('target_role: "后端工程师"\ncompany: "目标公司"\nsource_jd: "负责订单服务与缓存治理"\njob_lead_id: "jl1"\nsource_jd_sha256: "jd-sha"\nkeywords:\n  - "Java"\n')
    report=root/f'mr-{run}.yaml';report.write_text('score_total: 80\ntop_cards:\n  - id: "ec1"\n')
    output=root/'outputs'/run
    monkeypatch.setattr(sys,'argv',['generate','--matching-report',str(report),'--output-dir',str(output),'--evidence-dir',str(stage),'--personal-profile',str(profile),'--job-profile',str(job)])
    assert run_generation._legacy_main()==0
    pdf=root/f'outputs/quick_runs/{run}/exports/resume_mr-{run}_A.pdf';pdf.parent.mkdir();pdf.write_bytes(b'%PDF-1.7\nfixture\n%%EOF')
    record={'run':{'run_id':run,'status':'DONE'},'resume_pdf':str(pdf.relative_to(root)),'artifacts':{'resume_pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(), 'resume_pdf_source_sha256':hashlib.sha256((output/f'resume_mr-{run}_A.md').read_bytes()).hexdigest(), 'resume_pdf_trace_sha256':hashlib.sha256((output/f'resume_mr-{run}_A.trace.json').read_bytes()).hexdigest()}}
    (root/f'outputs/quick_runs/{run}.json').write_text(json.dumps(record))
    return run,pdf,profile


def test_existing_review_queue_binds_content_without_second_approval_store(tmp_path,monkeypatch):
    from tools.infra.resume_content import validate_generated_content,require_queue_content
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    run,pdf,profile=ready_run(tmp_path,monkeypatch);proof=validate_generated_content(tmp_path,run)
    md=tmp_path/f'outputs/{run}/resume_mr-{run}_A.md'
    c={'job_lead_id':'jl1','source_jd_sha256':'jd-sha','resume_version':proof['resume_version'],'content_basis':proof,'status':'pending','delivery_kind':'generated_pdf','company':'目标公司','position':'后端工程师'}
    c['snapshot']=ReviewSnapshotStore(tmp_path/'outputs/agent_runs').create('review',c,md.read_text(),dry_run=False,pdf_content=pdf.read_bytes())
    q={'run_id':'review','quick_run_id':run,'candidates':[c]}
    assert require_queue_content(tmp_path,q)==proof
    with pytest.raises(ValueError,match='resume_content_review_required'):require_queue_content(tmp_path,q,require_approval=True)
    from tools.sidecar.handlers import agent,native_pdf
    monkeypatch.setattr(agent,'_PROJECT_ROOT',tmp_path);monkeypatch.setattr(agent,'_AGENT_RUN_DIR',tmp_path/'outputs/agent_runs');monkeypatch.setattr(agent,'_REVIEW_QUEUE_DIR',tmp_path/'outputs/review_queue')
    agent._save_queue(agent._get_queue_file('review'),q)
    packet=native_pdf.handle_begin_upload({'meta':{'correlation_id':'test'},'run_id':'review','accept_account_effects':True})
    assert bytes(packet['pdf_bytes'])==pdf.read_bytes()
    q=agent._load_queue(agent._get_queue_file('review'))
    assert require_queue_content(tmp_path,q,require_approval=True)==proof
    record=json.loads((tmp_path/f'outputs/quick_runs/{run}.json').read_text());assert 'content_review' not in record
    pdf.write_bytes(pdf.read_bytes()+b'changed')
    with pytest.raises(ValueError):require_queue_content(tmp_path,q,require_approval=True)


def test_changed_career_never_passes_content_checks(tmp_path,monkeypatch):
    from tools.infra.resume_content import validate_generated_content
    run,_,profile=ready_run(tmp_path,monkeypatch);validate_generated_content(tmp_path,run)
    profile.write_text(profile.read_text().replace('订单服务','改过的业务'))
    with pytest.raises(ValueError):validate_generated_content(tmp_path,run)


def test_new_markdown_cannot_reuse_old_pdf(tmp_path,monkeypatch):
    from tools.infra.resume_content import validate_generated_content
    run,_,_=ready_run(tmp_path,monkeypatch)
    monkeypatch.setattr(sys,'argv',sys.argv+['--resume-positioning','custom','--custom-positioning','架构工程师'])
    assert run_generation._legacy_main()==0
    with pytest.raises(ValueError,match='resume_pdf_source_changed'):
        validate_generated_content(tmp_path,run)


def test_staged_evidence_must_match_confirmed_source_version(tmp_path,monkeypatch):
    from tools.infra.resume_content import validate_generated_content
    run,_,_=ready_run(tmp_path,monkeypatch)
    staged=tmp_path/f'outputs/quick_runs/{run}/evidence_cards/ec1.yaml'
    staged.write_text(staged.read_text().replace('回归验证通过','未经档案确认的新结果'))
    assert run_generation._legacy_main()==0
    md=tmp_path/f'outputs/{run}/resume_mr-{run}_A.md'
    trace=json.loads(md.with_suffix('.trace.json').read_text())
    assert trace['readiness']['content_ready'] is False
    with pytest.raises(ValueError,match='resume_evidence_changed'):
        validate_generated_content(tmp_path,run)


def test_legacy_quick_run_done_is_not_content_approval(tmp_path):
    from tools.infra.resume_content import validate_generated_content
    p=tmp_path/'outputs/quick_runs';p.mkdir(parents=True);(p/'qr_old.json').write_text(json.dumps({'run':{'run_id':'qr_old','status':'DONE'}}))
    with pytest.raises(ValueError):validate_generated_content(tmp_path,'qr_old')


def test_default_route_cannot_bypass_missing_career(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from tools.channels.base import DeliveryRequest
    from tools.infra.liepin_default_delivery import LiepinOfficialChannel
    from tools.domain.result import Err
    monkeypatch.chdir(tmp_path)
    channel=LiepinOfficialChannel(token_store=SimpleNamespace(load=lambda:pytest.fail('不应读取凭据')),
       read_client=SimpleNamespace(get_resume=lambda _:pytest.fail('不应联网')),
       write_client=SimpleNamespace(apply=lambda *a:pytest.fail('不应发送')))
    request=DeliveryRequest('run','lead','liepin','','https://www.liepin.com/job/123.shtml',False,{'delivery_kind':'platform_default','delivery_attempt_id':'a','platform_job_id':'123','platform_job_type':'2'})
    result=channel.deliver(request)
    assert isinstance(result,Err) and result.error.reason=='career_profile_unconfirmed' and result.error.not_submitted
