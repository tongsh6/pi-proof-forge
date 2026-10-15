"""新版附件页面仍只读指定已上传文件并核对字节摘要。"""
import subprocess
from pathlib import Path


def test_inspector_reads_legacy_and_module_cards_without_platform_writes():
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_inspect.js','utf8');
(async()=>{for(const modern of [false,true]){
 const file={fileName:'candidate',originalExtension:'pdf',fileId:'/recruit-auth/resume/attachment-res/c/new.PDF',fileSize:12,encryAttachmentId:'id',accessPath:'/recruit-auth/resume/attachment-res/c/new.PDF?ticket=test'};
 const card={textContent:'candidate.pdf',__reactFiber$test:{memoizedProps:{attachmentResume:file},return:null}};
 const selector=modern?'attachmentCard--':'.resume-card-container';
 const document={body:{innerText:'candidate.pdf'},scripts:[],querySelectorAll:s=>s.includes(selector)?[card]:[]};
 const location={origin:'https://c.liepin.com',href:'https://c.liepin.com/resume/edit'};const fetched=[];
 await vm.runInNewContext(script.replace('UPLOAD_PAYLOAD',JSON.stringify({filename:'candidate.PDF'})).replace('UPLOAD_NONCE','"n"'),{document,location,URL,performance:{getEntriesByType:()=>[]},Uint8Array,encodeURIComponent,
   crypto:{subtle:{digest:async()=>new Uint8Array(32).fill(1).buffer}},fetch:async(url,options)=>{fetched.push([url,options]);return{status:200,arrayBuffer:async()=>new Uint8Array(12).buffer}}});
 const result=JSON.parse(new URL(location.href).searchParams.get('payload'));const info=JSON.parse(result.responses[0].payload);
 assert.equal(info.attachment_count,1);assert.equal(info.attachments[0].encryAttachmentId,'id');assert.equal(info.attachments[0].download.byte_length,12);
 assert.equal(fetched.length,1);assert.equal(fetched[0][1].credentials,'include');assert.ok(!fetched[0][1].method||fetched[0][1].method==='GET');
 assert.equal(info.attachments[0].accessPath,'/recruit-auth/resume/attachment-res/c/new.PDF');assert.ok(file.accessPath.includes('?ticket='),'不修改页面原记录');
}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
