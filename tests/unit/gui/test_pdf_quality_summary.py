from pathlib import Path
import subprocess


def test_quality_summary_distinguishes_unknown_failed_and_passed():
    root=Path(__file__).resolve().parents[3]
    path=root/'ui/src/components/pdf-quality-summary.tsx'
    assert path.exists(), '审批质量信息组件尚未实现'
    js=r'''
const fs=require('fs'),ts=require('typescript'),vm=require('vm'),assert=require('assert/strict');
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(process.argv[1],'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:n=>n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:{} });
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const render=q=>text(exports.PdfQualitySummary({quality:q}));
const unknown=render({status:'unrecorded'});assert.ok(unknown.includes('quality.unrecorded'));assert.ok(!unknown.includes('/100'));
const failed=render({status:'bound',matching_score:86,resume_score:43,expression_score:70,content_ready:true,quality_passed:false,gap_tasks:['本人职责待核对']});
assert.ok(failed.includes('86')&&failed.includes('43')&&failed.includes('70'));assert.ok(failed.includes('quality.failed'));assert.ok(failed.includes('本人职责待核对'));assert.ok(!failed.includes('quality.passed'));
const passed=render({status:'bound',content_ready:true,quality_passed:true,gap_tasks:[]});assert.ok(passed.includes('quality.passed'));
'''
    r=subprocess.run(['node','-e',js,str(path)],cwd=root/'ui',capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
