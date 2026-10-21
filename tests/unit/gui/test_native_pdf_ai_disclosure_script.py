import subprocess
from pathlib import Path


def test_ai_disclosure_sends_statement_in_target_chat_and_reports_dom_confirmation():
    code = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const TEXT='测试声明：本投递所使用的简历和投递操作均由 AI 自动化执行。';
let clicks=0,sent=false;
class FakeTextarea{
  constructor(){this._value='';this.className='ant-im-input ant-im-input-borderless im-ui-textarea';this.tagName='TEXTAREA';
    this.parentElement={className:'im-ui-input-content'};this.__input=false;}
  get value(){return this._value;}set value(v){this._value=v;}
  getClientRects(){return [1];}dispatchEvent(event){if(event.type==='input')this.__input=true;}focus(){}
  getAttribute(){return '请输入文字，按Enter键发送';}
}
const input=new FakeTextarea();
const button={className:'ant-im-btn im-ui-basic-send-btn',tagName:'BUTTON',textContent:'发送',
  get disabled(){return !input.__input;},getClientRects(){return [1];},click(){clicks++;sent=true;}};
const container={className:'im-ui-chat-container',get innerText(){return '韩先生 公司 岗位 '+(sent?TEXT:'');},
  getClientRects(){return [1];}};
const doc={body:{innerText:'公司 岗位'},querySelectorAll(selector){
  if(selector==='[class*="im-ui"]')return [container,input,button];
  if(selector==='textarea.im-ui-textarea,textarea')return [input];
  if(selector==='.im-ui-basic-send-btn,button')return [button];
  if(selector==='.im-ui-basic-send-btn')return [button];
  return [];
}};
const location={href:'https://www.liepin.com/job/123.shtml',origin:'https://www.liepin.com'};
const window={fetch:async()=>({clone:()=>({json:async()=>({})})})};
function Xhr(){}Xhr.prototype.open=function(){};Xhr.prototype.send=function(){};
class Event{constructor(type,opts){this.type=type;this.bubbles=!!(opts&&opts.bubbles);}}
const payload={ai_disclosure:{text:TEXT},filename:'cv.pdf',job_url:'https://www.liepin.com/job/123.shtml',company:'公司',position:'岗位'};
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_ai_disclosure.js','utf8')
  .replace('UPLOAD_PAYLOAD',JSON.stringify(payload)).replace('UPLOAD_NONCE','"t"');
