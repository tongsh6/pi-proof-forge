# Execution Roadmap / 项目推进路线图

> 公开文档中的 `<local-candidate>` 为脱敏占位；真实候选名称、路径与执行安排仅保存在本机记录。

本文件决定“下一步做什么”。`docs/project-ledger.md` 只记录事实，本文件维护推进顺序、依赖和完成口径。

路线图必须同时对齐：

- 项目愿景：`PLAN.md` 的 evidence-first 求职引擎。
- 项目宪法：`constitution.md` 的 Evidence-First、No Fabrication、Spec-First、TDD、外部自动化驱动真实页面验收。
- 核心系统设计：`openspec/specs/pi-proof-forge-core.md` 的 v2 六边形领域核心和核心 pipeline。
- Agent 设计：`openspec/changes/autonomous-agent-delivery-loop/design.md` 的 10 状态机、Gate、Review、Delivery。
- GUI 设计：`ui/design/DESIGN.md` 的 9 页信息架构与页面职责。

## Vision Alignment

PiProofForge 的主线不是“把页面做完”，而是完成可追溯的 evidence-first 求职闭环：

1. 原始材料资产化为 Evidence Cards，且 `results` / `artifacts` 缺失不得进入候选池。
2. Job Profile/JD 与 Evidence Cards 做可解释匹配，输出分项得分、理由、缺口任务。
3. 简历生成坚持模板拼装优先、LLM 受控改写次之，不引入无证据事实。
4. Scorecard 反驱补证据任务，而不是降低事实保真标准。
5. 投递与反馈回流到版本、权重、模板和证据补全。

因此路线图中的任何 `next` 任务都必须说明它推进了上述哪一段闭环，不能只因为局部实现容易就插队。

## System Design Alignment

执行路线必须遵守以下设计边界：

- GUI 页面顺序和职责以 `ui/design/DESIGN.md` 为准：Overview -> Resumes -> Evidence -> Jobs -> Quick Run -> Agent Run -> Submissions -> Policy -> System Settings。
- Quick Run 是 4 阶段单次 pipeline：Evidence Extraction -> Matching -> Generation -> Evaluation。
- Agent Run 是 10 状态机：INIT -> DISCOVER -> SCORE -> GENERATE -> EVALUATE -> GATE -> REVIEW -> DELIVER -> LEARN -> DONE。
- Policy 承载 Gate Policy 与 Exclusion List；System Settings 承载 Channels 与 LLM Config。
- 业务实现必须保持 v2 架构边界：domain 零外部依赖，engines/orchestration 向内依赖，infra 是唯一外部 IO/LLM/YAML 适配层。
- 新的 GUI 结构性变更必须同步 `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen`，否则不得标为完成。

## Current Mainline

用户旅程闭环：

`系统设置配置 LLM -> 简历中心个人资料和材料库 -> 证据页提炼/维护 Evidence Cards -> Jobs 建立岗位画像 -> Quick Run 生成匹配报告/简历/Scorecard -> Agent Run 门禁/审批/投递 -> Submissions 反馈迭代`

## Current Focus

`small_company_high_match_delivery`

2026-10-23 手工导入岗位的手动投递指引（resume_target_unreviewed UX 修复）：得物 V2EX 手工导入画像（`source=v2ex`、`import_mode=manual`）跑完 Quick Run 后在 Submissions 报原始码 `resume_target_unreviewed`——App 内原生 PDF 投递要求目标绑定已审核的猎聘官方线索（`job_lead_id` + `source_jd_sha256` + 线索官方审核 + JD 指纹一致），手工导入目标无法满足，属目标身份/审核硬门禁。修复为前置提示：`jobs.listProfiles` 新增 `native_pdf_delivery:{supported,reason}`；Quick Run 下拉标注「仅手动投递」、输入区提前提示，结果区不再给 App 内「准备 PDF」，改为展示已生成 PDF 路径 + 「去岗位中心记录手动投递」；Submissions 把 `resume_target_unreviewed` / `pdf_job_review_required` 映射为可读说明。门禁本身不放宽。验证：全量单测 **1765 通过、1 跳过、53 subtests**，`tsc --noEmit`、roadmap/v2/AIEF 门禁通过。P0-026 仍唯一 `next`（待面试反馈）。

2026-10-23 方向评估改为建议层（产品原则修正）：原 Quick Run 在方向评估 `excluded` 时硬停止（`SKIPPED`、不生成），与「产品可分析建议但不能强阻断用户」冲突；同一得物岗位 10-21 判 `needs_review`、10-22 判 `excluded`，判读本身有波动。改为：方向 `excluded` 继续生成/评测/PDF（`DONE`）；启动前新增 `run.quick.checkDirection` 预检，`excluded` 弹确认框展示原因/偏好/JD 原文，用户可选「取消」或「仍然运行」，确认写入 `direction_acknowledgement` 审计；结果页保留警示卡与「仅供参考」说明；预检失败 fail-open。策略排除清单/职业档案/证据/授权等硬门禁不变。验证：全量单测 **1762 通过、1 跳过、53 subtests**，`tsc --noEmit`、roadmap/v2/AIEF 门禁通过；真实 App 复跑由用户在页面执行。P0-026 仍唯一 `next`（待面试反馈）。

2026-10-22 附件移除真实执行成功（补记）：用户重启 App 后于 `15:23:51Z` 勾选确认并点击「移除此平台附件」，`ar_20261022140520046851` 在 `15:23:53Z` 返回 `removed`（本地历史保留）。App 自动先做只读附件页检查；`beginPdfRemoval` 对 `receipt_binding_mismatch` 做一次性校正（log sha256 `cd797d75…`→`0fdf1047…`，旧附件 `287f8d2d…`→`287c8e228d…`）并记录 `evidence_reconciliations`，随后仅一次精确 `remove-attachment-resume` POST（HTTP200/flag1，`encryAttachmentId` 等于绑定附件）；2 卡片页的 before/after 集合为 `[IDSZFJa0…, YAaU8ett…]→[YAaU8ett…]`。`pdf_delivery`/submission_log/native_receipt/delivery_attempts 均保留成功历史，平台剩 1 张同字节遗留卡。证据 `outputs/acceptance/attachment-removal-evidence-20261022/validation.json`（含 `real_user_action`、移除后 sha256 与可复跑回放）；`.pen` 待补；P0-026 仍唯一 `next`（待面试反馈）。

2026-10-22 附件移除误报 `attachment_removal_success_required`（用户实测）：对已成功投递的 `.5` PDF 点「移除此平台附件」被拦。真实运行 `ar_20261022140520046851` 的 `pdf_delivery.state=success` 无误，缺口在成功证据：最终发送前按恢复流程重传同一 PDF 后，绑定已更新为新附件（`IDSZFJa0…`/`287c8e228d…`），但 `submission_log.input_artifacts.attachment_id` 仍是开始投递时的旧值 `287f8d2d…`，`inspect_submission_evidence` 返回 `receipt_binding_mismatch`，而门禁把“未成功”和“成功证据未通过”合并报成 `success_required`；同时平台有 2 张同字节附件卡，旧门禁“页面恰好 1 行”也会阻断。修复：`verifyPdfReceipt` 把回执证明的实际发送附件写入 submission_log（旧值留 `attachment_id_history`）；`beginPdfRemoval` 仅对可自证的 `receipt_binding_mismatch` 做一次性本地校正并记录 `evidence_reconciliations`，其余报 `attachment_removal_evidence_unverified[:reason]`；多卡片页改为“观察完整 + 目标卡唯一 + 原字节校验”，其它遗留卡允许存在；Submissions 页新增 5 个 removal 错误可读映射。验证：全量单测 **1645 通过、1 跳过、53 subtests**，GUI **140 通过**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过；真实数据只读回放（`outputs/acceptance/attachment-removal-evidence-20261022/`）完成 `receipt_binding_mismatch → begin in_flight(2 cards) → log 校正 → evidence verified → finish removed`，篡改回执副本均拒绝，真实文件 sha256 前后一致、平台写入 0。边界：真实 App 重启后勾选确认并点击「移除此平台附件」即可，Rust 命令会在 beginPdfRemoval 前自动只读刷新附件页检查，平台删除仍由人点击确认；平台上 2 份同字节附件本轮未删除；`.pen` 待补；P0-026 仍唯一 `next`（待面试反馈）。

2026-10-22 恢复后真实发送成功（第 19 笔，睿秀 · AI 全栈）：附件绑定恢复（只读 inspect，22:56）后用户在 App 内点击「确认投递所选 PDF」，`ar_20261022140520046851` 于 `2026-10-22T14:58:01Z`（22:58 CST）真实发送成功——`POST …/chat/send-resume` HTTP 200 / flag=1；submission_log 9 步全 success（含真实 `send-common-msg` 的 AI 声明确认），`native_receipt` success，attempt `423f27982c0b4e229d06c46802d80bab` success、`deliveries_completed=1`、`app_verified_deliveries=1`；真实投递累计 19 笔。证据：`outputs/submissions/liepin/native-423f27982c0b4e229d06c46802d80bab/`。边界：平台仍保留 2 份同字节附件待清理；反馈同步仍为 10-12 的 18 行/17 匹配，需下次只读同步；23:00 另一次 check-mode 运行未产生平台写入；`.pen` 待补。P0-026 仍唯一 `next`（待面试反馈）。

2026-10-22 附件绑定误清/重复附件/恢复后未核验（用户实测 `pdf_delivery_not_pending`）：新版简历页附件卡片懒加载，检查脚本在渲染前抓取得到 0 张卡片，误判附件被移除并清绑定；恢复重传随后在平台产生 2 份同名同内容附件，而“无旧 list 回包”核验路径要求恰好 1 张 → 绑定无法建立；UI 又因投递阶段 phase 恒为 resume_interaction_pending 跳过重新 inspect，导致下一步 pdfInteractionPacket 报绑定缺失。修复：inspect 等待卡片渲染（最多 8s）；核验容忍同字节重复附件并只绑定上传 ack fileId（字节不同仍拒绝）；投递中绑定缺失改报 attachment_verification_required；UI 恢复按 upload_state 重新核验并在自动推进前提示缺绑定。用只读 inspect 已恢复真实 binding（新上传 ack fileId），未发送/未删除。验证：全量单测 **1632 通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱既有失败），GUI **139 通过**，tsc/build/roadmap/v2/AIEF 门禁通过；证据 `outputs/acceptance/attachment-binding-recovery-20261022/validation.json`。边界：最终发送仍需用户手动确认；平台上 2 份重复附件可稍后清理；`.pen` 待补。P0-026 仍唯一 `next`。

2026-10-22 最终发送前附件被移除的恢复（核实“投递出去了”）：只读聊天探测显示平台聊天里只有打招呼语与 AI 声明、没有简历消息，动作区仍显示「发简历」；平台附件列表为 0、队列处于 `resume_interaction_pending` 且 `final_send_started=false`，即简历未真正发出，附件在最终发送前从平台消失。平台入口复核：附件数 0 时添加入口恢复，点击后新弹窗 `ant-c-modal-root` + 1 个 file input + 拖拽区，证明上传脚本新路径可用。修复：`_pre_send_reupload_allowed` 在“已进入投递但尚未最终发送且无有效附件绑定”时允许重新上传同一份已批准 PDF（清失效绑定、旧上传进 history，`final_send_started` 后仍拒绝）；页面显示附件已不在并提供「重新上传同一 PDF 并继续」（upload→只读核验绑定→继续自动推进，不自动发简历）；新增只读调试动作 `probeChatMessages` 用于核实是否已发送。验证：全量单测 **1631 通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱既有失败），GUI **139 通过**，tsc/build/roadmap/v2/AIEF 门禁通过；证据 `outputs/acceptance/missing-attachment-recovery-20261022/validation.json`。边界：本轮只读，未重新上传/未发送；真实恢复与最终发送需用户重启 App 后验收；`.pen` 待补。P0-026 仍唯一 `next`。

2026-10-22 同岗位重复投递冲突提示与一键载入（用户实测 `delivery_already_attempted`）：AI 声明修复后，用户重跑 Quick Run 生成 `.6` PDF 并重新固定同一岗位，被后端一次性投递门禁拒绝。定位：22:06 已有 `in_flight` attempt（PDF `.5`，`communication_started`，未最终发送），同一 job_key 不允许第二笔；后端正确但错误不可读，用户不知道应继续已有流程。修复：`native_pdf._existing_attempt_hint` 只读扫描审核队列，在 `delivery_already_attempted` 错误中附带已固定的 `quick_run_id`/PDF；Submissions 页显示已固定版本与「载入已固定的投递流程」按钮，一键按回传 quick_run_id 重新 prepare 并恢复原阶段，随后继续自动推进。验证：新增 1 项后端 + 1 项 GUI 测试；全量单测 **1628 通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱既有失败），GUI **138 通过**，tsc/build/roadmap/v2/AIEF 门禁通过；证据 `outputs/acceptance/delivery-attempt-conflict-20261022/validation.json`。边界：未创建/结束/发送任何投递，in_flight 保持原状；同岗位第二笔仍禁止，暂未提供“结束未决尝试换新 PDF”入口；`.pen` 待补。P0-026 仍唯一 `next`。

2026-10-22 AI 投递声明“已发送却判未确认”修复（用户实测 `ai_disclosure_not_confirmed`）：附件清理后自动推进到沟通阶段被 AI 声明步骤阻断。定位队列 `ar_20261022140520046851`：声明实际已通过 `POST .../send-common-msg` HTTP 200 发出、请求含完整声明原文，脚本标记 confirmed；但脚本把网络证据放在 observation 顶层 `network`，后端校验只读 `ai_disclosure.network`，真实证据被误判缺失。修复：后端在 `evidence=network` 时接受两种位置（仍要求 HTTP 200 且请求含声明原文，DOM 证据仍要求 dom_confirmed），脚本同步镜像 network 到 `ai_disclosure.network`；Submissions 页把该错误映射为可读提示与重试入口。验证：真实失败 observation 回放修复前 False→修复后 True（无重复发送/无平台写入）；新增 2 项后端 + 1 项 GUI 测试；全量单测 **1624 通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱既有失败），GUI **137 通过**，tsc/build/roadmap/v2/AIEF 门禁通过；证据 `outputs/acceptance/ai-disclosure-evidence-20261022/validation.json`。边界：本轮未重复发送声明或发简历，最终发送仍由用户手动确认；`.pen` 待补。P0-026 仍唯一 `next`。

2026-10-22 附件简历达上限诊断与上传/清理选择器修复（用户实测“自动推进停在当前阶段”）：用户重启后点击自动推进仍停在上传阶段，队列 hints 为“附件控件不唯一:共0个”。用 debug 文件触发器在真实 Tauri webview/真实猎聘会话做只读 DOM 诊断，确认「附件简历」区已有 3 张卡片、`sectionAction` 为空，而其它 section 都有 `resume-add-icon`：平台附件简历上限为 3，已达上限时上传入口不渲染，此前重复重试不可能成功。修复：上传脚本优先点击附件区 `data-nick=resume-add-icon` 入口，附件 ≥3 且无入口时回传 `attachment_quota_reached`（不再空点控件）；清理与单份移除脚本适配新版 `attachmentCard`/`ant-c-dropdown-menu-item`/`ant-c-modal-root` 选择器与 pointer 点击序列（保留旧选择器兼容、请求前守卫与身份复核）；Submissions 页显示上限原因与「移除旧的 App 生成附件」入口、清理成功本地解锁自动推进，并把上传“确定未派发”显示为可读错误而非通用停止。验证：真实 App 触发器 `action=upload` 在派发前识别上限并落库 `not_submitted`+`attachment_quota_reached`（无平台写入/无删除）；GUI 全量 136 通过、`tsc --noEmit` 通过；证据 `outputs/acceptance/attachment-quota-20261022/validation.json`。边界：未删除任何平台附件（确认框已取消），上限释放后的真实上传待用户清理后验证；`.pen` 待补。P0-026 仍唯一 `next`。

