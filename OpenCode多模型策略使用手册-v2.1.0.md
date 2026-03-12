# OpenCode 多模型协同策略 — 使用手册（优化版）

> 手册版本：v2.1.0 | 修订日期：2026-03-09 | 适配 OpenCode：1.2.22
>
> 本版基于你当前真实可用资源重构：
> `Claude 订阅`、`OpenAI 订阅`、`GitHub Copilot 订阅`、`OpenCode Zen 免费`、`DeepSeek API Key`，
> 同时确认 `Gemini CLI 当前不可用`。
>
> 目标不是“平均使用所有模型”，而是：
> **把高价值任务尽量压到订阅额度里，把高频并发任务压到低成本通道里，把免费与备用通道设计成可持续溢出层。**

---

## 1. 本版相对旧版的关键修正

### 1.1 旧版的主要问题

1. 仍把 `Google / Gemini CLI` 放在主路由，但你当前实际上不可用。
2. 把 `GitHub Copilot` 只当应急备用，低估了它作为“跨家族溢出层”的价值。
3. 对 `Claude` 的定位偏理想化，没充分考虑你现在是**标准订阅**，不是 `Max`。
4. `DeepSeek` 只被当作便宜替补，没有被充分用作“高频并发主力”。
5. 没把“额度”拆成三种约束来管：
   - 订阅额度：主要受速率限制和公平使用影响
   - API 额度：主要受现金成本影响
   - 免费额度：主要受稳定性和能力上限影响

### 1.2 本版核心改法

1. `Gemini CLI` 退出主路径，不再做默认假设。
2. `OpenAI` 承担编码主路径。
3. `Claude` 退到规划、评审、关键决策，不再承担长时间高频流水线。
4. `DeepSeek` 升级为“高频探索 / 并发 background / 廉价一轮筛选”的主力。
5. `Copilot` 从 P3 纯兜底，提升为“订阅溢出层 + 跨模型家族补位层”。
6. `OpenCode Zen` 明确定位为“免费兜底层”，不是主战场。

---

## 2. 当前资源盘点

| 资源 | 当前状态 | 最适合承担什么 | 主要约束 |
|---|---|---|---|
| Claude 订阅 | 可用 | 规划、架构、复杂审查、最终定稿 | 标准订阅，长时间高强度并发容易限流 |
| OpenAI 订阅 | 可用 | 编码主力、复杂实现、关键修复 | 也有公平使用和速率限制，不适合无限并发 |
| GitHub Copilot 订阅 | 可用 | 直连模型受限时的跨家族溢出，尤其 Claude/GPT/Gemini 备用 | 延迟和稳定性通常不如直连 |
| OpenCode Zen | 免费可用 | 免费兜底、轻量知识任务、低优先级备用 | 能力和稳定性不建议承担关键路径 |
| DeepSeek API Key | 可用 | 高频、并发、探索、检索、粗筛、廉价推理 | 直接花钱，必须加预算护栏 |
| Gemini CLI | 当前不可用 | 不纳入默认策略 | 不可依赖 |

---

## 3. 优化后的路由总原则

### 3.1 三层目标

1. **关键路径尽量吃订阅**
   - 让最贵、最需要稳定质量的部分优先消耗 `OpenAI` / `Claude` 订阅。
2. **高频并发尽量吃 DeepSeek**
   - 把 explore、librarian、背景分析、文档初筛、批量比对压到 `DeepSeek`。
3. **超额与波动交给 Copilot / Zen**
   - 直连被限流、某家短时不稳定、需要不同模型家族时，用 `Copilot`
   - 免费兜底和低优先级任务，用 `OpenCode Zen`

### 3.2 新的优先级

| 优先级 | 通道 | 定位 |
|---|---|---|
| **P1** | OpenAI 订阅 | 编码与执行主路由 |
| **P1** | Claude 订阅 | 规划、评审、关键推理主路由 |
| **P2** | DeepSeek API | 高频、并发、探索、粗筛主路由 |
| **P3** | GitHub Copilot 订阅 | 订阅模型溢出层、跨家族补位层 |
| **P4** | OpenCode Zen 免费 | 免费兜底层 |
| **P5** | 本地 / 其他 | 离线或特殊场景备用 |

