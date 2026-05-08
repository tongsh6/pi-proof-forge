# Benchmark 003 — LLM vs Rule 全对比

> 日期：2026-05-08
> LLM：LM Studio `openai/gpt-oss-120b` @ localhost:1234
> 数据集：jp-2026-001 (Backend Tech Lead) + 10 张证据卡

## 对比总览

| 指标 | Rule | LLM | 胜出 | 解读 |
|------|------|-----|------|------|
| Matching K-score | 0.600 | **0.730** | LLM | LLM 语义理解更全面 |
| Matching Total | **0.800** | 0.770 | Rule | Rule Q/E 恒为 1.0，LLM 更审慎 |
| 选中卡数 | 10/10 | **3/10** | LLM | LLM 选择性更强，简历更聚焦 |
| Gap Tasks 数量 | 2 | **4** | LLM | LLM 发现更多具体缺口 |
| Gap Tasks 质量 | 模板化 | **可执行** | LLM | "SLA/SLO monitoring" vs "补充X相关证据" |
| Eval Coverage | 0.0 | 0.0 | 持平 | 评测引擎需改进语义匹配 |
| Eval Total | 0.65 | 0.65 | 持平 | 同上 |
| Matching 耗时 | <0.01s | 7.9s | Rule | 规则引擎快 3 个数量级 |
| Generation 耗时 | <0.01s | 3.6s | Rule | LLM 改写增加 3.6s 延迟 |
| Fabrication Guard | PASS | PASS | 持平 | 两者均无事实编造 |

## LLM Matching 详细结果

### 选中的证据卡（3/10）

| 证据卡 | Rule 分 | LLM 选 | 理由 |
|--------|---------|--------|------|
| ec-2026-001 高峰期订单系统稳定性治理 | 0.800 | ✅ | 稳定性治理直接命中 must_have |
| ec-2026-011 微服务平台从零搭建 | 0.700 | ✅ | Java/Redis 栈 + 架构经验 |
| ec-2026-013 活动报名状态机扩展 | 0.700 | ✅ | 跨模块协作 + 高并发处理 |

### LLM 缺口任务（比 Rule 更具体）

| 缺口 | 来源 |
|------|------|
| Demonstrated experience with SLA/SLO definition and monitoring | LLM |
| Explicit high-concurrency system design details | LLM |
| Clear evidence of cross-team collaboration | LLM |
| Kafka usage in the majority of selected projects | LLM |

### Rule 缺口任务（模板化）

| 缺口 | 来源 |
|------|------|
| 补充 高并发系统设计 相关证据 | Rule |
| 补充 跨团队协作 相关证据 | Rule |

## LLM Generation 对比

### Rule TemplateAssembler 输出（380 chars）
```
# Resume v1-rule
## Highlights
- 高峰期订单系统稳定性治理
  - 故障率下降 43%
- 亚玛芬运动中心微服务平台从零搭建
  - 平台支撑始祖鸟...
```

### LLM Rewriter 输出（419 chars）
```
## Highlights
- **高峰期订单系统的稳定性治理**
  - 将故障率降低了 43%。
- **亚玛芬运动中心微服务平台从零搭建**
  - 支撑始祖鸟、萨洛蒙、FILA Golf、Kolon 等多品牌业务...
- **始祖鸟活动报名邀约同行人功能：跨四模块状态机扩展**
  - 在四个模块中统一上线邀约同行人能力...
```

**差异**：LLM 使用粗体强调、更自然的措辞、无事实新增。

## 诊断

### LLM 优势
1. **语义匹配**：K-score 0.73 > 0.60，理解 "稳定性治理" 与 "SLA" 的语义关联
2. **精准筛选**：3/10 而非 10/10，生成更聚焦的简历
3. **可执行缺口**：具体指出缺少什么（"SLA/SLO monitoring"），而非模板化提示
4. **措辞优化**：保留事实的前提下提升表达质量

### LLM 劣势
1. **延迟高**：匹配 7.9s + 生成 3.6s ≈ 12s（Rule < 0.01s）
2. **非确定性**：同输入多次运行可能得到不同结果
3. **依赖外部服务**：需要 LM Studio 运行

### 评测引擎局限
- **Coverage 恒为 0**：评测用纯文本匹配 JD 关键词，LLM 改写后的内容虽语义相关但不含字面关键词
- **改进方向**：LLM Evaluator 的语义解释层应能覆盖这一问题

### 建议的混合策略
1. **Rule 初筛 + LLM 精选**：Rule 快速过滤（<0.01s），LLM 对 Top5 深度评分（~8s）
2. **Rule 生成 + LLM 改写**：TemplateAssembler 确保事实保真，LLMRewriter 优化表达
3. **LLM 缺口发现**：用 LLM 生成可执行的补证据任务

## 复现命令

```bash
# 需要 LM Studio 运行在 localhost:1234，模型 openai/gpt-oss-120b
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
generation_reg = composer.build_generation_registry()
composer.add_llm_strategies(client, "openai/gpt-oss-120b",
    composer.build_evidence_registry(), matching_reg, generation_reg,
    composer.build_evaluation_registry())

rule = matching_reg.create("rule").score(cards, jp)
llm = matching_reg.create("llm").score(cards, jp)
print(f"Rule: total={rule.score_breakdown.get('total'):.3f} K={rule.score_breakdown.get('K'):.3f} cards={len(rule.evidence_card_ids)}")
print(f"LLM:  total={llm.score_breakdown.get('total'):.3f} K={llm.score_breakdown.get('K'):.3f} cards={len(llm.evidence_card_ids)}")
print(f"LLM gaps: {llm.gap_tasks}")
PYEOF
```