2026-10-22 投递卡死与 Quick Run 假进度修复（用户截图实测）：Submissions 在「附件控件未找到」后所有按钮变灰，Quick Run 四阶段同时显示同一状态，且手动投递要依次点 8 个按钮。定位两处根因：① 上传脚本在派发前确定失败时上报 `not_submitted`，但 `handle_finish_upload` 把非 uploaded 一律写成 `unknown`，`handle_begin_upload` 只对平台文件名拒绝这一种 reconciliation 放行，真实队列 `ar_20261021185426217475` 因此永久无法重试（与 DESIGN“prepared/not_submitted 可上传、unknown 不重传”不符）；② `run.quick.start` 同步执行整条管线，阻塞 sidecar 串行循环，UI 无法轮询，只能把四阶段同时标进行中。修复：上传状态区分「确定性未派发（not_submitted 且无 POST/PUT/PATCH 观察，可重新批准上传并保留 history）」与「unknown（已派发但结果不明，仍禁止重传）」，旧队列 raw unknown + 自证未派发读取时只读归一（不改文件），`_public` 增加 `upload_state/upload_attempts/upload_hints/can_retry_upload` 供页面展示上次失败原因，每日投递恢复判定复用同一归一；Quick Run 改为后台线程 Popen 执行 + 新增 `run.quick.get` 轮询，四阶段按 run_log 事件真实推进并显示阶段耗时，轮询不绑定页面生命周期；Submissions 把 8 个手动步骤收敛为「自动推进到最终确认」（自动打开/检查 App 内会话 → 上传 → 核验附件 → 登记单次授权 → 开始投递 → 检查沟通/发简历确认界面），最终发送仍需人工点击、点完自动只读核验回执，高级操作只保留只读诊断。验证：全量单测 **1617 项通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱环境失败为既有环境问题），GUI **131 项通过**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过；真实旧队列只读归一为 `not_submitted`、可重试且脱敏 hints 可见（文件未改写、无平台写入）；Quick Run acceptance 1 通过 1 跳过。边界：真实 Tauri 窗口端到端与自动链真实页面耗时待用户执行 `./app restart` 后验收；新版猎聘附件控件选择器仍是已知外部阻塞（修复只保证明确未派发可重试并可视化原因，若重试仍返回相同 hints 需用“诊断附件入口”取 DOM 证据后另开修复）；真正 unknown 仍禁止重传；`.pen` 待补。P0-026 仍唯一 `next`。

2026-10-22 Quick Run 匹配阶段 HTTP 502 有限重试（Strata App Host 并发长请求 300s 超时）：用户重跑 Quick Run `qr_20261021182815881138` 时 matching 失败 `HTTPError`（不再是 semantic_invalid_response）。定位：Strata App Host 的 `native-gateway.mjs` 用 Node fetch 转发到引擎，fetch 默认 300s 超时，超时抛错后 host 返回 502；期间统一后台被其他客户端长生成占用（serving 记录 `req/0.7.3` 单请求 1.79 万–2.42 万输出 tokens、4–6 分钟，本应用请求 `durationMs≈300.7s / error=fetch failed` 两条），PiProofForge 的语义评审请求排队超过 300s 即失败。修复：`LLMClient` 对 POST/GET 的 502/503/504 做有限重试（2s/5s，最多 3 次，4xx 不重试）；`run_matching_scoring` 对 HTTPError 输出含 HTTP 状态与“稍后重试或减少并发推理任务”的可行动文案。新增 5 项单测。验证：全量 **1700 项通过、1 跳过、53 subtests**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过；证据 `outputs/acceptance/strata-502-retry-20261022/`。边界：有限重试缓解 300s 单请求超时，不能消除其他重型推理任务长期占用统一后台的根因（建议 Quick Run 时避免同时跑 novel-studio/openclaw 等重任务，或在 Strata App 调大并行度）；完整 Quick Run 由用户重跑验证；P0-026 仍唯一 `next`。

2026-10-22 Quick Run 语义评审兼容本地模型 map 形输出（用户实测失败修复）：用户切换到 Strata App 统一后台（`iq3_s`）后 Quick Run `qr_20261021180502735753` 在 matching-scoring 失败 `semantic_invalid_response`。定位：本地模型在 recall 修复回合把每卡输出为以卡 id 为键的对象（`{ec_x:{...}}`），而 `semantic_review._rows` 只接受 `{"cards":[...]}`；首次尝试校验失败后的第二次尝试仍是 map 形。修复：`_rows` 对“顶层键恰好等于全部期望 id 且值为对象”的等价结构归一为行数组，随后仍逐项校验覆盖/分数/引用/理由（缺 id、重复 id、非对象仍拒绝）；`semantic_matching` 修复提示明确顶层结构必须保持数组、不得改成 id 键对象。新增 3 项单测。验证：全量 **1695 项通过、1 跳过、53 subtests**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过；真实复跑（同一 51 卡/岗位画像/`iq3_s`/47831）`run_semantic_matching` 完整 **SUCCESS**（model_calls 7、cache_hits 10、repair_calls 1、153.8s），证据 `outputs/acceptance/semantic-map-normalization-20261022/`。边界：未改语义判定标准与证据/引用校验；首次复跑 recall 全部通过后遇到一次 Strata App Host 502（外部瞬时错误，未新增通用重试），二次复跑通过；Quick Run 后续 generation/evaluation 阶段待用户重跑确认；P0-026 仍唯一 `next`。

2026-10-22 Strata App 统一推理后台（独立任务，不改变 P0-026）：按用户指令「修改方案 只一套由 Strata App 管理的推理后台统一连接 http://127.0.0.1:47831/v1」，把 2026-10-21 的直连引擎方案（8081 / `qwen3.8-flash-next-q2_0`）修正为唯一统一入口。`tools/infra/llm/client.py` 新增 `STRATA_UNIFIED_BASE_URL="http://127.0.0.1:47831/v1"`，`LLMClient` 在 provider=strata 且缺 base_url 时回退该入口；settings 默认 provider 改为 strata（新配置 model 为空），读取/保存/checkLlmConnection 都把 strata 的 base_url 归一为统一入口（旧 8081/8082 地址不生效），空 `/v1/models` 返回 `BLOCKED_LOCAL_PROVIDER` 并提示先在 Strata App 加载模型，切 provider 清旧 model/base_url；`extract_evidence_llm` 对 strata 缺 base_url 回退统一入口，不落 OpenAI 默认地址；手工 CLI/管线（matching/generation/evaluation、agent CLI）缺省 `--base-url` 按 provider 选择（strata 落 47831），agent CLI 对 strata 不再注入 LM Studio 占位 Key。页面 Strata 预设改用共享常量 `STRATA_UNIFIED_BASE_URL`、model 默认空，Base URL 与 Model 只读（模型需检查连接后从 `/v1/models` 选择），默认选中 Strata；LM Studio / OpenAI / DeepSeek / OpenAI Compatible 保留为可切换 fallback，预设与行为不变。中英文 i18n、DESIGN、侧车 RPC 契约与 openspec proposal/design/spec/tasks 同步。验证：新增/更新 settings、`LLMClient`、extract、GUI 契约与 helper 测试，全量 **1692 项通过、1 跳过、53 subtests**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过；真实页面验收（Chromium + 只读桥接 + 临时 policy，非 Tauri 窗口）18 项检查字段（13 项硬断言）全部 PASS：默认选中 Strata、Base URL `http://127.0.0.1:47831/v1` 只读、Model 只读且为空，切 DeepSeek 再切回 Strata 端点复位/模型清空，检查连接真实请求 47831 返回 `Strata App unified backend ... 1 个模型` 并自动选中 `iq3_s`，保存后临时 policy 为 `provider=strata`/`model=iq3_s`/统一 base_url，页面无 JS 错误；另用真实 `LLMClient` 向 47831 发起一次最小结构化请求返回 `{"ok":true}`（response model `iq3_s`）。证据 `outputs/acceptance/strata-unified-20261022/`。边界：未改写本机 `policy.local.yaml`（生效 provider 仍为 DeepSeek）与用户凭据；真实“App 加载模型→选模型→保存→跑一次任务”页面验收待用户执行；`.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`。

2026-10-22 岗位批量适配预检与推荐清单（P0-026 续，短期目标提效）：真实投递 18 笔、同步 17 条仍为 0 面试，最近一笔投递岗位 fit 仅 56；逐个跑 Quick Run 才能判断岗位是否匹配（真实全链 12–29 分钟），选岗靶向成为最大瓶颈。本轮按用户确认实现“先预检、再决定跑哪单”：复用现有 job_profiles / matching_reports / scorecards 与已审核证据卡，不新增模型调用、不改生成/投递门禁。新增 `tools/engines/matching/fit_precheck.py`：可信 assessed（scorecard 有四层 `tiers.fit`）优先——有投递建议时按 apply/strengthen/reconsider/fix_facts 映射 recommended/consider/caution/hold，无建议时按 fit 通过/语义分与缺口数映射；旧评分卡没有四层报告时不得冒充“已预检失败”，退回规则预检。规则预检只读 `saved_eligible` 且可入池证据卡（51 张、34,345 字符），按 keywords/must_have/nice_to_have 与证据文本做英文完整词边界 + 中文二字窗口匹配，过滤通用词；年限/学历类不可验证要求不进入分母；输出 coverage、命中要求数、evidence_hits、matched/missing terms 与 `basis`。`jobs.listProfiles.items[]` 新增 `fit_precheck`（source/state/rank/coverage/counts/terms/fit_state/fit_score/basis），排序白名单增加 `fit_precheck`；状态排序 recommended(0)>consider(1)>promising(2)>caution(3)>hold(4)>unknown(5)>low(6)，规则覆盖 ≥0.65 且命中≥1 → promising、≥0.35 → caution、否则 low，缺要求/缺证据 → unknown。Jobs 页新增「投递建议」清单（仅 active 画像、排除 low/unknown/hold，按 rank 取前三，含徽标/覆盖/命中数，点击选中）、画像卡预检徽标、详情预检依据与命中/未命中要求；新增「推荐优先/最近更新」排序（客户端，默认推荐优先），首屏改为按 `fit_precheck` 排序取 100 个画像，避免漏掉更匹配的老画像；Quick Run 目标下拉与提示显示规则预检结论与命中数（assessed 保持原提示）。验证：新增 `tests/unit/matching/test_fit_precheck.py` 20 项 engine 测试、6 项 handler 回归与 `test_fit_precheck_ui.py` 3 项 GUI 测试（7 state 徽标/推荐排序/排除/详情/空态/接线），全量 **1677 项通过、1 跳过、48 subtests**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 三门禁通过。真实工作区回放（`outputs/acceptance/fit-precheck-20261022/replay.py`，0 模型调用）：26 个 active 画像排序为 得物 Java consider → Senior Software Architect / Full-Stack Tech Lead promising → 高级全栈/Backend Tech Lead/Tech Lead JAVA+AI caution → 20 个低匹配（含全部模拟 IC 画像）low；真实页面验收（只读桥接 + 真实工作区 + Playwright Chromium，Tailwind 已加载）Jobs 页渲染「01 Java技术专家（电商交易）· 得物App · 补强后投递」「02 Senior Software Architect · 初步匹配 72% 命中 8/11」「03 Full-Stack Tech Lead · 初步匹配 76% 命中 11/12」，无页面错误；断言切换「最近更新」后网格顺序变化、点击推荐项后画像详情联动到对应岗位、推荐区背景取到主题面板色（样式生效），截图 `jobs-precheck-ranking.png`/`jobs-page.png`。独立审查发现阻断 B1（四层报告缺语义分/建议时仍被当作可信 assessed，且失败数映射反向）与页面证据样式缺失等问题；已修复为 fit_score 只取语义评审分（0 合法）、无分无有效建议退回规则预检、失败数单调映射，并补四层-无语义分、fit_score=0、空建议与 legacy 回归；Quick Run 对不可信 four-tier failed 也显示规则预检解释。边界：规则预检是启发式参考，不替代语义对位评审、不自动运行 Quick Run、不写卡、不写平台；本次为 Chromium 只读桥接页面验收，真实 Tauri 窗口验收待补；`.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`，待面试反馈。

2026-10-22 质量报告→投递建议与缺口类型（P0-026 续，落用户方向「帮助拿到面试/录用」）：按 2026-10-21 用户明确的两项待办，把四层质量报告从“通过/未通过”改为可执行投递建议，并区分「证据缺失 vs 未表达」。复用现有四层评估器、`quality_report` 与四层报告组件，不新增评分框架、不改 `auto_pass` 口径、不拦截投递。实现：`QualityFailure` 增加可选 `gap_kind`（`evidence_missing`：证据池非 supported，含 partial/insufficient/conflict/未知；`not_expressed`：证据池 supported 但正文未表达或未进首屏），仅对位 R2.2/R2.3；对位矩阵行增加 `evidence_support`；R2.2 中“supported 但不在首屏”的 reason 明确为位置缺口；R2.3 支持率只由 supported 决定，缺口计数只统计非 supported 行，两类同时存在时输出两条 R2.3 failure。`quality_report` 增加 `delivery_advice`（`recommendation: apply|strengthen|reconsider|fix_facts` + `label` + `advisory_only:true` + `gap_counts`（前三条职责口径）+ `summary` + `reasons[]` + `next_actions[]`）：事实/硬性条件缺口优先 `fix_facts`，前三条职责 ≥2 项证据缺口 `reconsider`，其余对位/结构/首屏缺口 `strengthen`，合格+对位通过即 `apply`（优质/突出失败只作可选改进）；合格层 metrics 增加 `pdf_check_state`，PDF 页数/裁切未回填按“未校验”提示且只排除 target=pdf 的 R1.5，首屏摘要/核心经历等可判缺口仍保留，apply 文案写明“除未校验项外”；`apply_pdf_check` 回填后只替换 target=pdf 的 R1.5 并重算建议（稀疏/旧报告不新增或重算）。Markdown 评估报告新增「投递建议」段与缺口类型标注；GUI 四层报告顶部新增建议区（结论、仅供参考、依据、下一步、前三条职责口径计数），逐项 failure 显示「证据缺口/未表达」徽标；中英文 i18n 与 `DESIGN.md`/RPC 契约/spec 同步。验证：新增 17 项后端测试（15 项先红后绿、2 项旧行为护栏）并扩展既有 GUI/CLI 断言，全量 **1648 项通过、1 跳过、48 subtests**；`tsc --noEmit`、`pnpm --dir ui build` 通过；真实数据回放（2 个真实 quick run + 本机判项缓存命中，**0 次模型调用**）：最近真实投递岗位「某上海专业技术服务公司 · 高级全栈工程师」建议 `reconsider`（3 项 R2.2 核心职责证据缺口），Fit A「得物App · Java技术专家」建议 `strengthen`（1 项 R2.2 证据缺口 + 1 项内容取舍）；同一报告通过真实 `quality-report.tsx` + 真实 `zh.json` 渲染出建议区与 5/1 个缺口徽标，证据 `outputs/acceptance/quality-advice-20261022/`。独立审查先审发现 1 项阻断 B1（PDF 未渲染时误把全部 R1.5 当未校验，隐藏首屏缺口仍给 apply）与 R2.3 计数口径 N1，均已修复并补回归：B1 改为结构化 `pdf_check_state` 且只排除 target=pdf，回填保留首屏 R1.5；N1 改为只统计非 supported 行并拆分两类 failure；另修复 apply 文案超出证据、稀疏报告兜底、R1.5 动作误映射、i18n 计数口径。真实 App 页面验收需下一次 Quick Run 在 App 内生成后查看（报告回放不覆盖页面级场景）；`.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`，待面试反馈。

2026-10-21 总览最近活动可读化（用户反馈）：Overview「最近活动」原先直接显示生成简历文件名（如 `resume_mr-qr_20261021133955495233_B.md`）和英文状态句，编号不可读。`overview.get` 活动项新增可选结构化字段 `target_role/company/variant/platform/status/title`：简历事件按 `resume_<matching_report_id>_<variant>.md` 回查匹配报告→岗位画像，投递事件读 submission_log `input_artifacts` 的岗位/公司；`description` 改为人类可读回退且不再包含运行编号/文件名。GUI 按中英文文案本地化展示（如「高级全栈工程师 · 某上海专业技术服务公司 · B 版」「… · 猎聘 · 成功」），证据事件直接显示标题，缺字段回退 description。真实页面验收：只读桥接 + 真实工作区数据以 Playwright 驱动 Overview，6 条活动均无编号、无页面错误；重启桌面 App（真实 Tauri 窗口）后最近活动显示「高级全栈工程师 · 某上海专业技术服务公司 · A/B 版」「… · 猎聘 · 成功」，截图 `outputs/acceptance/overview-activity-20261021/`（`tauri-app-activity.png` 为真实 App）。全量 **1631 项通过、1 跳过、48 subtests**，`pnpm --dir ui build` 通过。Resumes 页版本名仍沿用文件名（同类可读性缺口，未在本轮扩大范围）；P0-026 仍唯一 `next`。

