"""岗位批量适配预检与推荐清单的 GUI 合同。

适配预检组件用 node + TypeScript transpile 真实执行，断言渲染内容；
页面接线、types 与 i18n 目录只做源码/结构检查。
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPONENT = ROOT / "ui" / "src" / "components" / "fit-precheck.tsx"
JOBS_PAGE = ROOT / "ui" / "src" / "pages" / "jobs" / "index.tsx"
QUICK_RUN_PAGE = ROOT / "ui" / "src" / "pages" / "quick-run" / "index.tsx"
TYPES = ROOT / "ui" / "src" / "lib" / "sidecar" / "types.ts"
I18N_FILES = [ROOT / "ui" / "src" / "i18n" / "en.json", ROOT / "ui" / "src" / "i18n" / "zh.json"]
STATES = ["recommended", "consider", "promising", "caution", "hold", "unknown", "low"]


def _render_component():
    assert COMPONENT.exists(), "岗位适配预检组件尚未实现"
    script = r'''
const fs=require('fs'),ts=require('typescript'),vm=require('vm'),assert=require('assert/strict');
const jsx=(type,props)=>({type,props:props||{}}),exports={};
const t=(key,options)=>{const opts=options||{};const parts=Object.entries(opts).filter(([name])=>name!=='defaultValue').map(([name,value])=>`${name}=${value}`);return parts.length?`${key} ${parts.join(' ')}`:key;};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(process.argv[1],'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:n=>n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-i18next'?{useTranslation:()=>({t})}:{}});
const text=v=>{v=typeof v==='object'&&v&&typeof v.type==='function'?v.type(v.props):v;return Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');};
const walk=(node,visit)=>{node=typeof node==='object'&&node&&typeof node.type==='function'?node.type(node.props):node;if(!node||typeof node!=='object')return;visit(node);const children=node.props&&node.props.children;if(Array.isArray(children))children.forEach(child=>walk(child,visit));else walk(children,visit);};
const testIds=node=>{const ids=[];walk(node,item=>{const id=item.props&&item.props['data-testid'];if(id)ids.push(id);});return ids;};

// 1) 7 种 state 徽标都渲染本地化文案；缺失 precheck 时不渲染。
for(const state of ['recommended','consider','promising','caution','hold','unknown','low']){
  const rendered=text(exports.FitPrecheckBadge({precheck:{source:'rule',state,rank:0,coverage:0.5}}));
  assert.ok(rendered.includes(`pages.jobs.precheck.state.${state}`),`badge ${state}: ${rendered}`);
}
assert.equal(text(exports.FitPrecheckBadge({precheck:null})),'','precheck 缺失时徽标不渲染');
assert.equal(text(exports.FitPrecheckBadge({})),'','未传 precheck 时徽标不渲染');

// 2) 推荐清单：rank 升序取前 3，排除 low/unknown/insufficient，点击回传画像 id。
const profiles=[
  {job_profile_id:'p_low',title:'LOWTITLE',company:'LowCo',status:'active',fit_precheck:{source:'rule',state:'low',rank:0,coverage:0.1}},
  {job_profile_id:'p_hold',title:'HOLDTITLE',company:'HoldCo',status:'active',fit_precheck:{source:'rule',state:'hold',rank:4,coverage:0.3}},
  {job_profile_id:'p_best',title:'BESTTITLE',company:'BestCo',status:'active',fit_precheck:{source:'assessed',state:'recommended',rank:0,coverage:null,matched_requirements:1,total_requirements:2}},
  {job_profile_id:'p_unknown',title:'UNKNOWNTITLE',company:'UnknownCo',status:'active',fit_precheck:{source:'insufficient',state:'unknown',rank:0}},
  {job_profile_id:'p_consider',title:'CONSIDERTITLE',company:'ConsiderCo',status:'active',fit_precheck:{source:'assessed',state:'consider',rank:1,coverage:0.8}},
  {job_profile_id:'p_promising',title:'PROMISINGTITLE',company:'PromisingCo',status:'active',fit_precheck:{source:'rule',state:'promising',rank:2,coverage:0.66}},
  {job_profile_id:'p_caution',title:'CAUTIONTITLE',company:'CautionCo',status:'active',fit_precheck:{source:'rule',state:'caution',rank:3,coverage:0.4}},
  {job_profile_id:'p_none',title:'NONETITLE',company:'NoneCo',status:'active'},
  {job_profile_id:'p_draft',title:'DRAFTTITLE',company:'DraftCo',status:'draft',fit_precheck:{source:'assessed',state:'recommended',rank:0,coverage:null}},
];
const selected=[];
const ranking=exports.FitPrecheckRanking({profiles,onSelect:id=>{selected.push(id);}});
const rankingText=text(ranking);
assert.ok(testIds(ranking).includes('jobs-precheck-ranking'),'推荐清单容器缺少 data-testid');
assert.ok(rankingText.includes('pages.jobs.precheck.heading'));
assert.ok(rankingText.includes('pages.jobs.precheck.subtitle'));
const positions=['BESTTITLE','CONSIDERTITLE','PROMISINGTITLE'].map(title=>rankingText.indexOf(title));
assert.ok(positions[0]>=0&&positions[0]<positions[1]&&positions[1]<positions[2],`推荐清单未按 rank 升序: ${positions}`);
for(const excluded of ['LOWTITLE','UNKNOWNTITLE','NONETITLE','CAUTIONTITLE','HOLDTITLE','DRAFTTITLE']){
  assert.ok(!rankingText.includes(excluded),`${excluded} 不应进入推荐清单前三`);
}
assert.ok(rankingText.includes('pages.jobs.precheck.state.recommended'));
assert.ok(rankingText.includes('pages.jobs.precheck.matched')&&rankingText.includes('matched=1')&&rankingText.includes('total=2'),'无 coverage 时用命中要求数说明');
assert.ok(rankingText.includes('pages.jobs.precheck.coverage')&&rankingText.includes('percent=66'),'有 coverage 时展示覆盖比例');
let clicked=false;
walk(ranking,node=>{
  if(!clicked&&node.props&&typeof node.props.onClick==='function'&&text(node).includes('BESTTITLE')){
    node.props.onClick();clicked=true;
  }
});
assert.ok(clicked,'推荐项缺少点击回调');
assert.deepEqual(selected,['p_best'],'点击推荐项应回传对应画像 id');
const assessedRanking=text(exports.FitPrecheckRanking({profiles:[
  {job_profile_id:'p_assessed',title:'ASSESSEDONLY',company:'AssessedCo',status:'active',fit_precheck:{
    source:'assessed',state:'consider',rank:1,coverage:null,matched_requirements:null,total_requirements:null,
  }},
],onSelect:()=>{}}));
assert.ok(assessedRanking.includes('pages.jobs.precheck.state.consider'));
assert.ok(!assessedRanking.includes('pages.jobs.precheck.coverage')&&!assessedRanking.includes('pages.jobs.precheck.matched'),'assessed 无命中明细时不虚构覆盖数');
const emptyRanking=text(exports.FitPrecheckRanking({profiles:[],onSelect:()=>{}}));
assert.ok(emptyRanking.includes('pages.jobs.precheck.heading'));
assert.ok(emptyRanking.includes('pages.jobs.precheck.empty'),'无候选时展示空态');

// 3) 详情：basis/coverage/命中/未命中/限制说明；缺失 precheck 返回 null。
const ruleDetail=text(exports.FitPrecheckDetail({precheck:{
  source:'rule',state:'caution',rank:3,coverage:0.72,matched_requirements:13,total_requirements:18,
  evidence_hits:4,matched_terms:['Java','Redis'],missing_terms:['Kubernetes'],
}}));
assert.ok(ruleDetail.includes('pages.jobs.precheck.basisRule'));
assert.ok(ruleDetail.includes('pages.jobs.precheck.coverage')&&ruleDetail.includes('percent=72'));
assert.ok(ruleDetail.includes('pages.jobs.precheck.matched')&&ruleDetail.includes('matched=13')&&ruleDetail.includes('total=18'));
assert.ok(ruleDetail.includes('Java')&&ruleDetail.includes('Redis'),'命中关键词应展示');
assert.ok(ruleDetail.includes('pages.jobs.precheck.missing')&&ruleDetail.includes('count=5'),'缺口计数用 total-matched 而非截断数组长度');
assert.ok(ruleDetail.includes('Kubernetes'),'未命中关键词应展示');
assert.ok(ruleDetail.includes('pages.jobs.precheck.limitation'),'规则预检应提示未调用模型的限制');
assert.ok(ruleDetail.includes('pages.jobs.precheck.state.caution'));
const assessedDetail=text(exports.FitPrecheckDetail({precheck:{
  source:'assessed',state:'recommended',rank:0,coverage:null,matched_requirements:null,total_requirements:null,
  evidence_hits:null,matched_terms:[],missing_terms:[],match_score:88,fit_state:'passed',fit_failures:0,
}}));
assert.ok(assessedDetail.includes('pages.jobs.precheck.basisAssessed'));
assert.ok(assessedDetail.includes('pages.jobs.precheck.state.recommended'));
assert.ok(!assessedDetail.includes('pages.jobs.precheck.limitation'),'模型评估结果不显示规则预检限制说明');
assert.ok(!assessedDetail.includes('pages.jobs.precheck.coverage')&&!assessedDetail.includes('pages.jobs.precheck.matched'),'assessed 无命中明细时不虚构覆盖数');
const insufficientDetail=text(exports.FitPrecheckDetail({precheck:{
  source:'insufficient',state:'unknown',rank:5,coverage:null,matched_requirements:0,total_requirements:0,
  evidence_hits:0,matched_terms:[],missing_terms:[],
}}));
assert.ok(insufficientDetail.includes('pages.jobs.precheck.basisInsufficient'));
assert.ok(insufficientDetail.includes('pages.jobs.precheck.limitation'),'规则/数据不足预检应提示未调用模型的限制');
assert.ok(!insufficientDetail.includes('pages.jobs.precheck.matched'),'无要求可验证时不显示 0/0 命中数');
assert.equal(text(exports.FitPrecheckDetail({precheck:null})),'','precheck 缺失时详情不渲染');
'''
    result = subprocess.run(
        ["node", "-e", script, str(COMPONENT)],
        cwd=ROOT / "ui",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _flatten(value, prefix=""):
    leaves = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            leaves.update(_flatten(child, path))
        else:
            leaves[path] = child
    return leaves


def test_fit_precheck_component_renders_badges_ranking_and_detail():
    _render_component()


def test_fit_precheck_types_and_i18n_contracts():
    types = _source("ui/src/lib/sidecar/types.ts")
    for token in (
        "export type FitPrecheckState",
        "export type FitPrecheckSource",
        "export interface FitPrecheck",
        "fit_precheck?: FitPrecheck",
        "coverage: number | null",
    ):
        assert token in types, token
    for state in STATES:
        assert f'"{state}"' in types, state

    catalogs = {}
    for i18n_file in I18N_FILES:
        catalog = json.loads(i18n_file.read_text(encoding="utf-8"))
        catalogs[i18n_file.name] = catalog
        precheck = catalog["pages"]["jobs"]["precheck"]
        for key in (
            "heading",
            "subtitle",
            "empty",
            "limitation",
            "basisAssessed",
            "basisRule",
            "basisInsufficient",
            "coverage",
            "matched",
            "missing",
            "sortLabel",
            "sortPrecheck",
            "sortUpdated",
        ):
            assert precheck.get(key), f"{i18n_file.name} pages.jobs.precheck.{key}"
        assert set(precheck["state"]) == set(STATES)
        for state in STATES:
            assert precheck["state"][state], f"{i18n_file.name} state.{state}"
        quick_run = catalog["pages"]["quickRun"]
        assert "{{label}}" in quick_run["fitBadgePrecheck"]
        for placeholder in ("{{label}}", "{{matched}}", "{{total}}"):
            assert placeholder in quick_run["fitHintPrecheck"], placeholder

    en_precheck = _flatten(catalogs["en.json"]["pages"]["jobs"]["precheck"])
    zh_precheck = _flatten(catalogs["zh.json"]["pages"]["jobs"]["precheck"])
    assert set(en_precheck) == set(zh_precheck)


def test_fit_precheck_pages_are_wired_to_component_and_sorting():
    component = _source("ui/src/components/fit-precheck.tsx")
    for token in (
        "export function FitPrecheckBadge",
        "export function FitPrecheckRanking",
        "export function FitPrecheckDetail",
        'data-testid="jobs-precheck-ranking"',
    ):
        assert token in component, token

    jobs = _source("ui/src/pages/jobs/index.tsx")
    for token in (
        'from "@/components/fit-precheck"',
        "FitPrecheckRanking",
        "FitPrecheckBadge",
        "FitPrecheckDetail",
        "fit_precheck",
        "sortedProfiles",
        "sortProfiles",
        'useState<ProfileSort>("precheck")',
        'data-testid="jobs-profile-sort"',
        'sort: { field: "fit_precheck", order: "asc" }',
        "pageSize: 100",
        "pages.jobs.precheck.sortLabel",
        "pages.jobs.precheck.sortPrecheck",
        "pages.jobs.precheck.sortUpdated",
    ):
        assert token in jobs, token

    quick_run = _source("ui/src/pages/quick-run/index.tsx")
    for token in (
        "fit_precheck",
        'source === "rule"',
        "pages.quickRun.fitBadgePrecheck",
        "pages.quickRun.fitHintPrecheck",
        "pages.jobs.precheck.state.",
    ):
        assert token in quick_run, token
