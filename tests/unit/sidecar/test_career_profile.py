import json
from pathlib import Path
import pytest
from tools.sidecar.handlers import profile


def career():
    return {'schema_version':1,'summary':'交易系统开发与交付。','work':[{'id':'work1','company':'合成公司','department':'研发','title':'后端工程师','start':'2022-01','end':'2025-06','current':False,'scope':'交易服务与库存平台','contributions':['负责交易接口和数据一致性方案'],'evidence_ids':['ec_test']}],
            'education_visibility':'show','education':[{'id':'edu1','school':'示例大学','major':'计算机','degree':'本科','start':'2018-09','end':'2022-06','current':False}],
            'skills':[{'id':'skill1','category':'服务开发','description':'Java 接口开发与 Redis 缓存实践','evidence_ids':['ec_test']}],
            'extras':[{'id':'extra1','title':'示例技术文章','description':'记录接口设计取舍','url':'https://example.com/article'}]}


def setup(tmp_path,monkeypatch):
    path=tmp_path/'personal_profile.yaml'
    path.write_text('name: "合成候选人"\nphone: "13800000000"\nemail: "test@example.com"\ncity: "上海"\ncurrent_position: "后端工程师"\ncustom_note: "preserve"\ncustom_list:\n  - "one"\n')
    e=tmp_path/'evidence_cards';e.mkdir();(e/'ec_test.yaml').write_text('id: "ec_test"\ntitle: "交易服务"\nstatus: "saved_eligible"\ncandidate_pool_eligible: "true"\nresults:\n  - "回归通过"\nartifacts:\n  - "报告"\n')
    monkeypatch.setattr(profile,'_PROFILE_PATH',path)
    return path


def test_legacy_basic_profile_is_not_a_confirmed_career(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    p=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile']
    assert p['completeness']==100
    assert p['career_status']['reviewed'] is False
    assert any(x['field']=='work' for x in p['career_status']['missing'])


def test_career_save_review_and_mutation_invalidate_confirmation(tmp_path,monkeypatch):
    path=setup(tmp_path,monkeypatch);original=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile']
    result=profile.handle_profile_update({'meta':{'correlation_id':'test'},'patch':{'career':career()},'expected_revision':original['revision']})
    p=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile'];assert p['career']['work'][0]['company']=='合成公司'
    assert not p['career_status']['reviewed'] and not p['career_status']['missing']
    with pytest.raises(ValueError,match='career_confirmation_required'):profile.handle_profile_review({'meta':{'correlation_id':'test'},'expected_revision':p['revision']})
    profile.handle_profile_review({'meta':{'correlation_id':'test'},'expected_revision':p['revision'],'confirmed':True})
    assert profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile']['career_status']['reviewed']
    profile.handle_profile_update({'meta':{'correlation_id':'test'},'patch':{'city':'杭州'},'expected_revision':p['revision']})
    assert not profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile']['career_status']['reviewed']
    assert 'custom_note: "preserve"' in path.read_text() and '  - "one"' in path.read_text()
    assert '合成公司' in path.read_text()


def test_stale_forms_and_invalid_dates_do_not_overwrite_profile(tmp_path,monkeypatch):
    path=setup(tmp_path,monkeypatch);p=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile']
    with pytest.raises(ValueError,match='profile_changed'):profile.handle_profile_update({'meta':{'correlation_id':'test'},'patch':{'career':career()},'expected_revision':'stale'})
    before=path.read_bytes();bad=career();bad['work'][0]['end']='2020-01'
    with pytest.raises(ValueError,match='career_date_order'):profile.handle_profile_update({'meta':{'correlation_id':'test'},'patch':{'career':bad},'expected_revision':p['revision']})
    assert path.read_bytes()==before


def test_education_omission_is_explicit_and_changed_evidence_revokes_review(tmp_path,monkeypatch):
    path=setup(tmp_path,monkeypatch);p=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile'];value=career();value['education']=[]
    profile.handle_profile_update({'meta':{'correlation_id':'test'},'patch':{'career':value},'expected_revision':p['revision']})
    p=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile'];assert any(i['field']=='education' for i in p['career_status']['missing'])
    value['education_visibility']='omit';profile.handle_profile_update({'meta':{'correlation_id':'test'},'patch':{'career':value},'expected_revision':p['revision']})
    p=profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile'];profile.handle_profile_review({'meta':{'correlation_id':'test'},'expected_revision':p['revision'],'confirmed':True})
    e=path.parent/'evidence_cards/ec_test.yaml';e.write_text(e.read_text().replace('回归通过','结果已变'))
    assert not profile.handle_profile_get({'meta':{'correlation_id':'test'}})['profile']['career_status']['reviewed']


def test_ready_career_and_materials_do_not_require_uploaded_reference_resume(tmp_path,monkeypatch):
    from tools.sidecar.handlers import materials
    path=setup(tmp_path,monkeypatch);p=profile.handle_profile_get({'meta':{'correlation_id':'t'}})['profile']
    profile.handle_profile_update({'meta':{'correlation_id':'t'},'patch':{'career':career()},'expected_revision':p['revision']})
    p=profile.handle_profile_get({'meta':{'correlation_id':'t'}})['profile'];profile.handle_profile_review({'meta':{'correlation_id':'t'},'expected_revision':p['revision'],'confirmed':True})
    monkeypatch.setattr(materials,'_PROFILE_PATH',path);monkeypatch.setattr(materials,'_UPLOADED_RESUMES_DIR',tmp_path/'no-upload')
    monkeypatch.setattr(materials,'list_material_source_items',lambda:[{'material_id':'source'}])
    result=materials.handle_material_readiness({'meta':{'correlation_id':'t'}})
    assert result['status']=='ready' and not result['missing_items']


def test_basic_profile_save_also_requires_loaded_revision(tmp_path,monkeypatch):
    path=setup(tmp_path,monkeypatch);before=path.read_bytes()
    with pytest.raises(ValueError,match='profile_changed'):
        profile.handle_profile_update({'meta':{'correlation_id':'t'},'patch':{'name':'陈旧表单'}})
    assert path.read_bytes()==before
