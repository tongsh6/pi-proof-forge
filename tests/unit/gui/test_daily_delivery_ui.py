"""实际执行每日授权组件的事件，不把测试组件当作原生验收。"""
import subprocess
from pathlib import Path


def test_daily_draft_requires_saved_scope_and_explicit_confirmation():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
let cursor=0,hooks=[],effects=[],tree,calls=[],navigations=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}},useCallback(f){return f}};
const item={run_id:'r1',company:'公司',position:'职位',pdf_sha256:'a'.repeat(64),pdf_path:'/safe/resume.pdf'};
let state={authorization:null,today:{day:'2026-10-05',confirmed:0,occupied:0},history:[],candidates:[item]};
const api={getDailyStatus:async()=>state,saveDailyDraft:async p=>{calls.push(['save',p]);state={...state,authorization:{...p,id:'auth',state:'draft',scope:p.run_ids.map(()=>item)}};return state},changeDailyAuthorization:async(id,status,confirmed)=>{calls.push([status,confirmed]);state={...state,authorization:{...state.authorization,state:status}};return state},runDailyDelivery:async()=>{calls.push(['run']);return state},closeInterruptedDaily:async()=>state};
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/agent-run/daily-delivery.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,Date,Set,console,window:{setInterval:()=>1,clearInterval:()=>{}},require:n=>n==='react-router-dom'?{useNavigate:()=>url=>navigations.push(url)}:n==='react'?react:n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='@/lib/sidecar/api'?api:n==='@/lib/errors'?{getErrorMessage:String}:n==='@tauri-apps/api/core'?{convertFileSrc:x=>x}:{} });
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const by=id=>nodes(tree).find(n=>n.props['data-testid']===id);async function settle(){for(let i=0;i<7;i++){cursor=0;tree=exports.DailyDeliveryPanel();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
(async()=>{await settle();assert.ok(by('daily-panel'));
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
