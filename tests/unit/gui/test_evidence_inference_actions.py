"""执行真实页面回调，验证逐条/批量确认的指纹接续与部分成功状态。"""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["single", "batch", "partial", "switch"])
def test_inference_confirmation_tracks_each_success(mode):
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
const mode=process.argv[1];
let hooks=[],cursor=0,effects=[],tree;
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},
useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},
useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card={evidence_id:'A',title:'售后服务',time_range:'',role_scope:'',context:'背景',actions:'行动',results:'成果',stack:['Java'],tags:[],artifacts:[],source_material_ids:['mat'],source_documents:[]};
let sha='sha0',inferenceCalls=0,failOnce=mode==='partial',release;
const second={...card,evidence_id:'B',title:'其他项目'};
const candidates=['time_range','role_scope'].map(field=>({field,value:field==='time_range'?'2023':'参与改造',level:'L3',confidence:.8,candidate_hash:field,evidence:[]}));
let pending=[...candidates],calls=[];
const api={
listEvidence:async()=>({items:[card,second].map(c=>({...c,status:'saved_eligible',updated_at:''}))}),
listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>({evidence:id==='B'?second:card}),
reconcileEvidence:async()=>({items:[{evidence_id:'A',missing_fields:[],untraceable_results:[],verbatim_candidates:[],date_hints:[],possible_duplicates:[],has_source:true}],summary:{total:1}}),
inferEvidenceFields:async()=>{inferenceCalls++;return{enabled:true,cards:[{card_id:'A',card_sha256:sha,candidates:[...pending]}],summary:{requested:1,candidates:pending.length}}},
confirmEvidenceInference:async p=>{calls.push({...p});assert.equal(p.card_sha256,sha,'下一字段必须使用上一次返回的新指纹');
if(mode==='switch'&&p.field==='time_range')await new Promise(resolve=>{release=resolve});
if(failOnce&&p.field==='role_scope'){failOnce=false;throw Error('暂时失败')}
pending=pending.filter(c=>c.field!==p.field);sha='sha'+(2-pending.length);
return{status:'accepted',card_sha256:sha,evidence_id:'A',field:p.field}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
exports,console,Intl,Date,Set,Map,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}}:n==='@/lib/sidecar/api'?api:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<12;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const byTest=id=>nodes(tree).find(n=>n.props['data-testid']===id);
const accept=()=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()==='pages.evidence.reconcile.inference.accept');
(async()=>{
await settle();byTest('evidence-inference-run').props.onClick();await settle();
if(mode==='single'){accept().props.onClick();await settle();assert.equal(nodes(tree).filter(n=>n.props['data-testid']==='evidence-inference-candidate').length,1);accept().props.onClick()}
else byTest('evidence-inference-batch').props.onClick();
await settle();
if(mode==='switch'){
const other=()=>nodes(tree).find(n=>n.type==='tr'&&text(n).includes('其他项目'));
other().props.onClick();await settle();release();await settle();
assert.equal(other().props['aria-selected'],true,'完成批量确认不能拉回开始时选中的卡');
}
if(mode==='partial'){
assert.equal(nodes(tree).filter(n=>n.props['data-testid']==='evidence-inference-candidate').length,1,'失败后仅剩未完成项');
byTest('evidence-inference-batch').props.onClick();await settle();
assert.deepEqual(calls.map(x=>x.field),['time_range','role_scope','role_scope'],'不能重放已接受的时间字段');
}
assert.equal(pending.length,0);
assert.equal(nodes(tree).filter(n=>n.props['data-testid']==='evidence-inference-candidate').length,0);
assert.equal(inferenceCalls,1,'确认后刷新不能隐式重新推断');
const summary=nodes(tree).find(n=>n.type==='button'&&text(n).includes('pages.evidence.summary.inference'));
assert.ok(text(summary).includes('0'),'汇总计数同步归零');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(
        ["node", "-e", script, mode], cwd=Path(__file__).resolve().parents[3],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
