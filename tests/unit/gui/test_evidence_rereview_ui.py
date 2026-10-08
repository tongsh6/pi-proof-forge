import subprocess
from pathlib import Path


def test_switching_cards_during_rereview_cannot_save_old_draft_into_new_card():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree,resolveB;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=id=>({evidence_id:id,title:id,time_range:'',role_scope:'',context:'context',actions:'action',results:'result',stack:[],tags:[],artifacts:[],source_material_ids:[id],source_documents:[]});
const calls=[],api={listEvidence:async()=>({items:[{...card('A'),status:'needs_review',score:0,updated_at:''},{...card('B'),status:'needs_review',score:0,updated_at:''}]}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>id==='A'?{evidence:card('A')}:new Promise(r=>resolveB=r),saveEvidenceDraft:async p=>{calls.push(p);return{evidence_id:p.evidence_id}}};
const jsx=(type,props)=>({type,props:props||{}}),exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
(async()=>{await settle();await button('materialDocument.reReview').props.onClick();await settle();const oldSave=button('pages.evidence.actions.saveEligible');
const row=nodes(tree).find(n=>n.type==='tr'&&n.props.onClick&&text(n).trim().startsWith('B'));row.props.onClick();await settle();
const header=nodes(tree).find(n=>n.type==='button'&&n.props.title==='pages.evidence.actions.save');assert.equal(header.props.disabled,true,'B加载中仍可保存A草稿');assert.equal(button('pages.evidence.actions.saveEligible'),undefined);
resolveB({evidence:card('B')});await settle();assert.equal(button('pages.evidence.actions.saveEligible'),undefined);assert.equal(calls.length,0);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