2026-10-21 投递 AI 自动化声明开关（策略配置）：新增默认关闭的系统开关与固定声明文案「您好，本次投递所使用的简历和投递操作均由 AI 自动化执行；如对简历内容有疑问，欢迎直接与我沟通。」。开启后，每次原生 PDF 投递在打开「发简历」前先由 App 在目标沟通会话向招聘方发送该声明，捕获真实发送证据（网络响应或聊天 DOM 回读）并由后端校验记录后才继续；声明未确认时阻断本次投递，重试不重复发送。每日/恢复门禁先于声明写入；成功回执的 submission_log 增加 `ai_disclosure` 步骤。策略配置页（门禁策略分组）新增「AI 投递声明」卡，Submissions 卡片显示已发送/待发送。真实页面预检：dev 探测在真实猎聘沟通页确认 `im-ui-chat-container` 含目标公司/岗位，填入 49 字声明后「发送」按钮由 disabled 变 enabled，随后清空；未点击发送、无平台写入。新增后端/JS/接线测试，全量 1631 项通过、1 跳过、48 subtests，`pnpm --dir ui build` 与 `cargo check` 通过；P0-026 仍唯一 `next`。真实“声明+发简历”同链需下一次用户授权投递时验证；`.pen` 待补（本机无 Pencil 工具）。

2026-10-21 猎聘确认弹窗真实字段与真实投递回执：按用户要求把「打开聊天」「点发简历」拆成两个独立探测，避免入口跳转销毁脚本。真实探测确认新版职位页沟通为页内抽屉（URL 不变）、沟通开始后入口文案为「继续聊」，唯一「发简历」位于 `im-ui-action-button action-item action-resume`。确认弹窗真实字段：`.ant-im-modal-root` 内标题「选择附件简历」+「招聘方将同时收到您的默认在线简历和附件简历」，3 个 `input.ant-im-radio-input`（value 为平台附件路径），本次 PDF `QHotN7e3RZOJwu4UPFet9g.PDF` 默认选中，按钮「立即投递」可用；既有确认匹配规则与真实字段一致，无需放宽。生产侧改为先幂等打开沟通抽屉、再独立执行「发简历」交互；prepare 在未抓到确认框前允许重试；职位页登录检测补上 `.header-quick-menu-username` 正向证据（职位页不渲染 `.nav-user-item`），并移除触发前多余导航。真实发送：run `ar_20261021134024153666` 于 2026-10-21T15:17:22Z 点击「立即投递」，`POST https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume` HTTP 200，请求 attachmentId `287e8a2787M348b993290a8` 与批准 PDF 绑定一致，响应 `{"flag":1,"data":{}}`；15:17:33Z 回执核验 success，submission_log 8 个必需步骤全通过，delivery_attempt `f61d3037e09f4a8dbdc0d15684746fa9` success，agent_run DONE 且 deliveries_completed=1；会话 UI 23:17 出现「童先生的简历 / 在线简历 / 附件简历」记录。全量 1609 项通过、1 跳过、48 subtests，`pnpm --dir ui build`、`cargo check`、roadmap/v2/AIEF 门禁通过。P0-026 仍唯一 `next`（待面试反馈）。

2026-10-21 Strata Provider 接入（独立任务，不改变 P0-026）：系统设置在 LM Studio 之后新增 Strata 本地 provider 预设（`http://127.0.0.1:8081/v1` / `qwen3.8-flash-next-q2_0`，5 列 provider 卡）。本地回环默认免鉴权：无 Key 时连接检查、推理与 Quick Run 子进程管线都可用，界面及 Overview / Quick Run / Agent Run 显示「本地服务，无需密钥（可选）」；可选 serving API Key 仍按 provider 保存到本机 0600 文件并支持清除。`LLMClient` 对 `provider=strata` 使用请求顶层 `reasoning_effort`（关闭与结构化 JSON 为 `none`，开启后 low/high，max 归一到 high），不发送 DeepSeek 风格 `thinking`，空 Key 不发 `Authorization`；`llm_request_available` 统一 keyless 判定供管线各 gate 复用，避免把无 Key Strata 当缺凭证。本机 Strata 真实 `/models`、结构化 JSON 线上载荷、settings 连接检查与 keyless matching 阶段（`--use-llm --require-llm`，4 次模型调用）通过，证据 `outputs/acceptance/strata-local-20261021/`；相关回归与全量 **1609 项通过、1 跳过、48 subtests**、`tsc` 与 roadmap/v2/AIEF 门禁通过，两轮独立审查（第 1 轮发现并修复 keyless 管线阻断，第 2 轮无阻断）。真实 App 页面点击验收待用户在本机 Strata 运行时执行；`.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`。

2026-10-20 DeepSeek Provider 接入（独立任务，不改变 P0-026）：系统设置新增 DeepSeek 预设（`https://api.deepseek.com` / `deepseek-flash`）、按 provider 分别保存 API Key 到本机 0600 权限文件、按 provider 的密钥状态与清除入口、DeepSeek 思考模式开关（默认关）与 low / high / max 思考强度。`settings.get/update/checkLlmConnection` 增加 provider-scoped 字段，新增 `settings.clearLlmApiKey`；`LLMClient` 仅对 DeepSeek 注入 `thinking`，其他 provider 与 LM Studio 既有分支不变。模型配置改为紧凑单卡：provider 分段选择、密钥状态内联、思考开关与 low/high/max 同排，去掉重复的 Secret Status / Connection Tests 卡片。相关后端/GUI 回归与全量 **1560 项通过、1 跳过、27 subtests** 通过；独立审查发现的跨 provider 密钥复用、旧占位污染在线 provider、预设未强制套用等阻断已修复。真实 App 需用户用自己的 Key 完成“检查连接 → 保存 → 重启 → 实际任务”验收；`.pen` 画布已更新 DeepSeek 选项、密钥状态/清除、思考开关与强度选择，截图见 `outputs/pen-sync-20261021/system-settings-llm-screen.png`、`outputs/pen-sync-20261021/llm-config-compact.png` 与真实 React 渲染 `outputs/pen-sync-20261021/react-system-settings.png`（mock 数据，仅验证布局）；`.pen` 主文件已保存，新增紧凑 mockup 若需保留请在 Pencil 中 Cmd+S。P0-026 仍唯一 `next`。

2026-10-21 新版猎聘附件上传阻塞：旧脚本在新版「附件简历 + → 上传弹窗」流程下找不到 PDF 控件，持续 not_submitted；已加 App 内一键自动上传、后台文件触发、登录等待、内层滚动、弹窗拖放和附件诊断，但诊断桥接超时，仍未上传/投递。下一步修诊断与新版选择器，拿到附件绑定后再核验岗位、发送、回执；delivery_attempts 仍 17，不计已投递。

2026-10-21 Fit A 得物 Java 技术专家真实整链：切换匹配目标 JD，修复 DeepSeek 结构化 JSON（thinking 关闭、json 提示词、职责输出格式/完整性、括号章节解析）与首屏量化排序、未配对事实非 bullet 渲染；真实 quick-start 整链 DONE，两页 PDF，合格/优质/突出通过，对位仅剩 R2.2 首条职责 weak 与 R2.4 众安项目未映射，auto_pass=false 如实保留。公共求职定位改为“事实边界内的职业化加工”，不以全绿为目标；质量层不拦截投递（Quick Run/原生 PDF 均不因 auto_pass 阻断，前端展示“仍可继续”）；JD 适配预检已落到岗位列表与 Quick Run 选择器（未预检/适配有缺口标注 + 非阻断提示）；后续继续报告语义与真实 App UI 验收。全量 1568 项通过、1 跳过、27 subtests。

2026-10-21 行动-成果关联与首屏成果位置：模板生成按同卡词面关联配对行动与成果（无关联不硬拼），工作经历无成果职责改为非 bullet；PDF 防止 bullet 跨页；按可配对量化成果数调整卡序，站内消息量化成果进入第一页。真实报告复跑优质层达标（首屏量化 1.0、全文 0.625、R3.1 全通过），对位 R2.2/R2.3 与突出 R4.2 如实保留；DeepSeek 判项改为结构化禁用 thinking + 缺 section 二次补段。全量 1564 项通过、1 跳过、27 subtests 通过。

2026-10-20 对位/优质与耗时接续：修复正文判项输入缺失、项目标题误判、专业/工具示例误拆、粗筛零分排除完整项目、无关上下文及缓存过度失效；核心项目与性能成果重新进入正文。用户确认的 ai-content-forge Python 个人项目已在真实 App 增补并确认，其余职业事实不变。带新档案的真实管线 11 分 53 秒（复用 13 批粗筛），随后同输入复跑 0 模型调用；这不代表冷启动耗时结论。最终两页 PDF 无裁切重叠，全部判项覆盖且合格层通过，但对位/优质/突出仍未通过，用户已确认的技能差距不能靠评分修复消除；行动与成果关联、首屏量化及突出点位置仍待完善。P0-026 保持唯一 `next`，详情见同日台账和本机验收记录。

2026-10-20 职责取向与真实整链：已按用户愿景将缺少细分职责且无反向信息的本人项目按主导/负责人视角提名为 L3 待确认候选，采纳后的责任表达不按来源等级机械降级；确认链路接续 sha、保留其他字段来源并支持部分失败重试。真实 App 单卡候选展示通过，同岗位/材料/51 卡重跑完成 46 个 JD 子项与两页 PDF，逐页目检无裁切重叠，事实与投递记录未改。当前稿合格/突出通过、对位/优质未通过，R2.1 判项待完整覆盖；首个项目行动跨页，总耗时 28 分 34 秒，15 分钟目标未达成。修复 PDF 回填后的旧阻断提示与缺口残留，1494 项回归、原生构建与项目检查通过；该提示修复仅完成组件/回填验证。C8 整批确认与 D5 质量收口未完成，下一步复核 R2.1 与首屏选材，P0-026 保持唯一 `next`。详见台账同日记录。

2026-10-20 统一 AI 任务语境：按用户意图与 evidence-first 求职愿景重写公共提示词，集中于 `tools/prompts/context.py`，经现有 LLMClient 覆盖各任务；明确主动恢复职业上下文、区分事实归属、结合 JD 解释价值及最少确认。同步移除局部提示词的字面第一人称门槛，推断提供有界原文、工作汇总和关联的已确认任职职责；公共指令与任职上下文纳入缓存。两项本机模型边界样本通过，真实售后卡从 0 候选变为 1 条有双来源的 L3 职责候选，项目时间仍空、事实未改写。全量 1472 项通过、1 跳过、18 subtests 通过，审查问题已修复。此前手填请求不再作为推进前置；继续沿候选核对与真实 App/PDF 验收推进，P0-026 仍唯一 `next`。

2026-10-20 证据补全接续：针对已分流为「值得补」的售后服务卡，发现推断检索漏掉已绑定来源、通用背景匹配挤占前 20 条，且把系统“支持/参与计算”误计为本人参与。已最小修复为绑定来源/标题优先及明确第一人称计数，失效旧推断缓存；29 项相关回归通过、独立审查无阻断。现有入口真实单卡调用约 30 秒，返回 0 候选；卡、档案、分流指纹保持不变。补查工作汇总与售后预约原文后，通用职责描述及接口示例日期仍不能确定本人的项目职责/期间，已向用户请求这两项事实。C8 整批确认与 D5 仍未验收，P0-026 保持唯一 `next`。

2026-10-20 Quick Run 方向评估失败修复：原失败运行的模型日志确认 `qwen3.8-flash-next@q2_k` 在方向筛选阶段将 800 个输出 token 全耗于推理，正文为空。沿既有 LLMClient 对该精确型号的 JSON 对象请求按请求关闭推理，补齐方向评估最多一次内容纠错、校验后缓存、真实调用统计和可读失败提示。原岗位/原模型实测两次调用（含一次原文引用纠错）通过，缓存复跑 0 调用；受影响回归 133 项通过（其中两项 PDF 测试沙盒内受限、沙盒外原样通过），18 subtests 通过，独立审查无阻断。仅修复并验证方向阶段，不声明整条真实 App 管线或 D5 已通过；C8/D5 与质量收口仍待推进，P0-026 保持唯一 `next`。详见台账同日记录。

2026-10-18 证据页结构重整（设计基线落地）：按 DESIGN「折叠使用规则」与结构重整节重排证据页——页头动作区、进入自动对账、常驻汇总条计数筛选、双栏列表+详情、详情「对账发现」、560px 提炼抽屉；引用外部目录迁到系统设置；删除独立对账列表/就地摘要/关系提示条；全局页头吸顶透缝修复（`.page-header top: -1.5rem`）。画布 Screen/Evidence 与提炼抽屉状态已同步，测试按新结构重写。

2026-10-18 证据页 UX：标题下增加“材料来源 → 材料对账 → 证据卡”三层关系提示；对账行“查看”改为就地展开只读摘要（含池/审核状态、字段等级、来源文档、对账发现与原文候选），完整编辑与来源校验仍通过“打开完整详情”进入下方证据详情面板；`.pen` 同步待补。

2026-10-18 生成按等级降级与首屏（Phase D1–D4）：真实 A/B 模板拼装已消费字段级 provenance（L1/L4 保留负责/主导，L3 降级参与/推动，L5 时间卡不进正文，年精度只呈现年）；LLM 改写受控复核并在提升强度/精度时回退模板；按 JD 引用排序证据卡并把首屏标记移到第一条经历之后，使 JD 前三条职责 bullet 进入首屏；resume_trace 的 claims 与顶层记录字段等级/依据/确认记录。B4 突出点回填正文需评估后二次生成，明确列为后续切片；D5 真实 App 两页 PDF 验收与 C8 真实卡确认待用户操作。P0-026 保持唯一 `next`。

2026-10-18 证据可信等级与跨文档推断（Phase C）：证据卡支持 L1–L5 provenance（字段级、含出处/置信度/确认记录，旧卡默认 L1/L5），单文档提炼注入文档元数据产出 L1/L2 时间候选（角色仅 L1），新增 `evidence.inferFields`（kb 检索→规则聚合→每卡一次 LLM→任职区间与原文回读校验→本地缓存/否决过滤）与 `evidence.confirmInference`（接受/修改后接受 L4/否决）；证据页对账面板新增「待确认推断」与批量接受高置信、低置信折叠，系统设置新增推断开关（关闭只给规则 L2 线索）；`.pen` 证据页同步。真实 85 卡运行与用户批量确认（C8）阻塞于用户先在 App 分流；P0-026 保持唯一 `next`，继续 Phase D。

2026-10-18 四层质量报告 Phase B：已接通受控 LLM 判项（带引用、无引用 fail-closed、按输入指纹缓存）、R1.4/R2.1/R3.1/R3.5 判定、突出点提名 top-2 与用户否决/替换（`quality.decideHighlight` + `app-data/quality_decisions.json`），Quick Run 与固定 PDF 审批的四层报告展示突出点与候选。规则/缓存/决策回归通过，真实本机模型回归结果见台账。P0-026 保持唯一 `next`，继续 Phase C/D。

2026-10-18 四层质量报告首片（Phase A）：已按 `openspec/changes/resume-quality-standard-and-evidence-inference` 落地四层标准规则判项、`quality_report`/`auto_pass`/`llm_pending`、legacy 分数降级、审批门禁改读 auto_pass、Quick Run/审批页四层展示与首屏标记；Phase A 基线（最新目标 JD PDF，不重新生成）合格层通过、对位/优质/突出未通过，auto_pass=false（LLM 判项待 Phase B）。全量回归与 tsc 通过，无平台写入。P0-026 保持唯一 `next`，继续 Phase B/C/D。详见台账同日「四层简历质量报告首片」。

2026-10-17 设计真源同步：已清空 DESIGN.md 四处「`.pen` 待补」并补齐引用式材料缺口，Jobs/Evidence/Resumes/System Settings 四屏画布更新落盘，屏幕列重排无重叠；同期 `develop` 15 个提交已推送 `origin/develop`。仅设计同步，不改变实现与验收状态；真实 App 分流验收仍待用户，P0-026 保持唯一 `next`。详见台账同日「`.pen` 设计同步」。

