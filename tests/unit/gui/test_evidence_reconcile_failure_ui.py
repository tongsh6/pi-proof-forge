"""证据页自动对账失败只请求一次（不进入重试循环）；列表被 100 条上限截断时明示。"""
import subprocess
from pathlib import Path

HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=id=>({evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',status:'saved_eligible',candidate_pool_eligible:true,score:80,updated_at:'',time_range_level:'L1',role_scope_level:'L1',source_document_count:1});
const jsx=(type,props)=>({type,props:props||{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
function load(api){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,document:{querySelector:()=>null},require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});return exports}
async function settle(page){for(let i=0;i<12;i++){cursor=0;tree=page();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const tid=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
'''


def _run(script: str) -> None:
    r = subprocess.run(['node', '-e', HARNESS + script], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


def test_auto_reconcile_failure_requests_once_and_manual_retry_works():
    _run(r'''
let reconcileCalls=0,fail=true;
const api={listEvidence:async()=>({items:[card('A')],next_cursor:null}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async()=>{throw Error('unused')},
reconcileEvidence:async()=>{reconcileCalls++;if(fail)throw Error('sidecar down');return{summary:{total:1,eligible:1,incomplete:0,legacy:0,untraceable_cards:0,missing_time_range:0,missing_role_scope:0,duplicate_cards:0,triaged_out:0,needs_fill:0,untriaged:1},items:[]}}};
const {EvidencePage}=load(api);
(async()=>{await settle(EvidencePage);await settle(EvidencePage);
assert.equal(reconcileCalls,1,'自动对账失败后不得自动重试');
assert.ok(text(tid('evidence-summary-hint')).includes('sidecar down'),'汇总条提示对账错误');
fail=false;tid('evidence-reconcile-run').props.onClick();await settle(EvidencePage);
assert.equal(reconcileCalls,2,'手动“重新对账”仍可触发');
assert.ok(!text(tid('evidence-summary-hint')).includes('sidecar down'),'成功后清除错误提示');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_truncated_list_shows_notice():
    _run(r'''
const api={listEvidence:async()=>({items:[card('A'),card('B')],next_cursor:'2'}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async()=>{throw Error('unused')},
reconcileEvidence:async()=>({summary:{total:150,eligible:150,incomplete:0,legacy:0,untraceable_cards:0,missing_time_range:0,missing_role_scope:0,duplicate_cards:0,triaged_out:0,needs_fill:0,untriaged:0},items:[]})};
const {EvidencePage}=load(api);
(async()=>{await settle(EvidencePage);
const note=tid('evidence-list-truncated');assert.ok(note,'有下一页游标时应提示列表被截断');
assert.ok(text(note).includes('pages.evidence.listTruncated'),'使用 listTruncated 文案');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_full_list_has_no_truncation_notice():
    _run(r'''
const api={listEvidence:async()=>({items:[card('A')],next_cursor:null}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async()=>{throw Error('unused')},
reconcileEvidence:async()=>({summary:{total:1,eligible:1,incomplete:0,legacy:0,untraceable_cards:0,missing_time_range:0,missing_role_scope:0,duplicate_cards:0,triaged_out:0,needs_fill:0,untriaged:0},items:[]})};
const {EvidencePage}=load(api);
(async()=>{await settle(EvidencePage);assert.equal(tid('evidence-list-truncated'),undefined,'未截断时不显示提示');})().catch(e=>{console.error(e);process.exitCode=1});
''')

