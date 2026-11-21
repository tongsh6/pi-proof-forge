"""执行 Jobs 组件的事件与状态，验证岗位绑定；不替代真实桌面验收。"""

import json
import runpy
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_full_jd_binding_survives_review_and_clears_on_target_change(tmp_path, monkeypatch):
    from tools.sidecar.handlers import jobs
    from tools.sidecar.server import process_request

    fixture = runpy.run_path(str(ROOT/"tests/unit/infra/test_liepin_job_detail.py"))
    respond, requests = fixture["transport"].__wrapped__(monkeypatch)
    monkeypatch.setattr(jobs, "_JOB_LEAD_DIR", tmp_path)
    jobs._write_job_lead_file(tmp_path/"lead-a.yaml", {"id":"lead-a","source":"liepin_official",
        "platform":"liepin","platform_job_id":fixture["RAW_ID"],"platform_job_type":"2","url":fixture["URL"]})
    respond(fixture["page"](title="登录猎聘"))
    failed_detail = process_request({"id":"detail","method":"jobs.fetchLiepinDetail",
                                   "params":{"meta":{"correlation_id":"ui-test"},"job_lead_id":"lead-a"}})["result"]
    assert len(requests) == 1
    # Seed an ordinary saved full official JD through the real handler, with HTTPS scripted.
    jobs._write_job_lead_file(tmp_path/"lead-saved.yaml", {"id":"lead-saved","source":"liepin_official",
        "platform":"liepin","platform_job_id":fixture["RAW_ID"],"platform_job_type":"2",
        "position":"Role-saved","url":fixture["URL"]})
    respond()
    captured = process_request({"id":"saved","method":"jobs.fetchLiepinDetail",
                               "params":{"meta":{"correlation_id":"fixture"},"job_lead_id":"lead-saved"}})["result"]
    assert captured["status"]=="pass" and len(requests)==2
    listing = process_request({"id":"list","method":"jobs.listLeads","params":{"meta":{"correlation_id":"fixture"}}})["result"]
    stored, = [lead for lead in listing["items"] if lead["job_lead_id"]=="lead-saved"]
    assert stored["jd_status"]=="full_unreviewed" and stored["source_jd"]==captured["jd_text"]

    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('./ui/node_modules/typescript');
