"""简历中心刷新/保存后不得卸载职业档案编辑器，否则未保存草稿会丢失（2026-10-11 UX 修复的复现测试）。"""
import subprocess
from pathlib import Path


def test_profile_save_keeps_career_editor_mounted():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let profileCalls=0,deferred=null;const toasts=[];
const profile={revision:'r1',name:'张三',phone:'',email:'',city:'',current_position:'',completeness:60,updated_at:'2026-10-11T00:00:00Z',career:{schema_version:1,summary:'',work:[],education_visibility:'show',education:[],skills:[],extras:[]},career_status:{ready:false,reviewed:false,missing:[]}};
const api={getProfile:async()=>{profileCalls++;return{profile}},listResumes:async()=>({items:[]}),listMaterials:async()=>({items:[]}),getMaterialReadiness:async()=>({status:'not_ready',missing_items:[],details:{}}),getResumePreview:async()=>({preview:null}),
updateProfile:async()=>{if(deferred)return new Promise(resolve=>{deferred.resolve=resolve});return{}},uploadResume:async()=>({}),uploadMaterial:async()=>({}),exportResumePdf:async()=>({path:'/tmp/x.pdf'})};
const CareerProfileEditor=()=>null;
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/resumes/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Map,Set,Promise,require:n=>{if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:k=>k,i18n:{language:'zh'}})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;if(n==='./career-profile')return{CareerProfileEditor};if(n==='@/lib/ui')return{notify:(tone,title)=>toasts.push([tone,title]),confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(rounds=8){for(let i=0;i<rounds;i++){index=0;tree=exports.ResumesPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const editor=()=>nodes(tree).find(n=>n.type===CareerProfileEditor);
(async()=>{
  await settle();
  assert.ok(editor(),'首次加载完成后应渲染职业档案编辑器');
  assert.ok(!text(tree).includes('common.loading'),'首次加载完成后不应再显示 loading');
  deferred={};
  const save=nodes(tree).find(n=>n.type==='button'&&text(n).trim()==='pages.resumes.profile.save');
  assert.ok(save,'应有基本资料保存按钮');
  save.props.onClick();
  await settle(3);
  assert.ok(editor(),'保存进行中编辑器不得被卸载');
  assert.ok(!text(tree).includes('common.loading'),'保存触发的重载不得整页回到 loading');
  deferred.resolve({});deferred=null;
  await settle();
  assert.ok(editor(),'保存完成后编辑器仍在');
  assert.ok(profileCalls>=2,'保存后应重新读取资料');
  assert.deepEqual(toasts.at(-1),['success','toasts.resumes.profileSaved'],'保存成功应有通知');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