2026-10-17 补全分流首片：试验确认人写文档只有公司/品牌级区间，不做自动逐字区间候选；证据页对账列表新增分流（值得补/不参与展示/重复），判断绑定卡指纹、不改卡，分流掉的卡不计缺口。1365 项回归与 tsc 通过，真实 App 页面验收待补；`.pen` 已于同日补齐。P0-026 保持唯一 `next`，下一步由用户在 App 分流后补“值得补”的卡。详见台账同日“证据卡补全分流首片”。

2026-10-17 索引覆盖补齐：沿既有引用入口纳入六份工作流编排/交付治理设计与实施计划（标为设计资料，非成果证明），材料 **24 份/6,601 档**。同一索引新增来源目录盘点与 `kb coverage`，工作资料 125 份 Office/PDF 已补目录及本地/LFS 状态，主动过滤和未纳入正文项显式展示；检索、逐份回读、verify 与独立复审通过。全量 1,351 项在沙盒内通过，8 项受限测试在沙盒外原样通过，1 跳过；不新增 GUI 深度验收结论。P0-026 保持唯一 `next`，下一片仍为证据卡补全工作台。详见台账同日“知识索引覆盖补齐”。

2026-10-17 引用式材料上线：App 可引用外部来源根内的文件/目录（不复制原件；内容变更可检出并阻断，刷新后重审）。首用已建「EC+ 始祖鸟工程档案」引用（6,058 文件/29.2MB），kb 文档 **6,595**、重建 1 秒、校验通过；证据链与 UI（证据页入口 + 系统设置「材料来源」）就绪；同日独立审查修复（TS 编译门禁、单档回读、偏好回读、错误码归一、重复引用拦截、撤根阻断、跳过计数等）。P0-026 保持唯一 `next`，本轮无平台写入。详见台账同日"引用式材料首片"。

2026-10-17 知识索引工具上线：`kb` CLI（build/tree/find/grep/read/refs/cards/leads/person-docs/verify）与 INDEX.md 已对全部知识资产（材料 1121 档/证据卡/岗位画像/岗位线索 624 条/职业档案）可用，真实数据构建 0.11 秒、校验通过；索引只做导航，引用必须回读原文并以 material_id/document_id/sha256 锚定。P0-026 的下一片「证据卡补全工作台」将复用其文档选择与日期线索；主线保持 P0-026 唯一 `next`，本轮无平台写入。详见台账同日"知识索引首片"。同日材料库查漏补缺：已从上游 worklog-private/ 差集导入 6 包 434 文件（求职资料/面试笔记/众安与九恒星补全/EC+ 其余品牌），materials 22 份 **1610 档**；始祖鸟 features 归档 5,076 与学习资料默认未导入、待分批决定。

2026-10-14 作品演示接续：已更正全局同名 CLI 的来源误认，改用本人作品 `@dsh/cli` 0.1.0 原入口和流水线。合成夹具真实运行完成 `verified` 与交接，固定6项测试全通过、仅目标函数变化；成功轮12请求约54秒，首轮包装兼容失败保留，两轮共24请求，不宣称稳定成功率。8分钟演示提纲及MongoDB根因/批大小案例已由真实App导入材料库并刷新回读，档案仍已确认。下一步由本人排练与追问验证，并核实实际雇主/学历条件后再定投递；没有新增平台上传或发送。P0-026仍唯一 `next`，面试目标未完成。

2026-10-14 缺口与候选接续：已完成来源对照，个人AI架构否定为误判，RDS方案存在但本人职责/上线阶段仍待回答；不把概念、计划或工具账号当生产云治理。App完成7组官方搜索并审阅10项候选，Sophon优先验证、不动产AI全栈为条件候选，其他按方向和硬性差距降级。两份两页待审稿已真实生成：50/50/69（仅4项任职、无编号职责，完整JD另人工核对）与50/36/68（10任职/8职责/46子项），分别8/8、17/17条可追溯，均未自动质量通过。串卡诊断及职责边界问题先失败回归后修复，1279项通过。下一步准备Sophon作品现场演示与具体架构/故障案例，再定投递；RDS可先留未知。本轮上传/投递0，P0-026仍唯一 `next`，面试目标未完成。详见台账同日“剩余缺口复核与下一批候选验证”。

2026-10-14 内容优先级更新：已修复“引用均同权后被固定条数截断”的正文遗漏；按新增父要求覆盖选原文，摘要保留已确认代表贡献，同项目场景/成果精确重复只展示一次且保留trace。真实App最终25缓存/0模型调用，两页PDF、19/19条可追溯，1275项测试通过。58/58/71仍未自动质量通过；部分AI实践误判已改善，个别公司专名/业务域与个人架构判断仍需人工复核。P0-026保持唯一 `next`，接下来区分这些误判与云治理/企业生产平台的真实缺口，再评岗位适用性；本轮上传/投递0，面试磨练未完成。详情见台账同日“原文事实优先级与最终正文验收”。

2026-10-13 评估校准更新：App 已按完整JD评审11项任职要求、8项职责和85个子项，区分证据池支持与正文呈现，保留备选关系和个人责任限定；固定PDF审核接入同版本质量摘要，历史未绑定记录明确显示未记录。真实51卡生成完成，53/45/71、20/20条可追溯、两页无裁切，1269项回归通过；与旧评估范围不同，不直接比较分数。整体质量仍未通过，P0-026保持唯一 `next`：下一片先补上已有平台职责划分/跨品牌复用在正文的遗漏，并复核语义判断中的可迁移经验与个人AI实践边界，再检查最终成品。新绑定审批正向场景仅隔离测试，历史分支已真实App回读；本轮新增上传/投递0，面试目标未完成。证据见台账同日“评估校准与固定PDF质量呈现”。

2026-10-13 目标正文更新：整份档案确认及重启回读已完成，已在 App 同岗位51卡语义管线验证新版内容取舍。新稿选跨品牌/统一运动中心/MongoDB，旧大屏退出，个人成果提前、技术栈显示，完整任职与教育压缩为两页；最终12缓存/0模型调用，20/20要点可追溯，1242项回归通过。指标86/77/74，仍完整待审核、自动质量未通过。P0-026保持唯一 `next`，下一片优先修复复合要求与责任强度评估、量化/表达口径和审批页缺口呈现，再验成品质量；新增上传/投递仍为0。详情见台账同日“目标正文取舍与真实两页 PDF 验收”。

2026-10-13 授权接续：用户授权重新确认整份职业档案，已在 App 完成并通过重启回读，上一条的确认阻断已解除。继续 P0-026 的选材与目标正文取舍，规范/回归和首轮实现已就绪，真实 App 同岗位51卡语义生成及 PDF 验收进行中；不把确认成功等同简历质量通过，不扩展上传或投递范围。

2026-10-13 补证首片：App 已支持同项目跨文档字段补证、原文/版本校验和年份精度，原材料变化会使相关确认及匹配/生成输入失效。统一运动中心的时间/职责、Feature治理职责已通过真实 App 保存并回读；Feature 盘点日期仍不能充当任期。1234项测试通过，桌面构建与独立审查通过。两卡变化使职业档案待确认，自动审批拒绝代点整份事实确认，已请求用户授权或自行确认；不绕过、不追加投递。P0-026 保持唯一 `next`，首片最终确认/生成验收后继续文档取舍、评估与审批缺口展示，详见台账同日“App 跨文档补证与年份精度首片”。

2026-10-13 质量复盘调整：用户要求先回看简历质量，再追查流程与工作资料整合。已核对实际发送的三页 PDF、App 实现和本机底稿，确认存在首屏定位弱、旧项目挤占篇幅、全量档案强制展示、语义结论夸大及资料跨文档对账不足等缺陷。51张可用卡仅5张满足展示条件，不代表其余经验不存在。P0-026 保持唯一 `next`，当前优先级改为：通过 App 接通已确认角色/时间/成果的对账 → 按完整 JD 职责取舍生成内容 → 校准评估并在审批展示缺口 → 真实 App 新版 PDF 验收；之后再推进新增投递及招聘反馈。先以统一平台/Feature治理的已有资料验证最小切片，不重建材料库或匹配引擎。首笔实投及旧快照保留，本轮复盘完成、修复待实施，面试目标未完成。依据见台账同日复盘和 `AIEF/docs/plans/2026-10-12-evidence-semantic-matching.md`；下一验收项沿用 P0-026，先完成其中的简历质量修复。

2026-10-12 首笔实投完成：用户确认的 `<local-candidate>` 平台负责人岗位已由 App 发送固定PDF并核验业务回执成功，平台状态回流为“已投递”（22:35）。本轮上传1/投递1/未决0，单次授权1/1已耗尽；已补齐新版附件核验与按岗位/PDF绑定的单次授权入口，1223项测试通过。当前推进真实招聘反馈、面试及复盘，P0-026保持唯一 `next`，不把投递成功等同于面试磨练完成。下一验收项：`外部真实 Tauri 页面自动化：small_company_high_match_delivery（首笔高匹配实投与状态回流已验，待面试反馈）`。

2026-10-12 登录接续：用户完成猎聘登录，App 已核验有效会话与可用附件入口（支持 PDF、最大20M）。最终固定 PDF 与岗位不变，下一步等待具体上传/投递确认；本次仅只读检查，上传和发送仍为 0。

2026-10-12 App 事实补齐接续：已在真实 App 中纠正 EC+ 个人期间、录入三项个人 AI 工程成果并确认档案，接通补充成果评估和完整事实选材。最终 51 卡评审、12 缓存/0 模型调用，86/73/75；事实完整，可进入人工审核，自动质量条件仍未全达。三页 PDF 已由 App 固定并预览，剩余为 App 内猎聘登录、具体上传/投递确认及业务回执；本轮实际上传/发送 0。1212 项测试通过，P0-026 仍唯一 `next`，详见台账“App 事实补齐与固定 PDF 审核”。

2026-10-12 App 偏好接续：已在真实 Tauri 页面完成职业方向材料导入、8 条原文偏好核对保存、平台负责人完整 JD 审核与全 51 卡语义评估。岗位方向符合、模型适配 86，简历覆盖/表达各 73，仍不可投递；明显不符岗位在生成前 SKIPPED，后续阶段及未生成文案已真实复验。1200 项测试通过。下一步通过 App 对账写回底稿已确认的时间/角色并补入个人 AI 工程作品，重新准备可投递版本；新实投与面试反馈仍未完成，P0-026 保持唯一 `next`。详见台账“App 求职偏好与方向筛选”。

2026-10-12 按本机求职资料校准：本轮小公司面试验证仍以产品型公司或企业内部平台的 Tech Lead / 技术负责人为主，后端负责人/企业应用架构为桥接方向，研发效能、Developer Platform、AI 工程系统/Agent Harness 为探索方向；不以普通 Java 开发或客户交付、实施、驻场岗位补足投递数量。AI 关注执行框架、开发者工具、评估/权限/治理，不按模型训练或普通 API 集成岗位筛选。文档中的 200–800 人公司偏好和月薪约 4w 属正式跳槽参考，本轮公司规模按用户最新的小公司实验要求执行，不把资料旧版 12–15 次投递规划当成本轮发送授权。定位依据与版本区别见台账“本机求职倾向回查”。

2026-10-12 语义链路更新：已复用本机 Qwen 完成四岗各 51/51 张证据的分批语义评审、引用驱动选材/生成和独立评测。岗位适配为 50 / 60 / 42 / 62，四份仍待补证据；最终缓存复跑共 44 hits、0 模型调用。真实 Tauri 页面已验证默认语义模式、完整 51 卡池、运行与逐项引用展开；测试 1177 通过、1 跳过。主线仍需按语义缺口补齐事实并筛选高匹配岗位，再做授权实投及反馈。P0-026 保持唯一 `next`；下一验收项：`外部真实 Tauri 页面自动化：small_company_high_match_delivery（语义生成已验，待高匹配实投与面试反馈）`。详情见台账同日“证据约束的语义匹配接通与四岗验证”。

2026-10-12 质量修复更新：Quick Run 关键词与完整硬性条件拆分，引用检查接入独立 trace，职责空值 `[]` 不再冒充本人角色。四个已审核画像通过 App handler 规则模式复测，均完成生成但评估为 52 / 54 / 55 / 52，保持 `NEEDS_EVIDENCE`；确认档案的关联问题已解除，三张反复入选的项目卡仍有本人职责、明确年月及任职时间冲突待核对，规则选材与模板技术栈展示仍需后续优化。测试 1158 通过、1 跳过；本轮是本地规则管线验证，不是 Qwen 重跑或真实页面深度验收。P0-026 保持唯一 `next`，详情及证据见台账同日“评分口径修复与四岗规则复测”。

2026-10-12 主线调整与投递实验转向：用户决定 BOSS / 智联 / 51job / 脉脉 / 拉勾因没有可操作的官方 API 或 CLI 暂不接入，先深化 App 自身能力；投递实验不再使用低匹配 JD，改用“JD 高匹配 + 微小公司”的猎聘岗位磨练面试（当前阶段以微小公司投递为主，大公司为后续目标）。为此落地：官方搜索返回的公司规模 / 融资阶段 / 行业 / 经验 / 学历透传到线索与画像，线索列表新增“公司规模”筛选（100 / 500 人以下）且关键词兼容工作地区；完整 JD 读取接受猎头岗位 `/a/<id>.shtml` 并放宽为“无截断提示且正文 ≥ 200 字即完整”；人机验证分发页重定向如实报告为安全挑战。真实数据：10 组关键词检索新增 243 条线索，上海 100 人以下 14 条，入围 7 条中 4 条取得完整 JD（两条猎头岗、两条企业岗），由本地 Qwen 解析并按实验授权保存为完整画像；其余因平台对脚本 UA 的人机验证拦截保持阻断，不绕过。P0-022 `maimai_source_integration` 回到 `not_started`；新增 P0-026 `small_company_high_match_delivery` 为唯一 `next`。下一验收项：`外部真实 Tauri 页面自动化：small_company_high_match_delivery（待实现）`。

2026-10-11 P0-022 首片实施：按《人工导入来源契约》（核心规范新增节）落地：来源链接按域名识别平台（maimai / lagou / boss / zhilian / qiancheng / liepin / other），人工导入平台在完整保存时只做 HTTPS 语法校验、不向平台发请求，画像与线索记录 `platform`、`import_mode: manual`、`source_recorded_at`，岗位页标明“人工导入 · 平台”；新增 `submission.recordManual` 手动投递记录（通道为平台码、`transport/mode: manual`、`status: manual_recorded`、`receipt_source: manual_tracking`，不可重试、可关联反馈），画像详情提供回填表单，投递列表通道显示平台中文名。L1 场景脚本 `tests/acceptance/test_scenario_maimai_source_import.py` 覆盖矩阵五项 covers 并写出旅程报告。状态仍为 `next`：深度验收需用户提供一条真实脉脉职位链接与完整 JD，在真实 Tauri 页面走通导入、生成与手动记录。

2026-10-11 P0-025 收口：用户决定按三次真实只读同步证据将 `liepin_feedback_sync` 标为 `deep_verified`（限制如实保留：同步由用户点击触发而非外部自动化；两笔“停止招聘”待下次同步更新；切片 3 沟通页回复只读读取未做，若立项另建条目）。按 2026-10-11 平台复核时的既定顺序，P0-022 `maimai_source_integration` 恢复为唯一 `next`；下一验收项：`外部真实 Tauri 页面自动化：maimai_source_integration（待实现）`。

2026-10-11 P0-025 进度：三次真实只读同步（06:26Z / 06:42Z / 07:00Z）均在 App 自有猎聘会话内完成，17 行记录中 16 笔受控投递全部按岗位编号匹配，第三次读到 14 笔真实状态（暂不合适 4、已查看 8、已投递 2），2 笔“停止招聘”当次归为 unknown（closed 映射随后落地，待下次同步更新），平台写入 0；总览“投递进展”卡已用真实数据读回。证据与只读边界汇总见 `outputs/acceptance/liepin-feedback-sync-20261011/validation.json`，矩阵已挂证据。限制：三次同步由用户点击触发而非外部自动化；切片 3（沟通页回复只读读取）未做。`liepin_feedback_sync` 仍为唯一 `next`，是否按现有证据收口为 `deep_verified` 以及之后的 next（S7 脉脉或切片 3）由用户决定。下一验收项：`外部真实 Tauri 页面自动化：liepin_feedback_sync（三次真实只读同步 16/16 匹配已留档，待用户决定收口）`。

