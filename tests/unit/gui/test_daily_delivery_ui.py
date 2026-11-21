"""实际执行每日授权组件的事件，不把测试组件当作原生验收。"""
import subprocess
from pathlib import Path


def test_daily_draft_requires_saved_scope_and_explicit_confirmation():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
let cursor=0,hooks=[],effects=[],tree,calls=[],navigations=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useRef(v){let i=cursor++;if(!hooks[i])hooks[i]={current:v};return hooks[i]},useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){if(hooks[i]?.cleanup)hooks[i].cleanup();hooks[i]={deps};effects.push(()=>{hooks[i].cleanup=fn()})}},useCallback(f){return f}};
const item={run_id:'r1',company:'公司',position:'职位',pdf_sha256:'a'.repeat(64),pdf_path:'/safe/resume.pdf'};
let state={authorization:null,today:{day:'2026-10-05',confirmed:0,occupied:0},history:[],candidates:[item]};
const persistedRows=[{job_profile_id:'jp_low',company:'不凑数',title:'无关岗位',reason:'fit_not_promising'},{job_profile_id:'jp_saved',company:'已保存准备',title:'平台负责人',reason:'preparation_saved_unapproved',preparation:{state:'fresh',reason:'inputs_unchanged',scope:'input_consistency_only',direction:{status:'needs_review',reason:'已保存的方向依据',jd_quote:'JD原文'},requirements_grounded:true,requirement_count:3,semantic_matching:{status:'partial',code:'semantic_no_relevant_evidence',scope:'advisory_partial',input_fresh:true,coverage_known:false,eligible_card_count:114,send_ready:false},evidence_precheck:{source:'rule',state:'caution',coverage:0.4,matched_requirements:2,total_requirements:5,evidence_hits:4,source_freshness_unverified_count:112},send_ready:false}},{job_profile_id:'jp_stale',company:'过期资料',title:'旧岗位',reason:'preparation_stale',preparation:{state:'stale',reason:'profile_changed',scope:'input_consistency_only',direction:{status:'aligned',reason:'STALE_ADVICE'},requirements_grounded:true,requirement_count:3,send_ready:false}}];
const api={getDailyPreparation:async maximum=>({maximum,selected:[{job_profile_id:'jp_auto',company:'自动准备公司',title:'Java',channel:'generated_pdf',reason:'semantic_review_required'}],deferred:persistedRows,shortfall:maximum-1,send_ready:false}),getDailyStatus:async()=>state,saveDailyDraft:async p=>{calls.push(['save',p]);state={...state,authorization:{...p,id:'auth',state:'draft',scope:p.run_ids.map(()=>item)}};return state},changeDailyAuthorization:async(id,status,confirmed)=>{calls.push([status,confirmed]);state={...state,authorization:{...state.authorization,state:status}};return state},runDailyDelivery:async()=>{calls.push(['run']);return state},closeInterruptedDaily:async()=>state};
let previewCalls=[];const previewReply=(id,markdown)=>({status:markdown?'preview':'blocked',code:markdown?'preview_partial_ready':'no_presentable_supported_work',job_profile_id:id,scope:'internal_targeted_excerpt',input_fresh:true,markdown,claims:[],limitations:[],preview_fact_count:markdown?1:0,partial:true,model_calls:0,active_target_eligible:false,deliverable:false,send_ready:false});
api.previewDailyPreparation=async id=>{previewCalls.push(id);return previewReply(id,id==='b'?'有据的内部片段':'')};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/agent-run/daily-delivery.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,Date,Set,console,window:{setInterval:()=>1,clearInterval:()=>{}},require:n=>n==='react-router-dom'?{useNavigate:()=>url=>navigations.push(url)}:n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='@/lib/sidecar/api'?api:n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})}:n==='@tauri-apps/api/core'?{convertFileSrc:x=>x}:{} });
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);async function settle(){for(let i=0;i<7;i++){cursor=0;tree=exports.DailyDeliveryPanel();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();assert.ok(by('daily-panel'));
assert.ok(by('daily-preparation-plan'),'每日面板应展示应用准备判断');
assert.ok(by('daily-saved-preparation-jp_saved'),'重新加载仍显示已保存准备状态');assert.ok(by('daily-semantic-saved-jp_saved'),'保存的语义状态可重载');assert.ok(text(by('daily-semantic-saved-jp_saved')).includes('daily.preparation.semanticCoverageUnknown'));assert.ok(!text(by('daily-semantic-saved-jp_saved')).includes('daily.preparation.semanticCoverage '));assert.ok(text(by('daily-saved-preparation-jp_saved')).includes('已保存的方向依据'));assert.ok(text(by('daily-saved-preparation-jp_saved')).includes('daily.preparation.evidenceOverlap'));assert.ok(text(by('daily-saved-preparation-jp_saved')).includes('daily.preparation.precheckStates.caution'));assert.ok(text(by('daily-saved-preparation-jp_saved')).includes('daily.preparation.legacySources'));assert.ok(text(by('daily-saved-preparation-jp_saved')).includes('daily.preparation.savedInputOnly'));assert.ok(text(by('daily-semantic-saved-jp_saved')).includes('daily.preparation.semanticOutcome.notRecorded'));assert.ok(!by('daily-semantic-outcome-saved-jp_saved'));assert.ok(by('daily-saved-preparation-jp_stale'));assert.ok(!text(tree).includes('STALE_ADVICE'),'过期建议不当作当前结果展示');assert.equal(calls.length,0,'读取保存结果不得调模型或发送');
assert.deepEqual(previewCalls,[],'加载不自动重看历史预览');let releasePreview;api.previewDailyPreparation=async id=>{previewCalls.push(id);return new Promise(r=>releasePreview=r)};const saved=by('daily-preview-open-jp_saved');assert.ok(saved);saved.props.onClick();saved.props.onClick();await settle();assert.deepEqual(previewCalls,['jp_saved'],'同岗请求不重入');releasePreview(previewReply('other','CROSS_JOB'));await settle();assert.ok(!text(tree).includes('CROSS_JOB'));assert.ok(!by('daily-preview-markdown-jp_saved'));assert.ok(!by('daily-preview-open-jp_stale'));api.previewDailyPreparation=async id=>{previewCalls.push(id);return previewReply(id,id==='b'?'有据的内部片段':'')};previewCalls=[];
assert.ok(text(tree).includes('自动准备公司'));assert.ok(text(tree).includes('daily.preparation.limitation'));
assert.ok(by('daily-preparation-jp_auto'));by('daily-preparation-jp_auto').props.onClick();assert.equal(navigations.at(-1),'/quick-run?job_profile_id=jp_auto');assert.equal(calls.length,0,'准备候选导航不触发保存/授权/发送');

assert.equal(calls.length,0,'加载不得自动补来源');
let releaseRefill,refillCalls=0,planCalls=0;const oldPlan=api.getDailyPreparation;api.getDailyPreparation=async m=>{planCalls++;return oldPlan(m)};
api.replenishDailyPreparation=async maximum=>{refillCalls++;assert.equal(maximum,3);return new Promise(r=>releaseRefill=r)};
const refill=by('daily-replenish');assert.ok(refill,'缺口卡应有来源补充入口');refill.props.onClick();refill.props.onClick();await settle();assert.equal(refillCalls,1,'同渲染连续点击不得重入');assert.equal(by('daily-replenish').props.disabled,true);
let assessmentCalls=[];api.assessDailyPreparation=async id=>{assessmentCalls.push(id);return {status:'blocked',code:'fixture_blocked',job_profile_id:id,direction:null,requirements_grounded:false,requirement_count:0,model_calls:0,active_target_eligible:false,send_ready:false}};
releaseRefill({status:'partial',code:'partial',maximum:3,shortfall:2,queries:['Python'],received_count:4,imported_count:2,source_prepared_count:1,source_prepared:[{job_lead_id:'jl1',job_profile_id:'jp1',company:'来源公司',title:'Java'}],deferred:[{job_lead_id:'jl2',reason:'existing_profile'}],errors:[{stage:'detail',code:'detail_failed'},{stage:'detail',job_lead_id:'jl_unverified',code:'JOB_DETAIL_UNAVAILABLE',detail_reason:'no_verified_detail'}],send_ready:false});await settle();
assert.equal(by('daily-replenish').props.disabled,false);assert.ok(by('daily-replenish-result'));assert.ok(text(tree).includes('来源公司'));assert.ok(text(tree).includes('detail_failed'));assert.ok(text(tree).includes('pages.jobs.liepinDetail.reasons.no_verified_detail'));assert.ok(text(tree).includes('jl_unverified'));assert.ok(text(tree).includes('existing_profile'));assert.ok(text(tree).includes('daily.preparation.refillLimitation'));assert.ok(planCalls>0,'完成应刷新计划');assert.equal(calls.length,0,'来源补充不得保存授权或发送');
assert.deepEqual(assessmentCalls,['jp1'],'补来源后应用自动核对新画像');assert.ok(text(tree).includes('fixture_blocked'));assert.ok(text(tree).includes('daily.preparation.unapproved'));
api.replenishDailyPreparation=async()=>{throw Error('source service unavailable')};by('daily-replenish').props.onClick();await settle();assert.ok(text(tree).includes('source service unavailable'));assert.ok(!by('daily-replenish-result'),'重试失败不可保留旧成功结果');assert.equal(by('daily-replenish').props.disabled,false);

api.replenishDailyPreparation=async()=>new Promise(r=>releaseRefill=r);by('daily-replenish').props.onClick();await settle();
const maxSelect=()=>nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='daily.maximum');assert.equal(maxSelect().props.disabled,true);
maxSelect().props.onChange({target:{value:'2'}});await settle();releaseRefill({status:'completed',code:'ok',maximum:3,shortfall:2,queries:[],received_count:1,imported_count:1,source_prepared_count:1,source_prepared:[{job_lead_id:'stale',job_profile_id:'stale',company:'STALE_RESULT',title:'role'}],deferred:[],errors:[],send_ready:false});await settle();assert.ok(!text(tree).includes('STALE_RESULT'),'目标改变后不得展示旧结果');assert.equal(by('daily-replenish').props.disabled,false,'过期完成也须释放本组件忙状态');maxSelect().props.onChange({target:{value:'3'}});await settle();


const assessmentSource=id=>({job_lead_id:id,job_profile_id:id,company:'Company '+id,title:'Role '+id});
api.replenishDailyPreparation=async()=>({status:'completed',code:'OK',maximum:3,shortfall:3,queries:[],received_count:4,imported_count:4,source_prepared_count:4,source_prepared:['a','b','b','c','d'].map(assessmentSource),deferred:[],errors:[],send_ready:false});
let matchCalls=[];api.matchDailyPreparation=async id=>{matchCalls.push(id);return {status:'partial',code:'advisory_only',scope:'advisory_partial',input_fresh:true,continuation_needed:false,match_outcome:{engine:'returned',reason:null,stop_causes:[],completed_check_count:1,usable_current_result:true},assessments:[{requirement_id:'r1',requirement_text:'真实要求',status:'partial',reason:'仍缺生产规模依据',citations:[{fact_id:'card:actions:0',text:'原始行动事实',candidate_support:true},{fact_id:'card:actions:1',quote:'同卡他人行动',candidate_support:false},{fact_id:'card:actions:2',text:'未标注引用'}]}],eligible_card_count:114,reviewed_card_count:8,degraded_card_count:4,degraded_check_count:2,deferred_card_count:102,deferred_check_count:3,assessment_schedule:{policy:'pending_source_requirements_v1',section_policy:'explicit_numbered_section_v1'},model_calls:4,send_ready:false}};
let releaseAssessment;assessmentCalls=[];api.assessDailyPreparation=async id=>{assessmentCalls.push(id);if(id==='a')return {status:'blocked',code:'first_blocked',direction:null,requirements_grounded:false,requirement_count:0};return new Promise(r=>releaseAssessment=r)};
by('daily-replenish').props.onClick();await settle();assert.deepEqual(assessmentCalls,['a','b'],'单项blocked不阻塞独立岗位');assert.ok(by('daily-assessing'));assert.ok(text(by('daily-assessing')).includes('Role b'));assert.equal(by('daily-replenish').props.disabled,true,'评估阶段锁仍有效');
releaseAssessment({status:'prepared',code:'OK',direction:{status:'aligned',reason:'test direction',jd_quote:'original JD'},requirements_grounded:true,requirement_count:2});await settle();assert.deepEqual(assessmentCalls,['a','b','c'],'唯一画像串行且最多3个');assert.deepEqual(matchCalls,['b'],'只有成功来源准备才自动进入语义匹配');assert.ok(text(by('daily-semantic-b')).includes('daily.preparation.semanticLimitation'));
const citationText='daily.preparation.semanticCandidateLimitation';
function checkCitations(audit) {
 const finding=nodes(audit).find(n=>n.type==='details'&&text(n).includes('真实要求'));
 assert.ok(finding);
 const refs=nodes(finding).filter(n=>n.type==='p'&&text(n).includes('card:actions:')).map(text);
 assert.equal(refs.length,3);
 assert.ok(refs[0].includes('原始行动事实')&&!refs[0].includes(citationText));
 assert.ok(refs[1].includes('同卡他人行动')&&refs[1].includes(citationText),'negative citation must be labeled as a limitation');
 assert.ok(refs[2].includes('未标注引用')&&!refs[2].includes(citationText));
 assert.ok(text(finding).includes('daily.preparation.supportStates.partial'));
}
checkCitations(by('daily-semantic-b'));
assert.ok(text(by('daily-semantic-b')).includes('daily.preparation.semanticDeferred'),'预算暂缓单列，不作为服务失败或能力不足');assert.ok(text(by('daily-semantic-b')).includes('daily.preparation.semanticSchedule'));assert.ok(text(by('daily-semantic-b')).includes('daily.preparation.semanticSectionSchedule'));assert.ok(text(by('daily-semantic-b')).includes('真实要求'));assert.ok(text(by('daily-semantic-b')).includes('原始行动事实'));assert.equal(calls.length,0,'语义匹配不得授权或发送');assert.ok(text(by('daily-assessment-b')).includes('daily.preparation.grounded'));assert.ok(text(by('daily-assessment-b')).includes('daily.preparation.directions.aligned'));
assert.deepEqual(previewCalls,['b'],'末轮后自动读取一次同岗预览');assert.ok(text(by('daily-preview-markdown-b')).includes('有据的内部片段'));
maxSelect().props.onChange({target:{value:'2'}});await settle();releaseAssessment({status:'prepared',code:'STALE_ASSESSMENT',direction:null,requirements_grounded:true,requirement_count:1});await settle();assert.ok(!text(tree).includes('STALE_ASSESSMENT'));assert.deepEqual(assessmentCalls,['a','b','c']);assert.equal(by('daily-replenish').props.disabled,false);maxSelect().props.onChange({target:{value:'3'}});await settle();
assessmentCalls=[];api.assessDailyPreparation=async id=>{assessmentCalls.push(id);return new Promise(r=>releaseAssessment=r)};by('daily-replenish').props.onClick();await settle();assert.deepEqual(assessmentCalls,['a']);maxSelect().props.onChange({target:{value:'2'}});await settle();releaseAssessment({status:'blocked',code:'stale',direction:null,requirements_grounded:false,requirement_count:0});await settle();assert.deepEqual(assessmentCalls,['a'],'目标变化后不发送后续评估');maxSelect().props.onChange({target:{value:'3'}});await settle();


api.replenishDailyPreparation=async()=>({status:'completed',code:'OK',source_prepared:[assessmentSource('deferred')],source_prepared_count:1,received_count:1,deferred:[],errors:[]});api.assessDailyPreparation=async id=>({status:'deferred',code:'direction_excluded',job_profile_id:id,direction:{status:'excluded',reason:'direction mismatch',jd_quote:'original JD'},requirements_grounded:false,requirement_count:0});by('daily-replenish').props.onClick();await settle();assert.ok(text(by('daily-assessment-deferred')).includes('daily.preparation.assessmentStates.deferred'));assert.ok(text(by('daily-assessment-deferred')).includes('daily.preparation.groundingDeferred'));assert.ok(!text(by('daily-assessment-deferred')).includes('daily.preparation.notGrounded'));
assert.deepEqual(matchCalls,['b'],'deferred和过期准备不调用语义匹配');
api.replenishDailyPreparation=async()=>({status:'completed',code:'OK',source_prepared:[assessmentSource('resume-cache')],source_prepared_count:1,received_count:1,deferred:[],errors:[]});api.assessDailyPreparation=async()=>({status:'prepared',code:'OK',direction:null,requirements_grounded:true,requirement_count:2});matchCalls=[];api.matchDailyPreparation=async (id,start,contract,token)=>{const i=matchCalls.length;assert.equal(start,i===0);assert.equal(contract,undefined);assert.equal(token,i===0?undefined:String(i).repeat(64));matchCalls.push(id);return {status:'partial',code:'budget_exhausted',scope:'advisory_partial',input_fresh:true,continuation_needed:true,continuation_digest:String(i+1).repeat(64),reviewed_card_count:8,eligible_card_count:114,send_ready:false}};by('daily-replenish').props.onClick();await settle();assert.equal(matchCalls.length,3,'有界缓存续做至多三轮');assert.ok(text(by('daily-semantic-resume-cache')).includes('daily.preparation.semanticPending'));assert.equal(calls.length,0);
await settle();assert.deepEqual(previewCalls,['b','resume-cache'],'三轮缓存续做也仅触发一次预览');assert.ok(text(by('daily-preview-result-resume-cache')).includes('no_presentable_supported_work'));assert.ok(!by('daily-preview-markdown-resume-cache'),'缺证不能展示空壳简历');
api.previewDailyPreparation=async id=>({...previewReply(id,'UNSAFE_PREVIEW'),deliverable:true});by('daily-preview-open-jp_saved').props.onClick();await settle();assert.ok(!text(tree).includes('UNSAFE_PREVIEW'));assert.ok(text(by('daily-preview-result-jp_saved')).includes('preview_mismatch'));
api.previewDailyPreparation=async id=>new Promise(r=>releasePreview=r);by('daily-preview-open-jp_saved').props.onClick();await settle();maxSelect().props.onChange({target:{value:'2'}});await settle();releasePreview(previewReply('jp_saved','OBSOLETE_PREVIEW'));await settle();assert.ok(!text(tree).includes('OBSOLETE_PREVIEW'));maxSelect().props.onChange({target:{value:'3'}});await settle();

let releaseMatch;matchCalls=[];api.matchDailyPreparation=async id=>{matchCalls.push(id);return new Promise(r=>releaseMatch=r)};by('daily-replenish').props.onClick();await settle();assert.equal(matchCalls.length,1);assert.equal(by('daily-replenish').props.disabled,true);maxSelect().props.onChange({target:{value:'2'}});await settle();releaseMatch({status:'partial',code:'STALE_MATCH',input_fresh:true,continuation_needed:true});await settle();assert.equal(matchCalls.length,1,'目标变化后不得继续模型调用');assert.ok(!text(tree).includes('STALE_MATCH'));maxSelect().props.onChange({target:{value:'3'}});await settle();
api.matchDailyPreparation=async()=>{throw Error('semantic service unavailable')};by('daily-replenish').props.onClick();await settle();assert.ok(text(tree).includes('semantic service unavailable'));await settle();assert.equal(by('daily-replenish').props.disabled,false);assert.equal(calls.length,0);
const populated=state;state={...state,candidates:[]};await nodes(tree).find(n=>n.type==='button'&&text(n)==='daily.refresh').props.onClick();await settle();assert.ok(by('daily-open-jobs'),'空清单应提供既有Jobs入口');by('daily-open-jobs').props.onClick();assert.equal(navigations.at(-1),'/jobs');assert.equal(calls.length,0,'导航不得保存或启用');state=populated;await nodes(tree).find(n=>n.type==='button'&&text(n)==='daily.refresh').props.onClick();await settle();assert.equal(by('daily-activate').props.disabled,true);assert.ok(text(tree).includes('公司'));
by('daily-candidate-r1').props.onChange({target:{checked:true}});await settle();await by('daily-save').props.onClick();await settle();assert.equal(JSON.stringify(calls[0][1].run_ids),JSON.stringify(['r1']));assert.equal(by('daily-activate').props.disabled,true);
by('daily-consent').props.onChange({target:{checked:true}});await settle();assert.equal(by('daily-activate').props.disabled,false);await by('daily-activate').props.onClick();await settle();assert.deepEqual(calls[1],['active',true]);assert.equal(by('daily-save').props.disabled,true);
await by('daily-pause').props.onClick();await settle();assert.equal(state.authorization.state,'paused');assert.equal(by('daily-run').props.disabled,true);assert.equal(by('daily-consent').props.checked,false);
await by('daily-revoke').props.onClick();await settle();assert.equal(state.authorization.state,'revoked');assert.equal(by('daily-run').props.disabled,true);assert.equal(calls.filter(c=>c[0]==='run').length,0);
state={...state,authorization:{...state.authorization,state:'active',scope:[item]},history:[{id:'batch',day:'2026-10-05',state:'running',reason:'',maximum:3,confirmed:1,unresolved:1,items:[{run_id:'r1',quick_run_id:'qr_recover',company:'恢复样例',position:'岗位',phase:'uploading',recovery_required:false}]}]};
api.closeInterruptedDaily=async id=>{calls.push(['close',id]);state={...state,history:[{...state.history[0],state:'finished',reason:'daily_upload_unconfirmed',items:[{...state.history[0].items[0],phase:'upload_unconfirmed',recovery_required:true}]}]};return state};
await nodes(tree).find(n=>n.type==='button'&&text(n)==='daily.refresh').props.onClick();await settle();assert.ok(text(tree).includes('恢复样例'),'历史需要显示具体岗位');assert.ok(text(tree).includes('daily.phases.uploading'));
assert.ok(by('daily-close-interrupted'));await by('daily-close-interrupted').props.onClick();await settle();assert.ok(text(tree).includes('daily.phases.upload_unconfirmed'));assert.equal(by('daily-run').props.disabled,true,'未核验项不能再次运行');
assert.ok(by('daily-review-batch-r1'));by('daily-review-batch-r1').props.onClick();assert.equal(navigations.at(-1),'/submissions?quick_run_id=qr_recover');assert.equal(calls.filter(c=>c[0]==='run').length,0,'恢复入口只导航，不重新发送');
state={...state,authorization:{...state.authorization,scope:[{...item,run_id:'different'}]},recovery_required:true,recovery_items:[{run_id:'old',quick_run_id:'qr_old',company:'旧授权待核验',position:'岗位',phase:'upload_unconfirmed',recovery_required:true}],history:[]};await nodes(tree).find(n=>n.type==='button'&&text(n)==='daily.refresh').props.onClick();await settle();assert.equal(by('daily-run').props.disabled,true,'换清单不能绕过全局未核验上传');assert.ok(text(tree).includes('旧授权待核验'));assert.ok(by('daily-review-recovery-old'));by('daily-review-recovery-old').props.onClick();assert.equal(navigations.at(-1),'/submissions?quick_run_id=qr_old');



api.replenishDailyPreparation=async()=>({status:'completed',code:'OK',source_prepared:['unmount-a','unmount-b'].map(assessmentSource),source_prepared_count:2,received_count:2,deferred:[],errors:[]});assessmentCalls=[];api.assessDailyPreparation=async id=>{assessmentCalls.push(id);return new Promise(r=>releaseAssessment=r)};by('daily-replenish').props.onClick();await settle();assert.deepEqual(assessmentCalls,['unmount-a']);hooks.forEach(h=>h?.cleanup?.());releaseAssessment({status:'blocked',code:'stale_unmount',direction:null,requirements_grounded:false,requirement_count:0});await Promise.resolve();await Promise.resolve();assert.deepEqual(assessmentCalls,['unmount-a'],'卸载后不发后续调用，不声称取消已发请求');
hooks=[];await settle();
let navigationRefills=0; assessmentCalls=[]; matchCalls=[]; const authorizationCalls=calls.length;
api.replenishDailyPreparation=async()=>{navigationRefills++;return new Promise(r=>releaseRefill=r)};
by('daily-replenish').props.onClick();await settle();hooks.forEach(h=>h?.cleanup?.());
persistedRows.push({job_profile_id:'persisted-after-navigation',company:'新来源',title:'后端',reason:'profile_review_required',recovery_action:{kind:'resume_assessment'}});
persistedRows.push({job_profile_id:'untrusted-draft',company:'手工来源',title:'后端',reason:'profile_review_required'});
releaseRefill({status:'completed',code:'OK',source_prepared:[assessmentSource('persisted-after-navigation')],source_prepared_count:1,received_count:1,deferred:[],errors:[]});await Promise.resolve();await Promise.resolve();
hooks=[];await settle();
assert.deepEqual(assessmentCalls,[],'重新打开不自行调模型');
assert.ok(!by('daily-resume-assessment-untrusted-draft'),'不能根据通用 draft 状态恢复');
api.assessDailyPreparation=async (id,sourceOnly)=>{assert.equal(sourceOnly,true);assessmentCalls.push(id);return {status:'prepared',code:'OK',job_profile_id:id,requirements_grounded:true,direction:null,requirement_count:1,model_calls:0,active_target_eligible:false,send_ready:false}};
api.matchDailyPreparation=async (id,start,contract,token)=>{const i=matchCalls.length;assert.equal(start,i===0);assert.equal(contract,undefined);assert.equal(token,i===0?undefined:String(i).repeat(64));matchCalls.push(id);return {status:'partial',code:'budget_exhausted',scope:'advisory_partial',input_fresh:true,continuation_needed:i<2,continuation_digest:i<2?String(i+1).repeat(64):undefined,send_ready:false}};
const resume=by('daily-resume-assessment-persisted-after-navigation');assert.ok(resume);resume.props.onClick();resume.props.onClick();await settle();
assert.deepEqual(assessmentCalls,['persisted-after-navigation']);assert.deepEqual(matchCalls,Array(3).fill('persisted-after-navigation'));
assert.equal(navigationRefills,1,'恢复不重新搜索来源');assert.equal(calls.length,authorizationCalls,'不保存授权或发送');
assert.ok(by('daily-assessment-persisted-after-navigation'),'恢复结果可见');
// Assessment persisted while its effect was interrupted. Only actionable saved state opens matching.
const noAuditState={state:'fresh',requirements_grounded:true,semantic_matching:null,direction:{status:'aligned'}};
persistedRows.push({job_profile_id:'grounded',company:'已核来源',title:'后端',reason:'preparation_saved_unapproved',recovery_action:{kind:'start_matching'},preparation:noAuditState});
persistedRows.push({job_profile_id:'has-audit',company:'已保存分析',title:'后端',reason:'preparation_saved_unapproved',preparation:{...noAuditState,semantic_matching:{status:'partial',code:'semantic_provider_timeout',scope:'advisory_partial',input_fresh:true}}});
hooks.forEach(h=>h?.cleanup?.());hooks=[];assessmentCalls=[];matchCalls=[];await settle();
assert.deepEqual(matchCalls,[],'重新打开不自行启动匹配');
assert.ok(!by('daily-start-matching-has-audit'),'已有失败记录不能冒充尚无结果');
api.matchDailyPreparation=async (id,startOnly)=>{assert.equal(startOnly,true);matchCalls.push(id);return {status:'partial',code:'budget_exhausted',scope:'advisory_partial',input_fresh:true,continuation_needed:true,send_ready:false}};
const start=by('daily-start-matching-grounded');assert.ok(start);start.props.onClick();start.props.onClick();await settle();
assert.deepEqual(assessmentCalls,[],'只继续匹配，不重做来源核对');assert.deepEqual(matchCalls,['grounded'],'显式恢复只启动一次');
assert.equal(navigationRefills,1);assert.equal(calls.length,authorizationCalls);
const recheckToken='a'.repeat(64);
persistedRows.push({job_profile_id:'contract-stale',company:'规则变更',title:'后端',reason:'preparation_saved_unapproved',recovery_action:{kind:'recheck_matching',audit_digest:recheckToken},preparation:{...noAuditState,semantic_matching:{status:'stale',code:'semantic_inputs_changed',scope:'advisory_partial',input_fresh:false}}});
persistedRows.push({job_profile_id:'other-stale',company:'证据变更',title:'后端',reason:'preparation_saved_unapproved',preparation:{...noAuditState,semantic_matching:{status:'stale',code:'semantic_inputs_changed',scope:'advisory_partial',input_fresh:false}}});
persistedRows.push({job_profile_id:'invalid-action',company:'异常投影',title:'后端',reason:'preparation_saved_unapproved',recovery_action:{kind:'start_matching',audit_digest:recheckToken}});
hooks.forEach(h=>h?.cleanup?.());hooks=[];await settle();
assert.ok(!by('daily-start-matching-invalid-action'),'非重核动作不得携带摘要');
assert.equal(matchCalls.length,1,'刷新后不自动重核');assert.ok(!by('daily-recheck-matching-other-stale'));
api.matchDailyPreparation=async (id,startOnly,token)=>{assert.equal(startOnly,false);assert.equal(token,recheckToken);matchCalls.push(id);return {status:'blocked',code:'semantic_contract_recheck_retained',scope:'advisory_partial',input_fresh:false,send_ready:false}};
const recheck=by('daily-recheck-matching-contract-stale');assert.ok(recheck);recheck.props.onClick();recheck.props.onClick();await settle();
assert.deepEqual(matchCalls,['grounded','contract-stale']);assert.ok(text(by('daily-semantic-contract-stale')).includes('semantic_contract_recheck_retained'));
const oldRow=persistedRows.findIndex(r=>r.job_profile_id==='contract-stale');
persistedRows[oldRow]={...persistedRows[oldRow],recovery_action:{kind:'recheck_matching',audit_digest:'b'.repeat(64)}};
maxSelect().props.onChange({target:{value:'2'}});await settle();
recheck.props.onClick();await settle();assert.deepEqual(matchCalls,['grounded','contract-stale'],'已替换计划的旧摘要不可执行');
const currentRecheck=by('daily-recheck-matching-contract-stale');
persistedRows.push({...persistedRows[oldRow]});maxSelect().props.onChange({target:{value:'3'}});await settle();
currentRecheck.props.onClick();await settle();assert.deepEqual(matchCalls,['grounded','contract-stale'],'重复画像不可执行恢复');
persistedRows.pop();

assert.equal(navigationRefills,1);assert.deepEqual(assessmentCalls,[]);assert.equal(calls.length,authorizationCalls);

const continueToken='c'.repeat(64);
persistedRows.push({job_profile_id:'fresh-incomplete',company:'未完成',title:'岗位',reason:'preparation_saved_unapproved',recovery_action:{kind:'continue_matching',audit_digest:continueToken},preparation:{...noAuditState,semantic_matching:{status:'partial',input_fresh:true,continuation_needed:true}}});
persistedRows.push({job_profile_id:'bare-ui-boolean',company:'无摘要',title:'岗位',reason:'preparation_saved_unapproved',preparation:{...noAuditState,semantic_matching:{status:'partial',input_fresh:true,continuation_needed:true}}});
hooks.forEach(h=>h?.cleanup?.());hooks=[];matchCalls=[];await settle();
assert.deepEqual(matchCalls,[],'重启仅读取，不续做');assert.ok(!by('daily-continue-matching-bare-ui-boolean'));
const continueOld=by('daily-continue-matching-fresh-incomplete');assert.ok(continueOld);
const rowIndex=persistedRows.findIndex(r=>r.job_profile_id==='fresh-incomplete');
persistedRows[rowIndex]={...persistedRows[rowIndex],recovery_action:{kind:'continue_matching',audit_digest:'d'.repeat(64)}};
maxSelect().props.onChange({target:{value:'2'}});await settle();
continueOld.props.onClick();await settle();assert.equal(matchCalls.length,0,'刷新后的旧摘要不可执行');
api.matchDailyPreparation=async (id,start,contract,token)=>{
  assert.equal(start,false);assert.equal(contract,undefined);assert.equal(token,'d'.repeat(64));matchCalls.push(id);
  return {status:'partial',code:'budget_exhausted',scope:'advisory_partial',input_fresh:true,continuation_needed:true,continuation_digest:'e'.repeat(64),send_ready:false};
};
const continueCurrent=by('daily-continue-matching-fresh-incomplete');continueCurrent.props.onClick();continueCurrent.props.onClick();await settle();
assert.deepEqual(matchCalls,['fresh-incomplete'],'只执行一轮，不连跑或重复点击');
assert.deepEqual(assessmentCalls,[]);assert.equal(navigationRefills,1);assert.equal(calls.length,authorizationCalls);
matchCalls=['grounded','contract-stale'];

persistedRows.push({job_profile_id:'typed-outcome',company:'引擎结果',title:'后端',reason:'preparation_saved_unapproved',preparation:{...noAuditState,semantic_matching:{status:'partial',code:'semantic_budget_exhausted',scope:'advisory_partial',input_fresh:true,cache_progress_count:4,match_outcome:{engine:'failed',reason:'semantic_engine_unavailable',stop_causes:['budget'],completed_check_count:0,usable_current_result:false},send_ready:false}}});
hooks.forEach(h=>h?.cleanup?.());hooks=[];await settle();
const typed=text(by('daily-semantic-saved-typed-outcome'));
assert.ok(!typed.includes(citationText));
const savedFinding={requirement_id:'saved-r',requirement_text:'真实要求',status:'partial',reason:'保留范围冲突',citations:[{fact_id:'card:actions:0',text:'原始行动事实',candidate_support:true},{fact_id:'card:actions:1',quote:'同卡他人行动',candidate_support:false},{fact_id:'card:actions:2',text:'未标注引用'}]};
for(const [id,status,input_fresh] of [['saved-citations','partial',true],['stale-citations','stale',false],['invalid-citations','invalid',false]]) {
 persistedRows.push({job_profile_id:id,company:'合成',title:'后端',reason:'preparation_saved_unapproved',preparation:{...noAuditState,semantic_matching:{status,scope:'advisory_partial',input_fresh,assessments:[savedFinding],send_ready:false}}});
}
hooks.forEach(h=>h?.cleanup?.());hooks=[];await settle();
checkCitations(by('daily-semantic-saved-saved-citations'));
for(const id of ['stale-citations','invalid-citations']) assert.ok(!text(by('daily-semantic-saved-'+id)).includes('同卡他人行动'));

assert.ok(typed.includes('daily.preparation.semanticOutcome.noUsable'));
assert.ok(typed.includes('semantic_engine_unavailable'));assert.ok(typed.includes('semanticOutcome.stops.budget'));
assert.ok(typed.includes('semanticOutcome.checks'));assert.ok(typed.includes('semanticCacheProgress'));
assert.ok(!typed.includes('daily.preparation.semanticStates.partial'));
assert.deepEqual(matchCalls,['grounded','contract-stale'],'显示诊断不调用模型');
const noUsable={status:'partial',code:'semantic_budget_exhausted',scope:'advisory_partial',input_fresh:true,
 match_outcome:{engine:'failed',reason:'semantic_engine_unavailable',stop_causes:['budget'],completed_check_count:0,usable_current_result:false},send_ready:false};
assert.ok(by('daily-preview-open-jp_saved'),'缺历史诊断的保存记录仍可发起只读复验');
const savedUnavailableNoEntry=!by('daily-preview-open-typed-outcome');
persistedRows.push({job_profile_id:'zero-result-start',company:'来源已就绪',title:'后端',reason:'preparation_saved_unapproved',
  recovery_action:{kind:'start_matching'},preparation:{...noAuditState,semantic_matching:null}});
hooks.forEach(h=>h?.cleanup?.());hooks=[];await settle();
const beforeEmpty=previewCalls.length;
api.previewDailyPreparation=async id=>{previewCalls.push(id);return previewReply(id,'WRONG_WITHOUT_USABLE_RESULT');};
api.matchDailyPreparation=async id=>{assert.equal(id,'zero-result-start');return noUsable;};
by('daily-start-matching-zero-result-start').props.onClick();await settle();
assert.ok(text(by('daily-semantic-zero-result-start')).includes('daily.preparation.semanticOutcome.noUsable'));
assert.deepEqual([savedUnavailableNoEntry,previewCalls.length===beforeEmpty,!by('daily-preview-result-zero-result-start')],
 [true,true,true],'明确没有可用结果：刷新后无预览按钮、即时不发预览 RPC、不显示片段');


// An open excerpt is tied to the audit being read, not to every later audit for the same job.
const oldPreviewJob='fresh-incomplete', resolveRace=[];
api.previewDailyPreparation=async id=>id===oldPreviewJob
 ?new Promise(resolve=>resolveRace.push(resolve))
 :previewReply(id,'OTHER_JOB_STAYS');
by('daily-preview-open-jp_saved').props.onClick();
by('daily-preview-open-'+oldPreviewJob).props.onClick();
await settle();
assert.equal(resolveRace.length,1);
assert.ok(text(tree).includes('OTHER_JOB_STAYS'));
api.matchDailyPreparation=async (id,start,contract,token)=>{
 assert.equal(id,oldPreviewJob);assert.equal(start,false);assert.equal(contract,undefined);
 assert.equal(token,'d'.repeat(64));
 return {status:'partial',code:'new_audit_b',scope:'advisory_partial',input_fresh:true,
 match_outcome:{engine:'returned',reason:null,stop_causes:[],completed_check_count:1,usable_current_result:true},send_ready:false};
};
by('daily-continue-matching-'+oldPreviewJob).props.onClick();await settle();
assert.ok(text(by('daily-semantic-'+oldPreviewJob)).includes('new_audit_b'));
if(resolveRace.length===2)resolveRace[1](previewReply(oldPreviewJob,'CURRENT_AUDIT_B'));
await settle();
resolveRace[0](previewReply(oldPreviewJob,'LATE_OLD_A'));
await settle();
assert.deepEqual([resolveRace.length,text(tree).includes('CURRENT_AUDIT_B'),
 !text(tree).includes('LATE_OLD_A'),text(tree).includes('OTHER_JOB_STAYS')],[2,true,true,true],
 '同岗续做只显示新审计，不阻塞新读或接纳旧回复；其他岗位片段保留');

const refreshButton=()=>nodes(tree).find(node=>node.type==='button'&&text(node).trim()==='daily.preparation.refresh');
const oldLocalId='zero-result-start';
const localView=()=>by('daily-semantic-'+oldLocalId);
assert.ok(localView(),'另一岗位显式续做后的自动计划更新仍保留当前操作回包');
assert.ok(by('daily-semantic-'+oldPreviewJob),'自动刷新即刻保留刚才的新匹配结果');
const indexA=persistedRows.findIndex(row=>row.job_profile_id===oldLocalId);
const rowA=persistedRows[indexA];
const savedB={...noUsable,code:'fresh_saved_b',
 match_outcome:{engine:'returned',reason:null,stop_causes:[],completed_check_count:2,usable_current_result:true}};
persistedRows[indexA]={...rowA,recovery_action:null,
 preparation:{...rowA.preparation,semantic_matching:savedB}};
const getPlan=api.getDailyPreparation;
let releaseGuardedMatch,autoReads=0;
api.getDailyPreparation=maximum=>{autoReads++;return getPlan(maximum);};
api.matchDailyPreparation=async id=>{
 assert.equal(id,oldPreviewJob);
 return new Promise(resolve=>releaseGuardedMatch=resolve);
};
const refreshBeforeBusy=refreshButton();
by('daily-continue-matching-'+oldPreviewJob).props.onClick();
refreshBeforeBusy.props.onClick();await settle();
assert.equal(autoReads,0,'同一事件轮次的刷新不能令已启动的恢复失效');
assert.equal(refreshButton().props.disabled,true);
releaseGuardedMatch({status:'blocked',code:'STOPPED_IN_CONTROL',scope:'advisory_partial',input_fresh:false,send_ready:false});
await settle();
assert.equal(autoReads,1,'结束后正常自动读取');
assert.ok(localView(),'自动读取不清除独立的本地回包');
let answerPlan,rejectPlan,refreshMaximum,refreshCount=0;
api.getDailyPreparation=maximum=>{refreshCount++;refreshMaximum=maximum;
 return new Promise((resolve,reject)=>{answerPlan=resolve;rejectPlan=reject;});};
const beforeRefreshPrev=previewCalls.length,beforeRefreshMatch=matchCalls.length;
refreshButton().props.onClick();await settle();
const noShadowPending=!localView();
rejectPlan(Error('REFRESH_READ_FAILED'));await settle();
assert.ok(text(tree).includes('REFRESH_READ_FAILED'));
const noShadowFailed=!localView();
refreshButton().props.onClick();await settle();answerPlan(await getPlan(refreshMaximum));await settle();
const freshPlanShows=Boolean(by('daily-preview-open-'+oldLocalId))&&!localView()
  &&text(by('daily-semantic-saved-'+oldLocalId)).includes('fresh_saved_b');
assert.deepEqual([noShadowPending,noShadowFailed,freshPlanShows,refreshCount,
 previewCalls.length===beforeRefreshPrev,matchCalls.length===beforeRefreshMatch],[true,true,true,2,true,true],
 '重新判断只读：等待/失败不显示旧语义结果，成功可用的已存结果及其预览入口不被遮挡');
api.getDailyPreparation=getPlan;
api.previewDailyPreparation=async id=>({...previewReply(id,'MALFORMED_PREVIEW'),claims:null});by('daily-preview-open-jp_saved').props.onClick();await settle();assert.ok(!text(tree).includes('MALFORMED_PREVIEW'));
api.previewDailyPreparation=async id=>new Promise(r=>releasePreview=r);by('daily-preview-open-jp_saved').props.onClick();await settle();hooks.forEach(h=>h?.cleanup?.());const beforeUnmountReply=hooks.map(h=>h?.v);releasePreview(previewReply('jp_saved','LATE_AFTER_UNMOUNT'));await Promise.resolve();await Promise.resolve();assert.deepEqual(hooks.map(h=>h?.v),beforeUnmountReply,'组件卸载后不写入预览状态');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_daily_timer_does_not_overlap_and_recovers_after_failure():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/sidecar/daily-trigger.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports});
(async()=>{let release,calls=0;const tick=exports.createDailyTrigger(()=>{calls++;return new Promise(r=>release=r)});const pending=tick();await tick();assert.equal(calls,1);release({});await pending;const next=tick();assert.equal(calls,2);release({});await next;
let failed=0;const safe=exports.createDailyTrigger(async()=>{failed++;throw Error('busy')});await safe();await safe();assert.equal(failed,2);})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
