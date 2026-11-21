"""Review UI sends a scope only from the explicit single-fact operator."""
import subprocess
from pathlib import Path


def test_fact_scope_review_is_explicit_and_revoke_keeps_fact_identity():
    script = r'''
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), ts=require('./ui/node_modules/typescript');
let hooks=[], index=0, tree, calls=[];
const react={useState(init){const i=index++;if(!(i in hooks))hooks[i]=init;return [hooks[i],v=>{hooks[i]=v;}]}};
const jsx=(type,props)=>({type,props}), exports={};
const path='ui/src/pages/evidence/components/evidence-review-section.tsx';
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,
 {exports,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx,Fragment:'fragment'}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:{}});
const source={material_id:'mat',document_id:'a'.repeat(64),sha256:'b'.repeat(64),label:'Exact source'};
const draft={source_material_ids:['mat'],source_documents:[source],actions:'已做恢复处理',results:'',field_sources:[
 {field:'actions',value:'已做恢复处理',quote:'已做恢复处理，未发布到生产。',material_id:'mat',document_id:source.document_id}
]};
const base={generatedDraft:draft,reviewedScopes:[{fact_id:'ec:actions:0',field:'actions',index:0,value:draft.actions,attribution:'self',target:'后端处理',environment:'test',implementation:'implemented',release:'not_released'}],reviewMissingItems:[],busy:false,onSaveReviewedDraft:(...x)=>calls.push(x)};
function render(p){index=0;tree=exports.EvidenceReviewSection({...base,...p});}
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const label=k=>nodes(tree).find(n=>n.props['aria-label']===k), button=k=>nodes(tree).find(n=>n.type==='button'&&text(n)===k);
render();assert.ok(!label('factScope.fact'),'fresh import must not offer authority');
render({scopeDraft:draft});assert.equal(calls.length,0);
const selected=nodes(label('factScope.fact')).filter(x=>x.type==='option')[1].props.value;
const change=(key,value)=>{label(key).props.onChange({target:{value}});render({scopeDraft:draft});};
change('factScope.fact',selected);
assert.ok(button('factScope.adopt').props.disabled);
assert.ok(text(tree).includes('未发布到生产'));
assert.equal(label('factScope.attribution').props.value,'unknown');
assert.deepEqual(nodes(label('factScope.attribution')).filter(x=>x.type==='option').map(x=>x.props.value),['unknown','self','team_lead','contributor','teammate']);
change('factScope.attribution','team_lead');change('factScope.target','后端处理');
assert.ok(label('factScope.release').props.disabled,'release selector requires known environment');
change('factScope.implementation','implemented');change('factScope.release','released');
assert.ok(button('factScope.adopt').props.disabled,'release needs known environment');
change('factScope.env','test');change('factScope.implementation','planned');change('factScope.release','released');
assert.ok(button('factScope.adopt').props.disabled);
change('factScope.implementation','implemented');change('factScope.release','not_released');
button('pages.evidence.actions.saveEligible').props.onClick();assert.deepEqual(calls[0],['eligible']);
button('factScope.adopt').props.onClick();
assert.equal(calls[1][1].kind,'adopt');assert.equal(calls[1][1].attribution,'team_lead');assert.equal('subject' in calls[1][1],false);assert.equal(calls[1][1].value,draft.actions);
assert.equal(calls[1][1].source.sha256,source.sha256);assert.equal(calls[1][1].environment,'test');
button('factScope.revoke').props.onClick();
assert.equal(JSON.stringify(calls[2]),JSON.stringify(['eligible',{kind:'revoke',field:'actions',index:0,value:draft.actions}]));
hooks=[];render({scopeDraft:draft});assert.ok(!button('factScope.adopt'),'reopen must clear unsubmitted inputs');
'''
    result = subprocess.run(["node","-e",script], cwd=Path(__file__).resolve().parents[3],
                            capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr


def test_detail_panel_recovers_ambiguous_scope_without_trusting_other_source_errors():
    script = r'''
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), ts=require('./ui/node_modules/typescript');
let hooks=[], index=0, tree, panelTree, reviewProps, calls=[];
const react={useState(init){const i=index++;if(!(i in hooks))hooks[i]=init;return [hooks[i],v=>{hooks[i]=v;}]}};
const jsx=(type,props)=>({type,props});
function load(path,children={}){
 const exports={};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,
  {exports,require:n=>n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx,Fragment:'fragment'}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:children[n]??{}});
 return exports;
}
const review=load('ui/src/pages/evidence/components/evidence-review-section.tsx');
const panel=load('ui/src/pages/evidence/components/evidence-detail-panel.tsx',{'./evidence-review-section':review});
const source={material_id:'mat',document_id:'a'.repeat(64),sha256:'b'.repeat(64),label:'Exact source'};
const draft={source_material_ids:['mat'],source_documents:[source],actions:'已做恢复处理',results:'',field_sources:[
 {field:'actions',value:'已做恢复处理',quote:'已做恢复处理',material_id:'mat',document_id:source.document_id}
]};
const error='fact_scope_source_not_unique';
const base={detailState:'ready',form:{},editing:true,busy:false,generatedDraft:draft,reviewTargetId:'ec',reviewMissingItems:[],
 draftFromForm:d=>d,onSaveReviewedDraft:(...args)=>calls.push(args),materialSources:[]};
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const label=k=>nodes(tree).find(n=>n.props['aria-label']===k), button=k=>nodes(tree).find(n=>n.type==='button'&&text(n)===k);
function render(sourceError=error,props={}){
 index=0;
 panelTree=panel.EvidenceDetailPanel({...base,detail:{evidence_id:'ec',source_material_ids:['mat'],source_error:sourceError,fact_scope_review:[]},...props});
 reviewProps=nodes(panelTree).find(n=>n.type===review.EvidenceReviewSection).props;
 tree=review.EvidenceReviewSection(reviewProps);
}
function choose(){const value=nodes(label('factScope.fact')).filter(n=>n.type==='option')[1].props.value;label('factScope.fact').props.onChange({target:{value}});}
render();
assert.equal(reviewProps.scopeDraft,draft,'ambiguous quote must leave the existing fact review reachable');
assert.equal(reviewProps.sourceError,error);
assert.ok(text(panelTree).includes('factScope.sourceNotUnique'));
assert.deepEqual(reviewProps.reviewedScopes,[],'recovery does not manufacture a verified scope');
assert.equal(calls.length,0);
choose();render();
assert.ok(button('factScope.adopt').props.disabled,'ambiguity does not prefill an accepted scope');
assert.equal(button('factScope.revoke').props.disabled,false);
button('factScope.revoke').props.onClick();
assert.equal(JSON.stringify(calls),JSON.stringify([['eligible',{kind:'revoke',field:'actions',index:0,value:draft.actions}]]));
render(error,{busy:true});assert.ok(button('factScope.revoke').props.disabled);
button('factScope.revoke').props.onClick();assert.equal(calls.length,1,'busy recovery cannot submit');
hooks=[];render('');choose();render('');
assert.ok(!button('factScope.revoke'),'ordinary unscoped facts must not offer revoke');
for(const sourceError of ['material_source_changed','material_source_missing','fact_scope_source_mismatch']){
 hooks=[];render(sourceError);
 assert.equal(reviewProps.scopeDraft,undefined,sourceError);
 assert.ok(!label('factScope.fact'),sourceError);
 assert.ok(!button('factScope.revoke'),sourceError);
}
for(const reviewTargetId of [undefined,'other']){
 hooks=[];render(error,{reviewTargetId});
 assert.equal(reviewProps.scopeDraft,undefined,'recovery must stay bound to the selected existing card');
 assert.ok(!label('factScope.fact'));
}
'''
    result = subprocess.run(["node", "-e", script], cwd=Path(__file__).resolve().parents[3],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
