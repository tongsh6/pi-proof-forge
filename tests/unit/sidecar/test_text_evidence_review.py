"""工作目录导入文本的人工审核，结果仍须可追溯。"""
import pytest
from tools.sidecar.handlers import evidence, materials


def test_text_material_can_be_reviewed_but_invented_results_remain_blocked(tmp_path,monkeypatch):
    m=tmp_path/'materials';m.mkdir()
    (m/'work.txt').write_text('工作方案\n支持用户租赁登记与归还。\n')
    (m/'work.meta.yaml').write_text('material_id: "work"\nfilename: "work.txt"\nextension: ".txt"\nlabel: "工作方案"\nkind: "raw_work_material_directory"\n')
    monkeypatch.setattr(materials,'_MATERIALS_DIR',m)
    monkeypatch.setattr(evidence,'_EVIDENCE_DIR',tmp_path/'evidence')
    draft={'source_material_ids':['work'],'title':'租赁设计','context':'工作方案','actions':'业务建模',
           'results':'支持用户租赁登记与归还。','stack':[],'tags':[],
           'artifacts':[{'type':'text_document','ref':'work','label':'工作方案'}]}
    params={'meta':{'correlation_id':'test'},'draft':draft,'review':{'decision':'approved'},'save_mode':'eligible'}
    result=evidence.handle_evidence_save_draft(params)
    assert result['candidate_pool_eligible'] is True
    draft['results']='效率提升 300%'
    with pytest.raises(ValueError,match='no_fabrication_guard'):
        evidence.handle_evidence_save_draft(params)
    with pytest.raises(ValueError,match='unsupported material'):
        evidence._selected_markdown_materials(['work'])
