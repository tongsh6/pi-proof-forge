import subprocess
from pathlib import Path


def test_career_editor_saves_draft_separately_from_confirmation():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree,requests=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useRef(v){let i=cursor++;if(!hooks[i])hooks[i]={current:v};return hooks[i]},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let p={revision:'r1',career:{schema_version:1,summary:'',work:[],education_visibility:'show',education:[],skills:[],extras:[]},career_status:{reviewed:false,missing:[{field:'work',label:'工作经历未填写'}]}};
let saved;const api={listEvidence:async()=>({items:[{evidence_id:'ec1',title:'真实项目',status:'saved_eligible',candidate_pool_eligible:true}]}),updateProfile:async(patch,revision)=>{requests.push(['save',patch,revision]);saved=patch.career;return{saved:true}},reviewCareerProfile:async revision=>{requests.push(['review',revision]);return{profile:{...p,career_status:{reviewed:true,missing:[]}}}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/resumes/career-profile.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,JSON,Set,Date,crypto:{randomUUID:()=>String(Math.random())},require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='@/lib/sidecar/api'?api:n==='@/lib/errors'?{getErrorMessage:String}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
async function settle(){for(let i=0;i<7;i++){cursor=0;tree=exports.CareerProfileEditor({profile:p,onSaved:async()=>{p={...p,career:saved||p.career,revision:saved?'r2':p.revision}}});let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();assert.ok(by('career-editor'));assert.ok(by('career-confirm').props.disabled);await by('career-add-work').props.onClick();await settle();assert.equal(nodes(tree).filter(n=>n.props['data-field']==='company').length,1);
by('career-summary').props.onChange({target:{value:'真实工作经历摘要'}});await settle();await by('career-save').props.onClick();await settle();assert.equal(requests[0][0],'save');assert.equal(requests[0][2],'r1');assert.equal(requests[0][1].career.work.length,1);assert.ok(by('career-confirm').props.disabled);assert.equal(requests.filter(x=>x[0]==='review').length,0);
p={...p,revision:'r3',career_status:{reviewed:false,missing:[]}};await settle();by('career-consent').props.onChange({target:{checked:true}});await settle();await by('career-confirm').props.onClick();await settle();assert.equal(requests.at(-1)[0],'review');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
