import subprocess
import pytest
from pathlib import Path


@pytest.mark.parametrize('extension',['pdf','PDF'])
def test_removal_targets_exact_card_and_never_confirms_ambiguity(extension):
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_remove.js','utf8');
(async()=>{for(const mode of ['valid','wrong','duplicate','changed','preexisting','other_menu','wrong_request','duplicate_request','form','duplicate_form','duplicate_json','notice','spaced','envelope','wrong_envelope','duplicate_data']){
 let menu=mode==='other_menu',dialog=['preexisting','notice'].includes(mode),notice=mode==='notice',confirmClicks=0,actualRequests=0;
 const record={fileId:'file-id',encryAttachmentId:mode==='wrong'?'wrong':'attachment',fileName:'cv_test',originalExtension:'pdf'};
 const icon={getClientRects:()=>[1],dispatchEvent:()=>{menu=true;},click:()=>{menu=true;}};
 const card={textContent:'cv_test.pdf',getClientRects:()=>[1],__reactFiber$test:{memoizedProps:{attachmentResume:record}},querySelectorAll:()=>[icon]};
 const other={...card,textContent:'other.pdf',__reactFiber$test:{memoizedProps:{attachmentResume:{...record,fileId:'other',encryAttachmentId:'other',fileName:'other'}}}};
 let cards=mode==='duplicate'?[card,{...card}]:[card,other];
 function Xhr(){this.listeners=[];this.status=200;this.responseText='{"flag":1,"data":{}}'}
 Xhr.prototype.open=function(){};Xhr.prototype.addEventListener=function(_,fn){this.listeners.push(fn)};
 Xhr.prototype.send=function(body){actualRequests++;const id=body instanceof FormData?body.get('encryAttachmentId'):(JSON.parse(body).data||JSON.parse(body)).encryAttachmentId;cards=id==='attachment'?[other]:[card];this.listeners.forEach(fn=>fn());};
 const confirm={textContent:mode==='spaced'?'确 定':'确定',disabled:false,getClientRects:()=>[1],click:()=>{confirmClicks++;const r=new Xhr();r.open('POST','https://api-c.liepin.com/api/com.liepin.cresume.attachment.remove-attachment-resume');let body=JSON.stringify({encryAttachmentId:mode==='wrong_request'?'other':'attachment'});if(mode==='form'||mode==='duplicate_form'){body=new FormData();if(mode==='duplicate_form')body.append('encryAttachmentId','other');body.append('encryAttachmentId','attachment');}if(mode==='envelope'||mode==='wrong_envelope')body=JSON.stringify({data:{encryAttachmentId:mode==='wrong_envelope'?'other':'attachment'}});if(mode==='duplicate_data')body='{"data":{"encryAttachmentId":"attachment"},"data":{}}';if(mode==='duplicate_json')body='{"encryAttachmentId":"other","encryAttachmentId":"attachment"}';r.send(body);if(mode==='duplicate_request'){const again=new Xhr();again.open('POST','https://api-c.liepin.com/api/com.liepin.cresume.attachment.remove-attachment-resume');again.send('{"encryAttachmentId":"attachment"}');}}};
 const close={getClientRects:()=>[1],disabled:false,click:()=>{dialog=false;notice=false;}};const modal={get innerText(){return notice?'1段经历可同步至在线简历中 无需手动填写，可直接添加到在线简历中':'确认提示 注意：此操作不可恢复，您确定要删除吗？'},getClientRects:()=>[1],querySelectorAll:s=>s==='input,textarea,select'?[]:s==='button.ant-modal-close'?[close]:[confirm]};
 const del={textContent:'删除',getClientRects:()=>[1],click:()=>{dialog=true;if(mode==='changed')record.encryAttachmentId='another';}};
 const document={body:{innerText:''},querySelectorAll:s=>s==='.attachment-view-box .resume-card-container'?cards:s==='.ant-dropdown-menu-item'&&menu?[del]:s==='.ant-modal-content'&&dialog?[modal]:[]};
 const location={href:'https://c.liepin.com/resume/edit'},window={fetch:async()=>{}};
 await vm.runInNewContext(source.replace('UPLOAD_PAYLOAD',JSON.stringify({filename:'cv_test.pdf',file_id:'file-id',attachment_id:'attachment',attachment_count:2})).replace('UPLOAD_NONCE','"t"'),{document,location,window,XMLHttpRequest:Xhr,URL,URLSearchParams,FormData,MouseEvent:class{},encodeURIComponent,setTimeout:(fn,ms)=>{if(ms<10000)fn();},clearTimeout:()=>{},getComputedStyle:()=>({visibility:'visible'})});
 const response=JSON.parse(new URL(location.href).searchParams.get('payload'));const detail=JSON.parse(response.responses[0].payload);
 const clicked=['valid','wrong_request','duplicate_request','form','duplicate_form','duplicate_json','notice','spaced','envelope','wrong_envelope','duplicate_data'].includes(mode);assert.equal(confirmClicks,clicked?1:0);assert.equal(detail.action.click_issued,clicked);assert.equal(actualRequests,['valid','duplicate_request','form','notice','spaced','envelope'].includes(mode)?1:0);
 if(mode==='valid'){assert.equal(detail.network.length,1);assert.equal(detail.after_ids.join(','),'other');}
}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    code=code.replace("{filename:'cv_test.pdf'","{filename:'cv_test."+extension+"'")
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_finished_attempt_cannot_remove_the_next_attempts_network_guard():
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');let run=1,menu=false,modalOpen=false,actual=0,timer=0,stale=[];const timers=new Map();
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_remove.js','utf8').replace('UPLOAD_PAYLOAD',JSON.stringify({filename:'cv.pdf',file_id:'file',attachment_id:'approved',attachment_count:1})).replace('UPLOAD_NONCE','"t"');
function Xhr(){this.listeners=[];this.status=200;this.responseText='{"flag":1}'}Xhr.prototype.open=function(){};Xhr.prototype.addEventListener=function(_,fn){this.listeners.push(fn)};Xhr.prototype.send=function(){actual++;this.listeners.forEach(fn=>fn())};
const icon={getClientRects:()=>[1],dispatchEvent(){if(run===2){for(const id of stale)timers.get(id)?.();menu=true;}}};
const card={getClientRects:()=>[1],querySelectorAll:()=>[icon],__reactFiber$t:{memoizedProps:{attachmentResume:{fileId:'file',encryAttachmentId:'approved',fileName:'cv',originalExtension:'pdf'}}}};
const del={getClientRects:()=>[1],textContent:'删除',click(){modalOpen=true}};
const confirm={getClientRects:()=>[1],textContent:'确定',disabled:false,click(){const r=new Xhr();r.open('POST','https://api-c.liepin.com/api/com.liepin.cresume.attachment.remove-attachment-resume');r.send('{"encryAttachmentId":"wrong"}')}};
const modal={getClientRects:()=>[1],innerText:'注意：此操作不可恢复，您确定要删除吗？',querySelectorAll:()=>[confirm]};
const document={body:{innerText:''},querySelectorAll:s=>s==='.attachment-view-box .resume-card-container'?[card]:s==='.ant-dropdown-menu-item'&&menu?[del]:s==='.ant-modal-content'&&modalOpen?[modal]:[]};
const location={href:'https://c.liepin.com/resume/edit'},window={fetch:async()=>{}};
const context=vm.createContext({window,document,location,XMLHttpRequest:Xhr,URL,URLSearchParams,FormData,MouseEvent:class{},encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),setTimeout:(fn,ms)=>{if(ms>=10000){timers.set(++timer,fn);return timer;}fn();return 0;},clearTimeout:id=>timers.delete(id)});
(async()=>{await vm.runInContext(source,context);stale=[...timers.keys()];run=2;location.href='https://c.liepin.com/resume/edit';await vm.runInContext(source,context);assert.equal(actual,0,'旧回调不得拆除新的请求前守卫');})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
