import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario",["switch_cards","unchanged","added","removed","replaced","reordered","duplicate","scope_adopt","scope_revoke","scope_ordinary","multiline_fact"])
def test_rereview_submits_only_the_matching_card_and_actual_source_additions(scenario):
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
let hooks=[],cursor=0,effects=[],tree,resolveB;const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const oldRef=id=>({material_id:id,document_id:id+'-doc',sha256:id+'-sha',label:id});
const baseCard=id=>({evidence_id:id,title:id,time_range:'',role_scope:'',context:'context',actions:['action'],results:['result'],stack:[],tags:[],artifacts:[],source_sha256:id+'-card-sha',fact_scope_review:[{fact_id:id+':results:0',field:'results',index:0,value:'result',attribution:'self',target:'合成验证对象',environment:'test',implementation:'implemented',release:'not_released'}],source_material_ids:[id],source_documents:[oldRef(id)],field_sources:[{field:'results',value:'result',quote:'result',material_id:id,document_id:id+'-doc'}]});
const multilineResult='在隔离测试环境、固定数据集下，\nP95 从 200 ms 降至 120 ms；生产效果未知。';
const multilineAction='核对本次请求样本，\n记录测试条件与失败项。';
const card=id=>{
  const base=baseCard(id);
  if(process.argv[1]!=='multiline_fact')return base;
  return {...base,actions:[multilineAction,'补充故障排查记录'],results:[multilineResult,'已交付排障手册'],
    field_sources:[
      {field:'results',value:multilineResult,quote:multilineResult,material_id:id,document_id:id+'-doc'},
      {field:'results',value:'已交付排障手册',quote:'已交付排障手册',material_id:id,document_id:id+'-doc'}],
    fact_scope_review:[{...base.fact_scope_review[0],fact_id:id+':results:1',index:1,value:'已交付排障手册'}]};
};
const calls=[],api={listEvidence:async()=>({items:[{...card('A'),status:'needs_review',score:0,updated_at:''},{...card('B'),status:'needs_review',score:0,updated_at:''}]}),listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>id==='A'?{evidence:card('A')}:new Promise(r=>resolveB=r),saveEvidenceDraft:async p=>{calls.push(p);return{evidence_id:p.evidence_id}}};
const jsx=(type,props)=>typeof type==='function'?type(props||{}):({type,props:props||{}}),runtime={jsx,jsxs:jsx},exports={};
const baseRequire=n=>n==='react'?react:n==='react/jsx-runtime'?runtime:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}}:n==='@/lib/sidecar/api'?api:n==='./material-document-picker'?{MaterialDocumentPicker:()=>null}:undefined;
const nodePath=require('node:path'),moduleCache={};
function loadPageModule(spec,fromDir){const abs=spec.startsWith('@/')?nodePath.resolve('ui/src',spec.slice(2)):nodePath.resolve(fromDir,spec);let file=abs;for(const ext of['','.tsx','.ts','.js']){if(fs.existsSync(abs+ext)){file=abs+ext;break}}if(moduleCache[file])return moduleCache[file];const out={};moduleCache[file]=out;const dir=nodePath.dirname(file),code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText;vm.runInNewContext(code,{exports:out,console,Intl,Date,Map,Set,URLSearchParams,require:n=>resolvePageModule(n,dir)});return out}
function resolvePageModule(spec,fromDir){const pageRoot=nodePath.resolve('ui/src/pages/evidence'),abs=spec.startsWith('@/')?nodePath.resolve('ui/src',spec.slice(2)):nodePath.resolve(fromDir,spec),pageSpec='./'+nodePath.relative(pageRoot,abs).split(nodePath.sep).join('/'),stub=baseRequire(pageSpec);if(stub!==undefined)return stub;if(spec.startsWith('.')||spec.startsWith('@/pages/'))return loadPageModule(spec,fromDir);const hit=baseRequire(spec);if(hit!==undefined)return hit;throw Error(spec)}
let pageActions;
const pageRequire=n=>{
  const m=resolvePageModule(n,'ui/src/pages/evidence');
  return n==='./use-evidence-page'?{useEvidencePage:()=>{pageActions=m.useEvidencePage();return pageActions}}:m;
};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,Intl,Date,Set,Map,require:pageRequire});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<8;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
(async()=>{await settle();await button('materialDocument.reReview').props.onClick();await settle();const oldSave=button('pages.evidence.actions.saveEligible');
const scenario=process.argv[1];
if(scenario==='multiline_fact'){
  const factInputs=field=>nodes(tree).filter(n=>n.type==='textarea'&&n.props['data-field']===field);
  assert.equal(factInputs('results').length,2,'两条结果必须分别编辑，内部换行不能成为新事实');
  assert.equal(factInputs('results')[0].props.value,multilineResult);
  assert.equal(factInputs('results')[1].props.value,'已交付排障手册');
  assert.equal(factInputs('actions').length,2);
  assert.equal(factInputs('actions')[0].props.value,multilineAction);
  const scopeOptions=()=>{const select=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='factScope.fact');
    return nodes(select.props.children).filter(n=>n.type==='option'&&n.props.value).map(n=>JSON.parse(n.props.value));};
  const original=scopeOptions();
  assert.equal(original[0].index,0);assert.equal(original[0].value,multilineResult);
  assert.equal(original[1].index,1);assert.equal(original[1].value,'已交付排障手册');
  factInputs('results')[0].props.onChange({target:{value:multilineResult+'\n追加一行条件。'}});await settle();
  assert.equal(pageActions.form.results.length,2);
  assert.equal(pageActions.form.results[0],multilineResult+'\n追加一行条件。');
  assert.equal(pageActions.form.results[1],'已交付排障手册');
  assert.equal(scopeOptions().length,1,'被改写的事实不能沿用旧引用确认');
  assert.equal(scopeOptions()[0].index,1,'兄弟事实位置不得随内部换行漂移');
  factInputs('results')[0].props.onChange({target:{value:multilineResult}});await settle();
  nodes(tree).find(n=>n.props['data-testid']==='evidence-add-results').props.onClick();await settle();
  assert.equal(factInputs('results').length,3);
  assert.equal(pageActions.form.results[2],'');
  factInputs('results')[2].props.onChange({target:{value:'另一条完整成果，\n保留本条限定。'}});await settle();
  assert.equal(pageActions.form.results[2],'另一条完整成果，\n保留本条限定。');
  nodes(tree).find(n=>n.props['data-testid']==='evidence-remove-results-2').props.onClick();await settle();
  assert.equal(factInputs('results').length,2);
  await button('pages.evidence.actions.saveEligible').props.onClick();await settle();
  assert.equal(calls.length,1);
  const request=calls[0];
  assert.equal(JSON.stringify(request.draft.results),JSON.stringify([multilineResult,'已交付排障手册']));
  assert.equal(JSON.stringify(request.draft.actions),JSON.stringify([multilineAction,'补充故障排查记录']));
  assert.equal(request.draft.field_sources[0].value,multilineResult);
  assert.equal(request.draft.field_sources[0].quote,multilineResult);
  assert.equal(request.draft.field_sources[1].value,'已交付排障手册');
  assert.equal(request.expected_sha256,'A-card-sha');
  assert.equal(Object.hasOwn(request.review,'fact_scope'),false);
  return;
}
if(scenario.startsWith('scope_')){
  const quote='原文 result，\n仍限测试环境。';
  const initial=pageActions.generatedDraft;
  pageActions.handleMergeChange({...initial,field_sources:initial.field_sources.map((binding,index)=>index===0?{...binding,quote}:binding)});
  await settle();
  const fact=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='factScope.fact');
  const option=nodes(fact.props.children).find(n=>n.type==='option'&&n.props.value);
  fact.props.onChange({target:{value:option.props.value}});await settle();
  for(const [label,value] of [['factScope.attribution','self'],['factScope.target','合成验证对象'],['factScope.env','test'],['factScope.implementation','implemented'],['factScope.release','not_released']]){
    nodes(tree).find(n=>n.props['aria-label']===label).props.onChange({target:{value}});
    await settle();
  }
  const action=scenario==='scope_ordinary'?'pages.evidence.actions.saveEligible':scenario==='scope_adopt'?'factScope.adopt':'factScope.revoke';
  assert.equal(button(action).props.disabled,false);
  await button(action).props.onClick();await settle();
  assert.equal(calls.length,1);
  const request=calls[0];
  assert.equal(request.evidence_id,'A');
  assert.equal(request.expected_sha256,'A-card-sha');
  assert.equal(request.review.merge_sources,false);
  assert.equal(request.draft.field_sources[0].quote,quote);
  assert.equal(JSON.stringify(request.draft.source_documents),JSON.stringify([oldRef('A')]));
  assert.equal(JSON.stringify(request.draft.actions),JSON.stringify(['action']));
  assert.equal(JSON.stringify(request.draft.results),JSON.stringify(['result']));
  if(scenario==='scope_ordinary'){
    assert.equal(Object.hasOwn(request.review,'fact_scope'),false,'普通保存不得隐式采纳当前选择');
  }else{
    assert.ok(request.review.fact_scope,'实际页面丢弃了显式范围指令');
    const scope=request.review.fact_scope;
    assert.equal(scope.kind,scenario==='scope_adopt'?'adopt':'revoke');
    assert.equal(scope.field,'results');assert.equal(scope.index,0);assert.equal(scope.value,'result');
    if(scope.kind==='adopt'){
      assert.equal(scope.source.quote,request.draft.field_sources[0].quote);
      assert.equal(scope.source.sha256,request.draft.source_documents[0].sha256);
      assert.equal(scope.source.document_id,'A-doc');
      assert.equal(scope.source.material_id,'A');
      assert.equal(scope.attribution,'self');assert.equal(scope.target,'合成验证对象');
      assert.equal(scope.environment,'test');assert.equal(scope.implementation,'implemented');
      assert.equal(scope.release,'not_released');
    }else{
      assert.equal(JSON.stringify(scope),JSON.stringify({kind:'revoke',field:'results',index:0,value:'result'}));
    }
  }
  return;
}