2026-10-11 主线调整：用户决定先深化 App 与猎聘渠道。探索确认官方 14 个工具没有投递进展查询，反馈只能由 App 自有猎聘会话只读读取页面；App 现有反馈迭代机制的来源仅有本地评测与手动记录，16 笔真实投递没有任何平台进展数据。新增 P0-025 `liepin_feedback_sync`（猎聘投递反馈回流）为唯一 `next`，设计见 `AIEF/docs/plans/2026-10-11-liepin-feedback-sync.md`；S7 脉脉回到 `not_started`，待反馈回流完成后按用户决定恢复。下一验收项：`外部真实 Tauri 页面自动化：liepin_feedback_sync（待实现）`。

2026-10-11 平台官方渠道复核与路线调整：应用户要求先核查 BOSS 直聘、智联招聘、前程无忧 51job 的官方接入渠道。结论：三家均没有面向求职者或第三方 App 的官方 API、MCP 或 SDK；BOSS 仅有企业 ATS 白名单且官方 AI 产品封闭，智联的 AI 版与职悟空为封闭产品、未登录页面薪资打码且完整 JD 需登录，51job 仅有企业 ehire、未登录可读搜索列表但详情页触发滑动验证且条款禁止抓取；可用的社区方案全是浏览器自动化或逆向接口，与平台协议冲突并有账号风险。用户决定：三家在线只读任务标为 `blocked` 并记录原因，统一改为在 App 内人工导入职位链接与完整 JD，走审核、匹配、定制版本与人工结果追踪，样本在 S8 计入来源覆盖、不冒充在线接入；主线接着做 S7 脉脉与拉勾来源导入。P0-022 `maimai_source_integration` 成为唯一 `next`；下一验收项：`外部真实 Tauri 页面自动化：maimai_source_integration（待实现）`。本轮无代码改动、无平台写入；核查详情见接入方案 2026-10-11 节。

2026-10-10 P0-018 收口：核对发现 App 已于 10 月 9 日 09:00（上海）自动执行第二日批次（视涯科技），1/1 success、未决 0，回执 HTTP 200 / flag=1，PDF 指纹与批准快照、SQLite 一致；10 月 8 日投递文件指纹不变，累计 16 条 success。真实 sidecar 只读读回：授权已按到期时间判为 expired、今日 0/3、两日历史均 completed；10 日无新批次。用户决定按现有证据收口，`daily_authorized_delivery` 标为 `deep_verified`，限制如实记录：每日合计 3 次上限仅隔离 SQLite/测试时钟验证，常驻调度仅开发壳，10-09 批次后的原生页面重启读回未在本会话执行。P0-019 `boss_readonly_integration` 成为唯一 `next`；下一验收项：`外部真实 Tauri 页面自动化：boss_readonly_integration（待实现）`。本轮无新增上传/发送/删除，授权未变。证据：`outputs/acceptance/daily-cross-day-20261009/validation.json`。

2026-10-08 首日实投更新：具体历史恢复入口确认后，两份指定旧测试附件已由 App 移除，本地原件/回执保留；原两岗每日授权正式启用。App 首个真实每日批次已完成固定 PDF 全链路，1/1 success、未决 0；后续候选与执行时间仅保存在本机授权记录，App 运行与唤醒条件保持。P0-018 仍唯一 next，真实跨日结果待观测，当前每日 1 岗验收不等于总体每日 3 岗目标全部完成。

2026-10-08 执行授权更新：用户已确认两岗/PDF 与两份旧附件移除。自动审批审查将恢复旧成功记录所需的“固定此 PDF 与目标岗位”按钮判为可能准备旧岗位投递；代码只读恢复分支已核对，仍被拒绝，已请求具体入口确认，未绕过。当前 App 草稿与 14 笔历史成功保持不变，无新增平台写入；P0-018 仍唯一 next，真实每日与跨日验收未完成。

2026-10-08 真实候选准备更新：用户授权实测后，App 官方搜索、完整 JD、Qwen 解析、完整职业简历生成、固定 PDF 及每日清单已走通两个新岗位。修复“职位描述”识别、模型重复超时及附件经历同步提示遮挡。两份 PDF 各两页并已核验；两日限额草稿已保存但未启用，具体清单与新增旧附件永久删除范围待确认。当前三份平台附件占用、无上传控件，本轮没有上传/投递/删除。P0-018 仍唯一 next，实际每日批次与真实跨日结果未完成，详见台账及 daily-candidates-20261008 验收记录。

2026-10-08 中断恢复分支更新：App 每日历史已显示逐项阶段与核验入口，结束中断时保留成功/未开始、上传和发送在途保守置未知，换清单或跨日不能绕过全局未决。已通过隔离 SQLite/测试时钟及本地合成中断状态的原生结束、核验、重启验收；测试数据已归档，真实资料/授权/历史投递未变。此完成 App 恢复分支，不代表真实每日执行成功；P0-018 仍唯一 next，剩余为实际非空授权批次完整执行、平台连续操作与真实多日结果观测。

2026-10-08 App 接续功能更新：Jobs 的完整已保存 JD 可精确进入 Quick Run，完整生成结果可直接进入原 PDF 固定/预览，再到原每日候选清单；不再依赖手抄编号。原生 PDF 与通用 Agent 审批路径已区分，导航不自动授权或写平台。本地非真实岗位样例已走通并在重启后恢复，测试数据已归档、真实数据与授权未变。后续按用户要求继续完善和验证 App 的每日执行能力，不由开发代理代完成业务；真实非空授权和跨日执行仍未验收，P0-018 保持唯一 next。

2026-10-08 用户已明确接受当前完整简历底稿，App 职业档案已确认，内容和排版验收按通过处理，后续持续优化。下一步按已确认档案绑定完整 JD、生成岗位定制版并准备候选清单；不再重复要求确认同一底稿，不将持续优化作为主线前置阻塞。P0-018 保持唯一 next，尚未启用新的每日投递授权。

2026-10-08 前置资料已接入：找回既有确认时间线与原始工作资料，职业档案现含 4 段工作、2 段教育及 5 组能力，原生 App 已回读并导出两页完整底稿，75 条事实可追溯。当前待用户核对并确认底稿，再绑定完整 JD 定制；不得继续将“没有任职/教育资料”作为 blocker。档案未确认、无目标 JD，未新增真实投递，P0-018 仍唯一 next。

2026-10-05 完整简历内容前置已实施：复用原个人资料文件、证据库、A/B 模板、固定 PDF 与批准队列，补齐职业档案编辑确认、完整章节和写操作内容门禁。真实 App 已验草稿保存/重启恢复、缺项阻断、历史 PDF 预览；合成档案通过完整输出验收。下一步先在简历中心补齐并确认真实任职时间轴、教育展示选择和核心能力，补足项目职责/时间，再生成和审核正式版本。当前真实档案仍未确认，在内容验收通过前不新增真实投递；P0-018 保持唯一 next，不把合成样稿或格式验证当作个人简历达标。

2026-10-05 质量前置更新：按用户要求先接通已有目录材料 → 文档片段提炼/审核 → 证据勾选 → App 生成/PDF。新样稿通过一页视觉与全文追溯检查，但两项经历的本人职责/时间仍缺，保持 NEEDS_EVIDENCE。新清单的三条候选在真实 App 当前均未取得完整 JD，尚未建立可启用的投递版本；继续补齐这两类前置缺口，P0-018 仍唯一 next，不把样稿优化或测试钟当作每日实投完成。详细事实见台账与 `outputs/acceptance/resume-quality-20261005/validation.json`。

2026-10-05 实施更新：P0-018 首版已接入持续授权清单、每日共享额度、App 内单批触发、暂停撤销、到期/午夜与未决阻断。真实 App 通过草稿保存、重启恢复、空清单禁止启用和撤销；没有新增发送。非空清单与实际每日执行、WebKit 重载连续操作、真实跨日验收仍待完成，状态保持唯一 next。下一验收项：`外部真实 Tauri 页面自动化：daily_authorized_delivery（首版已实现，待非空授权与跨日实测）`。

2026-10-02 验证更新：用户追加授权的三岗 PDF 批次已完成 3/3；App 新增并真实验证指定旧附件移除，保留本地原件与历史回执，再完成第三笔上传/发送/回执闭环。累计 14 条真实投递证据 verified，当前验证额度全部用完。此为明确授权的补充验证，不是每日自动投递；P0-018 仍为唯一 next，六平台后续顺序不变。

2026-10-01 当前状态：P0-017A 与 P0-017 已通过真实 App 两路线的结果/反馈收口及 11 条历史投递只读统一验收。唯一 next 为 P0-018 每日受控投递；下一验收项：`外部真实 Tauri 页面自动化：daily_authorized_delivery（待实现）`。现有授权批次仍为 10/10 与 1/1，本轮没有新增发送。以下日期段落保留阶段历史，以最新状态为准。

下一次“继续推进项目”默认只处理 `acceptance/journey_implementation_matrix.yaml` 中第一个 `status: next` 的任务。

2026-09-27 重新排程：先完成 P0-011 的猎聘官方凭据与只读接入，P0-017 改为 `blocked`，等待认证、完整 JD、指定简历版本及回执契约就绪。`next` 只表示下一实施任务，不表示已接入或已验收。本次是方案与计划更新，没有启用平台写操作。

2026-09-28 验收更新：P0-011 已完成真实原生只读成功与清理阻断链，状态为 `deep_verified`。既定 S2 单列为 P0-017A `official_delivery_prerequisites`，作为唯一 `next`；P0-017 真实投递保持 `blocked`。新增条目仅明确原有前置工作，尚未开始实施。矩阵 order 仅用于排序，既有 P0 编号不变。

2026-09-29 产品边界纠正：闭环必须由 App 自身完成选岗、准备、审批、发送与回执追踪。开发代理控制招聘网站不算产品能力；外部自动化仅操作 App 做验收。Jobs 默认简历审批入口与结果来源分离已实现，原生防重/未审核阻断/历史来源展示已验；新岗位准备成功链尚待原生验收。已有 1 次真实发送由网站外部观察确认，App 自行确认仍为 0，不能把它计入 10 岗位 App 闭环。后续先补程序可核验回执和生成 PDF 附件绑定，不再用网页观察补写产品成功；保持 P0-017A 唯一 next / P0-017 blocked。

2026-09-29 当日收口：默认简历单笔真实 App 链已通过。一个已授权测试岗位经 App 审核、准备、批准后仅发送一次；实际返回“应聘成功”，修复词表后由 App 本地核验保存回执，状态和追踪跨重启保留。累计实际确认 2 次（App 自行确认 1、历史外部观察 1），10 岗位 App 目标为 1/10。当前 P0-017A 的剩余重点调整为生成 PDF 绑定、通用 API L3/反馈契约及余下批次；不能再以“默认简历回执仍未知”作为 blocker。单笔默认简历成功不解除 PDF 版本绑定要求，也不代表定时投递已启用。

2026-09-29 十岗批次结果：累计 10 个真实岗位已确认成功，包含历史两笔及本轮 8 笔，均为平台默认简历；第一笔已由 App 用精确响应 hash 引用本机接收证据完成程序确认。SQLite 批次上限已耗尽（10/10），不得因原始验收质量差异追加第 11 次。PDF 路线原生会话实测 `LOGIN_PAGE_REDIRECTED_TO_BLANK`，指定附件发送尚未完成；此为近期目标仍未完成的部分，P0-017A 唯一 next 保持。后续先解决产品 PDF 接入与生成/版本绑定，准备完成前不再发真实请求，额外实投需新授权。

### 招聘平台接入批次（2026-09-27）

2026-09-30 本次收口：用户允许平台附件影响后，指定 PDF 已通过 App 完成固定快照、一次上传、平台附件身份与原字节回读绑定、目标会话/确认框核对、最终一次发送和业务回执落盘。额外 `generated_pdf` 批次 1/1 success，与原十岗 10/10 独立，当前测试授权均已耗尽。后续 P0-017A 仅收口通用 API L3/runbook/反馈契约，不能再重复本次上传/实投或把 PDF/授权写成 blocker；每日自动 3 次与六平台后续工作仍按既定顺序推进。

2026-09-30 当时的下一验收项为默认简历/PDF 之后的统一验收与反馈收口，已于 2026-10-01 完成。

2026-09-30 PDF 前置进展：App 自有 Tauri 会话已完成用户登录、程序检查和重启保留，旧 Playwright 空白页已不再阻塞这条兼容路线。App 已读取附件面板要求，并由真实 TXT 材料审核、完整 JD 审核、模板生成及 PDF 导出形成一份本地候选文件。平台实际提示上传将解析补全在线简历、且附件随后续主动投递一起发送；这一影响尚未获得授权，本轮未上传或发送。指定附件身份绑定、发送适配与业务回执仍未完成，不能把剩余工作写成只差授权。补充 1 次 PDF 的批次存储已实现，但未启用实际额度；原十岗仍为 10/10。P0-017A 唯一 next / P0-017 blocked 不变。

方案、来源快照和复用点见 [招聘平台接入方案](../AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md)。用户已确认六平台进入整体目标：猎聘、BOSS直聘、智联招聘、前程无忧 51job 为核心平台，脉脉、拉勾为补充来源。六家都有明确交付任务；优先完成猎聘闭环，保留既有 WIP，不新增通用 MCP 平台或第二套投递引擎。

| 顺序 | 范围与依赖 | 退出条件 |
| --- | --- | --- |
| S1 / P0-011 已验收 | 猎聘官方 Token + HTTP，只读搜索/简历读取；复用设置页、sidecar、infra 与 Job Lead | 真实 Tauri 配置/回读脱敏；后端区分有效、失效、限流和非 JSON；真实只读结果可入 Jobs；新协议不要求浏览器 profile；无写请求 |
| S2 / P0-017A 已验收 | S1 通过后补完整 JD、岗位原始 ID/type、版本绑定；调整平台路由、审批续跑和 API 证据契约，补最小稳定岗位键 / in-flight 防重 | 重启不重复提交成功或未决岗位；完整 JD 经审核；发送内容与已审批版本有可审计绑定；成功/失败/未知回执有依据；未知不重试、不降级邮件；缺任一项则保持阻断 |
| S3 / P0-017 已验收 | S2 就绪，具体岗位、简历版本和最终提交已授权 | 一次真实投递的业务回执、版本、submission log、L3 与反馈入口互相可追溯；仅记录 blocker 不算完成 |
| S4 / P0-018 已验收 | S3 通过后，扩充防重的并发/跨日验证、上海日界成功计数、单个触发入口、持续授权与受控凭据存储 | 所有启用平台合计每天最多 3 次确认成功；未知占位并暂停；重启/换版本不重投；暂停/撤销有效；连续多日留下真实结果或缺额原因 |
| S5 / P0-019 BOSS，在线只读 blocked，改人工导入 | 猎聘主线及每日目标通过后，修复固定版本的 CLI 只读适配 | 搜索→详情→完整 JD→审核→匹配/定制版本/追踪真实贯通；认证失效、错误和空结果正确区分；只读完成不开放投递 |
| S6 / P0-020 智联、P0-021 51job，在线只读 blocked，改人工导入 | BOSS 只读通过后，分别核实两平台维护路线、认证与岗位读取契约 | 每个平台独立通过在线搜索/详情、完整 JD 及下游闭环；智联旧版支持、51job URL 识别或人工导入均不能代替在线验收 |
| S7 / P0-022 脉脉、P0-023 拉勾（暂缓） | 复用已有岗位入口，完成两家补充来源；默认排在 S6 后 | 分别完成真实职位链接+完整 JD 导入、来源/时间标记、审核、匹配/定制版本/人工结果追踪；汇总六平台来源覆盖 6/6，在线接入与投递状态单独展示 |
| S8 / P0-024 六平台覆盖验收 | 汇总上述各平台已有真实页面与业务证据，补验实际缺口 | 来源覆盖 6/6、四核心在线只读 4/4 分别达标；猎聘人工补 JD 不算在线详情完成，缺失时保留该项 blocker；不要求六平台自动投递，不另建审计框架 |

