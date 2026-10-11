"""证据详情栏默认只读：已保存的卡显示文本与“编辑”按钮，点编辑才出现表单；新建草稿直接进入编辑态。"""
import subprocess
from pathlib import Path


def test_saved_card_is_read_only_until_edit_and_new_draft_edits_immediately():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card=id=>({evidence_id:id,title:'标题'+id,time_range:'2024-01 ~ 2024-06',role_scope:'负责人',context:'背景',actions:'行动',results:'成果',stack:['Java'],tags:['后端'],artifacts:[],source_material_ids:[id],source_documents:[]});
const api={listEvidence:async()=>({items:[{...card('A'),status:'saved_eligible',score:80,updated_at:''}]}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>({evidence:card(id)})};
const jsx=(type,props)=>({type,props:props||{}}),exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}]}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
const titleInput=()=>nodes(tree).find(n=>n.type==='input'&&n.props.placeholder==='pages.evidence.fields.title');
(async()=>{await settle();
assert.equal(titleInput(),undefined,'已保存的卡默认不应出现标题输入框');
assert.ok(text(tree).includes('标题A'),'只读态应显示标题文本');
assert.ok(text(tree).includes('成果'),'只读态应显示成果文本');
const edit=button('pages.evidence.actions.edit');assert.ok(edit,'只读态应有编辑按钮');
edit.props.onClick();await settle();
assert.ok(titleInput(),'点编辑后出现表单');assert.ok(button('pages.evidence.actions.cancelEdit'),'编辑态应有取消');
button('pages.evidence.actions.cancelEdit').props.onClick();await settle();
assert.equal(titleInput(),undefined,'取消后回到只读');
button('pages.evidence.actions.new').props.onClick();await settle();
assert.ok(titleInput(),'新建草稿直接进入编辑态');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
