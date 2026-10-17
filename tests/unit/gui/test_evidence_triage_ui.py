"""补全分流：对账列表里给缺字段卡标“值得补/不参与展示/重复”，已分流的默认收起，卡变化后判断过期重新出现。"""
import subprocess
from pathlib import Path


def test_reconcile_triage_controls():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=id=>({evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',context:'背景',actions:'行动',results:'成果',stack:['Java'],tags:['后端'],artifacts:[],source_material_ids:[id],source_documents:[]});
const triageCalls=[],reconcileCalls=[];const api={listEvidence:async()=>({items:[]}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>({evidence:card(id)}),
reconcileEvidence:async ids=>{reconcileCalls.push(ids);return{summary:{total:4,eligible:0,incomplete:4,legacy:0,untraceable_cards:0,missing_time_range:1,missing_role_scope:2,duplicate_cards:1,triaged_out:1,needs_fill:1,untriaged:3},items:[{evidence_id:'A',title:'标题A',pool_status:'incomplete',has_source:true,traceable_results:1,untraceable_results:[],suggested_sources:[],verbatim_candidates:[],missing_fields:['time_range'],date_hints:[],possible_duplicates:['C'],triage:null},
{evidence_id:'B',title:'标题B',pool_status:'incomplete',has_source:true,traceable_results:1,untraceable_results:[],suggested_sources:[],verbatim_candidates:[],missing_fields:['role_scope'],date_hints:[],possible_duplicates:[],triage:{decision:'not_for_display',note:'',duplicate_of:'',stale:false}},
{evidence_id:'C',title:'标题C',pool_status:'incomplete',has_source:true,traceable_results:1,untraceable_results:[],suggested_sources:[],verbatim_candidates:[],missing_fields:['role_scope'],date_hints:[],possible_duplicates:[],triage:{decision:'needs_fill',note:'',duplicate_of:'',stale:false}},
{evidence_id:'D',title:'标题D',pool_status:'incomplete',has_source:true,traceable_results:1,untraceable_results:[],suggested_sources:[],verbatim_candidates:[],missing_fields:['role_scope'],date_hints:[],possible_duplicates:[],triage:{decision:'not_for_display',note:'',duplicate_of:'',stale:true}}]}},
setEvidenceTriage:async(id,decision,extra)=>{triageCalls.push([id,decision,extra]);return{}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}]}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
const titleInput=()=>nodes(tree).find(n=>n.type==='input'&&n.props.placeholder==='pages.evidence.fields.title');
(async()=>{await settle();
const fold=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-fold');fold.props.onToggle({currentTarget:{open:true}});await settle();
let list=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-list');
let rows=nodes(list).filter(n=>n.type==='li');
assert.deepEqual(rows.map(r=>r.props['data-evidence-id']),['C','A','D'],'值得补排最前；已分流且未过期的 B 默认隐藏；过期判断的 D 重新出现');
assert.ok(text(rows[2]).includes('pages.evidence.reconcile.triage.stale'),'过期判断要标出');
const sel=r=>nodes(r).find(n=>n.type==='select'&&n.props['data-testid']==='evidence-triage-select');
const optA=nodes(sel(rows[1])).filter(n=>n.type==='option').map(o=>o.props.value);
assert.deepEqual(optA,['','needs_fill','not_for_display','duplicate'],'有疑似重复时才提供“重复”');
assert.ok(!nodes(sel(rows[0])).some(n=>n.type==='option'&&n.props.value==='duplicate'),'无疑似重复不提供“重复”');
assert.ok(text(nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-fold')).includes('pages.evidence.reconcile.triage.summary'),'摘要含分流计数');
await sel(rows[1]).props.onChange({target:{value:'duplicate'}});await settle();
assert.equal(JSON.stringify(triageCalls[0]),JSON.stringify(['A','duplicate',{duplicate_of:'C'}]),'重复默认指向第一张疑似卡');
assert.equal(reconcileCalls.length,2,'分流后重新对账回读');
await sel(rows[0]).props.onChange({target:{value:''}});await settle();
assert.equal(JSON.stringify(triageCalls[1]),JSON.stringify(['C','',{}]),'选“未分流”即清除');
const toggle=nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-triage-show-hidden');assert.ok(toggle,'应可显示已分流的卡');
toggle.props.onClick();await settle();
rows=nodes(nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-reconcile-list')).filter(n=>n.type==='li');
assert.ok(rows.some(r=>r.props['data-evidence-id']==='B'),'展开后显示已分流的 B');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
