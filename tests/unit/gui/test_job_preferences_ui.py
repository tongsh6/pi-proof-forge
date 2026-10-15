"""偏好预览不能自动生效，保存要绑定来源和修订号。"""
import subprocess
from pathlib import Path


def test_preferences_preview_then_confirm_save():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
const hooks=[];let index=0,effects=[],tree,saved=0;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((x,i)=>x===b[i]);
const react={useState(v){let i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useRef(v){let i=index++;return hooks[i]||(hooks[i]={current:v})},useEffect(fn,deps){let i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const calls=[],draft={schema_version:1,source:{material_id:'m1',document_id:'d1',sha256:'hash',filename:'m1.md',label:'求职资料'},items:[{kind:'primary',text:'产品平台 Tech Lead',quote:'主投产品平台 Tech Lead。'}]};
const api={listMaterialDocuments:async()=>({items:[{document_id:'d1',label:'求职资料'}]}),generateJobPreferences:async(...args)=>{calls.push(['generate',...args]);return{draft}},saveJobPreferences:async(...args)=>{calls.push(['save',...args]);return{preferences:{...draft,revision:'new'}}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/resumes/job-preferences.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2021}}).outputText,{exports,console,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='@/lib/sidecar/api'?api:n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},buttonClass:{primary:'',secondary:''}}:(()=>{throw Error(n)})()});
const props={profile:{job_preferences:{schema_version:1,revision:'old',items:[],source:null}},materials:[{material_id:'m1',label:'求职资料'}],onSaved:async()=>saved++};
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.JobPreferencesEditor(props);let p=effects;effects=[];p.forEach(fn=>fn());await Promise.resolve()}}
const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
(async()=>{await settle();assert.equal(calls.length,0);by('preferences-material').props.onChange({target:{value:'m1'}});await settle();await by('preferences-generate').props.onClick();await settle();assert.equal(saved,0);assert.equal(calls.length,1);assert.ok(text(tree).includes('主投产品平台 Tech Lead。'));assert.equal(by('preferences-save').props.disabled,true);by('preferences-confirm').props.onChange({target:{checked:true}});await settle();await by('preferences-save').props.onClick();await settle();assert.equal(saved,1);assert.equal(calls[1][0],'save');assert.equal(calls[1][2],'old');assert.equal(calls[1][1].source.material_id,'m1')})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
