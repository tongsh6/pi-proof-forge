"""验证采用补证原文时的草稿状态变化，使用项目已有 TypeScript 编译器。"""
import json
import subprocess
from pathlib import Path


def test_adopting_sources_keeps_prior_facts_and_replaces_only_explicit_single_field():
    root = Path(__file__).resolve().parents[3]
    source = root / 'ui/src/pages/evidence/source-merge.ts'
    assert source.exists(), '补证草稿的采用操作尚未实现'
    script = r'''
      const ts = require('typescript'), fs = require('fs');
      const code = ts.transpileModule(fs.readFileSync(process.argv[1], 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText;
      const module = {exports:{}}; new Function('exports','module',code)(module.exports,module);
      const {adoptSource} = module.exports;
      let d = {source_material_ids:['m1'],source_documents:[],artifacts:[{ref:'m1',label:'旧材料',type:'text_document'}],
               role_scope:'参与开发',time_range:'',context:'平台',actions:'保留原行动',results:'保留原成果',field_sources:[]};
      const ref = {material_id:'m2',document_id:'doc2',sha256:'hash2',label:'底稿'};
      d = adoptSource(d,'time_range','2022 – 至今',ref);
      d = adoptSource(d,'role_scope','Tech Lead',ref);
      d = adoptSource(d,'actions','建立 Feature 机制',ref);
      d = adoptSource(d,'actions','建立 Feature 机制',ref);
      d = adoptSource(d,'results','新增成果一\n新增成果二',ref);
      console.log(JSON.stringify(d));
    '''
    result = subprocess.run(['node','-e',script,str(source)],cwd=root/'ui',capture_output=True,text=True,check=True)
    draft = json.loads(result.stdout)
    assert draft['source_material_ids'] == ['m1','m2']
    assert len(draft['source_documents']) == 1 and len(draft['artifacts']) == 2
    assert draft['time_range'] == '2022 – 至今' and draft['role_scope'] == 'Tech Lead'
    assert draft['actions'] == '保留原行动\n建立 Feature 机制'
    assert draft['results'] == '保留原成果\n新增成果一\n新增成果二'
    assert len(draft['field_sources']) == 5
    assert all(c['quote'] == c['value'] for c in draft['field_sources'])
