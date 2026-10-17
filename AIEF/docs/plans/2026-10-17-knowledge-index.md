# 知识索引（Knowledge Index）设计与实施计划

> 设计日期：2026-10-17 ｜ 状态：已确认（小样评审通过）｜ 目标阶段：Phase 1（CLI 先行）

**目标**：把全部本机知识资产（材料/证据卡/职业档案/岗位画像）建成一层确定性、可校验的导航索引，让 AI 用「目录 + 字面检索 + 回读原文」查询，而不是 RAG。

**架构**：`tools/infra/knowledge_index.py`（纯函数构建器与查询）→ `tools/kb.py`（CLI 薄壳）→ `knowledge-index/`（本地产物 index.json + INDEX.md，不入库）。Phase 2 在侧车加 RPC 薄适配复用同一模块。

**关键纪律**：索引只做导航，派生值（日期窗口/类型）不是事实；引用必须携带 `material_id / document_id / sha256` 三元组；合成夹具材料（mat_quick_run_verify）永不作事实来源。

---

## 数据模型（与评审小样一致）

- **material**：material_id, label, kind, filename, sha256, bytes, document_count, frontmatter_dated, date_hint_docs, documents[]
- **document**：document_id, label, path[], doc_type, title, chars, sha256, dates{frontmatter, window}, person_doc
- **card**：card_id, title, status, time_range, role_scope, candidate_pool_eligible, missing[], date_hints[], employer, source_documents[], sha256, demo
- **profile**：revision, file_sha256, work[{id,company,short,start,end,evidence_ids}], job_preferences{confirmed_at, source ref}
- **job**：job_id, target_role, company, status, jd_sha256, jd_chars, sha256, demo
- **relations**：card→cites→doc、work→evidence→card、job_preferences→sourced_from→doc
- **source_coverage**：roots / items（root_id、path、kind、status、availability、references）/ counts / excluded_counts / errors；附件与未纳入项只作导航，不新增事实。
- **asset_inventory**：已登记实体文件路径及指纹，补足 verify 对新增、删除和 meta 变化的检测。

## 派生规则（全部确定性）

- `doc_type`：按 label 后缀命中：速读卡/业务地图/架构切片/验收/发布/复盘/术语表/总结/需求/方案/日志/清单/手册/规范/索引 → 否则「文档」
- `title`：frontmatter `title:` → 首个 `# 标题` → 文件名
- `dates.frontmatter`：正文前 600 字符内 `created/updated: 'YYYY-MM-DD…'`
- `dates.window`：全文 `YYYY[-./年]M` 归一后的 min–max（YYYY-MM）
- `person_doc` 白名单（含备注）：mat_331bc1bc 时间线 / mat_723e3040 EC+详细底稿 / mat_ff4f2006 九恒星项目经验 / mat_2e91704b 早期经历 / mat_4c98d63a 作品集 / mat_ae7f0dbd Sophon 排练稿 / mat_2b6f65a5 方向分析 / mat_660ac6d6 众安月志 /（mat_7dad703c 内 label 为 工作汇总-1.md、工作汇总.md）
- `card.missing`：time_range / role_scope 为空（或时间不可解析）即缺
- `card.date_hints`：引用文档 window 合并去重，上限 6
- `card.employer`：由 profile work.evidence_ids 反查；简称映射 一里智辉→EC+、众安保险→众安、九恒星→九恒星、伊尔普→伊尔普

## CLI 契约（tools/kb.py，均支持 --json）

```
kb build [--root .] [--out knowledge-index]
kb tree <material_id> [path前缀]
kb find [--type T] [--material M] [--path P] [--title-token K] [--date-from] [--date-to] [--limit N]
kb grep <字面量> [--scope docs|cards|jobs|all] [--material M] [--limit N]
kb read <material_id> <document_id>             # 回读并校验档号；失效拒绝(exit 2)
kb refs <card_id|work_id>
kb cards [--missing time|role|any] [--has-date-hints] [--employer X] [--include-demo]
kb person-docs
kb verify
kb coverage [--root-id ID] [--path PREFIX] [--status indexed|unindexed|stale|filtered|metadata_only|unavailable] [--limit N] [--json]
kb index
```

