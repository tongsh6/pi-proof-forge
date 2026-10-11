"""执行真实设置页组件，验证本地凭据状态；只使用合成状态，不访问用户凭据。"""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_local_credential_errors_keep_delete_available_and_never_claim_success():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('./ui/node_modules/typescript');
const hooks = [];
let index = 0, effects = [], tree;
const same = (a, b) => a && b && a.length === b.length && a.every((x, i) => x === b[i]);
const react = {
  useState(initial) {
    const slot = index++;
    if (!hooks[slot]) hooks[slot] = { value: typeof initial === 'function' ? initial() : initial };
    return [hooks[slot].value, next => { hooks[slot].value = typeof next === 'function' ? next(hooks[slot].value) : next; }];
  },
  useMemo(fn, deps) {
    const slot = index++;
    if (!hooks[slot] || !same(hooks[slot].deps, deps)) hooks[slot] = { value: fn(), deps };
    return hooks[slot].value;
  },
  useCallback(fn, deps) { return react.useMemo(() => fn, deps); },
  useEffect(fn, deps) {
    const slot = index++;
    if (!hooks[slot] || !same(hooks[slot].deps, deps)) { hooks[slot] = { deps }; effects.push(fn); }
  },
};
const messages = JSON.parse(fs.readFileSync('ui/src/i18n/zh.json', 'utf8'));
const t = (key, opts = {}) => key.split('.').reduce((value, part) => value?.[part], messages) ?? opts.defaultValue ?? key;
const prefix = 'pages.systemSettings.liepinApi.';
let auth = {
  configured: false, saved: true, state: 'error', code: 'CREDENTIAL_STORAGE_ERROR',
  last_checked_at: '', last_error: '合成本地凭据读取失败', scope: 'read_only',
  storage: 'local_file', storage_path: '/synthetic/credentials/liepin-token',
};
let nextAuth = auth, thrownError = null;
const calls = [];
const api = {
  getSettings: async () => ({ channels: [], liepin_api: auth, llm_config: { provider: 'lm_studio', model: 'local', base_url: 'http://localhost/v1', timeout: 120, temperature: .2, api_key: { configured: false } } }),
  updateLiepinCredential: async payload => {
    calls.push(payload);
    if (thrownError) throw thrownError;
    auth = nextAuth;
    return { auth };
  },
};
const exports = {};
const code = ts.transpileModule(fs.readFileSync('ui/src/pages/system-settings/index.tsx', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021, jsx: ts.JsxEmit.ReactJSX }
}).outputText;
vm.runInNewContext(code, { exports, require: name => {
  if (name === 'react-router-dom') return { useSearchParams: () => [{ get: () => null }] };
  if (name === 'react') return react;
  if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
  if (name === 'react-i18next') return { useTranslation: () => ({ t, i18n: { language: 'zh' } }) };
  if (name === 'lucide-react') return new Proxy({}, { get: (_, key) => key });
  if (name === '@/lib/errors') return { getErrorMessage: error => error.message };
  if (name === '@/lib/sidecar/api') return api;
  if (name === '@/lib/ui') return {notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};
  throw new Error(`Unexpected import ${name}`);
}});
function render() { index = 0; effects = []; tree = exports.SystemSettingsPage(); for (const effect of effects) effect(); }
async function settle() { for (let i = 0; i < 5; i++) { await new Promise(resolve => setImmediate(resolve)); render(); } }
function nodes(node) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(nodes);
  return [node, ...nodes(node.props?.children)];
}
function text(node) {
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(text).join(' ');
  return text(node?.props?.children || '');
}
const button = key => nodes(tree).find(node => node.type === 'button' && text(node).trim() === t(prefix + key));
const tokenInput = () => nodes(tree).find(node => node.props?.placeholder === t(prefix + 'tokenPlaceholder'));
async function click(key) { const node = button(key); assert.ok(node, `Missing button ${key}`); assert.ok(!node.props.disabled, `Disabled ${key}`); node.props.onClick(); await settle(); }
async function reload() { nodes(tree).find(node => node.type === 'button' && text(node).includes(t('common.refresh'))).props.onClick(); await settle(); }
(async () => {
  render(); await settle();
  assert.ok(text(tree).includes(auth.storage_path), '用户可看到保存路径');
  assert.ok(text(tree).includes('明文') && text(tree).includes('0600') && text(tree).includes('重启'), '说明本机保存边界');
  assert.equal(button('clear').props.disabled, false, '读取失败仍能删除保存项');
  assert.equal(button('check').props.disabled, true);
  assert.equal(button('readResume').props.disabled, true);
  assert.ok(text(tree).includes('合成本地凭据读取失败'), '显示后端固定安全错误，不把读取失败伪装为未配置');
  nextAuth = { ...auth, last_error: '合成本地凭据删除失败' };
  await click('clear');
  assert.ok(text(tree).includes('合成本地凭据删除失败'));
  assert.equal(button('clear').props.disabled, false, '删除失败仍可重试');
  assert.equal(calls.at(-1).action, 'clear');
  nextAuth = { ...auth, saved: false, configured: false, state: 'unconfigured', code: 'AUTH_REQUIRED', last_error: '' };
  await click('clear');
  assert.equal(button('clear').props.disabled, true, '成功删除后不再显示保存项');
  assert.ok(!text(tree).includes('合成本地凭据删除失败'));
  auth = { ...auth, saved: true, configured: false, state: 'unconfigured', code: 'AUTH_REQUIRED', last_error: '' };
  await reload();
  assert.equal(button('clear').props.disabled, false, '仅保存项存在时可删除');
  assert.equal(button('check').props.disabled, true, '文件存在不等于 Token 已加载');
  auth = { ...auth, saved: false, configured: false, state: 'error', code: 'CREDENTIAL_STORAGE_ERROR', last_error: '合成路径读取失败' };
  await reload();
  assert.equal(button('clear').props.disabled, false, '无法确定文件存在时也可删除');
  tokenInput().props.onChange({ target: { value: 'synthetic-token-never-persisted' } }); await settle();
  nextAuth = { ...auth, last_error: '合成本地凭据保存失败' };
  await click('set');
  assert.equal(tokenInput().props.value, '', '提交后不保留 Token');
  assert.ok(text(tree).includes('合成本地凭据保存失败'));
  assert.equal(button('check').props.disabled, true, '失败不能声称新 Token 已配置');
  thrownError = new Error('uncontrolled RPC body: synthetic-secret-must-not-be-displayed');
  await click('clear');
  assert.ok(!text(tree).includes('synthetic-secret-must-not-be-displayed'), '未受控传输异常不能回显密钥');
  assert.ok(text(tree).includes(t(prefix + 'requestError')), '传输错误使用固定安全提示');
  thrownError = null;
  auth = { ...auth, configured: true, saved: true, state: 'unverified', code: 'OK', last_error: '' };
  await reload();
  assert.equal(tokenInput().props.value, '', '自动读取后仍不回显 Token');
  assert.equal(button('check').props.disabled, false);
  assert.equal(button('readResume').props.disabled, false);
  auth = { ...auth, saved: false };
  await reload();
  assert.equal(button('clear').props.disabled, false, '仅内存已配置时也可删除');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
