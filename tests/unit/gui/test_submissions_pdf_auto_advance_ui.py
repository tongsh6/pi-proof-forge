"""Submissions PDF 一键自动推进与失败原因可视化的 GUI 回归测试。

用 node + TypeScript 转译真实页面源码，并以手写 React hooks mock 渲染；
不连接 sidecar/Tauri，全部 API 走可控 mock。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

BOOTSTRAP = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ts=require('./ui/node_modules/typescript');const hooks=[];let cursor=0,effects=[],tree;
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useRef(v){return react.useMemo(()=>({current:v}),[])},useState(v){const i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>{hooks[i].v=typeof n==='function'?n(hooks[i].v):n}]},
useMemo(fn,deps){const i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},useCallback(fn,deps){return react.useMemo(()=>fn,deps)},
useEffect(fn,deps){const i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
let params=new URLSearchParams({quick_run_id:'qr_linked'});let nativeStatus='authenticated';const navigations=[],calls=[];let confirmAnswer=true,refreshCount=0,sessionCalls=0;
const base={company:'公司',position:'岗位',pdf_sha256:'hash'};
const api={listSubmissions:async()=>{refreshCount+=1;return{items:[]}},listResumes:async()=>({items:[]}),getChannelSession:async()=>({session:{login_status:'login_required',account_identity:{}},artifact_paths:{}}),
openLiepinNativeSession:async()=>{sessionCalls+=1;return{status:'opened'}},checkLiepinNativeSession:async()=>{sessionCalls+=1;return{status:nativeStatus}},inspectLiepinNativeAttachments:async()=>({status:'authenticated',attachment_view:{inputs:[],hints:[]}}),
syncLiepinFeedback:async()=>({status:'records',matched:[],unmatched_rows:0,submissions_total:0,synced_at:'now',page_url:''}),
prepareLiepinPdf:async id=>({run_id:'run1',...base,phase:'prepared',account_effects_accepted:true}),
previewDailyPdf:async()=>({pdf_base64:'JVBERi0=',pdf_sha256:'hash'}),
uploadLiepinNativePdf:async(id,accept)=>{calls.push('upload:'+id+':'+accept);return{run_id:id,...base,phase:'uploaded_unverified',upload_state:'uploaded_unverified',upload_attempts:1}},
inspectUploadedLiepinPdf:async id=>{calls.push('inspect-upload:'+id);return{run_id:id,...base,phase:'attachment_verified'}},
inspectLiepinPdfTarget:async id=>{calls.push('target:'+id);return{run_id:id,...base,phase:'attachment_verified'}},
authorizeSingleLiepinPdf:async id=>{calls.push('authorize:'+id);return{run_id:id,...base,phase:'attachment_verified',single_delivery_authorized:true}},
startLiepinPdfCommunication:async id=>{calls.push('communicate:'+id);return{run_id:id,...base,phase:'communication_started'}},
continueLiepinPdfDelivery:async(id,action)=>{calls.push('continue:'+action);return{run_id:id,...base,can_confirm_send:action==='prepare',phase:action==='send'?'final_send_pending':action==='prepare'?'resume_interaction_pending':'communication_started'}},
verifyNativePdfReceipt:async id=>{calls.push('verify-receipt');return{run_id:id,...base,phase:'success',platform_filename:'cv_old.pdf'}},
removeLiepinNativePdfAttachment:async()=>({...base,phase:'success',platform_filename:'cv_old.pdf'}),
recheckLiepinNativePdfRemoval:async()=>({...base,phase:'success',platform_filename:'cv_old.pdf'}),
cleanupLiepinNativeAttachments:async()=>{calls.push('cleanup');return{status:'done',hints:[]}},diagnoseLiepinNativeAttachments:async()=>({status:'done',hints:[]}),
retrySubmission:async()=>undefined,getSubmissionDetail:async()=>({submission:null}),listSubmissionFeedback:async()=>({items:[],iterations:[]}),createFeedbackIteration:async()=>({}),decideQualityHighlight:async()=>undefined};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/submissions/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
exports,console,Intl,Date,Map,Set,URLSearchParams,require:n=>{if(n==='react-router-dom')return{useSearchParams:()=>[params],useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:(k,o)=>k+((o&&/delivery_already_attempted_detail|existingPreparedHint/.test(k))?JSON.stringify(o):''),i18n:{language:'zh'}})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@tauri-apps/api/core')return{convertFileSrc:x=>x};if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;if(n==='@/lib/ui')return {notify:()=>{},confirmAction:async()=>confirmAnswer,buttonClass:new Proxy({},{get:()=>''})};if(n==='@/components/pdf-quality-summary')return{PdfQualitySummary:()=>null};if(n==='@/components/quality-report')return{QualityReportPanel:()=>null};throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
function render(){cursor=0;tree=exports.SubmissionsPage()}
async function wait(rounds=12){for(let i=0;i<(rounds||12);i++){render();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
const byTestId=id=>nodes(tree).find(n=>n.props&&n.props['data-testid']===id);
const consentInput=()=>nodes(tree).find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props['aria-label']==='pages.submissions.nativePdf.consent');
const autoAdvance=()=>byTestId('pdf-auto-advance');
const finalConfirm=()=>byTestId('pdf-final-confirm');
async function mountPage(pdf){
  api.prepareLiepinPdf=async id=>{calls.push('prepare:'+id);return{run_id:'run1',...base,account_effects_accepted:true,...(pdf||{phase:'prepared'})}};
  await wait();
  await button('pages.submissions.nativePdf.prepare').props.onClick();
  await wait();
}
async function confirmSession(){await button('pages.submissions.nativeSession.check').props.onClick();await wait()}
async function approvePdf(){await button('pages.submissions.nativePdf.preview').props.onClick();await wait();consentInput().props.onChange({target:{checked:true}});await wait()}
'''

RUNNER = r'''
(async()=>{__BODY__})().catch(e=>{console.error(e);process.exitCode=1});
'''


def _run(body: str) -> subprocess.CompletedProcess[str]:
    script = BOOTSTRAP + RUNNER.replace("__BODY__", body)
    return subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )


def _assert_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_auto_advance_requires_preview_consent_then_runs_serial_chain():
    """a) 未预览/未勾选时禁用；预览+勾选后按固定顺序推进且不自动最终发送。"""
    body = r'''
await mountPage({phase:'prepared'});
assert.ok(autoAdvance(),'缺少自动推进主按钮 pdf-auto-advance');
assert.equal(autoAdvance().props.disabled,true,'未预览未勾选时自动推进必须禁用');
assert.equal(finalConfirm(),undefined,'未到最终确认前不得显示最终确认');
await confirmSession();
assert.equal(autoAdvance().props.disabled,true,'仅完成会话认证、未预览时自动推进仍必须禁用');
await approvePdf();
assert.equal(autoAdvance().props.disabled,false,'预览+勾选+会话认证后自动推进必须可用');
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.deepEqual(calls,['upload:run1:true','inspect-upload:run1','authorize:run1','communicate:run1','continue:inspect','continue:prepare'],'自动推进必须按 upload→inspect→authorize→communicate→inspectChat→prepareResume 串联');
assert.ok(!calls.includes('continue:send'),'自动推进不得自动执行最终发送');
assert.ok(finalConfirm(),'推进到确认前必须显示最终确认按钮 pdf-final-confirm');
assert.ok(text(tree).includes('pages.submissions.nativePdf.autoAdvanceReady'),'必须提示已推进到确认投递');
'''
    _assert_ok(_run(body))


def test_final_confirm_sends_then_auto_verifies_receipt_and_refreshes():
    """b) can_confirm_send 时显示最终确认；人点后自动只读核验回执并刷新记录。"""
    body = r'''
await mountPage({phase:'resume_interaction_pending',can_confirm_send:true});
assert.ok(finalConfirm(),'can_confirm_send=true 时必须显示最终确认按钮');
assert.equal(finalConfirm().props.disabled,false,'最终确认按钮应可点击');
calls.length=0;const refreshBefore=refreshCount;
await finalConfirm().props.onClick();await wait();
assert.deepEqual(calls,['continue:send','verify-receipt'],'点击最终确认后必须发送并自动核验回执');
assert.ok(refreshCount>refreshBefore,'回执核验后必须刷新投递记录');
assert.ok(text(tree).includes('pages.submissions.nativePdf.phase.success'),'核验成功应显示成功阶段');
assert.equal(finalConfirm(),undefined,'投递成功后不得再次显示最终确认按钮');
'''
    _assert_ok(_run(body))


def test_final_confirm_send_failure_keeps_button_and_readable_error():
    """b-2) 最终发送失败时保留最终确认按钮与可读错误，不伪造成功。"""
    body = r'''
await mountPage({phase:'resume_interaction_pending',can_confirm_send:true});
api.continueLiepinPdfDelivery=async()=>{calls.push('continue:send-fail');throw new Error('NATIVE_SESSION_PAGE_NOT_READY')};
calls.length=0;
await finalConfirm().props.onClick();await wait();
assert.deepEqual(calls,['continue:send-fail'],'发送失败后不得继续核验回执');
assert.ok(finalConfirm(),'发送失败时必须保留最终确认按钮');
assert.equal(finalConfirm().props.disabled,false,'失败后最终确认按钮应恢复可点击');
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.native_session_page_not_ready'),'失败原因必须映射为可读 i18n');
assert.ok(!text(tree).includes('pages.submissions.nativePdf.phase.success'),'发送失败不得显示投递成功');
'''
    _assert_ok(_run(body))


def test_final_confirm_receipt_failure_does_not_fake_success():
    """b-3) 发送成功但回执核验失败时保留只读核验入口与错误，不伪造成功。"""
    body = r'''
await mountPage({phase:'resume_interaction_pending',can_confirm_send:true});
api.verifyNativePdfReceipt=async()=>{calls.push('verify-receipt-fail');throw new Error('pdf_receipt_unconfirmed')};
calls.length=0;
await finalConfirm().props.onClick();await wait();
assert.deepEqual(calls,['continue:send','verify-receipt-fail'],'发送后必须尝试核验回执');
assert.ok(!text(tree).includes('pages.submissions.nativePdf.phase.success'),'回执失败不得伪造成功');
assert.ok(text(tree).includes('pages.submissions.nativePdf.receiptNotAvailable'),'回执失败显示既有可读提示');
assert.equal(finalConfirm(),undefined,'发送已发起后不得再次显示最终确认按钮');
assert.equal(button('pages.submissions.nativePdf.receipt').props.disabled,false,'只读回执核验入口必须保留');
'''
    _assert_ok(_run(body))


def test_not_submitted_shows_hints_and_chain_starts_from_upload():
    """c-1) not_submitted 展示 upload_hints 与可重试提示，自动链从 upload 开始。"""
    body = r'''
await mountPage({phase:'not_submitted',upload_state:'not_submitted',can_retry_upload:true,upload_attempts:2,upload_hints:['附件控件不唯一:共0个','上传弹窗未出现']});
const hints=byTestId('pdf-upload-hints');
assert.ok(hints,'not_submitted 必须展示 pdf-upload-hints');
assert.ok(text(hints).includes('附件控件不唯一:共0个'),'必须逐条渲染上次上传失败原因');
assert.ok(text(hints).includes('上传弹窗未出现'),'必须渲染全部 upload_hints');
assert.ok(text(hints).includes('pages.submissions.nativePdf.uploadNotSubmittedRetry'),'not_submitted 必须显示可重试上传');
assert.ok(text(hints).includes('pages.submissions.nativePdf.uploadAttemptsLabel'),'应展示上传尝试次数');
assert.equal(autoAdvance().props.disabled,true,'未重新预览/勾选时仍不能重试');
await confirmSession();await approvePdf();
assert.equal(autoAdvance().props.disabled,false,'not_submitted 预览勾选认证后可重试上传');
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.equal(calls[0],'upload:run1:true','not_submitted 自动链必须从 upload 开始');
assert.ok(!calls.some(c=>c.startsWith('prepare')),'not_submitted 重试不得重新准备快照');
assert.deepEqual(calls,['upload:run1:true','inspect-upload:run1','authorize:run1','communicate:run1','continue:inspect','continue:prepare']);
'''
    _assert_ok(_run(body))


def test_unknown_disables_auto_advance_but_keeps_readonly_inspect():
    """c-2) unknown 显示禁止重传提示、自动推进禁用、只读检查可用。"""
    body = r'''
await mountPage({phase:'unknown',upload_state:'unknown',can_retry_upload:false,upload_hints:['结果未知：页面在点击后关闭']});
const hints=byTestId('pdf-upload-hints');
assert.ok(hints,'unknown 必须展示 pdf-upload-hints');
assert.ok(text(hints).includes('pages.submissions.nativePdf.uploadUnknownNoRetry'),'unknown 必须显示禁止重传提示');
assert.ok(text(hints).includes('结果未知：页面在点击后关闭'),'unknown 必须显示原因');
assert.equal(autoAdvance().props.disabled,true,'unknown 阶段自动推进必须禁用');
assert.ok(button('pages.submissions.nativePdf.inspect'),'只读检查入口保留');
assert.equal(button('pages.submissions.nativePdf.inspect').props.disabled,false,'unknown 阶段只读检查必须可用');
calls.length=0;
await button('pages.submissions.nativePdf.inspect').props.onClick();await wait();
assert.ok(calls.includes('inspect-upload:run1'),'只读检查已保存附件可用');
assert.ok(!calls.some(c=>c.startsWith('upload')),'unknown 禁止重传');
'''
    _assert_ok(_run(body))


def test_auto_advance_stops_immediately_on_failure():
    """d) 自动链中途失败立即停止，后续动作不得继续调用，错误可读。"""
    body = r'''
await mountPage({phase:'prepared'});
await confirmSession();await approvePdf();
api.inspectUploadedLiepinPdf=async id=>{calls.push('inspect-upload-fail');throw new Error('NATIVE_SESSION_LOGIN_REQUIRED')};
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.deepEqual(calls,['upload:run1:true','inspect-upload-fail'],'失败后必须立即停止，不得继续后续动作');
assert.ok(!calls.some(c=>c.startsWith('authorize')||c.startsWith('communicate')||c.startsWith('continue:')),'失败后不得调用授权/开始投递/沟通检查');
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.native_session_login_required'),'失败原因必须映射为可读 i18n');
assert.equal(autoAdvance().props.disabled,false,'失败后按钮应恢复可用以便人工重试');
assert.equal(finalConfirm(),undefined,'失败不得推进到最终确认');
'''
    _assert_ok(_run(body))

def test_auto_advance_checks_session_itself_and_blocks_on_login():
    """e) 自动链在需要上传时先打开/检查 App 内会话，不再要求用户单独点“检查会话”。"""
    body = r'''
await mountPage({phase:'prepared'});
await approvePdf();
assert.equal(autoAdvance().props.disabled,false,'预览+勾选后即可自动推进，无需先手动检查会话');
calls.length=0;sessionCalls=0;
await autoAdvance().props.onClick();await wait();
assert.ok(sessionCalls>=2,'自动链必须先打开并检查 App 内会话');
assert.equal(calls[0],'upload:run1:true','会话有效后从上传开始');
'''
    _assert_ok(_run(body))


def test_auto_advance_stops_before_upload_when_session_not_logged_in():
    """e-2) 会话未登录时自动链不得上传，给出可读错误且不伪造成功。"""
    body = r'''
nativeStatus='waiting_for_login';
await mountPage({phase:'prepared'});
await approvePdf();
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.deepEqual(calls,[],'未登录时不得调用任何上传/写操作');
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.native_session_login_required'),'必须显示可读登录提示');
assert.equal(autoAdvance().props.disabled,false,'失败后按钮仍可重试');
'''
    _assert_ok(_run(body))

def test_quota_reached_shows_action_and_disables_auto_until_cleanup():
    """f) 附件达平台上限：展示原因与清理入口，自动推进禁用；清理后可再推进。"""
    body = r'''
await mountPage({phase:'not_submitted',upload_state:'not_submitted',can_retry_upload:true,upload_attempts:2,
  upload_hints:['attachment_quota_reached']});
const hints=byTestId('pdf-upload-hints');
assert.ok(hints,'附件上限必须展示 pdf-upload-hints');
assert.ok(text(hints).includes('pages.submissions.nativePdf.quotaReached'),'必须显示附件已达上限');
const cleanup=button('pages.submissions.nativePdf.quotaCleanupAction');
assert.ok(cleanup,'必须提供移除旧附件入口');
await approvePdf();
assert.equal(autoAdvance().props.disabled,true,'附件达上限时自动推进必须禁用，避免空转重试');
calls.length=0;
await cleanup.props.onClick();await wait();
assert.ok(calls.includes('cleanup'),'点击清理必须调用移除旧附件命令');
assert.ok(text(tree).includes('pages.submissions.nativePdf.quotaCleanupDone'),'清理后提示可再次自动推进');
assert.equal(autoAdvance().props.disabled,false,'清理成功后应解锁自动推进（后端旧 hints 不再阻塞）');
'''
    _assert_ok(_run(body))


def test_auto_advance_reports_quota_reached_instead_of_generic_stop():
    """f-2) 上传仍返回 not_submitted + 上限提示时，自动链必须给出可读上限错误，而不是静默停止。"""
    body = r'''
await mountPage({phase:'prepared'});
await approvePdf();
api.uploadLiepinNativePdf=async(id,accept)=>{calls.push('upload-quota');return{run_id:id,...base,phase:'not_submitted',can_retry_upload:true,upload_hints:['attachment_quota_reached','附件简历已达上限（3 个）']}};
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.deepEqual(calls,['upload-quota'],'上传未进入下一阶段时不得继续后续写操作');
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.attachment_quota_reached'),'必须显示可读上限错误');
assert.ok(!text(tree).includes('pages.submissions.nativePdf.autoAdvanceStopped'),'不得只给通用“已停止”提示');
'''
    _assert_ok(_run(body))


def test_auto_advance_reports_undispatched_upload_instead_of_generic_stop():
    """f-3) 上传脚本确定未派发但也没抛错时，自动链必须显示“未上传任何文件”的明确原因。"""
    body = r'''
await mountPage({phase:'prepared'});
await approvePdf();
api.uploadLiepinNativePdf=async(id,accept)=>{calls.push('upload-undispatched');return{run_id:id,...base,phase:'not_submitted',can_retry_upload:true,upload_hints:['附件控件不唯一:共0个','弹窗:未出现']}};
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.deepEqual(calls,['upload-undispatched'],'未派发时停止，不得继续');
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.pdf_upload_not_dispatched'),'必须显示未派发原因');
assert.ok(!text(tree).includes('pages.submissions.nativePdf.autoAdvanceStopped'),'不得只给通用停止提示');
'''
    _assert_ok(_run(body))


def test_auto_advance_maps_ai_disclosure_failure_to_readable_error():
    """f-4) AI 声明未确认时显示可读原因与重试入口，而不是原始错误码。"""
    body = r'''
await mountPage({phase:'communication_started'});
api.continueLiepinPdfDelivery=async(id,action)=>{calls.push('continue:'+action);throw new Error('ai_disclosure_not_confirmed')};
calls.length=0;
await autoAdvance().props.onClick();await wait();
assert.deepEqual(calls,['continue:inspect'],'声明未确认时停止并保留重试');
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.ai_disclosure_not_confirmed'),'必须映射为可读声明未确认提示');
assert.equal(autoAdvance().props.disabled,false,'失败后应可再次自动推进重试');
'''
    _assert_ok(_run(body))


def test_delivery_already_attempted_offers_loading_pinned_delivery():
    """f-5) 同岗位已有进行中投递时，不再让用户重新固定新 PDF；可一键载入已固定流程继续。"""
    body = r'''
await wait();
const runSelect=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.submissions.nativePdf.selectQuickRun');
runSelect.props.onChange({target:{value:'qr_new'}});await wait();
const preparedCalls=[];
api.prepareLiepinPdf=async id=>{
  preparedCalls.push(id);
  if(id==='qr_new')throw new Error('[VALIDATION_ERROR] delivery_already_attempted:quick_run_id=qr_old|pdf=旧版.pdf');
  return {run_id:'run_old',...base,phase:'communication_started',can_confirm_send:false};
};
await button('pages.submissions.nativePdf.prepare').props.onClick();await wait();
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.delivery_already_attempted_detail'),'必须显示可读的同岗位进行中说明');
assert.ok(text(tree).includes('旧版.pdf'),'必须显示已固定 PDF 名');
assert.ok(text(tree).includes('qr_old'),'必须显示已固定 Quick Run');
const recovery=byTestId('pdf-existing-prepared');
assert.ok(recovery,'必须提供载入已固定流程入口');
assert.ok(button('pages.submissions.nativePdf.loadPreparedPdf'),'缺少载入按钮');
await button('pages.submissions.nativePdf.loadPreparedPdf').props.onClick();await wait();
assert.ok(preparedCalls.includes('qr_old'),'载入必须按后端回传的 quick_run_id 继续');
assert.equal(nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='pages.submissions.nativePdf.selectQuickRun').props.value,'qr_old');
assert.ok(text(tree).includes('pages.submissions.nativePdf.existingPreparedLoaded'),'载入后提示可继续自动推进');
assert.equal(byTestId('pdf-existing-prepared'),undefined,'载入成功后不再显示冲突提示');
'''
    _assert_ok(_run(body))


def test_attachment_removal_failure_maps_readable_errors():
    """g) 移除平台附件失败时映射可读错误（证据未核验/投递未核验成功），不裸露原始错误码。"""
    body = r'''
await mountPage({phase:'success', platform_filename:'cv_old.pdf'});
const removalConsent=()=>nodes(tree).find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props['aria-label']==='pages.submissions.nativePdf.removeConsent');
assert.ok(removalConsent(),'投递成功卡片必须提供移除确认 checkbox');
assert.equal(button('pages.submissions.nativePdf.remove').props.disabled,true,'未勾选移除确认时移除按钮必须禁用');
removalConsent().props.onChange({target:{checked:true}});await wait();
assert.equal(button('pages.submissions.nativePdf.remove').props.disabled,false,'勾选移除确认后移除按钮必须可用');
api.removeLiepinNativePdfAttachment=async()=>{throw new Error('[VALIDATION_ERROR] attachment_removal_evidence_unverified:receipt_binding_mismatch')};
await button('pages.submissions.nativePdf.remove').props.onClick();await wait();
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.attachment_removal_evidence_unverified'),'证据复核未通过必须映射为可读错误');
assert.ok(!text(tree).includes(':receipt_binding_mismatch'),'不得裸露后端原因后缀');
api.removeLiepinNativePdfAttachment=async()=>{throw new Error('[VALIDATION_ERROR] attachment_removal_success_required')};
await button('pages.submissions.nativePdf.remove').props.onClick();await wait();
assert.ok(text(tree).includes('pages.submissions.nativePdf.errors.attachment_removal_success_required'),'投递未核验为成功必须映射为可读错误');
assert.ok(!text(tree).includes('[VALIDATION_ERROR]'),'不得展示原始错误前缀');
'''
    _assert_ok(_run(body))


def test_missing_platform_attachment_can_reupload_and_continue():
    """f-6) 最终发送前平台附件被移除时，可重新上传同一 PDF、核验绑定后继续自动推进。"""
    body = r'''
await mountPage({phase:'resume_interaction_pending',can_confirm_send:false,can_reupload_attachment:true});
const block=byTestId('pdf-reupload-missing');
assert.ok(block,'缺少附件已不在的恢复提示');
assert.ok(text(block).includes('pages.submissions.nativePdf.reuploadMissingTitle'));
api.inspectUploadedLiepinPdf=async id=>{calls.push('inspect-upload:'+id);return{run_id:id,...base,phase:'resume_interaction_pending',attachment_bound:true,can_reupload_attachment:false}};
calls.length=0;
await button('pages.submissions.nativePdf.reuploadMissingAction').props.onClick();await wait();
assert.ok(calls.includes('upload:run1:true'),'必须先重新上传同一份已批准 PDF');
assert.ok(calls.includes('inspect-upload:run1'),'上传后必须重新核验平台附件绑定');
assert.ok(text(tree).includes('pages.submissions.nativePdf.reuploadMissingDone'),'恢复后提示可继续自动推进');
assert.equal(byTestId('pdf-reupload-missing'),undefined,'恢复成功后不再显示缺失提示');
assert.equal(autoAdvance().props.disabled,false,'附件重新绑定后自动推进应可用');
'''
    _assert_ok(_run(body))