退出码：0 正常；2 引用失效/校验失败；1 参数或环境错误。

## 实施任务（TDD，逐步提交）

### Task 1：构建器核心——材料与文档
- 测试 `tests/unit/infra/test_knowledge_index.py`：合成 tmp 根（materials 含 meta+包/单档、含 frontmatter 日期与文件名日期），断言 material 统计与 document 派生（doc_type/title/dates/window/sha）
- 实现 `tools/infra/knowledge_index.py: build_index(root, out=None, now=None)` 的 materials/documents 部分

### Task 2：卡片、雇主、缺字段与日期线索
- 测试：真卡（缺 time/role、引用某档）→ missing/date_hints/employer/sha；示例卡（无 status）→ demo=true
- 实现 cards 段与 profile work 反查

### Task 3：档案、岗位画像与关系
- 测试：profile(work/evidence_ids/job_preferences source)、jobs(真/示例)、relations 三类边
- 实现对应段

### Task 4：INDEX.md 生成
- 测试：板块齐全（资产盘点/材料树/非事实警示/待办信号/使用说明）
- 实现 `render_index_md(index)`

### Task 5：verify（失效检测）
- 测试：篡改材料/卡片/档案文件 → verify 报 stale
- 实现 `verify_index(root, index)`

### Task 6：CLI 全部命令 + --json
- 测试 `tests/unit/test_kb_cli.py`：capsys 断言 tree/find/grep/read/refs/cards/person-docs 输出；read 失效 exit 2
- 实现 `tools/kb.py`

### Task 7：真机验收与配置
- `.gitignore` 增加 `knowledge-index/`
- 真实数据 `kb build`：断言 16 材料/1121 档/51+10 卡/22+5 画像；小样同款命令抽查（refs ec_418bec8b 等）

### Task 8：收口
- 全量回归 +（可选）独立审查；台账/路线图补记；分组提交

## 2026-10-17 覆盖补齐切片

- 已有能力：`material.reference.scan/create` 可直接纳入允许根内的六份工作流设计/实施文本；`split_material_documents`、索引构建、find/grep/read 均复用。
- 实际缺口：上游未纳入文件、附件及拆档过滤项未进入导航；原“全量资产已纳入”只检查已登记实体；verify 不发现新增实体。
- 最小补齐：在同一 index.json 增加 `source_coverage`（来源根、文件相对路径、状态、可用性、正文引用、计数和扫描错误）。由 infra 中的目录盘点函数生成，`kb coverage [--root-id ID] [--path PREFIX] [--status STATUS] [--limit N] [--json]` 薄适配查询。文本指纹与现有文档比对；附件只读文件头判断 LFS 指针，保持 metadata_only，不转换或下载。
- 数据边界：只扫描既有本机材料来源白名单；隐藏目录剪枝、符号链接与敏感名跳过；解析过滤规则与证据选材共用。学习资料和模板仍可显示为未纳入或过滤项，不能自动成为个人经历。
- 验收：先失败测试覆盖漏文本、过滤项、本地/LFS 附件、来源变化、缺失目录、符号链接/敏感边界、实体新增及 CLI；六份真实文本通过既有引用入口创建，再构建索引、find/grep/read 与覆盖盘点回读。仅声明 CLI/材料入口验证，不提升 GUI 深度验收状态。
- 已实施：12 项新回归覆盖上述边界及 CRLF、分片顺序、跨快照拼接、非 UTF-8 和 `--root` 策略。六份设计/实施文档已通过引用入口纳入；材料 24 份/正文 6,601 档，六份检索与回读通过。附件仅目录覆盖结果、全量回归环境区别见同日项目台账。

## 测试基线命令

```
python -m pytest tests/unit/infra/test_knowledge_index.py tests/unit/infra/test_knowledge_coverage.py tests/unit/test_kb_cli.py -q
python -m pytest tests/unit -q          # 全量回归
```
