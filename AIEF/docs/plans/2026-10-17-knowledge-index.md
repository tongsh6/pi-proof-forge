# 知识索引（Knowledge Index）设计与实施计划

> 设计日期：2026-10-17 ｜ 状态：已确认（小样评审通过）｜ 目标阶段：Phase 1（CLI 先行）

**目标**：把全部本机知识资产（材料/证据卡/职业档案/岗位画像）建成一层确定性、可校验的导航索引，让 AI 用「目录 + 字面检索 + 回读原文」查询，而不是 RAG。

**架构**：`tools/infra/knowledge_index.py` 承担构建与工程导航查询，既有应用用例直接复用，`knowledge-index/` 的 index.json 与 INDEX.md 是不入库的本地派生物。CLI 不是应用内部 API；原设想的单独构建 RPC 不再新增，当前接入见下述 L4。

**关键纪律**：索引只做导航，派生值（日期窗口/类型）不是事实；引用必须携带 `material_id / document_id / sha256` 三元组；合成夹具材料（mat_quick_run_verify）永不作事实来源。

---

## 数据模型（与评审小样一致）

- **material**：material_id, label, kind, filename, sha256, bytes, document_count, frontmatter_dated, date_hint_docs, documents[]
- **document**：document_id, label, path[], doc_type, title, chars, sha256, dates{frontmatter, window}
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
- 索引不按材料 ID、文件名或私人白名单推断“个人权威文档”。检索优先使用已绑定且指纹一致的具体原文；其他文档按现有相关性召回，任何导航标签都不授予事实权威。
- `card.missing`：time_range / role_scope 为空（或时间不可解析）即缺
- `card.date_hints`：引用文档 window 合并去重，上限 6
- `card.employer`：由 profile work.evidence_ids 反查；公司名称和简称复用通用 `company_aliases` 规则，不维护个人雇主映射。

## CLI 契约（tools/kb.py，均支持 --json）

```
kb build [--root .] [--out knowledge-index]
kb tree <material_id> [path前缀]
kb find [--type T] [--material M] [--path P] [--title-token K] [--date-from] [--date-to] [--limit N]
kb grep <字面量> [--scope docs|cards|jobs|all] [--material M] [--limit N]
kb read <material_id> <document_id>             # 回读并校验档号；失效拒绝(exit 2)
kb refs <card_id|work_id>
kb cards [--missing time|role|any] [--has-date-hints] [--employer X] [--include-demo]
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
- 测试 `tests/unit/test_kb_cli.py`：capsys 断言 tree/find/grep/read/refs/cards 输出；read 失效 exit 2
- 实现 `tools/kb.py`

### Task 7：真机验收与配置
- `.gitignore` 增加 `knowledge-index/`
- 使用明确合成的材料、卡、档案和岗位验证 build/refs/read/verify；真实资料验收在授权范围内执行，具体个人数据与统计只留本地运行记录。

### Task 8：收口
- 全量回归 +（可选）独立审查；台账/路线图补记；分组提交

## 2026-10-17 覆盖补齐切片

- 已有能力：`material.reference.scan/create` 可纳入允许根内的文本；`split_material_documents`、索引构建、find/grep/read 均复用。
- 实际缺口：上游未纳入文件、附件及拆档过滤项未进入导航；原“全量资产已纳入”只检查已登记实体；verify 不发现新增实体。
- 最小补齐：在同一 index.json 增加 `source_coverage`（来源根、文件相对路径、状态、可用性、正文引用、计数和扫描错误）。由 infra 中的目录盘点函数生成，`kb coverage [--root-id ID] [--path PREFIX] [--status STATUS] [--limit N] [--json]` 薄适配查询。文本指纹与现有文档比对；附件只读文件头判断 LFS 指针，保持 metadata_only，不转换或下载。
- 数据边界：只扫描既有本机材料来源白名单；隐藏目录剪枝、符号链接与敏感名跳过；解析过滤规则与证据选材共用。学习资料和模板仍可显示为未纳入或过滤项，不能自动成为个人经历。
- 验收：先失败测试覆盖漏文本、过滤项、本地/LFS 附件、来源变化、缺失目录、符号链接/敏感边界、实体新增及 CLI；通过既有引用入口创建合成材料，再构建索引并回读。CLI/材料入口验证不提升 GUI 深度验收状态。
- 已实施的工程回归覆盖上述边界及 CRLF、分片顺序、跨快照拼接、非 UTF-8 和 `--root` 策略。个人材料盘点、文件量和本机覆盖结果不写入应用仓库。

## 应用接入：L4 推断输入准备（限定工程与合成应用验收完成）

- 当前实际消费者为 evidence.inferFields；build_index 已有，但此前只有 knowledge CLI 构建，应用只读预生成文件。复用构建器在有实际目标的请求中准备当前索引，不增构建 RPC，不让日常推断依赖开发者命令。
- 每次按需重建避免依赖 verify 对 skipped 正文恢复等尚不完整的复用判断；不新增 dirty 字段。现 CLI 继续共用 infra 承担工程导航与诊断，不维护另一套应用流程。
- 索引不是事实来源：引用材料未确认 refresh 时，即使新索引仍列旧文档，实际推断也必须校验当前登记、允许根、manifest 与精确原文。全库覆盖诊断不成为单卡来源门禁。
- 复用现有 material_id/document_id/sha256、ValidatedSourcePaths 与原子写；实际读取和发布校验归原推断消费者。单份材料元数据、正文与摘要应同版，不用构建末端重新取值为旧解析补新版本。没有第二索引、来源副本、业务脚本或事务框架。
- 具体权威、缓存、启停和版本竞争边界归 evidence-provenance R4.5；本片先闭合推断输入与候选发布，确认已存候选的来源复核随后处理。
- 最终全量 2874 passed、1 skipped、101 subtests passed；原 8 RPC 合成应用去掉索引 bootstrap 后，经 1 次本机 Splash 验证由 inferFields 创建 index.json/INDEX.md，候选引用同版、原卡不变。不是原生 UI、候选确认或正式件验收。

## 测试基线命令

```
python -m pytest tests/unit/infra/test_knowledge_index.py tests/unit/infra/test_knowledge_coverage.py tests/unit/test_kb_cli.py -q
python -m pytest tests/unit -q          # 全量回归
```