当前不安装/升级社区 CLI，不下载 Firefox，不开启定时任务。当前唯一 `next` 为 P0-026 `small_company_high_match_delivery`（不在本表内，见 Current Focus 与矩阵 order 27）；S5、S6 三家在线只读因无官方渠道于 2026-10-11 标为 `blocked` 并改走人工导入，样本在 S8 计入来源覆盖；S7 脉脉、拉勾与 S8 为 `not_started`，在 P0-026 之后按序恢复；P0-011、P0-017A、P0-017、P0-018 与 P0-025 已 `deep_verified`。默认按表串行推进；同批平台独立验收，某平台被外部契约阻塞时可记录原因后重排依赖和唯一 `next`，不删除该平台目标，也不形成并行 WIP。S7 自 2026-10-11 起依赖已验收的 Jobs 手工 JD/线索入口，不再依赖 BOSS 只读基线。历史 P0-012/013/015/016 证据保留为旧实现验证；迁移到官方 API 后要重验对应受影响切片，不能沿用其状态宣称新路线通过。

六平台来源覆盖的共同完成标准：每家至少 1 个真实来源的完整 JD 样本，贯通来源/获取时间、画像审核、可解释匹配、定制简历版本关联和结果追踪。人工导入/手工反馈必须明确标记；四家核心平台在线只读任务只有真实搜索/详情和失败路径验收通过才可完成，不能以人工样本将其升级为 `deep_verified`；2026-10-11 起 BOSS/智联/51job 的在线只读保持 `blocked` 并保留原因，其人工导入样本只计入来源覆盖。平台投递能力另验实际发送版本、授权和回执。

后续矩阵映射：P0-018 `daily_authorized_delivery`；P0-019 `boss_readonly_integration`；P0-020 `zhilian_readonly_integration`；P0-021 `qiancheng_readonly_integration`；P0-022 `maimai_source_integration`；P0-023 `lagou_source_integration`；P0-024 `six_platform_coverage_acceptance`；P0-025 `liepin_feedback_sync`（2026-10-11 新增，猎聘投递反馈回流）。这些是目标与待实施验收，不声明新脚本或结果产物已存在。

## Accepted Delivery Goal / 已确认的近期投递目标

2026-09-28 用户要求一次 10 岗位的真实闭环验证批次，偏好低 JD 匹配度且薪资待遇好，目的是尽量避开未来正式求职机会。本批次先验证 1 条完整成功链再扩至 10 条，成功须有实际发送版本与平台回执依据；低匹配不能保证真实投递不影响后续求职。该请求不永久改写下述每日 3 次自动投递目标，亦不把测试/检查结果算作真实投递。当前前置检查与阻断见项目台账，仍沿 P0-017A → P0-017 推进。

2026-09-05 用户同意：先以猎聘单平台完成每日合计 3 个不同岗位的自动投递，再按实际需要扩展平台；每天一个批次即可，不要求三个执行时间点。此处记录已确认方向，不代表功能已实现或真实投递已启用。

2026-09-27 用户补充确认六平台整体覆盖目标，已替换“是否扩展平台按需决定”的规划表述；首个平台和每日目标仍按既有阶段实施。多平台启用后，共用每日合计 3 次的上限，不变为每家 3 次；规划纳入不代表写操作已获授权。

- 首版简历来源：优先从系统基于 Personal Profile、工作材料/Evidence Cards、目标公司与 Job Profile/JD 生成的版本中选择；已有版本适合同类岗位且审核通过时复用，缺少合适版本时沿现有生成链路补齐，再导出 PDF。用户上传的简历是可选的导入/基准资产，不能把“用户提供现成 PDF”设为默认前提，也不能把已有生成能力整体后置。
- 成功标准：按 `Asia/Shanghai` 自然日统计，所有启用平台合计的目标且上限为 3 次确认成功的投递；候选不足、登录失效或结果不明时报告原因，不以检查模式、模拟成功或重复投递补足次数。
- 授权目标：支持预先明确渠道、候选范围、简历版本、每日上限和有效期，范围内自动执行、可暂停或撤销；具体岗位与简历的授权记录尚待建立，现有真实投递确认门禁继续生效。
- 最小路线：官方凭据与只读接入（P0-011 已验收）→ 当前 P0-017A：完整 JD / 版本 / 回执契约及最小持久化防重 → 单次真实投递闭环（P0-017）→ 每日目标（P0-018）→ BOSS（P0-019）→ 智联/51job（P0-020/021）→ 脉脉/拉勾（P0-022/023）。各平台达到规划接入深度后再逐项扩展投递，后续阶段不提前标记完成。

### 已有能力探索（2026-09-05）

以下保留当时的定位与实施历史；当前传输方案、下一步和状态以 2026-09-27 批次表为准，浏览器附件探索不再是默认推进路线。

已核对 `openspec/changes/autonomous-agent-delivery-loop/`、相关 `tools/` 实现与测试、`scripts/`、当前投递产物及 Job Lead bridge WIP；以下结论作为实施起点，不用旧清单的勾选状态替代实际能力判断。

| 能力 | 已有定位 | 处理方向 |
| --- | --- | --- |
| 自动/手动模式、单次投递上限 | Agent design 第 2、3 节；`tools/config/fragments.py`、`tools/orchestration/review_stage.py`、`agent_loop.py` | 已有设计和部分实现；复用并接通批准后的执行，单次 `max_deliveries` 不代替每日上限 |
| 猎聘执行与候选准备 | `tools/submission/liepin.py`、`tools/channels/liepin.py`、现有 External L3 Job Lead bridge WIP | 沿现有渠道修复成功判定并完成真实验证，不新建浏览器投递器 |
| 频控 | `tools/submission/rate_limit.py` 与 `test_submission_rate_limit.py` | 复用操作频控；当前计数在操作前发生，不能作为每日成功投递数 |
| 投递日志与运行持久化 | `tools/submission/storage.py`、`tools/infra/persistence/file_run_store.py` | 复用现有记录与产物；优先补必要索引或状态，不预设另建台账服务或数据库 |
| 幂等 | Agent design 第 10.3 节；tasks C5；`AgentLoop` 的本轮候选去重 | 原设计已存在，当前未找到持久化投递去重接入；补齐跨运行防重，换 run id、日期或简历版本不能自动重投同一岗位 |
| 每日触发与持续授权 | 已检查 Agent policy/CLI、投递脚本及工作流入口 | 尚未找到对应完整实现；在既有投递流程外增加最小触发与授权范围校验，不引入 Airflow/Celery 或新编排平台 |

P0-017 首批进展（2026-09-05 历史记录）：投递成功判定和 Job Lead bridge 的代码修复已通过本地测试，当时状态为 `next`。生成输入消费和共享 PDF 导出已补齐；Agent `_run_delivery` 已复用 exporter，按尝试保存并传递带版本/指纹的 PDF。`_send_resume_via_chat` 仍未绑定 `resume_path`，当前明确阻断默认平台简历发送；已有 `_upload_resume` 等能力需结合真实页面最小接通。下一步沿 App 自有 Playwright 会话核对附件入口，并完成候选内容审核和岗位有效性确认。缺口应落实为具体字段、证据或接口问题，不转化为要求用户在系统外制作成品 PDF。

生成前置能力已在本地补齐：见 `AIEF/docs/plans/2026-09-05-targeted-resume-generation.md` 与 ledger 的同日进展。已有存量测试岗位候选 PDF、独立追溯和规则评测，当前 71/100、`NEEDS_REVIEW`。接下来审核生成稿与具体缺口、确认岗位有效性，再将选定生成版本接入投递；本地集成测试和 PDF 检查不替代原生 GUI/真实渠道验收，P0-017 当时保持 `next`；当前状态见 2026-09-27 排期。

共享 HTML/CSS 排版已接入正式导出与简历中心；2026-09-05 已在重建的真实 Tauri 调试窗口完成候选选择、预览和 PDF 导出，文件位于 `outputs/<local-candidate>/formal-export/from-native-ui.pdf`。这一前置切片已验证，下一步仍是内容审核和正确 PDF 的投递绑定；每日去重、成功计数与定时入口按上述阶段后续推进。

## Efficiency And Quality / 效率与质量约束

- 工程取舍遵守 `constitution.md` 第 6 条：质量达标、效率优先、成本可控，不做重型工程。
- 新增内容或功能前遵守第 7 条，先探索已有设计与实现，在当前任务中说明复用点和缺口；对已有能力优先修复或接通。
- 在当前任务与依赖范围内，优先处理影响用户闭环的具体缺陷；用最小可验收切片推进，不以扩大框架或完善审计层本身作为进展。
- 方案需要新增依赖、架构层或明显增加模型调用时，简述它解决的实际问题、收益和维护成本；复用当前任务记录即可，不新增固定评审流程。
- 验证覆盖受影响行为、关键失败路径与必需门禁；只有声明真实旅程完成时，才必须具备对应的真实页面或渠道证据，小改动不重复执行无关全链路。
- 达到约定验收标准后收口；后续优化仅在存在实际质量缺口、运行瓶颈或重复维护成本时进入任务队列。

## WIP Rules

- 一次只推进一个 journey step。
- 未达到 `deep_verified` 的上游依赖，不允许推进下游深度验收。
- 新功能不能只以源码 marker 或页面加载作为完成口径。
- 每个 `verified_native` 或 `deep_verified` 任务必须有自动化验收脚本和完成证据。
- 场景化验收必须由外部自动化驱动真实页面、真实 Tauri 桌面壳或真实浏览器边界；内部 handler/unit/contract 和 audit 只能作为辅助或汇总证据。
- 遇到同优先级任务时，按旅程顺序推进，而不是按局部可做性随机选择。
- `next` 任务必须映射到项目愿景的一段闭环和 GUI/系统设计中的明确页面职责。
- 对业务能力新增或语义变更，必须优先补 OpenSpec/设计计划或确认已有设计覆盖；实现必须带失败测试或验收缺口测试。

## Task Queue

### P0-001 System Settings LLM Deep Acceptance

Status: `deep_verified`

Journey step: `system_settings_llm`

Vision link:

- 保障后续证据提炼、匹配、生成、评测有可配置模型供应商。
- 属于运行环境前置能力，不替代 evidence-first 主链路本身。

Unlocks:

- `quick_run_llm_consumption`
- `agent_run_llm_consumption`

DoD:

- 真实 Tauri shell。
- 真实 sidecar。
- 本地 OpenAI-compatible `/v1/models` stub。
- Provider defaults。
- 连接检查返回模型列表。
- 选择模型、保存、重新读回。
- API key 只回读 masked 状态。
- 未配置 base_url 返回结构化 `BLOCKED_LOCAL_PROVIDER`。

Evidence:

- 外部真实页面自动化（待实现）
- `docs/acceptance-depth.md`

### P0-002 Quick Run Consumes Persisted LLM Config

Status: `deep_verified`

Journey step: `quick_run_llm_consumption`

Depends on:

- `system_settings_llm`

DoD:

- 使用临时 policy 配置 LLM。
- Quick Run 真实 Tauri 页面读到同一 provider/model/base_url/masked key 摘要。
- Quick Run 启动结果或 run context 能证明使用的是持久化配置摘要。
- 仍以 Evidence Cards、Job Profile、Matching Report、Resume、Scorecard 为主链路产物，不把 LLM 配置验收误当成 pipeline 验收。
- 不泄露明文 API key。
- 失败时输出结构化验收事件。

Expected evidence:

- `tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py`
- `tests/unit/gui/test_quick_run_page_contract.py`
- `outputs/quick_runs/qr_*.json`
- `outputs/agent_runs/qr_*/summary.json`

### P0-003 Agent Run Consumes Persisted LLM Config

Status: `deep_verified`

Journey step: `agent_run_llm_consumption`

Depends on:

- `system_settings_llm`
- `quick_run_llm_consumption`

Expected evidence:

- `tests/acceptance/test_scenario_agent_run_guided_batch.py`
- `tests/unit/gui/test_agent_run_page_contract.py`
- `outputs/agent_runs/ar_*.json`

### P0-006 Quick Run Consumes Material-Derived Inputs

Status: `deep_verified`

Journey step: `quick_run_material_consumption`

Depends on:

- `evidence_material_sources`

DoD:

- Quick Run 真实 Tauri 页面能证明材料库来源已进入运行前上下文。
- Quick Run 启动结果或 run context 能证明使用的是材料派生 Evidence 与选中 Job Profile。
- 生成 Matching Report、Resume、Scorecard 时保留 Evidence Card 可追溯路径。
- 不把“页面能看到材料来源”误当成 pipeline 消费验收。

Expected evidence:

- 外部真实页面自动化（待实现）
- 外部真实页面自动化脚本（待实现）
- `outputs/quick_runs/qr_*.json`
- `outputs/agent_runs/qr_*/summary.json`

### P0-004 Resumes Material Library Native Acceptance

Status: `verified_native`

Journey step: `resumes_material_library`

Vision link:

- 对应 PLAN 的“日志层/原始材料”输入。
- 只是 evidence-first 的前置资产入口，完成后必须继续推进 Evidence Card 提炼与校验。

Evidence:

- 外部真实页面自动化（待实现）

### P0-005 Evidence Material Sources Native Acceptance

Status: `verified_native`

Journey step: `evidence_material_sources`

Depends on:

- `resumes_material_library`

Vision link:

- 将材料入口连到 Evidence 页面，但当前仍只到“来源可见”；下一层应推进 Evidence Card 提炼、review 和 results/artifacts 门禁。

Evidence:

- 外部真实页面自动化（待实现）

### P0-007 Evidence Card Extraction And Review

Status: `deep_verified`

Journey step: `evidence_card_extraction_review`

Depends on:

- `evidence_material_sources`

Vision link:

- 这是项目核心护城河：原始材料 -> Evidence Cards。
- 必须验证 raw_source、results、artifacts、review 决策和 No Fabrication。

Expected evidence:

- L1/API 合同：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_evidence_review_20260521 --level L1`
- 后端合同：`python3 -m pytest tests/unit/sidecar/test_evidence_handler.py tests/acceptance/test_scenario_generate_review_and_complete_evidence_card.py -q`
- GUI 合同：`python3 -m pytest tests/unit/gui/test_evidence_page_contract.py tests/unit/gui/test_i18n_catalog.py -q`
- 外部真实页面深度验收：外部真实页面自动化（待实现）

### P0-008 Setup Job Target Deep Acceptance

Status: `deep_verified`

Journey step: `setup_job_target`

Depends on:

- `evidence_card_extraction_review`

Vision link:

- 为 Evidence Cards 提供可解释匹配目标，是 Evidence -> Matching -> Resume 闭环的下一段。
- 必须验证 pasted JD、strict JSON draft、review 决策、incomplete/complete profile 门禁，以及可访问 source URL 时的 Job Lead 双向链接。

Expected evidence:

- L1/API 合同：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_job_target_20260521 --level L1`
- 后端合同：`python3 -m pytest tests/unit/sidecar/test_jobs_handler.py tests/acceptance/test_scenario_setup_job_target.py -q`
- 外部真实页面深度验收 主入口：外部真实页面自动化（待实现）

### P0-009 Quick Run Generate And Evaluate Resume

Status: `deep_verified`

Journey step: `quick_run_generate_and_evaluate_resume`

Depends on:

- `system_settings_llm`
- `evidence_card_extraction_review`
- `setup_job_target`

Vision link:

