"""补全分流：在详情面板「对账发现」区标记值得补/不参与展示/重复，变更后重新对账。"""
import subprocess
from pathlib import Path


def test_reconcile_triage_controls():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=id=>({evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',status:'saved_incomplete',candidate_pool_eligible:false,score:80,updated_at:'',time_range_level:'L1',role_scope_level:'L1',source_document_count:1});
const triageCalls=[],reconcileCalls=[];const api={listEvidence:async()=>({items:[card('A')]}),listEvidenceMaterialSources:async()=>({items:[]}),
getEvidence:async id=>({evidence:{evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',context:'背景',actions:'行动',results:'成果',stack:[],tags:[],artifacts:[],source_documents:[],source_material_ids:[id],time_range_provenance:{level:'L1'},role_scope_provenance:{level:'L1'}}}),
reconcileEvidence:async ids=>{reconcileCalls.push(ids);return{summary:{total:1,eligible:0,incomplete:1,legacy:0,untraceable_cards:0,missing_time_range:0,missing_role_scope:1,duplicate_cards:1,triaged_out:0,needs_fill:0,untriaged:1},items:[{evidence_id:'A',title:'标题A',pool_status:'incomplete',has_source:true,traceable_results:1,untraceable_results:[],suggested_sources:[],verbatim_candidates:[],missing_fields:['role_scope'],date_hints:[],possible_duplicates:['C'],triage:null}]}},
setEvidenceTriage:async(id,decision,extra)=>{triageCalls.push([id,decision,extra]);return{}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,document:{querySelector:()=>null},require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const tid=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
(async()=>{await settle();
const row=nodes(tree).filter(n=>n.type==='tr').find(r=>nodes(r).some(x=>x.type==='td'));row.props.onClick();await settle();
const sel=()=>tid('evidence-triage-select');assert.ok(sel(),'详情面板应有分流下拉');
const options=nodes(sel()).filter(n=>n.type==='option').map(o=>o.props.value);
assert.deepEqual(options,['','needs_fill','not_for_display','duplicate'],'有疑似重复时才提供“重复”');
await sel().props.onChange({target:{value:'duplicate'}});await settle();
assert.equal(JSON.stringify(triageCalls[0]),JSON.stringify(['A','duplicate',{duplicate_of:'C'}]),'重复默认指向第一张疑似卡');
assert.ok(reconcileCalls.length>=2,'分流后重新对账回读');
await sel().props.onChange({target:{value:''}});await settle();
assert.equal(JSON.stringify(triageCalls[1]),JSON.stringify(['A','',{}]),'选“未分流”即清除');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
