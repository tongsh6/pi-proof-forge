import subprocess
from pathlib import Path


def test_chat_entry_never_clicks_when_target_page_changed():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let clicks=0;const window={};
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_chat_open.js','utf8').replace('CHAT_PAYLOAD',JSON.stringify({job_url:'https://www.liepin.com/job/123.shtml',company:'公司',position:'岗位'}));
vm.runInNewContext(source,{window,location:{href:'https://www.liepin.com/job/456.shtml'},URL,document:{body:{innerText:'公司 岗位'},querySelectorAll:()=>[{textContent:'聊一聊',getClientRects:()=>[1],click:()=>clicks++}]},getComputedStyle:()=>({visibility:'visible'})});
assert.equal(clicks,0);assert.equal(window.__ppfPdfChatAction.click_issued,false);
'''
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_restore_uses_actual_im_launcher_not_its_noninteractive_label():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let launched=0,labelClicks=0;const title={tagName:'DIV',className:'im-ui-basic-entry-title',textContent:'我的沟通',children:[],getClientRects:()=>[1],click:()=>labelClicks++};
const icon={tagName:'DIV',className:'im-ui-basic-entry im-ui-basic-entry-c',textContent:'',children:[],getClientRects:()=>[1],click:()=>launched++};
const doc={body:{innerText:''},querySelectorAll:s=>s==='*'?[title,icon]:s==='.im-ui-basic-entry.im-ui-basic-entry-c'?[icon]:[]};
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_interact.js','utf8').replace('UPLOAD_PAYLOAD',JSON.stringify({action:'inspect',filename:'cv.pdf',company:'公司',position:'岗位'})).replace('UPLOAD_NONCE','"test"');
(async()=>{await vm.runInNewContext(source,{window:{},document:doc,location:{href:'https://www.liepin.com/job/123.shtml'},URL,encodeURIComponent,setTimeout:fn=>fn(),getComputedStyle:()=>({visibility:'visible'})});assert.equal(launched,1);assert.equal(labelClicks,0);})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_final_send_rechecks_selected_platform_file_id():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_interact.js','utf8');
(async()=>{for(const selected of ['wrong','file-id','duplicate']){
 let clicks=0;const root={className:'im-ui-chat-container',innerText:'公司 岗位',parentElement:null};
 const resume={textContent:'发简历',tagName:'SPAN',className:'im-ui-action-button-title',children:[],parentElement:root,getClientRects:()=>[1]};
 const confirm={textContent:'立即投递',disabled:false,click:()=>clicks++};
 const modal={className:'ant-im-modal-content',innerText:'选择附件简历 默认在线简历和附件简历 cv_hash',getClientRects:()=>[1],querySelectorAll:s=>s.startsWith('input')?(selected==='duplicate'?[{type:'radio',checked:true,value:'file-id'},{type:'radio',checked:false,value:'file-id'}]:[{type:'radio',checked:true,value:selected}]):s==='button'?[confirm]:[]};
 const doc={querySelectorAll:s=>s==='*'?[resume]:s==='.ant-im-modal-content'?[modal]:[]};
 function Xhr(){}Xhr.prototype.open=function(){};Xhr.prototype.send=function(){};
 const location={href:'https://www.liepin.com/job/123.shtml'},window={fetch:async()=>{}};
 const script=source.replace('UPLOAD_PAYLOAD',JSON.stringify({action:'send',file_id:'file-id',filename:'cv_hash.pdf',company:'公司',position:'岗位'})).replace('UPLOAD_NONCE','"test"');
 await vm.runInNewContext(script,{document:doc,location,window,XMLHttpRequest:Xhr,URL,URLSearchParams,encodeURIComponent,setTimeout:fn=>fn(),getComputedStyle:()=>({visibility:'visible'})});
 const result=JSON.parse(new URL(location.href).searchParams.get('payload'));const detail=JSON.parse(result.responses[0].payload);
 assert.equal(clicks,selected==='file-id'?1:0);assert.equal(detail.action.reason,selected==='file-id'?'approved_attachment_confirmation':'confirmation_not_verified');
}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_prepare_selects_only_unique_approved_attachment_without_sending():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_interact.js','utf8');
(async()=>{for(const count of [0,1,2]){
 let selectedClicks=0,sendClicks=0;const root={className:'im-ui-chat-container',innerText:'公司 岗位',parentElement:null};
 const resume={textContent:'发简历',tagName:'SPAN',className:'im-ui-action-button-title',children:[],parentElement:root,getClientRects:()=>[1],click:()=>{}};
 const old={type:'radio',checked:true,value:'old',disabled:false};
 const targets=Array.from({length:count},()=>({type:'radio',checked:false,value:'file-id',disabled:false,click(){selectedClicks++;old.checked=false;this.checked=true;}}));
 const modal={className:'ant-im-modal-content',innerText:'选择附件简历 默认在线简历和附件简历 cv_hash',getClientRects:()=>[1],querySelectorAll:s=>s.startsWith('input')?[old,...targets]:s==='button'?[{textContent:'立即投递',disabled:false,click:()=>sendClicks++}]:[]};
 const doc={querySelectorAll:s=>s==='*'?[resume]:s==='.ant-im-modal-content'?[modal]:[]};
 const location={href:'https://www.liepin.com/job/123.shtml'};
 await vm.runInNewContext(source.replace('UPLOAD_PAYLOAD',JSON.stringify({action:'prepare',file_id:'file-id',filename:'cv_hash.pdf',company:'公司',position:'岗位'})).replace('UPLOAD_NONCE','"t"'),{window:{},document:doc,location,URL,encodeURIComponent,setTimeout:fn=>fn(),getComputedStyle:()=>({visibility:'visible'})});
 assert.equal(selectedClicks,count===1?1:0);assert.equal(sendClicks,0);
}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_daily_send_refuses_expired_or_cancelled_permission_after_async_wait():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{for(const mode of ['expired','cancelled']){
 let clicks=0,ready=false;const root={className:'im-ui-chat-container',innerText:'公司 岗位',parentElement:null};
 const resume={textContent:'发简历',children:[],parentElement:root,getClientRects:()=>[1]};
 const confirm={textContent:'立即投递',disabled:false,click:()=>clicks++};
 const entry={getClientRects:()=>[1],querySelector:()=>({textContent:'公司'}),click:()=>ready=true};
 const modal={innerText:'选择附件简历 默认在线简历和附件简历 cv_hash',getClientRects:()=>[1],querySelectorAll:s=>s.startsWith('input')?[{checked:true,value:'file-id'}]:s==='button'?[confirm]:[]};
 const doc={querySelectorAll:s=>s==='*'?(ready?[resume]:[]):s==='.im-ui-contact-list-item'?[entry]:s==='.ant-im-modal-content'?[modal]:[]};
 const window={fetch:async()=>{}},location={href:'https://www.liepin.com/job/123.shtml'};let now=10;
 function Xhr(){}Xhr.prototype.open=function(){};Xhr.prototype.send=function(){};
 const payload={action:'send',file_id:'file-id',filename:'cv_hash.pdf',company:'公司',position:'岗位',daily_cycle:'cycle',write_deadline_ms:20};
 const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_interact.js','utf8').replace('UPLOAD_PAYLOAD',JSON.stringify(payload)).replace('UPLOAD_NONCE','"t"');
 await vm.runInNewContext(source,{window,document:doc,location,URL,URLSearchParams,XMLHttpRequest:Xhr,Date:{now:()=>now},encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>{if(mode==='expired')now=30;else window.__ppfCancelledDailyCycle='cycle';fn();}});
 assert.equal(clicks,0,'权限在 await 期间失效仍发送');
}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert r.returncode==0,r.stderr


def test_delayed_post_stays_blocked_after_observation_finishes():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{let sent=0,delayed;const root={className:'im-ui-chat-container',innerText:'公司 岗位'};
const resume={textContent:'发简历',children:[],parentElement:root,getClientRects:()=>[1]};
const window={fetch:async()=>{sent++;return {clone:()=>({json:async()=>({flag:1})})}}};
const confirm={textContent:'立即投递',disabled:false,click:()=>{delayed=()=>window.fetch('https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume',{method:'POST',body:'{}'}).catch(()=>{});}};
const modal={innerText:'选择附件简历 默认在线简历和附件简历 cv_hash',getClientRects:()=>[1],querySelectorAll:s=>s.startsWith('input')?[{checked:true,value:'file-id'}]:s==='button'?[confirm]:[]};
function Xhr(){}Xhr.prototype.open=function(){};Xhr.prototype.send=function(){};
let now=0;const payload={action:'send',file_id:'file-id',filename:'cv_hash.pdf',company:'公司',position:'岗位',daily_cycle:'cycle',write_deadline_ms:2500};
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_interact.js','utf8').replace('UPLOAD_PAYLOAD',JSON.stringify(payload)).replace('UPLOAD_NONCE','"t"');
await vm.runInNewContext(source,{window,document:{querySelectorAll:s=>s==='*'?[resume]:s==='.ant-im-modal-content'?[modal]:[]},location:{href:'https://www.liepin.com/job/123.shtml'},URL,URLSearchParams,XMLHttpRequest:Xhr,Date:{now:()=>now},encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),setTimeout:(fn,ms)=>{if(ms<2000){now=ms;fn();}return 1;},clearTimeout:()=>{}});
now=3000;window.__ppfCancelledDailyCycle='cycle';await delayed();assert.equal(sent,0,'观察结束后迟发 POST 绕过守卫');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
