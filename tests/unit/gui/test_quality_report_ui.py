"""四层质量报告组件与页面入口的 GUI 合同。

组件用 node + TypeScript transpile 真实执行，页面只做源码约定检查，
避免只断言字符串却不知道组件渲染出什么。
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _render_component():
    component = ROOT / "ui/src/components/quality-report.tsx"
    assert component.exists(), "四层质量报告组件尚未实现"
    script = r'''
const fs=require('fs'),ts=require('typescript'),vm=require('vm'),assert=require('assert/strict');
const jsx=(type,props)=>({type,props:props||{}}),exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(process.argv[1],'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:n=>n==='react/jsx-runtime'?{jsx,jsxs:jsx}:n==='react-router-dom'?{useNavigate:()=>()=>{}}:n==='react-i18next'?{useTranslation:()=>({t:(key,opts)=>{if(key.startsWith('quality.report.tier.'))return key.split('.').pop();if(key==='quality.report.llmPending')return key+' '+((opts||{}).rules||'');if(key==='quality.report.legacyValue')return key+' '+((opts||{}).rule)+' '+((opts||{}).expression);return key;}})}:{} });
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props.children):String(v??'');
const sample={auto_pass:false,llm_pending:['R1.4','R3.1'],legacy_scores:{rule_total:52,llm_expression:69},
  tiers:{eligible:{passed:false,failures:[{rule:'R1.3',target:'项目经历「统一平台建设」（ec_1234）',reason:'证据卡 time_range 缺失'}]},
         fit:{passed:true,failures:[]},strong:{passed:false,failures:[{rule:'R3.3',target:'bullet#2',reason:'出现空话词：深入理解'}]},
         distinct:{passed:false,failures:[{rule:'R4.2',target:'highlights',reason:'无合格突出点'}],blocked_by:'eligible',
           highlights:[{highlight_id:'hl_b3_d1',bullet_ref:'bullet#3',jd_item_id:'d1',exceeds:'规模、难度',level:'L1',reason:'规模超出 JD 字面'}],
           metrics:{candidates:[{highlight_id:'hl_b3_d1',bullet_ref:'bullet#3',jd_item_id:'d1',exceeds:'规模、难度',level:'L1'},{highlight_id:'hl_b4_d2',bullet_ref:'bullet#4',jd_item_id:'d2',exceeds:'范围',level:'L2',rejected:false}]}}}};
const decisions=[];
const rendered=text(exports.QualityReportPanel({report:sample,onHighlightDecision:(id,action)=>{decisions.push([id,action]);}}));
for(const tier of ['eligible','fit','strong','distinct'])assert.ok(rendered.includes(tier),tier);
assert.ok(!rendered.includes('quality.passed'));
assert.ok(rendered.includes('quality.failed'));
for(const rule of ['R1.3','R3.3','R4.2'])assert.ok(rendered.includes(rule),rule);
assert.ok(rendered.includes('ec_1234')&&rendered.includes('证据卡 time_range 缺失'));
assert.ok(rendered.includes('quality.report.llmPending')&&rendered.includes('R1.4'));
assert.ok(rendered.includes('quality.report.legacyValue')&&rendered.includes('52')&&rendered.includes('69'));
assert.ok(rendered.includes('quality.report.blockedBy'));
assert.ok(rendered.includes('quality.report.highlights')&&rendered.includes('bullet#3')&&rendered.includes('规模、难度'));
assert.ok(rendered.includes('quality.report.reject')&&rendered.includes('quality.report.select'));
assert.ok(rendered.includes('quality.report.candidate'));
assert.ok(rendered.includes('quality.report.openCard'));
const passed=text(exports.QualityReportPanel({report:{auto_pass:true,llm_pending:[],tiers:{eligible:{passed:true,failures:[]},fit:{passed:true,failures:[]},strong:{passed:true,failures:[]},distinct:{passed:true,failures:[]}}}}));
assert.ok(passed.includes('quality.passed'));
const missing=text(exports.QualityReportPanel({report:null}));
assert.ok(missing.includes('quality.report.missing'));
'''
    result = subprocess.run(
        ["node", "-e", script, str(component)],
        cwd=ROOT / "ui",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_quality_report_component_renders_tiers_failures_and_legacy_scores():
    _render_component()


def test_quick_run_and_approval_pages_consume_quality_report():
    quick = _source("ui/src/pages/quick-run/index.tsx")
    assert "QualityReportPanel" in quick
    assert "quickRunResult?.quality_report" in quick
    assert "decideQualityHighlight" in quick and "onHighlightDecision" in quick
    submissions = _source("ui/src/pages/submissions/index.tsx")
    assert "QualityReportPanel" in submissions
    assert "nativePdf.quality?.quality_report" in submissions
    assert "decideQualityHighlight" in submissions and "onHighlightDecision" in submissions

    api = _source("ui/src/lib/sidecar/api.ts")
    assert '"quality.decideHighlight"' in api


def test_sidecar_types_and_i18n_expose_four_tier_report():
    types = _source("ui/src/lib/sidecar/types.ts")
    for token in ("QualityReport", "QualityTier", "QualityFailure", "auto_pass", "llm_pending"):
        assert token in types
    for lang in ("zh", "en"):
        catalog = json.loads(_source(f"ui/src/i18n/{lang}.json"))
        report = catalog["quality"]["report"]
        assert report["tier"]["eligible"] and report["tier"]["fit"]
        assert report["tier"]["strong"] and report["tier"]["distinct"]
        assert "{{rules}}" in report["llmPending"]
        for key in ("highlights", "reject", "select", "candidate", "decisionSaved"):
            assert report[key]