- 完成单岗位主链路：eligible Evidence Cards -> explainable matching -> fact-preserving resume/PDF -> scorecard/gap feedback。
- 必须验证 complete job profile/JD、Personal Profile、saved eligible evidence 的选择、resume positioning 记录、匹配报告、候选人可见简历、PDF、Scorecard、gap tasks 和独立事实追溯。
- 简历生成目标是“针对目标公司/岗位簇的可投递版本”，不是一份简历投所有公司/岗位；候选人 PDF 不得包含 `Evidence trace`、本机路径、source report、内部 evidence id 或系统版本标题，这些追溯信息必须进入 run record / `resume_trace` / scorecard。
- Scorecard 未达可投递阈值、Personal Profile 缺必需字段或仍有必需 gap tasks 时，Quick Run 必须输出 `NEEDS_REVIEW` / `NEEDS_EVIDENCE`，不得把 PDF 标为合格投递版本。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py`
- GUI acceptance：外部真实页面自动化（待实现）
- Run record：`outputs/quick_runs/qr_*.json`
- Pipeline summary：`outputs/agent_runs/qr_*/summary.json`

### P0-010 Agent Run Guided Batch

Status: `deep_verified`

Journey step: `agent_run_guided_batch`

Depends on:

- `quick_run_generate_and_evaluate_resume`
- `agent_run_llm_consumption`

Vision link:

- 将已验证的单岗位 Quick Run 闭环扩展到 Agent Run 的 10 状态机。
- 必须验证 gate/review/delivery 边界：未人工批准不得进入外部投递，运行日志必须可追溯。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_agent_run_guided_batch.py`
- GUI acceptance：外部真实页面自动化（待实现）
- Run record：`outputs/agent_runs/ar_*.json`
- Review queue：`outputs/review_queue/ar_*.json`

### P0-011 Channel Session Setup / 官方凭据与只读接入

Status: `deep_verified`

2026-09-28 真实验收完成：承接用户已配置会话，外部 CUA 重新验证连接、读取/展开平台简历、搜索导入 19 条摘要并刷新回读；清理后恢复未配置、预览消失，无凭据搜索明确 AUTH_REQUIRED 且既有线索保留。没有读取 Token、保存简历正文或发起投递。实际动作证据为 `outputs/acceptance/liepin_official_readonly/native-readonly-live-20260928.json`。清理测试后当前会话未配置，后续查询需重新输入官网 Token（官网授权未撤销）。

2026-09-28 早前实施记录：官方只读 HTTP、会话内 Token、Settings 验证/清理/简历预览和 Jobs 搜索入库已经接通，本地回归与前端构建通过，设计/RPC 已同步。真实 Tauri 调试窗口已确认设置入口和后端就绪；当前等待用户在 App 配置 Token，账号业务成功、真实搜索入库和清理动作链仍未验收。`outputs/acceptance/liepin_official_readonly/native-readonly.json` 明确记录 `complete=false`，本任务不因本地测试或设置卡可见而提升完成状态。

2026-09-28 入口修复：已使用固定 `/mcp/auth` 地址与原生系统浏览器命令替代普通外链，外部 CUA 点击后确认 Chrome 的“授权配置 — 猎聘 CLI”标签页。该切片证据为 `outputs/acceptance/liepin_official_readonly/authorization-link-20260928.json`；真实账号验证仍待用户配置 Token。

2026-09-27 原任务安排：复用已有页面和 sidecar，在 infra 接入猎聘官方 Token 与只读 HTTP。认证方法迁移不继承旧 browser 验收结果；当前只有历史账号只读样本和本轮公开契约/元数据核对，App 接入尚待实施。Firefox 下载授权不再是本任务依赖。

2026-09-08 补充：用户实际登录时出现延迟 `about:blank` 跳转，已确认来自当前网站脚本。默认 Chrome 与已有 helper 均不兼容；短暂打开表单不代表可用。Firefox 兼容验证依赖下载尚待授权，下游深度验收继续暂停。

2026-09-09 调研更新：已找到猎聘官方 Token + MCP/CLI 路线，用户完成人工登录；V2 确认简历与搜索的只读成功样本（HTTP 200、业务码 0、简历文本和 20 个不同岗位）。本批 `jobType="2"` 与投递 `jobKind` 的官方编码范围一致；不再以下载 Firefox 作为调研前提。现行 App 的 Playwright 登录方式仍未替换，不能提升本任务验收状态；剩余重点为正式只读接入、完整 JD、指定附件版本与真实投递回执。详见 `docs/reports/2026-09-08-liepin-integration-research.md`。

2026-09-06 复核：原实现只接受前端信号，历史 `deep_verified` 不成立。现已真实接通 App 打开登录窗口与未登录检查，原生证据位于 `outputs/acceptance/app_session_20260906/`；真实人工登录成功与复用仍待验收，不推进下游深度完成声明。

Journey step: `channel_session_setup`

Depends on:

- `agent_run_guided_batch`

Vision link:

- 在受控投递前建立官方认证与真实岗位读取边界，为完整 JD 和可解释匹配提供可追溯输入。
- 用户在官方页面完成登录和取凭据；App 后端只读验证，不保存密码、不处理验证码、不触发简历修改或真实投递。

Expected evidence:

- 已执行入口：`CUA 原生动作记录：outputs/acceptance/liepin_official_readonly/native-readonly-live-20260928.json`。
- 原生动作链：配置凭据 → 验证后端只读能力 → 回读仅显示状态 → 搜索 → Jobs 查看真实结果；覆盖失效/清理后的状态复位。
- 契约验证：分别处理简历 `errCode` / 搜索 `code`、简历文本和列表字段、401/429/非 JSON；确认无写请求和凭据泄露。
- 9 月 browser 会话脚本及 `tests/acceptance/test_scenario_channel_session_setup.py` 是复用基础和历史证据，需增量更新，不能直接证明官方 Token 切片通过。

### P0-012 Submission Check Mode

Status: `deep_verified`

Journey step: `submission_check_mode`

Depends on:

- `channel_session_setup`
- `agent_run_guided_batch`

Vision link:

- 使用已验证渠道会话、已保存 Job Lead 和已生成 PDF 简历执行 check-mode 投递演练。
- 必须记录登录态、目标岗位、简历路径、频控、安全门禁和 submit_skipped，仍然不得触发最终投递。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_submission_check_mode.py`
- GUI acceptance：外部真实页面自动化（待实现）

### P0-013 Feedback Iteration After Check Mode

Status: `deep_verified`

Journey step: `feedback_iteration_after_check_mode`

Depends on:

- `submission_check_mode`

Vision link:

- 将 check-mode 的 scorecard gap、阻断原因或目标恢复结果转成可审计的迭代决策。
- 必须保留原始 artifact，记录用户选择，并路由回 Evidence、Jobs 或 Resume 生成，让下一轮 check-mode 有明确版本关联。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_feedback_iteration_after_check_mode.py`
- GUI acceptance：外部真实页面自动化（待实现）

### P0-014 Closed Loop E2E Audit

Status: `deep_verified`

Journey step: `closed_loop_e2e_audit`

Depends on:

- `feedback_iteration_after_check_mode`

Vision link:

- 审计完整 evidence-first 求职闭环是否已从 L1 合同、外部真实页面深度验收 证据和 journey report 上连成一条链。
- 不新增业务能力，优先补齐断裂的 traceability、验收覆盖和文档事实。

Expected evidence:

