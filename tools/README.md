# 工具说明

本文件是 `tools/` 的命令行文档唯一真源。所有业务命令统一通过 v2 CLI 入口调用；
`tools/` 根目录不再保留按阶段拆分的脚本。

## 统一 CLI 入口

```bash
python3 -m tools.cli.entrypoints <command> [args]
```

命令：`extract` / `extract-batch` / `match` / `generate` / `evaluate` / `pipeline` / `agent` / `check` / `kb`

- 业务命令：入口只做参数解析并调用编排层（`tools/orchestration/`），业务实现位于
  `tools/engines/`，外部 IO/模型适配位于 `tools/infra/`。
- `check` 子命令：`arch`（分层/唯一实现/legacy 残留）、`roadmap`（路线图契约）、
  `aief`（AIEF L3）、`submission-readiness`（投递就绪）、`boss-cli`（外部 CLI
  live smoke），实现位于 `tools/tooling/`。
- `kb` 子命令：知识索引构建与查询（实现位于 `tools/tooling/knowledge.py`）。
- 分层约束由 `python3 -m tools.cli.entrypoints check arch --root .` 强制。

### 证据提炼（规则模式）

```bash
python3 -m tools.cli.entrypoints extract \
  --input tools/sample_raw.txt \
  --output evidence_cards/ec-2026-010.yaml \
  --id ec-2026-010
```

- `--input`：原始语料路径，`-` 表示 stdin。
- `--output`：输出 YAML；省略时打印到 stdout。
- `--id` / `--title`：覆盖卡 id / 标题。
- 规则抽取是确定性的：识别「背景/动作/结果/证据/技术栈」分节与常见技术栈/标签词，
  缺失字段写入 `gaps`，不编造内容。

### 证据提炼（LLM 模式）

```bash
python3 -m tools.cli.entrypoints extract \
  --input tools/sample_raw.txt \
  --output evidence_cards/ec-2026-011.yaml \
  --use-llm \
  --prompt tools/prompts/evidence-extraction.md
```

- `--model`：模型名，默认取 `LLM_MODEL`。
- `--base-url`：OpenAI-compatible 地址，默认按 provider 选择；Strata 固定使用
  App 管理的统一入口 `http://127.0.0.1:47831/v1`。
- `--api-key`：默认取 `LLM_API_KEY`；本地 keyless provider 无需密钥。
- keyless 本地 provider 缺少 base_url 时必须显式提供，不会静默落到 OpenAI 地址。

### 批量证据提炼（项目级）

把材料目录按项目聚类，产出待审核的证据卡草稿（不调用模型也能产出「项目规模卡」）：

```bash
# 先看有哪些项目簇（不写文件）
python3 -m tools.cli.entrypoints extract-batch \
  --material-id <material_id> --dry-run --min-documents 3

# 规则模式：产出项目规模卡（文档构成 + 规模事实，全部来自目录统计）
python3 -m tools.cli.entrypoints extract-batch --material-id <material_id>

# LLM 模式：产出业务卡（事实必须逐字可定位，否则剔除）
LLM_PROVIDER=lm_studio LLM_MODEL=qwen3.8-27b@q8_0 \
LLM_BASE_URL=http://127.0.0.1:1234/v1 LLM_TIMEOUT=900 \
python3 -m tools.cli.entrypoints extract-batch --material-id <material_id> --use-llm

# 后处理：回填来源绑定/project_key/卡分类、规范化时间与计划值
python3 -m tools.cli.entrypoints extract-batch --material-id <material_id> --repair

# 入池：按宪法第 1 条硬门槛逐卡校验（results/artifacts/来源），不合规直接拒绝
python3 -m tools.cli.entrypoints extract-batch --material-id <material_id> --approve-batch
```

- `--min-documents`：少于该文档数的簇不提炼（过滤碎片）；
- `--exclude-clusters assets,模板`：排除噪音簇；
- `--force`：忽略进度记录重跑；进度文件在 `outputs/batch_extract/<material_id>.json`，支持断点续跑与单簇失败隔离；
- 产出的卡默认 `status: draft` + `candidate_pool_eligible: false`，必须审核后才能进入候选池。

### 投递就绪检查

```bash
python3 -m tools.cli.entrypoints check delivery-ready --root . --check-llm
```

只读检查职业档案确认状态、入池卡合规性、可原生投递岗位、猎聘凭据存在性，
输出未就绪原因清单；不写文件、不访问平台、不读凭据内容。

### 匹配评分

```bash
# 规则评分（确定性，不调用模型）
python3 -m tools.cli.entrypoints match \
  --job-profile job_profiles/jp-2026-001.yaml \
  --evidence-dir evidence_cards \
  --output matching_reports/mr-2026-002.yaml

# 语义评审（逐批调用模型，结果带缓存与输入指纹）
python3 -m tools.cli.entrypoints match ... --use-llm

# 严格 LLM：任何语义失败都返回非零，不回退规则报告
python3 -m tools.cli.entrypoints match ... --use-llm --require-llm
```

