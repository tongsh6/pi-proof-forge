"""求职偏好从材料提炼，经确认保存，再由 App 筛岗使用。"""
import importlib
import json

import pytest

from tools.sidecar.handlers import materials, profile
from tools.infra.llm.client import LLMClient


def setup(tmp_path, monkeypatch):
    root=tmp_path/'materials';root.mkdir()
    text='主投产品型公司 Tech Lead。\n不选择客户交付、驻场和普通 Java 开发岗位。'
    (root/'mat_p.md').write_text(text)
    (root/'mat_p.meta.yaml').write_text('material_id: "mat_p"\nfilename: "mat_p.md"\nextension: ".md"\nlabel: "求职方向"\n')
    monkeypatch.setattr(materials,'_MATERIALS_DIR',root)
    monkeypatch.setattr(profile,'_PROFILE_PATH',tmp_path/'personal_profile.yaml')
    profile._PROFILE_PATH.write_text('name: "测试"\ncareer_review_json: "keep-review"\n')
    module=importlib.import_module('tools.sidecar.handlers.job_preferences')
    monkeypatch.setattr(module.settings_handler,'_load_llm_config',lambda:{'provider':'lm_studio','base_url':'http://localhost/v1','api_key_for_request':'local','model':'test','timeout':30})
    response={'items':[{'kind':'primary','text':'产品型 Tech Lead','quote':'主投产品型公司 Tech Lead。'},
                       {'kind':'avoid','text':'客户交付、驻场、普通Java开发','quote':'不选择客户交付、驻场和普通 Java 开发岗位。'}]}
    monkeypatch.setattr(LLMClient,'post_json',lambda *args,**kwargs:{'choices':[{'message':{'content':json.dumps(response)}}]})
    return module,root,response


def test_generate_then_confirm_does_not_change_career_review(tmp_path,monkeypatch):
    module,root,_=setup(tmp_path,monkeypatch)
    before=profile._PROFILE_PATH.read_bytes()
    draft=module.handle_generate({'meta':{},'material_id':'mat_p'})['draft']
    assert profile._PROFILE_PATH.read_bytes()==before
    revision=module.get_preferences(profile._load_profile())['revision']
    with pytest.raises(ValueError,match='confirmation'):
        module.handle_save({'meta':{},'draft':draft,'expected_revision':revision})
    result=module.handle_save({'meta':{},'draft':draft,'expected_revision':revision,'confirmed':True})
    assert result['preferences']['items'][0]['kind']=='primary'
    assert profile._load_profile()['career_review_json']=='keep-review'
    assert profile._profile_payload(profile._load_profile())['job_preferences']['revision']==result['preferences']['revision']
    with pytest.raises(ValueError,match='preferences_changed'):
        module.handle_save({'meta':{},'draft':draft,'expected_revision':revision,'confirmed':True})
    (root/'mat_p.md').write_text('已改变的原文')
    with pytest.raises(ValueError,match='source_changed'):
        module.handle_save({'meta':{},'draft':draft,'expected_revision':result['preferences']['revision'],'confirmed':True})


def test_fabricated_preference_quote_is_rejected(tmp_path,monkeypatch):
    module,_,response=setup(tmp_path,monkeypatch)
    response['items'][0]['quote']='用户愿意任何时候加班'
    with pytest.raises(ValueError,match='quote_not_in_source'):
        module.handle_generate({'meta':{},'material_id':'mat_p'})


def test_direction_uses_jd_quote_and_known_preference(tmp_path,monkeypatch):
    module,_,_=setup(tmp_path,monkeypatch)
    draft=module.handle_generate({'meta':{},'material_id':'mat_p'})['draft']
    from tools.infra import job_preferences as infra
    good={'status':'excluded','reason':'要求驻场客户交付','criterion_index':1,'jd_quote':'负责客户驻场实施与交付'}
    assert infra.validate_direction(good,draft,'负责客户驻场实施与交付')['status']=='excluded'
    with pytest.raises(ValueError):infra.validate_direction({**good,'criterion_index':10},draft,'负责客户驻场实施与交付')
    with pytest.raises(ValueError):infra.validate_direction({**good,'jd_quote':'虚构JD'},draft,'负责客户驻场实施与交付')


