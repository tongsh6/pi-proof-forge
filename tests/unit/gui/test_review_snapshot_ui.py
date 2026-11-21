"""执行真实审批组件，验证快照、恢复与阻断结果展示。"""
import json
import subprocess
from pathlib import Path

import pytest

from tests.unit.infra.test_review_snapshot import quality_candidate


@pytest.mark.parametrize('with_quality', [False, True], ids=['unrecorded', 'm1-pending-quality'])
def test_review_restores_snapshot_and_shows_result_without_claiming_submission(with_quality):
    script = r'''
const assert = require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const ts=require('./ui/node_modules/typescript');
const llmConfig={}, quality=JSON.parse(process.argv[1]);
const translate=(key,opts={})=>key==='quality.report.llmPending'?key+' '+opts.rules:key==='quality.report.legacyValue'?key+' '+opts.rule+' '+opts.expression:key;
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/llmConfig.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports:llmConfig});
const hooks=[]; let cursor=0, effects=[], tree;
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={
 useState(initial){const slot=cursor++;if(!hooks[slot])hooks[slot]={value:typeof initial==='function'?initial():initial};return[hooks[slot].value,v=>{hooks[slot].value=typeof v==='function'?v(hooks[slot].value):v}];},
 useMemo(fn,deps){const slot=cursor++;if(!hooks[slot]||!same(hooks[slot].deps,deps))hooks[slot]={value:fn(),deps};return hooks[slot].value;},
 useCallback(fn,deps){return react.useMemo(()=>fn,deps)},
 useRef(value){return react.useMemo(()=>({current:value}),[])},
 useEffect(fn,deps){const slot=cursor++;if(!hooks[slot]||!same(hooks[slot].deps,deps)){hooks[slot]={deps};effects.push(fn)}},
};
let candidates=[{job_lead_id:'lead-1',company:'仅本地验收',position:'验证岗位',resume_version:'v7',snapshot_status:'ready',resume_preview:'# 已固定的简历内容',matching_score:20,evaluation_score:quality?99:70,round_index:0,quality_snapshot:quality}];
let results=[], status='REVIEW_PENDING',nativeQuickRun=null;const calls=[],navigations=[];
const api={
 listJobProfiles:async()=>({items:[]}),
 getSettings:async()=>({llm_config:{provider:'lm_studio',model:'test',base_url:'local',api_key:{configured:true}}}),
 getPendingReview:async(runId)=>{calls.push({pendingRunId:runId}); return ({run_id:runId||'wrong-latest-run',candidates,delivery_results:results,native_pdf_quick_run_id:nativeQuickRun})},
 recheckReceipt:async(runId,leadId)=>{calls.push({recheck:leadId,runId});results=[{job_lead_id:leadId,status:'success',success:true,code:'submitted',submission_id:'api-test',receipt_source:'app_api',app_verified:true}];status='DONE';return{status:'ready',delivery_results:results}},
 getAgentRun:async()=>({run:{run_id:'run-1',status,round:0,options:{}},events:[]}),
 submitReview:async(decisions,runId)=>{calls.push({decisions,runId});candidates=[];status='DELIVERY_BLOCKED';results=[{job_lead_id:'lead-1',status:'blocked',success:false,code:'official_delivery_contract_unverified'}];return{accepted:1,delivery_results:results}},
};
const jsx=(type,props)=>typeof type==='function'?type(props||{}):({type,props:props||{}}), exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/agent-run/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2021}}).outputText,{
 exports,console,Intl,Date,Map,Set,URLSearchParams,require:(name)=>{
  if(name==='react-router-dom')return{useSearchParams:()=>[new URLSearchParams('run_id=run-1'),()=>{}],useNavigate:()=>url=>navigations.push(url)};
  if(name==='./daily-delivery')return{DailyDeliveryPanel:()=>null};
  if(name==='react')return react;
  if(name==='react/jsx-runtime')return{jsx,jsxs:jsx,Fragment:'fragment'};
  if(name==='react-i18next')return{useTranslation:()=>({t:translate,i18n:{language:'zh'}})};
  if(name==='@/components/quality-report'){
   const component={};
   vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/components/quality-report.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2021}}).outputText,{exports:component,Set,require:n=>{
    if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};
    if(n==='react-i18next')return{useTranslation:()=>({t:translate})};
    if(n==='react-router-dom')return{useNavigate:()=>url=>navigations.push(url)};
    throw Error(n);
   }});return component;
  }
  if(name==='lucide-react')return new Proxy({}, {get:(_,key)=>key});
  if(name==='@/lib/errors')return{getErrorMessage:e=>e.message};
  if(name==='@/lib/llmConfig')return llmConfig;
  if(name==='@/lib/sidecar/api')return api;
  if(name==='@/lib/ui')return {notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};
  throw Error(name);
 }});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props?.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props?.children):String(v??'');
function render(){cursor=0;tree=exports.AgentRunPage()}
async function settle(){for(let i=0;i<15;i++){render();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
(async()=>{
 await settle();
 assert.ok(calls.filter(c=>'pendingRunId' in c).every(c=>c.pendingRunId==='run-1'),'不能恢复其他最新队列');
 assert.ok(text(tree).includes('# 已固定的简历内容'),'重开审批页应恢复快照正文');
 assert.ok(text(tree).includes('v7'),'展示审批的固定版本');
 if(quality){
  const displayed=text(tree);
  for(const tier of ['eligible','fit','strong','distinct'])assert.ok(displayed.includes('quality.report.tier.'+tier),'实际Agent页面缺少'+tier+'层报告');
  assert.ok(displayed.includes('quality.failed')&&!displayed.includes('quality.passed'),'旧分99不能冒充自动质量通过');
  const pending=quality.quality_report.llm_pending;
  assert.ok(pending.length>0&&!pending.includes('R1.4'),'纯标题夹具没有待判职责，仍有其他未判项');
  assert.ok(displayed.includes('quality.report.llmPending '+pending.join('、')),'实际未判项必须完整展示');
  assert.ok(displayed.includes('quality.report.legacyValue 99'),'旧总分作为参考展示');
  assert.ok(displayed.includes('quality.report.advice.advisory'),'质量结果是建议');
 }
 const approve=button('pages.agentRun.approve');assert.ok(approve&&!approve.props.disabled);
 await approve.props.onClick();await settle();
 assert.equal(calls.find(c=>c.decisions).runId,'run-1','恢复后使用明确运行编号');
 assert.ok(text(tree).includes('pages.agentRun.deliveryCodes.official_delivery_contract_unverified'),'审批之后必须显示实际阻断');
 results=[{job_lead_id:'lead-1',status:'unknown',success:false,code:'delivery_result_unknown',submission_id:'api-test'}];
 await button('pages.agentRun.refresh').props.onClick();await settle();
 await button('pages.agentRun.recheckReceipt').props.onClick();await settle();
 assert.equal(calls.find(c=>c.recheck).runId,'run-1');
 assert.equal(calls.find(c=>c.recheck).recheck,'lead-1');
 assert.equal(calls.filter(c=>c.decisions).length,1,'重核不能重复批准或发送');
 assert.ok(text(tree).includes('pages.agentRun.deliveryCodes.submitted'));
 candidates=[{job_lead_id:'broken',company:'损坏快照',position:'测试',resume_version:'v8',snapshot_status:'invalid',quality_snapshot:quality}];
 await button('pages.agentRun.refresh').props.onClick();await settle();
 assert.ok(button('pages.agentRun.approve').props.disabled,'损坏快照不能批准');
 assert.ok(!button('pages.agentRun.reject').props.disabled,'仍可拒绝');
 assert.ok(!text(tree).includes('quality.report.tier.eligible'),'损坏快照不能继续展示其报告为当前质量');
 nativeQuickRun='qr_native';candidates=[{job_lead_id:'pdf',company:'本地PDF',position:'测试',resume_version:'v9',snapshot_status:'ready'}];await button('pages.agentRun.refresh').props.onClick();await settle();
 assert.equal(button('pages.agentRun.approve'),undefined,'原生PDF不能误入通用批准');assert.equal(button('pages.agentRun.reject'),undefined);assert.equal(button('pages.agentRun.skip'),undefined);
 assert.ok(button('pages.agentRun.reviewNativePdf'));button('pages.agentRun.reviewNativePdf').props.onClick();assert.equal(navigations.at(-1),'/submissions?quick_run_id=qr_native');assert.equal(calls.filter(c=>c.decisions).length,1);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    quality = quality_candidate('# 已固定的简历内容')['quality_snapshot'] if with_quality else None
    result = subprocess.run(['node', '-e', script, json.dumps(quality, ensure_ascii=False)], cwd=Path(__file__).resolve().parents[3],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