- 证据池超过 `--llm-max-cards`（默认 8）时，只把规则分最高的前 N 张交给模型，
  但全部证据仍会分批评审。
- 退出码：`0` 成功；`1` LLM 必需但不可用/失败；`2` 岗位命中企业例外清单。

### 简历生成

```bash
python3 -m tools.cli.entrypoints generate \
  --matching-report matching_reports/mr-2026-002.yaml \
  --output-dir outputs \
  --evidence-dir evidence_cards \
  --job-profile job_profiles/jp-2026-001.yaml
```

- 产出 A/B 两版 Markdown 与 `.trace.json`：两版都通过校验后才落盘，避免 LLM
  中途失败留下看似完整的单版结果。
- `--resume-positioning technical_depth|delivery_owner|custom` 控制定位；
  `--use-llm` 时模型只选择证据卡，不改写证据字段；`--require-llm` 下选择失败即阻断。
- 生成阶段禁止引入新事实：字段等级、时间精度与措辞降级由
  `tools/engines/generation/template_assembler.py` 决定。

### 质量评测

```bash
python3 -m tools.cli.entrypoints evaluate \
  --input outputs/resume_mr-2026-002_A.md \
  --output outputs/scorecards/scorecard_mr-2026-002_A.md \
  --job-profile job_profiles/jp-2026-001.yaml
```

- 规则分项：关键词覆盖、量化占比、空话/重复、篇幅、逐条追溯；规则分数不可被
  模型改写。
- `--use-llm` 时补充语义评审合并与四层质量报告（合格/对位/优质/突出），
  LLM 判项带缓存与一次缺项纠错。
- 质量结论属于建议层，不拦截投递（投递硬门禁只涉及事实、授权与不可逆外部副作用）。

### 单次 pipeline（Quick Run 使用同一入口）

```bash
python3 -m tools.cli.entrypoints pipeline \
  --raw tools/sample_raw.txt \
  --job-profile job_profiles/jp-2026-001.yaml
```

- 四阶段进程内串联：证据提炼 → 匹配评分 → 简历生成 → 质量评测。
- 每次运行写统一 Run Record：`outputs/agent_runs/<run_id>/run_log.json` 与
  `summary.json`，事件含 `PIPELINE_START` / `PIPELINE_STEP_*` / `PIPELINE_DONE`。
- `--skip-evidence-extraction`：使用给定证据目录，不再提炼（Quick Run 使用）。
- `--use-llm` / `--require-llm` 语义与各阶段命令一致。
- 命中企业例外清单返回退出码 `2`（并写兼容审计文件 `outputs/<run_id>/run_log.json`）。

### Agent Loop

```bash
# dry-run：只生成执行计划与日志，不打开浏览器
python3 -m tools.cli.entrypoints agent \
  --policy policy.yaml --dry-run --run-id run-001 --output-dir outputs/agent_runs
```

10 状态机：INIT → DISCOVER → SCORE → GENERATE → EVALUATE → GATE → REVIEW →
DELIVER → LEARN → DONE。manual REVIEW 会写 `outputs/review_queue/<run_id>.json`
并返回 `REVIEW_PENDING`，不会未经审批进入投递。

## 知识索引与来源覆盖

`kb` 子命令复用材料库和已配置来源根，提供确定性目录、字面检索及原文回读。正文引用使用
material_id/document_id/sha256；附件目录、日期线索和设计计划不能直接当作个人实绩。

```bash
python3 -m tools.cli.entrypoints kb build
python3 -m tools.cli.entrypoints kb verify --json
python3 -m tools.cli.entrypoints kb coverage --status unindexed
python3 -m tools.cli.entrypoints kb coverage --status metadata_only --path 'sample-project/' --json
python3 -m tools.cli.entrypoints kb find --title-token 'DAG' --json
python3 -m tools.cli.entrypoints kb read <material_id> <document_id>
```

`coverage` 区分正文已收录、未纳入、来源不一致、规则过滤和仅目录；附件会标记本地
实体或 Git LFS 指针。不会自动下载、转换或纳入正文。`verify` 发现来源目录/已登记
资产变化后要求重建导航，冻结材料的刷新仍沿用原有确认流程。详见
`AIEF/docs/plans/2026-10-17-knowledge-index.md`。

## 投递与渠道工具