def test_app_matching_stops_on_excluded_direction_before_card_review(tmp_path,monkeypatch):
    module,_,_=setup(tmp_path,monkeypatch)
    draft=module.handle_generate({'meta':{},'material_id':'mat_p'})['draft']
    module.handle_save({'meta':{},'draft':draft,'confirmed':True,'expected_revision':module.get_preferences(profile._load_profile())['revision']})
    from tools.infra import semantic_matching
    job=tmp_path/'job.yaml';job.write_text('target_role: "Java交付负责人"\nsource_jd: "负责客户驻场实施与交付"\nkeywords:\n  - "Java"\n')
    card=tmp_path/'ec1.yaml';card.write_text('title: "Java项目"\nresults:\n  - "完成接口"\nartifacts:\n  - "报告"\n')
    calls=[]
    class Client:
        chat_completions_url='http://localhost/v1/chat/completions'
        def post_json(self,url,payload,**kwargs):
            calls.append(payload)
            return {'choices':[{'message':{'content':json.dumps({'status':'excluded','reason':'驻场交付与偏好冲突','criterion_index':1,'jd_quote':'负责客户驻场实施与交付'})}}]}
        @staticmethod
        def extract_content(response):return response['choices'][0]['message']['content']
    with pytest.raises(ValueError,match='career_direction_excluded'):
        semantic_matching.run_semantic_matching(job_path=job,evidence_files=[card],personal_profile=profile._PROFILE_PATH,
            client=Client(),model='test',cache_dir=tmp_path/'cache')
    assert len(calls)==1


def test_direction_binds_material_and_file_jd_to_reused_report(tmp_path,monkeypatch,capsys):
    module,root,_=setup(tmp_path,monkeypatch)
    draft=module.handle_generate({'meta':{},'material_id':'mat_p'})['draft']
    module.handle_save({'meta':{},'draft':draft,'confirmed':True,'expected_revision':module.get_preferences(profile._load_profile())['revision']})
    from tools.infra import semantic_matching as infra
    monkeypatch.setattr(infra,'_profile_facts',lambda _: {})
    jd=tmp_path/'job.txt';jd.write_text('负责产品平台长期架构建设')
    job=tmp_path/'job.yaml';job.write_text('target_role: "平台负责人"\nsource_jd: "job.txt"\nmust_have:\n  - "平台建设"\n')
    card=tmp_path/'ec1.yaml';card.write_text('title: "平台"\nresults:\n  - "完成平台的长期架构建设"\nartifacts:\n  - "报告"\n')
    calls=[]
    class Client:
        chat_completions_url='http://localhost/v1/chat/completions'
        def post_json(self,url,payload,**kwargs):
            data=json.loads(payload['messages'][1]['content']);calls.append(data)
            if 'jd' in data:
                assert data['jd']==jd.read_text(), '文件路径必须解析为正文'
                response={'status':'aligned','reason':'产品平台主投方向','criterion_index':0,'jd_quote':data['jd']}
            else:
                citation={'fact_id':'ec1:results:0','quote':'完成平台的长期架构建设'}
                response=({'cards':[{'id':'ec1','score':90,'reason':'平台经验','requirement_ids':['r1'],'citations':[citation]}]}
                          if data['stage']=='recall' else {'assessments':[{'requirement_id':'r1','status':'supported','reason':'平台经验','citations':[citation]}]})
            return {'choices':[{'message':{'content':json.dumps(response)}}]}
        @staticmethod
        def extract_content(response):return response['choices'][0]['message']['content']
    options=dict(job_path=job,evidence_files=[card],personal_profile=profile._PROFILE_PATH,client=Client(),model='test',cache_dir=tmp_path/'cache')
    result=infra.run_semantic_matching(**options)
    assert result['statistics']['model_calls']==3
    report=tmp_path/'report.yaml';infra.write_semantic_report(report,result)
    assert infra.load_semantic_report(report)['direction_review']['status']=='aligned'
    source=root/'mat_p.md';original=source.read_text();source.write_text(original+'新偏好')
    with pytest.raises(ValueError,match='semantic_input_changed'):infra.load_semantic_report(report)
    source.write_text(original)
    jd.write_text('改变的岗位正文')
    with pytest.raises(ValueError,match='semantic_input_changed'):infra.load_semantic_report(report)
    # URL 没有可引用的正文，不能把网址当职责证据，也不能继续卡片匹配。
    job.write_text(job.read_text().replace('job.txt','https://example.org/jobs/123'))
    before=len(calls)
    with pytest.raises(ValueError,match='career_direction_jd_body_missing'):infra.run_semantic_matching(**options)
    assert len(calls)==before

    from tools import run_matching_scoring
    pool=tmp_path/'pool';pool.mkdir();(pool/card.name).write_bytes(card.read_bytes())
    monkeypatch.setattr('sys.argv',['matching','--job-profile',str(job),'--evidence-dir',str(pool),'--personal-profile',str(profile._PROFILE_PATH),
        '--output',str(report),'--use-llm','--require-llm','--model','test','--api-key','local'])
    assert run_matching_scoring._legacy_main()==1
    assert '请先补齐并审核完整 JD' in capsys.readouterr().out
