# Benchmark 004 — LLM Evaluator：打破 coverage=0 盲区

> 日期：2026-05-08
> LLM：LM Studio `openai/gpt-oss-120b` @ localhost:1234
> 变更：LLMEvaluationEngine prompt 增强，新增语义覆盖、捏造风险、缺口/优点/改进分析

## 背景

Benchmark 001-003 中，RuleEvaluationEngine 的 coverage 维度恒为 0.0——因为它用纯文本匹配 JD 关键词，而简历内容不含字面关键词（关键词在 stack 字段中，生成内容用中文描述）。

LLMEvaluationEngine 的设计是"规则打分 + LLM 语义解释层"。本轮验证它能否填补语义盲区。

## LLM Evaluator 新增维度

| 维度 | 说明 | 来源 |
|------|------|------|
| `coverage` (blended) | 30% rule-coverage + 70% LLM semantic-coverage | 混合 |
| `llm_semantic_coverage` | LLM 判断的语义级关键词覆盖率 | LLM |
| `llm_fabrication_risk` | 无证据支撑声明的可能性（越低越好） | LLM |
| `llm_gaps_count` | LLM 识别的具体关键词缺口数量 | LLM |
| `llm_strengths_count` | LLM 识别的优点数量 | LLM |
| `llm_improvements_count` | LLM 建议的改进数量 | LLM |

## 对比结果

### 两份被评测简历

| 简历 | 生成方式 | 长度 | 来源卡数 |
|------|---------|------|---------|
| Rule Resume | TemplateAssembler | 380 chars | 3 |
| LLM Resume | TemplateAssembler → LLMRewriter | 419 chars | 3 |

### 评测对比矩阵

| 指标 | Rule→Rule | Rule→LLM | LLM→Rule | LLM→LLM |
|------|-----------|----------|----------|---------|
| | (rule eval on rule gen) | (rule eval on llm gen) | (llm eval on rule gen) | (llm eval on llm gen) |
| **Total Score** | 0.504 | 0.550 | **0.578** | **0.653** |
| Coverage (blended) | 0.000 | 0.000 | 0.210 | 0.294 |
| Semantic Coverage | — | — | 0.300 | 0.420 |
| Fabrication Risk | — | — | 0.400 | 0.120 |
| Keyword Gaps | — | — | 7 | 4 |
| Strengths | — | — | 5 | 4 |
| Improvements | — | — | 6 | 5 |

## 关键发现

### 1. Rule Evaluator 接近于"盲"
两份简历的 Rule Eval 总分差仅 0.046，coverage 双双为 0。Rule Evaluator 无法判断哪份简历更好。

### 2. LLM Evaluator 能区分质量
LLM→Rule = 0.578, LLM→LLM = 0.653，总分差 0.075。更重要的是语义维度揭示了真实差异。

### 3. LLM Rewriter 提升了语义覆盖率
- Rule-resume semantic coverage: **0.300**（LLM 认为 30% 的 JD 关键词有语义对应）
- LLM-resume semantic coverage: **0.420**（改写后提升到 42%）
- 改写减少了关键词缺口：7 → 4

### 4. LLM Rewriter 降低了捏造风险
- Rule-resume fabrication risk: **0.400**（模板化表述可能显得不够可信）
- LLM-resume fabrication risk: **0.120**（改写后表述更自然、更可信）
- 关键：LLM 改写没有引入新事实，但降低了"看起来像编的"风险

### 5. Coverage 公式生效
30% rule-coverage (0.0) + 70% LLM semantic-coverage (0.300/0.420) = 0.210/0.294。Coverage 维度从"恒为 0"变为"有意义"。

## 诊断

### 成功验证
- LLM Evaluator 的语义解释层设计正确且有效
- LLM Rewriter 在保持事实保真的前提下提升语义匹配度
- 混合 coverage 公式（30/70）产出可区分的评分

### 仍需改进
1. **LLM Evaluator 延迟**：每次评测需 ~5s（LLM API 调用），批量评测场景需缓存
2. **LLM 一致性**：同输入多次运行可能得到不同分数（大模型固有问题）
3. **Fabrication Risk 需校准**：当前 0.120/0.400 是 LLM 主观判断，需与人工评审对比

## 复现命令

```bash
python3 - <<'PYEOF'
import sys; sys.path.insert(0, ".")
from tools.config.composer import Composer
from tools.engines.evidence.store import EvidenceStore
from tools.domain.models import JobProfile
from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import parse_simple_yaml
from pathlib import Path

store = EvidenceStore("evidence_cards")
cards = [c for c in (store.get(p.stem) for p in sorted(Path("evidence_cards").glob("ec-*.yaml"))) if c and c.is_eligible()]
jp_parsed = parse_simple_yaml(Path("job_profiles/jp-2026-001.yaml").read_text(encoding="utf-8"))
jp = JobProfile(id="jp-2026-001", title=jp_parsed["scalars"].get("target_role",""),
    keywords=tuple(jp_parsed["lists"].get("keywords",[])), level="senior",
    must_have=tuple(jp_parsed["lists"].get("must_have",[])),
    nice_to_have=tuple(jp_parsed["lists"].get("nice_to_have",[])))

composer = Composer.from_policy_path("policy.yaml")
client = LLMClient(base_url="http://localhost:1234/v1", api_key="lm-studio")
matching_reg = composer.build_matching_registry()
gen_reg = composer.build_generation_registry()
eval_reg = composer.build_evaluation_registry()
composer.add_llm_strategies(client, "openai/gpt-oss-120b",
    composer.build_evidence_registry(), matching_reg, gen_reg, eval_reg)

# Generate resume
llm_report = matching_reg.create("llm").score(cards, jp)
selected = [c for c in cards if c.id in llm_report.evidence_card_ids] or cards[:5]
rule_resume = gen_reg.create("template").assemble(llm_report, selected, "v1")
llm_resume = gen_reg.create("llm").rewrite(rule_resume, f"Target: {jp.title}", "e-commerce")

# Evaluate
re = eval_reg.create("rule")
le = eval_reg.create("llm")
print(f"Rule evaluator on rule resume: {re.evaluate(rule_resume, jp).total_score:.3f}")
print(f"Rule evaluator on LLM resume:  {re.evaluate(llm_resume, jp).total_score:.3f}")
print(f"LLM evaluator on rule resume:  {le.evaluate(rule_resume, jp).total_score:.3f}")
print(f"LLM evaluator on LLM resume:   {le.evaluate(llm_resume, jp).total_score:.3f}")
PYEOF
```
