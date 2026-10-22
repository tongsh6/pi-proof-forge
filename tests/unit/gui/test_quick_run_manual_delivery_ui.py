"""手工导入/未绑定平台线索的画像：Quick Run 只给手动投递指引，不再把用户带进必然失败的 App 内投递流程。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_manual_import_profile_gets_manual_delivery_guidance() -> None:
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let searchParams=new URLSearchParams({job_profile_id:'job-manual'});const navigations=[];const calls=[];
const taskState={tasks:{},start(){},finish(){},fail(){},clear(){}};
const api={getProfile:async()=>({profile:{career_status:{ready:true,reviewed:true,missing:[]}}}),
listEvidence:async()=>({items:[{evidence_id:'ec1',title:'项目一',status:'saved_eligible'}],next_cursor:null}),
listEvidenceMaterialSources:async()=>({items:[{material_id:'work',label:'工作'}]}),
listJobProfiles:async()=>({items:[
 {job_profile_id:'job-manual',status:'active',title:'Java技术专家',company:'得物App',source_jd:'完整JD',native_pdf_delivery:{supported:false,reason:'manual_import'}},
 {job_profile_id:'job-official',status:'active',title:'平台负责人',company:'某公司',source_jd:'完整JD',native_pdf_delivery:{supported:true,reason:''}}],next_cursor:null}),
getSettings:async()=>({llm_config:{api_key:{configured:false}}}),
checkQuickRunDirection:async()=>({direction:null,requires_confirmation:false,unavailable_reason:''}),
startQuickRun:async payload=>{calls.push(payload);return{run_id:'qr-run',status:'DONE',resume_pdf:'outputs/qr-run/exports/resume.pdf',resume_readiness:{content_ready:true,status:'NEEDS_REVIEW',reasons:[],gap_tasks:[],quality_passed:false},traceability:{evidence_card_ids:['ec1'],resume_traceable:true},score_breakdown:{}}}};
const exports={},jsx=(type,props)=>typeof type==='function'?type(props||{}):({type,props:props||{}});
const llmConfig={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/llmConfig.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports:llmConfig});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/quick-run/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Map,Set,URLSearchParams,window:{setInterval:()=>0,clearInterval:()=>{}},require:n=>{if(n==='react-router-dom')return{useSearchParams:()=>[searchParams,p=>searchParams=new URLSearchParams(p)],useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:(k)=>k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/llmConfig')return llmConfig;if(n==='@/lib/quick-run-tracker')return{isQuickRunTerminal:s=>['DONE','SKIPPED','FAILED','TIMEOUT','stopped'].includes(s),trackQuickRun:async()=>null};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};if(n==='@/state/task-store')return{useTaskStore:Object.assign(sel=>sel(taskState),{getState:()=>taskState})};if(n==='@/components/pdf-quality-summary')return{PdfQualitySummary:()=>null};if(n==='@/components/quality-report')return{QualityReportPanel:()=>null};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.QuickRunPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);const start=()=>nodes(tree).find(n=>n.props['data-automation-id']==='quick-run-start');
const materialSelect=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.quickRun.materialSource');assert.ok(materialSelect,'材料来源必须可见');materialSelect.props.onChange({target:{value:'work'}});await settle();
assert.ok(by('quick-run-manual-delivery-hint'),'手工导入画像应在输入区提前提示仅支持手动投递');
const profileSelect=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.quickRun.selectProfile');
const optionTexts=nodes(profileSelect).filter(n=>n.type==='option').map(n=>text(n));
assert.ok(optionTexts.some(value=>value.includes('pages.quickRun.manualDeliveryOnlyBadge')),'目标下拉应标注仅手动投递');
await start().props.onClick();await settle();
assert.ok(!by('quick-run-prepare-pdf'),'手工导入画像不得出现 App 内准备 PDF');
const manualResult=by('quick-run-manual-delivery-result');assert.ok(manualResult&&text(manualResult).includes('pages.quickRun.manualDeliveryHint'),'结果区应说明不可 App 内投递并给出 PDF 指引');
assert.ok(by('quick-run-record-manual'),'结果区应提供记录手动投递入口');
by('quick-run-record-manual').props.onClick();assert.equal(navigations.at(-1),'/jobs');
profileSelect.props.onChange({target:{value:'job-official'}});await settle();
await start().props.onClick();await settle();
assert.ok(by('quick-run-prepare-pdf'),'已绑定官方线索的画像应恢复正常准备 PDF');
console.log('manual delivery ui ok');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
