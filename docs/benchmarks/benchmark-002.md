# Benchmark 002 — Stack Field Fix 前后对比

> 日期：2026-05-08
> 变更：Matching 引擎扩展搜索范围至 EvidenceCard.stack 字段
> 对比基线：benchmark-001

## 变更摘要

`RuleMatchingEngine.score()` 原来只搜索 `tags`, `title`, `results` 字段。修复后新增 `stack` 字段搜索。同时 `EvidenceCard` 领域模型新增 `stack: tuple[str, ...]` 字段，`EvidenceStore` 同步加载。

## 对比结果

| 指标 | 修复前 (benchmark-001) | 修复后 (benchmark-002) | 变化 |
|------|----------------------|----------------------|------|
| K (关键词覆盖) | 0.0 | 0.6 | +0.6 |
| Q (量化强度) | 1.0 | 1.0 | — |
| E (证据强度) | 1.0 | 1.0 | — |
| **Matching Total** | **0.5** | **0.8** | **+0.3** |
| Evaluation Total | 0.65 | 0.65 | — |
| Gap Tasks | 2 项 | 0 项 | — |

### 单卡匹配分变化（Top 5）

| 证据卡 | 修复前 | 修复后 | 命中关键词 |
|--------|--------|--------|-----------|
| ec-2026-001 | 0.500 | **0.800** | Java, Redis, Kafka |
| ec-2026-011 | 0.500 | **0.700** | Java, Redis |
| ec-2026-012 | 0.500 | **0.700** | Java, Redis |
| ec-2026-013 | 0.500 | **0.700** | Java, Redis |
| ec-2026-014 | 0.500 | **0.700** | Java, Redis |
| ec-2026-003 | 0.500 | **0.500** | (无命中) |

### 区分度

- 修复前：10 张卡全部 0.500（无法区分）
- 修复后：4 个层级（0.500 / 0.600 / 0.700 / 0.800），可有效排序

## 诊断

### 已修复
- Matching 引擎现在搜索 `tags + stack + title + results` 四个信号源
- 证据卡可按技术栈相关性排序

### 仍存在的问题
1. **Evaluation coverage 仍为 0.0**：生成内容不包含技术栈词（生成引擎只用 `title + results`，不含 `stack`）
2. **JD 关键词 SLA/SLO 无证据卡覆盖**：需要新增含 SLA/SLO 治理的证据卡
3. **Gap tasks 只检查 must_have，不检查 keywords**：SLA/SLO 缺失不会触发补证据任务

### 待 LLM API 接入后验证
- LLM Matching 能否通过语义理解发现更多关联（当前 rule 模式仅字符串匹配）
- LLM Rewriter 是否能在不改事实的前提下注入技术栈关键词
- LLM Evaluator 的解释层质量

## 复现命令

```bash
python3 - <<'PYEOF'
import sys; sys.path.insert(0, ".")
from tools.config.composer import Composer
from tools.engines.evidence.store import EvidenceStore
from tools.domain.models import JobProfile
from tools.infra.persistence.yaml_io import parse_simple_yaml
from pathlib import Path

store = EvidenceStore("evidence_cards")
cards = [store.get(p.stem) for p in sorted(Path("evidence_cards").glob("ec-*.yaml"))]
cards = [c for c in cards if c and c.is_eligible()]

jp_parsed = parse_simple_yaml(Path("job_profiles/jp-2026-001.yaml").read_text(encoding="utf-8"))
jp = JobProfile(id="jp-2026-001", title=jp_parsed["scalars"].get("target_role",""),
    keywords=tuple(jp_parsed["lists"].get("keywords",[])), level="senior")

composer = Composer.from_policy_path("policy.yaml")
m = composer.build_matching_registry().create("rule")
g = composer.build_generation_registry().create("template")
e = composer.build_evaluation_registry().create("rule")

report = m.score(cards, jp)
resume = g.assemble(report, cards, "v1")
scorecard = e.evaluate(resume, jp)

print(f"Matching Total: {report.score_breakdown.get('total')} (K={report.score_breakdown.get('K')})")
print(f"Evaluation Total: {scorecard.total_score}")
for card in cards:
    single = m.score([card], jp)
    print(f"  {card.id}: {single.score_breakdown.get('total'):.3f}")
PYEOF
```
