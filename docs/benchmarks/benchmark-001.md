# Benchmark 001 — Rule-Mode Pipeline Baseline

> 日期：2026-05-08
> 模式：rule-mode（无 LLM）
> 目标：建立首个可量化的质量基线

## 1. 测试配置

| 参数 | 值 |
|------|-----|
| Job Profile | jp-2026-001 (Backend Tech Lead) |
| Keywords | Java, Redis, Kafka, SLA, SLO |
| Must-have | 高并发系统设计, 稳定性治理, 跨团队协作 |
| Evidence Cards | 10 张（全部 eligible） |
| Matching Engine | RuleMatchingEngine |
| Generation Engine | TemplateAssembler |
| Evaluation Engine | RuleEvaluationEngine |

## 2. Matching 结果

### 总分

| 维度 | 分数 | 说明 |
|------|------|------|
| K (关键词覆盖) | **0.0** | 0/5 关键词命中 |
| Q (量化强度) | 1.0 | 全部 10 张卡有 results |
| E (证据强度) | 1.0 | 全部 10 张卡有 artifacts |
| **Total** | **0.5** | (K×0.5 + Q×0.25 + E×0.25) |

### 关键发现 #1：关键词覆盖率 = 0

JD 关键词 `Java, Redis, Kafka, SLA, SLO` 全部出现在证据卡的 `stack` 字段中，但 `RuleMatchingEngine.score()` 只在 `tags`, `title`, `results` 中搜索关键词——不搜索 `stack` 字段。

| 证据卡 | Stack 中包含的 JD 关键词 |
|--------|------------------------|
| ec-2026-011 | Java |
| ec-2026-017 | Java |
| ec-2026-013 | Java |

这导致 10 张证据卡全部获得相同的匹配分（0.5），无法区分。

### 缺口清单

| 缺口 | 严重度 |
|------|--------|
| 补充 高并发系统设计 相关证据 | 高 |
| 补充 跨团队协作 相关证据 | 中 |

## 3. Generation 结果

| 指标 | 值 |
|------|-----|
| 版本 | v1-benchmark-001 |
| 格式 | Markdown |
| 长度 | 1,467 字符 |
| 选中卡数 | 10/10 |
| 亮点条目 | 10 条（每卡 1 条） |
| 无证据内容 | 0（通过 FabricationGuard 检查） |

### 关键发现 #2：Template Assembler 行为正确

`TemplateAssembler` 正确地从 10 张证据卡中各提取了 `title` + `results`，生成了 1,467 字符的简历草稿。`FabricationGuard` 未触发，说明所有内容均可追溯到证据卡。

但生成质量受限于匹配阶段——因为匹配分无法区分证据卡优劣，简历包含了所有 10 张卡的亮点，而非精选 Top N。

## 4. Evaluation 结果

| 维度 | 分数 | 说明 |
|------|------|------|
| coverage (关键词覆盖) | **0.0** | 生成内容中无 JD 关键词出现 |
| quant (量化占比) | 1.0 | 内容含大量数字指标 |
| clarity (清晰度) | 1.0 | 1,467 字符 < 4,000 阈值 |
| length (篇幅) | 1.0 | 在 150-4,000 范围内 |
| citation (引用检查) | 1.0 | 含 `-` 连接符 |
| **Total** | **0.65** | |

### 关键发现 #3：Evaluation coverage 与 Matching K-score 一致

评测引擎的 `coverage` 维度搜索的是生成内容中的 JD 关键词出现次数，结果同样是 0.0——与匹配引擎的 K-score 一致。这验证了两个引擎在关键词检测上的一致性。

## 5. 诊断总结

### 当前基线

- **Matching Total**: 0.5 / 1.0
- **Evaluation Total**: 0.65 / 1.0
- **Fabrication Guard**: PASS（无违规）
- **Evidence Eligibility**: 10/10（全部通过 results+artifacts 校验）

### 已确认问题

| # | 问题 | 影响 | 修复方向 |
|---|------|------|----------|
| 1 | Matching 引擎不搜索 `stack` 字段 | 关键词覆盖率恒为 0，无法区分证据卡质量 | 扩展 `RuleMatchingEngine` 搜索范围至 `stack` |
| 2 | 无关键词命中时全部卡分数相同 | 匹配报告无区分度，Top N 选择退化为全选 | 引入 `stack` 搜索后可解决 |
| 3 | JD 与证据卡语言不匹配 | JD 用英文技术栈（Java/Redis/Kafka），证据卡 tags 用中文 | 需要双语关键词映射或 LLM 语义匹配 |

### 待验证（需 LLM 接入）

- LLM 模式下的关键词覆盖率和匹配质量对比
- LLM 改写是否引入无证据内容（FabricationGuard 压力测试）
- LLM Evaluation 的解释层质量

## 6. 下步行动

1. **P0 — 修复 Matching 引擎**：扩展 `rule_scorer.py` 的搜索范围至 `EvidenceCard.stack` 字段
2. **P1 — LLM 模式对比**：接入 LLM API 后重新跑同一组数据，对比 rule vs LLM 的匹配分和生成质量
3. **P2 — 双语关键词映射**：建立中英文技术栈同义词表，提升 rule 模式下的关键词覆盖率

## 7. 复现命令

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

print(f"Matching Total: {report.score_breakdown.get('total')}")
print(f"Evaluation Total: {scorecard.total_score}")
PYEOF
```
