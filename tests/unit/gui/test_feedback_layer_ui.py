"""全局反馈层：Toast 去重/上限/错误需手动关闭，确认框按用户决定解析，并且同一时刻只保留一个。"""
import subprocess
from pathlib import Path


def test_feedback_store_toasts_and_confirmations():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
// 最小 zustand：create(init) 返回带 getState/setState 的 hook 函数。
const zustand={create(init){let state;const set=p=>{state={...state,...(typeof p==='function'?p(state):p)}};const get=()=>state;state=init(set,get);const hook=sel=>sel?sel(state):state;hook.getState=get;hook.setState=set;return hook;}};
const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/ui.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports,Date,Promise,require:n=>{if(n==='zustand')return zustand;throw Error(n)}});
const {notify,confirmAction,useFeedbackStore}=exports;
(async()=>{
  const first=notify('success','已保存');
  assert.equal(useFeedbackStore.getState().toasts.length,1);
  assert.equal(useFeedbackStore.getState().toasts[0].duration,5000,'成功通知自动消失');
  assert.equal(notify('success','已保存'),first,'相同通知去重');
  notify('error','失败','原因');
  assert.equal(useFeedbackStore.getState().toasts.at(-1).duration,0,'错误通知需手动关闭');
  for(let i=0;i<6;i++)notify('info','n'+i);
  assert.equal(useFeedbackStore.getState().toasts.length,4,'最多保留 4 条');
  useFeedbackStore.getState().dismissToast(useFeedbackStore.getState().toasts[0].id);
  assert.equal(useFeedbackStore.getState().toasts.length,3);

  const p1=confirmAction({title:'删除？',tone:'danger'});
  assert.ok(useFeedbackStore.getState().confirm,'确认框应打开');
  useFeedbackStore.getState().settleConfirm(true);
  assert.equal(await p1,true);
  assert.equal(useFeedbackStore.getState().confirm,null,'确认后关闭');
  const p2=confirmAction({title:'A'});
  const p3=confirmAction({title:'B'});
  assert.equal(await p2,false,'被新确认框取代的旧请求按取消处理');
  useFeedbackStore.getState().settleConfirm(false);
  assert.equal(await p3,false);
  useFeedbackStore.getState().settleConfirm(true);
  assert.equal(useFeedbackStore.getState().confirm,null,'没有待确认请求时 settle 不报错');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
