import subprocess
import pytest
from pathlib import Path


@pytest.mark.parametrize('extension',['pdf','PDF'])
def test_inspection_uses_signed_url_only_in_memory_and_returns_redacted_metadata(extension):
    code=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let fetched='';const record={fileName:'cv',originalExtension:'pdf',fileId:'/recruit-auth/resume/attachment-res/c/test.pdf',accessPath:'/recruit-auth/resume/attachment-res/c/test.pdf?tk=sensitive-query#fragment',fileSize:5};
const card={textContent:'cv.pdf','__reactFiber$test':{memoizedProps:{attachmentResume:record},return:null}};
const link={textContent:'cv.pdf',href:'https://tdoss.liepin.com/o/test.pdf?tk=sensitive-query#fragment'};
const document={body:{innerText:'cv.pdf'},scripts:[],querySelectorAll:s=>s.includes('.attachment-view-box .resume-card-container')?[card]:s==='a'?[link]:[]};
const location={href:'https://c.liepin.com/resume/edit',origin:'https://c.liepin.com'};
const script=fs.readFileSync('ui/src-tauri/src/liepin_native_pdf_inspect.js','utf8').replace('UPLOAD_PAYLOAD','{"filename":"cv.pdf"}').replace('UPLOAD_NONCE','"test"');
(async()=>{await vm.runInNewContext(script,{document,location,URL,Uint8Array,encodeURIComponent,performance:{getEntriesByType:()=>[]},fetch:async url=>{fetched=url;return{status:200,arrayBuffer:async()=>new Uint8Array([37,80,68,70,45]).buffer}},crypto:{subtle:{digest:async()=>new Uint8Array(32).buffer}}});
assert.ok(fetched.includes('sensitive-query'));assert.ok(record.accessPath.includes('sensitive-query'));
const result=JSON.parse(new URL(location.href).searchParams.get('payload'));assert.ok(!JSON.stringify(result).includes('sensitive-query'));assert.ok(!JSON.stringify(result).includes('#fragment'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    code=code.replace('"filename":"cv.pdf"','"filename":"cv.'+extension+'"')
    result=subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