### 3.3 一条最重要的纪律

> **不要把最贵的模型放在最长的链路上。**
>
> `Claude` 和 `OpenAI` 负责“关键一击”。
> `DeepSeek` 负责“多轮试探、批量探索、廉价并发”。

---

## 4. 额度视角的最优分工

### 4.1 Claude：少量高价值，不做背景流水线

Claude 标准订阅最怕的不是单次使用，而是：

- 长会话
- 多并发
- 反复 revise
- 被拿去做本可以廉价完成的探索任务

**所以 Claude 的最佳用法是：**

- 需求澄清
- 方案对比
- 复杂 review
- 关键方案的最终定稿
- 风险评估

**不要默认让 Claude 做：**

- 全程 explore
- 大量 background task
- 扫库式检索
- 连续小步代码修补

### 4.2 OpenAI：承担编码主链路，但避免无意义长回合

OpenAI 订阅最应该用在：

- 实现主任务
- 改代码
- 修 bug
- refactor
- 复杂 diff 审查

但也要避免：

- 把“找资料、列候选、先粗筛”这类任务直接扔给 OpenAI
- 同一任务先后起多个 OpenAI 重型 agent 并发互卷

### 4.3 DeepSeek：把“并发价值”吃满

DeepSeek 最适合吃掉这些本来最浪费订阅额度的任务：

- 多文件初步扫描
- 文档检索和摘要
- 先列备选方案
- 生成初版 TODO
- 简单报错定位
- 批量日志/SQL/配置比对
- background explore / librarian

这类任务数量多、价值密度低、容易并发，最适合用 API 廉价吃掉。

### 4.4 Copilot：从“纯备用”升级为“溢出层”

Copilot 不该做默认主力，但非常适合：

- `Claude` 限流时，临时切 `github-copilot/claude-*`
- `OpenAI` 限流时，临时切 `github-copilot/gpt-*`
- 需要 `Gemini` 家族能力，但你本机 `Gemini CLI` 当前不可用时，走 `github-copilot/gemini-*`

一句话：

> `Copilot` 不是第一选择，但它是非常有价值的“订阅缓冲池”。

### 4.5 OpenCode Zen：免费兜底，不放关键路径

OpenCode Zen 适合：

- 免费 fallback
- 非关键问答
- 轻量总结
- 低优先级辅助 agent

不适合：

- 关键编码主链路
- 最终审查
- 高风险改动的唯一判断来源

---

## 5. 推荐的任务路由

### 5.1 编码实现类

| 任务 | 第一选择 | 第二选择 | 第三选择 |
|---|---|---|---|
| 功能开发 | OpenAI | Copilot GPT / Claude | DeepSeek 先分析后再升级 |
| Bug 修复 | OpenAI | Claude 审查 + OpenAI 修复 | Copilot GPT |
| 重构 | OpenAI | Claude 先定边界，再 OpenAI 落地 | Copilot |
| 大 diff review | Claude | OpenAI | Copilot Claude |

### 5.2 规划与架构类

| 任务 | 第一选择 | 第二选择 | 第三选择 |
|---|---|---|---|
| 需求拆解 | Claude | Copilot Claude | DeepSeek 初稿后升级 |
| 架构比较 | Claude | OpenAI 高阶模型 | Copilot Claude |
| 风险评审 | Claude | OpenAI | Copilot |
| 决策 memo | Claude | OpenAI | DeepSeek 初稿后润色 |

### 5.3 探索与检索类

| 任务 | 第一选择 | 第二选择 | 第三选择 |
|---|---|---|---|
| 全仓扫描 | DeepSeek Chat | OpenCode Zen | Copilot |
| 文档摘要 | DeepSeek Chat | Copilot Gemini | OpenCode Zen |
| 日志分析 | DeepSeek Chat | OpenAI | Claude |
| 快速问答 | DeepSeek Chat | OpenCode Zen | Copilot |