const hooks = [];
let index = 0, effects = [], tree;
const same = (a, b) => a && b && a.length === b.length && a.every((x, i) => x === b[i]);
const react = {
  useRef(initial) { const slot = index++; if (!hooks[slot]) hooks[slot] = { value: { current: initial } }; return hooks[slot].value; },
  useState(initial) {
    const slot = index++;
    if (!hooks[slot]) hooks[slot] = { value: typeof initial === 'function' ? initial() : initial };
    return [hooks[slot].value, (next) => { hooks[slot].value = typeof next === 'function' ? next(hooks[slot].value) : next; }];
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
const t = (key) => key;
let profiles = ['a', 'b'].map(id => ({ job_profile_id: `profile-${id}`, job_lead_id: `lead-${id}`, title: `Role-${id}`, company: `Company-${id}`, status: 'draft', match_score: 0, evidence_count: 0, resume_count: 0, updated_at: '', business_domain: '', source_jd: '', tone: '', keywords: [], must_have: [], nice_to_have: [], seniority_signal: [] }));
const leads = ['a', 'b'].map(id => ({ job_lead_id: `lead-${id}`, job_profile_id: `profile-${id}`, company: `Company-${id}`, position: `Role-${id}`, source: 'liepin_api', status: 'draft', favorited: false, updated_at: '', platform: 'liepin', platform_job_id: id, jd_status: 'summary_only' }));
const calls = [];
leads[0].salary = '40-70k·15薪';
leads[0].location = '上海-浦东新区';
leads[0].company_size = '1-49人';
leads[0].financing_stage = '天使轮融资';
let failDetail = false, failPrepare = false, driftOnFetch = false, captureSameBody = false;
let holdList = false, releaseList = null, failList = false, revokeOnFailure = false;
const listFilters = [];
const navigations = [];
leads[0].source = 'liepin_official'; leads[0].jd_status = 'complete_reviewed';
const api = {
  prepareLiepinDefault: async (id) => { calls.push(['prepare', id]); return failPrepare ? {status:'blocked',code:'ALREADY_ATTEMPTED',message:'raw private error'} : {status:'ready',run_id:'explicit-run'}; },
  listJobProfiles: async (filters) => {
    listFilters.push(filters.status);
    const response = { items: filters.status ? profiles.filter(p => p.status === filters.status) : profiles };
    if (holdList) {holdList=false;return new Promise(resolve => {releaseList=()=>resolve(response)})}
    if (failList) throw Error('local refresh failed');
    return response;
  },
  listJobLeads: async () => ({ items: leads }),
  fetchLiepinJobDetail: async (id) => {
    calls.push(['fetch', id]);
    if (revokeOnFailure) {
      profiles = profiles.map(p=>p.job_profile_id==='profile-a' ? {...p,native_pdf_delivery:{supported:false,reason:'job_review_required'}} : p);
      return {status:'blocked',code:'JOB_ID_MISMATCH',job_lead_id:id,job_profile_id:'profile-a',jd_text:''};
    }
    if (captureSameBody) {
      return {status:'pass',code:'OK',job_lead_id:id,job_profile_id:'profile-a',
              jd_text:'Full JD lead-a',source_url:'https://www.liepin.com/job/123.shtml',
              source_jd_sha256:'same',jd_status:'complete_reviewed'};
    }
    if (driftOnFetch) {
      profiles = profiles.map(p => p.job_profile_id === 'profile-a' ? {...p,status:'saved_incomplete'} : p);
      return {status:'pass',code:'OK',job_lead_id:id,job_profile_id:'profile-a',
              jd_text:'Full JD lead-a', source_url:'https://www.liepin.com/job/123.shtml',
              source_jd_sha256:'changed',jd_status:'full_unreviewed'};
    }
    return failDetail ? {...JSON.parse(process.argv[1]), message:'raw unsafe message'} : { status: 'pass', code: 'OK', job_lead_id: id, job_profile_id: `profile-${id.slice(-1)}`, jd_text: `Full JD ${id}`, source_url: `https://www.liepin.com/job/${id}.shtml`, source_jd_sha256: 'sha', jd_status: 'full' };
  },
  generateJobProfileDraft: async (payload) => {
    calls.push(['generate', payload]);
    return { draft: { target_role: 'Parsed role', source_jd: payload.jd_text, source_url: payload.source_url, jd_summary: '', keywords: ['Java'], must_have: ['Java'], nice_to_have: [], seniority_signal: [], missing_items: [], job_lead_id: payload.job_lead_id, job_profile_id: 'profile-a' } };
  },
  saveJobProfileDraft: async (payload) => { calls.push(['save', payload]); return { job_profile_id: 'profile-a', job_lead_id: 'lead-a' }; },
};
const exports = {};
const code = ts.transpileModule(fs.readFileSync('ui/src/pages/jobs/index.tsx', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021, jsx: ts.JsxEmit.ReactJSX }
}).outputText;
vm.runInNewContext(code, { exports, require: (name) => {
  if (name === 'react-router-dom') return { useNavigate: () => url => navigations.push(url) };
  if (name === 'react') return react;
  if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
  if (name === 'react-i18next') return { useTranslation: () => ({ t, i18n: { language: 'en' } }) };
  if (name === 'lucide-react') return new Proxy({}, { get: (_, key) => key });
  if (name === '@/components/fit-precheck') return { FitPrecheckBadge: () => null, FitPrecheckRanking: () => null, FitPrecheckDetail: () => null };
  if (name === '@/lib/errors') return { getErrorMessage: (error) => error.message };
  if (name === '@/lib/sidecar/api') return api;
  if (name === '@/lib/ui') return {notify:()=>{},confirmAction:async()=>true,buttonClass:new Proxy({},{get:()=>''})};
  throw new Error(`Unexpected import ${name}`);
}});
function render() { index = 0; effects = []; tree = exports.JobsPage(); for (const effect of effects) effect(); }
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
const button = (label) => nodes(tree).find(node => node.type === 'button' && text(node).includes(label));
const input = (placeholder) => nodes(tree).find(node => node.props?.placeholder === placeholder);
async function click(label) { const node = button(label); assert.ok(node, `Missing button ${label}`); assert.ok(!node.props.disabled, `Disabled ${label}`); node.props.onClick(); await settle(); }
(async () => {
  render(); await settle();
  assert.ok(button('pages.jobs.actions.generateResume'),'完整JD需有原生成入口');assert.ok(button('pages.jobs.actions.generateResume').props.disabled,'草稿不得生成定制版');
  profiles[0].status='active';profiles[0].source_jd='已审核完整JD';render();await settle();await click('pages.jobs.actions.generateResume');assert.equal(navigations.pop(),'/quick-run?job_profile_id=profile-a');
  await click('pages.jobs.tabs.leads');
  assert.ok(text(tree).includes('1-49人 · 天使轮融资'), '线索行显示官方公司规模与融资阶段');
  const sizeFilter = nodes(tree).find(node => node.props?.['data-testid'] === 'lead-size-filter');
  assert.ok(sizeFilter, '线索筛选区提供公司规模下拉');
  assert.deepEqual(nodes(sizeFilter).filter(node => node.type === 'option').map(node => node.props.value), ['', '99', '499'], '规模档位：不限 / 100 人以下 / 500 人以下');
  assert.ok(text(tree).includes('40-70k·15薪'), '展示官方薪资原文');
  assert.ok(text(tree).includes('上海-浦东新区'), '展示官方地区原文');
  assert.ok(text(tree).includes('pages.jobs.leads.notProvided'), '未知待遇地区不推断');
  await click('pages.jobs.liepinPreparation.prepare');
  assert.equal(calls.find(c => c[0] === 'prepare')[1], 'lead-a');
  assert.equal(navigations[0], '/agent-run?run_id=explicit-run');
  failPrepare = true;
  await click('pages.jobs.liepinPreparation.prepare');
  assert.equal(navigations.length, 1);
  assert.ok(text(tree).includes('pages.jobs.liepinPreparation.codes.ALREADY_ATTEMPTED'));
  assert.ok(!text(tree).includes('raw private error'));
  await click('pages.jobs.liepinDetail.fetch');
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value, 'Full JD lead-a');
  assert.ok(text(tree).includes('lead-a'), '显示已绑定线索');
  const oldRefresh=nodes(tree).find(n=>n.type==='button'&&n.props.title==='common.refreshShortcut');
  holdList=true;oldRefresh.props.onClick();await settle();assert.ok(releaseList);
  driftOnFetch = true;
  await click('pages.jobs.liepinDetail.fetch');
  releaseList();await settle();

  driftOnFetch = false;
  await click('pages.jobs.tabs.profiles');
  assert.ok(button('pages.jobs.actions.generateResume').props.disabled,'官方正文变化后的旧 active 不得继续生成');
  assert.ok(text(tree).includes('pages.jobs.status.saved_incomplete'),'需显示后端读回的真实待确认状态');
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value,'Full JD lead-a','保留刚核实的同源正文');
  await click('pages.jobs.tabs.leads');

  await click('pages.jobs.actions.manualDraft');
  const summary = nodes(tree).find(node => node.props?.['aria-label'] === 'pages.jobs.jdDraft.reviewSummary');
  const mustHave = nodes(tree).find(node => node.props?.['aria-label'] === 'pages.jobs.jdDraft.reviewMustHave');
  assert.ok(summary && mustHave);
  assert.equal(summary.props.value, '', '手工稿不伪造摘要');
  assert.equal(calls.filter(c => c[0] === 'generate').length, 0, '手工入口不调用模型');
  summary.props.onChange({target:{value:'测试摘要'}});
  mustHave.props.onChange({target:{value:'JD 中明确的要求'}});
  await settle();
  await click('pages.jobs.actions.generateDraft');
  assert.equal(calls.find(c => c[0] === 'generate')[1].job_lead_id, 'lead-a');
  assert.ok(button('pages.jobs.jdDraft.unbind'), '转到画像标签仍保留同源绑定');
  const keywordInput = () => nodes(tree).find(node => node.props?.['aria-label'] === 'pages.jobs.jdDraft.reviewKeywords');
  keywordInput().props.onChange({ target: { value: 'Java, ' } }); await settle();
  assert.equal(keywordInput().props.value, 'Java, ', '编辑关键词时保留尚未完成的分隔符');
  keywordInput().props.onChange({ target: { value: 'Java, Redis' } }); await settle();
  await click('pages.jobs.actions.saveComplete');
  const save = calls.find(c => c[0] === 'save')[1];
  assert.equal(save.job_lead_id, 'lead-a');
  assert.equal(save.job_profile_id, 'profile-a');
  assert.equal(save.draft.target_role, 'Parsed role', '不能被旧画像编辑器覆盖已解析岗位');
  assert.equal(save.draft.keywords.join(','), 'Java,Redis');
  await click('pages.jobs.tabs.leads');
  await click('pages.jobs.liepinDetail.fetch');
  await click('pages.jobs.actions.generateDraft');
  await click('Role-b');
  assert.equal(button('pages.jobs.actions.saveComplete'), undefined, '切换其他画像必须清旧生成稿');
  assert.equal(button('pages.jobs.jdDraft.unbind'), undefined, '切换其他画像必须解除旧绑定');
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value, '');
  await click('pages.jobs.tabs.leads');
  await click('pages.jobs.liepinDetail.fetch');
  failDetail = true;
  await click('pages.jobs.liepinDetail.fetch');
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value, 'Full JD lead-a', '获取失败保留旧稿');
  assert.ok(!text(tree).includes('raw unsafe message'));
  assert.ok(text(tree).includes('pages.jobs.liepinDetail.reasons.access_required'));
  await click('pages.jobs.jdDraft.unbind');
  assert.equal(button('pages.jobs.jdDraft.unbind'), undefined);
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value, 'Full JD lead-a', '显式解除绑定保留正文供人工导入');
  await click('pages.jobs.jdDraft.clear');
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value, '');
  const previousCalls=calls.length;
  const saved=JSON.parse(process.argv[2]);
  leads.push(saved,{...saved,job_lead_id:'lead-url-only',position:'Role-url-only',source_jd:'https://www.liepin.com/job/42.shtml'},
    {...saved,job_lead_id:'lead-literal',position:'Role-literal',source_jd:saved.source_jd+'<script>literal</script>'},
    {...saved,job_lead_id:'lead-manual',position:'Role-manual',source:'manual'},
    {...saved,job_lead_id:'lead-empty',position:'Role-empty',source_jd:'暂无'});
  await click('pages.jobs.tabs.profiles');
  await click('pages.jobs.tabs.leads');
  // Change the existing filter to reload rows as a fresh local read.
  const refresh=nodes(tree).find(node=>node.type==='button'&&node.props.title==='common.refreshShortcut');
  refresh.props.onClick(); await settle();
  await click('Role-saved');
  const storedBody=()=>nodes(tree).find(node=>node.props?.['data-testid']==='jobs-stored-jd-body');
  assert.equal(storedBody().type,'pre');
  assert.equal(storedBody().props.children,saved.source_jd,'还原持久化岗位原文，不调用详情');
  assert.ok(text(tree).includes('pages.jobs.liepinDetail.storedHint'),'历史依据状态须明确');
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value,'','只读预览不注入编辑器');
  assert.equal(button('pages.jobs.jdDraft.unbind'),undefined,'预览不建立绑定');
  await click('Role-literal');
  assert.equal(storedBody().props.children,saved.source_jd+'<script>literal</script>');
  assert.equal(storedBody().props.dangerouslySetInnerHTML,undefined);
  await click('Role-url-only');assert.equal(storedBody(),undefined,'纯 URL 不能作为已存正文');
  await click('Role-manual');assert.equal(storedBody(),undefined,'不将手工材料冒充官方已存正文');
  await click('Role-empty');assert.equal(storedBody(),undefined,'占位符不是正文');
  await click('Role-b');assert.equal(storedBody(),undefined,'选择摘要行不会继承旧正文');
  assert.equal(calls.length,previousCalls,'查看持久来源不触发读取外站、模型、保存或审批');
  failDetail=false;
  profiles=profiles.map(p=>({...p,status:'active',source_jd:'旧已审核正文'}));
  const refreshLocal=async()=>{nodes(tree).find(n=>n.type==='button'&&n.props.title==='common.refreshShortcut').props.onClick();await settle()};
  await click('pages.jobs.tabs.profiles');
  await refreshLocal();
  const statusFilter=nodes(tree).find(n=>n.type==='select' && text(n).includes('pages.jobs.filters.allStatuses'));
  statusFilter.props.onChange({target:{value:'active'}});await settle();
  nodes(tree).find(n=>n.type==='form'&&text(n).includes('pages.jobs.filters.apply')).props.onSubmit({preventDefault(){}});
  await settle();
  await click('pages.jobs.tabs.leads');
  await click('Role-a');
  const reads=listFilters.length;
  captureSameBody=true;await click('pages.jobs.liepinDetail.fetch');captureSameBody=false;
  assert.ok(listFilters.length>reads && listFilters.at(-1)==='active','同正文亦读回最新官方凭据与档案');
  driftOnFetch=true;await click('pages.jobs.liepinDetail.fetch');driftOnFetch=false;
  await click('pages.jobs.tabs.profiles');
  assert.ok(button('pages.jobs.actions.generateResume').props.disabled);
  assert.ok(!button('Role-a') && button('Role-b'));
  assert.equal(input('pages.jobs.jdDraft.jdPlaceholder').props.value,'Full JD lead-a','当前筛选排除旧档案不清除同源正文');
  assert.equal(listFilters.at(-1),'active');

  profiles=profiles.map(p=>({...p,status:'active',source_jd:'旧已审核正文'}));await refreshLocal();
  await click('Role-a');assert.ok(!button('pages.jobs.actions.generateResume').props.disabled);
  await click('pages.jobs.tabs.leads');await click('Role-a');
  failList=true;driftOnFetch=true;await click('pages.jobs.liepinDetail.fetch');driftOnFetch=false;
  await click('pages.jobs.tabs.profiles');
  assert.ok(button('pages.jobs.actions.generateResume').props.disabled,'本地读回失败亦不得重开已撤审核的入口');
  assert.ok(input('pages.jobs.jdDraft.jdPlaceholder').props.value==='Full JD lead-a');
  failList=false;
  profiles=profiles.map(p=>({...p,status:'active',source_jd:'旧已审核正文'}));await refreshLocal();
  await click('Role-a');assert.ok(!button('pages.jobs.actions.generateResume').props.disabled);
  await click('pages.jobs.tabs.leads');await click('Role-a');
  const beforeFailureReads=listFilters.length;
  failDetail=true;await click('pages.jobs.liepinDetail.fetch');failDetail=false;
  await click('pages.jobs.tabs.profiles');
  assert.ok(!button('pages.jobs.actions.generateResume').props.disabled,'暂时无法读详情不能撤当前可用档案');
  assert.equal(listFilters.length,beforeFailureReads);
  await click('pages.jobs.tabs.leads');revokeOnFailure=true;await click('pages.jobs.liepinDetail.fetch');revokeOnFailure=false;
  assert.ok(text(tree).includes('pages.jobs.liepinDetail.codes.JOB_ID_MISMATCH'));
  await click('pages.jobs.tabs.profiles');
  assert.ok(button('Role-a'),'历史审批档案仍可读');
  const staleCta=button('pages.jobs.actions.generateResume');
  assert.ok(staleCta.props.disabled,'撤销来源的历史 active 档案不得再生成');
  const previousNavigation=navigations.length;
  staleCta.props.onClick();assert.equal(navigations.length,previousNavigation);
  profiles=profiles.map(p=>({...p,native_pdf_delivery:{supported:true,reason:''}}));await refreshLocal();
  await click('Role-a');assert.ok(!button('pages.jobs.actions.generateResume').props.disabled);
  await click('pages.jobs.tabs.leads');await click('Role-a');
  holdList=true;await refreshLocal();
  failList=true;revokeOnFailure=true;await click('pages.jobs.liepinDetail.fetch');revokeOnFailure=false;
  releaseList();await settle();
  await click('pages.jobs.tabs.profiles');
  assert.ok(!button('Role-a')&&button('Role-b'),'未读回的单一旧档案撤下、不撤其他档案');
  assert.ok(button('pages.jobs.actions.generateResume').props.disabled,'本地读回失败、旧读取迟到都不恢复撤销的来源');



})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps(failed_detail), json.dumps(stored)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
