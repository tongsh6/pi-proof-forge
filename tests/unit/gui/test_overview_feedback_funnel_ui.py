"""总览页消费 overview.get 的 feedback_funnel：按状态渲染分段条与计数，零数据给空态，不把未同步算作进展。"""
import subprocess
from pathlib import Path


def test_overview_renders_feedback_funnel_from_metrics():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const llmConfig={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/llmConfig.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports:llmConfig});
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const navigations=[];
let funnel={delivered:2,viewed:8,interested:0,interview:0,rejected:4,closed:2,unknown:0,unsynced:0};
const api={getOverview:async()=>({metrics:{evidence_count:1,matched_jobs_count:1,resume_count:1,submission_count:16,feedback_funnel:funnel},recent_activities:[],match_trend:[],gaps:[]})};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/overview/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Math,Intl,Date,Map,Set,Promise,require:n=>{if(n==='react-router-dom')return{useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx,Fragment:'fragment'};if(n==='react-i18next')return{useTranslation:()=>({t:(k,o)=>o&&o.count!==undefined?k+':'+o.count:k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/llmConfig')return llmConfig;if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.OverviewPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
(async()=>{
  await settle();
  const card=by('overview-funnel');assert.ok(card,'总览应渲染投递进展卡片');
  const segs=nodes(card).filter(n=>n.props['data-funnel-segment']);
  assert.deepEqual(segs.map(n=>n.props['data-funnel-segment']),['delivered','viewed','rejected','closed'],'分段只包含非零状态且按进展顺序排列');
  assert.equal(segs[1].props.style.width,'50%','已查看 8/16 应占 50% 宽度');
  const rows=nodes(card).filter(n=>n.props['data-funnel-row']);
  assert.ok(rows.length>=6,'应列出各状态行');
  const viewedRow=rows.find(n=>n.props['data-funnel-row']==='viewed');assert.ok(text(viewedRow).includes('8'),'已查看行应显示计数 8');
  assert.ok(text(card).includes('pages.overview.funnel.synced:16')||text(card).includes('16'),'应显示已同步/总数');
  const open=nodes(card).find(n=>n.type==='button'&&text(n).trim()==='pages.overview.funnel.open');assert.ok(open,'应有进入投递记录的入口');open.props.onClick();assert.equal(navigations.at(-1),'/submissions');
  funnel={delivered:0,viewed:0,interested:0,interview:0,rejected:0,closed:0,unknown:0,unsynced:0};
  const refresh=nodes(tree).find(n=>n.type==='button'&&text(n).trim()==='pages.overview.refresh');await refresh.props.onClick();await settle();
  assert.ok(text(by('overview-funnel')).includes('pages.overview.funnel.empty'),'没有投递时应显示空态');
  assert.equal(nodes(by('overview-funnel')).filter(n=>n.props['data-funnel-segment']).length,0,'空态不渲染分段');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
