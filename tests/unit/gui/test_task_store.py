"""全局长任务 store：开始后为 running，完成后保留结果，失败记录原因，清除后不再显示。"""
import subprocess
from pathlib import Path


def test_task_store_tracks_running_done_and_error():
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const zustand={create(init){let state;const set=p=>{state={...state,...(typeof p==='function'?p(state):p)}};const get=()=>state;state=init(set,get);const hook=sel=>sel?sel(state):state;hook.getState=get;hook.setState=set;return hook;}};
const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/state/task-store.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports,Date,require:n=>{if(n==='zustand')return zustand;throw Error(n)}});
const {useTaskStore}=exports;
const s=()=>useTaskStore.getState();
s().start({kind:'quickRun',label:'快速运行 · 目标A',path:'/quick-run',profileId:'jp1'});
assert.equal(s().tasks.quickRun.status,'running');assert.ok(s().tasks.quickRun.startedAt>0);
s().finish('quickRun',{run_id:'qr1',status:'DONE'});
assert.equal(s().tasks.quickRun.status,'done');assert.equal(s().tasks.quickRun.result.run_id,'qr1');assert.equal(s().tasks.quickRun.profileId,'jp1');
s().start({kind:'quickRun',label:'x',path:'/quick-run'});s().fail('quickRun','boom');
assert.equal(s().tasks.quickRun.status,'error');assert.equal(s().tasks.quickRun.detail,'boom');
s().clear('quickRun');assert.equal(s().tasks.quickRun,undefined);
s().finish('quickRun');assert.equal(s().tasks.quickRun,undefined,'没有任务时 finish 不应凭空创建');
'''
    r=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stdout+r.stderr
