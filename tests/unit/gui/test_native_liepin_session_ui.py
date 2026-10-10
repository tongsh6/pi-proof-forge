"""执行原生登录入口组件事件；不是网站登录成功的证明。"""
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
let params=new URLSearchParams({quick_run_id:'qr_linked'});const navigations=[];let nativeStatus='waiting_for_login'; const calls=[];const api={listSubmissions:async()=>({items:[]}),getChannelSession:async()=>({session:{login_status:'login_required',account_identity:{}},artifact_paths:{}}),
openLiepinNativeSession:async()=>{calls.push('open');return{status:'opened'}},checkLiepinNativeSession:async()=>{calls.push('check');return{status:nativeStatus}}};
api.inspectLiepinNativeAttachments=async()=>{calls.push('inspect');return{status:'authenticated',attachment_view:{inputs:[{accept:'.pdf'}],hints:['支持 PDF']}}};
api.prepareLiepinPdf=async id=>{calls.push('prepare:'+id);return{run_id:'prepared',company:'公司',position:'岗位',phase:'prepared',pdf_sha256:'hash',account_effects_accepted:true}};
api.previewDailyPdf=async id=>{calls.push('preview:'+id);return{pdf_base64:'JVBERi0=',pdf_sha256:'hash'}};
api.uploadLiepinNativePdf=async(id,accept)=>{calls.push('upload:'+id+':'+accept);return{run_id:id,company:'公司',position:'岗位',phase:'uploaded_unverified',pdf_sha256:'hash'}};
api.inspectUploadedLiepinPdf=async id=>{calls.push('inspect-upload:'+id);return{run_id:id,phase:'attachment_verified',company:'公司',position:'岗位',pdf_sha256:'hash'}};
api.inspectLiepinPdfTarget=async id=>{calls.push('target:'+id);return{run_id:id,phase:'attachment_verified',company:'公司',position:'岗位',pdf_sha256:'hash'}};
api.startLiepinPdfCommunication=async id=>{calls.push('communicate:'+id);return{run_id:id,phase:'communication_started',company:'公司',position:'岗位',pdf_sha256:'hash'}};
api.continueLiepinPdfDelivery=async(id,action)=>{calls.push('continue:'+action);return{run_id:id,can_confirm_send:action==='prepare',phase:action==='send'?'final_send_pending':action==='prepare'?'resume_interaction_pending':'communication_started',company:'公司',position:'岗位',pdf_sha256:'hash'}};
api.verifyNativePdfReceipt=async id=>{calls.push('verify-receipt');return{run_id:id,phase:'success',platform_filename:'cv_old.pdf',company:'公司',position:'岗位',pdf_sha256:'hash'}};
let removalState='unknown'; api.recheckLiepinNativePdfRemoval=async id=>{calls.push('recheck-removal');return{run_id:id,phase:'success',platform_filename:'cv_old.pdf',attachment_removal_state:'not_submitted',company:'公司',position:'岗位',pdf_sha256:'hash'}};
api.removeLiepinNativePdfAttachment=async(id,confirmed)=>{calls.push('remove:'+id+':'+confirmed);return{run_id:id,phase:'success',platform_filename:'cv_old.pdf',attachment_removal_state:removalState,company:'公司',position:'岗位',pdf_sha256:'hash'}};
const exports={},jsx=(type,props)=>({type,props:props||{}});
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/submissions/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
exports,console,Intl,Date,Map,Set,URLSearchParams,require:n=>{if(n==='react-router-dom')return{useSearchParams:()=>[params],useNavigate:()=>url=>navigations.push(url)};if(n==='react')return react;if(n==='react/jsx-runtime')return{jsx,jsxs:jsx};if(n==='react-i18next')return{useTranslation:()=>({t:k=>k,i18n:{language:'zh'}})};if(n==='lucide-react')return new Proxy({},{get:(_,k)=>k});if(n==='@tauri-apps/api/core')return{convertFileSrc:x=>x};if(n==='@/lib/errors')return{getErrorMessage:e=>String(e)};if(n==='@/lib/sidecar/api')return api;throw Error(n)}});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
function render(){cursor=0;tree=exports.SubmissionsPage()}
async function settle(){for(let i=0;i<8;i++){render();const pending=effects;effects=[];for(const fn of pending)fn();await Promise.resolve();await Promise.resolve()}}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()===label);
(async()=>{await settle();assert.equal(nodes(tree).find(n=>n.props['aria-label']==='pages.submissions.nativePdf.quickRun').props.value,'qr_linked');assert.equal(calls.length,0,'带参进入不得自动准备或写入');assert.ok(button('pages.submissions.nativeSession.open'),'缺少 App 原生登录入口');
await button('pages.submissions.nativeSession.open').props.onClick();await settle();
await button('pages.submissions.nativeSession.check').props.onClick();await settle();
assert.deepEqual(calls,['open','check']);assert.ok(text(tree).includes('pages.submissions.nativeSession.status.waiting_for_login'));
nativeStatus='authenticated';await button('pages.submissions.nativeSession.check').props.onClick();await settle();
await button('pages.submissions.nativeSession.inspect').props.onClick();await settle();assert.deepEqual(calls,['open','check','check','inspect']);assert.ok(text(tree).includes('支持 PDF'));
const runInput=nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.quickRun');assert.ok(runInput);runInput.props.onChange({target:{value:'quick'}});await settle();
await button('pages.submissions.nativePdf.prepare').props.onClick();await settle();assert.ok(button('pages.submissions.nativePdf.upload').props.disabled);assert.ok(button('pages.submissions.nativePdf.dailyCandidates'));await button('pages.submissions.nativePdf.dailyCandidates').props.onClick();assert.equal(navigations.at(-1),'/agent-run');
assert.equal(nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.consent').props.checked,false);
assert.ok(button('pages.submissions.nativePdf.preview'));await button('pages.submissions.nativePdf.preview').props.onClick();await settle();assert.ok(calls.includes('preview:prepared'));
nodes(tree).find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props['aria-label']==='pages.submissions.nativePdf.consent').props.onChange({target:{checked:true}});await settle();
await button('pages.submissions.nativePdf.upload').props.onClick();await settle();assert.ok(calls.includes('upload:prepared:true'));assert.ok(text(tree).includes('pages.submissions.nativePdf.phase.uploaded_unverified'));
await button('pages.submissions.nativePdf.inspect').props.onClick();await settle();assert.ok(calls.includes('inspect-upload:prepared'));
await button('pages.submissions.nativePdf.target').props.onClick();await settle();assert.ok(calls.includes('target:prepared'));
await button('pages.submissions.nativePdf.communicate').props.onClick();await settle();assert.ok(calls.includes('communicate:prepared'));assert.ok(button('pages.submissions.nativePdf.communicate').props.disabled);
await button('pages.submissions.nativePdf.inspectChat').props.onClick();await settle();await button('pages.submissions.nativePdf.prepareResume').props.onClick();await settle();assert.ok(calls.includes('continue:prepare'));assert.ok(button('pages.submissions.nativePdf.prepareResume').props.disabled);
assert.equal(button('pages.submissions.nativePdf.send').props.disabled,false);await button('pages.submissions.nativePdf.send').props.onClick();await settle();assert.ok(button('pages.submissions.nativePdf.send').props.disabled);assert.ok(calls.includes('continue:send'));
await button('pages.submissions.nativePdf.receipt').props.onClick();await settle();assert.ok(calls.includes('verify-receipt'));assert.ok(text(tree).includes('pages.submissions.nativePdf.phase.success'));
assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.removeConsent').props.onChange({target:{checked:true}});await settle();await button('pages.submissions.nativePdf.remove').props.onClick();await settle();assert.ok(calls.includes('remove:prepared:true'));assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);await button('pages.submissions.nativePdf.recheckRemoval').props.onClick();await settle();assert.ok(calls.includes('recheck-removal'));assert.equal(button('pages.submissions.nativePdf.remove').props.disabled,false);removalState='removed';await button('pages.submissions.nativePdf.remove').props.onClick();await settle();assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);
// 平台附件已在 App 外消失：成功记录仍可只读检查，页面提示并禁用移除。
api.inspectUploadedLiepinPdf=async id=>{calls.push('inspect-success');return{run_id:id,phase:'success',platform_filename:'cv_old.pdf',attachment_removal_state:'',platform_attachment_state:'missing_on_platform',company:'公司',position:'岗位',pdf_sha256:'hash'}};
assert.equal(button('pages.submissions.nativePdf.inspect').props.disabled,false,'成功记录仍可只读检查');await button('pages.submissions.nativePdf.inspect').props.onClick();await settle();assert.ok(calls.includes('inspect-success'));
assert.ok(text(tree).includes('pages.submissions.nativePdf.platformMissing'));assert.ok(button('pages.submissions.nativePdf.remove').props.disabled);assert.ok(nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='pages.submissions.nativePdf.removeConsent').props.disabled);
api.prepareLiepinPdf=async()=>({run_id:'interrupted',company:'本地恢复样例',position:'岗位',phase:'communication_started',pdf_sha256:'hash',recovery_only:true});
params=new URLSearchParams({quick_run_id:'qr_recovery'});await settle();await button('pages.submissions.nativePdf.prepare').props.onClick();await settle();assert.ok(text(tree).includes('pages.submissions.nativePdf.recoveryOnly'));
assert.ok(button('pages.submissions.nativePdf.prepareResume').props.disabled);assert.ok(button('pages.submissions.nativePdf.communicate').props.disabled);assert.ok(button('pages.submissions.nativePdf.upload').props.disabled);assert.ok(button('pages.submissions.nativePdf.send').props.disabled);assert.equal(button('pages.submissions.nativePdf.inspectChat').props.disabled,false,'只读核验仍可用');
params=new URLSearchParams({quick_run_id:'../invalid'});await settle();assert.equal(nodes(tree).find(n=>n.props['aria-label']==='pages.submissions.nativePdf.quickRun').props.value,'');assert.ok(button('pages.submissions.nativePdf.prepare').props.disabled);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],text=True,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
