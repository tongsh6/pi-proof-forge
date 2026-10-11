"""Quick Run 复用已有参数，材料与模型选择必须真实进入请求。"""
import subprocess
import pytest
import json
from pathlib import Path


@pytest.mark.parametrize('requested,profile_ready',[('job-b',True),('missing',True),('job-b',False)])
def test_quick_run_uses_selected_material_and_explicit_model_choice(requested,profile_ready):
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let searchParams=new URLSearchParams({job_profile_id:REQUESTED});const navigations=[];let contentReady=true,deferred=null;
const calls=[];const api={getProfile:async()=>({profile:{career_status:{ready:PROFILE_READY,reviewed:PROFILE_READY,missing:[]}}}),listEvidence:async()=>({items:[{evidence_id:'actual',title:'实际项目',status:'saved_eligible'},{evidence_id:'extra',title:'额外项目',status:'saved_eligible'},{evidence_id:'old',status:'ready'}]}),listEvidenceMaterialSources:async()=>({items:[{material_id:'sample',label:'样例'},{material_id:'work',label:'工作'}]}),listJobProfiles:async(_filters,options)=>options?.cursor?({items:[{job_profile_id:'job-b',status:'active',title:'指定目标',company:'B公司',source_jd:'完整要求B'}],next_cursor:null}):({items:[{job_profile_id:'job-a',status:'active',title:'另一目标',company:'A公司',source_jd:'完整要求A'}],next_cursor:'second'}),getSettings:async()=>({llm_config:{api_key:{configured:false}}}),
startQuickRun:async payload=>{calls.push(payload);if(deferred)return new Promise(resolve=>deferred.resolve=resolve);return{run_id:'qr_run',status:'DONE',resume_pdf:'outputs/test.pdf',resume_readiness:{content_ready:contentReady,status:contentReady?'NEEDS_REVIEW':'NEEDS_EVIDENCE',reasons:[],gap_tasks:[]},traceability:{evidence_card_ids:['actual'],resume_traceable:true},score_breakdown:{}}}};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/quick-run/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Map,Set,URLSearchParams,window:{setInterval:()=>0,clearInterval:()=>{}},require:n=>{if(n==='react-router-dom')return{useSearchParams:()=>[searchParams,p=>searchParams=new URLSearchParams(p)],useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:k=>k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return {notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.QuickRunPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
const selected=()=>nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.quickRun.selectProfile');
assert.equal(calls.length,0,'导航不得自动生成');assert.equal(selected().props.value,REQUESTED,'不得静默改为列表首项');
if(REQUESTED==='missing'||!PROFILE_READY){assert.ok(nodes(tree).find(n=>n.props['data-automation-id']==='quick-run-start').props.disabled);assert.ok(text(tree).includes(REQUESTED==='missing'?'pages.quickRun.targetUnavailable':'pages.quickRun.profileRequired'));return;}
let select=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.quickRun.materialSource');assert.ok(select,'材料必须可选');select.props.onChange({target:{value:'work'}});await settle();
const extra=nodes(tree).find(n=>n.props['data-evidence-id']==='extra');assert.ok(extra,'缺少复用evidence_ids的选材入口');extra.props.onChange({target:{checked:false}});await settle();
let start=()=>nodes(tree).find(n=>n.type==='button'&&text(n).includes('pages.quickRun.start'));assert.equal(start().props.disabled,false,'第二页的有效目标也应可启动');await start().props.onClick();await settle();
assert.equal(calls[0].job_profile_id,'job-b');assert.ok(by('quick-run-prepare-pdf'));by('quick-run-prepare-pdf').props.onClick();assert.equal(navigations.at(-1),'/submissions?quick_run_id=qr_run');
assert.equal(calls[0].options.material_id,'work');assert.equal(calls[0].options.use_llm,false);assert.equal(calls[0].options.require_llm,false);assert.deepEqual(calls[0].options.evidence_ids,['actual']);
let toggle=nodes(tree).find(n=>n.type==='input'&&n.props.type==='checkbox');toggle.props.onChange({target:{checked:true}});await settle();assert.ok(!by('quick-run-prepare-pdf'),'改输入即清旧结果');contentReady=false;await start().props.onClick();await settle();assert.equal(calls[1].options.require_llm,true);assert.ok(!by('quick-run-prepare-pdf'),'DONE不代表完整内容');
deferred={};await start().props.onClick();await settle();assert.ok(selected().props.disabled);searchParams=new URLSearchParams({job_profile_id:'job-a'});await settle();deferred.resolve({run_id:'late-old-run',status:'DONE',resume_pdf:'old.pdf',resume_readiness:{content_ready:true,reasons:[],gap_tasks:[]},traceability:{evidence_card_ids:['actual'],resume_traceable:true}});await settle();assert.equal(selected().props.value,'job-a');assert.ok(!by('quick-run-prepare-pdf'),'晚到旧目标响应不应覆盖新选择');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    script=script.replace('REQUESTED',json.dumps(requested)).replace('PROFILE_READY',str(profile_ready).lower())
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
