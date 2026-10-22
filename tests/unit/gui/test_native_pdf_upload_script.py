import subprocess
from pathlib import Path


def test_upload_script_refuses_bad_digest_and_ambiguous_inputs_before_dispatch():
    source=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('ui/src-tauri/src/liepin_native_upload.js','utf8');
(async()=>{for (const count of [0,1,2]) {
 let changed=0;
 const location={origin:'https://c.liepin.com',pathname:'/resume/edit'};
 const payload={filename:'resume_test.pdf',pdf_sha256:'11'.repeat(32),pdf_bytes:[37,80,68,70,45]};
 const document={body:{innerText:''},querySelectorAll:s=>s==='input[type="file"]'?Array.from({length:count},()=>({accept:'.pdf',disabled:false,dispatchEvent:()=>changed++})):[]};
 await vm.runInNewContext(script.replace('UPLOAD_PAYLOAD',JSON.stringify(payload)).replace('UPLOAD_NONCE','"n"'),{
  document,location,window:{},URL,crypto:{subtle:{digest:async()=>new Uint8Array(32).buffer}},Uint8Array,encodeURIComponent,
  setTimeout:fn=>fn(),getComputedStyle:()=>({visibility:'visible'})});
 assert.equal(changed,0);assert.ok(location.href.includes('piproofforge-pdf://result'));
 const result=JSON.parse(new URL(location.href).searchParams.get('payload'));assert.equal(result.status,'not_submitted');
}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',source],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_upload_script_reports_attachment_quota_before_clicking_controls():
    """附件已达上限（3 个、无添加图标）时明确回传 attachment_quota_reached，不空点页面控件。"""
    source = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('ui/src-tauri/src/liepin_native_upload.js','utf8');
let clicks=0;
const card={getClientRects:()=>[1],innerText:'旧附件.pdf'};
const section={
  className:'section--x marginTop--x',getClientRects:()=>[1],
  querySelectorAll:s=>s.includes('attachmentCard')?[card,card,card]:[],
  querySelector:()=>null,
};
const header={className:'sectionHeader--x',parentElement:section};
const title={textContent:'附件简历',getClientRects:()=>[1],parentElement:header};
const location={origin:'https://c.liepin.com',pathname:'/resume/edit',href:'https://c.liepin.com/resume/edit'};
const document={body:{innerText:''},querySelectorAll:s=>{
  if(s.includes('sectionTitle'))return[title];
  if(s==='input[type="file"]')return[];
  if(s==='body *')return[title];
  return[];
}};
const window={scrollTo:()=>{}};
(async()=>{await vm.runInNewContext(script.replace('UPLOAD_PAYLOAD',JSON.stringify({filename:'resume_test.pdf',pdf_sha256:'11'.repeat(32),pdf_bytes:[37,80,68,70,45]})).replace('UPLOAD_NONCE','"n"'),{
 document,location,window,URL,encodeURIComponent,Uint8Array,getComputedStyle:()=>({visibility:'visible'}),
 setTimeout:fn=>fn(),crypto:{subtle:{digest:async()=>new Uint8Array(32).buffer}}});
 const result=JSON.parse(new URL(location.href).searchParams.get('payload'));
 assert.equal(result.status,'not_submitted');
 assert.deepEqual(Array.from(result.hints),['attachment_quota_reached']);
 assert.equal(clicks,0,'达上限时不得点击任何页面控件');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',source],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