### 5.4 多模态与视觉类

由于 `Gemini CLI` 当前不可用，视觉/长上下文不要再默认依赖 Google 直连。

建议顺序：

1. `github-copilot/gemini-*`
2. `openai/gpt-5.4`
3. `OpenCode Zen`

---

## 6. 推荐的 Agent 分工

### 6.1 Native Agent 建议

| Agent | 推荐模型策略 | 原因 |
|---|---|---|
| `build` | OpenAI 主力 | 编码产出比最高 |
| `plan` | Claude Sonnet / Claude 主订阅 | 做规划，不要长期驻场 |
| `deep-reason` | DeepSeek Reasoner 起步，难题再升 OpenAI/Claude | 先省钱，再升级 |
| `reviewer` | Claude | 更适合做风险收敛与最终审读 |
| `batch` | DeepSeek Chat | 批量低价值任务最合适 |
| `cross-review` | OpenAI 或 Claude | 关键输出做第二视角 |

### 6.2 oh-my-opencode Agent 建议

原始自动配置能用，但对你当前额度结构并不最优。更适合你的使用法如下：

| Agent | 推荐默认 | 说明 |
|---|---|---|
| `sisyphus` | Claude Sonnet，而不是长期默认 Opus | 标准订阅下更耐用 |
| `hephaestus` | OpenAI Codex | 继续做重实现 |
| `oracle` | OpenAI 高阶模型 | 关键分析保质量 |
| `librarian` | DeepSeek Chat / OpenCode Zen | 不值得烧订阅 |
| `explore` | DeepSeek Chat | 高频、便宜、够快 |
| `prometheus` | Claude Sonnet 默认，难题再切 Opus | 把 Opus 留给真正难题 |
| `metis` | Claude Sonnet 默认，难题再切 Opus | 同上 |
| `momus` | OpenAI / Claude 二选一 | 做代码批判与质量收口 |
| `atlas` | DeepSeek Chat 或 Claude Sonnet | 看任务价值决定 |
| `multimodal-looker` | Copilot Gemini / OpenAI | 因为 Gemini CLI 当前不可用 |

### 6.3 你现在最该避免的配置

1. `sisyphus/prometheus/metis` 全部长期挂 `Claude Opus`
2. `librarian/explore` 还用订阅模型
3. 视觉任务继续默认写成 `google/gemini-*` 直连
4. `Copilot` 只留作最后一层，不参与正常额度调度

---

## 7. 最优工作流

### 7.1 默认工作流

1. `DeepSeek` 做第一轮 explore / 文档筛选 / 文件定位
2. `Claude` 做需求确认、方案裁剪、风险边界
3. `OpenAI` 做主实现
4. `Claude` 或 `OpenAI` 做最终 review

这个顺序的好处：

- 订阅模型只消耗在关键位置
- 便宜通道负责高频脏活
- 总体质量不降

### 7.2 高频任务工作流

适用于：

- 看日志
- 搜索配置
- 列候选方案
- 汇总报错

建议：

1. 先全部交给 `DeepSeek Chat`
2. 只有出现不确定结论，再升级到 `Claude` 或 `OpenAI`

### 7.3 高风险任务工作流

适用于：

- 大面积重构
- 安全相关
- 复杂并发 / 事务 / 一致性

建议：

1. `Claude` 先收边界
2. `OpenAI` 落实现
3. `Claude` 再做最终审查

---

## 8. 额度保护规则

### 8.1 Claude 保护规则

1. 同一时间最多只让一个 `Claude` 重型链路长跑。
2. 规划完成后立即切回 `OpenAI` 或 `DeepSeek`，不要让 Claude 持续占线。
3. `Opus` 只在以下场景使用：
   - 真正复杂的架构权衡
   - 多方案博弈
   - 最终高风险评审

