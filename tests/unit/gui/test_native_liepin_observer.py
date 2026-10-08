"""原生附件入口兼容语义文本节点，不绑定特定 HTML 标签。"""
import subprocess
from pathlib import Path


def test_attachment_entry_accepts_paragraph_and_refuses_ambiguity():
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_observe.js','utf8').replaceAll('NONCE_VALUE','"test"').replaceAll('INSPECT_ATTACHMENTS','true');
for (const count of [1,2]) {
  let clicks=0;
  const entries=Array.from({length:count},()=>({tagName:'P',textContent:'附件简历',children:[],getClientRects:()=>[1],click:()=>clicks++}));
  const doc={body:{innerText:'支持 PDF'},querySelectorAll(selector){
    if(selector==='*')return entries;
    if(selector==='.nav-user-item, [data-selector="c-logout"]')return [{getClientRects:()=>[1]}];
    return [];
  }};
  const location={origin:'https://c.liepin.com',hostname:'c.liepin.com',pathname:'/'};
  vm.runInNewContext(source,{document:doc,location,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),encodeURIComponent});
  const payload=JSON.parse(new URL(location.href).searchParams.get('payload'));
  assert.equal(payload.attachment_view.entry_count,count);
  assert.equal(clicks,count===1?1:0);
}
{
  const location={origin:'https://c.liepin.com',hostname:'c.liepin.com',pathname:'/resume/edit'};
  let opened=false;
  const upload={textContent:'去上传',children:[],getClientRects:()=>[1],click:()=>opened=true};
  const link={href:'https://c.liepin.com/resume/preview?resId=private',textContent:'预览/下载简历',getClientRects:()=>[1]};
  const doc={body:{innerText:'附件简历\n支持 PDF'},querySelectorAll(selector){
    if(selector==='a')return [link];
    if(selector==='*')return [upload];
    if(selector==='input[type="file"]')return opened ? [{accept:'.pdf',multiple:false,disabled:false}] : [];
    return [];
  }};
  vm.runInNewContext(source,{document:doc,location,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),encodeURIComponent,URL});
  const payload=JSON.parse(new URL(location.href).searchParams.get('payload'));
  assert.equal(payload.authenticated,true);
  assert.equal(payload.attachment_view.inputs[0].accept,'.pdf');
}
'''
    result = subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],text=True,capture_output=True,timeout=15)
    assert result.returncode == 0, result.stdout+result.stderr


def test_attachment_inspection_reports_bounded_visible_controls_without_clicking():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');let clicks=0;
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_observe.js','utf8').replaceAll('NONCE_VALUE','"test"').replaceAll('INSPECT_ATTACHMENTS','true');
const button={tagName:'BUTTON',textContent:'暂不添加',children:[],getClientRects:()=>[1],click:()=>clicks++};
const doc={body:{innerText:'附件简历'},querySelectorAll:s=>s==='button,[role="button"]'?[button]:[]};
const location={origin:'https://c.liepin.com',hostname:'c.liepin.com',pathname:'/resume/edit'};
vm.runInNewContext(source,{document:doc,location,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),encodeURIComponent,URL});
const result=JSON.parse(new URL(location.href).searchParams.get('payload'));
assert.ok(result.attachment_view.hints.some(s=>s.includes('暂不添加')));assert.equal(clicks,0);assert.ok(result.attachment_view.hints.length<=20);
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_existing_attachment_opens_only_the_unique_add_control():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_observe.js','utf8').replaceAll('NONCE_VALUE','"t"').replaceAll('INSPECT_ATTACHMENTS','true');
for(const count of [1,2]){
 let clicks=0;const plus=Array.from({length:count},()=>({getClientRects:()=>[1],click:()=>clicks++}));
 const doc={body:{innerText:'附件简历 existing.pdf'},querySelectorAll:s=>s==='[data-testid="attachment-resume-add-btn"]'?plus:s==='input[type="file"]'&&clicks?[{accept:'.pdf',multiple:false,disabled:false}]:[]};
 const location={origin:'https://c.liepin.com',hostname:'c.liepin.com',pathname:'/resume/edit'};
 vm.runInNewContext(source,{document:doc,location,getComputedStyle:()=>({visibility:'visible'}),setTimeout:fn=>fn(),encodeURIComponent,URL});
 assert.equal(clicks,count===1?1:0);const result=JSON.parse(new URL(location.href).searchParams.get('payload'));assert.equal(result.attachment_view.inputs.length,count===1?1:0);
}
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_attachment_inspection_closes_only_identified_sync_notice():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('ui/src-tauri/src/liepin_native_observe.js','utf8').replaceAll('NONCE_VALUE','"t"').replaceAll('INSPECT_ATTACHMENTS','true');
for(const scenario of ['notice','other','ambiguous','parse','late_parse','late_origin']){
 let closed=0,opened=0,synced=0;
 const close={getClientRects:()=>[1],getAttribute:n=>n==='aria-label'?'Close':null,click:()=>closed++};
 const sync={textContent:'立即查看',getClientRects:()=>[1],getAttribute:()=>null,click:()=>synced++};
 const dialog={innerText:scenario==='other'?'请确认同步在线简历':'1段经历可同步至在线简历中\n无需手动填写，可直接添加到在线简历中',getClientRects:()=>closed?[]:[1],querySelectorAll:()=>scenario==='ambiguous'?[close,close,sync]:[close,sync]};
 const add={getClientRects:()=>closed?[1]:[],click:()=>opened++};
 const doc={body:{innerText:'附件简历'},querySelectorAll:s=>s==='[role="dialog"]'?[dialog]:s==='[data-testid="attachment-resume-add-btn"]'?[add]:s==='input[type="file"]'&&opened?[{accept:'.pdf',multiple:false,disabled:false}]:[]};
 const location={origin:'https://c.liepin.com',hostname:'c.liepin.com',pathname:scenario==='parse'?'/resume/parse-result':'/resume/edit'};
 vm.runInNewContext(source,{document:doc,location,getComputedStyle:()=>({visibility:'visible'}),setTimeout:(fn,delay)=>{if(delay===250&&scenario==='late_parse')location.pathname='/resume/parse-result';if(delay===250&&scenario==='late_origin')location.origin='https://safe.liepin.com';fn();},encodeURIComponent,URL});
 assert.equal(closed,['notice','late_parse','late_origin'].includes(scenario)?1:0,scenario);
 assert.equal(opened,scenario==='notice'?1:0,scenario);
 assert.equal(synced,0,scenario);
}
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
