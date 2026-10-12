import subprocess
from pathlib import Path


def test_career_editor_auto_link_button_calls_api_with_current_revision():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree,requests=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useRef(v){let i=cursor++;if(!hooks[i])hooks[i]={current:v};return hooks[i]},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let p={revision:'r1',career:{schema_version:1,summary:'',work:[],education_visibility:'show',education:[],skills:[],extras:[]},career_status:{reviewed:false,missing:[{field:'work',label:'工作经历未填写'}]}};
let saved;const api={listEvidence:async()=>({items:[]}),updateProfile:async()=>({saved:true}),reviewCareerProfile:async()=>({profile:p}),autoLinkEvidence:async(rev,apply)=>{requests.push(['autolink',rev,apply]);return{applied:3,unresolved:[{evidence_id:'x',title:'t',reason:'no_signal'}],suggestions:[],already_linked:1,revision:'r9'}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/resumes/career-profile.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,JSON,Set,Date,crypto:{randomUUID:()=>String(Math.random())},require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='@/lib/sidecar/api'?api:n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
async function settle(){for(let i=0;i<7;i++){cursor=0;tree=exports.CareerProfileEditor({profile:p,onSaved:async()=>{p={...p,career:saved||p.career,revision:saved?'r2':p.revision}}});let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();const btn=by('career-autolink');assert.ok(btn,'职业档案应有自动关联按钮');assert.ok(!btn.props.disabled,'未修改时可用');
await btn.props.onClick();await settle();assert.deepEqual(requests.at(-1).slice(0,2),['autolink','r1'],'用当前修订号调用自动关联');
by('career-summary').props.onChange({target:{value:'改了'}});await settle();assert.ok(by('career-autolink').props.disabled,'有未保存修改时禁用');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
