"""附件清理脚本：新版卡片「...」菜单 + ant-c 确认框；只删 App 命名规则的旧 PDF。"""
import subprocess
from pathlib import Path


def test_cleanup_removes_only_app_generated_attachments_with_new_dom():
    source = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('ui/src-tauri/src/liepin_native_cleanup_attachments.js','utf8');
let menu=false,dialog=false,confirmClicks=0,removed=[];
const appRecord={fileName:'童双龙-某司-后端-20261010.1',originalExtension:'pdf',fileId:'/a.pdf',encryAttachmentId:'a'};
const otherRecord={fileName:'自定义简历',originalExtension:'pdf',fileId:'/b.pdf',encryAttachmentId:'b'};
const makeCard=(record)=>({
  getClientRects:()=>[1],
  get innerText(){return String(record.fileName)+'.pdf 0.6MB2026.10.10 21:56上传';},
  __reactFiber$t:{memoizedProps:{attachmentResume:record}},
  querySelectorAll:s=>s.includes('anticon-ellipsis')||s.includes('more-icon')?[icon]:[],
});
const icon={getClientRects:()=>[1],getBoundingClientRect:()=>({x:0,y:0,width:10,height:10}),dispatchEvent:()=>{menu=true;}};
const del={getBoundingClientRect:()=>({x:0,y:0,width:10,height:10}),getClientRects:()=>[1],textContent:'删除',click:()=>{dialog=true;},dispatchEvent:e=>{if(e&&e.type==='click')dialog=true;}};
const doConfirm=()=>{confirmClicks++;dialog=false;menu=false;const idx=cards.findIndex(c=>c.record.fileName===appRecord.fileName);if(idx>=0)removed.push(cards.splice(idx,1)[0].record.fileName);};
const confirm={getBoundingClientRect:()=>({x:0,y:0,width:10,height:10}),getClientRects:()=>[1],textContent:'确 定',disabled:false,click:doConfirm,dispatchEvent:e=>{if(e&&e.type==='click')doConfirm();}};
const modal={getBoundingClientRect:()=>({x:0,y:0,width:400,height:200}),getClientRects:()=>[1],get innerText(){return '确认提示 注意：此操作不可恢复，您确定要删除吗？ 取 消 确 定';},querySelectorAll:()=>[confirm]};
let cards=[{card:null,record:appRecord},{card:null,record:otherRecord}];
for(const item of cards)item.card=makeCard(item.record);
const location={origin:'https://c.liepin.com',pathname:'/resume/edit',href:'https://c.liepin.com/resume/edit'};
const document={
  body:{innerText:''},
  querySelectorAll:s=>{
    // 模拟真实 DOM：组合选择器（新版）与旧版选择器各命中一次，不能同时命中。
    if(s.includes('[class*=')&&s.includes('attachmentCard'))return cards.map(c=>c.card);
    if(s==='.attachment-view-box .resume-card-container')return[];
    if(s==='div,main,section')return[];
    if(s.includes('[class*=')&&s.includes('dropdown-menu-item'))return[];
    if(s==='.ant-dropdown-menu-item')return menu?[del]:[];
    if(s.includes('[class*=')&&s.includes('ant-c-modal-root'))return[];
    if(s==='.ant-modal-content')return dialog?[modal]:[];
    return[];
  },
};
const window={scrollTo:()=>{}};
(async()=>{await vm.runInNewContext(script.replace('UPLOAD_PAYLOAD','{}').replace('UPLOAD_NONCE','"n"'),{
  document,location,window,URL,encodeURIComponent,getComputedStyle:()=>({visibility:'visible'}),
  setTimeout:fn=>fn(),DataTransfer:class{},MouseEvent:class{constructor(type){this.type=type;}},
});
 const result=JSON.parse(new URL(location.href).searchParams.get('payload'));
 const detail=JSON.parse(result.responses[0].payload);
 assert.equal(result.status,'success');
 assert.deepEqual(Array.from(detail.removed),['童双龙-某司-后端-20261010.1']);
 assert.equal(confirmClicks,1,'只确认一次删除');
 assert.equal(detail.skipped[0],'自定义简历','非 App 命名规则的附件不得删除');
 assert.equal(cards.length,1);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node','-e',source],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
