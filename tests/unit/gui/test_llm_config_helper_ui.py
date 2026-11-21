"""执行共享 LLM/keyless 判定 helper 的真实行为，避免各页面各自复制 provider 语义。"""
import subprocess
from pathlib import Path


def test_llm_config_helper_keyless_and_configured_semantics():
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('./ui/node_modules/typescript');
const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/lib/llmConfig.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText,{exports,URL});
const {isKeylessProvider,isLlmConfigured,isLlmSecretConfigured,STRATA_UNIFIED_BASE_URL}=exports;
assert.equal(STRATA_UNIFIED_BASE_URL,'http://127.0.0.1:47831/v1','Strata App 统一推理后台只有唯一入口');
const secret=(configured=false)=>({configured,masked:configured,updated_at:'',source:configured?'saved':'none'});
const config=(provider,model,configured=false)=>({provider,model,base_url:null,timeout:60,temperature:.2,api_key:secret(configured)});
assert.equal(isKeylessProvider('lm_studio'),true,'LM Studio 无密钥可用');
assert.equal(isKeylessProvider('strata'),true,'Strata 本地服务无密钥可用');
assert.equal(isKeylessProvider('openai'),false);
assert.equal(isKeylessProvider('deepseek'),false);
assert.equal(isKeylessProvider(null),false);
assert.equal(isKeylessProvider(undefined),false);
assert.equal(isLlmConfigured(config('strata','qwen3.8-flash-next-q2_0')),true,'Strata 有模型且无密钥即视为已配置');
assert.equal(isLlmConfigured(config('lm_studio','local-model')),true,'LM Studio 有模型且无密钥即视为已配置');
assert.equal(isLlmConfigured(config('openai','gpt-4')),false,'云端 provider 无密钥不算已配置');
assert.equal(isLlmConfigured(config('deepseek','deepseek-flash')),false);
assert.equal(isLlmConfigured(config('strata','')),false,'无模型不算已配置');
assert.equal(isLlmConfigured(config('strata','   ')),false,'空白模型不算已配置');
assert.equal(isLlmConfigured(config('openai','gpt-4',true)),true,'已保存密钥优先于 provider 语义');
assert.equal(isLlmConfigured(null),false);
assert.equal(isLlmConfigured(undefined),false);
assert.equal(isLlmSecretConfigured(config('strata','')),true,'keyless provider 的密钥状态按可用处理');
assert.equal(isLlmSecretConfigured(config('lm_studio','')),true);
assert.equal(isLlmSecretConfigured(config('openai','gpt-4')),false);
assert.equal(isLlmSecretConfigured(config('openai','gpt-4',true)),true);
assert.equal(isLlmSecretConfigured(config('deepseek','deepseek-flash',true)),true);
assert.equal(isLlmSecretConfigured(null),false);
for(const base_url of ['http://127.0.0.1:8000/v1','https://localhost/v1','http://[::1]:8000/v1']){
 const c={...config('openai_compatible','local'),base_url};
 assert.equal(isLlmConfigured(c),true,base_url); assert.equal(isLlmSecretConfigured(c),true,base_url);
 assert.equal(isLlmConfigured({...c,model:''}),false);
}
for(const base_url of ['', 'http://localhost.evil/v1','http://127.0.0.1.evil/v1','http://user@localhost/v1','http://localhost:bad/v1','http://localhost:65536/v1','http://localhost:/v1','http://localhost:0/v1','ftp://localhost/v1','//localhost/v1','http://127.1/v1','http://2130706433/v1','http://[::1/v1','http://remote.example/v1','http://localhost'+String.fromCharCode(92)+'@evil/v1','http://local'+String.fromCharCode(10)+'host/v1']){
 const c={...config('openai_compatible','local'),base_url};
 assert.equal(isLlmConfigured(c),false,base_url); assert.equal(isLlmSecretConfigured(c),false,base_url);
}
assert.equal(isLlmConfigured({...config('openai_compatible','',true),base_url:'http://127.0.0.1:8000/v1'}),false,'empty model remains unavailable even with a key');
console.log('llmConfig helper OK');
'''
    result = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
