import subprocess
from pathlib import Path


def test_text_material_manual_review_stays_bound_and_does_not_call_model():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const hooks=[];let index=0,effects=[],tree;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){const i=index++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const calls=[];const api={listEvidence:async()=>({items:[]}),listEvidenceMaterialSources:async()=>({items:[{material_id:'work',filename:'work.txt',label:'实际工作材料',extension:'.txt',preview:''}]}),
 generateEvidenceDraft:async()=>{throw Error('手工审核不可调用模型')},saveEvidenceDraft:async payload=>{calls.push(payload);return{evidence_id:'reviewed'}}};
const exports={};
const jsx=(type,props)=>typeof type==='function'?type(props||{}):({type,props:props||{}});
const runtime={jsx,jsxs:jsx};
const baseRequire=n=>{if(n==='react')return react;if(n==='react/jsx-runtime')return runtime;if(n==='react-i18next')return{useTranslation:()=>({t:k=>k})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return {notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};if(n==='react-router-dom')return {useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}};if(n==='./material-document-picker')return{MaterialDocumentPicker:()=>null};if(n==='./source-merge-panel')return{EvidenceSourceMerge:()=>null};return undefined};
const nodePath=require('node:path'),moduleCache={};
function loadPageModule(spec,fromDir){const abs=spec.startsWith('@/')?nodePath.resolve('ui/src',spec.slice(2)):nodePath.resolve(fromDir,spec);let file=abs;for(const ext of['','.tsx','.ts','.js']){if(fs.existsSync(abs+ext)){file=abs+ext;break}}if(moduleCache[file])return moduleCache[file];const out={};moduleCache[file]=out;const dir=nodePath.dirname(file),code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText;vm.runInNewContext(code,{exports:out,console,Intl,Date,Map,Set,URLSearchParams,require:n=>resolvePageModule(n,dir)});return out}
function resolvePageModule(spec,fromDir){const pageRoot=nodePath.resolve('ui/src/pages/evidence'),abs=spec.startsWith('@/')?nodePath.resolve('ui/src',spec.slice(2)):nodePath.resolve(fromDir,spec),pageSpec='./'+nodePath.relative(pageRoot,abs).split(nodePath.sep).join('/'),stub=baseRequire(pageSpec);if(stub!==undefined)return stub;if(spec.startsWith('.')||spec.startsWith('@/pages/'))return loadPageModule(spec,fromDir);const hit=baseRequire(spec);if(hit!==undefined)return hit;throw Error(spec)}
const pageRequire=n=>resolvePageModule(n,'ui/src/pages/evidence');
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Map,Set,require:pageRequire});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){index=0;tree=exports.EvidencePage();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
const field=label=>nodes(nodes(tree).find(n=>n.type==='label'&&text(n).includes(label))).find(n=>n.type==='input'||n.type==='textarea');
(async()=>{await settle();nodes(tree).find(n=>n.props&&n.props['data-testid']==='evidence-open-drawer').props.onClick();await settle();const option=nodes(tree).find(n=>n.type==='option'&&n.props.value==='work');assert.ok(!option.props.disabled,'真实 txt 材料应可选择');
const select=nodes(tree).find(n=>n.type==='select'&&nodes(n).includes(option));select.props.onChange({target:{value:'work'}});await settle();
assert.ok(button('pages.evidence.actions.generateDraft').props.disabled,'汇总 txt 不发送给模型');
await button('pages.evidence.actions.manualDraft').props.onClick();await settle();
assert.equal(field('pages.evidence.fields.results').props.value,'');
field('pages.evidence.fields.title').props.onChange({target:{value:'租赁设计'}});field('pages.evidence.fields.results').props.onChange({target:{value:'支持用户租赁登记与归还。'}});await settle();
await button('pages.evidence.actions.saveEligible').props.onClick();await settle();
assert.equal(calls[0].draft.source_material_ids[0],'work');assert.equal(calls[0].draft.artifacts[0].ref,'work');assert.equal(calls[0].draft.artifacts[0].type,'text_document');assert.equal(calls[0].draft.results,'支持用户租赁登记与归还。');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