if(scenario!=='switch_cards'){
  const initial=pageActions.generatedDraft;
  if(scenario==='added'){
    const {adoptSource}=loadPageModule('./source-merge','ui/src/pages/evidence');
    pageActions.handleMergeChange(adoptSource(initial,'results','more',oldRef('N')));
  }else if(scenario==='removed'){
    pageActions.handleMergeChange({...initial,source_documents:[]});
  }else if(scenario==='replaced'){
    pageActions.handleMergeChange({...initial,source_documents:[{...oldRef('A'),sha256:'replacement'}]});
  }else if(scenario==='reordered'){
    pageActions.handleMergeChange({...initial,source_material_ids:['N','A'],source_documents:[oldRef('N'),oldRef('A')]});
  }else if(scenario==='duplicate'){
    pageActions.handleMergeChange({...initial,source_documents:[oldRef('A'),oldRef('A')]});
  }
  await settle();
  await button('pages.evidence.actions.saveEligible').props.onClick();
  if(['removed','replaced','reordered','duplicate'].includes(scenario)){
    assert.equal(calls.length,0,'旧引用不能移除或替换');
  }else{
    assert.equal(calls.length,1);
    const [request]=calls;
    assert.equal(request.expected_sha256,'A-card-sha');
    assert.equal(request.review.merge_sources,scenario==='added');
    assert.deepEqual(Array.from(request.draft.source_material_ids),scenario==='added'?['A','N']:['A']);
  }
  return;
}
const row=nodes(tree).find(n=>n.type==='tr'&&n.props.onClick&&text(n).trim().startsWith('B'));row.props.onClick();await settle();
const header=nodes(tree).find(n=>n.type==='button'&&n.props.title==='pages.evidence.actions.save');assert.ok(!header||header.props.disabled===true,'B加载中仍可保存A草稿');assert.equal(button('pages.evidence.actions.saveEligible'),undefined);
resolveB({evidence:card('B')});await settle();assert.equal(button('pages.evidence.actions.saveEligible'),undefined);assert.equal(calls.length,0);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script,scenario],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
