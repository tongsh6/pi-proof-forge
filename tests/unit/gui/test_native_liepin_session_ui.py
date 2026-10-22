"""执行原生登录入口与 PDF 投递组件事件；不是网站登录成功的证明。"""
import subprocess
from pathlib import Path


def test_native_login_entry_only_opens_and_checks_session():
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ts=require('./ui/node_modules/typescript');const hooks=[];let cursor=0,effects=[],tree;
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useRef(v){return react.useMemo(()=>({current:v}),[])},useState(v){const i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},
useEffect(fn,deps){const i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let params=new URLSearchParams({quick_run_id:'qr_linked'});const navigations=[];let nativeStatus='waiting_for_login'; const calls=[];let confirmAnswer=true;
const base={company:'公司',position:'岗位',pdf_sha256:'hash'};
const api={listSubmissions:async()=>({items:[]}),listResumes:async()=>({items:[]}),getChannelSession:async()=>({session:{login_status:'login_required',account_identity:{}},artifact_paths:{}}),
openLiepinNativeSession:async()=>{calls.push('open');return{status:'opened'}},checkLiepinNativeSession:async()=>{calls.push('check');return{status:nativeStatus}}};
api.inspectLiepinNativeAttachments=async()=>{calls.push('inspect');return{status:'authenticated',attachment_view:{inputs:[{accept:'.pdf'}],hints:['支持 PDF']}}};
api.syncLiepinFeedback=async()=>{calls.push('sync-feedback');return{status:'records',page_url:'https://c.liepin.com/x',matched:[{submission_id:'s1',normalized_status:'viewed',status_label:'已查看',match_basis:'job_id'}],unmatched_rows:0,submissions_total:1,synced_at:'now'}};
api.prepareLiepinPdf=async id=>{calls.push('prepare:'+id);return{run_id:'prepared',...base,phase:'prepared',account_effects_accepted:true}};
api.previewDailyPdf=async id=>{calls.push('preview:'+id);return{pdf_base64:'JVBERi0=',pdf_sha256:'hash'}};
api.uploadLiepinNativePdf=async(id,accept)=>{calls.push('upload:'+id+':'+accept);return{run_id:id,...base,phase:'uploaded_unverified',upload_state:'uploaded_unverified',upload_attempts:1}};
api.inspectUploadedLiepinPdf=async id=>{calls.push('inspect-upload:'+id);return{run_id:id,...base,phase:'attachment_verified'}};
api.inspectLiepinPdfTarget=async id=>{calls.push('target:'+id);return{run_id:id,...base,phase:'attachment_verified'}};
api.authorizeSingleLiepinPdf=async id=>{calls.push('authorize:'+id);return{run_id:id,...base,phase:'attachment_verified',single_delivery_authorized:true}};
api.startLiepinPdfCommunication=async id=>{calls.push('communicate:'+id);return{run_id:id,...base,phase:'communication_started'}};
api.continueLiepinPdfDelivery=async(id,action)=>{calls.push('continue:'+action);return{run_id:id,...base,can_confirm_send:action==='prepare',phase:action==='send'?'final_send_pending':action==='prepare'?'resume_interaction_pending':'communication_started'}};
api.verifyNativePdfReceipt=async id=>{calls.push('verify-receipt');return{run_id:id,...base,phase:'success',platform_filename:'cv_old.pdf'}};
let removalState='unknown'; api.recheckLiepinNativePdfRemoval=async id=>{calls.push('recheck-removal');return{run_id:id,...base,phase:'success',platform_filename:'cv_old.pdf',attachment_removal_state:'not_submitted'}};
api.removeLiepinNativePdfAttachment=async(id,confirmed)=>{calls.push('remove:'+id+':'+confirmed);return{run_id:id,...base,phase:'success',platform_filename:'cv_old.pdf',attachment_removal_state:removalState}};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/submissions/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
exports,console,Intl,Date,Map,Set,URLSearchParams,require:n=>{if(n==='react-router-dom')return{useSearchParams:()=>[params],useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:k=>k,i18n:{language:'zh'}})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@tauri-apps/api/core')return{convertFileSrc:x=>x};if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return {notify:()=>{},confirmAction:async()=>confirmAnswer,buttonClass:new Proxy({},{get:()=>''})};if(n==='@/components/pdf-quality-summary')return{PdfQualitySummary:()=>null};if(n==='@/components/quality-report')return{QualityReportPanel:()=>null};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
function render(){cursor=0;tree=exports.SubmissionsPage()}
async function settle(){for(let i=0;i<10;i++){render();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
const byTestId=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
(async()=>{await settle();assert.equal(nodes(tree).find(n=>n.props['aria-label']==='pages.submissions.nativePdf.selectQuickRun').props.value,'qr_linked');assert.equal(calls.length,0,'带参进入不得自动准备或写入');assert.ok(button('pages.submissions.nativeSession.open'),'缺少 App 原生登录入口');
await button('pages.submissions.nativeSession.open').props.onClick();await settle();
await button('pages.submissions.nativeSession.check').props.onClick();await settle();
assert.deepEqual(calls,['open','check']);assert.ok(text(tree).includes('pages.submissions.nativeSession.status.waiting_for_login'));
nativeStatus='authenticated';await button('pages.submissions.nativeSession.check').props.onClick();await settle();
await button('pages.submissions.nativeSession.inspect').props.onClick();await settle();assert.deepEqual(calls,['open','check','check','inspect']);assert.ok(text(tree).includes('支持 PDF'));
await button('pages.submissions.platformFeedback.sync').props.onClick();await settle();assert.ok(calls.includes('sync-feedback'),'只读同步走专用命令');assert.ok(text(tree).includes('pages.submissions.platformFeedback.summary'));
const runInput=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.submissions.nativePdf.selectQuickRun');assert.ok(runInput);runInput.props.onChange({target:{value:'quick'}});await settle();
await button('pages.submissions.nativePdf.prepare').props.onClick();await settle();assert.ok(calls.includes('prepare:quick'));assert.ok(text(tree).includes('pages.submissions.nativePdf.phase.prepared'));
assert.ok(button('pages.submissions.nativePdf.dailyCandidates'));await button('pages.submissions.nativePdf.dailyCandidates').props.onClick();assert.equal(navigations.at(-1),'/agent-run');
// 一键自动推进主按钮：未预览、未勾选时禁用；预览并勾选后串行推进到最终确认前。
const autoAdvance=()=>byTestId('pdf-auto-advance');
assert.ok(autoAdvance(),'缺少自动推进主按钮 pdf-auto-advance');
assert.ok(autoAdvance().props.disabled,'未预览未勾选时自动推进必须禁用');
assert.equal(nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.consent').props.checked,false);
await button('pages.submissions.nativePdf.preview').props.onClick();await settle();assert.ok(calls.includes('preview:prepared'));
nodes(tree).find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props['aria-label']==='pages.submissions.nativePdf.consent').props.onChange({target:{checked:true}});await settle();
assert.equal(autoAdvance().props.disabled,false,'预览并勾选且会话有效后自动推进应可用');
calls.length=0;await autoAdvance().props.onClick();await settle();
assert.deepEqual(calls,['open','check','upload:prepared:true','inspect-upload:prepared','authorize:prepared','communicate:prepared','continue:inspect','continue:prepare'],'自动推进必须先检查 App 内会话，再按 upload→inspect→authorize→communicate→inspectChat→prepareResume 串联');
assert.ok(!calls.includes('continue:send'),'自动推进不得自动最终发送');
assert.ok(text(tree).includes('pages.submissions.nativePdf.autoAdvanceReady'));
const finalConfirm=()=>byTestId('pdf-final-confirm');
assert.ok(finalConfirm(),'推进到确认前应显示最终确认按钮 pdf-final-confirm');
// 最终确认仍由人点击；点击后自动只读核验回执。
calls.length=0;await finalConfirm().props.onClick();await settle();
assert.deepEqual(calls,['continue:send','verify-receipt'],'最终确认后必须自动核验回执');
assert.ok(text(tree).includes('pages.submissions.nativePdf.phase.success'));
assert.ok(!finalConfirm(),'成功后不得再显示最终确认按钮');
// 高级操作只保留只读诊断，不再暴露重复写操作。
assert.ok(!button('pages.submissions.nativePdf.upload'),'高级操作不得保留重复上传按钮');
assert.ok(!button('pages.submissions.nativePdf.communicate'),'高级操作不得保留重复开始投递按钮');
assert.ok(!button('pages.submissions.nativePdf.prepareResume'),'高级操作不得保留重复准备简历按钮');
assert.ok(button('pages.submissions.nativePdf.inspect'),'只读检查入口保留');
assert.ok(button('pages.submissions.nativePdf.receipt'),'只读回执核验入口保留');
assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.removeConsent').props.onChange({target:{checked:true}});await settle();await button('pages.submissions.nativePdf.remove').props.onClick();await settle();assert.ok(calls.includes('remove:prepared:true'));assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);await button('pages.submissions.nativePdf.recheckRemoval').props.onClick();await settle();assert.ok(calls.includes('recheck-removal'));assert.equal(button('pages.submissions.nativePdf.remove').props.disabled,false);removalState='removed';await button('pages.submissions.nativePdf.remove').props.onClick();await settle();assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);
// 平台附件已在 App 外消失：成功记录仍可只读检查，页面提示并禁用移除。
api.inspectUploadedLiepinPdf=async id=>{calls.push('inspect-success');return{run_id:id,phase:'success',platform_filename:'cv_old.pdf',attachment_removal_state:'',platform_attachment_state:'missing_on_platform',company:'公司',position:'岗位',pdf_sha256:'hash'}};
assert.equal(button('pages.submissions.nativePdf.inspect').props.disabled,false,'成功记录仍可只读检查');await button('pages.submissions.nativePdf.inspect').props.onClick();await settle();assert.ok(calls.includes('inspect-success'));
assert.ok(text(tree).includes('pages.submissions.nativePdf.platformMissing'));assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);assert.ok(nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.removeConsent').props.disabled);
api.prepareLiepinPdf=async()=>({run_id:'interrupted',company:'本地恢复样例',position:'岗位',phase:'communication_started',pdf_sha256:'hash',recovery_only:true});
params=new URLSearchParams({quick_run_id:'qr_recovery'});await settle();await button('pages.submissions.nativePdf.prepare').props.onClick();await settle();assert.ok(text(tree).includes('pages.submissions.nativePdf.recoveryOnly'));
assert.ok(autoAdvance().props.disabled,'恢复态禁止自动推进写操作');assert.equal(button('pages.submissions.nativePdf.inspectChat').props.disabled,false,'只读核验仍可用');
params=new URLSearchParams({quick_run_id:'../invalid'});await settle();assert.equal(nodes(tree).find(n=>n.props['aria-label']==='pages.submissions.nativePdf.selectQuickRun').props.value,'');assert.ok(button('pages.submissions.nativePdf.prepare').props.disabled);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],text=True,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
