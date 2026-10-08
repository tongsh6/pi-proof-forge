import subprocess
from pathlib import Path


def test_document_search_and_selection_keep_server_identity():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree,chosen,calls=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useRef(v){let i=cursor++;if(!hooks[i])hooks[i]={current:v};return hooks[i]},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const doc={document_id:'doc-hash',sha256:'sha',label:'项目/开发方案.md',char_count:20};const api={listMaterialDocuments:async(id,q)=>{calls.push(['list',id,q]);return{items:[doc],matched:1,total:2}},readMaterialDocument:async(id,key)=>{calls.push(['read',id,key]);return{...doc,text:'原文验证通过。'}}};
const exports={},jsx=(type,props)=>({type,props:props||{}});vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/material-document-picker.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='@/lib/sidecar/api'?api:n==='@/lib/errors'?{getErrorMessage:String}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);
async function settle(){for(let i=0;i<7;i++){cursor=0;tree=exports.MaterialDocumentPicker({materialId:'material',onSelect:d=>chosen=d,disabled:false});let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();assert.equal(chosen,null);by('document-query').props.onChange({target:{value:'开发方案'}});await settle();await by('document-search').props.onClick();await settle();assert.ok(calls.some(x=>x[2]==='开发方案'));
await by('document-select').props.onChange({target:{value:'doc-hash'}});await settle();assert.equal(chosen.document_id,'doc-hash');assert.equal(chosen.sha256,'sha');assert.equal(chosen.material_id,'material');assert.ok(by('document-preview').props.children.includes('原文验证通过。'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],text=True,capture_output=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
