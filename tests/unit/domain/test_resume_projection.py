import copy
from tools.run_generation import build_template_resume
from tools.infra.resume_content import content_body_issues


def data():
    p={'name':'候选人','phone':'13800000000','email':'test@example.com','city':'上海','current_position':'Tech Lead',
       'career':{'summary':'旧的通用摘要。','education_visibility':'omit','education':[],
       'work':[{'id':'recent','company':'当前公司','title':'Tech Lead','start':'2021-03','current':True,'end':'','scope':'跨品牌平台架构与交付。','contributions':['管理团队并参与平台建设。'],'evidence_ids':['a']},
               {'id':'old','company':'早期公司','title':'Java开发','start':'2013-02','end':'2021-03','scope':'旧系统维护。','contributions':['早期的低相关功能开发。'],'evidence_ids':[]}],
       'skills':[{'id':'s','category':'平台开发','description':'Java微服务架构。','evidence_ids':['a']}],
       'extras':[{'id':'ai','title':'个人AI工具','description':'个人独立工程验证，仍在迭代。','url':'https://example.com/ai'},
                 {'id':'other','title':'无关补充项目','description':'其他个人探索。','url':''}]}}
    c={'id':'a','title':'消息平台','time_range':'2022 – 至今','role_scope':'核心开发者','context':'性能数据来自本机验证，不是生产指标。','actions':['重构发送链路。'],'results':['本机发送耗时由38秒降到6秒。'],'stack':['MongoDB','Docker Swarm'],'artifacts':['source']}
    refs=[{'source_id':'a','field':'results','text':c['results'][0]}, {'source_id':'personal_profile','field':'career.extras.ai.description','text':p['career']['extras'][0]['description']}]
    return p,c,refs


def render():
    p,c,refs=data();claims=[]
    text=build_template_resume('A','r',80,'now',[c],personal_profile=p,job_context={'target_role':'平台负责人','company':'目标公司'},preferred_facts=refs,claims=claims)
    return p,text,claims


def test_targeted_body_keeps_timeline_but_does_not_copy_all_old_contributions():
    p,text,claims=render()
    assert '早期的低相关功能开发。' not in text
    assert all(v in text for v in ('当前公司','2021-03','早期公司','2013-02','Java开发'))
    assert '无关补充项目' not in text
    assert '个人独立工程验证，仍在迭代。' in text
    assert text.index('个人AI工具') < text.index('## 工作经历')
    assert text.index('## 项目经历') < text.index('## 工作经历')
    assert not content_body_issues(p,text,display_policy='targeted_v1')
    assert content_body_issues(p,text.replace('早期公司','另一家公司'),display_policy='targeted_v1')


def test_targeted_technical_stack_and_evidence_boundaries_are_not_suppressed():
    _,text,claims=render()
    assert 'Docker Swarm' in text
    assert '性能数据来自本机验证，不是生产指标。' in text
    assert any(c['field']=='stack' and c['text']=='Docker Swarm' for c in claims)
    assert all(c['text'] in text for c in claims)


def test_full_legacy_body_guard_stays_strict_without_new_trace_policy():
    p,text,_=render()
    assert content_body_issues(p,text)


def test_only_cited_work_contribution_is_selected_once():
    p,c,refs=data()
    p['career']['work'][0]['contributions'].append('未被引用的详细背景。')
    refs.append({'source_id':'personal_profile','field':'career.work.recent.contributions','text':'管理团队并参与平台建设。'})
    text=build_template_resume('A','r',80,'now',[c],personal_profile=p,preferred_facts=refs)
    assert text.count('管理团队并参与平台建设。')==1
    assert '未被引用的详细背景。' not in text


def test_cited_skill_category_is_not_lost_to_three_uncited_groups():
    p,c,refs=data()
    p['career']['skills']=[{'id':f's{i}','category':f'普通能力{i}','description':f'基础工作{i}。','evidence_ids':['a']} for i in range(3)]
    p['career']['skills'].append({'id':'ai','category':'AI工程治理','description':'有界权限与验证闭环。','evidence_ids':['b']})
    refs.append({'source_id':'personal_profile','field':'career.skills.ai.category','text':'AI工程治理'})
    text=build_template_resume('A','r',80,'now',[c],personal_profile=p,preferred_facts=refs)
    assert 'AI工程治理' in text


def test_cited_stack_is_selected_before_display_limit_and_keeps_each_source():
    p,c,refs=data();c['stack']=[f'Tech{i}' for i in range(9)]+['Docker Swarm']
    other=copy.deepcopy(c);other['id']='b';other['stack']=['Docker Swarm']
    refs.extend([{'source_id':key,'field':'stack','text':'Docker Swarm'} for key in ('a','b')]);claims=[]
    text=build_template_resume('A','r',80,'now',[c,other],personal_profile=p,preferred_facts=refs,claims=claims)
    assert 'Docker Swarm' in text
    assert {c['evidence_id'] for c in claims if c['field']=='stack' and c['text']=='Docker Swarm'}=={'a','b'}


def test_summary_preserves_confirmed_personal_ownership_qualifier():
    p,text,_=render()
    assert p['career']['work'][0]['contributions'][0] in text.split('## 核心能力')[0]


