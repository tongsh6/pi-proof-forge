"""证据页信息架构：进入即对账、汇总条计数筛选、详情面板承载对账发现。"""
import subprocess
from pathlib import Path


def test_reconcile_summary_filters_and_detail_diagnosis():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=(id,title,status,eligible)=>({evidence_id:id,title,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',status,candidate_pool_eligible:eligible,score:80,updated_at:'',time_range_level:'L1',role_scope_level:'L1',source_document_count:2});
const calls=[],reconcileCalls=[];const api={listEvidence:async()=>({items:[card('A','标题A','saved_incomplete',false),card('B','标题B','saved_eligible',true)]}),
listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>{calls.push(['get',id]);return{evidence:{evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',context:'背景',actions:'行动',results:'成果',stack:['Java'],tags:['后端'],artifacts:[],source_documents:[],source_material_ids:[id],time_range_provenance:{level:'L1'},role_scope_provenance:{level:'L1'}}}},
reconcileEvidence:async ids=>{reconcileCalls.push(ids);return{summary:{total:2,eligible:1,incomplete:1,legacy:0,untraceable_cards:1,missing_time_range:1,missing_role_scope:0,duplicate_cards:0,triaged_out:0,needs_fill:0,untriaged:1},items:[{evidence_id:'A',title:'标题A',pool_status:'incomplete',has_source:true,traceable_results:0,untraceable_results:['改写句'],suggested_sources:[],verbatim_candidates:[{result:'改写句',verbatim:'原句',similarity:0.8}],missing_fields:['time_range'],date_hints:['2024-06'],possible_duplicates:['B'],triage:null}]}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,document:{querySelector:()=>null},require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const tid=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
(async()=>{await settle();
assert.equal(reconcileCalls.length,1,'进入页面自动对账一次');
assert.ok(!tid('evidence-reconcile-fold')&&!tid('evidence-reconcile-list'),'不再有独立对账折叠区/列表');
assert.ok(!tid('evidence-reconcile-preview'),'不再有行内就地摘要');
assert.ok(tid('evidence-summary'),'应有常驻对账汇总条');
assert.ok(text(tid('evidence-summary-counts')).includes('pages.evidence.summary.all')&&text(tid('evidence-summary-counts')).includes('2'),'汇总条显示全部计数');
assert.ok(text(tid('evidence-summary-counts')).includes('pages.evidence.summary.untraceable'),'汇总条显示不可追溯计数');
const rows=()=>nodes(tree).filter(n=>n.type==='tr').filter(r=>nodes(r).some(x=>x.type==='td'));
assert.equal(rows().length,2,'默认列出全部卡');
nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-summary-untraceable').props.onClick();await settle();
assert.equal(rows().length,1,'点击汇总计数即筛选列表');
assert.ok(text(rows()[0]).includes('标题A')&&text(rows()[0]).includes('pages.evidence.summary.tags.untraceable'),'问题标签与筛选同源');
rows()[0].props.onClick();await settle();
assert.ok(calls.some(c=>c[0]==='get'&&c[1]==='A'),'点行加载详情');
assert.ok(tid('evidence-diagnosis'),'详情面板应显示对账发现');
const diag=tid('evidence-diagnosis');
assert.ok(text(diag).includes('改写句')&&text(diag).includes('2024-06'),'对账发现显示不可追溯结果与时间线索');
assert.ok(tid('evidence-triage-select'),'分流控件在对账发现区');
const view=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-view');assert.equal(view,undefined,'列表行不再承载查看按钮');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
