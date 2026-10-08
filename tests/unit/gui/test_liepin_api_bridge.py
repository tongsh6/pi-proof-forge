"""执行真实 TypeScript RPC 适配层，仅替换桌面 invoke 边界。"""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_liepin_read_only_rpc_requests_and_results():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('./ui/node_modules/typescript');
const requests = [];
const nativeCalls = [];
let failOpening = false;
const auth = {
  configured: true, state: 'valid', code: 'OK', last_checked_at: '2026-09-28',
  last_error: '', scope: 'read_only', storage: 'local_file',
  storage_path: '/synthetic/credentials/liepin-token', saved: true
};
let nextResult = { meta: {}, auth };
const cache = new Map();
function load(filename) {
  if (cache.has(filename)) return cache.get(filename);
  const exports = {};
  cache.set(filename, exports);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021 }
  }).outputText;
  const requireLocal = (specifier) => {
    if (specifier === '@tauri-apps/api/core') return { invoke: async (command, payload) => {
      if (command === 'open_liepin_authorization') {
        nativeCalls.push({ command, payload });
        if (failOpening) throw new Error('OPEN_AUTHORIZATION_FAILED');
        return undefined;
      }
      assert.equal(command, 'sidecar_request');
      const request = JSON.parse(payload.request);
      requests.push(request);
      return JSON.stringify({ jsonrpc: '2.0', id: request.id, result: nextResult });
    }};
    const target = specifier.startsWith('@/')
      ? path.resolve('ui/src', specifier.slice(2))
      : path.resolve(path.dirname(filename), specifier);
    return load(target + '.ts');
  };
  vm.runInNewContext(code, {
    exports, require: requireLocal, window: { __TAURI_INTERNALS__: {} },
  }, { filename });
  return exports;
}
(async () => {
  const api = load(path.resolve('ui/src/lib/sidecar/api.ts'));
  assert.equal(typeof api.updateLiepinCredential, 'function', '缺少官方凭据 RPC 适配');
  assert.equal(typeof api.getLiepinResume, 'function', '缺少平台简历只读适配');
  assert.equal(typeof api.searchLiepinJobs, 'function', '缺少在线岗位搜索适配');
  assert.equal(typeof api.openLiepinAuthorization, 'function', '缺少原生浏览器打开能力');
  await api.openLiepinAuthorization();
  assert.deepEqual(nativeCalls.map(x => x.command), ['open_liepin_authorization']);
  assert.equal(nativeCalls[0].payload, undefined);
  failOpening = true;
  await assert.rejects(api.openLiepinAuthorization(), /OPEN_AUTHORIZATION_FAILED/);
  const saved = await api.updateLiepinCredential({ action: 'set', token: 'test-session-secret' });
  assert.equal(saved.auth.state, 'valid');
  await api.updateLiepinCredential({ action: 'check' });
  await api.updateLiepinCredential({ action: 'clear' });
  nextResult = { meta: {}, auth, status: 'pass', code: 'OK', message: '', resume_text: '<b>纯文本</b>' };
  assert.equal((await api.getLiepinResume()).resume_text, '<b>纯文本</b>');
  nextResult = { meta: {}, auth, status: 'pass', code: 'OK', message: '', items: [], received_count: 0, imported_count: 0, page: 0 };
  const empty = await api.searchLiepinJobs('后端');
  assert.equal(empty.status, 'pass');
  assert.equal(empty.received_count, 0);
  nextResult = { ...nextResult, status: 'blocked', code: 'RATE_LIMITED', message: '稍后重试', page: 2 };
  const blocked = await api.searchLiepinJobs('架构', 2);
  assert.equal(blocked.status, 'blocked');
  assert.equal(blocked.code, 'RATE_LIMITED');
  assert.equal(typeof api.fetchLiepinJobDetail, 'function', '缺少完整 JD 读取适配');
  nextResult = { meta: {}, status: 'pass', code: 'OK', message: '', job_lead_id: 'lead-a', job_profile_id: 'profile-a', jd_text: '完整岗位描述', source_url: 'https://www.liepin.com/job/123.shtml', source_jd_sha256: 'digest', jd_status: 'full' };
  const detail = await api.fetchLiepinJobDetail('lead-a');
  assert.equal(detail.jd_text, '完整岗位描述');
  assert.equal(detail.job_profile_id, 'profile-a');
  const draft = { target_role: '后端', source_jd: detail.jd_text, jd_summary: '', keywords: [], must_have: [], nice_to_have: [], seniority_signal: [], job_lead_id: 'lead-a', job_profile_id: 'profile-a' };
  nextResult = { meta: {}, draft };
  await api.generateJobProfileDraft({ jd_text: detail.jd_text, source_url: detail.source_url, job_lead_id: 'lead-a' });
  await api.saveJobProfileDraft({ draft, save_mode: 'complete', review: { decision: 'approved' }, job_lead_id: 'lead-a', job_profile_id: 'profile-a' });
  assert.deepEqual(requests.map(({ method, params: { meta, ...params } }) => ({ method, params })), [
    { method: 'settings.liepinCredential', params: { action: 'set', token: 'test-session-secret' } },
    { method: 'settings.liepinCredential', params: { action: 'check' } },
    { method: 'settings.liepinCredential', params: { action: 'clear' } },
    { method: 'settings.liepinResume', params: {} },
    { method: 'jobs.searchLiepin', params: { keyword: '后端', page: 0 } },
    { method: 'jobs.searchLiepin', params: { keyword: '架构', page: 2 } },
    { method: 'jobs.fetchLiepinDetail', params: { job_lead_id: 'lead-a' } },
    { method: 'jobs.generateProfileDraft', params: { jd_text: '完整岗位描述', source_url: 'https://www.liepin.com/job/123.shtml', job_lead_id: 'lead-a' } },
    { method: 'jobs.saveProfileDraft', params: { draft, save_mode: 'complete', review: { decision: 'approved' }, job_lead_id: 'lead-a', job_profile_id: 'profile-a' } },
  ]);
  assert.ok(requests.every((request) => request.params.meta.correlation_id));
  assert.ok(!JSON.stringify(requests.slice(1)).includes('test-session-secret'));
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
