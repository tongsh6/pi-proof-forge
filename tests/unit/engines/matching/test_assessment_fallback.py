"""Fallback supplies attributable evidence, not merely matching-looking titles."""
import json

from tools.engines.matching.semantic_matching import _bounded_assessment_facts


def card(source, fields, role='参与开发'):
    return {f'{source}:{field}:0':{'source_id':source,'field':field,'text':text,'source_role':role}
            for field,text in fields.items()}


def wire_size(rows):
    return len(json.dumps({key:{k:v for k,v in row.items() if k in ('text','source_role','source_qualifiers')}
                           for key,row in rows.items()},ensure_ascii=False,sort_keys=True))


def test_fallback_preserves_actual_work_and_qualifiers_without_upgrading_status():
    source=card('a',{'title':'部署平台','context':'2026-01 计划上线；2026-02 提交测试，未确认生产上线',
                     'time_range':'2026-01至2026-02','actions':'提交测试验证；正式上线日期未确认',
                     'results':'测试通过；不代表生产发布'})
    chosen=_bounded_assessment_facts(source,set(),900)
    assert {'actions','results','context','time_range'} <= {row['field'] for row in chosen.values()}
    assert chosen['a:actions:0']==source['a:actions:0']
    assert chosen['a:context:0']==source['a:context:0']
    assert all(chosen[key]==source[key] for key in chosen)


def test_tiny_budget_and_long_cards_never_force_oversize_first_fact():
    facts=card('a',{'title':'x'*1000, 'actions':'x'*1500})
    assert _bounded_assessment_facts(facts,{'a:title:0'},2)=={}
    assert _bounded_assessment_facts(facts,set(),2)=={}


def test_long_first_cards_do_not_starve_later_fitting_work():
    facts={}
    for i in range(30):
        facts.update(card(f'a{i:02}',{'title':'标题','actions':'长'*4000,'context':'大型项目'}))
    facts.update(card('z',{'title':'可见项目','actions':'修复接口配置'}))
    chosen=_bounded_assessment_facts(facts,set(),250)
    assert 'z:actions:0' in chosen
    assert wire_size(chosen)<=250


def test_title_only_and_unknown_role_remain_metadata_not_attributable_work():
    facts=card('a',{'title':'同名岗位'})
    facts.update(card('b',{'title':'真实团队记录','actions':'上线生产服务'},role=''))
    facts.update(card('c',{'title':'本人项目','results':'投产后灰度观测正常'}))
    chosen=_bounded_assessment_facts(facts,set(),1000)
    assert chosen['a:title:0']==facts['a:title:0']
    assert chosen['b:title:0']==facts['b:title:0']
    assert 'b:actions:0' not in chosen
    assert chosen['c:results:0']==facts['c:results:0']


def test_cited_fact_keeps_priority_under_exact_wire_budget():
    facts=card('a',{'actions':'此前未被召回的工作'})
    facts.update(card('z',{'actions':'已召回的工作'}))
    key='z:actions:0'
    chosen=_bounded_assessment_facts(facts,{key},wire_size({key:facts[key]}))
    assert chosen=={key:facts[key]}


def test_ample_room_keeps_later_work_and_adds_context_to_cited_actions():
    facts=card('a',{'title':'一号','actions':'接入测试环境','results':'验收未确认',
                    'context':'项目仅提交测试，生产状态待核实'})
    facts['a:actions:1']={**facts['a:actions:0'],'text':'增加权限审计'}
    facts['a:results:1']={**facts['a:results:0'],'text':'试用期间未发现重复调用'}
    facts['a:actions:0']['source_qualifiers']=['主导或参与']
    from tools.engines.matching.semantic_matching import _wire_facts
    chosen=_bounded_assessment_facts(facts,{'a:actions:0'},1100)
    assert set(chosen)==set(facts)-{'a:title:0'}
    wire=_wire_facts(chosen,assessment=True)
    assert wire['a:actions:0']['source_role']=='参与开发'
    assert wire['a:actions:0']['source_qualifiers']==['主导或参与']
    for key in wire:
        assert wire[key]['text']==facts[key]['text']


def test_actual_assess_requests_fit_with_large_escaped_profile_and_long_jd(tmp_path,monkeypatch):
    from tools.engines.matching import semantic_matching as engine
    from tools.infra.llm.task_runner import check_budget
    from test_advisory_pending_order import Client, fixture

    kwargs,_=fixture(tmp_path)
    credential={'source_id':'personal_profile','field':'career.skills.misc.category','text':'"\\'*800}
    monkeypatch.setattr(engine,'_profile_facts',lambda *a,**kw:{'personal_profile:career.skills.misc.category:0':credential})
    class MeasuringClient(Client):
        def post_json(self,url,payload,**kw):
            assert not check_budget(engine.SEMANTIC_MATCHING,payload)
            return super().post_json(url,payload,**kw)

    client=MeasuringClient()
    result=engine.run_semantic_matching(**kwargs,client=client,advisory=True)
    assert set(result['completed_check_ids'])=={'r1','r2','r3','r4'}
    assert len([seen for seen in client.seen if seen['stage']=='assess'])==4
