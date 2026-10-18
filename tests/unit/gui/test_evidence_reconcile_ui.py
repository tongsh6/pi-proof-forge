"""材料对账折叠区：展开时才调用对账接口，列出有问题的卡与原因，“查看”进入该卡详情。"""
import subprocess
from pathlib import Path


def test_reconcile_fold_runs_on_open_and_lists_problem_cards():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=id=>({evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',context:'背景',actions:'行动',results:'成果',stack:['Java'],tags:['后端'],artifacts:[],source_material_ids:[id],source_documents:[]});
const calls=[],reconcileCalls=[],scrolls=[];const api={listEvidence:async()=>({items:[{...card('A'),status:'saved_eligible',score:80,updated_at:''}]}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>{calls.push(['get',id]);return{evidence:card(id)}},reconcileEvidence:async ids=>{reconcileCalls.push(ids);return{summary:{total:3,eligible:1,incomplete:1,legacy:1,untraceable_cards:1,missing_time_range:2,missing_role_scope:1,duplicate_cards:1},items:[{evidence_id:'A',title:'标题A',pool_status:'eligible',has_source:true,traceable_results:2,untraceable_results:[],suggested_sources:[],verbatim_candidates:[],missing_fields:[],date_hints:[],possible_duplicates:[]},{evidence_id:'B',title:'标题B',pool_status:'incomplete',has_source:true,traceable_results:1,untraceable_results:['改写句'],suggested_sources:[],verbatim_candidates:[{result:'改写句',verbatim:'原句',similarity:0.8}],missing_fields:['time_range'],date_hints:['2024-06','2024-09'],possible_duplicates:['A']},{evidence_id:'C',title:'标题C',pool_status:'legacy',has_source:false,traceable_results:0,untraceable_results:[],suggested_sources:[{material_id:'m',document:'d',result:'r'}],verbatim_candidates:[],missing_fields:['role_scope'],date_hints:[],possible_duplicates:[]}]}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,document:{querySelector:sel=>sel==='[data-testid="evidence-detail-panel"]'?{scrollIntoView:()=>scrolls.push(sel)}:null},require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}]}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
const titleInput=()=>nodes(tree).find(n=>n.type==='input'&&n.props.placeholder==='pages.evidence.fields.title');
(async()=>{await settle();
const fold=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-fold');assert.ok(fold,'证据页应有材料对账折叠区');
assert.equal(reconcileCalls.length,0,'未展开前不调用对账接口');
assert.ok(text(fold).includes('pages.evidence.reconcile.hint'),'未对账时显示提示');
fold.props.onToggle({currentTarget:{open:true}});await settle();
assert.equal(reconcileCalls.length,1,'展开时调用一次对账接口');
const list=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-list');assert.ok(list,'应渲染问题清单');
const rows=nodes(list).filter(n=>n.type==='li');assert.equal(rows.length,2,'只列有问题的卡（B、C），正常卡 A 不出现');
assert.ok(text(rows[0]).includes('标题B'),'结果不可追溯的卡排最前');
assert.ok(text(rows[0]).includes('pages.evidence.reconcile.reasons.untraceable')&&text(rows[0]).includes('pages.evidence.reconcile.reasons.missingTimeHint')&&text(rows[0]).includes('pages.evidence.reconcile.reasons.duplicate'),'原因串包含不可追溯、缺时间线索与疑似重复');
assert.ok(text(rows[1]).includes('pages.evidence.reconcile.reasons.noSource')&&text(rows[1]).includes('pages.evidence.reconcile.reasons.missingRole'));
const fold2=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-fold');assert.ok(text(fold2).includes('pages.evidence.reconcile.summaryLine'),'对账后摘要行替换提示');
const view=nodes(rows[0]).find(n=>n.type==='button');view.props.onClick();await settle();
assert.ok(calls.some(c=>c[0]==='get'&&c[1]==='B'),'“查看”进入该卡详情');
assert.ok(scrolls.includes('[data-testid="evidence-detail-panel"]'),'“查看”后把详情面板滚入视口，避免长列表下看起来无响应');
fold2.props.onToggle({currentTarget:{open:true}});await settle();assert.equal(reconcileCalls.length,1,'已有结果时再次展开不重复调用');
const run=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-run');run.props.onClick();await settle();assert.equal(reconcileCalls.length,2,'重新对账按钮再调一次');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