(async()=>{
  await vm.runInNewContext(source,{window,document:doc,location,URL,URLSearchParams,Event,XMLHttpRequest:Xhr,
    encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),Date});
  const result=JSON.parse(new URL(location.href).searchParams.get('payload'));
  const detail=JSON.parse(result.responses[0].payload);
  assert.equal(clicks,1,'statement not sent');
  assert.equal(detail.action.click_issued,true);
  assert.equal(detail.action.reason,'approved_ai_disclosure_send');
  assert.equal(detail.ai_disclosure.confirmed,true);
  assert.equal(detail.ai_disclosure.evidence,'dom');
  assert.ok(detail.context.class_name.includes('im-ui-chat-container'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node', '-e', code], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ai_disclosure_is_idempotent_when_statement_already_visible():
    code = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const TEXT='测试声明：本投递由 AI 自动化执行。';
let clicks=0;
class FakeTextarea{constructor(){this.value='';this.className='im-ui-textarea';this.tagName='TEXTAREA';this.parentElement={className:'im-ui-input-content'};}getClientRects(){return [1];}dispatchEvent(){}focus(){}getAttribute(){return '';}}
const input=new FakeTextarea();
const button={className:'im-ui-basic-send-btn',tagName:'BUTTON',textContent:'发送',disabled:false,getClientRects(){return [1];},click(){clicks++;}};
const container={className:'im-ui-chat-container',innerText:'公司 岗位 '+TEXT,getClientRects(){return [1];}};
const doc={body:{innerText:'公司 岗位 '+TEXT},querySelectorAll(selector){
  if(selector==='[class*="im-ui"]')return [container,input,button];
  if(selector==='textarea.im-ui-textarea,textarea')return [input];
  if(selector==='.im-ui-basic-send-btn,button')return [button];
  return [];
}};
const location={href:'https://www.liepin.com/job/123.shtml',origin:'https://www.liepin.com'};
const window={};
function Xhr(){}Xhr.prototype.open=function(){};Xhr.prototype.send=function(){};
class Event{constructor(type,opts){this.type=type;}}
const payload={ai_disclosure:{text:TEXT},filename:'cv.pdf',job_url:'https://www.liepin.com/job/123.shtml',company:'公司',position:'岗位'};
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_ai_disclosure.js','utf8')
  .replace('UPLOAD_PAYLOAD',JSON.stringify(payload)).replace('UPLOAD_NONCE','"t"');
(async()=>{
  await vm.runInNewContext(source,{window,document:doc,location,URL,URLSearchParams,Event,XMLHttpRequest:Xhr,
    encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),Date});
  const detail=JSON.parse(JSON.parse(new URL(location.href).searchParams.get('payload')).responses[0].payload);
  assert.equal(clicks,0,'duplicate statement sent');
  assert.equal(detail.ai_disclosure.confirmed,true);
  assert.equal(detail.ai_disclosure.evidence,'dom');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node', '-e', code], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ai_disclosure_blocks_on_wrong_target_missing_composer_and_expired_permission():
    code = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const TEXT='测试声明';
const scenarios=[
  {name:'url',href:'https://www.liepin.com/job/999.shtml',context:'公司 岗位',composer:true,expected:'target_url_mismatch'},
  {name:'recipient',href:'https://www.liepin.com/job/123.shtml',context:'公司',composer:true,expected:'active_recipient_not_verified'},
  {name:'composer',href:'https://www.liepin.com/job/123.shtml',context:'公司 岗位',composer:false,expected:'composer_missing'},
  {name:'expired',href:'https://www.liepin.com/job/123.shtml',context:'公司 岗位',composer:true,expected:'daily_write_cancelled',deadline:1},
];
(async()=>{
for(const scenario of scenarios){
  let clicks=0;
  class FakeTextarea{constructor(){this.value='';this.className='im-ui-textarea';this.tagName='TEXTAREA';this.parentElement={className:'im-ui-input-content'};}getClientRects(){return [1];}dispatchEvent(){}focus(){}getAttribute(){return '';}}
  const input=new FakeTextarea();
  const button={className:'im-ui-basic-send-btn',tagName:'BUTTON',textContent:'发送',disabled:false,getClientRects(){return [1];},click(){clicks++;}};
  const container={className:'im-ui-chat-container',innerText:scenario.context,getClientRects(){return [1];}};
  const doc={body:{innerText:scenario.context},querySelectorAll(selector){
    if(selector==='[class*="im-ui"]')return [container,input,button];
    if(selector==='textarea.im-ui-textarea,textarea')return scenario.composer?[input]:[];
    if(selector==='.im-ui-basic-send-btn,button')return [button];
    return [];
  }};
  const location={href:scenario.href,origin:'https://www.liepin.com'};
  const window={};
  function Xhr(){}Xhr.prototype.open=function(){};Xhr.prototype.send=function(){};
  class Event{constructor(type,opts){this.type=type;}}
  const payload={ai_disclosure:{text:TEXT},filename:'cv.pdf',write_deadline_ms:scenario.deadline,
    job_url:'https://www.liepin.com/job/123.shtml',company:'公司',position:'岗位'};
  const source=fs.readFileSync('ui/src-tauri/src/liepin_native_ai_disclosure.js','utf8')
    .replace('UPLOAD_PAYLOAD',JSON.stringify(payload)).replace('UPLOAD_NONCE','"t"');
  await vm.runInNewContext(source,{window,document:doc,location,URL,URLSearchParams,Event,XMLHttpRequest:Xhr,
    encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),Date:{now:()=>scenario.deadline?2:0}});
  const detail=JSON.parse(JSON.parse(new URL(location.href).searchParams.get('payload')).responses[0].payload);
  assert.equal(detail.action.click_issued,false,scenario.name);
  assert.equal(detail.action.reason,scenario.expected,scenario.name);
  assert.equal(clicks,0,scenario.name);
}
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node', '-e', code], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