def test_project_fact_selection_keeps_broad_platform_evidence_before_cutoff():
    p,c,_=data()
    c['actions']=['使用框架开发服务。','配置注册中心。','编写HTTP通信。','定义用户、活动、支付等微服务职责。']
    c['results']=['查询延迟降低。','代码库包含多个模块。','18个服务统一平台，13项模式跨品牌复用。']
    refs=[]
    for field in ('actions','results'):
        for i,value in enumerate(c[field]):
            ids=['r1'] if i<len(c[field])-1 else ['d1','d2','d4']
            refs.extend({'source_id':'a','field':field,'text':value,'requirement_id':ref,'support_weight':2} for ref in ids)
    claims=[]
    text=build_template_resume('A','r',53,'now',[c],personal_profile=p,preferred_facts=refs,claims=claims)
    assert c['actions'][3] in text
    assert c['results'][2] in text
    assert sum(x['field']=='actions' for x in claims)==3
    assert sum(x['field']=='results' for x in claims)==2
    assert all(x['text'] in text for x in claims)


def test_fact_priority_prefers_new_requirements_not_duplicate_citations():
    p,c,_=data();c['results']=['常规成果一。','常规成果二。','覆盖新的平台要求。']
    refs=[{'source_id':'a','field':'results','text':v,'requirement_id':'r1','support_weight':2}
          for v in c['results'][:2] for _ in range(10)]
    refs.append({'source_id':'a','field':'results','text':c['results'][2],'requirement_id':'d2','support_weight':1})
    text=build_template_resume('A','r',53,'now',[c],personal_profile=p,preferred_facts=refs)
    assert c['results'][2] in text
    assert c['results'][1] not in text


def test_generation_retains_positive_child_citations_without_promoting_unsupported_children():
    from tools.run_generation import semantic_preferred_facts
    facts={str(i):{'source_id':'a','field':'actions','text':f'原文行动{i}。'} for i in range(3)}
    review={'facts':facts,'assessments':[{'requirement_id':'d1','status':'conflict','citations':[{'fact_id':str(i)} for i in range(3)],
            'checks':[{'requirement_id':'d1.c1','status':'supported','citations':[{'fact_id':'0'}]},
                      {'requirement_id':'d1.c2','status':'partial','citations':[{'fact_id':'1'}]},
                      {'requirement_id':'d1.c3','status':'conflict','citations':[{'fact_id':'2'}]}]}]}
    refs=semantic_preferred_facts(review)
    assert [(r['text'],r['requirement_id'],r['support_weight']) for r in refs]==[('原文行动0。','d1',2),('原文行动1。','d1',1)]


def test_cited_detail_does_not_displace_confirmed_primary_contribution_in_summary():
    p,c,refs=data();work=p['career']['work'][0]
    detail='开展接口联调与局部流程验收。';work['contributions'].append(detail)
    refs.append({'source_id':'personal_profile','field':'career.work.recent.contributions','text':detail})
    text=build_template_resume('A','r',58,'now',[c],personal_profile=p,preferred_facts=refs)
    summary=text.split('## 职业概述\n', 1)[1].split('\n## ', 1)[0]
    assert work['contributions'][0] in summary
    assert detail not in summary
    assert detail in text.split('## 工作经历')[1]


def test_result_already_in_same_project_context_is_not_repeated_but_stays_traced():
    p,c,refs=data();c['context']='统一系统，减少业务开发成本，提高业务开发效率。'
    c['results']=['减少业务开发成本','提高业务开发效率'];claims=[]
    text=build_template_resume('A','r',58,'now',[c],personal_profile=p,preferred_facts=refs,claims=claims)
    assert text.count('减少业务开发成本')==1
    assert text.count('提高业务开发效率')==1
    assert {x['text'] for x in claims if x['field']=='results'}==set(c['results'])


def test_extra_selection_prioritizes_new_requirement_coverage_over_profile_order():
    p, c, _ = data()
    p['career']['extras'] = [
        {'id': 'ai1', 'title': '个人工具一', 'description': '模型调用与工具执行', 'url': ''},
        {'id': 'ai2', 'title': '个人工具二', 'description': 'AI 工作流', 'url': ''},
        {'id': 'python', 'title': 'Python 内容生成', 'description': 'Python 多平台内容生成已运行', 'url': ''},
    ]
    refs = [{'source_id': 'personal_profile', 'field': f"career.extras.{item['id']}.description",
             'text': item['description'], 'requirement_id': req, 'support_weight': 1}
            for item, req in zip(p['career']['extras'], ['r8', 'r8', 'r4'])]
    text = build_template_resume('A', 'r', 50, 'now', [c], personal_profile=p, preferred_facts=refs)
    assert 'Python 内容生成' in text
    assert '个人工具一' in text and '个人工具二' not in text


def test_extra_selection_accounts_for_requirements_already_in_project_body():
    p, c, _ = data()
    p['career']['extras'] = [
        {'id': 'ai1', 'title': '个人工具一', 'description': '模型调用', 'url': ''},
        {'id': 'ai2', 'title': '个人工具二', 'description': '重复的工具执行实践', 'url': ''},
        {'id': 'python', 'title': 'Python 内容生成', 'description': 'Python 内容生成已运行', 'url': ''},
    ]
    refs = [{'source_id': 'personal_profile', 'field': f"career.extras.{item['id']}.description",
             'text': item['description'], 'requirement_id': req, 'support_weight': 1}
            for item, req in zip(p['career']['extras'], ['r8', 'd2', 'r4'])]
    refs.append({'source_id': 'a', 'field': 'actions', 'text': c['actions'][0],
                 'requirement_id': 'd2', 'support_weight': 1})
    text = build_template_resume('A', 'r', 50, 'now', [c], personal_profile=p, preferred_facts=refs)
    assert 'Python 内容生成' in text and '个人工具一' in text
    assert '个人工具二' not in text
