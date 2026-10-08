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