- L1 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_closed_loop --level L1`
- 已完成：L1 acceptance runner 内置 `closed_loop_e2e_audit`，审计 selected cases、journey rules、外部真实页面深度验收 evidence 和 Quick Run -> Agent Run -> Submissions -> feedback iteration traceability。
- 审计证据：`outputs/acceptance/acceptance_closed_loop_20260522/closed-loop-audit.json`

### P0-015 External L3 Submission Validation

Status: `deep_verified`

Journey step: `external_l3_submission_validation`

Depends on:

- `closed_loop_e2e_audit`

Vision link:

- 将已验证的本地/check-mode 闭环推进到受控外部渠道验证。
- 必须继续保持显式用户授权、最终提交门禁、频控、target verify、无 secret/captcha 绕过和可回溯反馈记录。

Expected evidence:

- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 当前交付：L3 runner 默认生成 live blocker 记录；未显式授权或未单独最终确认时，`external_submission_attempted=false`。
- 真实渠道路径：仅当 `PIPF_EXTERNAL_L3_AUTHORIZED=true`、`PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true`、`PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true`、`PIPF_EXTERNAL_L3_SESSION_DIR` 指向已存在的共享 session 根目录且 Liepin 持久化会话目录包含非空、可识别的浏览器状态标记，并且 Job URL / resume PDF / profile / confirmed job id / confirmed recruiter 均已提供时，才允许启动 `tools.submission.run_submission --submit`。
- 证据：`outputs/acceptance/acceptance_external_l3/external-l3-validation.json` 与 `.md`。

### P0-016 External L3 Authorization Handoff

Status: `deep_verified`

Journey step: `external_l3_authorization_handoff`

Depends on:

- `external_l3_submission_validation`

Vision link:

- 将 External L3 blocker 转成可执行的授权交接包，而不是让用户只看到“未授权”。
- 必须列出下一次真实渠道验证所需 env、最终提交确认清单、禁止输入项和不含真实值的命令模板。

Expected evidence:

- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 交接包字段：`operator_handoff.required_env`、`pre_run_checklist`、`forbidden_inputs`、`runbook`、`preflight_command_template`、`preflight_review_checklist`、`preflight_review_result`、`authorization_readiness_action_plan`、`authorization_intake_checklist`、`authorized_template_release_decision`、`live_run_go_no_go_decision`、`command_template`
- 证据：`outputs/acceptance/acceptance_external_l3/external-l3-validation.json` 与 `.md`

### P0-017A Official Delivery Prerequisites / 既定 S2

Status: `deep_verified`

2026-10-22 状态同步：与 journey 矩阵 order 17 一致（2026-10-01 已复用真实 10+1 回执完成两路线原生反馈读回与统一验收）；下方 2026-09-28 起记录保留为当时过程，旧 browser/API 交接不再作为本任务阻塞口径。

Journey step: `official_delivery_prerequisites`

Depends on:

- `channel_session_setup`
- `external_l3_authorization_handoff`

沿既定 S2 核实完整 JD、平台原始 ID/type、审核版本与实际发送内容的绑定和回执语义；补齐审批续跑、平台路由、最小稳定岗位键/in-flight 防重以及 API recorder/L3/runbook。仍受 P0-017 的具体目标与最终提交授权边界约束，不因为只读认证通过就试投。该阶段按下述首片推进，旧 browser handoff 的完成状态不替代 API 契约验收。

2026-09-28 首片进展：公开完整 JD 获取、原 Lead/Profile 审核绑定、CLI/App 候选画像一致性和单平台路由已实施。真实 App 读取了一份 294 字 JD 并保留原来源绑定，当前为 `full_unreviewed`；真实解析被模型未配置阻断，原文保留且候选仍不可用。235 项相关回归、前端构建及独立复核通过，仅证明对应代码和输入首片，不提升整体完成状态。

模型进展：用户指定的本地 LM Studio `qwen/qwen3.8-27b` 已通过原生配置/保存/重启回读和真实后端 JD 解析验证；结构化输出兼容已修复。实际解析用已有 294 字快照，原网页刷新本轮不可用；尚未完成原生草稿审核/保存。证据为 `outputs/acceptance/official_delivery_prerequisites/lmstudio-qwen38-20260928.json`。

凭据进展：用户明确不接钥匙串、接受本机明文权限文件；已实现固定用户目录保存（文件 `0600`、目录 `0700`）、正常退出保留和主动删除区分。隔离凭据的真实后端跨进程保存/恢复/删除通过，见 `outputs/acceptance/official_delivery_prerequisites/liepin-local-credential-20260928.json`。用户保存后，本轮又验证真实 App 重启自动恢复、原生验证连接通过；未清理真实保存项。

测试候选进展：官方搜索薪资/地区字段已补齐并经原生列表/详情回读；60 条岗位中按月薪下限至少 35k 初筛 12 条，其中 7 条公开完整 JD 可用。既定测试岗位已在原生 App 解析并保存为待审核画像 （本机画像编号不公开），没有批准投递。候选资料为 `outputs/acceptance/official_delivery_prerequisites/ten-job-candidates-20260928.json`，完整待审核原文存于原 Lead/Profile；实际匹配、简历版本与发送闭环仍待完成。

审批进展：审批前固定 Markdown/PDF 与目标指纹、预览/校验、重复批准幂等、批准后恢复执行、企业排除复查与持久化投递占位已接入。合成样本已通过真实原生预览→批准→明确检查/阻断→重开恢复，未向平台发送；证据为 `outputs/acceptance/official_delivery_prerequisites/review-resume-20260928.json`。文件一致性与本地续跑验证不等于官方接口已能发送该 PDF。

剩余依赖：完成实际候选的画像审核/匹配/简历准备，明确实际发送内容与权威回执，再完成 API L3。官方输入仍只有 jobId/jobKind，当前写入继续以 `official_delivery_contract_unverified` 阻断，不转入旧浏览器或 Email。已请用户选择本次是否接受平台默认简历先投既定测试岗位；未收到选择前保持当前发送边界。P0-017A 尚未整体完成。

Expected evidence:

- 目标入口：`外部真实页面与官方契约验证：投递前置能力（待实现）`。
- 完整 JD 与审核版本可追溯、实际发送绑定有证据、成功/失败/未知回执有依据；未知结果不重试、不自动切换邮件。
- 真实 App 的审批/前置检查与辅助契约测试共同验证，无法绑定版本或缺关键接口时保留具体 blocker。

### P0-017 Authorized External L3 Live Run

Status: `deep_verified`

2026-10-22 状态同步：与 journey 矩阵 order 18（App 路线 saved_submission 只读验收）及下方 S3 已验收口径一致；真实 App 原生 PDF 投递已多次取得业务回执（最近一笔见 Current Focus 2026-10-22 第 19 笔）。旧 CLI 浏览器 L3 的 `missing_gates` 仅剩用户授权与最终提交确认，属可选补跑路线，不再作为本任务阻塞口径。以下 Blocker 为 2026-09-28 历史记录。

Blocker（2026-09-28）：官方只读已验收，真实本机凭据恢复与验证已通过；完整 JD 审核、指定简历/附件版本、真实业务回执、审批续跑、最小防重与 API 验收契约仍待 P0-017A 收口。本轮未发生真实投递。

Journey step: `authorized_external_l3_live_run`

Depends on:

- `official_delivery_prerequisites`
- `external_l3_authorization_handoff`
- `channel_session_setup`

Vision link:

- 在用户显式授权并单独确认最终提交后，执行一次真实外部渠道 L3 验证，或记录真实渠道 blocker。
- 必须把真实渠道结果或 blocker 与 submission log、L3 validation record 和后续反馈追溯连接起来。

Expected evidence:

- 下列 session 目录、browser 步骤与旧 runbook 属于当前浏览器实现。官方 API 迁移必须同步 recorder、L3、runbook 与受影响验收，以后端凭据检查和版本/回执证据落实等价门禁；不得伪造浏览器状态文件，或将 Token 填进旧授权模板来放行。
- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 前置条件：用户提供 `PIPF_EXTERNAL_L3_AUTHORIZED=true`、`PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true`、`PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true`、指向已存在共享 session 根目录的 `PIPF_EXTERNAL_L3_SESSION_DIR`、真实 Job URL、resume PDF、profile YAML、确认 job id 与确认 recruiter。
- 候选准备入口：`python3 -m tools.acceptance.external_l3_job_lead_bridge --lead-source <job_leads.yaml> --lead-index <n> --resume-pdf <resume.pdf> --profile <profile.yaml> --session-dir <session-root>` 可从已验证 Job Lead 与 check-mode submission log 自动生成脱敏确认包和 shell-safe env 模板；该模板默认不授权、不确认最终提交，仍需用户审批候选和授权边界。
- 人工运行入口：`docs/runbooks/external-l3-live-run.md` 是 P0-017 真实运行 runbook；`operator_handoff.runbook` 和 Markdown 报告必须引用该路径，并声明文件存在状态、SHA256 指纹、必需章节完整性、运行前必须复核、复制命令前必须替换 live 输入、原始 live 输入不持久化。
- 预检证据：`external-l3-validation.json` 必须包含 `live_run_readiness.ready`、`submit_command_allowed`、`missing_gates` 和逐项 gate 状态；真实输入 gate 必须覆盖 Job URL 格式、resume PDF 文件存在且扩展名有效、profile YAML 文件存在且扩展名有效。
- Pre-submit blocker 诊断证据：submit 命令启动前产生 live blocker 时，`live_blocker.failed_checks` 与 `live_blocker.diagnostics` 必须直接汇总 missing gates、readiness gates 和输入产物审计摘要；`external-l3-validation.md` 必须同步展示 submit 是否允许启动、missing gates 和输入审计摘要，journey contract 必须拒绝 Markdown 与 JSON blocker 诊断不一致的报告。
- Readiness 语义：`live_run_readiness` 只表示 submit 命令启动前的 gate 结果；命令执行后的 traceability blocker 必须记录在 `submit_safety_decision.post_run_blocker_reason` 和 `live_blocker`，不得回写成 pre-run gate 失败；journey contract 必须验证 `submit_safety_decision` 中的 blocker reason 与 `live_blocker.reason` 一致。
- 输入产物证据：`external-l3-validation.json` 必须包含 `live_input_artifacts`，用 scheme/host、文件扩展名、大小与 SHA256 证明本次验证绑定到具体输入产物，同时不持久化 Job URL 原值、确认值、文件原始内容或 resume/profile 文件名；文件名字段只能写 `<redacted>` 与 `basename_persisted=false`。`external-l3-validation.md` 必须同步展示文件名与原内容未持久化结论，让人工审阅无需深挖 JSON。
- 频控证据：`external-l3-validation.json` 必须包含 `rate_limit_policy`，并把 max-per-batch、cooldown seconds、daily limit 显式传给真实 submit 命令；频控被关闭时必须在 submit 前阻断。
- 人工会话证据：`external-l3-validation.json` 必须包含 `session_readiness`、`manual_session_ready_confirmed` gate 和 `manual_session_storage_ready` gate；真实渠道命令启动前必须由用户确认共享渠道 session 已通过人工登录或刷新可用，设置 `PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true`，且 `PIPF_EXTERNAL_L3_SESSION_DIR` 指向已存在的共享 session 根目录并包含至少一个非空 Liepin 持久化会话状态标记，例如 `Local State`、`Default/Preferences`、`Default/Network/Cookies` 或 `storage-state.json`；空文件和 `.DS_Store` 等误放文件不得计为状态证据。未确认或 session 存储未准备好时必须阻断在 submit 命令启动前，自动化不得接收或持久化密码、验证码或短信码。
- 禁止输入证据：`external-l3-validation.json` 必须包含 `forbidden_input_audit`，只记录 forbidden env 是否出现，不记录原值；一旦提供密码、验证码、短信码或原始密钥类输入，必须在 submit 命令启动前记录 `forbidden_external_l3_sensitive_inputs` blocker。
- 目标确认预检证据：`external-l3-validation.json` 必须包含 `target_confirmation_audit`，只记录 Job URL 岗位 ID 是否可解析、确认岗位 ID 是否提供、二者是否一致、确认 recruiter 是否提供，以及 recruiter 页面匹配必须由 `target_verify` 证明的边界；不记录原始 ID 或 recruiter 原值；岗位 ID 二者不一致时必须在 submit 命令启动前记录 `target_confirmation_mismatch` blocker。
- 命令审计证据：真实渠道命令执行后，validation record 只允许保存脱敏 command 和脱敏后的 stdout/stderr 尾部，不能保存 Job URL、resume/profile 路径、确认 job id 或确认 recruiter 原值。
- 提交安全证据：`external-l3-validation.json` 必须包含 `submit_safety_decision`，记录最终提交命令是否被阻断、允许待执行或已执行，并保留授权、最终确认、真实输入和禁止凭据/验证码输入的决策依据；pre-submit blocker 的 `blocking_reason` 与 post-command blocker 的 `post_run_blocker_reason` 必须分别与同一条 `live_blocker.reason` 对齐。
- 授权确认证据：`operator_handoff.authorization_packet` 必须记录必需确认声明、授权签核清单、签核待补数、证据清单、中止条件、脱敏策略和禁止输入项，且不持久化原始确认值；授权签核清单必须把外部渠道授权、最终提交确认、人工 session、真实输入产物、目标确认和禁止输入映射到 env、gate、source_path、status 与原值不落盘边界；`operator_handoff.authorization_packet.pending_acknowledgement_count=0` 是模板发布、Go/No-Go 放行和授权模板执行前置条件；确认声明、中止条件和 pre-run checklist 必须覆盖 `PIPF_EXTERNAL_L3_SESSION_DIR` 指向已存在 session 根目录且 Liepin 持久化会话目录包含非空、可识别浏览器状态标记；`operator_handoff.runbook` 必须把交接包绑定到中文真实运行 runbook 的路径、SHA256 和必需章节完整性；`operator_handoff.runtime_options` 必须记录当前 channel、session/output 目录、timeout 和 headless 配置；`operator_handoff.preflight_command_template` 必须保持 `PIPF_EXTERNAL_L3_AUTHORIZED=false` 和 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false`，用于无授权本地预检；`operator_handoff.preflight_result_expectation` 必须说明预检正常结果应为 `live_blocker_recorded` / `explicit_user_authorization_required`，且不触碰外部渠道、不完成 P0-017；`operator_handoff.preflight_review_checklist` 必须把授权模板执行前的复核项结构化到 validation 状态、blocker reason、外部提交未启动、submit 命令未允许、P0-017 未完成、输入审计脱敏、session、频控、证据清单、runbook 指纹和反馈追溯；`operator_handoff.preflight_review_result` 必须对这些复核项写出 observed 值和 pass/fail，并把真实运行输入、session 或目标确认缺口记录为 `authorization_decision_blockers`；`operator_handoff.authorization_readiness_action_plan` 必须把这些缺口转成可执行待补行动，覆盖人工 session、Job URL、resume PDF、profile YAML 和目标确认的必需证据与原值不落盘边界；`operator_handoff.authorization_intake_checklist` 必须把显式授权、最终提交确认、人工 session、session dir、Job URL、resume PDF、profile YAML、确认 job id 和确认 recruiter 映射到 env、占位符、gate、当前状态和原值不落盘边界；`operator_handoff.authorized_template_release_decision` 必须在待补行动清零、授权输入接收清单清零、授权签核待补数清零、预检复核允许进入授权决策、authorization packet 就绪、显式授权和最终提交确认存在前保持 `template_released_to_operator=false`、`copy_execution_allowed=false`，并列出发布阻断项与发布前必需条件；`operator_handoff.live_run_go_no_go_decision` 必须汇总 readiness、submit safety、行动计划、输入清单、授权签核计数、模板发布决策和 P0-017 完成门禁，在授权模板未发布或 submit 命令未允许前保持 `go_for_live_run=false`、`submit_command_may_start=false` 和 `copy_authorized_template_allowed=false`，且每个 no-go blocker 必须映射到处理路线、证据来源和必需证据；`operator_handoff.live_run_execution_sequence` 必须把预检、复核、No-Go 路线处理、授权行动、授权输入、授权签核、模板发布、Go/No-Go、授权模板执行和 P0-017 完成验证排成结构化顺序门禁，并把第一处阻断作为下一可执行步骤；真实渠道命令已执行但 P0-017 未完成时，状态必须是 `authorized_live_run_executed_pending_p0_verification`，并把 `next_executable_step` 指向 `verify_p0_017_completion`，避免把 post-command blocker 误读为还没执行授权模板；只有这些缺口清零时才允许进入授权决策，且在真实运行前始终保持 `authorized_template_execution_allowed=false`；`operator_handoff.command_template` 必须使用 shell-safe 的 live 输入占位符，并反映这些运行配置与当前有效频控参数；`external-l3-validation.md` 必须分开展示本地预检模板、预检预期结果、预检复核清单、预检复核结果、授权就绪行动计划、授权输入接收清单、授权确认包与签核清单、授权模板发布决策、真实运行 Go/No-Go 决策、No-Go 处理路线、真实运行执行顺序门禁和授权真实运行模板，不能把已被覆盖或已失效的默认值写成下一次真实运行模板，也不能让路径空格或 `<...>` 占位符被 shell 误解析；`operator_handoff.command_template_review` 必须记录 `copy_paste_ready=false`、占位符替换要求、显式授权要求、独立最终提交确认要求、人工会话可用确认要求、session 存储就绪确认要求、执行顺序、预检模板不启用授权/最终提交、授权模板执行前必须按预检复核清单与复核结果复核证据，避免操作者把带授权 env 的模板盲贴为真实运行命令。
- 授权确认 verifier：`external_l3_authorization_packet_recorded` 必须同时覆盖无授权 no-go 态、签核清零的授权待执行态和真实渠道命令已执行态；当 `operator_handoff.authorization_packet.status=executed` 且签核计数为 `pending_acknowledgement_count=0` / `satisfied_acknowledgement_count=6` 时，journey report 必须把确认包判为有效执行态，而不是回退为缺失。
- 证据清单：`external-l3-validation.json` 必须包含 `evidence_manifest`，统一列出 validation JSON/Markdown、关键嵌入段、中文真实运行 runbook、preflight review checklist/result、authorization packet、authorization readiness action plan、authorization intake checklist、authorized template release decision、live run Go/No-Go decision、live run execution sequence、P0-017 completion gate、live blocker 或 submission log、feedback source 的位置、必需性、存在状态和 `raw_live_inputs_persisted=false`；runbook 清单项必须与 `operator_handoff.runbook` 的路径、指纹和章节完整性一致；authorization packet 清单项必须证明签核清单、签核待补数和原值不落盘边界自洽；preflight review checklist/result、authorization readiness action plan、authorization intake checklist、authorized template release decision、live run Go/No-Go decision、live run execution sequence 与 P0-017 completion gate 清单项必须与 `operator_handoff` 的必需复核项、待补行动、env/gate 映射、签核计数、发布阻断项或发布成功态、发布前必需条件、no-go 决策或 go 决策、resolution routes、执行顺序和路线图完成证据一致；`external-l3-validation.md` 必须逐项同步展示同一清单的位置、必需性、存在状态和状态值，journey contract 必须拒绝 Markdown 与 JSON 清单不一致的报告，让人工复核无需在多个 JSON 段之间拼接证据边界。
- 结果分级：`external-l3-validation.json` 必须包含 `outcome_summary`，明确 runner `pass` 只代表证据写出与验收规则通过；必须区分 `pre_submit_blocker_recorded`、`post_command_blocker_recorded` 和 `external_validated`，并在真实外部验证成功前保持 `p0_017_complete=false`。`external-l3-validation.json` 还必须包含 `p0_017_completion_gate`，逐项列出显式授权、最终提交确认、人工 session、session 存储、真实输入、外部提交、submission log 反向链接、submission log success、反馈追溯和 `external_validated` outcome 的完成证据；任一 required evidence 未满足时，必须保持 `acceptance_pass_is_completion=false` 并列出完成阻断项。`external-l3-validation.md` 与顶层 acceptance step message 必须同步展示该分级和完成门禁，并区分 submit 命令未启动与命令后 blocker；blocker 场景中的 `outcome_summary.next_action` 必须与 `live_blocker.next_action` 一致，Markdown 中的 outcome、blocker reason、next action 和 P0-017 完成门禁必须与 JSON 一致，避免顶层摘要把“阻断被正确记录”误读为“P0-017 已完成”或给出另一个处理路径。
- 追溯证据：真实渠道命令即使返回成功，也必须解析并确认 `submission_log.yaml/json` 存在，且 submission log 路径必须位于预期 submission 输出根目录下，并写回本次 `external_l3_validation_run_id`、`external_l3_validation_path` 和匹配 validation record 的输入产物指纹；命令输出指向允许根目录外时，validation 和 Markdown 必须只记录允许根目录、路径边界结论和拒绝原因，不得读取相邻 JSON 或泄露被拒绝的原始越界路径；submission log 必须声明 `live_inputs_redacted=true` 与 `input_artifacts.job_url.raw_value_persisted=false`，其中的原始 Job URL、resume/profile 路径字段以及 `steps.detail` 内的确认岗位 ID、确认 recruiter、页面读取到的岗位 ID/招聘方等真实输入必须脱敏；External L3 模式下提交器不得捕获或引用原始浏览器截图或 HTML snapshot，SubmissionRecorder 必须在记录层忽略 screenshot 引用，validation 必须递归拒绝 submission log 中的截图/HTML snapshot 字段、嵌套诊断字段或路径片段，只能通过 `input_artifacts` 和存在性/匹配数摘要保留非内容型追溯；否则记录为 `submission_log_not_linked` blocker。只有 submission log 自身 `status=success` 时才能计为 `external_validated`；returncode 为 0 但 log status 不是 success 时必须记录业务 blocker，已知 `error` 使用精确 `external_channel_*` 归因，未知业务失败才回落到 `external_channel_submission_not_success`。
- 诊断证据：`submission_traceability` 必须记录 `checks` 与 `failed_checks`，并在 `external-l3-validation.md` 同步展示 failed checks 与逐项 checks 表；journey contract 必须拒绝 Markdown 检查表与 JSON 不一致的报告，让操作者能区分缺日志、JSON 不可解析、反向链接不匹配或输入产物指纹不匹配。
- Blocker 诊断证据：真实渠道命令执行后产生 live blocker 时，`live_blocker.failed_checks` 与 `live_blocker.diagnostics` 必须直接汇总 returncode、submission log 路径、traceability checks 和成功投递关键步骤摘要；当 submission log 可解析且 `error` 属于已知渠道业务失败时，即使命令 returncode 为 0，post-command blocker reason 也必须优先使用 `external_channel_rate_limited`、`external_channel_login_required`、`external_channel_security_redirect`、`external_channel_job_unavailable`、`external_channel_target_verify_failed`、`external_channel_submit_safety_failed`、`external_channel_send_resume_failed`、`external_channel_submission_uncertain` 或 `external_channel_runtime_failed` 等精确归因；`main_chat_click_failed:*`、`send_resume_click_failed:*`、`confirm_send_button_not_found`、`upload input not found*` 与 `phase=*` 这类真实发简历链路错误必须归入 `external_channel_send_resume_failed`。未知错误才回落到 `external_channel_command_returned_nonzero`；journey contract 验证器必须对 `batch_cooldown`、`daily_limit_exceeded` 等已知业务 error 与 blocker reason 做一致性校验，禁止只在文档中声明该要求。
- Submission log 业务摘要：当 `submission_log.json` 可解析时，validation record 必须把 status、error、mode 和已脱敏的 last step 写入 `submission_traceability.submission_log_summary`，并同步到 Markdown 报告与 post-command live blocker diagnostics；journey contract 必须拒绝缺少 mode 或 Markdown 摘要与 JSON 不一致的报告；即使原 submission log detail 触发 traceability blocker，也不得把原始 detail 复制进 validation record；如果 last step detail 包含未脱敏 target_verify 观测值或 HTML snapshot 描述，摘要必须使用脱敏占位。
- Submission log 关键步骤证据：成功投递的 `submission_log.json` 必须记录并通过 `rate_limit`、`login_check`、`target_verify`、`submit_safety`、`chat_send_resume` 和 `submit`；缺失或失败时不得把 returncode=0 信任为 L3 成功，必须转为 traceability blocker；Markdown 报告必须同步展示必需步骤、已记录步骤、缺失步骤和失败步骤，让人工复核无需深挖 JSON。
- Timeout 证据：真实渠道命令超时时，validation record 必须写出 `external_channel_command_timed_out` live blocker、timeout 秒数、脱敏 stdout/stderr tail 和下一步处理路径；Markdown 报告必须同步展示 timeout blocker 原因、超时状态和 timeout 秒数，journey contract 必须拒绝 Markdown 与 JSON 不一致的报告。
- 命令启动错误证据：真实渠道命令因浏览器、驱动、权限或本地运行时问题启动失败时，validation record 必须写出 `external_channel_command_launch_failed` live blocker，并脱敏保存错误类型/信息；Markdown 报告必须同步展示错误类型和脱敏错误信息，且不得泄露 Job URL 或本地文件路径。
- 反馈证据：`external-l3-validation.json` 必须包含 `post_submit_feedback_traceability`；成功时连接 submission log 到 feedback iteration，blocker 时连接 blocker record 到阻断处理路径；blocker 场景中的 `source_reason` 必须与 `live_blocker.reason` 一致，Markdown 报告必须同步展示与 JSON 一致的 `source_status`、`source_reason` 和下一步，避免后续反馈入口处理的是另一个原因。
- 证据：`outputs/acceptance/acceptance_external_l3/external-l3-validation.json`，以及真实渠道生成且反向链接 L3 validation 的 `outputs/submissions/liepin/*/submission_log.yaml/json`。

## Machine Contract

机器可读真源是 `acceptance/journey_implementation_matrix.yaml`。

本文件和矩阵的基本约束由 `python3 tools/check_execution_roadmap.py --root .` 与 `tests/acceptance/test_journey_implementation_matrix.py` 锁定。