### 8.2 OpenAI 保护规则

1. `OpenAI` 负责实现，不负责全仓扫描。
2. 同一任务不要同时起多个重型 `OpenAI` coder 并发。
3. 遇到“先搜再改”的任务，先交给 `DeepSeek` 做搜索。

### 8.3 DeepSeek 预算规则

如果你还没有明确预算，建议先用下面这套默认护栏：

| 维度 | 建议值 |
|---|---|
| 单任务软上限 | 3 元 |
| 单日软上限 | 10 元 |
| 单月软上限 | 200 元 |

触发规则：

1. 单任务多轮 explore 已经明显反复，立刻升到 `Claude` 或 `OpenAI`
2. 同类任务连续并发很多时，优先用 `DeepSeek`
3. 真正关键决策不要为了省几毛钱反复重试廉价模型

### 8.4 Copilot 使用规则

Copilot 建议只在以下场景启用：

1. `Claude` 直连被限流
2. `OpenAI` 直连被限流
3. 需要 `Gemini` 家族能力但你当前没有 `Gemini CLI`

不建议：

- 长期把所有默认路由都切到 Copilot

---

## 9. 推荐的降级链

### 9.1 编码链

`OpenAI -> Copilot GPT/Claude -> DeepSeek Chat（先分析）-> OpenCode Zen`

### 9.2 规划链

`Claude -> Copilot Claude -> OpenAI -> OpenCode Zen`

### 9.3 探索链

`DeepSeek Chat -> Copilot -> OpenCode Zen`

### 9.4 视觉链

`Copilot Gemini -> OpenAI -> OpenCode Zen`

---

## 10. 配置优化建议

本版不是让你“所有角色都升配”，而是让你把贵模型留给关键时刻。

### 10.1 应长期保留的思路

- `build` 继续偏 `OpenAI`
- `explore/librarian` 偏 `DeepSeek`
- `visual-engineering/artistry` 偏 `Copilot Gemini`
- `Zen` 保留在 fallback 链中

### 10.2 应避免的思路

- 把所有高层 agent 都堆到 `Claude Opus`
- 把 `Gemini CLI` 当作仍然可用的主通道
- 让 `DeepSeek` 只做边角料
- 让 `Copilot` 永远闲置

---

## 11. 场景化执行建议

### 11.1 日常开发

- 先 `DeepSeek` 探路
- 再 `OpenAI` 实做
- 最后 `Claude` 收口

### 11.2 紧急救火

- 首选 `OpenAI`
- 若限流，切 `Copilot GPT/Claude`
- 再不行走 `OpenCode Zen`

### 11.3 大型方案设计

- `Claude` 起方案
- `OpenAI` 验证可实现性
- `Claude` 最终审稿

### 11.4 大批量机械分析

- 全部优先压到 `DeepSeek`
- 只有异常样本再升级到订阅模型

---

## 12. 最终建议：你的最佳使用姿势

如果只保留一句话，建议是：

> **OpenAI 负责写，Claude 负责判，DeepSeek 负责跑量，Copilot 负责溢出，Zen 负责兜底。**

进一步拆开就是：

1. **OpenAI** 吃主实现
2. **Claude** 吃关键规划和最终 review
3. **DeepSeek** 吃 explore / librarian / batch / background
4. **Copilot** 吃限流和 Gemini 能力缺口
5. **OpenCode Zen** 吃免费 fallback

这是最符合你当前真实资源结构、也最兼顾额度与利用率的方案。

---

## 13. 版本升级说明

### v2.1.0

- 从“多家模型平均协同”改为“按额度类型分层调度”
- 移除 `Gemini CLI` 作为默认可用前提
- 提升 `DeepSeek` 为高频并发主力
- 提升 `Copilot` 为订阅溢出层
- 下调 `Claude` 的常驻负载，避免标准订阅过早限流
- 将手册目标改为“最大化模型利用率，同时保护额度”