```bash
# dry-run：仅生成执行计划与日志
python3 -m tools.submission.run_submission \
  --platform liepin --job-url "https://www.liepin.com/job/xxxx" \
  --resume outputs/resume_mr-2026-005_A.pdf \
  --profile profiles/candidate_profile.yaml --dry-run

# 共享登录态刷新：写入 outputs/submissions/liepin/session/liepin
.venv/bin/python3 tools/setup_liepin_session.py \
  --session-dir outputs/submissions/liepin/session \
  --browser-channel chrome --timeout-ms 45000

# 投递就绪门禁（要求最新一次 run 为 submit + success + 至少 1 张截图）
python3 -m tools.cli.entrypoints check submission-readiness \
  --root outputs/submissions --platform liepin --require-status success --min-screenshots 1

# 从已验证 Job Lead 生成 External L3 确认包（默认脱敏 JSON，不触发外部提交）
python3 -m tools.acceptance.external_l3_job_lead_bridge \
  --lead-source job_leads/jl-validated-20260513.yaml \
  --lead-index 1 \
  --resume-pdf uploaded_resumes/rv_49ab4b78.pdf \
  --profile profiles/candidate_profile.yaml \
  --session-dir outputs/submissions
```

真实猎聘搜索默认关闭，避免 dry-run / 单元测试意外触发平台访问；需要搜索真实职位时
显式开启：`export PPF_ENABLE_LIEPIN_SEARCH=1`。

## 企业例外清单

可以在仓库根目录放置 `policy.yaml`（或设置环境变量 `PPF_POLICY_PATH` 指向文件）
来定义需要排除的企业名单。

生效的策略文件按以下顺序解析：环境变量 `PPF_POLICY_PATH` > 仓库根目录已存在的
`policy.local.yaml`（已被 .gitignore 忽略）> 仓库默认 `policy.yaml`。sidecar 设置页的
读写、排除名单加载和投递前的排除检查都使用同一规则。

本机 LLM、投递模式等只适合当前机器的运行配置应写入 `policy.local.yaml`：只要该文件
存在，App 就不会再把本机配置写回仓库跟踪的 `policy.yaml`（首次可
`cp policy.yaml policy.local.yaml`）。也可以用环境变量显式指定：

```bash
PPF_POLICY_PATH=policy.local.yaml ./app start
PPF_POLICY_PATH=policy.local.yaml python3 -m tools.cli.entrypoints agent --policy policy.local.yaml --dry-run --run-id run-001 --output-dir outputs/agent_runs
```

支持以下字段（均为字符串列表）：

- `exclusion_list`：简单名单，按精确匹配处理。
- `excluded_companies`：支持 `exact:` / `contains:` 前缀。
- `excluded_legal_entities`：简单名单，按精确匹配处理。
- 也兼容 OpenSpec 中的 `filters.excluded_companies` / `filters.excluded_legal_entities` 结构。

匹配优先级：

- `excluded_legal_entities` 优先于企业展示名/别名匹配。
- `excluded_companies` / `exclusion_list` 用于展示名、常用名、别名过滤。

示例：

```yaml
excluded_companies:
  - "exact:Acme Inc"
  - "contains:外包"
excluded_legal_entities:
  - "某某人力资源有限公司"
```

也支持：

```yaml
filters:
  excluded_companies:
    - match: exact
      value: "示例科技有限公司"
    - match: contains
      value: "外包"
  excluded_legal_entities:
    - "某某人力资源有限公司"
```

> BOSS/智联只读职位发现是项目旧 adapter 接口，尚未适配上游 2.0.0；该路径只调用外部
> `boss-agent-cli` 的 schema/status/search/detail 读操作，不启用投递写操作。默认关闭，
> 需要时显式设置 `PPF_ENABLE_BOSS_AGENT_SEARCH=1` 与 `PPF_BOSS_AGENT_CLI`。版本/命令/
> 字段迁移见 `AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md`。

## 打包副本约定

- `tools/README.md` 是工具文档的 source of truth。
- `ui/src-tauri/resources/tools/README.md` 是由 `python3 ui/scripts/stage_python_runtime.py`
  在打包前 staging 出来的资源副本。
- 需要更新工具说明时，只修改 `tools/README.md`，然后重新执行 staging / build；
  不要直接修改 `ui/src-tauri/resources/tools/README.md`。

## CI 校验

- `.github/workflows/aief-l3-check.yml`：在 `pull_request` 与 `develop/main/master` push
  时触发；仅当 `.github/workflows/aief-l3-check.yml`、`AIEF/**`、`tools/tooling/**`、`tools/cli/**`
  变更时运行 `python3 -m tools.cli.entrypoints check aief --root . --base-dir AIEF`。
- `.github/workflows/ui-packaged-smoke.yml`：在 `pull_request` 与 `develop/main/master`
  push 时触发；仅当 `ui/**`、`tools/**`、`tests/**`、`evidence_cards/**`、
  `matching_reports/**`、`job_profiles/**` 或 workflow 自身变更时运行
  `npm run smoke:app`。
- `release-notes/**` 变更不会单独触发上述 workflow；当前策略默认只对会影响门禁结果的
  路径执行 CI。
