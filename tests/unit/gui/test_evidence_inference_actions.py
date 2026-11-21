"""执行真实页面回调，验证逐条/批量确认的指纹接续与部分成功状态。"""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["single", "batch", "partial", "switch"])
def test_inference_confirmation_tracks_each_success(mode):
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('./ui/node_modules/typescript');
const mode=process.argv[1];
let hooks=[],cursor=0,effects=[],tree;
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
const react={useState(v){let i=cursor++;if(!hooks[i])hooks[i]={v:typeof v==='function'?v():v};return[hooks[i].v,n=>hooks[i].v=typeof n==='function'?n(hooks[i].v):n]},
useMemo(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={v:fn(),deps};return hooks[i].v},
useCallback(fn,deps){return react.useMemo(()=>fn,deps)},useRef(v){return react.useMemo(()=>({current:v}),[])},
useEffect(fn,deps){let i=cursor++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}};
const card={evidence_id:'A',title:'售后服务',time_range:'',role_scope:'',context:'背景',actions:['行动'],results:['成果'],stack:['Java'],tags:[],artifacts:[],source_material_ids:['mat'],source_documents:[]};
let sha='sha0',inferenceCalls=0,failOnce=mode==='partial',release;
const second={...card,evidence_id:'B',title:'其他项目'};
const candidates=['time_range','role_scope'].map(field=>({field,value:field==='time_range'?'2023':'参与改造',level:'L3',confidence:.8,candidate_hash:field,evidence:[]}));
let pending=[...candidates],calls=[];
const api={
getSettings:async()=>({evidence_inference:{enabled:true}}),
listEvidence:async()=>({items:[card,second].map(c=>({...c,status:'saved_eligible',updated_at:''}))}),
listEvidenceMaterialSources:async()=>({items:[]}),getEvidence:async id=>({evidence:id==='B'?second:card}),
reconcileEvidence:async()=>({items:[{evidence_id:'A',missing_fields:[],untraceable_results:[],verbatim_candidates:[],date_hints:[],possible_duplicates:[],has_source:true}],summary:{total:1}}),
inferEvidenceFields:async()=>{inferenceCalls++;return{enabled:true,cards:[{card_id:'A',card_sha256:sha,candidates:[...pending]}],summary:{requested:1,candidates:pending.length}}},
confirmEvidenceInference:async p=>{calls.push({...p});assert.equal(p.card_sha256,sha,'下一字段必须使用上一次返回的新指纹');
if(mode==='switch'&&p.field==='time_range')await new Promise(resolve=>{release=resolve});
if(failOnce&&p.field==='role_scope'){failOnce=false;throw Error('暂时失败')}
pending=pending.filter(c=>c.field!==p.field);sha='sha'+(2-pending.length);
return{status:'accepted',card_sha256:sha,evidence_id:'A',field:p.field}}};
const jsx=(type,props)=>typeof type==='function'?type(props||{}):({type,props:props||{}}),runtime={jsx,jsxs:jsx},exports={};
const baseRequire=n=>n==='react'?react:n==='react/jsx-runtime'?runtime:n==='react-i18next'?{useTranslation:()=>({t:k=>k})}:n==='lucide-react'?new Proxy({},{get:(_,k)=>k}):n==='@/lib/errors'?{getErrorMessage:String}:n==='@/lib/ui'?{notify:()=>{},confirmAction:async()=>true}:n==='react-router-dom'?{useSearchParams:()=>[{get:()=>null}],useNavigate:()=>()=>{}}:n==='@/lib/sidecar/api'?api:undefined;
const nodePath=require('node:path'),moduleCache={};
function loadPageModule(spec,fromDir){const abs=spec.startsWith('@/')?nodePath.resolve('ui/src',spec.slice(2)):nodePath.resolve(fromDir,spec);let file=abs;for(const ext of['','.tsx','.ts','.js']){if(fs.existsSync(abs+ext)){file=abs+ext;break}}if(moduleCache[file])return moduleCache[file];const out={};moduleCache[file]=out;const dir=nodePath.dirname(file),code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText;vm.runInNewContext(code,{exports:out,console,Intl,Date,Map,Set,URLSearchParams,require:n=>resolvePageModule(n,dir)});return out}
function resolvePageModule(spec,fromDir){const pageRoot=nodePath.resolve('ui/src/pages/evidence'),abs=spec.startsWith('@/')?nodePath.resolve('ui/src',spec.slice(2)):nodePath.resolve(fromDir,spec),pageSpec='./'+nodePath.relative(pageRoot,abs).split(nodePath.sep).join('/'),stub=baseRequire(pageSpec);if(stub!==undefined)return stub;if(spec.startsWith('.')||spec.startsWith('@/pages/'))return loadPageModule(spec,fromDir);const hit=baseRequire(spec);if(hit!==undefined)return hit;throw Error(spec)}
const pageRequire=n=>resolvePageModule(n,'ui/src/pages/evidence');
vm.runInNewContext(ts.transpileModule(fs.readFileSync('ui/src/pages/evidence/index.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
exports,console,Intl,Date,Set,Map,require:pageRequire});
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
async function settle(){for(let i=0;i<12;i++){cursor=0;tree=exports.EvidencePage();let e=effects;effects=[];e.forEach(f=>f());await Promise.resolve();await Promise.resolve()}}
const byTest=id=>nodes(tree).find(n=>n.props['data-testid']===id);
const accept=()=>nodes(tree).find(n=>n.type==='button'&&text(n).trim()==='pages.evidence.reconcile.inference.accept');
(async()=>{
await settle();byTest('evidence-inference-run').props.onClick();await settle();
if(mode==='single'){accept().props.onClick();await settle();assert.equal(nodes(tree).filter(n=>n.props['data-testid']==='evidence-inference-candidate').length,1);accept().props.onClick()}
else byTest('evidence-inference-batch').props.onClick();
await settle();
if(mode==='switch'){
const other=()=>nodes(tree).find(n=>n.type==='tr'&&text(n).includes('其他项目'));
other().props.onClick();await settle();release();await settle();
assert.equal(other().props['aria-selected'],true,'完成批量确认不能拉回开始时选中的卡');
}
if(mode==='partial'){
assert.equal(nodes(tree).filter(n=>n.props['data-testid']==='evidence-inference-candidate').length,1,'失败后仅剩未完成项');
byTest('evidence-inference-batch').props.onClick();await settle();
assert.deepEqual(calls.map(x=>x.field),['time_range','role_scope','role_scope'],'不能重放已接受的时间字段');
}
assert.equal(pending.length,0);
assert.equal(nodes(tree).filter(n=>n.props['data-testid']==='evidence-inference-candidate').length,0);
assert.equal(inferenceCalls,1,'确认后刷新不能隐式重新推断');
const summary=nodes(tree).find(n=>n.type==='button'&&text(n).includes('pages.evidence.summary.inference'));
assert.ok(text(summary).includes('0'),'汇总计数同步归零');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(
        ["node", "-e", script, mode], cwd=Path(__file__).resolve().parents[3],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# These cases use real React, the typed API and Tauri transport in Chrome.
# Only the native RPC boundary is synthetic; the original four Node controls stay above.
INFERENCE_ENTRY = r"""
import React from "react";
import {createRoot} from "react-dom/client";
import {MemoryRouter} from "react-router-dom";
import {mockIPC} from "@tauri-apps/api/mocks";
import i18n from "/src/i18n/index.ts";
import {EvidencePage} from "/src/pages/evidence/index.tsx";
import {SystemSettingsPage} from "/src/pages/system-settings/index.tsx";
await i18n.changeLanguage("en");

let root;
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const waitFor = async predicate => {
  for (let i = 0; i < 200; i++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error("Evidence component did not reach the interaction boundary");
};
const byTest = id => document.querySelector('[data-testid="' + id + '"]');
const click = element => {
  if (!element || element.disabled) throw new Error("Missing operable evidence control");
  element.click();
};
const edit = (element, value) => {
  if (!element || element.readOnly) throw new Error("Missing editable candidate");
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, value);
  element.dispatchEvent(new Event("input", {bubbles: true}));
};
const button = (row, key) => Array.from(row.querySelectorAll("button"))
  .find(item => item.textContent.trim() === i18n.t("pages.evidence.reconcile.inference." + key));

window.runInferenceCase = async ({mode}) => {
  if (root) root.unmount();
  document.getElementById("root").replaceChildren();
  const first = {field: "time_range", value: "2023", level: "L2", precision: "year",
    confidence: .8, candidate_hash: "a".repeat(64), evidence: []};
  const second = {...first, value: "2024", candidate_hash: "b".repeat(64)};
  const role = {field: "role_scope", value: "负责合成项目接口设计与联调", level: "L3",
    confidence: .8, candidate_hash: "c".repeat(64), evidence: []};
  const card = id => ({evidence_id: id, title: id === "A" ? "合成项目甲" : "合成项目乙",
    time_range: "", role_scope: "", context: "合成项目的完整背景。",
    actions: ["设计接口并完成跨系统联调。"], results: ["完成接口文档交付。"],
    stack: ["Python"], tags: [], artifacts: [], source_material_ids: ["synthetic"],
    source_documents: [], source_sha256: "0".repeat(64),
    review_decision: "approved", candidate_pool_eligible: true});
  const cards = {A: card("A"), B: card("B")};
  const sameField = ["second_accept", "second_reject", "edited"].includes(mode);
  const group = mode === "partial_other_card" ? [
    {card_id: "A", card_sha256: "0".repeat(64), candidates: [first]},
    {card_id: "B", card_sha256: "0".repeat(64), candidates: [role]},
  ] : [{card_id: "A", card_sha256: "0".repeat(64),
    candidates: sameField ? [first, second, role] : [first, role]}];
  const settings = {
    meta: {correlation_id: "synthetic-inference-ui"},
    gate_policy: {gate_mode: "manual", delivery_mode: "manual", batch_review: false},
    exclusion_list: [], excluded_legal_entities: [], material_source_roots: [],
    channels: [], liepin_api: {configured: false, state: "unconfigured"},
    evidence_inference: {enabled: true},
    llm_config: {provider: "openai_compatible", model: "synthetic-model",
      base_url: "https://synthetic.invalid/v1", thinking_enabled: null,
      thinking_effort: "high", configured_providers: [], api_key: {configured: false}},
  };
  const calls = [], reads = {A: 0, B: 0};
  let inferenceCalls = 0, reconcileCalls = 0, listCalls = 0, settingsReads = 0;
  let releaseInference;
  let readsAtFailure = null, reconcileAtFailure = null, failureCount = 0;
  const result = (request, value) => JSON.stringify({jsonrpc: "2.0", id: request.id,
    result: {meta: {correlation_id: "synthetic-inference-ui"}, ...value}});
  const failure = request => {
    failureCount++;
    readsAtFailure = structuredClone(reads);
    reconcileAtFailure = reconcileCalls;
    return JSON.stringify({jsonrpc: "2.0", id: request.id, error: {
      code: "VALIDATION_ERROR", message: "Synthetic candidate state publication failed",
      details: {retryable: false},
    }});
  };
  const write = (id, field, value, level, sha) => {
    cards[id][field] = value;
    cards[id][field + "_provenance"] = {level};
    cards[id].source_sha256 = sha;
    cards[id].review_decision = "pending";
    cards[id].candidate_pool_eligible = false;
  };
  mockIPC((command, args) => {
    if (command !== "sidecar_request") throw new Error("Unexpected native call: " + command);
    const request = JSON.parse(args.request);
    const p = request.params || {};
    if (request.method === "evidence.list") {
      listCalls++;
      return result(request, {items: Object.values(cards).map(card => ({
        ...card, status: card.candidate_pool_eligible ? "saved_eligible" : "draft", updated_at: "",
      })), next_cursor: null});
    }
    if (request.method === "evidence.listMaterialSources") return result(request, {items: []});
    if (request.method === "evidence.get") {
      reads[p.evidence_id]++;
      return result(request, {evidence: structuredClone(cards[p.evidence_id])});
    }
    if (request.method === "evidence.reconcile") {
      reconcileCalls++;
      return result(request, {items: Object.keys(cards).map(id => ({
        evidence_id: id, missing_fields: [], untraceable_results: [], verbatim_candidates: [],
        date_hints: [], possible_duplicates: [], has_source: true,
      })), summary: {total: 2}});
    }
    if (request.method === "settings.get") {
      settingsReads++;
      if (mode === "settings_error") return JSON.stringify({jsonrpc: "2.0", id: request.id,
        error: {code: "INTERNAL_ERROR", message: "Synthetic inference setting unavailable", details: {retryable: false}}});
      return result(request, settings);
    }
    if (request.method === "settings.update" && p.section === "evidence_inference") {
      settings.evidence_inference.enabled = p.payload.enabled;
      return result(request, {section: "evidence_inference", saved: true});
    }
    if (request.method === "evidence.inferFields") {
      inferenceCalls++;
      const response = result(request, {enabled: settings.evidence_inference.enabled, cards: structuredClone(group),
        summary: {requested: group.length, candidates: group.flatMap(card => card.candidates).length}});
      if (mode === "disabled_pending") return new Promise(resolve => {releaseInference = () => resolve(response);});
      return response;
    }
    if (request.method !== "evidence.confirmInference") throw new Error("Unexpected RPC: " + request.method);
    calls.push(structuredClone(p));
    const count = calls.length;
    if (mode === "single_after_write") {
      write("A", "time_range", "2035", "L2", "1".repeat(64));
      return failure(request);
    }
    if (mode === "partial_other_card" && count === 2) {
      write("B", "role_scope", "已写入且仍待审核的合成职责", "L3", "2".repeat(64));
      return failure(request);
    }
    if (mode === "partial_retry" && count === 2) return failure(request);
    const chosen = sameField ? (mode === "edited" ? first : second)
      : count === 1 ? first : role;
    const level = mode === "edited" ? "L4" : chosen.level;
    const value = mode === "edited" ? "2024" : chosen.value;
    const sha = p.action === "reject" ? cards[p.evidence_id].source_sha256
      : (count === 1 ? "1" : "2").repeat(64);
    if (p.action !== "reject") write(p.evidence_id, chosen.field, value, level, sha);
    return result(request, {status: p.action === "reject" ? "rejected" : "accepted",
      evidence_id: p.evidence_id, field: chosen.field, candidate_hash: chosen.candidate_hash,
      card_sha256: sha, value, provenance: {level}});
  });
  root = createRoot(document.getElementById("root"));
  root.render(React.createElement(MemoryRouter, {initialEntries: ["/evidence"]},
    React.createElement(EvidencePage)));
  let error = null;
  const stages = [];
  const view = () => ({
    rows: Array.from(document.querySelectorAll('[data-testid="evidence-inference-candidate"]'))
      .map(row => ({text: row.textContent, value: row.querySelector("input").value})),
    count: Number(byTest("evidence-summary-inference")?.querySelector("span")?.textContent),
    detail: byTest("evidence-detail-view")?.textContent || "",
    errorVisible: document.body.innerText.includes("Synthetic candidate state publication failed"),
    settingsErrorVisible: document.body.innerText.includes("Synthetic inference setting unavailable"),
  });
  try {
    if (mode === "settings_error") {
      await waitFor(() => settingsReads > 0 && (byTest("evidence-detail-view")
        || document.body.innerText.includes("Synthetic inference setting unavailable")));
      await tick(); await tick();
      return {error, calls, reads, readsAtFailure, reconcileCalls, reconcileAtFailure,
        inferenceCalls, failureCount, settingsReads, enabled: settings.evidence_inference.enabled,
        stages, ...view()};
    }
    await waitFor(() => byTest("evidence-inference-run") && byTest("evidence-diagnosis"));
    click(byTest("evidence-inference-run"));
    await waitFor(() => inferenceCalls === 1 && (mode === "disabled_pending" || !byTest("evidence-inference-run").disabled));
    await tick();
    if (["disabled", "disabled_pending"].includes(mode)) {
      const host = document.createElement("div");
      document.body.append(host);
      const settingsRoot = createRoot(host);
      try {
        settingsRoot.render(React.createElement(MemoryRouter,
          {initialEntries: ["/system-settings?section=evidenceInference"]},
          React.createElement(SystemSettingsPage)));
        await waitFor(() => byTest("evidence-inference-toggle"));
        click(byTest("evidence-inference-toggle"));
        await waitFor(() => !settings.evidence_inference.enabled && !byTest("evidence-inference-toggle").disabled);
      } finally {
        settingsRoot.unmount();
        host.remove();
      }
      const before = listCalls, beforeSettings = settingsReads;
      window.dispatchEvent(new Event("pipf:refresh"));
      await waitFor(() => listCalls > before && settingsReads > beforeSettings);
      await tick(); await tick();
      if (mode === "disabled_pending") {
        releaseInference();
        await waitFor(() => !byTest("evidence-inference-run").disabled);
      }
    } else if (["sequential", "partial_retry", "partial_other_card"].includes(mode)) {
      if (mode === "partial_other_card") {
        const row = Array.from(document.querySelectorAll("tr")).find(row => row.textContent.includes("合成项目乙"));
        click(row);
        await waitFor(() => byTest("evidence-detail-view").textContent.includes("合成项目乙"));
      }
      click(byTest("evidence-inference-batch"));
      await waitFor(() => calls.length >= 2 && !byTest("evidence-inference-run").disabled);
      stages.push(view());
      if (mode === "partial_retry") {
        click(byTest("evidence-inference-batch"));
        await waitFor(() => calls.length === 3 && !byTest("evidence-inference-run").disabled);
      }
    } else {
      const desired = mode.startsWith("second_") ? "2024" : "2023";
      const row = Array.from(document.querySelectorAll('[data-testid="evidence-inference-candidate"]'))
        .find(row => row.querySelector("input").value === desired);
      if (mode === "edited") {
        edit(row.querySelector("input"), "2024");
        await tick();
      }
      click(button(row, mode === "edited" ? "acceptEdited" : mode === "second_reject" ? "reject" : "accept"));
      await waitFor(() => calls.length === 1 && !byTest("evidence-inference-run").disabled);
    }
    await tick(); await tick();
  } catch (reason) {
    error = String(reason.message || reason);
  }
  return {error, calls, reads, readsAtFailure, reconcileCalls, reconcileAtFailure,
    inferenceCalls, failureCount, settingsReads, enabled: settings.evidence_inference.enabled,
    stages, ...view()};
};
"""


@pytest.fixture(scope="module")
def inference_browser_behavior():
    from tests.unit.gui.test_system_settings_behavior import run_component_cases

    modes = (
        "second_accept", "second_reject", "edited", "disabled",
        "single_after_write", "partial_other_card", "sequential", "partial_retry",
        "settings_error", "disabled_pending",
    )
    return run_component_cases(
        INFERENCE_ENTRY, {mode: {"mode": mode} for mode in modes}, "runInferenceCase",
    )


def _browser_case(observations, name):
    actual = observations[name]
    assert actual["error"] is None, actual
    assert actual["inferenceCalls"] == 1, "confirmation and refresh must not infer again"
    return actual


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_chrome_second_same_field_candidate_keeps_its_identity(inference_browser_behavior, action):
    actual = _browser_case(inference_browser_behavior, "second_" + action)
    assert len(actual["calls"]) == 1
    assert actual["calls"][0].get("candidate_hash") == "b" * 64, actual["calls"]
    assert actual["calls"][0]["field"] == "time_range"
    assert actual["calls"][0]["action"] == action
    assert [row["value"] for row in actual["rows"]] == ["2023", "负责合成项目接口设计与联调"]
    assert actual["count"] == 2


def test_chrome_edit_to_another_candidate_value_still_identifies_original(inference_browser_behavior):
    actual = _browser_case(inference_browser_behavior, "edited")
    assert actual["calls"][0].get("candidate_hash") == "a" * 64, actual["calls"]
    assert actual["calls"][0]["value"] == "2024"


def test_chrome_modified_acceptance_withdraws_group_and_updates_count(inference_browser_behavior):
    actual = _browser_case(inference_browser_behavior, "edited")
    assert actual["rows"] == [], actual
    assert actual["count"] == 0
    assert "2024" in actual["detail"] and "L4" in actual["detail"]


def test_chrome_disabling_inference_hides_old_l3_without_rerunning(inference_browser_behavior):
    actual = _browser_case(inference_browser_behavior, "disabled")
    assert actual["enabled"] is False
    assert [row["value"] for row in actual["rows"]] == ["2023"], actual
    assert actual["count"] == 1
    assert actual["calls"] == []


@pytest.mark.parametrize(("mode", "card_id", "written"), [
    ("single_after_write", "A", "2035"),
    ("partial_other_card", "B", "已写入且仍待审核的合成职责"),
])
def test_chrome_confirmation_failure_refreshes_actual_written_card(
    inference_browser_behavior, mode, card_id, written,
):
    actual = _browser_case(inference_browser_behavior, mode)
    assert actual["errorVisible"] is True
    assert actual["reads"][card_id] > actual["readsAtFailure"][card_id], actual
    assert actual["reconcileCalls"] > actual["reconcileAtFailure"], actual
    assert written in actual["detail"], actual
    assert [call["evidence_id"] for call in actual["calls"]] == (
        ["A", "B"] if mode == "partial_other_card" else ["A"]
    ), "no failed request or previously successful candidate may be replayed automatically"


def test_chrome_settings_read_failure_does_not_hide_successful_evidence(inference_browser_behavior):
    actual = inference_browser_behavior["settings_error"]
    assert actual["error"] is None, actual
    assert "合成项目甲" in actual["detail"], actual
    assert actual["settingsErrorVisible"] is True
    assert actual["rows"] == [] and actual["calls"] == []
    assert actual["inferenceCalls"] == 0


def test_chrome_delayed_inference_cannot_restore_l3_after_disable_refresh(inference_browser_behavior):
    actual = _browser_case(inference_browser_behavior, "disabled_pending")
    assert actual["enabled"] is False
    assert [row["value"] for row in actual["rows"]] == ["2023"], actual
    assert actual["count"] == 1
    assert actual["calls"] == []


def test_chrome_original_acceptance_chains_sha_and_preserves_progress(inference_browser_behavior):
    actual = _browser_case(inference_browser_behavior, "sequential")
    assert [call["card_sha256"] for call in actual["calls"]] == ["0" * 64, "1" * 64]
    assert [call["field"] for call in actual["calls"]] == ["time_range", "role_scope"]
    assert actual["rows"] == [] and actual["count"] == 0
    assert "2023" in actual["detail"] and "负责合成项目接口设计与联调" in actual["detail"]


def test_chrome_partial_retry_does_not_replay_the_successful_field(inference_browser_behavior):
    actual = _browser_case(inference_browser_behavior, "partial_retry")
    assert actual["stages"][0]["count"] == 1
    assert [call["field"] for call in actual["calls"]] == ["time_range", "role_scope", "role_scope"]
    assert [call["card_sha256"] for call in actual["calls"]] == ["0" * 64, "1" * 64, "1" * 64]
    assert actual["rows"] == [] and actual["count"] == 0
