"""Quick Run 真实阶段进度：轮询 tracker 与页面阶段状态。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# 页面模块的所有依赖 mock；纯函数测试与渲染测试共用。
COMMON_PRELUDE = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const exports={},jsx=(type,props)=>({type,props:props||{}});
const llmConfig={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/llmConfig.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports:llmConfig});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const stageStatus=(stepKey)=>{const card=nodes(tree).find(n=>n.props['data-stage']===stepKey);return card?card.props['data-stage-status']:undefined};
'''



TRACKER_TEST = COMMON_PRELUDE + r'''
(async()=>{
const state={attachRunId(k,id){this.attached=id},setProgress(k,p){this.progress=p},finish(k,r){this.finished=r},fail(k,d){this.failed=d}};
const taskStore={getState:()=>state};
const notifyCalls=[];let responses=[];let errors=0;
const api={getQuickRun:async()=>{if(errors>0){throw Error('poll failed')}const next=responses.shift();if(!next)throw Error('no more responses');return next}};
const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/quick-run-tracker.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports,console,Set,Promise,
require:n=>{if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:(tone,title,desc)=>notifyCalls.push([tone,title,desc])};if(n==='@/state/task-store')return{useTaskStore:taskStore};throw Error(n)}});
const {trackQuickRun,isQuickRunTerminal}=exports;
assert.equal(isQuickRunTerminal('RUNNING'),false);assert.equal(isQuickRunTerminal('DONE'),true);
responses=[{run_id:'qr1',status:'RUNNING',progress:{stages:[{key:'match',status:'running',elapsed_seconds:3}]}},{run_id:'qr1',status:'DONE',progress:{stages:[{key:'match',status:'done',elapsed_seconds:9}]}}];
const result=await trackQuickRun('qr1',{sleep:async()=>{},getRun:api.getQuickRun,doneMessage:'done',failedMessage:'failed'});
assert.equal(state.attached,'qr1');assert.equal(state.progress.stages[0].status,'done');assert.equal(state.finished.run_id,'qr1');
assert.equal(result.status,'DONE');assert.equal(notifyCalls.length,1);assert.equal(notifyCalls[0][0],'success');
// 轮询失败达到上限时收口为 error，不伪造成功。
const state2={attachRunId(){},setProgress(){},finish(){throw Error('must not finish')},fail(kind,d){this.failed=d}};
const api2={getQuickRun:async()=>{throw Error('offline')}};
const exports2={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/quick-run-tracker.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports:exports2,console,Set,Promise,
require:n=>{if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api2;if(n==='@/lib/ui')return{notify:()=>{}};if(n==='@/state/task-store')return{useTaskStore:{getState:()=>state2}};throw Error(n)}});
const failed=await exports2.trackQuickRun('qr2',{sleep:async()=>{},maxPollErrors:2,failedMessage:'failed'});
assert.equal(failed,null);assert.ok(state2.failed.includes('offline'));
console.log('tracker ok');
})().catch(e=>{console.error(e);process.exitCode=1});
'''

STAGE_FUNCTION_TEST = COMMON_PRELUDE + r'''
const stageState={tasks:{},getState:()=>stageState};
const api={};const navigations=[];
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/quick-run/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Map,Set,URLSearchParams,window:{setInterval:()=>0,clearInterval:()=>{}},
require:(n=>{if(n==='react-router-dom')return{useSearchParams:()=>[new URLSearchParams()],useNavigate:()=>()=>{}};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:k=>k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/llmConfig')return llmConfig;if(n==='@/lib/quick-run-tracker')return{isQuickRunTerminal:()=>false,trackQuickRun:async()=>null};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};if(n==='@/state/task-store')return{useTaskStore:Object.assign(sel=>sel(stageState),{getState:()=>stageState})};if(n==='@/components/pdf-quality-summary')return{PdfQualitySummary:()=>null};if(n==='@/components/quality-report')return{QualityReportPanel:()=>null};throw Error(n)})});
const {getStageStatus}=exports;const progress={stages:[{key:'extract',status:'done'},{key:'match',status:'running'},{key:'generate',status:'waiting'},{key:'evaluate',status:'waiting'}]};
assert.equal(getStageStatus('running',null,'',0,progress.stages,'extract'),'done');
assert.equal(getStageStatus('running',null,'',1,progress.stages,'match'),'running');
assert.equal(getStageStatus('running',null,'',2,progress.stages,'generate'),'waiting');
assert.equal(getStageStatus('running',null,'',1,undefined,'match'),'waiting');
assert.equal(getStageStatus('running',null,'',2,undefined,'generate'),'waiting');
assert.equal(getStageStatus('done','DONE','',2,undefined,'generate'),'done');
assert.equal(getStageStatus('error','FAILED','generation',0,undefined,'extract'),'done');
assert.equal(getStageStatus('error','FAILED','generation',1,undefined,'match'),'done');
assert.equal(getStageStatus('error','FAILED','generation',2,undefined,'generate'),'error');
assert.equal(getStageStatus('error','FAILED','generation',3,undefined,'evaluate'),'waiting');
assert.equal(getStageStatus('error','SKIPPED','matching-scoring',0,undefined,'extract'),'done');
assert.equal(getStageStatus('error','SKIPPED','matching-scoring',1,undefined,'match'),'skipped');
assert.equal(getStageStatus('error','SKIPPED','matching-scoring',3,undefined,'evaluate'),'skipped');
console.log('stage function ok');
'''

RENDER_TEST = COMMON_PRELUDE + r'''
let searchParams=new URLSearchParams({job_profile_id:'job-a'});const navigations=[];
const taskStore={tasks:{},start(t){this.tasks[t.kind]={...t,status:'running',startedAt:Date.now()}},attachRunId(k,id){if(this.tasks[k])this.tasks[k].runId=id},
setProgress(k,p){if(this.tasks[k])this.tasks[k].progress=p},finish(k,r){if(this.tasks[k])this.tasks[k]={...this.tasks[k],status:'done',finishedAt:Date.now(),result:r}},
fail(k,d){if(this.tasks[k])this.tasks[k]={...this.tasks[k],status:'error',detail:d,finishedAt:Date.now()}},clear(k){delete this.tasks[k]}};
const calls=[];let trackerResolve=null;let trackerPromise=null;
const runningProgress={stages:[{key:'extract',status:'done',elapsed_seconds:1},{key:'match',status:'running',elapsed_seconds:4,started_at:'2026-10-22T00:00:00Z'},{key:'generate',status:'waiting'},{key:'evaluate',status:'waiting'}]};
const doneResult={run_id:'qr1',status:'DONE',resume_pdf:'outputs/qr1/resume.pdf',resume_readiness:{content_ready:true,status:'NEEDS_REVIEW',reasons:[],gap_tasks:[],quality_passed:false},traceability:{evidence_card_ids:['ec1'],resume_traceable:true},score_breakdown:{},progress:{stages:[{key:'extract',status:'done'},{key:'match',status:'done'},{key:'generate',status:'done'},{key:'evaluate',status:'done'}]}};
const failedResult={run_id:'qr2',status:'FAILED',failed_step:'generation',reason:'模型失败',progress:{stages:[{key:'extract',status:'done'},{key:'match',status:'done'},{key:'generate',status:'error'},{key:'evaluate',status:'waiting'}]}};
const startQuickRunMock=async payload=>{calls.push(payload);return{run_id:'qr1',status:'RUNNING',progress:runningProgress}};
const trackQuickRunMock=async(id,options)=>{calls.push('track:'+id);trackerPromise=new Promise(resolve=>{trackerResolve=resolve});return trackerPromise};
const api={getProfile:async()=>({profile:{career_status:{ready:true,reviewed:true,missing:[]}}}),
listEvidence:async()=>({items:[{evidence_id:'ec1',title:'项目一',status:'saved_eligible'}],next_cursor:null}),
listEvidenceMaterialSources:async()=>({items:[{material_id:'work',label:'工作'}]}),
listJobProfiles:async()=>({items:[{job_profile_id:'job-a',status:'active',title:'目标A',company:'A公司',source_jd:'完整要求A'},{job_profile_id:'job-b',status:'active',title:'目标B',company:'B公司',source_jd:'完整要求B'}],next_cursor:null}),
getSettings:async()=>({llm_config:{api_key:{configured:false}}}),startQuickRun:startQuickRunMock,
checkQuickRunDirection:async()=>({direction:null,requires_confirmation:false})};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/quick-run/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Map,Set,URLSearchParams,window:{setInterval:()=>0,clearInterval:()=>{}},
require:(n=>{if(n==='react-router-dom')return{useSearchParams:()=>[searchParams,p=>searchParams=new URLSearchParams(p)],useNavigate:()=>url=>navigations.push(url)};
if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:k=>k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});
if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/llmConfig')return llmConfig;
if(n==='@/lib/quick-run-tracker')return{isQuickRunTerminal:s=>['DONE','SKIPPED','FAILED','TIMEOUT','stopped'].includes(s),trackQuickRun:trackQuickRunMock};
if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};
if(n==='@/state/task-store')return{useTaskStore:Object.assign(sel=>sel(taskStore),{getState:()=>taskStore})};
if(n==='@/components/pdf-quality-summary')return{PdfQualitySummary:()=>null};if(n==='@/components/quality-report')return{QualityReportPanel:()=>null};throw Error(n)})});
async function settle(){for(let i=0;i<12;i++){index=0;tree=exports.QuickRunPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const startButton=()=>nodes(tree).find(n=>n.props['data-automation-id']==='quick-run-start');
(async()=>{await settle();
const material=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.quickRun.materialSource');material.props.onChange({target:{value:'work'}});await settle();
assert.equal(startButton().props.disabled,false);
await startButton().props.onClick();await settle();
assert.ok(calls.some(c=>c==='track:qr1'),'RUNNING 后应进入轮询 tracker');
taskStore.setProgress('quickRun',runningProgress);await settle();
assert.equal(stageStatus('extract'),'done');assert.equal(stageStatus('match'),'running');assert.equal(stageStatus('generate'),'waiting');assert.equal(stageStatus('evaluate'),'waiting');
assert.ok(text(tree).includes('pages.quickRun.progress.running'),'进行中阶段应显示本阶段耗时');
taskStore.setProgress('quickRun',doneResult.progress);trackerResolve(doneResult);await settle();await settle();
assert.equal(stageStatus('extract'),'done');assert.equal(stageStatus('match'),'done');assert.equal(stageStatus('generate'),'done');assert.equal(stageStatus('evaluate'),'done');
assert.ok(nodes(tree).find(n=>n.props['data-testid']==='quick-run-prepare-pdf'),'完成后应显示准备 PDF');
// 失败阶段：只有失败阶段 error，后续等待；结果不得伪造完成。
api.startQuickRun=async()=>({run_id:'qr2',status:'RUNNING',progress:runningProgress});
await startButton().props.onClick();await settle();
trackerResolve(failedResult);await settle();await settle();
assert.equal(stageStatus('extract'),'done');assert.equal(stageStatus('match'),'done');assert.equal(stageStatus('generate'),'error');assert.equal(stageStatus('evaluate'),'waiting');
// 目标切换后旧轮询结果不得覆盖新页面的状态。
api.startQuickRun=async()=>({run_id:'qr3',status:'RUNNING',progress:runningProgress});
await startButton().props.onClick();await settle();
searchParams=new URLSearchParams({job_profile_id:'job-b'});await settle();
trackerResolve(doneResult);await settle();await settle();
assert.equal(nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.quickRun.selectProfile').props.value,'job-b');
assert.ok(!nodes(tree).find(n=>n.props['data-testid']==='quick-run-prepare-pdf'),'旧目标结果不得显示');
console.log('render ok');
})().catch(e=>{console.error(e);process.exitCode=1});
'''


def _run_node(script: str) -> None:
    result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_quick_run_tracker_polls_and_settles_task():
    _run_node(TRACKER_TEST)


def test_quick_run_stage_status_uses_real_progress():
    _run_node(STAGE_FUNCTION_TEST)


def test_quick_run_page_renders_stage_progress_and_terminal_states():
    _run_node(RENDER_TEST)
