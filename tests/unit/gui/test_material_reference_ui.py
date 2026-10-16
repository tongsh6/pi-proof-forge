"""引用式材料 UI：证据页“引用外部目录”流与系统设置“材料来源”管理。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

REACT = r'''
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
'''


def _run(script: str) -> None:
    r = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


def test_evidence_page_reference_flow():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;''' + REACT + r'''
const scanCalls=[],createCalls=[],checkCalls=[];let loads=0;
const material=(id,label,extra)=>Object.assign({material_id:id,resource_id:'res_'+id,label,kind:'raw_work_material',filename:id+'.md',extension:'.md',uploaded_at:'',preview:'',size_bytes:1,source_mode:'',source_root:'',source_relpath:'',manifest_sha256:'',file_count:''},extra||{});
const api={listEvidence:async()=>({items:[]}),
 listEvidenceMaterialSources:async()=>{loads+=1;return{items:[material('m1','本地材料'),material('r1','引用·始祖鸟',{extension:'.txt',source_mode:'referenced',file_count:'5076',source_root:'/vault',source_relpath:'00-EC+'})]}},
 getSettings:async()=>({material_source_roots:[{id:'msr_1',label:'仓',path:'/vault'}]}),
 scanMaterialReference:async(root,rel)=>{scanCalls.push([root,rel]);return{root_id:root,relpath:rel,file_count:12,total_bytes:3456,sample_files:['a.md'],skipped:[],skipped_count:0,existing_materials:[]}},
 createMaterialReference:async(root,rel,label)=>{createCalls.push([root,rel,label]);return material('r2','引用·测试',{source_mode:'referenced'})},
 checkMaterialReference:async id=>{checkCalls.push([id]);return{material_id:id,status:'changed',changed:['a.md'],missing:[],added:['b.md'],manifest_sha256:'x',checked_at:''}},
 refreshMaterialReference:async()=>({manifest_sha256:'y',file_count:12}),removeMaterialReference:async()=>({removed:true})};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Set,Map,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}]}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:n==='./source-merge-panel'?{EvidenceSourceMerge:()=>null}:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const by=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();
const open=by('material-reference-open');assert.ok(open,'材料库应有引用入口');await open.props.onClick();await settle();
const rootSel=by('material-reference-root');assert.ok(rootSel,'应列出来源根下拉');assert.ok(text(rootSel).includes('仓'));
const rel=by('material-reference-relpath');rel.props.onChange({target:{value:'proj'}});await settle();
by('material-reference-scan').props.onClick();await settle();
assert.deepEqual(scanCalls[0],['msr_1','proj']);
assert.ok(by('material-reference-preview'),'扫描后显示预览');
const label=by('material-reference-label');label.props.onChange({target:{value:'引用·测试'}});await settle();
const loadsBefore=loads;by('material-reference-create').props.onClick();await settle();
assert.deepEqual(createCalls[0],['msr_1','proj','引用·测试']);
assert.ok(loads>loadsBefore,'创建后重载材料');
const list=by('material-reference-list');assert.ok(list&&text(list).includes('引用·始祖鸟'),'已引用列表包含引用材料');
by('material-reference-check').props.onClick();await settle();
assert.deepEqual(checkCalls[0],['r1']);
assert.ok(text(by('material-reference-list')).includes('pages.evidence.materialSources.referenceStatusChanged'),'状态检查结果内联显示');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    _run(script)


def test_settings_material_sources_section():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree;''' + REACT + r'''
const rootUpdates=[];
const api={getSettings:async()=>({gate_policy:{},exclusion_list:[],excluded_legal_entities:[],material_source_roots:[{id:'msr_1',label:'仓',path:'/vault'}],channels:[],liepin_api:{state:'unconfigured',configured:false,saved:false,storage_path:''},llm_config:{provider:'lm_studio',model:'m',base_url:'',api_key:{configured:false,updated_at:''},timeout:60,temperature:0.2}}),
 updateMaterialSourceRoots:async roots=>{rootUpdates.push(roots);return{section:'material_source_roots',saved:true}},
 checkLlmConnection:async()=>({}),openLiepinAuthorization:async()=>({}),updateLiepinCredential:async()=>({}),updateLlmConfig:async()=>({}),getLiepinResume:async()=>({})};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/system-settings/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,
{exports,console,Intl,Date,Set,Map,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k,i18n:{language:'zh'}})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}]}:n==='@/lib/sidecar/api'?api:{}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const by=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.SystemSettingsPage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();
const nav=nodes(tree).find(n=>n.type==='button'&&text(n).includes('pages.systemSettings.nav.materialSources'));
assert.ok(nav,'设置导航应有材料来源');nav.props.onClick();await settle();
assert.ok(by('settings-material-sources'),'材料来源区块渲染');
assert.ok(text(by('material-root-list')).includes('仓'),'列出已有来源根');
const path=by('material-root-path');path.props.onChange({target:{value:'/vault2'}});await settle();
by('material-root-add').props.onClick();await settle();
assert.deepEqual(JSON.parse(JSON.stringify(rootUpdates[0])),[{"id":"msr_1","label":"仓","path":"/vault"},{"id":"","label":"","path":"/vault2"}]);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    _run(script)
