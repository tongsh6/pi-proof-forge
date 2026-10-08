import json
import pytest
from pathlib import Path
from tools import run_generation


def complete_profile():
    return {'name':'合成候选人','phone':'13800000000','email':'test@example.com','city':'上海','current_position':'后端工程师',
        'career':{'schema_version':1,'summary':'交易系统开发与交付。',
          'work':[{'id':'w1','company':'实际任职公司','department':'研发','title':'后端工程师','start':'2022-01','end':'2025-12','current':False,'scope':'订单与库存服务','contributions':['负责接口设计与稳定性验证'],'evidence_ids':['ec-1']}],
          'education_visibility':'show','education':[{'id':'e1','school':'示例大学','major':'计算机','degree':'本科','start':'2018-09','end':'2022-06','current':False}],
          'skills':[{'id':'s1','category':'服务与数据','description':'Java 服务及 Redis 缓存实践','evidence_ids':['ec-1']}],
          'extras':[{'id':'x1','title':'工程实践文章','description':'记录接口取舍','url':'https://example.com/work'}]}}


def card():
    return {'id':'ec-1','title':'客户品牌订单平台','raw_source':'source','time_range':'2024-01 ~ 2024-06','context':'峰值订单查询慢','role_scope':'接口模块负责人','actions':['设计 Redis 缓存策略'],'results':['接口回归通过'],'stack':['Java','Redis'],'artifacts':['报告']}


def test_complete_resume_uses_existing_template_and_keeps_employer_project_separate():
    claims=[]
    text=run_generation.build_template_resume('A','r',90,'now',[card()],personal_profile=complete_profile(),job_context={'company':'目标公司','target_role':'Java工程师'},claims=claims)
    sections=['职业概述','核心能力','工作经历','项目经历','教育经历','补充成果']
    assert all('## '+x in text for x in sections)
    assert [text.index('## '+x) for x in sections]==sorted(text.index('## '+x) for x in sections)
    assert '实际任职公司（2022-01 ~ 2025-12）' in text
    assert '所属工作：实际任职公司' in text
    assert '客户品牌订单平台' in text and '示例大学' in text
    assert any(x['field']=='career.work.w1.company' for x in claims)
    assert all(c['text'] in text for c in claims)
    assert '20年经验' not in text and '管理50人' not in text


def test_education_omission_and_summary_from_existing_facts():
    profile=complete_profile();profile['career']['education_visibility']='omit';profile['career']['summary']=''
    text=run_generation.build_template_resume('B','r',90,'now',[card()],personal_profile=profile)
    assert '## 教育经历' not in text and '示例大学' not in text
    assert '## 职业概述' in text and '订单与库存服务' in text


def test_generation_context_reads_confirmed_career_and_checks_work_link(tmp_path):
    from tools.infra.career_profile import inspect_career
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    profile=complete_profile();career=profile.pop('career');path=tmp_path/'personal_profile.yaml'
    evidence=tmp_path/'evidence_cards';evidence.mkdir();(evidence/'ec-1.yaml').write_text('status: "saved_eligible"\ncandidate_pool_eligible: "true"\nresults:\n  - "通过"\nartifacts:\n  - "报告"\n')
    fields={**profile,'career_json':json.dumps(career,ensure_ascii=False)}
    state=inspect_career(fields,evidence);fields['career_review_json']=json.dumps({'revision':state['revision']})
    path.write_text('\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in fields.items())+'\n')
    loaded,_=run_generation.load_generation_context(path,None)
    assert loaded['career_status']['reviewed'] is True
    selected=card();selected['source_sha256']=loaded['evidence_hashes']['ec-1']
    missing=run_generation.career_generation_issues(loaded,[selected])
    assert missing==[]
    outside=card();outside['time_range']='2020-01 ~ 2020-06'
    assert any('时间' in r for r in run_generation.career_generation_issues(loaded,[outside]))
    unlinked=card();unlinked['id']='ec-other'
    assert any('关联' in r for r in run_generation.career_generation_issues(loaded,[unlinked]))


@pytest.mark.parametrize('period',['待补充','2024-06 ~ 2024-01','2024.01 ~ 2027.06','2024-01 ~ 至今','测试验收：2026-04-21'])
def test_project_period_must_be_a_valid_interval_inside_employment(period):
    p=complete_profile();p['career_status']={'reviewed':True,'missing':[]}
    c=card();c['time_range']=period
    assert any('时间' in r for r in run_generation.career_generation_issues(p,[c]))


@pytest.mark.parametrize('period',['2024-01 ~ 2024-06','2024.01 至 2024.06','2024年1月—2024年6月'])
def test_explicit_project_date_formats(period):
    p=complete_profile();p['career_status']={'reviewed':True,'missing':[]}
    c=card();c['time_range']=period
    assert run_generation.career_generation_issues(p,[c])==[]
