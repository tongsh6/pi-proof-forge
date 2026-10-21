"""总览按前置条件显示“开始前清单”（模型是否配置以密钥/本地占位是否保存过为准，keyless 本地 provider 有模型即可；后端未配置时也会返回默认 provider/model）：缺项时列出步骤并把页头主按钮指向第一个缺项；全部就绪时不显示清单，主按钮回到启动智能运行。"""
import subprocess
from pathlib import Path


SCRIPT = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const llmConfig={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/llmConfig.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports:llmConfig});
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const navigations=[];
let state=__STATE__;
const api={
  getOverview:async()=>({metrics:{evidence_count:state.evidence,matched_jobs_count:0,resume_count:0,submission_count:0},recent_activities:[],match_trend:[],gaps:[]}),
  getSettings:async()=>({llm_config:{provider:state.provider||'openai',model:state.model||'gpt-4',base_url:null,api_key:{configured:state.llmConfigured,masked:state.llmConfigured,updated_at:''},timeout:30,temperature:0}}),
  getMaterialReadiness:async()=>({status:state.readiness,missing_items:state.missing}),
  listJobProfiles:async()=>({items:state.profiles}),
};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/overview/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Math,Intl,Date,Map,Set,Promise,require:n=>{if(n==='react-router-dom')return{useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx,Fragment:'fragment'};if(n==='react-i18next')return{useTranslation:()=>({t:(k,o)=>o&&o.count!==undefined?k+':'+o.count:k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/llmConfig')return llmConfig;if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.OverviewPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
(async()=>{
  await settle();
  __ASSERTIONS__
})().catch(e=>{console.error(e);process.exitCode=1});
'''


def run(state: str, assertions: str) -> None:
    script = SCRIPT.replace('__STATE__', state).replace('__ASSERTIONS__', assertions)
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_overview_lists_missing_steps_and_points_primary_action_to_first_gap():
    run(
        "{llmConfigured:false,readiness:'incomplete',missing:['career_profile'],evidence:0,profiles:[]}",
        r'''
  const setup=by('overview-setup');assert.ok(setup,'前置条件缺失时应显示开始前清单');
  const steps=nodes(setup).filter(n=>n.props['data-setup-step']);
  assert.deepEqual(steps.map(n=>n.props['data-setup-step']),['llm','resumes','evidence','jobs'],'清单按用户旅程顺序列出四步');
  assert.ok(steps.every(n=>n.props['data-setup-done']==='false'),'四步都未完成');
  const primary=by('overview-primary-action');assert.ok(primary,'页头应有主按钮');
  assert.equal(text(primary).trim(),'pages.overview.setup.steps.llm.action','主按钮指向第一个缺项：配置模型');
  primary.props.onClick();assert.equal(navigations.at(-1),'/system-settings?section=llm');
  const stepButton=nodes(steps[1]).find(n=>n.type==='button');stepButton.props.onClick();assert.equal(navigations.at(-1),'/resumes','每一步都有直达按钮');
  assert.equal(nodes(tree).find(n=>n.type==='button'&&text(n).trim()==='pages.overview.startAgent'),undefined,'缺项时不显示启动智能运行');
''',
    )


def test_overview_hides_checklist_when_everything_is_ready():
    run(
        "{llmConfigured:true,readiness:'ready',missing:[],evidence:3,profiles:[{job_profile_id:'jp1',status:'active'}]}",
        r'''
  assert.equal(by('overview-setup'),undefined,'全部就绪时不显示清单');
  const primary=by('overview-primary-action');assert.equal(text(primary).trim(),'pages.overview.startAgent');
  primary.props.onClick();assert.equal(navigations.at(-1),'/agent-run');
''',
    )


def test_overview_partial_readiness_marks_done_steps():
    run(
        "{llmConfigured:true,readiness:'ready',missing:[],evidence:0,profiles:[]}",
        r'''
  const setup=by('overview-setup');assert.ok(setup);
  const done=Object.fromEntries(nodes(setup).filter(n=>n.props['data-setup-step']).map(n=>[n.props['data-setup-step'],n.props['data-setup-done']]));
  assert.deepEqual(done,{llm:'true',resumes:'true',evidence:'false',jobs:'false'});
  assert.equal(text(by('overview-primary-action')).trim(),'pages.overview.setup.steps.evidence.action');
''',
    )


def test_overview_treats_keyless_local_provider_with_model_as_configured():
    run(
        "{llmConfigured:false,provider:'strata',model:'qwen3.8-flash-next-q2_0',readiness:'incomplete',missing:['career_profile'],evidence:0,profiles:[]}",
        r'''
  const setup=by('overview-setup');assert.ok(setup,'其他前置缺失时清单仍显示');
  const llmStep=nodes(setup).find(n=>n.props['data-setup-step']==='llm');
  assert.equal(llmStep.props['data-setup-done'],'true','keyless Strata 已选模型且无密钥也应视为已配置');
  assert.equal(text(by('overview-primary-action')).trim(),'pages.overview.setup.steps.resumes.action','主按钮应指向下一个缺项而非配置模型');
''',
    )
