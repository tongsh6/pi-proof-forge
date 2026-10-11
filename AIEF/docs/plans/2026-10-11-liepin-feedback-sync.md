# 猎聘投递反馈回流（P0-025 `liepin_feedback_sync`）

日期：2026-10-11。状态：设计已定，首片实施中。用户决定：先深化 App 与猎聘渠道，优先补齐愿景中"投递与反馈回流"一段的真实数据。

## 1. 目标与边界

- 目标：对 App 已完成的每笔真实猎聘投递（默认简历 API 路线与原生 PDF 路线共 16 笔），在 App 自有猎聘会话内只读读取平台展示的投递进展（已投递、已查看、感兴趣、不合适、面试邀约等），落为可追溯的反馈来源，驱动现有"补证据 / 调岗位 / 重新生成"的下一轮计划，并在总览展示投递漏斗。
- 为什么不走官方 API：2026-09-08 调研实际取得的 14 个官方 MCP 工具只有简历维护、搜索与投递，官网说明"投递进展通过 App 消息和短信触达，Agent 查询进展属于后续能力"。因此反馈只能由 App 自己的已登录 WebView 会话读取页面，这与现有附件检查、沟通页观察同一边界。
- 只读边界：同步只允许导航到 `c.liepin.com` 下的用户中心与投递记录页并读取页面；不点击"聊一聊 / 发简历 / 发送 / 投递 / 删除"等业务控件，不发消息，不改平台简历。与原生 PDF 操作共用 `NativeOperationGuard` 互斥，每日批次运行中不同步。
- 不编造：页面没有识别出的状态一律记为 `unknown`；找不到投递记录页时记录 `records_page_not_found` 与脱敏后的候选链接列表，不猜测状态；历史回执、投递日志、批准快照、SQLite 尝试记录一律不改。

## 2. 复用点与缺口

| 已有 | 复用方式 |
| --- | --- |
| `tools/sidecar/handlers/submission.py` 的反馈项 `_feedback_items_from_submission_log`、迭代记录 `_create_managed_feedback`、来源集合 `_ALLOWED_FEEDBACK_SOURCES` | 新增来源 `platform_delivery_status`；迭代动作与记录格式不变 |
| `tools/sidecar/handlers/native_pdf._sanitize_observation` | 观察入库前统一脱敏与去 query |
| Rust `liepin_webview.rs` 的会话检查、`allowed_navigation`、`run_pdf_script`、`NativeOperationGuard` | 新命令 `sync_liepin_feedback` 复用同一会话与观察回传机制 |
| 线索文件 `job_leads/<id>.yaml` 的 `platform_job_id` 与 `url` | 16 笔受控投递均可取得岗位编号，用于与页面行匹配 |
| Submissions 页"PDF 投递"区块与列表/详情、Overview `overview.get` | 加入同步按钮、状态徽标、历史与漏斗指标 |

缺口：投递记录页的 URL 与结构未在本项目内观察过，首次真实运行由"发现"步骤定位并记录，映射规则按真实观察再收紧。

## 3. 数据与接口

- 新文件 `outputs/submissions/liepin/<submission_id>/platform_feedback.json`：`{schema_version, submission_id, history:[{observed_at, page_url, status_label, normalized_status, match_basis, time_label, excerpt}], latest:{...}}`，只追加不覆盖历史；回执与日志文件不变。
- 同步日志 `outputs/submissions/liepin/platform_feedback_sync.json`：最近一次同步的状态、页面 URL（去 query）、匹配/未匹配行数、`records_page_not_found` 时的候选链接文本与路径。
- `submission.feedback.syncPacket`：返回受控且成功的投递清单 `{submission_id, company, position, platform_job_id, job_url, delivered_at, delivery_kind}` 与发现规则 `{start_url, link_keywords}`；只读。
- `submission.feedback.recordPlatformStatus`：接收 Rust 回传的观察 `{status, page_url, discovery:{links}, rows:[{job_url, job_id, company, position, status_label, time_label, excerpt}]}`，脱敏、限长，按岗位编号匹配（无编号时按公司+岗位精确匹配），归一化状态：已投递→`delivered`，已查看/已浏览→`viewed`，感兴趣/有意向/合适→`interested`，不合适/不匹配/已拒绝→`rejected`，面试/邀约→`interview`，其余→`unknown`；返回匹配摘要。
- 反馈项：有 `platform_feedback` 时在 `submission.feedback.list` 加入 `platform_delivery_status`，推荐动作：`rejected`→`update_job_target`，`viewed` 超过 7 天无进展→`add_or_edit_evidence_card`，`interested`/`interview`/`delivered`/`unknown`→`acknowledge_and_skip`。
- 列表项增加 `platform_feedback:{status,label,observed_at}`；`overview.get` 增加 `feedback_funnel:{delivered, viewed, interested, interview, rejected, unknown, unsynced}`。

## 4. Rust 与页面脚本

- `sync_liepin_feedback(app, window)`：`require_local_command` → 取 `NativeOperationGuard` → 会话检查须 `authenticated` → `syncPacket` → 导航 `https://c.liepin.com/` → 运行 `liepin_native_feedback_discover.js` 收集文本含"投递"的站内链接（去 query，仅 `c.liepin.com` / `www.liepin.com`）→ 若命中则 `allowed_navigation` 校验后导航 → 运行 `liepin_native_feedback_records.js` 读取包含 `www.liepin.com/job/<id>` 链接的卡片文本及状态词 → 回传 → `recordPlatformStatus`。脚本只读 DOM，不触发点击；无命中时回传 `records_page_not_found`。
- 观察载荷限长 64 KB，字段白名单由后端 `_sanitize_observation` 与结构校验共同约束。

## 5. 验收与切片

- 切片 1（本次）：后端两接口、反馈来源、列表/总览指标、Rust 命令与两段脚本、Submissions 页同步按钮/徽标/历史；单测与界面回归先红后绿；规范与设计同步。
- 切片 2：真实 App 首次同步，记录投递记录页实际结构，按观察收紧匹配与状态映射，完成外部真实 Tauri 页面验收；Overview 漏斗卡片视觉。
- 切片 3：沟通页招聘方回复的只读读取（仅 PDF 路线已建立的会话），作为 `interested`/`interview` 的补充来源。
- 验收口径：真实 App 一次同步覆盖 16 笔投递，匹配与未匹配各有明细，`unknown` 不冒充进展；重启后状态与历史可读回；期间平台写入为 0。
