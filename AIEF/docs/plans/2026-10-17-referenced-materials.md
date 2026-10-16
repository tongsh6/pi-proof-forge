# 引用式材料（Referenced Materials）设计与实施计划

> 设计日期：2026-10-17 ｜ 状态：已确认 ｜ 性质：App 一级能力（材料引用）首个切片

**目标**：让 App 可以"引用"允许来源根内的外部文件/目录作为材料——不复制原件、内容变更可被发现并阻断，证据/生成/档案/索引全链路可用。首个真实用例：`worklog-private/00-EC+/10-projects/亚玛芬/始祖鸟`（约 5,076 个未入库文件）。

**为什么不用复制/链接**：快照复制会产生不跟随源的副本；符号/硬链接被证据契约明确拒绝（静默可变）。引用式材料以"冻结清单 + 逐文件 sha256 + 读取前校验"实现单源真相与变更可发现。

---

## 一、数据模型

材料 meta 扩展（快照材料行为不变）：

```
source_mode: "referenced"            # 未写 = 快照（兼容旧材料）
source_root: "<允许根绝对路径>"
source_relpath: "<根内相对路径>"
manifest_sha256: "<清单哈希>"
file_count: "N"
```

- 清单文件：`materials/.referenced/{material_id}.manifest.json`
  `{ "root": "...", "relpath": "...", "files": [{"relpath","sha256","bytes"}], "skipped": [...], "created_at": "..." }`
- 合并缓存：`materials/.referenced/{material_id}-{manifest_sha256[:12]}.txt`（`# Source:` 分隔，同导入器格式；派生、可重建、非事实源）
- **清单冻结语义**：内容变更/文件删除 → 校验失败（阻断）；新增文件不自动进入（状态报告 added，刷新后纳入）

## 二、允许来源（App 设置能力）

- 本机 policy 字段 `material_source_roots_json`：`[{"id":"msr_xxxxxxxx","label","path"}]`（私有路径，不提交仓库）
- 系统设置页新增「材料来源」节：添加/移除
- 安全规则（scan/create/verify 共用）：
  - 目标 resolve 后必须位于某个允许根内；拒绝符号链接文件与穿越
  - 只收 `.md/.txt`；跳过 dot 开头路径、空文件、敏感名（secret/token/密码/passwd/credential/私钥）
  - 无允许根 → 引用能力关闭（RPC 报 `material_source_root_required`）

## 三、RPC（sidecar）

| RPC | 行为 |
|---|---|
| `materials.reference.scan` | `{root_id, relpath}` → 预览：file_count/total_bytes/sample_files(≤20)/skipped/重叠提示 |
| `materials.reference.create` | `{root_id, relpath, label}` → 建 manifest+缓存+meta；返回材料项 |
| `materials.reference.status` | `{material_id}` → 重扫源 → `ok` 或 `changed`（changed/added/removed 摘要） |
| `materials.reference.refresh` | `{material_id, confirmed:true}` → 重建 manifest+缓存（新清单）；已绑定卡片随指纹失配进入"来源已变更，需重审" |
| `materials.reference.remove` | `{material_id, confirmed:true}` → 删 meta+manifest+缓存（不动源） |

- `settings.get` 返回 `material_source_roots`；`settings.update` 接受该字段（校验路径存在/去重/非材料库自身）
- `materials.list` 项增加 `source_mode`、`reference`（root/relpath/file_count）

## 四、证据链集成（关键）

- 读取校验统一入口：`validated_source_inputs` 指纹条目新增 `mode`；referenced 时：
  1. 按 `source_root`+`source_relpath` 重扫并比对 `manifest_sha256` 与逐文件哈希
  2. 校验缓存文件 sha256
  任何不符 → `material_source_changed`（证据/职业档案/run_generation/agent 四处自动生效）
- 草稿与生成读取：`_selected_text_materials` 对 referenced 先校验；变更 → 阻断并提示刷新（绝不把过期内容放进草稿）
- 指纹形状（saveDraft 写入）：
  `{material_id: {filename: ".referenced/...txt", sha256: <缓存哈希>, mode: "referenced", manifest_sha256, source_root, source_relpath}}`

## 五、UI

- 系统设置「材料来源」：列表 + 添加（路径输入 + 校验反馈）+ 移除
- 证据页材料库：「引用外部目录」入口（选根 → 相对路径 → 扫描预览 → 命名 → 创建）；列表项「引用」徽标 + 文件数；操作：状态检查/刷新/解除引用（刷新与解除需确认）
- i18n 中英；DESIGN.md 与 `.pen` 同步（pencil 工具可用后执行）

## 六、kb 集成

- 校验与合并逻辑抽到 `tools/infra/referenced_materials.py`（sidecar 与 kb 共用）
- `kb build`：referenced 材料按缓存建文档，标 `source_mode: referenced` + `reference_status`（校验 manifest；changed 时如实标注）；assets 行注明引用材料数
- `kb verify`：纳入 referenced 的 manifest 校验
- INDEX「范围说明」：上游来源改为"以引用材料纳入"

## 七、实施任务（TDD）

1. **infra resolver**（`tools/infra/referenced_materials.py`）
   - 测试 `tests/unit/infra/test_referenced_materials.py`：确定性 manifest、变更/删除→changed、新增→added、敏感跳过、containment 拒绝、合并文本格式
2. **设置白名单 + 引用 RPC**（`tools/policy/exclusions.py` + `tools/sidecar/handlers/materials.py` + `server.py`）
   - 测试 `tests/unit/sidecar/test_materials_reference.py`：scan/create/status/refresh/remove、根校验、list 字段、`_selected_text_materials` 阻断
3. **证据链接入**（`tools/infra/evidence_sources.py` + 指纹写入）
   - 测试：引用材料建草稿→保存→校验通过；改源文件→validated 报 changed；刷新→旧指纹失配
4. **UI**（system-settings + evidence 页 + i18n）
   - GUI 测试（node transpile 模式）：入口按钮、扫描→创建流、徽标与操作
5. **kb 集成**（`tools/infra/knowledge_index.py` + `tools/kb.py`）
   - 扩展既有测试；真实数据重建
6. **文档与验收**：openspec/RPC 文档、DESIGN.md、导出 `.pen` 同步、台账/路线图；首用创建始祖鸟引用 + 全链路冒烟 + 回归 + 独立审查

## 八、验收口径

- 始祖鸟树（5,076 文件）经 App UI 创建为引用材料；kb documents 1610 → ~6,800
- 证据流：可选该材料生成草稿并保存（指纹含 manifest 校验）
- 改源文件 → 全链路阻断并提示刷新；刷新后确认语义正确（旧绑定重审）
- 回归全绿；无平台写入；快照材料与旧指纹完全兼容
