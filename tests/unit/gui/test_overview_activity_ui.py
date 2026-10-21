"""总览最近活动：展示可读的目标岗位/公司/平台/状态（本地化），不回显运行编号或文件名。

使用真实 zh.json 文案，回归“编号没人能看懂”的活动流展示缺陷。
"""
import subprocess
from pathlib import Path


SCRIPT = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const zh=JSON.parse(fs.readFileSync('ui/src/i18n/zh.json','utf8'));
const lookup=(key)=>{let cur=zh;for(const part of key.split('.')){if(cur&&typeof cur==='object'&&part in cur)cur=cur[part];else return undefined;}return cur;};
const translate=(key,options)=>{const value=lookup(key);if(value===undefined)return options&&options.defaultValue!==undefined?options.defaultValue:key;if(typeof value!=='string')return key;return value.replace(/\{\{(\w+)\}\}/g,(_,name)=>options&&options[name]!==undefined?String(options[name]):'');};
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const activities=[
  {activity_id:'submission_native-f61d',type:'submission_sent',description:'Submission success via liepin',timestamp:'2026-10-21T15:17:33+00:00',target_role:'高级全栈工程师',company:'某上海专业技术服务公司',platform:'liepin',status:'success'},
  {activity_id:'resume_mapped_b',type:'resume_generated',description:'Generated resume_mr-qr_20261021133955495233_B.md',timestamp:'2026-10-21T13:39:55+00:00',target_role:'高级全栈工程师',company:'某上海专业技术服务公司',variant:'B'},
  {activity_id:'evidence_title',type:'evidence_imported',description:'Evidence updated: MongoDB 索引治理',timestamp:'2026-10-21T13:30:00+00:00',title:'MongoDB 索引治理'},
  {activity_id:'resume_legacy',type:'resume_generated',description:'Resume generated (variant A)',timestamp:'2026-10-20T10:00:00+00:00',variant:'A'},
  {activity_id:'submission_legacy',type:'submission_sent',description:'Submission blocked via liepin',timestamp:'2026-10-19T10:00:00+00:00',platform:'liepin',status:'blocked'},
  {activity_id:'agent_run',type:'agent_run_completed',description:'Agent run completed',timestamp:'2026-10-18T10:00:00+00:00'},
];
const api={
  getOverview:async()=>({metrics:{evidence_count:1,matched_jobs_count:1,resume_count:1,submission_count:1},recent_activities:activities,match_trend:[],gaps:[]}),
  getSettings:async()=>({llm_config:{provider:'deepseek',model:'deepseek-flash',base_url:null,api_key:{configured:true,masked:'****',updated_at:''},timeout:30,temperature:0}}),
  getMaterialReadiness:async()=>({status:'ready',missing_items:[]}),
  listJobProfiles:async()=>({items:[{job_profile_id:'jp_1'}]}),
};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/overview/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Math,Intl,Date,Map,Set,Promise,require:n=>{if(n==='react-router-dom')return{useNavigate:()=>()=>{}};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx,Fragment:'fragment'};if(n==='react-i18next')return{useTranslation:()=>({t:translate,i18n:{language:'zh'}})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/llmConfig')return{isLlmConfigured:()=>true};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};if(n==='i18next')return{};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.OverviewPage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
const row=id=>nodes(by('overview-activity')).find(n=>n.props['data-activity-id']===id);
(async()=>{
  await settle();
  const panel=by('overview-activity');assert.ok(panel,'总览应渲染最近活动列表');
  const rows=nodes(panel).filter(n=>n.props['data-activity-id']);
  assert.equal(rows.length,6,'活动列表渲染全部事件');
  const submission=row('submission_native-f61d');assert.ok(submission,'投递事件应可见');
  const submissionText=text(submission);
  assert.ok(submissionText.includes('高级全栈工程师')&&submissionText.includes('某上海专业技术服务公司'),'投递事件应展示目标岗位与公司');
  assert.ok(submissionText.includes('猎聘')&&submissionText.includes('成功'),'投递事件应展示本地化平台与状态');
  assert.ok(!submissionText.includes('native-f61d'),'投递事件不得回显运行编号');
  const mapped=row('resume_mapped_b');
  const mappedText=text(mapped);
  assert.ok(mappedText.includes('高级全栈工程师')&&mappedText.includes('B 版'),'简历事件应展示目标岗位与版本');
  assert.ok(!mappedText.includes('resume_mr-')&&!mappedText.includes('qr_2026'),'简历事件不得回显文件名或运行编号');
  const evidence=row('evidence_title');
  assert.ok(text(evidence).includes('MongoDB 索引治理'),'证据事件应展示证据标题');
  assert.ok(!text(evidence).includes('Evidence updated'),'证据事件不应回显英文原始描述');
  const legacyResume=row('resume_legacy');
  assert.ok(text(legacyResume).includes('已生成 A 版简历'),'缺少岗位信息的简历事件使用本地化回退文案');
  const legacySubmission=row('submission_legacy');
  assert.ok(text(legacySubmission).includes('猎聘')&&text(legacySubmission).includes('已阻断'),'缺少岗位信息的投递事件仍展示平台与状态');
  const agentRun=row('agent_run');
  assert.ok(text(agentRun).includes('Agent run completed'),'未结构化的事件回退到后端描述');
})().catch(e=>{console.error(e);process.exitCode=1});
'''


def test_overview_activity_shows_readable_targets_instead_of_run_ids():
    result = subprocess.run(
        ["node", "-e", SCRIPT],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
