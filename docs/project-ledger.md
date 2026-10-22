# Project Ledger

Last updated: 2026-10-22

## 2026-10-22 恢复后真实发送成功：第 19 笔（睿秀 · AI 全栈）

- 触发与补记原因：附件绑定误清的问题经只读 inspect 恢复（`outputs/acceptance/attachment-binding-recovery-20261022/validation.json`，22:56）后，用户于 App 内点击「确认投递所选 PDF」；上一则条目只记录到“最终发送仍需用户手动确认”，本条目补记该笔真实发送与回执结果。
- 目标与版本：睿秀企业管理 · AI全栈开发工程师（`jl_liepin_d0d729857c77774374b8`，画像 `jp_a6ea6776`，匹配 75 / 评测 77）；使用 `qr_20261022140512348125` 生成的 `童双龙-睿秀-AI-20261022.5.PDF`（`pdf_sha256=c46bee9cf20bd6b4a92a2a8ed0bfb1e4f994a408e1089e9c010c3c2b368680f1`），平台 file_id `…/IDSZFJa0TrmpZmA-TBXjhA.PDF`、attachment_id `287c8e228dM348d9c389cae`。
- 真实发送：`ar_20261022140520046851` 于 `2026-10-22T14:58:01Z`（22:58 CST）完成；`POST https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume` HTTP 200、`flag=1`、`data={}`；`delivery_attempts` attempt `423f27982c0b4e229d06c46802d80bab` state=success，`deliveries_completed=1`、`app_verified_deliveries=1`。
- 证据链：`outputs/submissions/liepin/native-423f27982c0b4e229d06c46802d80bab/submission_log.json` status=success，9 个必需步骤全 success（rate_limit / target_verify / submit_safety / resume_attachment_binding / login_check / ai_disclosure / chat_send_resume / submit / receipt）；`native_receipt.json` status=success（sha256 `dbc414d05bef7e97333a253a039fc95b55b76807332c884c2c28f235f248c2e8`）；AI 投递声明在发送简历前由真实 `send-common-msg` 网络证据确认，未重复发送。
- 计数与后续：`delivery_attempts` 累计 **19 笔真实投递 success**；平台反馈同步仍停在 2026-10-12（18 行 / 17 匹配），需下一次只读同步更新本笔及两笔“停止招聘”。同日 23:00 另有一次引导批次 `ar_20261022150033687798`（`submit_enabled=false`），check-mode 返回 `checked_not_submitted`，未产生真实投递或平台写入。
- 边界：平台上本笔与另一份同字节附件并存（2 份，fileId 不同、size 相同），待附件维护清理；未删除平台数据、未重复发送；`.pen` 待补；P0-026 仍唯一 `next`（待面试反馈）。

## 2026-10-22 附件绑定误清、重复附件与恢复后未核验（pdf_delivery_not_pending）

- 现象（用户实测）：恢复上传完成后点自动推进报 `run.agent.pdfInteractionPacket failed with VALIDATION_ERROR: pdf_delivery_not_pending`。
- 定位：① 新版简历页附件卡片懒加载，`liepin_native_pdf_inspect.js` 在卡片渲染前抓取，`attachment_count=0` 被当成“附件已移除”并清掉 binding（实际附件仍在）。② 恢复流程按当时逻辑重新上传同一份 `.5` PDF，平台出现 2 份同名同内容附件（旧卡未消失 + 新上传）。③ 无旧 `list-attachment-resume` 回包的当前页核验路径要求“恰好 1 张卡片”，2 张即 `attachment_current_state_mismatch`，绑定无法建立。④ UI 恢复流程用 `phase` 判断是否重新 inspect，而投递阶段 `phase` 始终是 `resume_interaction_pending`，导致上传后跳过核验 → 下一步 `pdfInteractionPacket` 因绑定缺失报 `pdf_delivery_not_pending`。
- 修复：① inspect 脚本先滚动并最多等待 8s 待卡片渲染。② `verify_uploaded_attachment` 无 list 回包路径允许同字节/同名重复附件：所有观测行 fileSize/ext 一致且恰好一行对应上传 ack `filePath`；字节不同的重复仍拒绝；绑定指向唯一 fileId，发送确认框按 fileId 选中。③ `handle_pdf_interaction_packet` 拆分错误：状态不在投递中 → `pdf_delivery_not_pending`；状态在投递中但 binding 缺失/失效 → `attachment_verification_required`。④ Submissions 恢复流程改用 `upload_state==='uploaded_unverified'` 判断重新核验，自动推进前绑定缺失给可读提示，补 `pdf_delivery_not_pending` 中英文文案。
- 只读恢复与验证：用 inspect（只读）在真实页面把 binding 恢复到新上传 ack 的 fileId（`IDSZFJa0…`/`287c8e228d…`，pdf_sha=c46bee…），`attachment_bound=true`、`can_reupload_attachment=false`；平台当前有 2 条同字节附件记录（fileId 不同、size 相同）。本轮未发送简历、未删除附件、无平台写入。证据 `outputs/acceptance/attachment-binding-recovery-20261022/validation.json`。
- 测试：新增 `test_liepin_attachment_binding.py` 重复附件只绑定 ack fileId / 不同大小仍拒绝；相关 native_pdf、inspect 脚本、GUI 恢复用例通过。全量单测 **1632 项通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱既有失败），GUI **139 项通过**；`tsc --noEmit`、roadmap/v2/AIEF 门禁通过。
- 边界：真实最终发送仍需用户在「确认投递所选 PDF」点击；平台上 2 份重复附件可在附件维护中清理后按恢复流程重传一次以获得唯一附件；`.pen` 待补。

## 2026-10-22 最终发送前平台附件被移除的恢复（“投递出去了”只读核实）

- 现象：用户反馈“投递出去了”。只读核实（真实 Tauri 会话，新增 `probeChatMessages` 调试动作）显示聊天里只有打招呼语与 AI 声明，**没有简历消息**、动作区仍显示「发简历」；同时平台附件列表为空（`attachment_count=0`），队列 `ar_20261022140520046851` 的 `pdf_delivery.state=resume_interaction_pending`、`final_send_started=false`、`attachment_binding` 因附件消失而失效并已清除。结论：简历并未真正发出；此前的“已推进到确认投递”不等于已发送，附件在最终发送前从平台消失（原因本轮未确定，可能用户清理或平台侧变化）。
- 平台入口复核：附件数 0 时「附件简历」区重新出现 `data-nick=resume-add-icon`；点击后新上传弹窗为 `ant-c-modal-root`，`fileInputs=1`，dropzone 文本「点击上传或将文件拖拽至此处」——证明此前“达上限无入口”的判断成立，且新上传脚本的 addIcon/modal/fileInput 路径可定位。
- 修复：① `native_pdf._pre_send_reupload_allowed`：仅当已进入投递、`final_send_started=false`、candidate approved、`content_review.confirmed` 且无有效附件绑定时，允许重新上传**同一份已批准 PDF**；重传前清掉失效 binding，旧上传进 `pdf_upload_history`；`_public` 增加 `can_reupload_attachment` 与 `attachment_bound`；`final_send_started` 后仍拒绝重传。② Submissions 页显示“平台附件已不在，本次投递尚未发出”，提供「重新上传同一 PDF 并继续」：确认后 upload → 只读 inspect 重新核验绑定 → 成功后提示继续自动推进；不自动发简历、不解除一次性投递尝试。③ 新增只读调试动作 `probeChatMessages`（真实会话中幂等打开沟通并读取消息/简历痕迹，不发送不投递），用于今后核实“是否已发送”。
- 验证：新增 2 项后端测试（pre-send 缺附件可重传并清旧绑定、final_send_started 后仍拒绝）与 1 项 GUI 测试（恢复块显示、upload+inspect 调用、成功后隐藏并解锁自动推进）；全量单测 **1631 项通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱环境既有失败），GUI **139 项通过**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。证据 `outputs/acceptance/missing-attachment-recovery-20261022/validation.json`。
- 边界：本轮只读探测，未重新上传/未发送；真实恢复上传与后续发送需用户重启 App 后操作验收；附件消失原因未确定；`.pen` 待补。

## 2026-10-22 同岗位重复投递冲突（delivery_already_attempted）提示与一键载入已固定流程

- 现象（用户实测）：AI 声明问题修复后，用户重跑了一次 Quick Run（`qr_20261022142953080437`，22:29 生成 `.6` PDF），在 Submissions 重新「固定此 PDF 与目标岗位」时报 `[VALIDATION_ERROR] delivery_already_attempted`，无法继续。
- 定位：队列 `ar_20261022140520046851`（quick run `qr_20261022140512348125`，PDF `童双龙-睿秀-AI-20261022.5.PDF`）在 22:06 已通过 `beginPdfDelivery` 为同一 job_key 登记了 `in_flight` attempt（`423f27982c0b4e229d06c46802d80bab`，`pdf_delivery.state=communication_started`，`final_send_started=false`，未发送简历）。`_validated_generation` 的 `has_attempt(job_key)` 按设计阻止同一岗位第二笔尝试，因此用 22:29 的新 PDF 重新固定被拒绝；后端行为正确，但错误只显示原始码，用户不知道应继续已有流程。两份 PDF 质量一致（fit 75 / resume 38 / advice strengthen）。
- 修复：① `native_pdf.py` 新增只读 `_existing_attempt_hint`：优先按 attempts 表的 job_key→run_id 精确指向已占位运行（同岗位存在多个历史准备队列时不会挑错），缺失时再只读扫描 `review_queue`；把 `:quick_run_id=...|pdf=...` 附加到 `delivery_already_attempted`（prepare 与 begin_delivery 两处），不改变一次性投递门禁。② Submissions 页解析该错误：显示已固定版本与「载入已固定的投递流程」按钮，点击后按回传 `quick_run_id` 调用 `prepare` 并恢复原阶段（`communication_started`），随后可继续自动推进；载入成功后不再显示冲突提示。中英文新增插值文案。
- 验证：新增 `_existing_attempt_hint` 单测（指向已固定 quick_run_id/pdf、无同岗位队列时为空串）与 GUI 测试（冲突显示已固定 PDF/Quick Run、载入按钮按 qr_old 重新 prepare、选择更新、提示消失）。全量单测 **1628 项通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱环境既有失败），GUI **138 项通过**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。证据 `outputs/acceptance/delivery-attempt-conflict-20261022/validation.json`。
- 边界：本轮未创建/结束/发送任何投递，`in_flight` attempt 保持原状；同岗位第二笔尝试仍被禁止；当前未提供“结束未决尝试后换新 PDF”的入口（后续可按需补）。`.pen` 待补。

## 2026-10-22 AI 投递声明已真实发送却判未确认（证据位置不匹配）

- 现象（用户实测）：清理旧附件后自动推进继续进行，但中断并显示原始错误 `ai_disclosure_not_confirmed`；队列 `ar_20261022140520046851` 已到 `communication_started`、`attachment_binding` 已核验，`pdf_delivery.ai_disclosure` 为空。
- 定位：该运行的 `interaction_history[ai_disclosure]` 实际包含一次**成功的真实发送**——`POST https://api-c.liepin.com/api/com.liepin.im.c.chat.send-common-msg` HTTP 200，请求 payload 中含完整声明原文；脚本也标记 `confirmed:true/evidence:network`。但发送脚本把网络证据放在 observation **顶层 `network`**，而 `native_pdf._disclosure_observation_matches` 只读 `ai_disclosure.network`，于是证据被判缺失 → 投递在发简历前被阻断，重试两次后返回 `ai_disclosure_not_confirmed`。此前 2026-10-21 只用 dry-run/回读验证过声明，未跑过真实发送，该形状差异因此未暴露。
- 修复：① `native_pdf.py` 在 `evidence=network` 时接受 `ai_disclosure.network` **或** observation 顶层 `network`，仍要求 `http_status==200` 且请求文本包含 `AI_DISCLOSURE_TEXT`；`evidence=dom` 不变（要求 `dom_confirmed=true`），其它形状/状态仍拒绝。② `liepin_native_ai_disclosure.js` 同时把 network 镜像进 `ai_disclosure.network`，减少历史形状漂移。③ Submissions 页把 `ai_disclosure_not_confirmed` 映射为可读错误（声明未确认送达、已停止、可再次自动推进重试；已送达声明不重复发送）。
- 验证：用真实保存的失败 observation 回放 `_disclosure_observation_matches`：修复前 False、修复后 True（未重复发送、无新增平台写入）；新增 2 项后端测试（顶层 network 接受；HTTP 非 200/请求缺声明原文/无网络证据仍拒绝）与 1 项 GUI 测试（可读错误+可重试）。全量单测 **1624 项通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱环境既有失败），GUI **137 项通过**，`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。证据 `outputs/acceptance/ai-disclosure-evidence-20261022/validation.json`。
- 边界：未由本轮重复发送声明或发简历；用户重试时脚本会先检查会话内是否已有声明原文（有则不重复发，没有才补发一次）；最终发送仍由人点击确认。`.pen` 待补。

## 2026-10-22 附件简历达到平台上限：上传/清理脚本选择器修复与 UI 上限提示

- 现象（用户反馈）：重启后点击「自动推进到最终确认」，页面只显示“自动推进已停在当前阶段”，没有继续到最终确认；队列 `ar_20261022133806821566` 的 `pdf_upload.state=not_submitted`，hints 仍为“附件控件不唯一:共0个，弹窗未出现，file控件总数:0”。
- 真实 DOM 诊断（debug 文件触发器 `action=diagnose`，真实 Tauri webview/登录会话，只读）：`https://c.liepin.com/resume/edit` 的「附件简历」区存在 3 张附件卡片；`sectionHeader` 的 `sectionAction` 为空（0 子节点、0×0），而其它每个 section 的 action 区都有 `data-nick="resume-add-icon"`/编辑图标。附件卡片「...」菜单项为 重命名 / 删除 / 同步至在线简历；删除确认框为 `ant-c-modal-root`（“注意：此操作不可恢复…” + 取消/确定）。结论：**平台附件简历上限为 3 个，已达上限时上传添加入口不渲染**；此前把“找不到控件”重复当成选择器故障重试，永远无法成功。
- 修复（`ui/src-tauri/src/`）：① `liepin_native_upload.js` 先定位附件区，存在 `resume-add-icon` 时用 pointer 序列点击该入口再走文件控件/拖放；附件卡片 ≥3 且无添加入口时回传 `attachment_quota_reached`（单条结构化 hint），不再空点控件；失败 hints 补充附件区/卡片数/入口诊断。② `liepin_native_cleanup_attachments.js` 与 `liepin_native_pdf_remove.js` 适配新版 `attachmentCard--` / `ant-c-dropdown-menu-item` / `ant-c-modal-root` 选择器与 pointer 点击序列（保留旧 `.resume-card-container` / `.more-icon` 兼容），单删仍保留请求前一次性守卫、附件身份复核与确认框校验；批量清理仍只删除 App 命名规则的旧 PDF。③ 通过触发器 `action=upload run_id=ar_20261022133806821566` 在真实 App 验证：脚本在派发前识别上限并落库 `phase=not_submitted`、`upload_hints=['attachment_quota_reached']`、`can_retry_upload=true`，**无平台写入**（未派发）。
- 页面（`ui/src/pages/submissions/index.tsx`）：识别 `attachment_quota_reached` 后展示“附件简历已达上限（3 个）”与「移除旧的 App 生成附件」按钮，自动推进禁用（避免空转）；清理成功后在本地一次性解锁自动推进（后端旧 hints 不阻塞），新一次上传若仍看到上限会重新锁定。上传返回 `not_submitted` 且未抛错时，自动链显示 `pdf_upload_not_dispatched` / `attachment_quota_reached` 可读错误，不再只给通用“已停止”。中英文新增 quota/cleanup/未派发相关 i18n。
- 测试：`test_native_pdf_upload_script.py` 新增达上限回传 token 且不点击控件；新增 `test_native_attachment_cleanup_script.py`（新版 DOM 只删 App 命名规则附件、确认一次）；`test_native_pdf_remove_script.py` 全模式在新选择器下通过；`test_submissions_pdf_auto_advance_ui.py` 新增上限展示/清理解锁/自动链可读错误 3 项。全量单测 **1622 项通过、1 跳过、53 subtests**（4 项 PDF 渲染器沙箱环境既有失败，与本轮无关），GUI **136 项通过**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。
- 证据：`outputs/acceptance/attachment-quota-20261022/validation.json`（真实 DOM 结构、卡片记录、菜单/确认框字段、端到端上限识别结果、无删除/无平台写入）。
- 边界：未删除任何平台附件（删除确认框已取消）；未验证上限释放后的真实上传（需用户点击清理后执行，新入口选择器为 `data-nick=resume-add-icon`，上传弹窗内容仍待真实页面验证）；上限数字由“3 张卡片 + 入口缺失 + 其它 section 有入口”推断，未从平台文案直接读取；`.pen` 待补。

## 2026-10-22 Submissions 投递按钮死锁修复、PDF 投递自动推进与 Quick Run 真实阶段进度

- 现象（用户截图实测）：① Submissions 的 PDF 投递在「附件控件未找到」后所有按钮变灰（只剩“一键自动上传/检查已保存附件”看似可点但无法继续），用户反馈“按钮都点不动”；② Quick Run 四个阶段同时显示同一状态（全部进行中或全部结果已生成），不是逐阶段推进；③ 用户质疑投递为何要手点 8 个按钮、快速运行为何不自动按阶段推进。
- 根因一（投递死锁）：`ui/src-tauri/src/liepin_native_upload.js` 在派发上传前确定失败时 `finish('not_submitted', hints)`（如“附件控件不唯一:共0个”“弹窗未出现”），派发后才失败才 `finish('unknown')`；但 `tools/sidecar/handlers/native_pdf.py::handle_finish_upload` 把除 `uploaded` 外的一切状态都写成 `pdf_upload.state='unknown'`，丢掉确定性未派发语义；`handle_begin_upload` 又只对 `platform_client_filename_rejected` 这一种 reconciliation 放行重试，导致真实队列 `outputs/review_queue/ar_20261021185426217475.json`（raw `unknown` + observation.status=not_submitted + responses=[]）永久无法重新上传，UI 只显示 `unknown` 与禁用按钮。该行为与 DESIGN“prepared/not_submitted 可批准上传、unknown 不得重传”不一致。
- 根因二（Quick Run 假进度）：`handle_quick_start` 用 `subprocess.run` 同步执行 `tools/run_pipeline.py`，阻塞 sidecar 串行 stdin/stdout 循环，页面只能等整条管线结束；执行期间代码把四个阶段全标为进行中以避免假进度，UI 无法轮询真实阶段。
- 修复一（投递恢复，`native_pdf.py`）：新增 `_upload_dispatched`（observation.responses 中出现 POST/PUT/PATCH 即视为已派发）、`_upload_effective_state`（旧队列 raw `unknown` 但 observation 自证 `not_submitted` 且未派发时只读归一为 `not_submitted`，不改写原文件）、`_public_upload_hints`（前 10 条提示，去内嵌 URL query/fragment、遮盖 token/cookie 等键值、截断 180 字符）。`handle_finish_upload` 改为 `uploaded→uploaded_unverified`、确定未派发→`not_submitted`、其余→`unknown`；`handle_begin_upload` 仅在有效状态非 `not_submitted` 时拒绝，重试时旧原始记录进入 `pdf_upload_history`。`NativePdfPreparation` 新增 `upload_state`、`upload_attempts`、`upload_hints`、`can_retry_upload`，`phase` 使用归一后的有效状态。每日投递 `daily_delivery._needs_recovery`/`_progress_item` 复用同一归一，避免“已证明未派发”的历史队列长期触发 `daily_recovery_required`。
- 修复二（Quick Run 真实进度，`agent.py`/`server.py`）：`run.quick.start` 同步校验后启动后台 daemon 线程并立即返回 `status=RUNNING`；后台用 `Popen` 执行管线（stdout/stderr 落临时文件避免管道填满），每约 0.5s 由 `outputs/agent_runs/<run_id>/run_log.json` 的 `PIPELINE_STEP_START/SUCCESS/FAILURE`、`PIPELINE_DONE/FAILED` 事件推导 `extract/match/generate/evaluate` 四阶段 `progress`（status/started_at/finished_at/elapsed_seconds/current_stage）。新增只读 RPC `run.quick.get`；`run.quick.cancel` 写取消标记并通过线程 Event 尽量 terminate/kill（宽限后 kill）记 `stopped`；超时按 `options.timeout_seconds` 记 `TIMEOUT`；同进程一次只允许一个活跃 Quick Run（`quick_run_already_running`）；quick run JSON 读写加 `threading.RLock` 并 `os.replace` 原子替换。未改 `run_pipeline`、LLM/匹配/生成逻辑。
- 修复三（Submissions UI，`ui/src/pages/submissions/index.tsx`）：8 个并列步骤按钮收敛为「自动推进到最终确认」+ 人工「确认投递所选 PDF」。自动链在用户确认副作用后先打开/检查 App 内猎聘会话，再串行执行 upload → inspect（附件核验）→ authorizeSingle（本岗位单次授权）→ communicate（开始本次投递）→ inspectChat → prepareResume，到 `resume_interaction_pending && can_confirm_send` 停止；每步只用上一步返回 payload 判断，失败立即停止并映射可读 i18n，绝不自动最终发送。最终发送仍由人点击，点击后自动只读 `verifyNativePdfReceipt` 并刷新投递记录；发送/回执失败保留按钮与错误、不伪造成功。高级操作折叠只保留只读诊断（检查已保存附件/核验目标岗位/检查本次沟通/核验本次回执）与附件维护，删除重复写按钮；`not_submitted`/`unknown` 展示 `upload_hints`、尝试次数与可重试/禁止重传说明。新增 `data-testid=pdf-auto-advance/pdf-final-confirm/pdf-upload-hints`；中英文各新增 `pages.submissions.nativePdf.*` 26 个 key（含 7 个业务错误码可读映射）。
- 修复四（Quick Run UI，`ui/src/pages/quick-run/index.tsx` + `lib/quick-run-tracker.ts` + `state/task-store.ts`）：start 后 1s 轮询 `run.quick.get`，四阶段卡片只按 `progress.stages` 显示 waiting/running/done/error/skipped 与阶段耗时；轮询不绑定页面生命周期（切页后仍更新全局任务 store，完成时收尾并通知，回到页面按岗位一致读回结果）；新增 `QuickRunStageProgress/QuickRunProgress` 类型、`getQuickRun`、任务 store 的 `runId/progress/attachRunId/setProgress`；执行中提示改为异步轮询说明。
- 测试：新增/重写约 30+ 项——`test_agent_handler.py`（14 项：进度纯函数 7、start 立即 RUNNING、get NOT_FOUND、并发拒绝、同步校验先抛错、cancel→stopped、timeout→TIMEOUT、运行中 run_log 推进）、`test_server.py`（start→get 轮询 DONE、get NOT_FOUND）、`test_native_pdf_flow.py`（6 项：确定性 not_submitted 可重试/history、unknown 仍拒绝、旧队列只读归一、含 POST 保持 unknown、uploaded 语义、hints 脱敏）、`test_daily_delivery.py`（1 项恢复归一）、`test_quick_run_progress_ui.py`（3 项 tracker/阶段状态/页面渲染）、`test_submissions_pdf_auto_advance_ui.py`（9 项自动链顺序/最终确认/失败停止/会话自检/hints）、`test_native_liepin_session_ui.py` 按新流程重写主链路。全量单测 **1617 项通过、1 跳过、53 subtests**；4 项失败均为沙箱内 PDF 渲染器无法启动的既有环境问题（`PDF_RENDER_FAILED: 渲染器未产生完整 PDF`，不涉及本轮逻辑）；GUI **131 项通过**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 三门禁通过；Quick Run acceptance 场景 1 通过 1 跳过（`.venv` 缺 PyYAML 的既有跳过）。
- 真实数据只读验证：对用户卡住的真实队列 `ar_20261021185426217475` 调用 `_public()`（文件 sha256 前后一致、未写平台）：`phase=not_submitted`、`upload_state=not_submitted`、`can_retry_upload=true`、`upload_attempts=1`、`upload_hints=['附件控件不唯一:共0个，候选:','弹窗:未出现，file控件总数:0']`。即重启 App 后该运行不再永久锁死，可预览+勾选后重新自动推进。证据：`outputs/acceptance/quickrun-progress-pdf-auto-20261022/validation.json`（含队列 sha256 前后一致、归一字段、测试/门禁结果与边界，无平台写入）。
- 边界与风险：① 未做真实 Tauri 窗口端到端点击验收（本机 App 已停止、真实猎聘会话需要用户侧操作）；自动链一次串行 6 个 Host Command，真实 webview 等待可能持续 10–30s，需用户实测。② 新版猎聘附件控件选择器仍是已知外部阻塞：本次修复保证“明确未派发”可重试并显示原因，不保证上传脚本一定能找到新版控件；若重试再次返回相同 hints，可用“诊断附件入口”提供 DOM 证据后另开修复。③ 真正 `unknown`（已派发但结果不明/超时）按设计仍禁止重传。④ sidecar 重启后残留的 RUNNING quick run JSON 不会自动恢复后台线程（get 会显示 RUNNING）；cancel/timeout 只 terminate 直接子进程，管线孙进程可能继续跑完（无平台写入）。⑤ `.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`（待面试反馈）。

## 2026-10-22 Quick Run 匹配阶段 HTTP 502 有限重试（Strata App Host 300s 超时）

- 现象：用户重跑 Quick Run `qr_20261021182815881138`（02:28–02:43，job `jp_a6ea6776`，51 卡），matching-scoring 失败 `语义评审失败：HTTPError`，未生成简历。
- 定位：Strata App Host 的 `server/native-gateway.mjs` 用 Node fetch 把 `/v1/chat/completions` 转发到本机引擎；fetch 默认 300s 超时，超时抛错后 host 返回 HTTP 502。`/api/serving` 记录本应用请求两次 `state=error / durationMs=300731、300688 / error=fetch failed`；同一时间段 `req/0.7.3` 客户端在统一后台连续生成长文（`tokensOut=24274、17916、24029`，单请求 266–349s），本应用请求排队超过 300s 即被 host 视为超时。
- 修复：`tools/infra/llm/client.py` 对 POST/GET 的瞬时 `502/503/504` 做有界重试（2s、5s，最多 3 次）；4xx 不重试，其他 provider 行为不变。`tools/run_matching_scoring.py` 对 `HTTPError` 输出含状态码的可行动文案（「推理后台暂时不可用（HTTP 502 Bad Gateway），已做有限重试仍失败；请稍后重试或减少同时运行的推理任务」），不再只显示 `HTTPError`。
- 测试：`tests/unit/infra/test_llm_client.py` 新增 4 项（502 重试后成功、GET 重试、4xx 不重试、有界重试次数）；`tests/unit/matching/test_run_matching_scoring.py` 新增 1 项（HTTPError 输出含状态与重试提示）。全量 **1700 项通过、1 跳过、53 subtests**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。
- 证据与边界：`outputs/acceptance/strata-502-retry-20261022/`（`validation.json` 记录 serving 错误/并发占用、host 300s 机制与修复；`capture.py` 只读抓取 serving 记录）。有限重试可缓解单次 300s 超时，但不能消除其他重型推理任务长期占满统一后台的根因；建议 Quick Run 期间避免同时跑 novel-studio/openclaw 等重推理任务，或在 Strata App 调大并行度。完整 Quick Run 待用户重跑验证；P0-026 仍唯一 `next`。

## 2026-10-22 Quick Run 语义评审兼容本地模型 map 形输出

- 现象：用户把本机配置切到 Strata App 统一后台（`provider=strata`、`model=iq3_s`、`base_url=http://127.0.0.1:47831/v1`）后运行 Quick Run `qr_20261021180502735753`（job `jp_a6ea6776`，51 张证据卡，`use_llm+require_llm`），matching-scoring 以 `semantic_invalid_response` FAILED，未生成简历。
- 定位：用同一输入与真实 `iq3_s` 复跑并记录模型原始回复。direction 与 recall 首批通过；某个 recall 批次的第二次（修复）回合把“每卡一行”输出成以卡 id 为键的对象（`{"ec_x":{"score":...}}`），`tools/engines/matching/semantic_review.py::_rows` 只接受顶层 `{"cards":[...]}`（assess 同理 `{"assessments":[...]}`），于是再次抛 `semantic_invalid_response`。
- 修复：`_rows` 在顶层对象恰好以全部期望 id 为键且值均为对象时，等价归一为行数组，再走原有逐项校验（id 覆盖/分数/引用/理由），缺 id、重复 id、未知 id、非对象值仍拒绝；`tools/infra/semantic_matching.py` 的修复提示明确要求顶层保持数组结构、不得改成 id 键对象、不得遗漏/重复输入 id。未放宽任何语义判定与引用校验。
- 测试：`tests/unit/matching/test_semantic_review.py` 新增 3 项（map 形 cards 归一、map 形 assessments 归一、异常对象结构仍拒绝）。全量 **1695 项通过、1 跳过、53 subtests**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。
- 真实复跑（证据 `outputs/acceptance/semantic-map-normalization-20261022/`）：同一 51 卡/岗位画像/`iq3_s @ 47831`，`run_semantic_matching` 完整 SUCCESS（`model_calls=7`、`cache_hits=10`、`batches=13`、`repair_calls=1`、`elapsed_seconds=153.8`）。首次复跑 recall 全部通过后遇到一次 Strata App Host `HTTP 502`（外部瞬时错误，未新增通用重试）；第二次使用已校验缓存复跑 assessments 成功。
- 边界：只修复 local 模型输出结构兼容与修复提示，不改语义标准/证据引用规则、不改 Quick Run 流程；用户需在 App 内重跑 Quick Run 继续验证 generation/evaluation 阶段；P0-026 仍唯一 `next`。

## 2026-10-22 Strata App 统一推理后台（方案修正，独立任务）

- 用户指令与定位：作者要求「修改方案 只一套由 Strata App 管理的推理后台统一连接 `http://127.0.0.1:47831/v1`」。2026-10-21 接入的是直接启动的 strata-engine（8081 / `qwen3.8-flash-next-q2_0`）；现在由 Strata App 统一管理模型加载与推理服务，在其 Host 上暴露唯一 OpenAI 兼容入口（本机 0.2.1 多次启动日志均为 47831）。本轮只改 PiProofForge 的推理后台连接口径，不新增 RPC/SDK/客户端，不改变 P0-026 与平台写入。
- 后端：`tools/infra/llm/client.py` 新增 `STRATA_UNIFIED_BASE_URL="http://127.0.0.1:47831/v1"`；`LLMClient` 在 provider=strata 且 base_url 为空时回退该入口（不落 OpenAI 默认地址）。`tools/sidecar/handlers/settings.py`：默认 provider 从 openai 改为 strata（`_DEFAULT_LLM_PROVIDER`），`_load_llm_config` 对 strata 恒返回统一 base_url、默认 model 为空；`_save_llm_config` 忽略页面/旧配置里的 strata 其他地址并归一为统一入口，切换 provider 且未显式给 model 时清除旧 provider 的 model；`checkLlmConnection` 对 strata 强制统一地址，`/v1/models` 为空返回 `BLOCKED_LOCAL_PROVIDER` 并提示先在 Strata App 加载模型；`_provider_label("strata")="Strata App"`。`tools/extract_evidence_llm.py` 对 strata 缺 base_url 回退统一入口，并把 provider 显式传给 LLMClient（`reasoning_effort` 在 CLI 路径同样生效）。
- 页面：`ui/src/lib/llmConfig.ts` 导出 `STRATA_UNIFIED_BASE_URL`；系统设置 Strata 预设 base_url 改用该常量、model 默认空，`toLlmForm(null)` 默认 provider=strata；Strata 的 Base URL 与 Model 输入只读，新增 `strataBaseUrlHint` / `strataModelManagedHint` 中英文提示，provider 卡 hint 改为「统一推理 · 47831」；其他 provider 预设/行为不变，切换 provider 仍清空检测结果。
- 测试：`tests/unit/sidecar/test_settings_handler.py` 更新并新增 7 项（默认 provider=strata/统一 base_url/保存归一/检查强制统一地址/空模型提示/切换清旧 model/base_url/active=deepseek 查 strata 不复用生效密钥）；`tests/unit/infra/test_llm_client.py` 新增 6 项（缺省地址回退 + `default_base_url` 按 provider 选择）；`tests/unit/test_extract_evidence_llm.py` 改为 strata 回退统一入口 + 非 strata keyless 仍阻断；`tests/unit/gui/test_system_settings_page_contract.py` 更新契约、只读字段、跨语言统一地址一致性，`test_llm_config_helper_ui.py` 更新常量断言。全量 **1692 项通过、1 跳过、53 subtests**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 三门禁通过。独立只读审查 approve（无阻断）；其非阻断建议已采纳：手工 CLI/管线缺省地址按 provider 选择、切 provider 同时清旧 base_url、跨语言地址一致性契约测试、文档历史口径注记。
- 真实页面验收（`outputs/acceptance/strata-unified-20261022/`，Chromium + 只读桥接 + 临时 policy/凭据，非 Tauri 窗口）：18 项检查字段（13 项硬断言）全部 PASS——新配置默认选中 Strata，Base URL 为 `http://127.0.0.1:47831/v1` 且只读、Model 只读且为空；切 DeepSeek 再切回 Strata 端点复位且旧 model 清空；点「检查连接」真实请求 47831 返回 `Strata App unified backend is reachable ... · 1 个模型` 并自动选中 App 当前加载模型 `iq3_s`；保存后临时 policy 为 `llm_provider: "strata"`、`llm_model: "iq3_s"`、`llm_base_url: "http://127.0.0.1:47831/v1"`；页面无 JS 错误，截图与 `page_validation.json` 同目录。另用真实 `LLMClient`（同一临时配置）向 47831 发起一次最小 `json_object` 请求：`/v1/models` 返回 `["iq3_s"]`，请求返回 `{"ok":true}`、response model `iq3_s`（真实 1 次本地模型调用，不计入自动化）。
- 边界：未改写本机 `policy.local.yaml`（生效 provider 仍为 DeepSeek）与用户凭据，不自动切换；真实 App 页面验收（App 加载模型 → 选 Strata → 检查连接 → 选模型 → 保存 → 跑一次任务）待用户执行；`.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`。

## 2026-10-22 岗位批量适配预检与推荐清单（P0-026 续）

- 背景与定位：真实投递 18 笔、平台同步 17 条（已查看 7、暂不合适 5、停止招聘 2、已投递 3、面试邀约 0、未同步 1），最近一笔投递岗位 fit 56；当前 26 个 active 画像只有 2 个有语义对位结果，其余逐个跑 Quick Run 才知是否值得投，选岗靶向成为拿面试的瓶颈。复用现有 job_profiles / matching_reports / scorecards / 已审核证据卡与 `delivery_advice`，不新增模型调用、不改生成/提交门禁。
- 预检引擎（新 `tools/engines/matching/fit_precheck.py`）：assessed 仅在 scorecard 具备四层 `quality_report.tiers.fit` 时可信，投递建议优先映射（apply→recommended、strengthen→consider、reconsider→caution、fix_facts→hold），无建议时按 fit 通过/语义适配分（<45 low、≥70 且缺口≤2 consider、其余 caution）与缺口数映射；旧评分卡没有四层报告时退回规则预检，不把历史 score_total 冒充对位失败。规则预检只读 `saved_eligible` 且 `candidate_pool_eligible != false` 的证据卡（51 张），按 keywords/must_have/nice_to_have 与证据文本匹配：英文完整词边界（`JavaScript` 不命中 `Java`）、中文二字窗口、通用词过滤；年限/学历/学位类不可验证要求不进入分母；输出 coverage、命中要求数、evidence_hits、matched/missing terms、basis。状态与 rank：recommended(0)>consider(1)>promising(2)>caution(3)>hold(4)>unknown(5)>low(6)；覆盖 ≥0.65 且命中≥1 → promising、≥0.35 → caution、否则 low；缺要求或缺证据 → unknown。纯函数、无模型调用、不写卡。
- RPC/页面：`jobs.listProfiles.items[]` 增加 `fit_precheck`（source/state/rank/coverage/matched_requirements/total_requirements/evidence_hits/matched_terms/missing_terms/fit_state/fit_failures/match_score/fit_score/basis），排序白名单增加 `fit_precheck`。Jobs 页新增「投递建议」清单（仅 active 画像、排除 low/unknown/hold，rank 前 3，点击选中）、画像卡徽标、详情预检依据与命中/未命中要求；新增「推荐优先/最近更新」客户端排序（默认推荐优先），首屏按 `fit_precheck` 取 100 个画像避免漏掉更匹配的老画像；Quick Run 目标下拉/提示对 `source=rule` 显示规则预检结论与命中数（assessed 保持原提示、insufficient 回退“未预检”）。中英文 i18n、DESIGN、RPC 契约与 core spec 同步；i18n 恢复原格式后每个 catalog 仅 +26 行。
- 测试：新增 `tests/unit/matching/test_fit_precheck.py` 20 项（assessed 优先/advice 覆盖/四层-无语义分退回规则/失败数单调/fit_score 低分与 legacy 回退/规则阈值/完整词边界/年限学历剔除/通用中文词/不足与排序）；`tests/unit/sidecar/test_jobs_handler.py` 新增 6 项（assessed 含建议、规则预检只用 eligible 卡、fit_precheck 排序且默认升序、旧评分卡回退、四层-无语义分不可信）；新增 `tests/unit/gui/test_fit_precheck_ui.py` 3 项（7 state 徽标、推荐清单排序/排除/点击/空态、详情命中/未命中/limitation、types/i18n/页面接线；含既有 JobsPage 测试的新组件 stub 1 行）。全量 **1677 项通过、1 跳过、48 subtests**；`tsc --noEmit`、`pnpm --dir ui build`、roadmap/v2/AIEF 三门禁通过。
- 真实数据与页面验收：`outputs/acceptance/fit-precheck-20261022/replay.py` 以真实工作区调用 handler（0 模型调用）：26 个 active 画像排序为 得物 Java `consider`、Senior Software Architect/Full-Stack Tech Lead `promising`（覆盖 72%/76%）、高级全栈/Backend Tech Lead/Tech Lead JAVA+AI `caution`、其余 20 个（含全部模拟 IC 画像）`low`；`page_validation.json` 与截图 `jobs-precheck-ranking.png`、`jobs-page.png` 来自只读桥接 + 真实工作区 + Playwright Chromium 的 Jobs 页：推荐清单依次渲染 得物 Java/补强后投递、Senior Software Architect/初步匹配 72% 命中 8/11、Full-Stack Tech Lead/初步匹配 76% 命中 11/12，页面无错误；断言切换「最近更新」后网格顺序变化、点击推荐项后画像详情联动、推荐区背景取到主题面板色（Tailwind 样式生效）。
- 独立审查：审出的阻断 B1（四层报告缺语义 fit_score/投递建议时仍被当作可信 assessed，且引擎回退用匹配总分冒充语义分、无分时失败数越多反而排得越前）已修复：`fit_score` 只取 `semantic_review.fit_score`，无分且无建议的四层报告退回规则预检，缺口语义分时不再使用 assessed；补四层-无语义分、legacy scorecard、失败数单调等回归；复审又发现残留边界（语义 fit_score=0 被当成缺失后错误退回规则预检），已修为 0–100 均视为显式分、空 advice 不算可信，并补 engine/handler 的 fit_score=0 回归与 Quick Run untrusted failed 的规则预检提示。非阻断项一并处理：`fit_precheck` 未显式 order 时默认 rank 升序、未覆盖要求计数改用 total-matched（不再被 8 项截断误导）、文案改为「未覆盖要求」、证据卡 glob 放宽为 `*.yaml`、页面验收补 Tailwind 样式与网格/详情联动断言。性能上语料缓存只覆盖解析（规则匹配约 300ms/26 画像），画像规模增长时按画像+语料指纹缓存属后续 backlog。
- 边界：规则预检是启发式参考，不替代语义对位评审、不自动跑 Quick Run、不写卡不写平台、不改变 `auto_pass` 与投递门禁；本次页面验收为 Chromium 只读桥接（非真实 Tauri 窗口，Tailwind 已生效）；复跑命令：`(.venv/bin/python outputs/acceptance/fit-precheck-20261022/rpc_bridge.py . 1451 &)` + `(cd ui && ./node_modules/.bin/vite --config ../outputs/acceptance/fit-precheck-20261022/vite.browser.config.mjs &)` + `.venv/bin/python outputs/acceptance/fit-precheck-20261022/drive.py outputs/acceptance/fit-precheck-20261022`（Playwright 在 `.venv`），真实 App 窗口与 `.pen` 画布待补（本机无 Pencil）。P0-026 仍唯一 `next`，待真实面试反馈。

## 2026-10-22 质量报告→投递建议与对位缺口类型（P0-026 续）

- 方向与复用：承接 2026-10-21 用户方向「产品目标改为帮助候选人拿到面试/录用；判项区分证据缺失 vs 未表达；报告改为投递建议」。复用现有四层评估器 `tools/engines/evaluation/tiered_evaluator.py`、`quality_report`、Markdown 评估报告与 `ui/src/components/quality-report.tsx`；未新增评分框架、模型调用或新 RPC，`auto_pass` 口径与审批门禁不变。
- 数据与模型：`QualityFailure` 增加可选 `gap_kind`（`evidence_missing` 证据池非 supported，含 partial/insufficient/conflict/未知；`not_expressed` 证据池 supported 但正文未表达或未进首屏），仅对位 R2.2/R2.3 使用；R2.4 内容取舍不带该字段，旧报告不出现该键。对位矩阵行增加 `evidence_support`（来自语义评审 requirement `status`）。R2.2 中 supported 但不在首屏的 reason 改为明确的位置缺口措辞；R2.3 支持率只由 supported 决定，缺口计数只统计非 supported 行；证据缺口与未表达同时存在时输出两条 R2.3 failure（各带 gap_kind 与各自计数）。
- 投递建议：`quality_report.delivery_advice = {recommendation, label, advisory_only, gap_counts, summary, reasons[], next_actions[]}`。规则（确定性、无模型）：合格层事实/硬性条件缺口（R1.1/R1.2/R1.7）→`fix_facts`；对位前三条职责 ≥2 项证据缺口→`reconsider`；其余对位缺口或合格层非事实缺口→`strengthen`；合格+对位通过→`apply`（优质/突出失败只写入可选改进依据）。合格层 metrics 增加 `pdf_check_state`；PDF 页数/裁切未回填时按“未校验”提示，只把 target=pdf 的 R1.5 排除在缺口外，首屏摘要/核心经历等已可判缺口必须保留；apply 的 summary/reasons 写明“除未校验项外”。`apply_pdf_check` 回填后只替换 target=pdf 的 R1.5，保留首屏 R1.5 并重算建议；四层结构不完整的稀疏/旧报告不新增或重算建议。建议不改变 `auto_pass`、不拦截投递、不替代用户最终决定。
- 报告与页面：`run_evaluation._quality_markdown` 在四层报告前输出「## 投递建议」（结论、摘要、依据、下一步），对位缺口后标注「（证据缺口）/（未表达）」；`quality-report.tsx` 顶部新增建议区（结论、仅供参考说明、依据、下一步、前三条职责口径的证据缺口/未表达计数），逐项 failure 显示缺口类型徽标，无 `delivery_advice` 的旧报告不渲染；`types.ts` 增加 `QualityDeliveryAdvice`/`gap_kind`；中英文 i18n 与 `ui/design/DESIGN.md`、`ui/design/contracts/sidecar-rpc.md` 同步；spec `openspec/changes/resume-quality-standard-and-evidence-inference/specs/resume-quality/spec.md` 增量记录「投递建议与缺口类型」。
- 验证：新增 17 项后端测试（15 项先红后绿、2 项旧行为护栏）并扩展既有 GUI/CLI 测试断言；全量 **1648 项通过、1 跳过、48 subtests**；`npx tsc --noEmit`、`pnpm --dir ui build` 通过。真实数据回放 `outputs/acceptance/quality-advice-20261022/replay.py`：用生产 `build_quality_report` + 本机判项缓存回放两个真实 run，判定 **0 次模型调用**（`judge_meta.cache=hit`，`model_calls` 取自实际 meta）——最近真实投递岗位「某上海专业技术服务公司 · 高级全栈工程师」(`qr_20261021133955495233`) 建议 `reconsider`，3 项 R2.2 核心职责证据缺口；Fit A「得物App · Java技术专家」(`qr_20261021090649699513`) 建议 `strengthen`，1 项 R2.2 证据缺口 + 1 项内容取舍。同一回放报告经真实组件 + 真实 `zh.json` 渲染（`render_report.py`，按渲染结果实际统计）得到建议结论、依据、下一步与 5/1 个缺口徽标（R2.3 双 failure 使最近岗位为 5 个）。证据：`outputs/acceptance/quality-advice-20261022/{validation.json,render_validation.json,*.scorecard.md,*.quality_report.json}`。
- 独立审查：先审发现 1 项阻断 B1（PDF 未渲染时把全部 R1.5 当“未校验”排除，会隐藏首屏摘要/核心经历缺口并给出 apply）与 R2.3 计数口径（N1）等问题，均已修复：B1 改为结构化 `pdf_check_state` 且只排除 target=pdf 项、回填保留首屏 R1.5；N1 改为只统计非 supported 行并拆分两类 failure；另修复 apply 文案在未校验时超出证据、稀疏报告兜底、R1.5 动作误映射、i18n 计数口径。复审通过：B1/N1/N2/N3/N5/N6/N7 均闭合、无新增阻断；复审提出的稀疏回归约束力（改为 strengthen fixture）与 spec `reconsider` 分支措辞已同轮修正。
- 边界：未在真实 App 内重新跑 Quick Run，故未做页面级场景验收（真实页面验收需下一次 App 内生成后查看建议区，如实标注）；未改 `auto_pass`、质量门禁、生成/匹配/投递逻辑，未触碰平台、事实、职业档案或授权；`.pen` 待补（本机无 Pencil 工具）。P0-026 仍唯一 `next`，待面试反馈。

## 2026-10-21 总览最近活动可读化

- 问题与定位：用户反馈 Overview「最近活动」显示无法理解的编号（生成简历事件直接展示文件名 `resume_mr-qr_20261021133955495233_B.md`）。定位 `tools/sidecar/handlers/overview.py::_list_recent_activity` 把 `path.name` 与英文状态句当作 `description`，违反 `ui/design/contracts/sidecar-rpc.md` 6.26 中 description 应为人类可读文案的约定；`ui/src/pages/overview/index.tsx` 原样渲染。
- 复用与实现：复用生成简历文件名约定 `resume_<matching_report_id>_<variant>.md`、`matching_reports/*.yaml` 的 `job_profile_id`、`job_profiles/*.yaml` 的 `target_role/company`，以及 submission_log `input_artifacts.company/position`（与 `submission._submission_item` 同源）。`ActivityItem` 增加可选 `target_role/company/variant/platform/status/title`；`description` 保留人类可读回退且不含运行编号/文件名。GUI 新增 `activityDescription()`：优先用结构化字段 + 既有 `codes.platform.*` 与 `pages.submissions.status.*` 文案本地化；证据事件显示标题；缺字段回退 description。补充 `check_mode_success_submit_skipped` 状态文案，新增 `data-testid="overview-activity"` 便于页面验收。契约 6.26 同步字段与“description 不得包含运行编号/文件名”规则。
- 验证：新增 `tests/unit/sidecar/test_overview_handler.py` 6 项活动流用例（简历目标/版本、无匹配报告时回退不含文件名、投递岗位/平台/状态、非成功投递回退不宣称已投递、非 A/B 后缀不当版本、证据标题）与 `tests/unit/gui/test_overview_activity_ui.py`（读取真实 `zh.json`，断言不出现运行编号/文件名并出现岗位/公司/版本/平台/状态）。全量 **1631 项通过、1 跳过、48 subtests**；`tsc --noEmit`、`pnpm --dir ui build` 通过。真实数据页面验收（只读桥接 + Playwright Chromium，非 Tauri WebView）：Overview 6 条活动渲染为「高级全栈工程师 · 某上海专业技术服务公司 · A/B 版」「高级全栈工程师 · 某上海专业技术服务公司 · 猎聘 · 成功」，无页面错误；截图与驱动脚本在 `outputs/acceptance/overview-activity-20261021/`。独立审查通过（非阻断改进已采纳：非成功投递回退文案、严格版本后缀、契约回退措辞；按现有体量接受每次解析目标画像的开销）。
- 边界：未改活动排序/条数与统计口径，未改 Resumes 页版本名（同类可读性缺口，后续按需处理），未触发任何平台写入；已重启桌面 App 并用真实 Tauri 窗口截图确认新文案（`tauri-app-activity.png`）；本轮新增文案/类型随共享工作区的并行提交 `340433a` 一并落库，其余改动单独提交。

## 2026-10-21 投递 AI 自动化声明开关（策略配置）

- 需求：用户要求新增一个动作——每次投递都让招聘方看到“本次投递所使用简历和投递行为为 AI 自动执行”的信息；做成系统开关，开启后每次投递自动附带，文案由产品确定（不强制原句）。
- 文案与存储：固定声明「您好，本次投递所使用的简历和投递操作均由 AI 自动化执行；如对简历内容有疑问，欢迎直接与我沟通。」（`tools/infra/ai_disclosure.py`，附 SHA256）；开关 `ai_disclosure_enabled` 保存在本机 `policy.local.yaml`，默认关闭；`settings.get` 返回 `ai_disclosure {enabled,text}`，`settings.update` 新增 `ai_disclosure` section，拒绝非布尔载荷。
- 投递链：`run.agent.pdfInteractionPacket` 在开关开启且尚无有效声明记录时，对 prepare/send 返回 `requires_ai_disclosure` 而不推进投递状态；每日中断/恢复、内容与额度门禁先于声明写入。Tauri 执行独立声明步骤（`liepin_native_ai_disclosure.js`）：目标 URL 匹配 + `im-ui-chat-container` 上下文含公司/岗位，向 `textarea.ant-im-input.im-ui-textarea` 填入固定文案，点击 `.im-ui-basic-send-btn`；捕获 POST 发送证据并回读聊天 DOM，后端校验 action/context/confirmed/network 后记录 `pdf_delivery.ai_disclosure`；确认后才允许 prepare 打开「发简历」、send 点击「立即投递」。声明未确认时 Rust 返回 `ai_disclosure_not_confirmed`，不继续投递；重试时若会话已出现同一声明原文则幂等跳过，不重复发送。
- 页面：策略配置页门禁策略分组底部新增「AI 投递声明」卡（默认关闭开关、固定文案预览、边界说明）；Submissions 的 PDF 投递卡片显示声明「已发送给招聘方 / 将在发送简历前由 App 发送」与实际文案；中英文 i18n 与 `ui/design/DESIGN.md` 同步，`.pen` 待补（本机无 Pencil 工具）。发送成功后 submission_log 增加 `ai_disclosure` 步骤（在 login_check 之后、chat_send_resume 之前）。
- 真实页面预检（无平台写入）：dev 探测 `probeAiDisclosureDryRun` 在真实猎聘沟通页确认 `im-ui-chat-container` 上下文含目标公司与岗位，把 49 字声明填入 `textarea.ant-im-input.im-ui-textarea`，「发送」按钮由 disabled 变为 enabled，随后清空草稿；未点击发送、未产生投递/附件/回执写入。
- 测试：新增 `tests/unit/sidecar/test_native_pdf_ai_disclosure.py`（开关默认值、要求→记录→prepare/send 放行、确认框场景、关闭时回归）、`test_settings_handler.py` 声明开关用例、`tests/unit/gui/test_native_pdf_ai_disclosure_script.py`（成功发送/幂等/错目标/缺输入框/过期权限）、`tests/unit/gui/test_ai_disclosure_ui.py`（开关页、接线、i18n、固定文案）。全量 1631 项通过、1 跳过、48 subtests。
- 位置修正：初版入口放在系统设置；按用户预期于同日迁移到策略配置页，系统设置不再保留重复入口，行为不变。
- 边界：开关默认关闭；真实“声明+发简历”同链尚未在真实投递中执行（需要用户授权新目标），本轮只验证真实输入框可填与按钮可用；不改变既有质量/匹配/回执规则；“被接收者看到”依赖投递时招聘方会话正常接收该聊天消息。

## 2026-10-21 猎聘确认弹窗真实字段核验与真实投递回执

- 目标与授权：沿用既有官方猎聘小公司岗位「某上海专业技术服务公司 · 高级全栈工程师」（`jl_liepin_4ba2781f552c26d6cb52`，职位 URL `https://www.liepin.com/a/80594047.shtml`），run `ar_20261021134024153666`；平台附件 `童双龙-某上-全栈-20261021.8.PDF`（SHA256 `462b31be…`）file_id `…/QHotN7e3RZOJwu4UPFet9g.PDF`、attachment_id `287e8a2787M348b993290a8`，单笔授权已存在。
- 探测拆分（dev 文件触发器，只读）：`probeChatOpen` 只打开沟通抽屉并在跳转/稳定后由独立就绪探测读取页面；`probeResumeDialog` 只点击「发简历」抓确认弹窗真实字段，不选附件、不发送；另加只读 `probeSnapshot` 诊断页。真实页面：新版沟通为职位页内抽屉（URL 不变），沟通开始后入口 `a.btn-main`/`a.btn-chat` 文案为「继续聊」（不再是「聊一聊」），唯一「发简历」为 `SPAN.im-ui-action-button-title`（父级 `im-ui-action-button action-item action-resume`）；`im-ui-basic-entry` 只是「我的沟通」列表入口，不能当作活跃会话。
- 真实确认弹窗字段：`DIV.ant-im-modal-root` → `.ant-im-modal-content`；标题 `选择附件简历` + `招聘方将同时收到您的默认在线简历和附件简历`；3 个 `input.ant-im-radio-input`，value 为平台附件路径；目标附件默认 `checked=true`；主按钮 `立即投递`（`ant-im-btn ant-im-btn-round ant-im-btn-primary`，enabled）。既有 `_confirmation_matches` 的锚点（文件名 stem、默认在线简历和附件简历、file_id 单选、立即投递按钮）与真实字段完全一致，保留原规则并作为本次发送的匹配规则，未放宽。
- 生产拆分与恢复：`liepin_native_pdf_chat_open.js` 改为幂等步骤 A（支持「聊一聊/继续聊」，匿名岗位不再要求公司名，改由 URL+岗位名约束；已见「发简历」时不再点击），`continue_liepin_pdf_delivery_inner` 在 inspect/prepare 前先执行该步骤，再独立执行原有「发简历」交互脚本；send 沿用已核验确认框。`handle_pdf_interaction_packet` 在未抓到确认框时允许 prepare 重试，抓到后仍阻断重复 prepare。`liepin_native_observe.js` 补 `.header-quick-menu-username` 正向登录证据，且仅在无正向证据时才把登录容器判为等待登录（职位页不渲染 `.nav-user-item`，此前会把已登录误判 waiting_for_login）；`followup_from_trigger` 移除动作前统一导航到附件页（竞态导致 `NATIVE_SESSION_CHECK_TIMEOUT`），新增 `receipt` 触发；旧合并探测 `liepin_native_chat_probe.js` 删除。
- 真实发送与回执：prepare 记录确认框后 `can_confirm_send=true`；2026-10-21T15:17:22Z 发送动作点击「立即投递」，捕获 `POST https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume` HTTP 200，请求 `imUserType=0`、`imApp=1`、32 位 imId/oppositeImId、`attachmentId=287e8a2787M348b993290a8`，响应 `{"flag":1,"data":{}}`（15:17:27Z 采集）。15:17:33Z `run.agent.verifyPdfReceipt` 核验 `success`：`outputs/submissions/liepin/native-f61d3037e09f4a8dbdc0d15684746fa9/native_receipt.json`（sha256 `0d6a8a24…`），`submission_log` success 且 rate_limit/target_verify/submit_safety/resume_attachment_binding/login_check/chat_send_resume/submit/receipt 8 步全 success；`delivery_attempts` attempt `f61d3037e09f4a8dbdc0d15684746fa9` success、single_pdf 授权批次消耗 1；`agent_runs/ar_20261021134024153666.json` DONE、`deliveries_completed=1`、`app_verified_deliveries=1`；只读回看会话 UI 23:17 新增「这是我的简历…童先生的简历 在线简历 附件简历」记录。
- 验证：`python3 -m pytest tests/ -q` → **1609 passed、1 skipped、48 subtests**；`pnpm --dir ui build`、`cargo check --manifest-path ui/src-tauri/Cargo.toml`、`check_execution_roadmap` / `check_v2_constraints` / `check_aief_l3` 通过。
- 边界：本轮未改质量评分、匹配或 PDF 内容；平台附件仍有 3 份、未删除旧附件；发送由 App 内 dev 文件触发器驱动生产 Tauri 代码（非人工点击 App 页面），外部 CUA 点击验收仍未做；P0-026 仍唯一 `next`（首笔高匹配实投与状态回流此前已验，面试反馈待回流）。

## 2026-10-21 Strata Provider 接入（本地推理，keyless）

- 定位与复用：现有系统设置已有 `lm_studio` / `openai` / `deepseek` / `openai_compatible` 预设、按 provider 凭据、思考开关与唯一 `LLMClient`；本机 Strata 桌面应用（strata-engine）提供 OpenAI 兼容本地推理（默认 `http://127.0.0.1:8081/v1`、当前模型 `qwen3.8-flash-next-q2_0`、本地默认无鉴权、思考控制走请求顶层 `reasoning_effort`）。实际缺口是 provider 预设/文案、keyless 语义、`reasoning_effort` 适配与子进程管线 credential gate，不新增 SDK/客户端/RPC 字段。Spec 见 `openspec/changes/strata-provider-integration/`。
- 请求层：`LLMClient.build_headers()` 空 Key 不发 `Authorization`；`provider=strata` 且 payload 未显式带 `reasoning_effort` 时——`json_object` 或思考关闭 → `none`，思考开启 → low/high（`max→high`）；绝不注入 `thinking`；显式值不覆盖；其他 provider 分支不变。新增 `KEYLESS_PROVIDERS` / `provider_is_keyless` / `llm_request_available`。
- settings：`_provider_label("strata")="Strata"`；`checkLlmConnection` 对 Strata 走 keyless local（无 Key 不返回 `BLOCKED_PROVIDER_CREDENTIAL`），失败/空模型列表返回 `BLOCKED_LOCAL_PROVIDER` 且消息用 Strata；可选 Key 仍存 `llm-strata-api-key`（0600）并按 provider 隔离。
- 页面：provider 5 列卡片（LM Studio / Strata / OpenAI / DeepSeek / OpenAI Compatible）；Strata 预设与思考开关（仅 low/high，切到 Strata 时 max→high）；无 Key 显示「本地服务，无需密钥（可选）」且 placeholder 不再误示已有 Key；新增 `ui/src/lib/llmConfig.ts` 供 System Settings / Overview / Quick Run / Agent Run 共用 keyless 判定，keyless Strata 有 model 即视为已配置。i18n 中英文补齐并修正思考提示与实现一致。
- keyless 管线（独立审查第 1 轮阻断 B1）：sidecar 不注入伪造 Key，管线脚本原以 `LLM_API_KEY` 判断 LLM 可用，导致 Quick Run 默认 `use_llm+require_llm` 在 matching 阶段误判失败。修复：`run_pipeline.has_llm_env`、`run_matching_scoring`、`run_generation`、`run_evaluation`（2 处）、`extract_evidence_llm` 统一复用 `llm_request_available`；在线 provider 无 Key 仍阻断；`extract_evidence_llm` keyless 缺 base_url 时显式报错，不落 OpenAI 默认地址。
- 并发投递页提交补齐（独立 fix commit）：并行会话提交的投递页/附件改动遗漏 `pages.submissions.nativePdf.{currentLinkedRun,moreActions,selectQuickRun,selectQuickRunPlaceholder}` 四个 i18n 键、两个 GUI 测试 mock 的 `listResumes`，且列表回填会把非法 `quick_run_id` 重新注入选择值；已按页面新 UI 最小补齐（非法回填校验与页头校验一致），全量门禁恢复全绿。未触碰该会话仍未提交的 `liepin_native_upload.js` 等改动。
- 验证：TDD 红→绿覆盖请求载荷、settings keyless/可选 Key/隔离、管线 gate（pipeline/matching/generation/evaluation/extract）与 GUI helper 行为（node-vm 真实执行）。全量 **1609 项通过、1 跳过、48 subtests**；`tsc --noEmit`、`check_execution_roadmap`、`check_v2_constraints`、`check_aief_l3` 通过。两轮独立审查：第 1 轮发现 B1 并修复，第 2 轮确认 B1 解决、无阻断（非阻断项已处理）。
- 真实本机验收（`outputs/acceptance/strata-local-20261021/validation.json`，gitignored）：keyless `/models` 通过且无 Authorization；结构化 JSON 真实请求 0.8s 成功，线上载荷 `reasoning_effort=none`、无 `thinking`、请求头仅 `content-type`；settings 连接检查通过且未触碰真实 policy；keyless matching 阶段 `env -u LLM_API_KEY LLM_PROVIDER=strata ... --use-llm --require-llm` 跑通（1/1 卡、4 次模型调用、22.84s、0 纠错），产物与 stdout 已留档。
- 边界：未改变当前生效 provider（仍为 DeepSeek）、未触碰用户真实凭据/policy、无平台写入；真实 App 页面点击验收（选 Strata → 检查连接 → 保存 → 跑一次实际任务）与 `.pen` 画布同步（本机无 Pencil 工具）待用户；P0-026 仍唯一 `next`。

## 2026-10-21 新版猎聘附件上传阻塞与 App 后台自动上传

- 问题：猎聘新版简历页把 PDF 附件上传改为「附件简历右侧 + → 上传附件简历弹窗 → 拖入/选择文件」；旧自动上传脚本只查找单一 `input[type=file][accept*=pdf]`，在弹窗打开前得到 0 个控件，持续返回 `not_submitted / 附件控件不唯一:共0个`。
- 已实现（尚未成功验证）：App 内「一键自动上传」（自动开会话、检查登录、导航、上传）；后台文件触发器 `app-data/auto_upload_request.json`（action=upload/diagnose），不依赖 computer use/窗口前台；登录态等待与重试；内层滚动容器处理；新版弹窗识别与 `DataTransfer` 自动拖放；旧附件清理与附件入口诊断。提交：`f265980`、`2f288f4`、`08fe502`、`216236b`。
- 当前阻塞：后台诊断触发超时，尚未拿到新版附件区真实 DOM；自动上传仍为 0 个 PDF 控件，未出现上传弹窗；无附件绑定、无投递记录、无回执。`delivery_attempts` 仍为 **17 条**，不能算已投递。
- 下一步：修复诊断桥接超时并抓取附件区 DOM；针对新版滚动容器/+ 按钮/上传弹窗修选择器；成功上传后再走检查附件、核验岗位、沟通、确认发送、核验回执。不得自动重传 unknown 上传。
- 证据：`outputs/acceptance/d5-fit-a-20261021/`（含真实上传尝试队列、UI 截图），以及 `outputs/review_queue/ar_20261021095944642230.json` 等。

## 2026-10-21 Fit A 真实整链（得物 Java 技术专家）与求职定位校准

- 目标切换（Fit A）：原 P0-026 的「高级全栈」JD 与事实不匹配，按用户决定改跑匹配度更高的「得物App · Java技术专家（电商交易）」。补全旧画像 `jp-2026-002`（status=active、审核字段、恢复 `jd_inputs/jd-2026-002.txt` 引用并解析职责章节），未编造证据。
- DeepSeek 结构化输出修复（真实整链暴露）：
  - 方向评估 `json_object` 请求缺 "json" 字样触发 HTTP 400；提示词补齐。
  - DeepSeek thinking 在 `json_object` 下耗尽小输出预算导致空正文/无效 JSON；LLMClient 对结构化 JSON 默认关闭 thinking（显式 thinking 仍优先）。
  - 语义评审职责阶段模型只返回部分职责/自创键名；提示词固定 `assessments` 数组格式并要求逐项完整覆盖，修复 `semantic_invalid_response`。
  - `【岗位职责】/【任职要求】` 章节解析；语义评审明确“目标公司专名/产品名不是任职前提”，避免把“未在得物任职”直接判为证据不足。
- 真实运行：通过 App quick-start handler（与 Quick Run 同管线）以 51 张已审核证据、EC+ 引用材料、DeepSeek 运行，产出两页 PDF；修复前 matching 阶段曾连续失败，修复后整链 DONE。
  - 合格层通过；优质层通过（首屏量化 1.0、全文 0.6、R3.1 全部通过、无 pending）；突出层通过（2 条首屏突出点）。
  - 对位层仍失败 2 项：R2.2 首条职责「负责得物App电商业务系统核心开发」首屏 weak（候选人有同类电商业务系统核心开发证据，但证据池仅 partial，且未在得物任职）；R2.4「众安双十一投屏」项目未映射到任何 JD 条目。
  - `auto_pass=false`；本轮 3/4 层通过，不宣称整体完成。fit_score=80，resume_score=40。
- 生成修复：首屏按可配对量化成果排序（不再固定语义首卡）；无词面关联的行动/结果改为非 bullet「职责：/结果：」保留原文，不再把无结果支撑的行动伪装成 achievement bullet（避免 R3.1 假失败）。
- R2.2 口径澄清：本次语义池 d1 的理由是「有同类电商业务系统核心开发经验，但非在得物App任职」，即模型把“未在得物任职”当成降级依据，而不是“没有同类电商经验”；该 partial 会把 r2_1 的 supported 封顶为 weak。已进一步在语义评审提示词中禁止把“未在目标公司任职/不是同名产品”作为 insufficient 或降级理由，后续运行生效。
- 用户投递权：质量层只作建议与事实护栏，不拦截投递。Quick Run 的「准备投递 PDF」本来只依赖正文可追溯与 PDF，不依赖 auto_pass；本轮又显式增加 `manual_override_allowed=true`、`quality_gate_blocking=false`，前端在质量未全绿时显示「仍可继续」文案与按钮，原生 PDF 的准备/授权/发送也不以 quality_passed 为门禁；最终发送仍由用户确认。
- 真实投递链尝试（用户授权 B）：选取既有官方猎聘小公司岗位「某上海专业技术服务公司 · 高级全栈工程师」（1-49 人，未投递过），重新在真实 UI 生成 PDF 并固定；打开 App 内猎聘会话并确认为有效登录；勾选授权并点击「批准并上传此 PDF」。上传观测返回 `not_submitted`、提示「附件控件不唯一」，未建立附件绑定，也未产生投递记录（delivery_attempts 仍为 17 条，最新仍 2026-10-12）。依据设计对 unknown/未提交不得自动重传，因此**没有确认真实投递成功**；需人工核对猎聘账号附件或修复上传控件选择后另行授权。另修复上传前若会话停在猎聘首页则自动导航到 `https://c.liepin.com/resume/edit` 的缺口（Rust 构建通过）。证据：`outputs/acceptance/d5-fit-a-20261021/native-pdf-queue.json`、`ui-pdf-approval-form.png`、`ui-pdf-uploaded-state.png`。
- 真实 App UI 验收（D5）：重启开发版 App 使其落在当前桌面后，从 Quick Run 选择「得物App · Java技术专家（电商交易）」、EC+ 引用材料、51/51 证据并点击启动，真实 UI 运行 DONE（run `qr_20261021091852163762`，score 85，fit 2 项失败）。结果页显示「查看并准备此 PDF（质量未全绿，仍可继续）」与「系统不会拦截投递意图」说明；点击后进入「投递记录 → PDF 投递」，在 auto_pass=false 下「固定此 PDF 与目标岗位」按钮仍可用。截图见 `outputs/acceptance/d5-fit-a-20261021/ui-*.png`。同时修复 i18n 单/双花括号导致的 `{count}`/`{{count}}` 显示问题。
- JD 适配预检（用户问题 1）：岗位画像列表沿最新匹配报告读取对应质量评分卡，新增 `fit_state=passed|failed|unassessed` 与 `fit_failures`；Quick Run 目标下拉直接标注「（适配有缺口，N 项）」「（未预检）」，选中后显示非阻断提示。系统不隐藏、不自动推荐不匹配 JD，也不拦截继续运行/投递；此前所有 active 画像未做预检即平铺为候选，是缺口来源。
- 口径重跑：禁止“未在目标公司任职”作为降级理由后重跑同一真实整链，score_total 80→85；合格/优质/突出仍通过。R2.2 d1 仍为 partial，理由变为「有品牌电商类核心系统开发经验，但非目标公司得物App，属同类可迁移」——这是模型坚持的具体公司差距，不是缺少同类电商经验；R2.4 变为「站内消息 MongoDB 改造」未映射。Fit 仍不通过，auto_pass=false，如实保留；用户仍可继续投递。
- 求职定位（用户方向）：产品目标从“auto_pass 全绿”改为“帮助候选人拿到面试/录用”；公共模型语境新增“事实边界内的职业化加工”（重排、结果前置、可迁移能力映射；禁止新增事实/职责/技术栈/数字）。后续继续落 JD 适配预检、判项区分“证据缺失 vs 未表达”、报告改为投递建议。
- 验证：全量 **1568 passed、1 skipped、27 subtests passed**；`tsc`、`execution_roadmap` 通过。
- 证据：`outputs/acceptance/d5-fit-a-20261021/`（quick-run.json、resume.pdf 两页、matching/semantic、PDF 分页文本、validation.json）。
- 边界：本轮通过 App quick-start handler 跑真实整链，**未完成真实 App UI 点击验收**；R2.2/R2.4 真实失败；`ui/design` 无变更。

## 2026-10-21 行动-成果关联与首屏成果位置修复（P0-026 续）

- 定位与复用：沿用既有模板生成、四层评估、判项缓存与 DeepSeek provider；不新增评分框架、不放宽阈值。真实输入复用 `qr_20261020152045116470` 的匹配报告、51 卡、同一目标岗位与职业档案。
- 问题（上版结果）：优质层 14 项失败，其中 R3.2 首屏量化 0.40、全文量化 0.24；R3.1 有 12 条 bullet 缺结果段或动作段；消息平台量化成果落在第二页；行动与成果分列、无关联；工作经历职责被当作 achievements bullet 但无成果依据。
- 修复：
  - 行动-成果词面配对（`pair_actions_results`）：同卡内按中文 bigram / 英文词交集加权（通用词权重 1、专有词权重 2）配对，每卡最多 3 条 bullet、每 bullet 最多 2 条结果；只做逐条呈现，不按索引硬拼、不写因果措辞；无词面关联时回退原文分列，让缺口由评估如实暴露。配对 bullet 由 action + “：” + result 组成，claims 分别覆盖 action/result，trace 校验 11/11。
  - 首屏组织：保留语义首卡，其余卡按“可配对量化成果数”排序，站内消息卡前移到第二位，使 20 万名单往返与 P95 等关键量化成果进入第一页；PDF 样式增加 `li { break-inside: avoid }`，避免 bullet 跨页切断。
  - 工作经历：无可核验成果的职责改为非 bullet「职责：」行，不再把职责伪装成成果 bullet；项目经历与补充成果仍保留配对 bullet。
  - DeepSeek 判项完整性：结构化判项禁用 thinking（此前 thinking 会把 6000 输出预算全耗在 reasoning，正文为空）；首轮缺 section 时第二轮只请求缺失 section，不再重复整份 prompt。本轮真实 DeepSeek judge 用时 2 次调用 + 1 次补段，覆盖全部 judged_sections。
- 真实复跑（同一匹配报告 + 51 卡模板生成，不调用生成模型；DeepSeek 判项）：优质层 **passed=true**，`quant_first_screen=1.0`、`quant_total=0.625`、R3.1 全 bullet 三段通过、`llm_pending=[]`。仍如实失败：对位 4 项（R2.2×3 证据池支撑不足、R2.3 硬性要求支持率 0.20）、突出 1 项（R4.2 突出点#2 未在首屏）、合格层 R1.5（本次评估未传 PDF；另行生成两页 PDF 并验证）。
- PDF 复核：2 页；第一页包含亚玛芬性能结果、15+ 系统、站内消息 20 万名单往返与 P95 两类量化成果；第二页从「补充成果」开始；无 bullet 跨页切断。`auto_pass=false`，不把优质层达标当作整体 P0-026 完成；对位/突出差距保留在质量报告与 gap 中。
- 验证：全量 **1564 passed、1 skipped、27 subtests passed**；`tsc`、`execution_roadmap` 通过。证据：`outputs/acceptance/quality-strong-20261021/`（resume、trace、DeepSeek 判项、scorecard、PDF 分页文本、validation.json）。
- 边界：本次为报告复跑与判项验证，未在真实 App 重跑整链，也未修改职业档案/分流文件；真实 App 页面验收与 P0-026 整体完成仍需用户执行。

## 2026-10-20 DeepSeek Provider 接入（独立任务）

- 定位与复用：现有系统设置已有 `lm_studio` / `openai` / `openai_compatible` 与唯一 `LLMClient`；DeepSeek 使用 OpenAI 兼容协议，不新增 SDK。实际缺口是 provider 预设、按 provider 的密钥持久化、页面状态与 DeepSeek thinking 适配。
- 凭据：从猎聘 Token 文件抽取 `LocalCredentialFile`（0700 目录、0600 文件、原子替换、拒绝符号链接），新增 `LLMApiKeyStore` 按 `llm-<provider>-api-key` 保存；`tests/conftest.py` 将凭据根固定到临时目录，测试不触碰用户真实密钥。旧 `LLM_API_KEY` 环境变量保留回退，`lm_studio` 保留 `lm-studio` 占位。
- 后端：`settings.get.llm_config` 增加 `thinking_enabled`、`thinking_effort`、`api_key.source`、`configured_providers`；`settings.update` 支持 `thinking_enabled`、`thinking_effort`（low / high / max，默认 high）与按 provider 写入密钥；新增 `settings.clearLlmApiKey`；连接检查按 provider 命名，缺在线密钥返回 `BLOCKED_PROVIDER_CREDENTIAL`。未提供真实密钥的历史在线配置不再被误报为可用。
- 请求：`LLMClient` 仅对 `provider=deepseek` 注入 `thinking.disabled` 或 `thinking.enabled + reasoning_effort=low|high|max`；显式参数不覆盖，其他 provider 不注入。sidecar 通过 `LLM_THINKING=on/off` 与 `LLM_THINKING_EFFORT` 传给管线子进程。
- 页面：Provider 改为四张分段选择卡（LM Studio / OpenAI / DeepSeek / OpenAI Compatible），DeepSeek 自动填充 `https://api.deepseek.com` / `deepseek-flash`；密钥状态与清除入口内联在 API Key 下；DeepSeek 思考开关与 low / high / max 分段控件同排；连接状态与检查按钮收进卡片底部；删除重复的 Secret Status / Connection Tests 卡片；切换 provider 清空连接检查与模型列表，并清空未保存的密钥输入。
- 验证：相关测试与全量 `python3 -m pytest tests -q` **1560 passed、1 skipped、27 subtests passed**；`tsc --noEmit`、`check_execution_roadmap`、`check_v2_constraints`、`check_aief_l3` 通过。独立审查发现并修复：跨 provider 连接检查复用当前密钥、旧 LM Studio 占位污染在线 provider、切换 provider 未强制套用 DeepSeek 预设、连接失败仍提示成功、清除密钥后旧连接状态残留、非 LM Studio 本地端点误标、provider 未无条件校验、异常消息可能回显畸形密钥。真实 DeepSeek API 调用与真实 App 页面验收尚未执行，需用户在自己的 Key 下完成；`.pen` 画布已更新 DeepSeek 选项、密钥状态/清除、思考开关与强度选择，截图见 `outputs/pen-sync-20261021/system-settings-llm-screen.png`、`outputs/pen-sync-20261021/llm-config-compact.png` 与真实 React 渲染 `outputs/pen-sync-20261021/react-system-settings.png`（mock 数据，仅验证布局）；`.pen` 主文件已保存，新增紧凑 mockup 若需保留请在 Pencil 中 Cmd+S。
- 边界：未新增平台写入，不改变 P0-026 唯一 `next`；未实现通用空正文重试。

## 2026-10-20 对位与优质层修复（P0-026 续）

- 推进顺序：遵照用户要求先修复简历对位、优质层，再处理运行耗时。复用现有匹配、模板生成、四层评估与原生 Quick Run；未另建评分框架或降低门槛。
- 判项输入与映射：补入实际正文的摘要、教育、技能和项目上下文，用正文行号与 bullet 定位且不传头部联系方式；完整 JD 进入判项与缓存，项目相关性按正文映射判断，修复项目名称不在 JD 就被判无关的问题。有效正文引用可补齐模型遗漏的重复定位字段，缺项最多一次纠错，未完成结果不写完整缓存；正文覆盖不能超过证据池支撑程度。
- 成果表达：区分已完成的非数值成果与量化成果，完整 trace 对应的 results 原文可确认结果段，量化仍需成果原文及指标/规模单位，年份和技术版本不计入。模型多条提名按既有排序选两条，不能把候选数误当成已选数。生成将核心项目放到能力/补充成果之前，前三职责行动和已有性能改善优先保留；独立行动与成果不按索引拼接，以免制造因果关系。
- 上游取材：发现已确认的消息平台卡因缺前端/Python/AI 标签被粗筛判零分，导致完整的数据库迁移、调度恢复与本机性能结果未进入逐项评审。改为完整项目仍进入逐项评审；有正向子项引用的零分卡可回到选材，保留粗筛原分数与完整性门槛。“计算机、软件工程、数学、电子信息等相关专业”保持列举语境，不拆成五项同时必须具备。
- 真实运行：同岗位、同引用材料、全部 51 卡从原生 App 启动。`qr_20261020143210916831` 暴露质量判项新增 JSON 格式未传 provider 的 HTTP 400，已补失败回归并接通既有 LM Studio 适配器。`qr_20261020143350072914` 完成两次判项但仍缺 R2.1，原始结果保留；发现已有效引用教育正文但重复定位字段为空，随后修复该格式问题。第三轮 `qr_20261020144438147839` 完成，消息平台与运营投屏卡获得逐项引用并进入正文，全部质量判项覆盖，耗时 15 分 29 秒。
- 用户事实确认与落地：用户明确确认 ai-content-forge 已实现、能运行且持续迭代；同时明确没有 React/Next.js、PostgreSQL、企业数据隔离/文件版本/备份方面的实际项目。根据材料库作品集原句，经真实 App 的职业档案入口新增 Python + DeepSeek 内容生成项目并确认；前后逐字段比较，除新增这一条补充成果及确认元数据外，其余职业事实一致，更新前档案和确认依据已保存。补充成果复用已有新增要求覆盖排序，并扣除正文已覆盖要求，避免按存储顺序截掉新项目。
- 耗时优化：粗筛缓存仅绑定该批卡及来源、完整请求和目标岗位；修改档案不再使全部卡重算。逐项评审保留完整输入指纹，读缓存继续校验引用与总输入。旧键按相同旧输入校验迁移，真实迁移 13 批、0 模型调用；质量判项只传正文实际引用的卡，减少无关上下文。带新档案的 `qr_20261020150512826977` 实际管线 **11 分 53 秒**：匹配 6 次模型调用（含 1 次纠错）、14 次缓存，质量判项 1 次、0 纠错。此为复用粗筛的档案更新场景，不等同冷启动达标。
- 最终结果：已核验且逐字保留的已确认档案职责，不再因模型漏项被误拒；新措辞、未确认档案或不完整 trace 仍阻断。原页面同输入复跑 `qr_20261020152045116470` 完成，匹配 19 次缓存、0 模型调用，质量判项缓存命中，`llm_pending=[]`。最终两页 PDF 逐页目检无裁切重叠，Python 项目已出现，合格层通过；对位仍 4 项失败、优质仍 14 项、突出仍 2 项，`auto_pass=false`。首屏量化 40%、全文约 24%，多条行动仍缺同条可验证结果，消息平台量化成果位于第二页。不能把评测修复或缓存提速认定为简历质量全部达标。
- 验证与边界：全量 **1521 项通过、1 跳过、18 subtests 通过**，原生调试构建和项目门禁通过，独立审查发现的技术差距对比误拦已先红后绿修复。证据卡与分流指纹保持不变，职业档案仅有本次获明确确认的增补，平台写入 0。证据在 `outputs/acceptance/quality-repair-20261020/`，原始失败与中间稿保留。P0-026 仍唯一 `next`；后续需在真实差距保留的前提下，继续从原始资料组织行动与成果的明确关联及首屏选材，不能通过拼接无关成果或放宽阈值消除失败。

## 2026-10-20 职责取向修订、确认接续与真实 App 验证（P0-026 续）

- 用户修订：本人经历项目在缺少细分职责记录且无反向信息时，产品应优先主导/负责人视角。已将该取向分析整合进公共指令与推断任务，作为有出处的 L3 待确认默认归因；撤回本轮曾尝试的 L3 机械降级，不把来源等级等同责任强度。已采纳职责、行动和限定在 A/B 与 trace 中保持原义；明确参与/协助/他人负责仍保留，默认归因不扩成独立或全权承担全部成果。
- 评估接通：R1.4 对有出处且用户已确认的 L3 不因等级自动拒绝主导/负责，未确认 L3/L5 仍不能自动成为已证实责任。模型判项输入增加职责等级及确认状态，缓存包含 provenance。既有自由改写组件仅作词数检查，不能宣称覆盖所有删限定/增强表达；当前 Quick Run 使用锁定字段模板链，不经过该自由改写组件。
- 确认链路修复：同一卡逐条/批量接受多个字段时，前端接续服务端返回的新 sha，后端保留另一字段已有 provenance；每次成功立即更新剩余候选与计数，部分失败不重放已成功项，不隐式重跑模型，不拉回用户已经切换的卡。已用实际组件回调（测试环境）和后端双顺序保存回归验证，没有在用户真实卡上代点确认。
- 真实页面：起初原生工具受 Mac 锁屏阻断；用户解锁后，用现有构建流程生成调试 `.app`（读取当前工作区），通过外部原生界面自动化打开证据页、筛选售后卡并点击推断。首轮显示的职责夹带“L3 默认归因候选”格式注记，已补失败测试、约束 value 内容并清理该特定末尾注记；重启后真实页面显示干净的“主导或深度参与方案设计与核心开发”，等级与置信度单独展示，原文可见，尚未接受。截图与 AX 记录在 `outputs/acceptance/native-evidence-20261020/`。
- 整链首轮：真实 App 选择原失败岗位、相同引用材料及全部 51 张已审核证据，运行 `qr_20261020132459268029` 在 105 秒后失败。方向阶段已通过，首批 6 卡两次均正分但无引用，触发 `semantic_support_requires_citation`；未生成简历，失败记录保留。
- 匹配纠错修复：错误列出本批全部缺引用的卡/要求编号；提示明确正分或关联要求必须带原文引用，确实无依据则零分且无关联/insufficient，仍最多一次纠错、失败不缓存。新回归先红后绿，61 项匹配测试通过，独立审查无阻断。此前新职责规则全量 1491 项通过、1 跳过、18 subtests 通过。
- 整链重跑：`qr_20261020133135301708` 由同一真实页面按原输入完成，状态 `DONE`；51/51 卡评审完成（38 张正向相关），覆盖 18 个 JD 条目、46 个子项，产出 A/B 正文、trace、Scorecard 和两页 PDF。总耗时 **28 分 34 秒**，未达到原定 15 分钟；匹配阶段 24 次模型调用、1 次缓存、5 次纠错，1461.8 秒。真实页面结果截图、原始首轮失败与成功输出均保留。
- 成品核对：两页 PDF 已逐页渲染目检，无裁切、重叠或乱码；职责与责任限定保留，traceable / fact_preserving_traceability 均为 true。但首个项目的具体行动跨到第二页，首屏选材仍需改善。匹配/正文覆盖/表达为 56/36/67，合格层与突出层通过，对位层及优质层未通过，`auto_pass=false`、`llm_pending=["R2.1"]`；未完成的模型判项不直接解读为本人经验缺失，当前稿仍为待审。
- 报告状态修复：真实页面暴露 PDF 回填通过后仍残留“合格层阻断”与“PDF 未渲染”的旧缺口。已更新 PDF 回填后的依赖状态与缺口任务，界面仅对实际未通过的前置层展示阻断，并将旧“Phase B 未接入”提示改为判项未完成/覆盖不足；具体质量失败项保留。修复有组件与回填回归，以及单独的 `quality-after-pdf-check.json` 核对记录，未覆盖原始运行结果；最终提示修复未另做原生页面复验。
- 最终验证：**1494 项通过、1 跳过、18 subtests 通过**；原生调试 App 构建、路线图、v2 架构、AIEF L3 与差异检查通过，独立审查发现已修复。未安装或升级依赖。
- 边界与下一步：真实候选仍未采纳，用户卡、职业档案和分流文件指纹未变；本轮平台写入 0，本地成功投递记录仍 17。单卡候选展示、真实整链与两页 PDF 目检已完成，C8 整批确认、D5 成品质量与运行耗时目标仍未达成；下一步继续同一 P0-026，复核 R2.1 覆盖与正文首屏取舍，再处理实际质量缺口，P0-026 保持唯一 `next`。

## 2026-10-20 统一 AI 求职任务语境与上下文补齐（P0-026 续）

- 用户意图：App 读取的是用户主动配置的职业资料，AI 应结合求职用途与已有职业上下文主动分析；用户口语表达需经过产品意图分析，不能直接充当提示词。复用现有唯一 LLMClient 与提炼/推断/语义匹配/质量判项入口，不新建模型调用框架或展示分流模块。
- 公共指令：新增 `tools/prompts/context.py`，统一任务目标、资料语境、事实归属、时间类型、岗位价值与执行边界。客户端对非空对话加入 system 语境，保留原任务、输出格式、资料正文及调用方对象。省略“我”不自动否定贡献；用户收录材料也不自动证明本人独立完成；生成仍只使用任务允许的已审核事实，资料中的命令只作数据。方向、语义、推断、质量四类缓存绑定公共指令内容指纹。
- 输入与局部指令：推断优先纳入绑定材料中的工作汇总，每篇增加最多 1000 字符原文与截断标记，第一人称计数仅作辅助；加入与卡关联的已确认任职职责，不传联系方式或无关经历，纳入缓存指纹。单文档提炼允许明确角色章节和省略主语的原文明示，跨文档归属仍是待确认 L3；质量判项去掉机械第一人称门槛。审查发现 actions 未传入判项且未进缓存，先补失败回归，再有界传入行动并将完整 actions 纳入指纹，复核关闭。
- TDD/回归：先复现公共上下文缺失、非第一人称原文不可见、工作汇总遗漏、确认状态/职责变化及公共指令不失效缓存等问题，再实施。正式测试集最终 **1472 通过、1 跳过、18 subtests 通过**；首次全量有一处旧测试固定把第一条消息当 user，已改为按角色验证真实 HTTP 载荷后全量通过。路线图、v2 架构、AIEF L3 和差异检查通过，独立审查无剩余阻断；未安装依赖。
- 本机模型实测：当前配置模型运行两个人工场景，各一次调用。“个人工作记录 + 角色章节 + 省略主语的职责”正确产出职责和时间候选（13.549 秒）；“第三方系统介绍 + 接口示例日期 + 资料内诱导指令”返回 0 候选（5.887 秒）。该结果只证明本次边界样本，不宣称模型普遍可靠。
- 真实售后卡：沿现有 handler 单次推断 101.894 秒，得到 **1 条 L3 职责候选**“主导或深度参与方案设计与核心开发”，保留责任限定、置信度 0.85，引用两份工作汇总的原句；项目时间缺可靠依据，保持空。候选存入既有待确认缓存，没有调用接受/事实确认；证据卡、职业档案及分流文件前后指纹相同，平台写入 0。证据：`outputs/acceptance/task-context-20261020/validation.json`。
- 口径更正与下一步：前一轮 0 候选反映了上下文提供不足，不能认定必须由用户手填；本轮已按用户要求先改善系统分析。新增职责仍是跨文档候选，需要真实 App 核对后采纳；C8 整批和 D5 两页 PDF 验收未完成，P0-026 不提升状态。适合展示的建议仍走现有 JD 匹配/选材/质量理由，本轮没有新增自动分流决策或接通手动“不参与展示”到生成。

## 2026-10-20 证据补全检索修复与售后服务单卡实测（P0-026 续）

- 定位与复用：当前有效分流仅一张「值得补」卡。复用 `evidence.inferFields`、`kb` 索引、现有候选缓存和确认入口；预检发现 20 条检索结果遗漏了卡已绑定的速读卡，长背景/技术栈命中使优惠券、站内消息文档靠前；“系统支持”“不参与计算”被误计为本人参与。未调用模型前先复现这两个问题。
- 最小修复：`select_documents` 优先保留 material_id/document_id/sha256 均一致的已绑定原文，再按卡标题相关性、背景匹配排序；设计资料及夹具排除保持。参与线索要求“我/本人”主体；推断版本升至 2 使旧候选缓存失效，保留既有否决哈希。先红后绿，29 项检索、候选、RPC、provenance 与生成相关测试通过；独立审查无阻断，路线图/差异检查通过。
- 真实读取与推断：修复后前三份为售后服务的速读卡、架构切片和业务地图，20 份正文中没有明确第一人称线索。现有 handler 使用当前配置执行单卡一次真实模型调用，29.945 秒返回 `status=ok`、时间/角色候选均为 0；另核对模型正文，两个字段均为空值、零置信度、空依据，非解析失败被当作成功候选。待确认缓存已写入；证据卡、职业档案、分流文件前后 sha256 均一致。证据：`outputs/acceptance/evidence-inference-20261020/validation.json`。
- 来源复核边界：工作汇总能支持售后领域及通用 Tech Lead/主导或深度参与描述，不能将其提升为该项目本人全程负责。售后预约说明中的 2024-02/04 日期属于接口示例数据，不能用作项目期间。已请求用户补充本人具体工作及大致时间，或说明是否不参与展示；收到前保持字段为空。
- 完成口径：本轮为检索缺陷修复、真实资料回读与单卡后端推断实测，没有替代真实 App 用户确认，C8 整批与 D5 两页 PDF 验收未完成；没有修改已确认事实或执行招聘平台写操作。上一片方向评估修复 WIP 保留。

## 2026-10-20 Quick Run 方向评估空正文修复（P0-026 续）

- 定位与复用：原失败运行 `qr_20261018063317021353` 在逐卡语义评审前的 `assess_direction` 失败。核对本机模型日志，原模型 `qwen3.8-flash-next@q2_k` 的响应正文为空，`finish_reason=length`、800 个输出 token 全为推理；原方向阶段未提供一次纠错，CLI 只展示 `JSONDecodeError`。复用既有 `LLMClient`、偏好来源校验、方向评估缓存与语义统计，不新增模型框架或调整全局配置。
- 修复：该精确型号与既有 `qwen/qwen3.8-27b` 的 LM Studio JSON 对象请求默认 `reasoning_effort=none`，显式参数优先，其他模型/供应方/非 JSON 请求保持原行为。方向阶段对空正文、非法 JSON、无效结构/引用最多纠错一次；网络错误不自动重试，两次失败仍阻断，只有校验通过的结果写缓存。方向调用和纠错计入总统计，缓存复跑为零调用；CLI 显示方向阶段的空正文/非法 JSON 提示。
- TDD 与回归：先复现空正文、型号适配缺失、一次纠错/缓存/统计缺口，再补非法状态结构与 CLI 失败诊断复现；修复后受影响回归 **133 项通过、18 subtests 通过**。其中 131 项在沙盒内通过，两项 Quick Run PDF 集成测试因 `PDF_RENDER_FAILED` 在沙盒内失败，使用本机已有浏览器沙盒外原样重跑 2/2 通过。项目 `.venv` 缺 PyYAML，扩大回归改用本机已有依赖的 `python3`，未安装或升级依赖。路线图、AIEF L3 和差异检查通过，独立审查无阻断。
- 原岗位/原模型实测：使用当前配置与原失败岗位 `jp_e43441bd`，首次正文已非空且推理 token 为 0，但引用未逐字命中 JD；一次纠错后引用与方向结构校验通过。共 2 次模型调用、1 次纠错，总计 64.801 秒，随后同输入缓存命中、0 模型调用。审计记录：`outputs/acceptance/quick-run-direction-20261020/validation.json`；不保存推理正文或凭据。
- 边界与下一步：本轮是方向阶段的真实本机模型验证及受影响管线回归，不是外部自动化驱动的真实 App 整链验收；未重跑全卡匹配/最终两页 PDF，不提升 C8/D5/P0-026 状态。当前分流文件已有 1 张「值得补」卡，早期“无分流文件”的阻塞描述仅代表当时状态；真实整批推断与用户确认仍未完成。平台写入 0，未改个人事实、已确认档案、投递授权或全局模型配置。

## 2026-10-18 证据页结构重整与页头吸顶修复（设计基线落地）

- 背景：证据页经历引用材料、补全分流、待确认推断、就地摘要四片叠加后出现 12 处点击才可见内容、两处两级嵌套、三块无主次折叠；同一张卡出现两份清单与两个“查看”。按 DESIGN「折叠使用规则」与「证据页结构重整（2026-10-18，设计基线）」重排，不新增能力。
- 画布先行：Screen/Evidence 重画 1440×980（页头动作区、常驻对账汇总条、双栏列表+详情、详情「对账发现」、底部删除）；新增 State/Evidence 提炼抽屉（遮罩 + 560px 抽屉）；删除 materialReconcileFold、reconcileInferenceRow、refMaterialEntry、refMaterialItem、docPick1 等旧节点；保存 `.pen` 并截图记录（outputs/acceptance/evidence-redesign-20261018/）。全局页头透缝按设计修复：`.page-header` 移除 `top-0`、改 `top: -1.5rem`（与 `-mt-6` 等值），全部 9 页生效。
- 代码：进入证据页自动跑一次对账；汇总条计数即筛选（全部/可用/待补/未入池/不可追溯/缺时间/疑似重复/待确认推断/值得补/已分流），右端重新对账/运行推断/批量接受高置信；列表列改为标题、时间+等级、角色+等级、来源文档数、状态+问题标签（不再显示分数与行内操作）；详情面板新增「对账发现」（原因、不可追溯结果与原文候选、时间线索、疑似重复、分流、待确认推断接受/修改后接受/否决、低置信折叠），原“已绑定字段依据”折叠取消，时间/角色旁显示等级与来源文档；删除独立对账列表/就地摘要/关系提示条；「从材料提炼」改为 560px 覆盖抽屉，引用外部目录管理迁到系统设置「材料来源」（扫描/创建/检查/刷新/解除），证据页保留跳转链接。
- 空态：0 张卡且无草稿/详情时只显示空态面板；空态新建/手动整理仍渲染详情编辑区。
- 后端：`evidence.list` 补充 `time_range_level`/`role_scope_level`/`source_document_count`（无新 RPC）；`ui` 列表一次取 100 条供前端问题筛选。i18n 删除 reconcile.hint/scope/view/hidePreview 与 triage.showOut/hideOut，新增 summary/emptyState/diagnosis 等文案。
- 验证：全量回归与 `tsc` 通过；GUI 合同按新结构重写（自动对账、汇总筛选、详情对账发现/分流、抽屉流程、引用迁移），`.pen` 已保存。
- 同日实现复核修复（4 项）：① 自动对账失败会无限重试（effect 以 `!reconcile` 为条件，失败后 reconcile 仍为 null）→ 改为 `autoReconciledRef` 每次加载只自动对账一次，失败由“重新对账”手动触发；② 列表受后端 100 条上限截断而汇总条为全量 → 按 `next_cursor` 显示“仅加载前 N 张”提示（`evidence-list-truncated`，文案 `listTruncated`）；③ 空态/抽屉跳转 `/resumes?section=materials` 简历页不响应 → 材料库区块加 `id="resumes-materials"` 并在加载完成后滚入；④ 对账发现时间线索 chip 用了未定义的 `bg-bg-inset` → 改 `bg-bg-hover`。新增 `tests/unit/gui/test_evidence_reconcile_failure_ui.py` 3 项（先红后绿），GUI 93 项与 `tsc` 通过。
- 同日偏差收口（3 项）：抽屉遮罩改用新增 token `--z-drawer: 150`（侧栏 100 / 对话框 200 之间），打开时盖住侧栏；详情保存按钮改为主色“图标 + 文字”（`evidence-save`），与编辑/取消同形态；推断候选接受 / 修改后接受 / 否决改为按钮组（主色 / 描边 / 警示描边）。DESIGN 的 Layering 表按实际 token 重写（原表 z-dropdown/z-modal 50/z-tooltip 与代码不符）。`test_evidence_reconcile_failure_ui.py` 追加源码合同 1 项，GUI 94 项与 `tsc` 通过。

## 2026-10-18 证据页信息架构与对账就地查看（UX 修复，P0-026 续）

- 问题：证据页“材料来源 / 材料对账 / 证据卡列表”三层职责没有显式说明；对账列表在上、证据详情面板在下，行内“查看”只把数据加载到远处详情，长列表下用户看不到任何可见变化，误以为按钮无响应。
- 信息架构（本轮明确并写入 DESIGN）：材料来源登记可被引用/采纳的材料目录与文档（`source_material_ids`/`source_documents` 的溯源对象）→ 材料对账对现有全部卡做只读体检（结果能否逐字追溯、缺字段、疑似重复、池状态、分流与推断候选，不改卡）→ 证据卡列表/详情负责编辑字段、来源、审核与附件。数据链路：材料来源 → 提炼/生成证据卡 → 对账定位问题 → 详情修正。
- 修复：证据页标题下新增三层关系提示条（`evidence-relation-hint`）；对账行“查看”改为就地展开只读摘要（`evidence-reconcile-preview`），数据出现在点击行正下方：池/审核/入池状态、时间与角色（带 L1–L5 等级）、场景、技术栈、标签、来源文档数、附件数、行动/成果、缺失项，以及“对账发现”（不可追溯结果、原文候选与相似度、材料时间线索、建议来源、疑似重复）；摘要内“打开完整详情（编辑/来源校验）”才加载右侧详情并滚动到视口；再次点“收起”关闭。
- 验证：GUI 合同测试覆盖就地展开、诊断数据显示、仅摘要不滚动、完整详情滚入详情面板；全量回归 **1438 通过、1 跳过、18 subtests**；`tsc --noEmit` 通过。
- `.pen` 待补：本轮未强行切换用户当前编辑器中的其他项目画布，证据页“关系提示条 + 对账摘要行”尚未同步到 `ui/design/piproofforge.pen`。
- 边界：复用 `evidence.get`，无后端/RPC 变更；对账仍不改卡。

## 2026-10-18 生成按等级降级与首屏组织（Phase D1–D4，P0-026 续）

- 定位与复用：真实生成入口是 `tools/run_generation.py`（A/B 模板拼装），已在其中消费字段级 provenance；`tools/engines/generation/template_assembler.py` 与 `llm_rewriter.py` 同步补齐纯函数/受控改写能力，不新增生成框架。
- D1 等级降级：证据卡读取时携带 `time_range_provenance`/`role_scope_provenance`/等级；L1/L4 保留负责/主导；L3 动作与结果降级为参与/推动，角色行呈现“参与 / 推动 · 角色”；L5 时间卡不进入正文；年精度只呈现起始年（如 2022）。
- D2 受控改写：`LLMRewriter.rewrite` 支持 `level_context`（max_role_level/time_precision），改写后规则复核：强措辞增加或月份精度变细则回退模板原文；提示词同步约束。
- D3 首屏组织（确定性部分）：按 JD 语义引用排序证据卡（引用优先，未引用压缩为最多 4 / 最少 2 条）；首屏标记移到第一条经历之后，使 JD 前三条职责对应的 bullet 进入首屏。B4 突出点提名发生在评估阶段（生成之前无法消费），正文回填突出点需评估后二次生成，本轮明确留作后续切片，不冒充已完成。
- D4 追溯：生成 trace 的 claims 对时间/角色携带 `provenance`（等级、依据、确认记录），trace 顶层增加 `field_provenance`；评估器解析卡内 JSON provenance，R1.4 措辞上限对真实卡生效。
- 验证：新增生成 provenance/首屏/受控改写测试 5 项，更新首屏标记与定向生成回归；全量回归 **1438 通过、1 跳过、18 subtests**；`tsc --noEmit` 与 `check_execution_roadmap` 通过。
- D5 阻塞：真实 App 用目标 JD 重新生成两页 PDF 并验收需要用户操作（生成、评测、固定 PDF 与人工审核）；本轮未执行真实生成，不以合成夹具冒充验收。C8（真实 85 卡推断确认）同样等待用户先在 App 分流。
- 边界：无平台写入；P0-026 仍唯一 `next`。

## 2026-10-18 证据可信等级与跨文档推断（Phase C，P0-026 续）

- 定位与复用：沿用证据卡 YAML、对账面板、`kb` 索引、职业档案任职区间与 LLM 配置；新增 `tools/infra/evidence_provenance.py`（等级/出处结构）与 `tools/infra/evidence_inference.py`（检索/聚合/校验/缓存），不新建存储或 RAG。
- C1/C2 provenance：卡字段 `time_range`/`role_scope` 可带 `*_provenance_json`（L1–L5、precision、evidence、confidence、confirmed_by_user、first_person_hits）；缺省按 L1（有值）/L5（空值）兼容旧卡；domain/引擎 store/validator 与 sidecar 读写同步；手工改时间/角色自动降级 L4。卡文件 sha256 指纹包含 provenance。
- C3 单文档提炼：`_llm_draft_prompt` 注入文档元数据（路径/文件名日期/首个日期标题/修改时间/任职区间 keys），要求模型按 L1（原文引用）/L2（元数据键）输出时间候选、角色仅 L1；无依据或超出任职区间的候选丢弃并记录 `provenance_warnings`。
- C4 跨文档推断：新 RPC `evidence.inferFields`；kb 索引按卡标题/标签/技术栈检索（限 20 篇，排除设计资料来源与合成夹具）；日期与第一人称句聚合后每卡一次 LLM 产出 L3 候选；校验任职区间与 excerpt 可回读后才入 `app-data/evidence_inference.json`，按卡 sha256+文档集合指纹缓存，否决候选不再提名。
- C5 用户确认：新 RPC `evidence.confirmInference` 支持接受（保留 L3 + confirmed）、修改后接受（L4）、否决（记 hash 不再提名）；写卡后进入待审核且保留 provenance。对账面板新增「待确认推断」行与高/低置信分组、批量接受高置信、修改值、单条否决；证据页 `.pen` 已同步该行（Screen/Evidence 1310 高，左列重排）。
- C6 开关：系统设置「证据推断」开关持久化 `policy.local.yaml`，关闭后只返回规则 L2 时间线索、不调用模型；UI 支持切换。
- 修复（2026-10-18）：材料对账列表“查看”原本只加载右侧详情、在长列表下详情面板位于折叠区下方且不滚动，用户看到“无反应”。现点击后滚动右侧详情面板到视口顶部（`evidence-detail-panel`），并补 GUI 合同测试；设计职责仍为“进入该卡详情、只读不改卡”。
- C7 文档：`sidecar-rpc.md`、`DESIGN.md`、`ui/design/piproofforge.pen` 已同步；`tsc --noEmit` 与全量回归通过（1400+ 项）。
- C8 阻塞：真实 85 卡运行与用户批量确认需要先在真实 App 完成分流（当前无 `app-data/evidence_triage.json`）；本轮按边界保留未验收，未用合成夹具冒充真实数据结果。
- 边界：推断不写卡、不自动确认；L2/L3 措辞降级与简历 trace 等级展示留 Phase D；无平台写入；P0-026 仍唯一 `next`。

## 2026-10-18 四层质量报告 Phase B：受控 LLM 判项与突出点（P0-026 续）

- 定位与复用：在 Phase A 规则报告上接通设计中的 LLM 判项，不新建模型调用框架。判项走 `LLMClient` 与既有 OpenAI-compatible 配置（pipeline `--use-llm` + 系统设置持久化 env），结果只进入质量报告与匹配矩阵，不改生成内容。
- B1 受控通道：新增 `tools/engines/evaluation/llm_judge.py`，单次调用输出 `r1_4/r2_1/r3_1/r3_5/r4_1` 五段 JSON；每条必须带 bullet 编号或证据卡 id 引用，无引用项丢弃，整体不可解析视为无效并保留 pending；`r2_1` 必须逐条覆盖全部 JD 条目才生效。缓存落 `app-data/quality_judgments/`，键 `resume_sha256 + job_profile_id + cards_fingerprint + model + prompt_version`，只缓存通过校验的结果；`max_tokens=2500` 防止本地模型无界生成。
- B2/B3 判项：R1.4 强措辞（负责/主导/独立负责/全权负责/设计并落地）必须被判项覆盖，`supported=false` 或缺判项均记失败；R2.1 用判项回写矩阵 `status`/`bullet_ref`/`first_screen`；R3.1 逐经历 bullet 判定场景/动作/结果，缺判项或缺段失败；R3.5 判定摘要行数、角色规模匹配与通用形容词。LLM 模式下的 `llm_pending` 只保留未覆盖段，全部覆盖后清空。
- B4 突出点：R4.1 提名 0–3 条候选（规模/难度/范围/稀缺组合，等级 L1/L2），按超出维度数与用户选择排序取 top-2；用户否决/替换写 `app-data/quality_decisions.json`（按 resume sha，同一候选 reject/select 互斥，重算时排除否决项并优先已选项）。新增 sidecar RPC `quality.decideHighlight`，校验 run、resume sha、highlight id 与 action 后原子落盘。
- B5 审批展示：四层报告组件在突出层显示突出点/候选（bullet ↔ JD、超出维度、等级、理由、引用），提供「否决」「设为突出点」；Quick Run 与固定 PDF 审批接入并提示「已记录，重新评测后生效」。契约见 `sidecar-rpc.md`，GUI 合同测试覆盖渲染与页面接线。
- 验证：新增 judge 校验 4 项、缓存/决策 4 项、judged evaluator 4 项、judge 集成 4 项、决策 RPC 6 项、GUI 合同更新；全量 **1408 通过、1 跳过、18 subtests**；`tsc --noEmit` 通过。
- B6 真实 JD 回归（本机 LM Studio）：`qwen3.8-flash-next` 系列加载 SIGSEGV、配置模型 27B 首次加载超时后，使用 `qwen/qwen3.6-35b-a3b`；关闭本机 reasoning 输出（仅本机 base_url 加 `reasoning_effort=none`）、`max_tokens=6000` 避免 thinking 吃满预算。首次 miss 58.0s，判项段 `r1_4/r3_1/r3_5/r4_1`，`r2_1` 仅覆盖 16/18 个 JD 条目，按 fail-closed 保留 R2.1 pending；同输入第二次 **cache hit、0.112s**、判项段一致，即 0 模型调用。真实结果：合格 R1.5 失败、对位 R2.2/R2.3/R2.4、优质 R3.1/R3.2、突出 R4.2（2 条候选均非首屏），auto_pass=false。证据 `outputs/acceptance/resume-quality-20261018/judged/validation.json`；不宣称判项稳定，R2.1 待重试或模型升级。
- 边界：LLM 判项不稳定时保留 pending/fail-closed，不伪造通过；用户决策只影响突出点选择，不写卡、不改生成事实；P0-026 仍唯一 `next`。

## 2026-10-18 四层简历质量报告首片（Phase A，P0-026 续）

- 定位与复用：简历质量缺口的规则部分落在既有 `run_evaluation`（pipeline 实际评测入口）与 sidecar `agent.py` 审批门禁；复用 `resume_trace` claims、语义评审矩阵、职业档案与证据卡解析，不新建评测框架。新增 `tools/engines/evaluation/tiered_evaluator.py` 承受 pure 规则判项，IO 留在 `run_evaluation`。
- 标准与配置：新增 `config/quality/thresholds.yaml`（R3.2 首屏 ≥0.6 / 全文 ≥0.4、R4.2 1–2 条、PDF ≤2 页等）与 `config/quality/filler_lexicon.yaml`（中英空话词表，可编辑）；加载失败回退内置默认值，不新增运行依赖。
- 规则判项：合格层 R1.1 追溯、R1.2 档案一致性/项目时间窗、R1.3 时间缺失（含卡 id）、R1.4 措辞上限（C 前按 L1）、R1.5 页数/首屏、R1.6 内部痕迹、R1.7 硬条件、R1.8 结构；对位层 R2.2 首屏前三职责、R2.3、R2.4，矩阵增加正文呈现与首屏列；优质层 R3.2 可验证量化、R3.3 空话、R3.4 重复、R3.6 术语大小写；突出层 R4.2 数量/首屏、R4.3 等级过滤。输出 `quality_report`：四层失败项必须定位 bullet/条目/卡 id，`auto_pass = 四层通过 ∧ llm_pending 为空`；Phase A 的 7 项 LLM 判项显式列为 pending，因此 auto_pass 保持 false（不假装通过）。
- 接入：`run_evaluation` 写 `quality-v1`、`quality_report` 与 `legacy_scores`，Markdown 增加四层报告段；`agent.py` 的 `quality_passed` 改读 `auto_pass`，PDF 导出后回填 R1.5 页数并重算，`reasons` 由 failures 生成，删除「低于参考线 78」与 `evaluation_reference_score`；`native_pdf` 质量快照携带四层报告供审批页展示；UI 新增四层折叠组件（failure 指向卡时可跳证据页）、旧分对比折叠区，Quick Run 与投递审批接入。A/B 模板与 HTML 渲染支持 `<!-- first-screen-end -->` 首屏标记。
- 验证：新增 tiered evaluator 15 项、首屏标记 2 项、评测报告接入 1 项、GUI 合同 3 项；`tsc --noEmit` 通过；全量回归 **1386 通过、1 跳过、18 subtests**。`check_execution_roadmap` 通过。
- A11 只读基线（不重新生成）：最新 resume A `9c93df84…` + target JD 固定 PDF（2 页）→ 合格层通过（裁切未自动校验，记 `clip_check=not_available`）、对位失败 R2.2/R2.3/R2.4、优质失败 R3.2、突出失败 R4.2；`auto_pass=false`（7 项 LLM pending）、legacy 52/68、17 项 gap；无平台写入。证据 `outputs/acceptance/resume-quality-20261018/`。
- 边界：Phase A 仅规则部分；R1.4 只做措辞上限检测；PDF 裁切仍由原生验收确认；真实 App 页面验收与 Phase B 之后统一进行。P0-026 仍唯一 `next`。

## 2026-10-17 `.pen` 设计同步（P0-026 续）

- 范围：清空 `ui/design/DESIGN.md` 四处「`.pen` 待补」（Jobs 公司规模、Evidence 材料对账折叠区、证据卡补全分流、职业档案自动关联按钮），并补齐引用式材料在 Evidence 与 System Settings 的设计缺口；同日 `develop` 15 个提交（知识索引至分流首片）已推送 `origin/develop`。
- 画布改动：Jobs `leadFilters` 加 `leadSizeFilter` 公司规模下拉、两条线索行加 `leadRow1Size`/`leadRow2Size` 规模·融资阶段；Evidence 材料来源区加 `refMaterialEntry`/`refMaterialItem`，新增 `materialReconcileFold`（六项计数、两条问题行、`triageSelect1/2` 分流下拉、卡变化警示、`reconcileShowHidden`）；Resumes 新增 `careerEditorOps`（自动关联证据/保存草稿/确认档案与禁用提示）；System Settings 新增 `setNav3`「材料来源」与 `setMaterialSourcesCard` 引用根字段卡。Screen/Evidence 900→1240、Screen/Resumes 900→968，左列屏幕按 40 间距重排，无重叠。
- 验证：`Export` 四屏截图逐屏核对，截图存 `outputs/pen-sync-20261017/`；经 Pencil 画布 `save-document` 落盘（525,000 字节，JSON 可解析、14 个顶层画框）；设计文档与路线图同步更新。无代码、数据或平台写入。
- 边界：这是设计真源同步，不是真实 App 页面验收；`.pen` 为示意数据，不含全部分流判定逻辑；真实 App 内分流验收仍待用户操作。

## 2026-10-17 证据卡补全分流首片（P0-026 续）

- 试验（用户授权只读本机材料、仅输出计数）：55 张缺时间/职责的真实卡中，按标题相似度在人写文档找逐字区间/角色句的命中为 4/1/0（阈值 0.4/0.5/0.6）；放宽到标题子串后 23 张有候选，但 16 张有区间的卡中 10 张对应多个不同区间、可与日期线索核对的 4 张仅 1 张一致。结论：人写文档记的是公司/品牌级区间，原“逐字区间候选”一级不成立，自动匹配会把任职期当项目时间，已放弃。
- 调整：先分流再补。新增 `evidence.triage.set` 与对账列表分流下拉（值得补/不参与展示/重复），判断存于 `app-data/evidence_triage.json` 并绑定卡 sha256，卡变化即失效；不改卡、审核、档案修订或生成。被分流掉的卡不再计入缺时间/缺职责。补全仍走既有跨文档补证面板。
- 验证：后端 4 项、GUI 1 项新回归先失败后通过；全量 **1349 通过、1 跳过、18 subtests**；`tsc --noEmit` 通过。真实数据只读对账：85 卡、缺时间 60、缺职责 63、未分流 85（尚未分流）。未做真实 App 页面验收，`.pen` 待补；无平台写入。
- 页面验收（2026-10-17 补记）：`tauri build --bundles app` 重新打包成功；桌面自动化与 Chrome 扩展对本地地址不可用，改用隔离数据副本（真实 85 卡与材料拷贝）+ 只读桥接（仅放行只读方法与 `evidence.triage.set`）+ 第二个 Vite，以 Playwright Chromium 驱动真实证据页。依次标“不参与展示”“重复”“值得补”：已分流卡收起、缺时间 60→58、值得补排第一、展开可见、重载回读一致、无页面错误；副本中修改一张已分流卡后判断标为失效并重新计入。发现下拉宽度随“与 ec_x 重复”文本变化，已固定为 w-36 并复验。截图与驱动脚本在 `outputs/triage-acceptance/`；副本已删除，真实数据未写入分流。非 Tauri WebView 原生验收。
- 下一步：用户在 App 证据页对缺字段卡分流，再对“值得补”的卡用补证面板补原文；分流后缺口数作为下一片（任职期约束的时间线索）的输入。

## 2026-10-17 知识索引覆盖补齐：工作流设计引用与上游目录盘点（P0-026 续）

- 定位与复用：现有材料库与索引一致，但上游六份工作流编排/交付治理设计和实施计划未登记，Office/PDF/图片附件及主动过滤项也未进入导航；原“全量资产已纳入”超出实际检查范围。复用既有 `material.reference.scan/create`、拆档规则、kb 构建与 find/grep/read，在同一 index.json 增加来源覆盖，不新增事实库或 UI。
- 数据补齐：六份文本通过原引用入口创建为 `mat_7751f5ca`（74,126 字节，6 文件，清单指纹 `453b2fe00c50…`），明确标记“设计/实施计划，非完成证明”。材料 **23→24**、正文 **6,595→6,601**、引用材料 **1→2**；来源原件与职业档案指纹未变，三主题 find/grep 及六份原文回读全部通过。
- 导航能力：`source_coverage` 与 `kb coverage` 显式区分 indexed/unindexed/stale/filtered/metadata_only/unavailable，按来源根、路径前缀、状态查询；隐藏目录剪枝，符号链接/敏感名跳过，错误显式报告。正文比较按单份材料的有序分片签名，兼容导入器换行归一；非 UTF-8 文本保留为目录项。`verify` 补已登记资产增删与 meta 指纹、来源目录盘点变化；引用授权检查使用 `--root` 对应策略。
- 真实盘点：5,759 个源文件正文已覆盖、1,213 个按规则过滤、469 个尚未纳入正文、817 个仅目录（附件/LFS/非 UTF-8），无扫描错误。其中工作资料 Office/PDF **125 份均有目录记录**（102 份 LFS 指针、23 份本地实体）；全部来源目录中的 LFS 指针 756 个。未纳入项包含此前默认排除的学习资料、模板等；不将目录覆盖宣称为正文可检索或经历已证明，也不自动下载 LFS。`kb verify` 通过。
- 验证：12 项新增回归先失败后修复，68 项受影响测试通过；独立审查提出 CRLF 和分片顺序问题，修复并复审通过。全量受限沙盒运行 **1,351 通过、8 失败、1 跳过、18 subtests 通过**；8 项均涉及既有 PDF 渲染或临时本地 HTTP 服务，在沙盒外原样复跑 **8/8 通过**。路线图、v2、AIEF 与差异检查通过。验证范围是 CLI/材料入口，未新增 GUI 深度验收结论；P0-026 仍唯一 next，本轮无平台操作。

## 2026-10-17 引用式材料首片：来源白名单、引用 RPC、证据链校验与 UI（P0-026 续）

- 能力：材料可引用允许来源根内的外部文件/目录，不复制原件；清单冻结（逐文件 sha256），内容变更/删除在读取、证据/档案校验、索引校验三处统一报 `material_source_changed` 并阻断；刷新（用户确认）后以最新内容为新基线，已绑定卡片自然进入"来源已变更，需重审"；新增文件不静默纳入。来源根由系统设置管理（路径必须为已存在目录，本机 policy 持久化）。
- 实现：`tools/infra/referenced_materials.py`（扫描/清单/校验/合并，含根内约束、符号链接拒绝、敏感名与空文件过滤）；`material.reference.scan/create/status/refresh/remove` 五个 RPC；`settings.get/update` 增加 `material_source_roots`；证据链在 `validated_source_inputs` 与 `_selected_text_materials` 收口校验；kb 构建/校验纳入引用材料（标记 `reference_status` 与「引用」）；UI：证据页「引用外部目录」（扫描预览→命名创建）与已引用列表（状态/刷新/解除），系统设置「材料来源」分类。
- 真实验收：始祖鸟工程档案经同 UI 代码路径创建为引用材料 `mat_0eb6c626`（扫描 6,060 文件 / 29.2MB、4.2s；建档 0.7s；缓存 31MB、清单 1.77MB；跳过 3,920 项=隐藏 2,812/非 md-txt 1,098/符号链接 5/空 2/敏感名 3）。审查后按扩展敏感名规则刷新为 6,058 文件、清单 `5390a47a…`；kb 重建 → materials 23 / documents **6,595**，`kb verify` 通过；真实读取校验 0.42s，指纹 mode=referenced。快照材料与旧指纹零回归。
- 独立审查与修复（同日）：审查子代理（含边界探针）发现并修复——TS 编译门禁曾失败（重复导入/缺失类型，已补 `tsc --noEmit` 提交门禁测试）；单档引用 kb 回读档号不一致；求职偏好从引用材料保存后无法回读；来源缺失/损坏清单错误码归一（统一 `material_source_changed`）；同路径重复引用拦截；撤根后指纹与 kb 校验阻断；扫描跳过数全量计数（更正此前 50 的截断误报）；坏清单 kb 误报 ok；`ensure` 校验 meta 与清单一致；敏感名规则扩展（password/密钥/凭证/全角 NFKC）；白名单拒绝 `/`、仓库根、材料库并去重 id。读取路径 memo 与 reconciler 校验列为后续项。回归 **1347 通过、1 跳过、18 subtests**（新增编译门禁与 10 项边界测试）。
- 边界：来源目录一分未动；缓存为派生文件（可重建）；与既有始祖鸟快照材料（998 文件子集）存在内容重叠，属预期（历史快照 vs 实时引用）；UI 真机冒烟由用户在 App 内确认。`.pen` 同步待办：pencil 工具要求先在 pen.dev 打开 `ui/design/piproofforge.pen` 后方可读写，DESIGN.md 已同步，`.pen` 待文件打开后补。

## 2026-10-17 材料库查漏补缺：导入 worklog-private 未索引资料（P0-026 续）

- 审计范围扩展：材料上游为私有工作仓 `worklog-private/`（00-EC+/01-ZA/02-NSTC/03-个人/04-编程，可导 md/txt 共 7,452 个）。此前仅导入策展子集；本轮按差集补齐。
- 本轮导入 **6 个材料包共 434 文件**（沿用 `handle_material_upload`，包与报告存 `backup-manifest/pi-proof-forge/material-bundles-20261017/`）：b5 求职资料（简历历史版本 24 + 投递自荐语 2 + 职业发展 2 + README，标注"历史口径，事实以时间线为准"）、b6 面试笔记 5、b7 众安补全 83、b8 九恒星补全 141、b9 EC+ 其余品牌 149（Pick Performance/冰雪集合店/Salomon/安踏/Kolon）、b10 EC+ 杂项 27（团队规范/个人汇总/00-总览）。
- 安全与噪音规则：3 个含密码/凭据文件（02-NSTC）与 1 个 Token 命名文件按既有规则跳过；250 个 workspace 模板与仓库元文件排除；b3/b4 已覆盖文件不重复导入（单文件导入的 4+1 个已从包中剔重）。
- 索引重建：materials **16→22**、documents **1121→1610**，`kb verify` 通过；INDEX「范围说明」补充上游来源；回归 **1320 通过、1 跳过、18 subtests**。
- 待决（未导入）：始祖鸟 features 归档 **5,076** 文件（体量大，建议分批/按需）；04-编程 学习资料约 350（教程/书籍/笔记）与旧个人项目 8，默认排除。
- 边界：无平台写入；求职历史简历仅作历史参考，不改动已确认事实与证据卡。

## 2026-10-17 知识索引首片：kb 查询工具与统一 INDEX（非 RAG）

- 目标与边界：为全部本机知识资产建立确定性导航索引（材料 16 份/1121 档、证据卡 85、岗位画像 27、职业档案 1），供 AI 用「目录树 + 字面检索 + 回读原文」查询，不引入向量/嵌入。索引只做导航：派生值（日期窗口/类型/线索）不是事实；引用必须回读原文并以 material_id/document_id/sha256 三元组锚定。
- 复用与实现：材料拆档复用 `split_material_documents`（稳定 document_id/sha256），卡片/档案/画像复用既有 YAML 解析，不新建数据存储；`tools/infra/knowledge_index.py`（构建/校验/渲染）+ `tools/kb.py`（build/tree/find/grep/read/refs/cards/person-docs/verify/index，全部支持 --json）已就绪。人写文档白名单 9 份（角色句可信来源）与合成夹具警示（mat_quick_run_verify 不得作事实来源）内置；产物 `knowledge-index/`（index.json + INDEX.md）本地产物、不入库。TDD 先失败后通过，新增 20 项测试。
- 真实数据验收：构建 **0.11 秒**，16 材料/1121 档/85 卡/27 画像；`kb verify` 通过；抽查 `kb refs ec_418bec8b` 正确显示九恒星引用链（mat_c70e7e91:dc974723…）与 2017-02 线索；缺时间/职责的真实卡 **55 张**（其中 21 张含日期线索）。完整回归 **1316 通过、1 跳过、18 subtests**。
- 查漏补缺（同日复核）：发现并补齐 **岗位线索 job_leads/ 624 条**（621 真实 + 3 示例；22 条已转画像，线索-画像双向链接核对一致）为新实体，含薪资/地点/公司规模/行业/状态，新增 `lead --promoted_to--> job` 关系与 `kb leads` 命令（--status/--has-profile/--size），grep 增加 leads 范围；构建器新增**索引缺口记录**（材料 meta 指向缺失文件等不再静默跳过，写入 INDEX.md「索引缺口」板块）；新增「范围说明」板块明确纳入/排除（排除 matching_reports/outputs 运行产物、uploaded_resumes 平台产物、profiles 模板、release-notes/scripts 仓库工程、resources 镜像副本，不重复索引）。回归 **1320 通过、1 跳过、18 subtests**。
- 审计修正（支撑后续补全）：材料线索比初判更丰富（雇主责任险 2018-11~12、读写分离现状 2026-02、Feature 收尾 2026-08 等）；模块文档中的"负责/主导"为系统职责噪声，已由人写文档白名单隔离；EC+ 品牌级周期（如始祖鸟 2019 起）按已确认时间线钳制为本人自 2021.03 参与，仅作参考，不自动填值。
- 下一步：证据卡补全工作台（三级候选：逐字区间/日期线索/无线索）复用本索引的文档选择、日期线索与引用校验；知识索引 Phase 2（侧车 RPC）按需启动。设计文档 `AIEF/docs/plans/2026-10-17-knowledge-index.md`。P0-026 保持唯一 `next`，本轮无平台写入。

## 2026-10-14 个人作品真实演示与面试案例材料（P0-026 续）

- 来源纠正：此前 `dsh --version` 的0.1.5-rc.2来自全局 `@deepseek-ai/dsh`，不是本人 `tongsh6/dsh`，不能作为本人作品启动证据。本轮使用本人仓库已构建 `@dsh/cli` 0.1.0；HEAD `c3680734e106aaa76d58f6b55668083d2c637e12`，运行后工作区仍干净，未安装、构建或修改作品源码。历史168次benchmark独立保留，整体ON64/84低于OFF69/84的边界不变。
- 定位与复用：现有App材料库、已确认dsh成果和MongoDB卡可用；代码、页面职责及路线图中未见现成作品演示/面试排练入口，故只创建本地合成夹具与讲解材料，再通过原生材料导入入口归档，不新增产品模块。演示调用作品原 `runCommand` / `runFullPipeline` / 真实 `DeepSeekClient`；外层文件/进程沙箱、固定API转发与预算是本次演示包装，不记为作品原生能力。
- 离线核验覆盖四项拒绝、三项允许写入、真实grep与npm测试工具、原模块导入。独立审查发现的路径规范化、允许工具、上游取消与响应头异常问题均已修复。凭据保留父进程、子进程仅见合成资料，固定12请求/300秒/1修复；没有降低既有测试或代写正确答案。
- 首轮 `2026-10-14T12-02-49-486Z`：12次真实请求全部HTTP200；包装测试命令与作品白名单及进程限制不兼容，导致预算耗尽，后续403来自本地额度限制。独立6/6测试通过但状态preflighted、退出1，保留为失败。改用作品已允许的npm test并离线实测后重跑，没有更改测试断言或作品实现。
- 成功轮 `2026-10-14T12-06-29-527Z`：12次真实请求约54秒，状态verified、退出0、0修复轮、交接已生成；初始4失败/2通过，最终固定6/6通过，只改src/batches.js，测试/配置指纹不变、无额外未跟踪文件。两轮共24次请求；单个合成任务的成功不等于通用可靠性或本人已现场演示。产物及来源指纹见 `outputs/interview_preparation/sophon-20261014/verification.json`。
- 案例材料按已审核卡 `ec_1bff0277` 及原文整理索引误选根因、流式发送与批大小取舍，保留本机容量验证/UAT待验边界；历史180单测+46集成仅为报告记录，本轮未重跑。原文“16MB单命令”的协议说法未直接采纳为确定事实。提纲包含8分钟演示顺序、源码入口、历史benchmark负向整体结果和需要本人回答的追问。
- 真实App已导入“作品实跑与架构案例（排练稿）”，材料数15→16，刷新后记录仍在、职业档案仍已确认；材料id与文件指纹保存在上述本机验证记录。没有重新生成简历或提高评分，没有修改已确认事实/证据卡、没有新增招聘平台上传或发送。下一步为本人限时排练、核实实际雇主与学历条件，再审核是否投递；P0-026保持唯一next，面试磨练目标尚未完成。

## 2026-10-14 本地PDF名称可读性修复

- 用户指出“某上”过度简略。原因是本地导出共用了猎聘24字符上传短名，匿名来源“某上海专业技术服务公司”被机械截断。Quick Run与简历中心目录导出已改为保留来源公司/岗位全称，复用原命名记录和文件锁、独立用途key及冲突处理；平台短名、旧记录及上传长度门禁保持。
- 三条入口/稳定性回归先失败后通过；51项受影响测试与独立审查通过。App重启后在简历中心重新导出两份最终A版，成功提示显示完整名称；与旧稿逐页文本和渲染像素完全一致，未重跑模型。新文件位于 `outputs/resume_exports/20261014/`，证据见 `outputs/acceptance/pdf-filenames-20261014/validation.json`。没有新增上传或投递，主线顺序不变。

## 2026-10-14 剩余缺口复核与下一批候选验证（P0-026 续）

- 资料复核：作品集与本机dsh/loamlog架构、模型路由代码可反证“完全无AI架构依据”，但不能据此声明公司级生产AI平台责任已证明。目标“四个业务域”不应成为同数量历史经验门槛；跨品牌协作仍需按实际职责边界核对。上述为人工来源对照，不覆盖历史模型分数。
- 云治理：App导入的RDS方案/数据库现状/评估文档与本机原件一致，包含阿里云代理、读写分离与验证计划，但负责人/上线时间为空，结果表有待采集项；已向用户询问本人职责、阶段及时间，未答前保留未知。运动中心文档的Kubernetes/Jenkins/ELK包含设计、todo与预期描述；个人工具多账号、业务账号域和只有标题的灾备文档不能当个人云治理实绩。没有更改原始资料、已确认档案或证据卡来抬分。
- App检索：完成7组官方在线搜索，合计140条返回（含重复），并结合既有完整JD人工审阅10项候选。Sophon核心工程为优先验证，不动产AI平台全栈为条件候选；VoiceCursor与已投平台负责人保留挑战样本。工业AI Infra、客户交付MES、芯片同名后端及超出当前证明范围的金融治理岗位不作为本批高匹配凑数。匿名或人力资源发布主体不等于已核实实际雇主；学历仅按JD原文判断，不添加全日制门槛。
- 两份已审核目标JD均由App刷新且原文未变，复用原画像及51张证据。Sophon `qr_20261014033036924611` 完成：17模型调用含1次纠错，335.26秒；50/50/69、8/8要点可追溯、两页，逐页未见裁切/重叠。自动范围仅4任职/0编号职责/9子项，非编号正文由人工另核，不可把50分当完整JD结论。面试重点为现场跑通作品、架构决策与根因复盘；原稿尚待人工审核，未上传/发送。
- 第二岗首跑 `qr_20261014033913786544` 被串卡引用阻断；先失败回归后补具体事实ID/期望卡定位，仍只纠错一次。重跑 `qr_20261014034530755503` 虽完成，但发现“背景与能力要求”被吞入职责，10任职/18职责/63子项的结果不采用。先补3个失败标题回归后，终止标题增加背景与能力要求/任职条件/加分经历，实际范围恢复10任职/8职责/46子项。独立审查无阻断，1279项完整回归通过、1跳过、18 subtests通过。
- 正确范围运行 `qr_20261014035843582041` 已由App完成：51卡，10任职/8职责/46子项，20次模型调用含1次修复、1缓存、626.63秒；50/36/68、17/17条要点可追溯，事实完整、自动质量未通过。两页PDF逐页未见裁切/重叠；Python/FastAPI、React/Next、PostgreSQL的直接经验依据仍不足，不能用Java/Vue或其他数据库经验替代，故保持条件备选。
- 作品运行补证：另读到dsh历史benchmark报告（2026-05-22，run `260521151313`，168次trial）。当时另查全局 `dsh --version` 为0.1.5-rc.2；**同日后续确认这是官方同名工具，该版本检查不能证明本人作品可启动，已由上方真实演示记录纠正**。历史报告支持曾实跑，不能单独等同当前面试演示已完成；整体ON64/84低于OFF69/84，不能把部分子集正向效果宣传成全面提升。提纲包括真实作品演示、模型路由/验证的架构取舍，以及MongoDB本机索引问题的复盘，保留本机/生产边界。
- 最终建议为Sophon优先验证、不动产AI全栈条件备选；未认定已凑齐两项高匹配岗位。下一步优先准备Sophon可复跑演示和具体故障/架构案例，再审核是否投递。RDS待答项可暂留未知，不阻断这一准备。资料/候选对照、最终两份PDF指纹、原生观察及失败/被替代记录见 `outputs/acceptance/p0-026-gap-review-20261014/validation.json`。本轮新增上传/投递0；P0-026仍唯一 `next`，面试磨练未完成。

## 2026-10-14 原文事实优先级与最终正文验收（P0-026 续）

- 定位与复用：生成器已有引用优先，但把所有被引用事实压成集合，再按原顺序截取3条行动/2条成果；这使跨品牌复用、服务职责划分被通用框架描述挤掉。本轮复用语义引用、模板、trace和原Quick Run，保留子项支持状态及父要求标识，按新增父要求支持权重取舍，同父项重复引用取最大值、不累加。不新增资料或人工改简历事实。
- 语义提示：澄清目标公司平台专名/城市/业务域数量不自动成为历史任职条件；先核对个人AI实践，再区分部分支撑与公司级生产缺口。旧支持门槛、来源校验、责任限定、最多一次纠错保持。提示词变化使对应评估缓存失效，未改写历史报告、未人工提高分数。
- 真实 App：首轮 `qr_20261014023614193411` 因未知事实ID失败，未生成新稿；补失败回归后让错误携带受限长度的具体编号，纠错提示要求复制输入真实ID，仍拒绝无效引用。第二轮 `qr_20261014024541779013` 复用缓存完成（4模型调用含1次修复、22缓存、108.38秒），51卡/11项要求/8项职责/85子项，58/58/71。独立审查及旧模式A/B×3定位对照通过。
- 成品反查又发现摘要按首条模型引用选了局部流程细节，且场景中的两条完整成果重复列为bullet，导致第三页。先补两个失败测试再修复：概述保留已确认当前职责与首条代表贡献，细节留在任职段；仅同卡场景精确包含完整成果时省略重复正文，results claims仍独立登记，不跨项目、不同义推断、不缩字号。
- 最终 App 运行 `qr_20261014025020412147`：**25缓存、0模型调用**，51卡，仍选跨品牌汇总/统一运动中心/MongoDB。**58/58/71，19/19条要点可追溯**，事实完整、`NEEDS_REVIEW`、自动质量未通过。PDF **2页、661733字节**，SHA256 `c5d655426382b7d403d2a0d5a68374a55967aa0552527f68c00cf56936bf1fa7`；逐页无裁切/重叠，摘要中的团队规模与“参与或负责”保留，个人开源/本机验证和教育性质边界明确。App展开平台规划，服务职责和18服务/13模式复用均显示已在正文呈现。
- 效果边界：固定旧评估做隔离诊断，正文排序使覆盖45→47、适配仍53；最终58/58还包含模型重评影响，不能全部归因于选材。正文仍有篇幅取舍导致子项未呈现，父级覆盖分等于适配分不代表全部子项都完整呈现。AI平台部分子项从不足转为部分支持，但 `d3.c7` 仍忽略个人项目架构依据，`d8.c4` 仍以目标业务域数量解释差距，属于待人工复核的判断，不据此宣称本人缺能力。
- 验证：最终完整回归 **1275通过、1跳过、18 subtests通过**；独立审查及追加审查无阻断问题。仅后端逻辑和文档调整，真实App新子进程已加载，无结构性UI/前端构建变更。旧审批队列、已发送PDF指纹与已确认资料保持，本轮新增上传/投递0。证据见 `outputs/acceptance/p0-026-fact-priority-20261014/validation.json`、同目录原生观察、对照和逐页图。
- 下一步：本轮已完成原文优先级、摘要及重复呈现修复。继续区分个人AI实践的剩余误判与云治理/企业生产平台的真实证据缺口，再决定此岗位的适用性及下一批候选；不要为了通过评分补造经历。P0-026保持唯一 `next`，面试反馈目标未完成。

## 2026-10-13 评估校准与固定PDF质量呈现（P0-026 续）

- 探索与复用：延续既有 semantic engine/infra、Quick Run、Scorecard、review snapshot、审批组件和内容门禁；不新增匹配引擎、资料库、模型或投递授权。规范、DESIGN、RPC及原 `.pen` 同步，先失败测试再实现，独立审查发现的问题已补回归关闭。
- 评估：`evidence-semantic-v3` 将完整JD可识别编号职责及任职条件共同评审，原文父要求保留、并列子项分批校验；备选关系保留为组，职责动作句不拆成孤立技术名。技术/职务标签和缺本人角色的项目不能直接证明完整实践；同卡结果继承责任限定，引用有效但夸大“主导”的理由保守降为部分支持，原不足/冲突不提高，无效引用仍阻断且每请求最多纠错一次。数字活动名、日期及技术版本不再冒充量化成果；表达仍是规则参考，未完成完整语义编辑质量判断。
- 审核：固定PDF保存绑定正文/PDF/Scorecard的质量摘要，摘要指纹纳入manifest；原审批动作记录所接受的质量缺口，展示事实完整、自动质量状态和匹配/覆盖/表达三项。缺失或被替换的已绑定摘要在释放上传字节前拒绝；历史无绑定记录显示“质量状态未记录”，不补造历史评分，不扩大授权。规则模式仍按原评分门槛判断。
- 实际运行：首轮 `qr_20261013113026583488` 在责任强度判断处失败，未生成新稿；51卡和32子项有效缓存保留。调整为上述保守校准后，真实 App 启动 `qr_20261013115220105966`，19:52至19:56完成（8模型调用、18缓存、1次请求修复、278.66秒），全部51卡评审。范围为11项任职要求、8项职责、85子项；父项3支持/14部分/2不足，子项20支持/38部分/27不足。指标 **53/45/71**，事实完整但仍 `NEEDS_REVIEW`、自动质量未通过。旧86分范围较窄，不能直接解释为候选人能力下降。
- 成品：仍选跨品牌汇总、统一运动中心、MongoDB治理，20/20条正文要点可追溯；PDF两页、662987字节，SHA256 `04ce69f1def18ac5710b59a3786957fc02ce1de18bcdcbe908a78a3da37ddb4a`。逐页检查无裁切/重叠，EC+ 2021-03、统一平台年份精度、非全日制、个人AI项目及本机测试限定保留。真实页面已展开复合云原生要求、平台规划职责及33条质量缺口，能区分证据池与正文状态。
- 历史回读：App重启后旧发送版本显示“质量状态未记录”和已有成功回执，重试投递禁用。回读按钮首次被自动审批因名称可能含写操作拒绝；核对既存quick_run_id和handler直接返回分支后重试成功。旧队列SHA256前后同为 `1da3029c038b337986bb6d681d4db8a905888739a4ec22848e90b10b2e5b75c4`，旧发送PDF指纹仍为 `2d3f8756e00138053f6da71e256d21fe4631870ef0618609e436c1574174818e`，无新增上传/发送。未为验收绕过同岗位防重复规则；新质量绑定审批的正向场景及损坏拒绝由临时目录集成测试覆盖，尚非新的真实岗位审批验收。
- 验证：完整回归 **1269通过、1跳过、18 subtests通过**（14.03秒）；前端TypeScript/Vite和Tauri调试App构建通过，独立审查最终无阻断项。原生运行及重启验收如上；Pencil实际区域截图可读，布局诊断仍报告 `4auHI` partially clipped，不能称设计机器检查全绿。证据、源码前副本及逐页图片位于 `outputs/acceptance/p0-026-assessment-20261013/`。
- 剩余：统一平台正文仍偏框架清单，已存在的微服务职责划分、18服务统一平台/13模式复用等事实未充分呈现；模型对目标公司专名、可迁移经验和个人AI项目还有需人工复核的过严判断。下一片先修复这些已有事实的表达/判断，不要求用户凭空补数，不将53分视为能力定论。整体简历质量及小公司面试磨练仍未完成，P0-026保持唯一 `next`。

## 2026-10-13 目标正文取舍与真实两页 PDF 验收（P0-026 续）

- 探索与复用：沿原语义匹配、模板、trace、内容门禁及原生 Quick Run/简历中心修复；不新增页面、匹配引擎、模型或投递入口。语义汇总可以读取全部完整项目事实，最终不再锁定初步三张；按逐项引用的新增事实覆盖选择，不用未引用旧项目补满名额。
- 正文取舍：语义版本以 trace 的 `targeted_v1` 区分完整档案和实际展示；保留身份、全部任职公司/职务/时间线及已选择展示的教育，省略未引用旧贡献。摘要保留当前职责和完整的已确认个人贡献限定；相关个人成果提前，技术栈正常展示。内容门禁只对这一经 trace 校验的新模式放宽全量贡献全文覆盖，档案修订、来源、正文/PDF绑定及审核授权仍保留；旧规则和默认平台简历契约不变。
- 真实 App 首跑 `qr_20261012174830526232`：51/51卡，11次模型调用、1缓存、0修复，273.44秒。选中跨品牌工作汇总、统一运动中心、MongoDB容量治理，2018年大屏退出。独立审查发现“引用能力分类时被前三组截断遗漏”，真实成品发现“技术栈在排序前已截八项导致Docker Swarm遗漏”，均补失败回归后修复；共享技能对实际包含此事实的每个来源建立 claims，未引入同义推断。审查最终无阻断项。
- 最终原生运行 `qr_20261012175759758556`：12缓存/0模型调用，输出A/B和PDF；App简历中心已查看最终A版。固定原事实及字号，教育改为完整单行信息，消除仅一条教育占第三页的分页问题。最终A版PDF两页、660335字节，SHA256 `18fb0ddc721aa6cc7ee03af5771fa866155508b97eaad660ca2795cf7cb74d54`；逐页渲染检查无文字裁切/重叠，工作区间和非全日制标注保留，统一平台仍为年份精度，个人AI项目与本机验证边界明确。跨品牌项目正常跨页，仍有长背景及泛化成果的后续编辑空间。
- 验收口径：岗位适配/正文覆盖/表达 **86/77/74**；`content_ready=true`、`NEEDS_REVIEW`、`quality_passed=false`。20/20条正文要点的trace验证通过，新生成内容门禁通过。云原生/云账号治理等仍缺直接证据，hands-on评估还引用未展示且缺角色/时间的代码审查卡；不能把86当作已验证能力或质量通过。复合要求/职责覆盖、责任强度判断、数字量化评分与审批缺口展示属于后续评估切片，本轮没有完成它们。
- 验证：完整回归 **1242通过、1跳过、18 subtests通过**；最后纯教育排版变更后相关11项再次通过，最终两页视觉检查通过；独立审查另外核对旧规则A/B×三种定位的正文与claims和基线一致。仅后端生成/校验和文档改动，无结构性UI变更，不需重建前端；App已正常重启加载，真实结果由原页面操作生成。路线图/差异检查通过。
- 用户“授权”对应的职业档案重新确认及重启回读已完成，来源整合首片的确认/生成接续已验证。旧发送PDF指纹保持不变，本轮平台上传0、发送0。新PDF、输入/输出摘要、源码修改前副本、原生观察及逐页图片见 `outputs/acceptance/p0-026-resume-projection-20261013/`；首片记录见相邻目录 `p0-026-source-merge-20261013/`。P0-026仍唯一 `next`，当前继续评估与审核信息的缺口，不声明简历整体质量或面试磨练完成。

## 2026-10-13 档案重新确认授权接续（P0-026）

- 用户明确回复“授权”，已由真实 App 勾选并执行整份职业档案事实确认；页面显示“职业档案已确认”“资料库状态已就绪”。正常退出并重启 App 后，确认状态与两张卡的更新记录仍保留，解除上一轮确认阻断；没有修改已确认档案正文或补造 Feature 项目任期。
- 确认后的修订号 `f9c61d303389c123ba2c2663b2466968fbf35f33da51eb8c6c3c3aaee0de283e`。原始补证记录已补充授权与重启证据；此次授权不扩展到招聘平台上传/发送。
- 已继续按既有计划实施目标正文取舍：先有规范和失败回归，语义选材可从全部完整卡中按新增引用覆盖决定最终项目，不凑三项；完整档案与目标展示分离，保留身份/时间线/教育及来源门禁。原生 App 已启动同一平台负责人岗位、51张证据、既有详细底稿的全链路生成；最终内容与 PDF 验收尚在进行，以后续结果为准。

## 2026-10-13 App 跨文档补证与年份精度首片（P0-026 续）

- 复用证据页原“重新审核”、材料片段选择器和 saveDraft，增加“从其他文档补充依据”：当前值与原文对照、本人/项目/阶段核对、单值替换与行动/成果逐条追加、保存后展开字段出处。原来源只能追加，卡版本与文档指纹必须一致；不另建材料库、事实存储或模型调用链。规范、RPC、DESIGN 和 `.pen` 已同步，设计布局复核无剩余裁切项。
- 补证卡原材料指纹现进入候选资格、职业档案修订、语义输入/缓存以及生成 trace；来源变化时不继续使用旧确认或报告，旧投递快照保留。年份/年月区间按原精度保存，生成检查和自动关联共用保守区间判断；与入离职边界不明确的年份仍须核实，单独盘点/验收日期不算任期。
- TDD 与独立审查：先复现多来源拒绝、年份拒绝、原材料变化不撤销确认等失败，再实现。审查发现普通编辑后重审可能绕过新事实引用、年份误关联上一任职、整份材料旧卡补精确引用后失去旧结果范围，均补失败回归并修复；最后批准事实快照持续保留并校验，含首次编辑及清空全部绑定后的路径。多行行动/成果采用改为逐行绑定。最后独立审查无剩余阻断项。
- 真实 App：在原生 Tauri 重建后，统一运动中心卡 `ec_0a93729d` 从既有 EC+ 详细底稿补入“2022 – 至今”和“Tech Lead，平台架构设计与核心模块开发”，审核保存、列表和详情回读、两项字段依据展开均成功。先输入源文不存在的职责句，App 明确提示未找到并禁止采用；真实引用才可进入草稿。Feature 盘点卡 `ec_57ff48ed` 补入“建立并持续执行 Feature 化交付机制”的职责依据并保存；其 2026-08-03 仍为事件日期，不转作项目区间，仍不能通过代表项目时间检查。旧结果未改写为生产指标或新的个人成果。
- 当前确认边界：两张卡变化使职业档案自动回到待确认（档案正文无变动、无缺项）；自动审批审查拒绝代点“确认整份职业档案”，理由是确认覆盖公司、职务、时间、教育与补充成果，超出本次两张卡的范围。已向用户请求整份档案重新确认授权或由用户在 App 确认，未绕过；整合后跨重启的最终档案确认/生成验收待继续。
- 验证：最终 `tests/unit + tests/acceptance` **1234 通过、1 跳过、18 subtests 通过**；TypeScript/Vite/Tauri debug app 构建通过，Vite 原有 chunk size 警告保留；路线图与差异检查通过。全量首跑的单个旧 GUI harness 新组件 import 错误已修复并复跑通过。无模型调用、无平台上传/发送；开发工具、依赖和全局配置未变。代码及两张原卡/档案的修改前副本、原文指纹和原生操作记录见 `outputs/acceptance/p0-026-source-merge-20261013/`。
- P0-026 仍唯一 `next`。这是资料整合首片，不声明整份简历质量或面试目标完成；后续按既有复盘顺序修正内容取舍、匹配/表达评估及审批缺口展示，再以同一岗位在 App 验收新版 PDF。

## 2026-10-13 简历质量、生成流程与资料整合复盘（P0-026 续）

- 按用户要求依次复查实际发送的简历、App 生成/评估/审批链路、本机求职底稿与材料库。审阅对象为 `qr_20261012133910934525` 的 A 版及 `ar_20261012134103796390` 固定快照；发送 PDF 的 SHA256 仍为 `2d3f8756e00138053f6da71e256d21fe4631870ef0618609e436c1574174818e`，701357 字节、3 页。重新渲染并逐页查看，未修改已发送文件。结论：事实边界与发送链路已有验证，岗位定制质量、评估可信度和资料整合仍有缺陷；前轮主要验证完整性、可读性和发送成功，不能据此宣称简历质量达标。
- **成品质量**：首屏职业概述和五组能力偏通用业务交付，未突出平台架构、工程治理与 AI 工程实践；工作经历和跨品牌汇总重复团队/模块规模，早期经历占用篇幅。第三个项目是 2018 年双十一大屏，在最终 11 项要求评估中引用数为 0；个人 AI 项目排在第三页教育经历之后。MongoDB 案例的本人职责、具体行动及本机容量验证边界值得保留；EC+ 2021-03、15+“参与或负责”、个人开源与公司经历的区分正确。三页本身不判失败，问题是信息优先级和重复。A/B 当前仅一条行动不同，尚未形成有效的不同表达版本。
- **模板与内容门禁**：`tools/run_generation.py:179-245` 固定输出全部能力、工作贡献及补充成果，有 skills groups 时不再展示证据 stack；`tools/infra/resume_content.py:22-32` 又要求上述档案文字全部出现在批准正文。只在内存中删除一条早期工作贡献的复现立即得到“批准正文缺少已确认职业档案中的内容”，原正文无问题。完整事实库被当作必须全文展示的模板，妨碍精简与定制；应保留完整任职时间线与事实来源，同时允许有依据的选择、压缩和排序。
- **选材与评估**：51 卡全量评审已有价值，但 46 卡被展示完整性检查排除；`tools/infra/semantic_matching.py:193-209` 在逐要求评估前即锁定最多三张完整卡，最终难以按新增覆盖替换第三张弱相关卡。岗位适配只逐项评估 11 条任职要求，原 JD 的 8 组工作职责未独立评估。r3 理由把“参与或负责 15+”升级为“主导15+”，r5 用两个技术名支持复合要求、r10 仅引职务名称支撑跨团队能力，说明原文引用有效不等于结论成立。86 是当前模型支持度，不能作为能力已充分证明的结论。
- **呈现与评分错位**：r5 引用 stack，生成器未展示该字段，评测按来源 ID 和字段精确对应判为未呈现；其中 MongoDB 实际已通过同项目其他字段充分出现，另有 Docker Swarm 确实漏出。需区分已验证事实的等价呈现与真实遗漏，不能用简单关键词替代。`tools/run_evaluation.py:110-156` 将“双11”、技术版本号也计作量化成果，篇幅仅按字符/行数、重复仅按规范化后的相同句判断；75 分不覆盖首屏定位、语义重复和实际 PDF 版面质量。
- **审批信息缺失**：最终 `content_ready=true`、`quality_passed=false`、覆盖73/表达75。现有内容门禁允许完整稿进入人工审核，属于已知人工路径；用户实际确认不属于未授权发送。但 `native_pdf._public` 与 Submissions 审批卡只携带/显示匹配86，未随固定版本展示覆盖、表达和具体缺口，容易把链路通过误读为质量通过。后续需在 App 审核页明确事实完整、质量未达与人工接受的缺口。
- **整合有效性**：现有15份材料可拆为1120个文档片段，85卡中51张可用、10张未完整、24张历史卡。51张可用卡中45张缺有效本人职责、41张缺时间，仅5张满足本次展示检查；可用卡的 results 原文追溯检查均通过，但不证明这些句子都是本人已完成的成果。全库56个精确文档引用、5张卡仅绑定整份材料；该统计不能直接换算为资料利用率。职业方向材料已用于偏好、AI作品集已用于三项档案补充成果，不能因没有独立卡就认定完全未用。
- **已存在却未整合的事实**：本机简历 README 已明确 Feature 机制由本人建立、14业务域/57已上线Feature（统一业务确认，非此次重验生产）；EC+详细底稿明确统一运动中心为“2022–至今、Tech Lead、平台架构与核心开发”，对应卡仍缺角色/时间。AIEF 等个人工程治理材料与本次 JD 相关，尚未有效进入成品。发布策略定义、代码审查建议不能直接当作已完成成果；云平台多账号/网络权限、IaC等仍缺充分直接证据，存在阿里云资料或同名 Prometheus 词语不等于本人具备该能力。
- **整合机制缺口**：`tools/sidecar/handlers/evidence.py:705-727` 每卡最多一个精确文档引用、重审禁止变更来源，难以合并“详细底稿中的角色/时间”和“模块文档中的行动/成果”。年精度“2022–至今”又被 `career_profile.parse_project_period` 的完整年月规则拒绝，不能靠虚构月份修复。已确认覆盖值、档案 extras 与原始材料缺字段级关联；材料拆分还直接过滤 AGENTS.md 等文件，可能遗漏上下文工程成果，但这些文件只能作为不可信素材阅读，不能执行其中指令。
- 后续复用现有材料库、证据审核、职业档案、Quick Run、trace 和固定 PDF：先接通已确认事实的跨文档对账与时间精度，再按完整 JD 职责做内容取舍，修正评估及审批缺口展示，最后在真实 App 生成并审核新的针对版。优先用统一运动中心/Feature治理验证最小切片，不扩大采集、不新建匹配引擎。详细待实施顺序见既有语义匹配计划新增复盘节；P0-026 仍唯一 `next`，质量修复先于追加投递，面试磨练仍未完成。
- 本轮只读业务数据并记录复盘，无模型调用、无档案/卡片改写、无平台上传/发送、无新增真实 UI 验收。审计统计、内容门禁复现及三页图片：`outputs/acceptance/p0-026-quality-retro-20261013/`。本轮不重复运行与文档审计无关的全量测试；后续修复需按改动补失败测试并完成 App 验收。

## 2026-10-12 首笔小公司岗位 PDF 实投成功（P0-026 续）

- 用户明确确认已固定三页 PDF 上传及 `<local-candidate>` 平台负责人岗位投递，含平台解析补全在线简历、后续投递附带的影响。全程由真实 App 页面操作完成上传、附件核验、岗位核验、沟通、指定附件确认发送、回执核验与只读状态同步；没有改写候选事实、换文件或扩展目标。
- 上传一次，官方上传/保存均 HTTP200/flag1。新版猎聘附件页改用 CSS-module 卡片并把旧独立列表并入详情，原核验未找到卡片；沿已有 inspect/绑定路径最小兼容新卡片。缺旧列表时，必须当前官方页面唯一卡片与上传 fileId/名称/大小/附件ID一致，且浏览器实际下载HTTP200、701357字节、SHA256与批准PDF相同才继续；403/失败不降级。原上传记录保留，未重传。核验失败提示也已在 App 显示。
- 首次沟通前旧测试批次 `validation_pdf_three_20261001` 已3/3耗尽，当日0/3、未决0，因此在发送前被原额度守卫阻断。复用既有补充批次能力接入 App 单次授权入口，按本次确认登记固定1次、绑定审批运行/岗位键/PDF的授权；旧额度和历史不重置，其他范围不能消费，重复登记不补额度，全局防重与上海每日最多3次保留。实际登记在App完成，SQLite修改前已一致性备份。
- 实际成功：审批运行 `ar_20261012134103796390`；提交 `native-6bfad50f0b4b497a998d0a7134348f78`；批准PDF指纹 `2d3f8756e00138053f6da71e256d21fe4631870ef0618609e436c1574174818e`。确认框选择与发送请求携带相同附件ID；`send-resume` 业务回执 HTTP200/flag1/data{}，App显示“PDF投递已获业务回执确认”。本地只读证据检查 `verified`，必需步骤、快照、回执和SQLite互相一致。
- 状态回流：从沟通页直接同步因缺正向登录标记被阻断；经既有只读附件检查回到标准页面后同步成功，17/17受控记录匹配、1条平台行未匹配。新岗位按 job_id 匹配，平台状态为“已投递”，平台时间 **2026-10-12 22:35**，未把发送成功当作已读、面试或录用。
- 验证：最终全量 **1223 通过、1 跳过、18 subtests 通过**，TypeScript/Vite/Tauri调试包及架构/路线图/差异检查通过；既有chunk size警告保留。附件核验与单次授权均独立审查通过，真实App恢复后验证。图稿、DESIGN、RPC及规范同步；工具/依赖/全局配置未改。
- 收口范围：当前单次授权1/1已用完，今日成功1、未决0；本轮上传1、投递1、删除0、重传0。本轮首笔实投验证与状态回流完成，P0-026仍为唯一next，后续等待真实招聘反馈、面试与复盘，面试磨练目标尚未完成。原生事件、静态契约依据、数据库备份和完整证据位于 `outputs/acceptance/p0-026-fact-enrichment-20261012/`。

## 2026-10-12 猎聘登录完成与上传前检查（P0-026 续）

- 用户表示已登录后，由真实 App 核验为有效登录；附件页首次跳转短暂显示未确认，页面稳定后重新核验成功，无需重复登录。App 只读检查到 1 个附件选择控件，支持 PDF 等格式，最大 20M；当前固定文件约 744KB，指纹与审阅快照一致。
- 平台页面再次明确：上传将智能解析并完善在线简历；主动投递/发简历或同意索要时附件随在线简历发送。用户本次只确认登录，具体 PDF 上传与目标岗位投递的确认仍待回答；批准框未勾选，候选 pending，上传/发送均 0。最终固定审核运行及文件不变，P0-026 保持唯一 next。

## 2026-10-12 App 事实补齐与固定 PDF 审核（P0-026 续）

- 原生 App 完成：跨品牌工作汇总卡重审，将个人期间纠正为 EC+ 任职期 `2021-03 ~ 至今`，背景明确为任职期间汇总，不再把品牌线 2019 起点当本人参与时间；原成果、附件与来源指纹保留。导入本机 AI 作品集，在既有职业档案“补充成果”录入 dsh、loamlog、ReleaseHub，明确个人独立/开源/持续迭代属性，保存并重新确认。未知的发布策略/代码审查本人职责与任期未补写。
- 复用补齐：语义事实表接入已确认 `career.extras`；全 51 卡仍评审，代表项目优先采用通过既有职责、时间、版本与任职关联检查的卡，最多三项且不以缺项卡凑数量。汇总同时获得拟展示项目完整事实，在相同支撑力度下优先引用；未展示引用仍记为 `not_present`。原生新增条目输入名称自动折叠的问题已修复，并通过不保存的临时草稿验证，最终档案保留三项真实成果。
- 模型质量异常如实处理：中间运行 `qr_20261012132219388656` 出现“12年未达10年”“4年未达3年”和 JD 未要求却强加企业生产门槛，64 分不作为有效结论。新增确定性矛盾校验及最多一次修复，要求评审带日期、逐项独立、不扩大“或”的条件；来源引用并不等于逻辑正确。独立审查发现的跨主体/跨转折/中文年限误杀与缺 status 错误路径均先红后绿修复；旧报告复用也重新校验。
- 最终原生运行 `qr_20261012133910934525`：方向符合，**51/51 卡，12 次缓存命中、0 模型调用**；模型适配 **86**、简历覆盖 **73**、表达质量 **75**。入选跨品牌工作汇总、MongoDB 容量治理、众安双十一项目。`content_ready=true`、`NEEDS_REVIEW`，事实缺项已清空；`quality_passed=false`（表达低于78且仍有云原生/云平台治理、简历未呈现缺口），没有把完整内容等同于自动质量通过或批准发送。
- PDF：由 App 生成并固定三页候选版本，逐页核对了日期、个人项目边界、分页和可读性。修复原材料截断 Markdown 强调符号的显示，并保留代码中的 `**` 运算符；不改源事实、Markdown 或旧固定快照。最终固定审核运行 `ar_20261012134103796390`，状态 prepared/pending，App 已预览、批准上传框未勾选。
- 验证：最终全量 **1212 通过、1 跳过、18 subtests 通过**；TypeScript/Vite/Tauri 调试包通过，既有 chunk size 警告保留；架构/路线图/差异检查通过；匹配、反误杀、连续录入与 PDF 格式均独立审查通过。最终图片与原生观察见 `outputs/acceptance/p0-026-fact-enrichment-20261012/`，修改前档案/卡片备份同目录；开发工具、依赖、全局配置未变。
- 下一动作：App 内猎聘会话目前显示登录/注册，需要用户登录；上传会补全在线简历并随后续投递附带，具体目标/PDF及该影响待确认。当前平台上传/发送均 0；P0-026 仍唯一 `next`，实际投递与面试反馈目标未完成。

## 2026-10-12 App 求职偏好与方向筛选（P0-026 续）

- 用户强调以 App 能力为主。本轮复用简历中心材料库、个人资料存储、Jobs 完整 JD 审核与 Quick Run 语义管线，补上“材料提炼偏好 → 引用核对 → 保存 → 按职责先筛方向”的缺失环节；本机脚本用于开发和诊断，实际材料导入、偏好保存、JD 解析审核与运行由外部自动化操作真实 Tauri 页面完成。
- 简历中心新增“求职方向与边界”折叠区。真实职业方向分析经本机 Qwen 提炼并核对后保存 8 条（主投 2、桥接 1、探索 1、回避 4），每条保留原文引用；偏好使用独立修订号，不进入简历、不使职业档案确认失效。来源材料变更需重新确认，文件型 JD 解析正文；偏好来源、岗位正文文件及档案指纹在评审发布和报告复用时校验。
- Quick Run 语义模式先判断方向符合 / 需核实 / 明确不符，明确不符时停止后续生成，展示偏好与 JD 原文；规则模式和 Agent 简化循环不宣称已接入这次语义判断。没有完整 JD 或偏好材料失效时给出明确处理提示。
- 真实正例：`<local-candidate>` 平台负责人（上海、50–99 人）由 App 读取完整 JD、解析并核对 11 项要求、保存完整画像，随后全 51 张证据评审完成。方向 aligned，模型岗位适配 **86**、简历覆盖 **73**、表达质量 **73**；首次 351 秒，14 次模型调用（含 2 次校验修复）。这些是模型支持度，不是已验真的能力结论或录用概率。原文引用可展开，仍 `NEEDS_EVIDENCE`、不可投递。
- 真实反例：复用已保存的模拟 IC 岗位，方向 excluded，管线 SKIPPED，未生成简历。首次页面暴露旧逻辑把 SKIPPED 当成四阶段全部完成；先红后绿修复无文件时的 `NOT_GENERATED` 和后续“已跳过”文案，更新 App 后原生复跑通过，并显示返回岗位中心入口。
- 验证：全量 **1200 通过、1 跳过、18 subtests 通过**；TypeScript / Vite / 离线 Tauri 调试包、v2 架构与路线图检查通过；Vite 仍有既有 chunk size 警告。独立审查发现的两处来源边界问题已修复，停止分支显示修复也复核通过。开发工具、依赖与全局设置无变更。
- 剩余主线：将底稿已明确的个人参与时间及本人角色通过 App 对账写回相关证据，补入个人 AI 工程作品且保持个人项目与任职经历的边界，再重新准备可投递版本。当前入选发布治理/代码审查卡缺角色与时间，云平台多账号/网络权限治理仍缺直接证据，AI 项目资料尚未进入本次评审；不得为提高分数补写未知事实。P0-026 仍唯一 `next`，本轮新实投 0，面试反馈目标未完成。
- 原生操作、来源、运行编号、结果与限制见 `outputs/acceptance/p0-026-job-preferences-20261012/native-page-observations.json`。

## 2026-10-12 本机求职倾向回查与筛岗纠偏

- 用户要求按本机已有求职倾向校准。实际读取 `worklog-private/03-个人/求职材料/简历-2026-08/README.md`、`职业发展/职业现状与下一阶段方向综合分析.md`（讨论日期 2026-08-10）、`90天跳槽决策与执行总结.md`，并对照 01/03/04 方向简历和经历底稿。
- 当前主定位：产品 / 内部平台型 Tech Lead，以企业软件架构、工程治理和 AI 工程化为能力组合。主目标为产品 Tech Lead/内部平台负责人；桥接为产品型公司的后端负责人/企业应用架构；探索研发效能、Developer Platform、AI 工程系统/Agent Harness。综合分析中的参考比例为 50% / 35% / 15%；AI 是差异化与长期增量，不是唯一身份。
- 明确降低或排除：客户交付技术负责人、实施、驻场、售前售后、直接长期承接客户问题、职责混合客户沟通/实施/开发/线上兜底的岗位；不退回普通高级 Java 开发。筛选要看产品生命周期、内部服务对象、需求治理、长期演进和权责边界，不能只看技术栈或 Tech Lead 标题。
- 旧 90 天文档的正式跳槽参考为上海、月薪约 4w、ToB/SaaS/平台型 200–800 人公司；本轮按用户最新的小公司面试验证范围，保留职业方向及组织边界，不擅自扩大发送数量或把旧时间窗口重新启动。
- 回查还确认：始祖鸟品牌线从 2019 年开始，个人参与明确从 2021.03 开始；运动中心底稿记载 2022–至今、Tech Lead/平台架构设计与核心模块开发。`作品集-AI开源项目.md` 已记录个人 Harness/开发者工具/评估治理项目，因此此前证据池“AI经验不足”的结果只反映已导入材料不全，不能作为本人无相关经验的结论。
- 本轮前置只读探索已新增 Java/企业应用等线索，尚无平台写入。MES 技术主管完整 JD 明示“排除零售，不要 ERP/OA”且偏客户交付，移出本轮优先候选；机械结构研发经理不属于软件方向；普通 Java 开发不作为主投。原始线索保留，后续按上述方向重筛。

## 2026-10-12 EC+ 任职开始时间确认

- 用户再次明确确认：EC+ 任职从 **2021-03** 开始。已核对 `personal_profile.yaml` 中 `work_ecplus.start=2021-03`、`current=true`，职业档案仍为已确认状态；此入职年月无需再次向用户核实。
- 冲突位于项目证据 `ec_32567922`：`time_range` 和 `context` 均写“2019 年至今”。任职时间确认不等于确认具体项目从 2021-03 开始，不能直接用入职月覆盖未知项目日期；该项目早期日期仍属待核对信息。本轮记录确认事实，保留档案原有确认状态。

## 2026-10-12 P0-026 证据约束的语义匹配接通与四岗验证

- 授权与复用：用户同意以语义匹配为岗位判断主线。复用已配置的本机 Qwen、LLMClient、Quick Run 的匹配→生成→评测、独立 trace 与既有结果区；Agent 简化循环本轮不迁移。规范及短设计见核心规范和 `AIEF/docs/plans/2026-10-12-evidence-semantic-matching.md`。
- 实施：全部合格卡按大小分批评审，取消 Quick Run LLM 的关键词前 N 张截断；逐卡相关度后汇总逐项 JD 的支持/部分支持/证据不足/冲突，绑定事实 ID、原文、全部输入指纹与模型版本。JSON/引用无效每请求最多纠错一次，再错则失败；网络超时不自动重试。缓存只存校验通过结果，源资料变化失效；生成阶段再次核对实际传入证据和档案，失效语义结果不能降级为旧解释模型成功。
- 生成与评测：引用卡优先进入三项代表项目，已引用原行动/结果优先进入正文；保持原字段拼装，不改写事实。区分证据池支持与简历是否呈现，语义适配、简历覆盖、表达质量和事实完整性分开；关键词保留辅助。生成与评测复用语义结果，不重复调用模型。语义源原文及缓存已加入 Git 忽略。
- GUI：默认语义模式，规则模式可显式选择；右侧展示独立指标、逐项状态、理由和可展开原文。真实页面发现原 `listEvidence()` 只取第一页，导致 51 张可用卡仅显示 17 张；已按游标读取全部，结果摘要显示数量而非 51 个内部编号。DESIGN、`.pen`、RPC、类型与中英词条同步。
- 验证：最终单元与验收 1177 通过、1 跳过、18 subtests 通过；TypeScript、Vite、离线 Tauri 调试包构建、架构与路线图检查通过。独立审查发现的换输入复用、缓存指纹、空白规范化与严格降级问题均已先红后绿修复。开发工具、模型、全局配置及依赖版本未变。
- 真实 Qwen：四个现有画像都评审 51/51 张卡并完成生成。最终结果（岗位适配 / 简历覆盖 / 表达质量）：Tech Lead JAVA+AI **50 / 50 / 73**；高级全栈 **60 / 55 / 73**；CTO/Tech Leader **42 / 42 / 75**；AI 全栈 **62 / 62 / 73**。这些是要求支持度，不是录用概率，不能与旧规则分数直接比较。四份仍 `NEEDS_EVIDENCE`、`quality_passed=false`、`deliverable=false`，未把语义判断变成无依据的个人事实。
- 成本与异常：首版未限制输出时首岗 600 秒超时；压缩重复字段并限制响应条数/长度后，前两岗首次完整评审约 269 / 271 秒。第三岗原文引用失败后复用缓存，272 秒完成（13 次模型调用、1 次缓存、3 个请求各纠错一次）；第四岗汇总二次失败时保持阻断，细化具体事实 ID 诊断后 26 秒完成（2 调用、10 缓存）。最终四岗复测共 **44 次缓存命中、0 次模型调用**，每岗完整本地管线约 0.5 秒；首次成功记录及失败运行均保留。
- 原生页面：使用仓库内调试 App、真实本机数据，由外部 native accessibility 自动化点击进入 Quick Run、选材料、启动，读回 DONE、51 张已评审与待补证据；展开要求核对原文及来源，截图目视确认长文本换行和折叠列表。首岗原生复跑 11 次缓存/0 模型调用。此证明语义生成切片，不代表 P0-026 的高匹配实投和面试反馈闭环完成。
- 最终原生读回：调试包更新后再跑 AI 全栈，`qr_20261012084852309167` DONE、11 缓存/0 模型调用，页面显示 62 / 62 / 73 与待补证据；展开“根因分析”要求，`回滚/降级策略及 Bug 复盘`、`ec_32567922.actions` 显示“已在简历呈现”，引用驱动排序已在真实页面验证。观察追加在同一原生记录的 `final_verification`。
- 证据：`outputs/acceptance/p0-026-semantic-20261012/validation.json`、`native-page-observations.json`、`first_successes/` 及逐岗记录。最终四岗运行 `qr_20261012084425353808` / `qr_20261012084425854751` / `qr_20261012084426354144` / `qr_20261012084426861673`。真实档案、证据卡、审批队列与历史回执未改，平台写入 0。
- 后续：按语义缺口核对本人职责/项目年月、职业时间冲突及岗位实际要求；模型结论仍供人工复核，引用存在不证明语义推断必然正确。P0-026 保持唯一 `next`。

## 2026-10-12 P0-026 评分口径修复与四岗规则复测

- 探索：实际 Quick Run 经过 `run_evaluation`，原实现把 `must_have` 整句与关键词混算、用数字/关键词冒充引用；Agent 使用另一简化 evaluator。本轮复用原 CLI、独立 `read_generation_trace`、App Quick Run handler 及现有门禁，共享词面覆盖函数，不新增投递链路。
- 实施：关键词去空/去重，英文完整词边界兼容 `HTTP+json`，排除求职意向标签/章节；完整硬性条件独立展示待核对与词面线索，不自动断言学历/年限/能力符合。Quick Run 引用分改为有效独立 trace 下完整 bullet 的个人资料/证据字段覆盖，失效输入不能得引用分。JSON 与 Markdown 同步明细；原权重、78 分参考线及审批门禁保持。Agent 本轮仅同步关键词覆盖，既有简化评测通过不能等同完整简历达标。
- 真实数据复现：`日立上线安排` 卡的 `role_scope` 为字符串 `[]`，此前会生成“角色：[]”且未列缺项。生成读取现在把 `[]` / `{}` / `null` / `None` 当缺本人职责，不修改源卡或确认过的职业档案。
- 先红后绿：13 项评测回归及 4 项职责空值回归；独立审查发现并修复加号词边界、Markdown 求职意向与 Agent 空关键词中性分三项问题。最终 `tests/unit + tests/acceptance`：1158 通过、1 跳过、18 subtests 通过；v2 架构和路线图检查通过。
- 真实本地复测：现有 App `handle_quick_start` 对四个已审核画像、51 张可用卡运行规则模式（LLM 调用 0），均 DONE 并生成新 A/B、PDF、Scorecard；不是本地 Qwen 重跑，也不是外部真实页面深度验收，分数不与此前 LLM 结果直接作效果对比。Tech Lead JAVA+AI 匹配/评估 53/52，高级全栈 60/54，CTO/Tech Leader 59/55，AI 全栈 53/52；四份独立追溯有效、bullet 引用均 28/28，但均 `NEEDS_EVIDENCE`、`quality_passed=false`、`deliverable=false`。
- 剩余缺口：规则排序四岗仍反复选中相同三张卡；`iss模块代码审查` 缺本人职责及项目时间；`日立上线安排` 无本人职责、日期来自多人上线安排且不满足明确年月任期；`亚玛芬运动品牌数字化建设` 写“2019–至今”，与已确认 EC+ 任职从 2021-03 开始的资料需核对。已阅读对应来源，文件创建日期和他人任务不能代填本人经历，已向用户询问确切事实。岗位硬性条件仍有 8 / 10 / 6 / 4 项待核对；既有分组能力会抑制独立技术栈展示，尚未改动生成选材和模板。
- 证据：`outputs/acceptance/p0-026-quality-20261012-final/validation.json`；新运行 `qr_20261012073328431222` / `qr_20261012073328919865` / `qr_20261012073329393331` / `qr_20261012073329863014`。确认档案、原审批队列及历史回执指纹未变；平台写入 0。P0-026 保持唯一 `next`，尚未完成高匹配实投或面试反馈验收。

## 2026-10-12 证据卡自动关联工作经历（P0-026 续）

- 决策：用户同意由 App 自动决定投递候选（走既有门禁，不再人工挑选），并批准开工“证据卡自动关联工作经历”。
- 规范：核心规范“材料对账与批量整理契约”新增自动关联条目。
- 代码：`tools/infra/career_profile.py` 新增公司别名、三信号关联建议与可用卡读取；`profile.autoLinkEvidence`（预览 / 写入，写入需 `expected_revision`）；职业档案编辑器“自动关联证据”按钮；`evidence_ids` 上限 30 → 200。测试：`tests/unit/infra/test_career_autolink.py`、`tests/unit/sidecar/test_profile_autolink.py`、`tests/unit/gui/test_career_autolink_ui.py`。
- 数据：对真实档案预览后写入：44 张可用卡全部给出唯一建议（一里智辉 EC+ 32、众安 6、九恒星 6；43 张靠材料标签命中公司别名、1 张靠同源材料继承），0 张无法判定；写入后四段工作分别关联 36 / 7 / 7 / 1 张，档案缺项 0，`career_status.reviewed` 变为 false，待用户在简历中心重新确认后 Quick Run 的职业档案一致性检查才会通过。
- App 自主挑选候选（用户决定不再人工挑选）：按智能运行页同样参数（引导批次、无真实发送、每画像最多 2 候选）对 4 个画像运行 App 门禁，规则引擎匹配 0.50 / 0.63 / 0.63 / 0.50、评估 0.53 / 0.58 / 0.56 / 0.53，4/4 通过阈值 0.3，各生成 1 条待审批候选（队列 ar_20261012051320*）；真实发送仍须用户在智能运行页批准并选择路线（猎头 `/a/` 三岗只能走平台默认简历，AI 全栈可走生成 PDF），且职业档案需先重新确认。
- 用户授权助手代为操作后：职业档案已按授权经 `profile.review` 重新确认（2026-10-12T06:34Z，缺项 0）。平台默认简历路线的“准备 + 批准发送”被执行环境的权限分类器拦截（涉及对招聘平台的真实写操作），助手未绕过；该步骤回到 App 智能运行页由用户点击完成（准备平台默认简历 → 批准）。开发实例已重启加载新 sidecar。

## 2026-10-12 材料对账与批量整理首片（P0-026 续）：把本机工作日志喂给 App

- 决策：用户指出本机已有充分资料，要求 App 具备核对、分析、整合材料的能力，并同意先由助手初步整理喂入 App。
- 探索结论：`~/workspace/worklog-private` 按公司/项目/模块组织（EC+ 6620 篇、众安 116 篇、九恒星 220 篇、求职材料 29 篇），其中 `00-EC+/00-overview/工作汇总/项目目录/<品牌>/<模块>/{5 分钟速读卡,业务地图,架构切片}.md` 正是 2021–2026 证据最薄年段的结构化汇总；9 张旧卡 ec-2026-011~019 有附件但无来源材料与状态，无法按现行守卫入池。
- 规范：核心规范新增“材料对账与批量整理契约（2026-10-12）”。
- 代码：`evidence.reconcile` 只读对账接口（可追溯性、来源建议、最接近原句、缺项、日期线索、疑似重复）+ 证据页“材料对账”折叠区；测试 `tests/unit/sidecar/test_evidence_reconcile.py`、`tests/unit/gui/test_evidence_reconcile_ui.py`。
- 数据：四份精选目录材料经 `material.upload` 导入（EC+ 工作汇总 246 篇 / EC+ 专题 90 篇 / 众安 33 篇 / 九恒星 76 篇；排除含密码字样与超长文档），副本归档于 `~/backup-manifest/pi-proof-forge/material-bundles-20261012/`；对 60 篇精选文档逐篇走 `generateDraft → saveDraft(eligible)`，审核人标注 `experiment_batch_2026-10-12`。
- 提炼结果：首轮 60 篇 → 21 张直接入池、26 张因模型改写原文被守卫降为待补、13 篇模型输出缺字段；修复轮用对账的“最接近原句”（相似度 ≥ 0.7）替换后 21 张待补卡重新入池、5 张仍待补，13 篇重试得 3 张入池、3 张待补、7 篇仍失败。对账终态：85 张卡中可用 51（此前 8）、待补 10、未入池旧卡 24（9 张 2026 手写卡 + 15 张 5 月 demo/qr 卡，后者互为疑似重复）；可用卡中 41 张缺时间、44 张缺本人角色（文档未明示，不编造；对账给出年月线索供用户确认），部分标题被模型译成英文，已在提示词要求保持文档原语言。
- 管线修复：51 张卡整池提示词使本地模型匹配阶段 600 秒超时（qr_20261012042910796448 FAILED/matching-scoring），匹配阶段加入规则预筛 `--llm-max-cards`（默认 12），规则报告仍用全部卡。对比（高级全栈 jp_e43441bd，同一 JD）：匹配 50 → 63，评估 34 → 45，量化占比 18% → 38%，证据引用 18% → 41%，must-have 覆盖 0% → 8%，全程 15 分钟（匹配 8 分钟）；模型选卡为跨品牌微服务架构卡、MongoDB 改造卡与 AI 编程工具编排卡。仍 `deliverable=false`，新的阻塞是本批新卡尚未关联到已确认职业档案的工作经历（readiness 报“需关联唯一的工作或合作经历 / 证据版本与已确认职业档案不一致”）与 `ec_80a0e672` 缺本人角色，需用户在简历中心关联并确认。
- 设置变更：无。

## 2026-10-12 小公司高匹配投递实验首片（P0-026）：公司事实透传、猎头岗位与自由格式 JD、超时下发

- 决策：用户确定 BOSS / 智联 / 51job / 脉脉 / 拉勾因无官方可操作 API 或 CLI 暂不接入，先深化 App 能力；投递实验改用“JD 高匹配 + 微小公司”的猎聘岗位磨练面试（现阶段以微小公司为主，大公司为后续目标）。矩阵新增 `small_company_high_match_delivery`（order 27）为唯一 `next`，`maimai_source_integration` 回到 `not_started`。
- 探索结论：官方搜索接口每条岗位已返回 `companySize` / `financingStage` / `industry` / `workYears` / `education`，原 handler 全部丢弃；详情读取只认 `/job/<id>.shtml`（猎头岗位在 `/a/<id>.shtml`，页面结构相同），且完整性判定要求同时出现中文“职责 / 要求”标题，真实 JD（“工作内容 / 我们期待你 / Job Responsibilities”）全部被判为“正文暂不可用”。
- 规范：核心规范新增“小公司高匹配投递实验契约（2026-10-12）”节：公司事实透传与 `company_size_max` 筛选语义、猎头路径同身份规则、完整性判定修订（无截断提示且 ≥ 200 字即完整，短正文仍须两类章节）。
- 代码：`jobs.py` 透传五个公司事实到线索/画像并支持规模筛选、关键词兼容地区；`liepin_job_detail.py` 接受 `/a/`、放宽 `_complete_body`、把 `safe.liepin.com` 人机验证分发页的 302 如实报告为 `SECURITY_CHALLENGE`（不跟随、不绕过）；`job_lead_binding.py` 与 `platform_feedback.py` 的岗位身份/ID 正则同步接受 `/a/`；Jobs 页线索行显示规模·融资阶段、筛选区新增公司规模下拉（100 / 500 人以下）、线索详情与画像侧栏带规模。
- 管线修复：Quick Run 匹配阶段失败（报告文件不存在）时结果解析抛 `KeyError: gap_tasks` 并把错误伪装成 `Unknown method`，现改为返回失败步骤与空缺口；系统设置的 LLM 超时此前从未下发到管线（五处硬编码 120 秒），现经 `LLM_TIMEOUT` 环境变量统一注入，本地 27B 模型的匹配阶段 120 秒必超时是本次真实运行失败的直接原因。
- 真实数据（App 自有 handler，只读）：10 组关键词 × 2 页检索新增 243 条线索；上海 · 100 人以下 14 条、500 人以下 32 条；入围 7 条中 4 条取得完整 JD（Tech Lead JAVA+AI 50-99 人、高级全栈 1-49 人、CTO/Tech Leader 1-49 人、AI 全栈 50-99 人），由本地 Qwen 解析并以实验授权审核保存为完整画像 `jp_65caa1fc` / `jp_e43441bd` / `jp_19a03f9c` / `jp_a6ea6776`（解析出的必备项随实验日志留档）；其余因平台对脚本 UA 的人机验证拦截保持阻断。已知限制：官方搜索无城市参数，线索地区多为区名（浦东新区等），“上海”关键词会漏掉这些行；猎头 `/a/` 岗位的生成 PDF 沟通路线仍显式阻断，待真实验证。
- 设置变更：经 App 自有 `settings.update` 把 LLM 超时 120 → 600 秒（原 `policy.local.yaml` 已备份到会话 scratchpad）。
- 验证：tests/unit + tests/acceptance 全量（1131 通过）、`tools/check_execution_roadmap.py`、tsc、`pnpm --dir ui build` 通过。
- Quick Run 真实结果（本地 qwen3.8-27b，匹配 + 生成 + 评估均走 LLM，每次 12～17 分钟）：Tech Lead JAVA+AI 匹配 33 / 评估 33；高级全栈 50 / 34；CTO/Tech Leader 32 / 38；AI 全栈 44 / 34；四份均 `deliverable=false`（参考线 78）。LLM 选卡在 8 张可用卡中按岗位切换（MongoDB 改造恒选，全栈岗加入租赁状态机与影展验收，Java 岗加入用友 NC 与伊尔普），项目经历固定取前 3 张；评估卡 must-have 覆盖率四份均为 0%（按 JD 必备项整句匹配，度量失真），量化占比 18%、证据引用 18%。两次 `NEEDS_EVIDENCE` 均指向 `ec_0f6287d2` 缺 `role_scope` / `time_range`（另有 `ec_4b0f457a`、`ec_9a1244c4` 同样缺失）。质量结论与改进计划见会话汇报，后续按 P0-026 推进。

## 2026-10-11 P0-022 脉脉来源导入首片：人工导入来源契约与手动投递记录

- 探索结论：粘贴 JD 加可选来源链接的人工导入链路已存在，但完整保存时后端会对来源链接发 GET 校验可达性，与脉脉 / 拉勾协议禁止脚本访问冲突；没有平台识别、人工导入标记、来源时间与手动投递记录。
- 规范：核心规范新增“人工导入来源契约”节（域名识别平台、人工平台不做 GET、`import_mode` / `platform` / `source_recorded_at`、仅链接不算完整 JD、来源覆盖与在线 / 投递能力分开、手动投递记录契约）。
- 后端（先红后绿）：`jobs.py` 新增 `platform_from_url` 与 `MANUAL_IMPORT_PLATFORMS`，保存时对人工平台记 `manual_platform_not_checked`，画像 / 线索写入与列表输出新字段；`submission.py` 新增 `handle_submission_record_manual`（`submission.recordManual`），手动记录不可重试、详情回执来源为 `manual_tracking`。新增单测 4 + 2 项；tests/unit（非 GUI）全部通过。
- 前端：类型与词条（平台中文名、人工导入、手动投递表单、`manual_recorded` 状态、`manual_record` 步骤）；岗位页画像卡 / 详情 / 线索行标明“人工导入 · 平台”，画像详情新增“记录一次手动投递”折叠表单；投递页通道显示平台中文名。tsc、tests/unit/gui 74 项通过。
- 验收：新增 L1 场景脚本 `tests/acceptance/test_scenario_maimai_source_import.py`，契约与场景用例目录加入 `maimai_source_integration`（契约用例数 11），矩阵登记证据，tests/acceptance 97 项通过。深度验收待用户提供真实脉脉链接与完整 JD。

## 2026-10-11 GUI 空工作区首次启动走查（UX 第七批）

- 用户同意先做空工作区走查再回主线。打包版复制到隔离目录并清空资源目录内的数据后直接运行，桌面控制逐页截图。
- 发现并修复：总览“选择一个模型”误判为已完成（后端未配置时也返回默认 openai/gpt-4，前端改按密钥是否保存过判定，并直达设置页模型分组，设置页支持 `?section=llm`）；证据卡无材料时仍显示整套提炼控件（改为一句提示加“去简历中心上传材料”，经壳层 `pipf:navigate` 事件跳转）；三处旧导航名文案（岗位页空态、每日投递空态、职业档案关联说明）。
- 验证：tests/unit/gui 74 项、tsc 通过（总览清单测试改为按密钥判定并断言直达模型分组；设置页测试补路由 mock）。重新打包后用空副本原生复核：总览四步全部待完成、主按钮“配置模型”直达设置页模型分组并显示未配置；证据卡无材料时只剩提示与“去简历中心上传材料”，点击跳到简历中心。复核后结束副本进程，用户开发实例未受影响。

## 2026-10-11 GUI 原生窗口读回（打包版）与两处 WebKit 修复

- 用户回到电脑旁授予桌面控制后，启动含第三至六批改动的打包版，用后台窗口控制逐页截图并操作标签、折叠、只读/编辑切换、分组切换，九页与设计一致，细节见 DESIGN.md 同名章节。
- 修复：每日投递卡“更多操作”弹层在 WebKit 下逐字换行（容器加 `w-max whitespace-nowrap`）；职业档案吸底栏的待补内容清单改为一行计数折叠。tsc、tests/unit/gui 74 项通过；重新打包后原生复核两处均正常。
- 结束后 AppleScript 退出打包版实例并释放桌面控制；用户自己的 `tauri dev` 实例全程未受影响。`.pen` 仍待用户在 VS Code 保存后单独提交。

## 2026-10-11 窗口尺寸与位置记忆（UX 第六批）

- 按用户“那继续”推进剩余项中需要一个项目级依赖的窗口状态记忆：Cargo 加入 `tauri-plugin-window-state = "=2.4.1"` 并在 `main.rs` 注册。首次用 `"2"` 解析到 2.5.0，要求 tauri ≥2.12，`tauri build` 以 npm 包 2.10.1 与 crate 2.12.3 版本不匹配报错；还原锁文件并固定 2.4.1 后通过，tauri 保持 2.10.3，锁文件新增 32 个插件依赖、6 个移除、12 个过渡升级。
- 验证：打包成功；启动打包版 14 秒后用 AppleScript 请求退出，应用数据目录写出 `.window-state.json`（主窗口 2880×1800 物理像素、坐标 288/112、未最大化）。恢复为插件标准行为，未做可视化核对。`cargo test` 19 项通过。
- 设计同步：DESIGN.md 的“桌面窗口与响应式规则”补一条，并追加第六批章节；`.pen` 无结构变化，不改。

## 2026-10-11 GUI 全局长任务指示（UX 第五批）

- 用户不便操作电脑、桌面控制授权两次被自动拒绝，原生视觉读回继续搁置；按用户“继续”的指示，做不需要授权也不加依赖的全局长任务指示。
- 实施：新增 `ui/src/state/task-store.ts`（zustand）；快速运行页启动时登记任务，结束时结果与通知始终写入全局 store，本页状态按版本守卫更新；回到页面恢复运行中 / 读回同目标结果 / 显示失败原因，并阻止重复启动；SideNav 底部显示进行中任务并可点回页面。词条 `shell.taskRunning` / `shell.taskOpen`。
- 验证：新增 `tests/unit/gui/test_task_store.py`，`test_quick_run_inputs_ui.py` 补 store mock；tests/unit/gui 74 项、tsc、vite build 通过。内置浏览器用只读桥接（`run.quick.start` 延迟 8 秒后拒绝）走通启动 → 切页看指示 → 回页为运行中 → 结束后指示消失且弹出失败通知 → 页面回到可运行态。发现并修复一处：页面卸载会递增版本守卫，原实现会把切页后到达的结果整体丢弃。
- 设计同步：DESIGN.md 追加第五批章节；`.pen` 新增约束卡（与第三、四批一起待用户保存后提交）。

## 2026-10-11 GUI 二级及更深层页面优化（UX 第四批）

- 起因：一级页面收口后，用户要求分析二级到四级页面并直接处理。分析用只读桥接逐层展开真实页面并量化：证据详情栏 1714px、画像详情 1134px、投递详情 1620px、职业档案编辑器 2991px（右栏可视 770px）；长说明文案 ≥40 字共 20 条；全站 Tailwind 透明度修饰符对 `var()` 颜色静默失效（策略 / 设置分组导航高亮缺失）。
- 实施：颜色 token 改为 RGB 通道 + `<alpha-value>`；i18n 新增 `codes.*` 字典（34 个步骤名、浏览器通道、来源、模式、平台）；证据详情栏改只读视图 + 编辑切换，技术信息与导入附件折叠，材料来源去重复卡并加步骤提示，文档预览去 YAML 头；画像详情只读 / 编辑切换，JD 解析成为新建主路径，猎聘搜索折叠，线索主按钮按状态；投递详情步骤名中文化、回执 JSON 折叠、标题改公司·岗位、ID 进技术详情、反馈下拉去 ID、边界说明压短可展开、旧通道会话与 Check Mode 合并为折叠的“高级与演练工具”；每日投递卡按状态重排、授权设置与历史折叠、单一主按钮与“更多操作”、勾选句压短并保留完整条款；职业档案条目折叠为一行摘要、操作栏吸底；自主运行无运行时显示空态；快速运行未运行时隐藏评分条。
- 先红后绿：新增 `tests/unit/gui/test_evidence_detail_view_mode_ui.py`；`test_evidence_rereview_ui.py` 断言改为“保存按钮可不存在，存在必禁用”，守护的不变量不变。tests/unit/gui 73 项通过，tsc、vite build 通过。
- 读回：内置浏览器 1440×900 逐层核对证据 / 岗位 / 投递 / 智能运行 / 简历 / 快速运行 / 策略页的深层区块，结果见 DESIGN.md 第四批“验证”；原生窗口未读回。注意浏览器面板在后台时 CSS 过渡会冻结，核对高亮要看 class 而不是 computed style。
- 设计同步：DESIGN.md 追加“UX 第四批”章节；`.pen` Implementation Constraints 新增约束卡 `wzkfN`（需用户在 VS Code 保存）。
- 提交与打包：第三、四批代码与文档已提交为 30689a9（`.pen` 待保存后另提）。`tauri build --bundles app` 打包成功（19:23），`ui/scripts/verify_packaged_app.py` 冒烟校验通过（握手 1.0.0、sidecar 0.1.0、ping ready）。原生窗口视觉读回未做：用户拒绝了本会话的桌面控制权限，打包版实例未启动；打包产物在 `ui/src-tauri/target/release/bundle/macos/PiProofForge.app`，可由用户自行打开核对。

## 2026-10-11 GUI 一级页面布局与引导优化（UX 第三批）

- 起因：用户要求从 App 定位与桌面端特点分析一级页面的一屏显示（固定/滚动划分）、操作引导与首次使用友好度，补充约束“不能元素堆砌、页面繁杂”，随后决定先处理分析出的问题。分析用源码审计加内置浏览器只读桥接真实数据截图（方法沿用本机记忆）；量化结果：简历中心 4748px、岗位中心 3659px、投递记录 3301px，证据/岗位/投递三页首屏均看不到主对象。
- 实施：全局样式新增 `.page-header`（吸顶实色页头）、`.page-icon-button`、`.stat-strip`、`.fold-section`、`.seg-tabs`；九页页头统一为标题 + 副标题 + ≤2 操作 + 图标刷新；证据/岗位/投递统计卡改一行统计条；证据筛选并入列表卡、材料来源折叠（无证据时展开）；岗位新建画像与 JD 解析合并为状态化折叠区块并在区块内加“创建画像”；简历中心职业档案按确认状态折叠、材料列表限高；快速运行与智能运行的模型摘要一行化、下拉下沉到运行输入；智能运行与投递记录改为页内任务标签（深链进入对应标签，非活动标签保持挂载）；投递表格去掉原始 JSON 副行，SHA256 改 12 位指纹加 tooltip；总览新增状态驱动的“开始前的几件事”清单与动态主按钮；AppShell 加 ⌘1…9 / ⌘R / ⌘S，`html lang` 跟随语言；导航名与页面标题按术语表收平，九页副标题改为用户语言，侧栏底部改“本地服务”。
- 先红后绿：新增 `tests/unit/gui/test_overview_setup_checklist_ui.py`（缺项列出四步并把主按钮指向第一个缺项、全部就绪隐藏清单、部分就绪标记已完成）；tests/unit/gui 72 项通过，tsc、vite build 通过。页面的刷新事件监听带 `window.addEventListener` 守卫，兼容既有 vm 测试 harness。
- 读回：内置浏览器 1440×900 九页首屏与滚动后页头吸顶、折叠默认态、`?quick_run_id` / `?run_id` 深链进入对应标签、合成 ⌘R 触发 `pipf:refresh`、⌘3 切到证据页、1280×800 无横向滚动。未做 Tauri 原生读回。
- 设计同步：`ui/design/DESIGN.md` 追加“UX 第三批”章节；`.pen` 经 Pencil 新增 Layout/PageHeader、StatStrip、SegTabs、FoldSection、Overview/SetupChecklist 组件（`urdhh`、`a38v5l` 两行，Design System 顶边上移至 -1060）、约束卡 `qxXC8`，Screen/Submissions 与 Screen/Agent Run 页头加标签实例、`subStats` 改统计条实例；`.pen` 需用户在 VS Code 保存后才落盘。
- 范围内未做：二级及更深层页面（证据详情、画像详情、PDF 投递流程卡内部、每日投递卡内部、设置分组）的分析与优化；窗口尺寸记忆、跟随系统外观、全局长任务指示。代码未提交，待用户确认。

## 2026-10-11 P0-025 验收证据整理并收口：三次真实同步留档挂入矩阵，按用户决定标为 deep_verified

- 汇总 `outputs/acceptance/liepin-feedback-sync-20261011/validation.json`：两次留档运行（首次、第三次）的行数/匹配/状态计数与页面状态计数、第二次运行的台账说明；当前只读读回（overview.get 漏斗 delivered 2 / viewed 8 / rejected 4 / unknown 2 / unsynced 0，submission.list 16 笔带平台进展，16 个 platform_feedback.json 各 3 条历史，22 个回执与日志文件修改时间均早于首次同步、0 个被改动）；只读边界（两段页面脚本无点击/提交/请求，唯一 location.href 为观察回传；Rust 本地命令校验、操作互斥、会话须 authenticated、域名白名单；后端脱敏限长与只追加）；五项 covers 逐条对应证据与限制。
- 矩阵 `liepin_feedback_sync` 挂上 5 份证据，脚本表述改为“三次真实只读同步 16/16 匹配已留档，待用户决定收口”，状态仍为唯一 next、深度仍 deep_required；路线图 Current Focus 同步。矩阵与路线图检查通过。
- 未做并如实记录：外部自动化触发的同步（调试进程对桌面控制不可见、打包版工作区无真实数据）、closed 映射后的再次同步、切片 3 沟通页回复读取。本会话无平台写入。
- 收口：用户决定“可以收口”，`liepin_feedback_sync` 标为 `deep_verified`（depth: deep），validation.json 记录用户决定与保留的限制；按既定顺序 P0-022 `maimai_source_integration` 恢复为唯一 next，矩阵 current_focus 与路线图 Current Focus 同步。切片 3 是否立项待用户决定。

## 2026-10-11 P0-025 切片 2 收尾：总览投递进展卡片

- 前端消费后端已有的 `overview.get.metrics.feedback_funnel`：总览右栏在匹配趋势与缺口待办之间新增“投递进展”卡，显示已同步/总数、按状态分段的部分-整体条（零值不画段）与 8 个状态行（图标 + 文字 + 计数，零值弱化），无受控投递时显示空态，入口直达投递记录。类型补 `OverviewFeedbackFunnel`，中英文词条补齐。按 dataviz 规范校验状态色：accent 与 accent-cyan 相邻不可辨（ΔE 6.7），故相邻阶段改用同色深浅并以图标和文字做辅助编码。
- 先红后绿：新增 `tests/unit/gui/test_overview_feedback_funnel_ui.py`（分段顺序与宽度、计数行、入口导航、空态）；tests/unit/gui 69 项通过，tsc 通过。
- 设计同步：DESIGN.md Overview 右栏补 Delivery Funnel 节；`.pen` Screen/Overview 右栏插入 `ovFunnel`（`KJlps`），三张右栏卡改为内容高度，Overview 画布增高到 1200 并把其后 8 个画面下移 300。
- 范围内未做：沟通页招聘方回复的只读读取（切片 3）；`liepin_feedback_sync` 的外部真实 Tauri 页面验收证据仍待按矩阵 covers 整理。

## 2026-10-11 GUI 交互与布局优化第二批：投递记录页

- 投递页按主任务重排：统计 → PDF 投递 → 尝试记录与运行详情 → 反馈迭代 → 通道会话 → Check Mode 演练（默认收起）。PDF 投递卡新增 8 步步骤条，按阶段推导当前步骤并只把当前步骤按钮标为主按钮，按钮启用逻辑不变。清除会话与两处重试接入确认框，会话清除/重试排队/反馈记录接成功通知；刷新保留内容；会话路径、反馈路径与详情日志路径折叠为“技术详情”；运行详情 sticky 并按 wide 断点降宽。中英文词条补齐。
- 验证：tsc、tests/unit/gui 68 项通过；内置浏览器 1440×900 读回投递页首屏与滚动后布局正常。原生读回：`tauri dev` 的调试进程不带 bundle id，桌面控制工具找不到窗口；改为 `tauri build --bundles app` 打包后启动打包版实例（每日授权为 expired、无待核验项，启动不触发批次），用桌面控制逐页截图核对总览、简历中心、证据页（含删除确认框弹出与 Esc 关闭）、智能运行、投递页步骤条、策略配置、系统设置，全部与设计一致；核对后退出该实例。核对中发现并修复两处：切换页面时主内容区沿用上一页滚动位置（AppShell 按路由复位到顶部）；策略页“投递模式”下拉在 WebKit 下因半透明背景退回原生白色外观（改为实色背景）。
- 设计文档：`ui/design/DESIGN.md` 追加“UX 第二批”章节；`.pen` 的 Screen/Submissions 补步骤条行。

## 2026-10-11 GUI 交互与布局优化第一批：反馈层、二次确认、刷新保活、右栏吸顶

- 起因：用户要求从 UX/UI 角度分析页面交互与布局并直接开工。分析方法：三路源码审计加内置浏览器真实数据截图（本机桌面截图权限不可用，改用隔离目录的只读 RPC 桥接 + 第二个 Vite 实例，不改仓库文件；方法已记入本机记忆）。结论见同日对话：视觉统一但缺统一反馈层、保存后整页回 loading、流程型任务无步骤化、右栏固定宽度挤压主内容、页面按功能堆叠而非主任务优先。
- 实施（均为非结构性改动）：新增 `ui/src/lib/ui.ts`（zustand 反馈 store：notify/confirmAction/buttonClass）与 `ui/src/components/feedback/{ToastViewport,ConfirmDialog}.tsx`，挂在 AppShell；sidecar ready 时不再占页面顶部，常驻状态移到 SideNav 底部，异常才显示横幅。总览/简历/证据/岗位四页改为首次加载才显示占位，之后重载保留内容（修复简历中心基本资料保存会卸载职业档案编辑器、丢未保存草稿的问题，复现测试 `tests/unit/gui/test_resumes_refresh_keeps_career_editor.py`）。16 类破坏性操作接入确认框；各页保存/生成/转化接成功通知；快速运行去掉永远不可达的取消按钮、执行期间诚实标注四阶段进行中并列出启动阻塞原因；证据表格列宽/固定表头/键盘可达；证据、岗位、智能运行右栏 sticky 并新增 `wide:1366px` 断点降宽；每日受控投递卡移到页头之后并按层级分组按钮、禁用原因 title；策略/设置页重新加载前确认丢弃草稿、删除凭据二次确认；总览统计卡可点击、缺口深链、趋势 key 重复警告修复。
- 投递页（submissions/index.tsx）由并行会话负责：`text-danger` 修正与 a 标签改路由已由其提交；清除会话/重试的二次确认待本批提交后由其接入 `confirmAction`。
- 验证：tsc、vite build 通过；tests/unit/gui 68 项通过（含新增 `test_feedback_layer_ui.py` 与简历保活测试，8 个既有 GUI 测试补了 `@/lib/ui` mock）；内置浏览器以 1440×900 读回总览、证据、智能运行、快速运行、岗位、简历、系统设置页面并打开/取消一次删除确认框。未做：Tauri WebKit 原生页面读回。`.pen` 在用户连上 Pencil 后已同步：Design System 新增 Feedback/Toast（`fQ00F`）、Feedback/ConfirmDialog（`FQxJ2`，含 Button/Danger `YBWSR`），SideNav 底部新增 sidecar 状态区并改为内容高度，Agent Run 的 `daily18` 移到页头之后，Implementation Constraints 新增约束卡 `kFfw8`；画布布局检查无裁切。
- 设计文档：`ui/design/DESIGN.md` 追加“2026-10-11 交互与布局优化（UX 第一批）”章节。代码与测试已按用户要求提交为 02565da；`.pen`、DESIGN.md Pen ID 回写与本条更新随后单独提交。

## 2026-10-11 反馈回流首次真实同步：入口与匹配通过，状态词未进摘要已按真实结构修正

- 用户在 App 内点"同步投递反馈（只读）"。App 自行在用户中心发现"17我的投递"入口 https://c.liepin.com/job/record/apply，记录页读到 17 行，16 笔受控投递全部按岗位编号匹配（10 笔默认简历 API 路线与 6 笔 PDF 路线），剩余 1 行是用户在 App 之外投递的 Java 岗，保持未匹配。平台写入 0。首次运行留档：outputs/acceptance/liepin-feedback-sync-20261011/first-run-sync.json 与 first-run-latest.json。
- 发现两处缺陷：卡片摘要只取前 80 字，状态词不在其中，16 条全部 unknown；时间匹配把"50-70k"的薪资区间当成日期。按真实卡片结构修正：记录脚本改为回传卡片各行文本（最多 16 行）与页面标签词，按块分成多条观察响应规避 12KB 载荷限制；Rust 合并多块；后端从短行里按优先级推导状态词、从行里推导时间，裸"月-日"须满足月日范围，页面标签词写入同步日志供核对真实用词。先红后绿补 2 项单测，Rust 合并断言补充。
- tests/unit 与 tests/acceptance 全部通过，Rust 19 项通过，前端构建、v2 约束通过。App 重启后待用户再点一次同步核对真实状态词；此前写入的 unknown 与错误时间保留在历史中，最新状态会被新一次同步覆盖。
- 第二次真实同步（2026-10-11T06:42:33Z）：仍为 17 行、16 笔按岗位编号匹配，平台写入 0。页面标签词证实猎聘投递记录的状态只有"已投递、已查看、面试邀约、不合适"四种，与归一化集合一致；但卡片 9 行仅含岗位信息，状态与时间在更外层的行容器里，16 条仍为 unknown。脚本改为从岗位链接向上定位"含状态词且只含这一条岗位链接"的容器并回传最多 24 行，同时把页面上短状态元素的计数分布写入同步日志；后端状态短行上限放宽到 20 字，补 1 项同一行含状态与时间的单测。全量 1087 项通过、前端构建通过，提交后 App 重启，待第三次同步核对。
- 第三次真实同步（2026-10-11T07:00:57Z）通过：17 行、16 笔按岗位编号匹配，14 笔读到真实状态与投递时间：暂不合适 4、已查看 8、已投递 2，与页面状态计数"暂不合适×4 已查看×8 已投递×2"完全一致；另 2 笔页面显示"停止招聘"，本次归为 unknown。随后把"停止招聘/已下线/招聘结束/已关闭"单独归一化为 closed（建议调整岗位，优先级 medium），不与招聘方拒绝混同，漏斗与中英文案同步，补 1 项单测；全量 1088 项通过、前端构建通过。留档 third-run-sync.json 与 third-run-latest.json。平台写入 0。愿景第六段"投递反馈回流"首次有了真实数据。

## 2026-10-11 P0-025 猎聘投递反馈回流首片：只读同步已实现，待真实页面首次运行

- 用户决定先深化 App 与猎聘渠道并选择投递反馈回流。探索确认：官方 14 个工具没有投递进展查询（官网称进展经 App 消息与短信触达），反馈只能由 App 自有已登录会话只读读取页面；App 现有反馈迭代机制来源仅本地评测与手动记录；16 笔受控投递均可由线索文件取得岗位编号与链接。设计见 AIEF/docs/plans/2026-10-11-liepin-feedback-sync.md；矩阵新增 liepin_feedback_sync 为唯一 next，S7 脉脉回到 not_started，路线图同步。
- 后端：新模块 tools/sidecar/handlers/platform_feedback.py 提供 submission.feedback.syncPacket 与 submission.feedback.recordPlatformStatus：观察脱敏限长后按岗位编号匹配（无编号时公司+岗位唯一精确匹配），状态按关键词归一化为 delivered/viewed/interested/interview/rejected，其余保持 unknown；只追加各记录的 platform_feedback.json 历史与 liepin/platform_feedback_sync.json 同步日志，回执、日志、快照不变；找不到记录页记 records_page_not_found 与脱敏候选链接。反馈项新增 platform_delivery_status 来源与动作建议（不合适→调整岗位，已查看超 7 天→补证据），列表项带平台进展摘要，总览 metrics 增加 feedback_funnel。先红后绿 6 项单测。
- Rust 与脚本：sync_liepin_feedback 命令复用会话检查、导航白名单、观察回传与操作互斥，先在用户中心发现文本含"投递"的站内链接，再导航到白名单内的非首页链接读取记录；两段脚本只读 DOM，按岗位链接定位卡片提取状态词与时间，不点击任何控件；载荷受原信封 12KB/65KB 限制。新增 1 项 Rust 单测。
- 前端：投递页登录区新增"同步投递反馈（只读）"按钮、边界说明与同步摘要，列表状态列下显示平台进展徽标与时间；中英文案同步；界面契约与会话回归断言补充。
- 验证：tests/unit 与 tests/acceptance 共 1081 项通过、1 项可选跳过；Rust 19 项通过；前端构建、v2 约束、路线图检查、AIEF L3 通过。OpenSpec 与 DESIGN 已同步；画布 .pen 因 Pencil 应用未连接本次未同步，待补。
- 未完成：投递记录页的真实结构尚未观察，首次真实同步由用户在 App 内点击执行；匹配与状态映射按真实观察再收紧；总览漏斗视觉与沟通页回复读取留到后续切片。本轮无平台写入。App 重启以加载新后端与命令。

## 2026-10-11 平台官方渠道复核：BOSS/智联/51job 在线只读改人工导入，S7 脉脉成为唯一 next

- 用户在 P0-019 开工前要求先核查 BOSS 直聘官方接入渠道，随后扩展到智联与 51job。先探索仓库：BOSS 适配器 tools/infra/discovery/boss_agent_cli.py 为旧命令形态骨架，本机未安装社区 CLI；从固定提交核对了 2.0.0 的真实契约（全局 `--platform --json`、位置参数搜索、`detail <security_id> --job-id`、统一 JSON 信封、岗位对象无 URL）。用户曾同意装进项目 .venv 并先做离线切片，核查结果出来后改变决定；本轮没有安装、没有改代码。
- 核查结论：三家均无面向求职者或第三方 App 的官方 API/MCP/SDK。BOSS 仅企业 ATS 白名单、官方 AI 产品封闭、协议禁止第三方工具；智联 AI 版与职悟空封闭，内置浏览器未登录实测薪资打码且完整 JD 需登录；51job 仅企业 ehire，未登录搜索列表完整可见但详情页触发滑动验证，未继续。社区方案均为浏览器自动化或逆向接口，有协议与账号风险。详情与来源见接入方案 2026-10-11 节。
- 用户决定：三家在线只读改为人工导入链接与完整 JD，接着做脉脉、拉勾导入。矩阵 boss/zhilian/qiancheng 三条标为 blocked 并记录原因，maimai_source_integration 改为 next 且依赖改为已验收的 setup_job_target，lagou 依赖脉脉，S8 依赖与覆盖口径改为"猎聘在线只读已验收、其余三家人工样本计入来源覆盖"；路线图 Current Focus、平台批次表与共同完成标准同步。路线图检查与矩阵测试通过。
- 内置浏览器只做了未登录只读浏览，遇到验证页即停止，没有登录、没有绕过验证、没有平台写入。
- 同日按用户要求复核脉脉与拉勾：均无官方开发者平台或 API，拉勾 open.lagou.com 仅存根页且第三方核查确认无公开 API；未登录实测脉脉职位搜索直接跳登录页，拉勾搜索页直接触发滑动验证，均未继续；脉脉服务协议与拉勾用户协议都明文禁止爬虫、脚本、第三方工具或非正常访问并可封禁账号。对 S7 的含义已写入接入方案：链接与完整 JD 只能由用户粘贴，App 只做来源识别、人工导入标记、语法校验与完整性检查，不发起平台请求。矩阵与 next 不变。

## 2026-10-10 策略文件路径统一：本机配置不再写回仓库 policy.yaml

- 缘起：收口 P0-018 时发现 App 设置页于 9 月 28 日把本机 LM Studio 的 provider、base_url、超时、密钥占位写进了仓库跟踪的 policy.yaml。原因是 sidecar 在未设 PPF_POLICY_PATH 时固定读写 policy.yaml，Tauri 启动 sidecar 不设该变量；另有 native_pdf、agent、approved_delivery 共 5 处排除名单读取硬编码 policy.yaml，与 tools/README 要求的本机配置放 policy.local.yaml 不一致。
- 实现：tools/policy/exclusions.py 新增 resolve_policy_path，规则为环境变量 PPF_POLICY_PATH > 仓库根已存在的 policy.local.yaml > 仓库默认 policy.yaml；设置页读写、排除名单默认加载和投递前排除检查全部改走同一规则，没有新增配置层或合并逻辑；tools/README 同步说明。先红后绿新增 3 项单测（路径优先级、当前目录默认加载、设置页写入本地文件而仓库文件不变）；tests/unit 与 tests/acceptance 共 826 项通过、1 项可选跳过，v2 约束通过。
- 本机迁移：两份文件先备份到 ~/backup-manifest/pi-proof-forge/policy-20261010/ 并附回滚说明，再把 policy.yaml 当前内容写入 policy.local.yaml（模型 qwen/qwen3.8-27b、超时 120、密钥占位 lm-studio，不含真实密钥），policy.yaml 还原为仓库版本。真实 sidecar settings.get 读回本地配置与门禁策略通过；App 随后重启以加载新后端。

## 2026-10-10 平台附件对账：App 外被移除的附件可识别，移除给出明确原因

- 缘起：卓胜微旧记录点"移除此平台附件"两次被 attachment_removal_identity_unverified 拦下，根因是三份旧附件已在 App 外消失而本地仍显示"平台附件在"。先核对既有 pdf_inspection 记录、发送后绑定冻结规则和移除核验，确认缺口只是缺少对账状态与可读原因；没有新增接口、存储或移除流程。
- 后端：记录附件检查时对已冻结的发送绑定做只读对账，完整附件页观察（含卡片计数）中没有该 fileId/encryAttachmentId 则写 platform_attachment.state=missing_on_platform，再次找到恢复 present；缺少计数的观察不做任何平台结论。移除前核验在新鲜观察未找到附件时返回 attachment_missing_on_platform 而非一般身份未核验，不创建占位；绑定、回执、快照、成功状态不变。
- 前端：成功卡片在平台附件已不在时显示提示并禁用移除勾选与按钮；"检查已保存附件（不重传）"对成功记录保持可用且只读，用于刷新对账；错误码映射为可读文案；中英文案同步。
- 验证：先红后绿新增 2 项移除单测与 1 段界面回归断言；tests/unit 的 sidecar、gui、infra 共 712 项通过、1 项可选跳过；前端构建与 v2 约束通过；DESIGN 与 OpenSpec 已同步。真实页面验证待用户在 App 内对卓胜微记录点"检查已保存附件"，App 已重启以加载新后端。本轮无平台写入。

## 2026-10-10 新格式文件名真实上传通过，旧附件已在 App 外消失

- 用户在 App 投递记录页对候选 ar_20261010133457367833 执行"批准并上传此 PDF"（2026-10-10T13:56:03Z）。平台响应：auth-upload HTTP 200 / flag=1，存储路径 …/ZVYXg-DaQbOZPn7vreU2nQ.PDF，fileLength 587034 与本地 PDF 一致；save-attachment-resume flag=1；list-attachment-resume 返回 1 条，fileName "童双龙-艾诺-模拟-20261010.1"、originalExtension pdf、fileSize 587034；页面提示"上传成功"。结论：猎聘接受 24 个 UTF-16 单元的"姓名-公司-岗位-年月日.序号.PDF"文件名，存储路径保留大写 .PDF，页面显示为小写 .pdf。本地状态 uploaded_unverified，附件身份绑定待用户点"检查已保存附件"；未发送。
- 移除旧附件的步骤最终没有执行：用户两次点"移除此平台附件"均被 attachment_removal_identity_unverified 拦下，第二次观察时页面已打开 4 分多钟仍为 0 张附件卡片并出现上传控件；上传后平台附件列表只有本次新附件，说明卓胜微、上海皮赛、视涯三份旧附件已在 App 之外被移除。本地三条记录的 attachment_binding 已与平台不一致，App 目前没有平台附件对账机制。第一次拦截曾被误判为页面加载时序问题，现更正。
- 用户随后点"检查已保存附件（不重传）"（2026-10-10T14:04:54Z）：页面附件卡片 1 张且精确匹配新附件，平台记录 fileName "童双龙-艾诺-模拟-20261010.1"、pdf、587034、auditStatus 1；原字节下载 HTTP 200 / 587034 字节，SHA256 a1b9ebd5…27adf 与本地 PDF 一致；attachment_id 257c822f85W328d953e97a8 已绑定，候选进入 attachment_verified。此结果也证明卡片选择器仍有效，之前 0 张是平台真实为空。候选保持未发送。
- 证据：outputs/acceptance/pdf-filename-20261010/validation.json，取代 10 月 8 日记录中"新命名的真实平台上传尚未验证"。本轮平台写入：上传 1 次，发送 0，删除 0。

## 2026-10-10 新格式文件名的真实上传测试：候选已备好，平台步骤待用户在 App 内点击

- 用户核对后确认：此前 6 次真实上传的附件名全部是旧格式 cv_<指纹前16位>.pdf，10 月 8 日定下的"姓名-公司-岗位-年月日.序号.PDF"尚未在猎聘实际上传过；用户回复"试试呗"要求实测。本会话没有桌面自动化工具，无法驱动 Tauri 壳点击上传，因此只完成 App 后端可做的准备，没有任何平台写入。
- 复用 10 月 7 日导入的官方线索，选择杭州艾诺半导体有限公司"模拟芯片设计工程师"（50-80k，用户偏好的低匹配高薪范围）。通过 sidecar 依次调用 jobs.fetchLiepinDetail 取得 373 字完整 JD、Qwen 解析 7 秒生成画像草稿、按 complete 保存为 jp_3fd3fac1（公开详情校验通过）、Quick Run qr_20261010133456921110 以模板拼装生成（同 10 月 7 日的材料与两张证据卡，规则匹配 45、评测 38、NEEDS_REVIEW），再固定为候选 ar_20261010133457367833。
- 固定时自动分配文件名"童双龙-艾诺-模拟-20261010.1.PDF"，恰为 24 个 UTF-16 单元，通过上传前校验；两页，快照 SHA256 a1b9ebd5dab305199e8dd767df14f42fe9e872a381c5eb4363b82c0ea1827adf，正文保留公司与岗位全称。命名登记表现有两条。daily.status 已列出该候选，getPendingReview 可见；授权仍为 expired，未启用。
- 猎聘三个附件位仍被卓胜微、上海皮赛、视涯的旧名附件占满，无上传控件；实测前须先在 App 内移除一份，建议移除最早的卓胜微测试附件。本轮上传/发送/删除均为 0，16 条历史成功记录不变。平台是否接受新名待用户在 App 内执行后记录。

## 2026-10-10 P0-018 跨日真实结果核验与收口，P0-019 成为唯一 next

- 用户询问下一步后选择收口 P0-018 并回复“开工”，接受按现有证据标为 deep_verified、不再追加真实投递批次的口径。本轮只做只读核验与文档入账：没有新增上传、发送、删除，没有修改授权、Token 或本地配置，没有驱动招聘网站。
- 核对发现台账与路线图停在 10 月 8 日“跨日结果待观测”，而 App 已于 10 月 9 日 09:00（上海）自动执行第二日批次 daily_15299220a31340c5895796d28cd75691：视涯科技“模拟IC设计工程师”，一次上传（HTTP 200）、附件原字节绑定、岗位/沟通确认、最终发送与回执落盘，finished / completed，确认 1/1、未决 0。提交 native-f2ba87d9867a49d495c5ecad1e952251，send-resume HTTP 200 / flag=1，投递日志 rate_limit、target_verify、submit_safety、resume_attachment_binding、login_check、chat_send_resume、submit、receipt 八步全部 success；PDF SHA256 b56fb0cdf992fe7625fa0f90915e5d151184c52fdc48604dd6750500557cce85 在批准快照、审批队列、回执、投递日志和 SQLite 每日条目中一致；agent run 状态 DONE。10 月 8 日投递日志与回执文件指纹与前一条台账一致，SQLite 累计 16 条 success。
- 以 .venv Python 直接启动 tools/sidecar/server.py 只读调用 daily.status：授权 395dafb9242b4011aa970fb53d1603af 按到期时间判为 expired，今日 2026-10-10 确认 0 / 剩余 3 / 未决 0，两日历史均 finished / completed 且各项 phase=success，无可授权候选、无需恢复；调用前后 SQLite 与 outputs 无文件变化。10 日无新批次，与到期一致；磁盘记录无法区分“到期阻断”与“App 未运行”，到期阻断仍以 10 月 5 日隔离时钟测试为准。
- 收口依据与限制：连续两日真实结果、重启不重投、到期生效已具备；每日合计 3 次上限只有隔离 SQLite/测试时钟验证，常驻调度只在开发壳验证，10 月 9 日批次后的原生页面重启读回本会话未执行（没有桌面自动化工具）。限制随验收记录保留，后续真实求职需要每日多岗时另行实测。记录：outputs/acceptance/daily-cross-day-20261009/validation.json。
- 矩阵 daily_authorized_delivery 改为 deep_verified / depth deep 并新增上述证据，boss_readonly_integration 改为 next，current_focus 与版本同步；路线图 Current Focus、平台批次表 S4/S5 与串行说明同步。路线图检查、v2 约束、AIEF L3 检查通过，tests/acceptance 96 项通过。
- policy.yaml 发现混入 App 于 9 月 28 日通过设置页写入的本机 LM Studio provider/base_url/密钥占位：sidecar 在未设置 PPF_POLICY_PATH 时默认读写仓库根 policy.yaml，与 tools/README 要求的 policy.local.yaml 不一致。本轮不提交也不还原该文件，避免正在使用的 App 丢配置，作为后续独立小修复处理。

## 2026-10-08 简历 PDF 改为可读文件名

- 用户要求“姓名-公司-岗位-年月日.序号.PDF”，并明确目标公司和岗位可以用简称。定位后复用原 Quick Run/exporter、简历中心目录导出、批准快照及附件绑定；新增的轻量命名记录仅保存版本与文件名映射，原文件锁保证并发分配，不增加导出器或投递流程。
- 自动文件名使用生成时姓名/目标、上海日期 YYYYMMDD 与从 1 开始的序号；同版本重复导出/重启沿用，同日同名简称组合的新版本递增。公司/岗位在超长时去常见地域/法律/级别后缀并保留可读前缀，适配猎聘 24 个 UTF-16 单元限制；姓名、日期、序号不为适配平台随意改写，仍无法适配则上传/每日启用前阻断。正文及岗位身份保留全称；显式指定导出文件路径仍尊重输入。
- 新候选的 pdf_filename 与原快照身份一起绑定，原 PDF 页和每日清单显示名称；扩展名大小写兼容而主体、文件指纹、平台附件身份仍严格核验。已准备/批准的旧快照及明日视涯清单不迁移，旧上传/回执继续使用原名，本轮没有新增上传或投递。
- TDD 覆盖同版本稳定、跨日/同日递增、并发与简称碰撞、路径字符、长名称、上传前不占位、快照改名拒绝、大写 PDF 的绑定/移除兼容。独立审查发现 macOS 大小写不敏感导致名称碰撞，先复现再以 NFC+casefold 判重修复，复审无 Critical/Important；前端/原生构建通过。OpenSpec、DESIGN、RPC 与画布同步。
- 真实 App 从简历中心选择既有上海皮赛 A 版，导出并重复导出到验收目录，实际名称为“童双龙-皮赛-模拟-20261008.1.PDF”，只有一份文件；两页渲染检查通过，76 条声明完整，正文公司/岗位全称不变。证据位于 outputs/acceptance/pdf-filename-20261008/。平台新命名的实际上传尚未额外实测，不把本地导出/单元测试冒充新的平台发送。P0-018 仍等待原定真实跨日验收。

## 2026-10-08 App 每日授权首日真实批次完成 1/1

- 用户对恢复历史记录的具体入口回复“帮我操作”，自动审批阻断已解除。通过 App 恢复奥维领芯、沁恒微电子两条原成功记录，仅执行各自独立附件移除；旧岗位发送按钮保持禁用，没有重复投递。两次移除均为一次指定请求、HTTP 200 / flag=1，附件数量依次 3→2→1；各 6 个本地快照/回执文件指纹不变。随后 App 观察到 1 个可用文件选择控件，上传位置恢复。
- App 启用原草稿 395dafb9242b4011aa970fb53d1603af：仅上海皮赛、视涯科技两个固定 PDF，每日最多 1 岗、上海 09:00、2026-10-10 00:00 到期。通过“执行今日批次”运行上海皮赛“模拟芯片设计工程师”，App 自动完成一次上传、平台附件原字节核验、岗位/沟通/附件确认、最终发送及回执落盘；没有在招聘网站上由代理点击业务按钮。
- 首日批次 daily_b2cf5fd2b0d94325ab9863c6ce696d24 为 finished / completed，确认 1/1、未决 0。提交 native-817e64aab7c943c6b44e3de44a833017 的本地证据 verified，PDF SHA256 为 55c0f19782b19427827c12383cfc148b5ad1ef143806f04e2b07d5341f83d5a3，回执 SHA256 为 cd79b3e43f5efb516e80fe4237b338bc95bf4f4aaec914f3ce06d75935c11aed；SQLite 累计 15 条 success。未声明招聘方已读或反馈。
- 正常退出、确认进程结束并重开后，App 读回同一 finished 批次、首日 1/1、未决 0、原授权与次日候选；没有新增批次或重复投递。开发版壳首次重开空白，定位为原 Vite 服务已退出，复用既有 pnpm dev 恢复后重启通过；没有安装、升级或修改全局配置。此验收仍使用开发版壳，未声明独立发布包的常驻调度已验收。
- 视涯科技保留为次日候选；授权到期和每日上限不扩大。App 需保持运行且电脑未休眠，关闭后不补过去日期。真实跨日结果尚未观测，P0-018 仍唯一 next，不以首日 1 次验证声明总体每日 3 次目标全部验收。执行记录：outputs/acceptance/daily-candidates-20261008/authorized-execution.json。

## 2026-10-08 两岗范围已确认，旧记录恢复被自动审批审查阻断

- 用户对前轮具体两岗/PDF、每日一岗及奥维/沁恒两份旧测试附件移除回复“好 开工”。原 App 草稿的两份文件指纹、每日上限、09:00 和 10 月 10 日到期时间均未改变。
- 恢复奥维旧 Quick Run 记录时，电脑操作自动审批审查拒绝“固定此 PDF 与目标岗位”按钮，认为它可能准备授权范围外的旧岗位投递。已核对 handle_prepare_pdf：已有 quick_run_id 分支只返回原成功记录；该记录正是指定旧附件移除入口。分步填写编号允许，但点击按钮仍被拒绝；没有绕过审查。已向用户请求对此具体历史恢复操作的明确确认。
- 两份旧附件各 6 个本地快照/投递证据文件指纹不变，原回执均 verified，SQLite 仍为 14 条 success。每日授权仍 draft / ever_active=false，上传/发送/删除均为 0；未启用定时以免在附件尚未释放时消耗今日批次。执行记录：outputs/acceptance/daily-candidates-20261008/authorized-execution.json。此为自动审批阻断，不是 Token、登录或用户原实测授权丢失。

## 2026-10-08 真实候选准备与 JD 解析、附件提示兼容修复

- 用户授权继续真实验证后，先核对 App：原 14 笔已成功、旧授权已撤销且范围为空，没有可复用的新候选。通过 App 使用原 Token 搜索“模拟IC”，导入 17 条官方草稿，再选择上海皮赛与视涯科技两个具名岗位；未重配 Token、钥匙串或本地 Qwen 模型。
- 真实准备发现两处解析缺口，均在原实现内先红后绿修复：完整 JD 的“职位描述”标题未识别；Qwen 在关键词里重复输出导致 120 秒超时。保留原 ID/正文完整性检查，给模型字段增加长度与条数限制、本地请求加 1800 token 上限，拒绝截断/超限结果，绑定岗位的公司、名称和来源由原线索保真。127 项相关测试及 18 项子测试通过，独立审查通过；修复后两份真实 JD 均由 App 模型解析并审核保存。
- App 复用已确认职业档案、消息平台与绿城两张完整证据，走 Jobs→Quick Run→生成→固定 PDF→原字节预览→每日候选；重启后两条仍在。两份各两页、76 条声明均可从 PDF 提取、渲染无截断，内容完整但保留待投递审核；规则匹配分均 43，关键词覆盖分别 0/9、0/10，评测分均 35，没有添加芯片设计经历来补分。
- 附件检查发现旧附件的经历同步提示遮挡入口。复用原生只读观察脚本，只关闭已识别唯一提示的 Close 控件，不同步或填写经历；独立审查发现延迟后页面边界需重验，补失败反例后修复。5 项观察/UI 测试、18 项 Rust 测试及原生构建通过，复审通过。真实 App 重启后可自动关闭提示并读到三份既有附件，但没有上传控件；未把检查结果当成上传成功。
- 已在 App 保存两岗草稿：每日最多 1 岗、上海 09:00、2026-10-10 00:00 到期，用于最小两日验证，不改总体每日 3 次目标。实际状态为 draft / ever_active=false。具体岗位、PDF 与新增永久移除奥维/沁恒两份旧测试附件的范围已提交用户确认；此前一般实测授权保留，不等于已确认这些删除动作。本轮上传/发送/删除均为 0，尝试库仍为 14 条 success、无未决。
- 验收记录为 outputs/acceptance/daily-candidates-20261008/native-validation.json。P0-018 仍唯一 next：实际非空授权批次和真实跨日结果尚未完成；候选准备与缺陷修复不替代这两项验收。

## 2026-10-08 每日批次中断恢复与逐项核验补齐

- 按 P0-018 推进 App 功能。先核对原 daily_runs、attempts、原生执行锁和 PDF 队列，确认日期锁/每日额度/暂停撤销已存在，缺口是历史不展示具体岗位与阶段、上传中断仍停在 in_flight、恢复入口不明确。本轮复用原状态与接口投影，没有新增恢复数据库、队列或执行引擎。
- 每日历史显示逐项阶段、确认成功/未决数量、上限、停止原因和返回同一 Quick Run 的原 PDF 核验入口；旧批未开始项不借用次日状态。结束中断批次时保留成功与未开始项，在途投递转 unknown 保留占位，上传中转 unknown 禁止重传；原队列记录停止依据，上传/沟通/新发送确认/最终发送受阻，原只读检查和本地回执核验保留。
- 独立审查复现“撤销旧授权、换清单可绕过未知上传”，已先红后绿改为启用及 claim 全局检查原队列，历史窗口外及旧授权未决也可追溯，已确认成功/明确失败的尝试排除。原生验收另发现每日项误显示无关手动批次的成功计数，已补复现测试并修复，计数统一回所属 daily 历史。
- 使用明确标注的本地合成中断状态，真实 App 完成重开→读取上传中/未开始/待回执→结束中断批次→精确回原 PDF→只读核验缺失回执→再次重启。两项保持未确认，未开始不变，缺失回执没有提升成功；写按钮禁用，逐项布局视觉检查通过。此为合成状态恢复验收，不是发生过真实平台请求的中断或实投成功证明。
- 80 项 Python/GUI 回归与 18 项 Rust 测试、前端构建、v2/路线图/AIEF/差异检查通过；独立复核无 Critical/Important。暂停/撤销/到期/跨日、换授权拦截使用隔离真实 SQLite 与测试时钟验证，没有修改系统时钟。规范、设计、RPC、画布已同步。
- 测试队列、快照和数据库行已可恢复归档；原 188 个业务文件与原数据库业务行完全保持，14 条真实投递证据仍 verified，持续授权仍未启用。本轮平台上传/发送/删除均为 0。验收记录 outputs/acceptance/daily-recovery-20261008/native-validation.json。P0-018 保持唯一 next：实际非空授权批次的完整执行及连续多日平台观测仍未验收，不以本次模拟恢复替代。

## 2026-10-08 App 岗位定制与候选准备接续补齐

- 用户再次明确目标是完善 App 功能，不能由开发代理代做业务。本轮先核对 Jobs 审核、Quick Run、固定 PDF 和每日清单的既有实现，确认核心能力已有，断点是页面接续依赖手抄编号。实施集中于原页面、原 RPC 和原审批队列；没有新增生成器、资料库、投递引擎或系统定时任务。
- Jobs 已保存 active 且含 JD 的画像提供“使用已保存 JD 生成定制简历”；Quick Run 精确带入目标、显示原职业档案确认状态，无效/未审核目标不自动改选首项。复用既有游标读取所有画像，修复较旧画像不在首屏时被误判不可用。切换岗位/材料/证据/定位清空旧结果，运行期间锁定输入，晚到响应不覆盖新目标。
- DONE、内容完整、追溯有效且已导出 PDF 的本次结果提供原 Submissions 接续入口，只预填准确编号；仍须用户点击原固定/预览/批准操作。prepared 候选可以前往原每日清单，空清单可直接回 Jobs。导航不自动生成、固定、选择候选、启用授权、上传或发送。
- 原生验收发现 Agent Run 通用审批按钮会错误接管原生 PDF 候选。先红后绿补齐 getPendingReview 的原 quick_run_id 路由，页面只提供返回对应 PDF 审核页；submitReview 在任何审批变更或通用投递前拒绝原生 PDF 队列。普通队列审批保留，不增加第二审批流程；缺少轮次的原生记录显示未记录。
- 使用清楚标注“非真实岗位/禁止投递”的本地样例，实际通过 Jobs→带参 Quick Run→显式生成→对应 Submissions→显式固定→原 PDF 预览→每日清单→重启→原 PDF 审核恢复。样例未勾选授权、未上传或发送，已可恢复地归档并移出活动画像、候选和生成列表。原 188 个业务文件指纹、SQLite 尝试与授权状态不变，14 条真实历史投递证据仍 verified；空清单回 Jobs 入口也已原生验证。
- 57 项相关 Python/GUI 回归、前端构建、v2/路线图/AIEF/差异检查通过。分页 Important 和原生审批混用均已修复，独立复审无 Critical/Important；OpenSpec、DESIGN、RPC、.pen 同步。原生记录为 outputs/acceptance/app-workflow-20261008/native-validation.json，明确仅证明本地样例的 App 接续，不代表真实招聘平台或每日跨日验收。
- P0-018 仍唯一 next。后续继续完成 App 每日执行自身的非空清单/中断恢复等验收，真实启用与跨日结果仍按原授权范围验证；不以代理人工准备、手动写成功记录或此次本地样例替代产品能力。

## 2026-10-08 用户确认完整简历底稿通过，后续持续优化

- 用户明确“按通过处理 后面再持续优化”。确认前核对当前职业档案 revision 与已交付底稿一致，Markdown/PDF 指纹未变化、档案无结构缺项；通过真实 App 勾选事实确认并保存，页面回读“档案已确认 / 资料库已就绪”，后端 reviewed/ready 均为 true。
- 本次通过范围为当前完整职业档案与两页底稿的事实、内容及排版验收。用户原话、档案版本、确认时间及已接受 Markdown/PDF/trace 指纹保存在既有验收记录 source_reconciliation.user_acceptance；不修改用户已经接受的 PDF，不再将同版本内容确认作为推进阻塞。
- 后续在此基线上持续优化，下一步按已确认档案和完整目标 JD 生成岗位定制版，再准备 P0-018 候选清单。当前底稿无具体公司/JD，内容通过不等于新投递授权；每日授权、既有投递额度及 14 条历史成功记录未变。本轮无平台上传、发送或删除。

## 2026-10-08 找回已有职业资料，完成来源对比和真实完整底稿

- 用户指出已有资料后，沿导入材料的原路径找到求职材料、经历底稿、已确认职业教育时间线及同期原始工作记录，并对比猎聘历史简历快照。此前“缺真实履历”的判断仅基于已导入范围，现纠正为“资料已存在，尚未接入 App”。时间采用确认底稿，旧版品牌起点/在职状态/教育日期不回填；姓名与联系方式保留原个人资料，不从别名或占位符覆盖。
- 复用 material.upload、evidence.saveDraft、profile.update，累计导入 7 份相关原文，整理 4 段工作、2 段教育和 5 组能力，增加 3 张历史工作证据及 1 张消息平台改造证据。材料来源、同期记录和结果原文关联保留；没有新增导入器、生成器、资料库或审批流程，也没有代码变更。档案结构缺项为零，最终事实确认仍未勾选。
- 消息平台改造使用 2026 年 7 月实施/压测记录核对时间、角色与性能数据，明确本机容量验证不等于生产性能；规模口径区分维护范围与个人独立开发量。对旧三张小功能卡中仍缺具体项目时间/职责的内容不补猜测，当前底稿选用两项具备时间与角色来源的代表项目。
- 原生成 CLI 输出 A/B 完整底稿，manual_career_review 选材记录明确未执行目标 JD 匹配，不伪造岗位或匹配分。真实原生 App 已读回档案、材料及生成版本，并通过原导出按钮生成 A 版 PDF。最终两页，75 条声明均可从 PDF 提取，所有工作与教育条目保留，两页渲染检查无截断，首版多余末页已通过减少重复表述收敛。
- 完整底稿位于 outputs/career_review_20261008/pdf/resume_mr-career-review-20261008_A.pdf；来源对比、档案指纹、原生回读/导出及 PDF 核验记录写入既有 outputs/acceptance/complete-career-20261005/validation.json 的 source_reconciliation。原临时开发 App 已不存在，本轮复用现有调试二进制恢复工作区内验证壳及现有 Vite 服务，无安装或升级。
- 档案保持未确认，生成记录 deliverable=false；本稿用于内容核对，未绑定具体公司和完整 JD，不能作为批准投递版本。本轮平台上传/投递/删除均为 0，14 条历史真实证据仍 verified。下一步只需核对本稿的当前事实及联系信息，再选完整 JD 定制，不再要求用户重填已存在的基础时间线；P0-018 仍唯一 next。

## 2026-10-05 完整职业简历能力补齐，真实档案待用户完善

- 按用户“可以开工”和“不要重复建设”，先核对已有简历中心、personal_profile.yaml、证据提炼/审核、模板 A/B、PDF 导出、固定快照与批准队列。实际缺口为职业时间轴、教育/能力/成果档案、完整正文组织和内容写入门禁；在这些入口上补齐，未另建资料库、生成器、审批页或投递流程。
- 原个人资料文件保存职业概述、任职/合作经历、分组能力、教育及展示选择、补充成果，关联既有审核证据。草稿保存不确认，明确确认绑定资料与证据指纹；所有表单保存使用加载版本防止陈旧覆盖。原模板按基本信息/求职意向、职业概述、核心能力、工作经历、项目经历、教育和可选成果生成，实际任职单位与客户项目分开，字段追溯保留。
- 原准备/上传/发送、默认简历路线和每日清单增加内容检查。职业档案未确认、证据版本变化、项目区间无法确认或越出任期、旧稿缺内容记录均阻断。导出 PDF 绑定当时 Markdown/trace；批准继续写原队列并绑定同一快照。投递页复用 daily.preview 读原 PDF，真实 WebKit 预览空白已修复；旧上传同意不再自动勾选新内容确认。
- 真实 App 验收完成空白工作草稿保存、正常退出/重启读回、缺项不可确认、移除测试草稿后保存、旧生成稿准备阻断，以及南京美辰历史成功快照原字节预览与发送禁用。基本五字段未变，测试空白条目已清理。隔离合成档案走原生成/导出/门禁，六个正文章节和基本信息一页完整，文字提取与渲染视觉通过；明确标注非本人履历，没有补造用户职业事实。
- 受影响资料/生成/内容门禁/PDF与默认路线/历史回执/GUI测试、前端构建、v2/路线图/AIEF检查通过；本机 HTTP/PDF 测试仅因沙箱失败的用例按原代码复跑通过。独立审查发现的四项 Important 已先红后绿修复，末次复核无 Critical/Important。验收记录：outputs/acceptance/complete-career-20261005/validation.json；合成输出仅作结构验证。
- 本轮上传/投递/平台删除均为 0。14 条真实投递证据仍全部 verified，三批 success 数为 10/1/3；每日授权保持 revoked、ever_active=0。真实职业档案仍待补工作履历、教育展示选择、核心能力及项目职责/时间后确认；不把能力实现或合成测试写成正式个人简历可投递，P0-018 仍唯一 next。

## 2026-10-05 先评审完整简历内容，再推进投递

- 用户指出目前生成内容仍过于简单，要求先梳理简历组成，再进行投递。核对实现确认：个人资料接口仅五个基础字段，正文生成主要为联系信息、定位、技能和项目经历，完整任职时间轴、教育背景和职业摘要尚未全面接入；上轮证据链与排版改进不等于解决完整职业履历结构。
- 在既有 `AIEF/context/tech/GENERATION.md` 增补内容标准讨论稿，覆盖基本信息/方向、职业摘要、能力技能、工作履历、代表项目、教育及可验证补充成果，并区分完整底稿、定制版本、内容验收与投递审批。标明为讨论稿，未把建议或待实现的门禁写成已完成能力。
- 本轮只梳理并记录用户推进顺序，没有代码实现、PDF 重生成或外部投递。内容完整性与事实审核通过前，不继续增加真实投递。

## 2026-10-05 复用既有生成前置能力，接通目录提炼并优化 App 简历样稿

- 用户要求开始准备新的授权清单，同时优化 App 生成 PDF，并强调项目已有明确生成目标与部分前置实现。重新对照 PLAN 第 7 节、核心 Generation/Evidence 规范、材料导入、证据审核、画像/匹配和 Quick Run；确认 15 分钟 A/B 定制产物与事实保真目标已有，问题在链路接通和质量门控。没有另建简历生成器或材料库。
- 实际断点：已导入的 998 文件工作目录保存为 TXT，旧模型提炼只支持 Markdown，最近生成只消费一张已审核且内容单薄的卡。现有上传 PDF 是历史 Quick Run 验收样例，未当作真实任职/业绩资料。新文档选择器从既有汇总恢复 664 个可选片段，过滤规则/模板/入口文档，支持名称筛选、原文预览和最多 24000 字符的完整分段；复用原 LM Studio 提炼、草稿审核和来源校验。
- 真实 App 使用 `qwen/qwen3.8-27b` 对门店租赁、始祖鸟之路、SV 影展验收三份文档提炼。首轮模型超时，启动已有 LM Studio 后确认原模型及本机服务 READY，再从 App 成功提炼；未重配凭据或换模型。人工按原文校正模型的实施断言、混合角色和推断日期，只保留可验证的设计/测试范围。通过 App 保存 `ec_0f6287d2`、`ec_9a1244c4`、`ec_f8b64115`，各自保存所选文档身份与指纹；两项设计经历无本人职责/时间依据，保持缺项。
- 普通编辑保留来源与审核元信息，事实改变明确降为待审核；按原来源重审时固定目标编号，切卡即时清空、加载中不可保存，后端拒绝换源覆盖并保留创建时间及扩展元信息。列表可用计数按实际候选资格计算，未审核历史卡不再因旧 ready 标记被误当可选。独立审查复现的来源丢失、过滤文档重入、重审异步串卡与历史字段覆盖均已先红后绿修复。
- Quick Run 勾选复用既有 evidence_ids，只选本次三张已审核卡；模型开关准确标注辅助选材。生成补入真实场景，按目标词和定位排序具体行动，缺角色/时间/技能等返回 missing_evidence_fields 并保持 NEEDS_EVIDENCE。PDF 共用模板改为清晰单栏层级、原章节顺序和自然续页；不靠添加数字、补造任职或缩小字号填满页面。
- App 实际生成 A/B 正文与 A 版 PDF。最终样稿运行 `qr_20261005073657165232`，一页，37 条追溯事实均在 PDF，排版分隔符规范化后全文与 Markdown 一致；最新页已渲染视觉检查。真实页面显示两项设计经历待补本人职责和经历时间，quality_passed=false/deliverable=false；目标沿用已完成测试岗位仅作对比，没有重复投递，也不将此稿称为正式可投递成品。慢 sidecar 请求移出主窗口事件线程，保留原串行协议；第三次提炼及生成时实测界面可读且显示运行中。
- 新候选按原低匹配/高薪验证偏好从已有官方线索筛出上海时识、展芯半导体、米高蒲志光芯片岗位。三次真实 App 获取均提示“职位页面暂不包含可用完整 JD”，所以没有补造画像、生成对应投递 PDF 或启用授权。不能把剩余问题写成只差用户确认。候选缓存薪资与这次失败状态单独保存在 `outputs/acceptance/resume-quality-20261005/validation.json`。
- 83 项受影响 Python/GUI 回归通过，1 项可选 PDF 字体 fixture 因默认未启用跳过；真实样稿另用 bundled pypdf 全文核验，18 项 Rust、前端/原生构建、静态门禁通过，独立复审通过。原 14 条投递证据仍 verified，当前无有效每日授权，本轮上传/投递/删除均为 0。P0-018 保持唯一 next；后续继续补真实履历字段和可用完整 JD，完成非空授权清单与跨日验收。

## 2026-10-05 P0-018 每日受控投递首版实现，真实未启用路径验收通过

- 用户“下一步开工”后按唯一 next 推进 P0-018。探索已有批准快照、SQLite 尝试库、原生 PDF 上传/绑定/发送/回执和 App 生命周期，复用这些能力；新增缺口为持续授权、上海日期计数、日期唯一触发、暂停撤销和短缺记录。未另建投递引擎或系统级定时任务。
- 智能运行页新增具体岗位/固定 PDF 清单、原字节 PDF 预览、每日 1–3 上限、上海执行时间、到期时间及独立确认。草稿不启用，清单启用后不可变；暂停、恢复、撤销及到期均约束下一次写操作。首版只授权已准备且尚未上传/投递的猎聘 PDF，最多 30 项；新岗位、文件、平台或附件删除不自动扩权。
- App 运行时每分钟检查，手动执行共用 SQLite 日期唯一键；同日最多一批，所有受控 reserve 共用总计三次的成功/未决额度，未知跨日阻断，重启/换版本/换授权不重投。中断批次可由空闲原生执行锁内的命令结束，不重发；已有在途保持未知占位。App 关闭/休眠不保证运行，不补过去日期。每日批次与历史验证额度独立留证。
- 独立审查发现午夜与页面等待的竞态，均补失败测试后修复：所有最终发送（包括旧单笔 PDF 和官方默认 API）重验占位日期；原生导航等待后再发写许可，页面在点击/网络写入处检查日界、到期和取消标志；观察结束关闭写门禁并保留到原生重载销毁旧文档，阻止迟发 POST 绕过。单笔和每日整批共用原生会话互斥，暂停/撤销不争用执行锁。最终独立复审无 Critical/Important。
- 真实 Tauri 已完成进入页面 → 保存空清单草稿 → 正常退出/确认进程结束 → 重开读取同一草稿 → 经 App 原生命令撤销。页面展示今日 0/3、占位 0、暂无可授权的新 PDF，启用/执行保持禁用；未勾选持续授权。当前所有真实已准备 PDF 均已投递，不能复用作新候选。只有草稿/阻断路径获原生验证，非空清单 PDF 预览、实际每日执行、重载连续操作及多日真实日期验收仍待完成，P0-018 不标为 deep_verified。
- 86 项受影响 Python/组件/页面脚本回归、18 项 Rust 测试、前端及原生构建通过；规范、DESIGN、RPC、`.pen` 与中英文界面同步。页面证据为 `outputs/acceptance/daily-authorized-delivery-20261005/native-inactive-validation.json`。没有新增上传/投递/删除，14 条历史成功证据再次只读复核均 verified；Token、钥匙串偏好和 LM Studio 配置未改。下一步沿既有 App 准备新岗位/PDF 清单，取得具体持续授权后做真实每日及跨日验收。

## 2026-10-02 App 自有附件移除通过，新增三笔 PDF 实投全部完成

- 用户对移除旧测试附件回复“允许”，并明确“移除应该是 App 的自己能力”。沿现有 PDF 批准运行、附件字节绑定、Tauri 会话和投递记录补齐移除能力；外部自动化只操作 App 主界面，平台菜单、确认及请求均由仓库内固定适配代码执行。Spec、DESIGN、RPC 和 `.pen` 已同步。
- 成功 PDF 卡片新增独立确认和“移除此平台附件”。App 重验原成功回执、批准 PDF、当前唯一附件身份及下载指纹，先持久化占位，再只允许一次指定附件的固定移除请求。精确业务成功与前后附件集合只减少目标同时成立才记 removed；未知禁止重删。只读“核验上次移除”仅在证明请求前拦截、零请求放行且原附件仍在时恢复未提交，保留原未知历史。
- 实际移除 `cv_b48a0f49ffdba28d.pdf`（南京美辰 ADC）：`remove-attachment-resume` HTTP 200 / `flag=1`，仅放行 1 次对应附件请求；另外两份附件保留。原 PDF/Markdown、JSON/YAML 投递日志及业务回执共 5 个文件指纹全部不变，原 success 和额度不变。正常重启后 App 仍显示“平台附件已移除，本地历史保留”，删除入口禁用。
- 释放位置后，App 完成卓胜微“技术专家-测试芯片设计”（30–60k·16薪，匹配 26）的上传、平台原字节回读、当前岗位/会话核对、选择附件及一次最终发送。运行 `ar_20261001085020339068`，提交 `native-2755d8df902c4c7293553f4502fb95db`；PDF SHA256 `2bdeaa70346bf438c55c70c49c19dcdc7c2adf668097bd26ffc0d58538e673ff`，回执文件 SHA256 `105c278864ba953ed2ccbb248524758b901e4c304837ac7aaa67cda7e61d8166`。`send-resume` 返回 HTTP 200 / `flag=1,data={}`，App 已核验为 success；重启后成功与禁止重复发送保留。
- 新批次 `validation_pdf_three_20261001` 最终为 consumed=3 / success=3 / remaining=0 / unknown=0 / in_flight=0，奥维领芯、沁恒微电子、卓胜微三笔均完成。原 11 笔保留，累计 14 条真实投递的本地证据只读复核均 verified；不以通用列表中混合的检查/测试记录计数，不声称招聘方已读或回复。
- TDD 覆盖身份/指纹/回执、一次性请求守卫、JSON data 封装、请求前拦截恢复、定时器清理及页面动作链；独立审查通过。最终 27 项受影响 Python/页面测试、16 项 Rust 测试、前端和原生构建通过。验收汇总：`outputs/acceptance/additional-three-20261001/validation-status.json`。这是本次明确授权的三岗验证批次，未开启每日自动投递；P0-018 仍为唯一 next，六平台规划不变。

## 2026-10-01 明确授权后新增两笔 PDF 实投成功，第三笔待附件位置决定

- 用户针对已展示的三份文件及对应猎聘岗位明确回复“授权”，此前上传自动审批阻断已解除。App 依次执行奥维领芯数字后端设计与沁恒 Sigma-Delta ADC 的固定快照恢复、批准上传、平台 fileId/原字节下载 SHA256 校验、招聘会话/选中文件确认、最终一次发送和本地回执核验。
- 奥维领芯：`ar_20261001082520713745`，提交 `native-f90f8c82ec974bcbbdccdf8eb49ad20f`，PDF `c969f5b8e4e09e7a50e5d8defeaff5c3fa247d84a49e9eed00b718c7caec7a31`，回执文件 `511e73b1c61b1297d6bb550ae8ce820b559974f58d79e5c6c212b2a64b444b27`。
- 沁恒：`ar_20261001084935349761`，提交 `native-37b1ac26bb4e47d4be141f280d61e7b7`，PDF `ca7e0c6b66865a6d088425a2180864a8f61ab5c24311d626e6c030cdd4ce1acf`，回执文件 `3c940349e59fa1f8d5c3cd2a1d95bc09ace94d12309d75c43f5765533b0d3041`。
- 两笔均真实观察到 `send-resume` HTTP 200 / `flag=1,data={}`，已由 App 核验并写为 success，完整本地证据检查 verified。每笔都核对该岗位所选附件；账号分别有 2/3 份附件时绑定通过。正常退出并重开 App 后，两笔仍显示公司、岗位、成功回执及禁用重试。没有声称招聘者已读或回复。
- 第二笔准备期间平台自动跳到 `/resume/parse-result`，旧会话检查显示 unverified。增量复用正常导航返回固定附件页后重新检查认证，不确认解析字段；Rust 测试先红后绿，16 项通过并经独立审查，Spec/DESIGN/RPC/.pen 同步。两笔实际发送通过；新增解析页恢复分支只有专项代码测试，未额外宣称其独立原生分支验收完成。
- 新批次 `validation_pdf_three_20261001` 为 consumed=2 / success=2 / remaining=1 / unknown=0 / in_flight=0。原 11 笔保留，累计确认 13 笔。卓胜微 `ar_20261001085020339068` 仍 pending，未上传、未占位、未发送。
- 平台附件数已达 3，完成第三份上传前需腾出位置。已请求单独确认移除旧测试 `cv_b48a0f49ffdba28d.pdf`（南京美辰 ADC），或保留旧附件只做两笔；当前尚未获删除确认，也没有删除。三份文件的上传/投递授权仍有效，不能把它扩成平台附件删除授权。实际状态见 `outputs/acceptance/additional-three-20261001/validation-status.json`。

## 2026-10-01 新增三个实投候选已准备，具体上传授权待确认

- 用户要求“新增几个实际投递验证一下”，本轮限定最多 3 个新岗位，沿用低匹配/高薪测试偏好；单独补充批次 `validation_pdf_three_20261001`，原 10+1 成功历史不变。这不是每日自动投递启用。已询问 PDF/默认简历路线，未收到选择时先按推荐 PDF 路线做可逆准备。
- App 真实页面完成三个新岗位的完整 JD 读取、原文审核画像和模板生成：奥维领芯数字后端设计（30–60k·15薪，23分）、沁恒 Sigma-Delta ADC（30–50k·13薪，23分）、卓胜微测试芯片设计（30–60k·16薪，26分）。使用既有真实材料与 `ec_4b0f457a`，不添加芯片经历、学历、量化成果。三份单页 PDF 已视觉检查，全文与源 Markdown 一致（排版分隔符及连字符规范化后）；均经 App 固定为 pending 快照。
- 多岗位准备暴露旧单附件假设：平台已有附件时使用加号，且最多保留 3 份。只读核对既定官方资源 SHA 后补固定加号入口；绑定改为上传 fileId/文件名/长度/当前卡片唯一匹配，准备确认时选择已批准 fileId，最终后端与页面两层重新核对。审查发现的“重复 fileId 但其中一个已选中”绕过已先红后绿修复。24 项相关 Python/页面测试、15 项 Rust 测试与原生构建通过，独立窄审通过。
- 首份奥维领芯 PDF 的 App 上传按钮被自动审批审核拒绝，原因是现有授权未明确覆盖新文件向猎聘上传及随投递附带发送。工具动作未执行，后台三项均 pending、无 upload/delivery 占位，新批次 consumed=0。已向用户发出带三份文件用途、具体目的地/岗位及平台副作用的明确确认，不能把沉默或预选选项当授权。
- 另已说明第三份上传前需要附件位置决定：是否移除上次测试 `cv_b48a0f49ffdba28d.pdf` 或只新增两次。尚未获得删除确认，也未删除任何平台附件。三份 PDF、不可变快照和备份均保留；状态记录 `outputs/acceptance/additional-three-20261001/validation-status.json`，本轮实际新增上传 0 / 投递 0。

## 2026-10-01 猎聘两路线结果追踪、反馈与统一验收收口

- 用户“开工”授权完成既定 P0-017A 剩余工作。先核对原 SubmissionRecorder、审批快照、API/PDF 回执核验、Submissions 详情、反馈迭代与 External L3；已有能力可复用，实际缺口是旧反馈仅接检查模式、真实 success 被误归为高优先级检查错误、旧 L3 只支持实时 Playwright 门禁。
- 新增共同只读证据检查，核验批准快照、岗位/版本、原业务响应、必需步骤、SQLite 尝试及已授权批次；API 默认文本观测与 PDF 字节绑定分别表述。当前 11 条既有记录均 verified，失败/未知/外部观察或证据变动不能升级成功；不联网、不补发、不改日志。旧首笔缺失公司/岗位从批准快照读回，不重写历史记录。
- 原 Submissions 详情统一显示版本、回执来源、指纹及证据完整性，列表与详情均禁用受控投递重试。原反馈接口新增历史读回及真实提交绑定，支持个人复盘/手动招聘反馈；内容必填，其他提交反馈或无生成依据的新声明被拒绝。后续动作只是计划，重新生成指向既有 Quick Run 并显示岗位画像，不复制 PDF 冒充新版本。
- 真实 Tauri 页面分别选择南京美辰 PDF 提交与白盒子 PLL 默认简历提交，保存明确标注的个人复盘。记录 `fi_20261001073854337587`、`fi_20261001074005379441` 分别保留原版本/日志/回执关联；正常退出并重启后两条均可读回，详情与截图实际显示证据完整。没有虚构招聘方回复、没有生成新简历、没有打开招聘网站或再次投递。页面证据为 `outputs/acceptance/official_delivery_prerequisites/submission-feedback-native-20261001.json`。
- External L3 增加显式 saved_app_records CLI，按提交编号只读复用原真实页面及业务证据，报告不复制反馈全文或敏感响应，也不回写源日志以制造反向引用。11 条提交统一结果为 external_validated / p0_017_complete=true；两路线各有真实反馈保存和重启读回样本。报告为 `outputs/acceptance/acceptance_app_delivery_20261001/external-l3-validation.json/.md`。
- 独立审查的两项 Important 均先红后绿修复：合法历史未知状态反馈不再阻断当前成功验收；非原生 surface、缺关键动作或错误 feedback iteration ID 不能充当页面完成证据。30 项新增用例、共 123 项受影响回归及 7 项路线图测试通过，前端构建通过；DESIGN、`.pen`、RPC 与实现一致，原生重启和视觉核验完成。
- P0-017A 与 P0-017 更新为 deep_verified，唯一 next 为 P0-018 每日受控投递。原批次仍为 10/10 success 与额外 PDF 1/1 success；本轮外部发送 0，未启动每日任务、未改凭据或 LM Studio、未安装升级工具。六平台后续目标保留。

## 2026-09-30 指定 PDF 经 App 真实发送并取得业务成功回执

- 用户授权的额外单笔 PDF 已完成。目标为南京美辰微电子有限公司“模拟IC设计工程师（ADC）”，官方标注 30–50k·18薪，匹配 23/100。App 从既有批准运行恢复同一招聘方会话，核对确认框唯一选中的平台 fileId 与已批准 PDF，再仅执行一次“立即投递”。确认框明确同时发送默认在线简历和这份附件，符合用户此前允许的范围。
- 平台真实端点 `com.liepin.im.c.chat.send-resume` 返回 HTTP 200、`flag=1, data={}`；请求 `attachmentId` 与平台回读字节核验过的 PDF 完全关联。原生记录的是“发送成功”业务回执，不声称招聘方已读、已回复或录用。
- App 本地“核验本次回执（不重发）”校验原始采集请求/响应、目标上下文、批准快照和附件身份后，更新既有 SubmissionRecorder、SQLite 和审批运行。运行 `ar_20260929213806534956` 为 DONE，App 自行确认 1；提交 `native-81d5f2fe745f4d95bfa2e3619dafd230` 为 success，共享步骤审计通过。额外批次 1/1 success，原十岗 10/10 success 保留，未新增第二个 PDF 岗位或重发。
- PDF SHA256 为 `b48a0f49ffdba28de2199d36f28fc0c5a9ce37b003f7017b86c3de20e4b9540b`，私有回执文件 SHA256 为 `508170af72256fcb88c09d10f39ed91169f2581d2c3a37c9a5f94e55d757042e`。批准原始 PDF 字节保存在只读快照，平台文件曾通过 App 会话下载，完整字节 hash 相同。
- 原生 UI 已显示 PDF 业务回执确认、正确公司/职位和“成功”，所有再次上传/开始/确认动作禁用；通用列表重试在前后端均被禁止。当前结果与上传成功、沟通已打开等中间态分开，保留首次文件名校验拒绝和原始采集记录。
- 独立审查发现并修复：观察中的签名附件 URL 两层脱敏（含嵌套 JSON），既有本次产物去除签名查询；从最终发送开始冻结历史附件绑定，后续平台文件变化不破坏旧回执。两项均先建立失败测试再修复，审查复核通过。
- 最终原生验收已正常退出并重开 App，以同一 Quick Run 恢复“PDF 投递已获业务回执确认”，再次本地核验成功。回执指纹、成功记录和批次数保持不变，上传/发送/重试均禁用；没有再次打开平台会话或发请求。最终 67 项受影响回归、15 项 Rust 测试、前端与原生构建、v2/路线图/AIEF/差异检查通过，DESIGN、`.pen`、RPC 一致性审查通过。
- 此次“十岗默认简历验证 + 额外一笔指定 PDF 发送”已获得真实业务证据；通用 API L3/runbook/反馈契约的统一验收与后续每日自动 3 次仍另行推进。P0-017A 仍唯一 next，但剩余工作不再包含本次 PDF 未完成或权限未授予。最终验收汇总见 `outputs/acceptance/official_delivery_prerequisites/pdf-app-completed-20260930.json`。

## 2026-09-30 用户允许平台附件影响，指定 PDF 上传与版本绑定通过（投递进行中）

- 用户在说明上传会解析补全在线简历、随后续投递附带后明确“允许”，这项影响不再等待授权。沿用额外 1 次生成 PDF 验证范围，不扩大原十岗批次。
- App 固定 `qr_20260929174329316560` 的原始 PDF 字节，审批运行 `ar_20260929213806534956`；审批、上传占位和状态通过本机队列持久化，远程窗口无本机文件或 sidecar 权限。
- 初次自动文件名 `resume_<16位指纹>.pdf` 为 27 字符，猎聘当前官方前端在请求前限制总长 24；App 以实际页面加载的官方资源 URL 和完整 SHA256 核实 beforeUpload 规则，保留原未知观测并归类客户端拒绝。改为 23 字符 `cv_b48a0f49ffdba28d.pdf` 后，真实上传/保存/附件列表响应均成功，当前账户仅这一份附件，大小 188078 字节。
- App 已使用自身登录会话回读平台文件，SHA256 与批准 PDF 完全相同：`b48a0f49ffdba28de2199d36f28fc0c5a9ce37b003f7017b86c3de20e4b9540b`。平台附件 ID 为 `297d842d8dG3a8a983e96ab`。普通无会话下载曾返回 403，未以此推断 Token 失效或再次要求配置；成功绑定依据已保存在审批队列。未未经核实确认平台解析出来的经历字段。
- 新批次 `validation_pdf_20260930` 上限 1、仅 `generated_pdf`；原 `validation_10_20260928` 的 10 条 success 保留。App 在进入南京美辰 ADC 岗位沟通前完成最新 JD/目标/附件复核，取得尝试 `81d5f2fe745f4d95bfa2e3619dafd230`，日志 `native-81d5f2fe745f4d95bfa2e3619dafd230`。目前为同一次进行中占位，不能再次开始或换岗重投。
- App 已识别目标沟通窗口的“发简历”入口，当前正在接通其确认和回执步骤；进入沟通与上传附件均不算 PDF 投递完成。P0-017A / 近期目标仍未标完成。开发代理仅用电脑控制操作 App 主界面验收，招聘页面动作由 App 固定适配代码执行。

## 2026-09-30 App 原生登录与本地 PDF 准备完成，平台附件副作用待决定

- 用户额外授权 1 次生成 PDF 实投，并在 App 内手动登录。为解决旧 Playwright/CDP 连接后的空白页，复用 Tauri 自带 WebView；实际完成主界面打开、程序正向登录检查、正常退出/重启后会话保留。全部网站交互由仓库内 App 代码执行，外部自动化只操作主业务界面做验收；未从外部控制招聘网站投递。
- 原生远程窗口按 HTTPS 官方域隔离；所有敏感 host command 同时校验主窗口和本地来源。只读观测有 nonce、严格字段、数量/长度限制，删除 URL query/fragment；遇到登录表单、网站安全验证、空白优先失败。未读取 Token、Cookie、密码或短信；未接入钥匙串、未安装工具或改变全局配置。
- App “检查附件要求”已真实打开管理页、关闭功能介绍并读取上传面板：支持 PDF/DOC/DOCX/JPG/PNG，上限 20M。页面明确提示上传即授权智能解析并完善在线简历，主动投递/发送简历时附件随后发送；这与单次低影响验证的范围不同，已询问用户是否接受额外影响，尚未上传。指定 PDF 与平台附件身份绑定、发送适配和业务回执仍未完成，不把权限问题表述为唯一剩余工作。
- 复用现有证据审核接口补齐 TXT 手工草稿。真实材料 `mat_7d4d23ad` 中门店租赁开发方案，经原生 App 人工整理、成果原文校验后保存 `ec_4b0f457a`；未沿用旧卡中未经核实的规模/提升数字、角色或时间。
- App 获取南京美辰“模拟IC设计工程师（ADC）”完整 JD 并审核保存 `jp_7e2bdb15`，绑定 `jl_liepin_ed62a4d31e0078cfe408`，官方标注 30–50k·18薪、上海。上海时识候选的详情读取失败后未继续使用该不完整目标。
- Quick Run 接通现有材料选择与模板参数，默认模板、可选模型，未修改 Qwen3.8 配置。原生运行 `qr_20260929174329316560` DONE，材料/证据/目标均为上述真实对象；匹配分 23/100，质量 32/100，保留 NEEDS_REVIEW 与实际缺口。低匹配是用户测试目的，不虚构相关技能来提升分数。
- App 已生成、预览并导出单页候选 PDF。真实复制文字测试发现 macOS 中文字体将“龙、门、用”等写为偏旁码点；先建立失败测试，再改用本机已有完整 Unicode 字体，复测通过。最终 PDF 为 188078 字节，SHA256 `b48a0f49ffdba28de2199d36f28fc0c5a9ce37b003f7017b86c3de20e4b9540b`；已确认视觉、姓名/目标/项目文字可准确提取且无内部追溯路径。
- SQLite 补充授权支持单独批次、不可变授权引用及 `generated_pdf` 路线限制，默认简历不能占用该额度；本机实际补充批次尚未激活。只读核对原十岗依然 10/10 success，本轮外部上传/投递均为 0，在线简历未修改。
- 验证：81 项 Python/组件测试通过（1 项真实字体测试常规跳过后单独执行通过）；14 项 Rust、9 项生成/矩阵契约通过，前端构建、roadmap 与 diff check 通过。含浏览器渲染的测试在沙箱内失败，按原测试用本机渲染器复跑通过，未改测试来绕过问题。设计文档、画布、RPC 与 OpenSpec 已同步；证据位于 `outputs/acceptance/official_delivery_prerequisites/pdf-native-preparation-20260930.json`。P0-017A 仍唯一 next，PDF 实投与整个近期目标保持未完成。

## 2026-09-29 十个真实岗位投递完成，PDF 路线仍阻塞

- 用户要求先完成近期目标。本轮先纠正计数边界：原授权为累计 10 个真实岗位，此前 2 个已发送岗位都占用名额，最多新增 8；App 验证质量计数不能成为追加第 11 次的理由。已沿现有 SQLite 防重库增加不可变批次授权、并发原子额度、未知暂停；默认简历与未来 PDF 共用上限。App 展示上限/已占用/确认成功/剩余，额满在准备及发送两层阻断。
- 核实历史首笔和第二笔原始 API 响应的完整 SHA256 完全相同。新增严格的本机证据引用核验，经 App 原审批页触发，验证已有受保护响应与双方日志指纹、旧快照/尝试身份后完成程序确认；保留外部观察历史，不伪造第一笔原始响应文件，不再次发送。两笔仍只占两个名额。
- 本轮通过原生 App 完成 8 个新的岗位：当前 JD 读取 → 原文人工审核 → 保存画像 → 默认简历固定快照 → 批准 → API 单次发送 → App 回执落盘。复用平台简历版本 `platform-default-f05ed38fe767`，本轮未控制招聘网站、未发送聊天消息，未重配 Token。
- 新候选来源为既有官方岗位和 App 搜索“模拟IC”的真实结果；无法取得当前完整 JD 的候选未投递。选择芯片/嵌入式方向及官方标注月薪下限 35k–50k 的岗位，依据与现有软件经历方向的差异作定性筛选；匹配分保持未评估，没有把未知写成 0，也不宣称全平台全局最低。
- 最终共有 10 个不同的原始平台岗位 ID、10 次 API 提交、10 条明确成功结果、10 条 success 防重记录；批次 `validation_10_20260928` 已用 10、成功 10、剩余 0、未知 0。每条审核快照与回执/简历版本均可关联。十笔均发送平台默认简历，其中一笔通过完整响应 hash 引用核验，原始事件保留。
- PDF 路线在 App 通道会话页实际执行“检查”“开始配置”：需要登录，随后网站把独立登录窗口跳到空白，返回 `LOGIN_PAGE_REDIRECTED_TO_BLANK`。未上传 PDF，指定附件发送仍未验证。本轮询问剩余名额分配，未收到回答后已说明采用既有默认简历授权补足 10；不能宣称 PDF 项或整个近期目标全部完成。额度已用完，后续新增真实发送需新的明确授权。
- 121 项相关 Python/组件/矩阵测试通过；前端构建通过。记录与十岗位清单为 `outputs/acceptance/official_delivery_prerequisites/ten-job-completed-20260929.json`，明确 `generated_pdf_route_complete=false`、`recent_goal_including_pdf_complete=false`。本轮不因额满启动新批次、不开启日常定时任务，不扩大六平台写入范围。

## 2026-09-29 App 默认简历单笔真实投递与回执恢复通过

- 用户“开工”后优先处理程序回执。只读核对官方 CLI 仍透传响应，未提供输出语义模型；沿现有官方 HTTP、审批快照、SubmissionRecorder 和防重实现，没有操作招聘网站。
- 首先补有界 `data.result` JSON 解包、严格正向业务文本/冲突判定、解析版本与原因。每次响应的必要业务字段保存为独立受保护证据（目录 0700 / 文件 0600），排除凭据/请求头/未知字段；普通日志和界面只返回摘要与指纹。未知结果保留提交编号。
- App 新增“核验已有回执”：只读本机证据，校验 hash、原 HTTP 响应指纹、run/candidate/job、简历与 attempt 绑定后更新结果；不联网、不再次投递。原 unknown 事件保留，重核事件追加，成功/失败仍保留防重。旧记录只有 hash 或外部网站观察时不升级为 App 成功。
- 真实目标为昇阳智慧(上海)科技有限公司“SOC设计负责人”，上海浦东，50–80k·15薪。App 获取完整 JD 后 Qwen3.8 两次解析超时；模型服务可连接且模型已加载，没有升级/替换或改全局配置。为解决实际表单缺口，增加显式手动整理入口及摘要/逐行要求编辑，仍复用原来源绑定和审核保存；仅依据 JD 填写，未编造模型结果。
- 原生 App 完成：选岗 → 读取完整 JD → 手工原文审核 → 保存 `jp_9e2ce725` → 准备默认简历快照 → 精确导航审批 → 展开正文 → 批准一次。后端 2026-09-29 22:38:32–33（上海时间）发送一次，HTTP 200 / errCode 0 / `data.result="应聘成功"`。该实际业务词未被早期规则涵盖，先保留 unknown；随后以真实无个人信息模板补失败测试，解析器版本 3 修复，在 App 点击本地核验后确认成功，没有第二次发送。
- 运行 `ar_20260929143736862627`，提交 `api-e04aadcc073846f488250555322c513f`，版本 `platform-default-f05ed38fe767`。App 显示 DONE、App 自行确认 1 / 外部观察 0；SQLite 为 success，共享 API 步骤审计通过，初始 unknown 留存。默认平台文本仅为发送前观测，不声称服务端锁定版本或发送了项目生成 PDF。
- 投递详情已保存公司、职位、审批运行、Lead 和简历版本，并能返回原审批；发现旧 retry 会改写 API 日志，先复现再禁止该路径。原生 App 重启后实测 API 重试禁用、详情版本及返回精确运行链接，成功数仍为 1。Token 自动复用，没有重新录入/删除，未接钥匙串。
- 98 项相关后端/组件回归、前端构建通过。真实证据：`outputs/acceptance/official_delivery_prerequisites/default-resume-app-closed-loop-20260929.json`。本次新增 1 次真实发送；累计实际确认 2 次，App 自行确认 1 次，历史外部观察确认 1 次。10 岗位 App 验证目标进度 1/10。
- 本轮完成默认简历单笔“岗位审核—审批—API 发送—回执恢复—持久化追踪”切片。其余 9 个 App 岗位、项目生成 PDF 绑定、通用 L3 场景与真实结果后的反馈迭代仍待完成；不把此切片升级为整个 evidence-first 生成/反馈链已完成。P0-017A 保留唯一 next，但回执词识别、审批成功链已不再列为未解决问题。

## 2026-09-29 纠正产品边界并接通 App 默认简历审批入口

- 用户明确目标是开发 App，开发代理代为控制招聘网站完成投递不符合目标。本轮停止网站操作，外部自动化仅用于原生 App 验收；不新增真实投递，不修改 Token 或引入钥匙串。
- 纠正上一阶段尚未入账的事实：用户“都试下”后，App 后端对上海帝奥微“高级数字验证工程师（高速）”调用默认简历接口一次，HTTP 200 / errCode 0 / 字符串结果被保守判为 unknown。随后由开发代理查看网站投递历史，观察到 2026-09-28 23:24 已投递，并通过外部核验工具写回实际成功。实际发送事实保留，但该过程不符合 App 自行确认回执与闭环验收。原运行 `ar_default_resume_20260928152118`、初始 unknown 事件、外部记录及成功防重均保留，不得重投。
- 同阶段曾在另一个“昇阳智慧 SOC 验证负责人”网站聊天页触发平台自动问候；没有发送生成 PDF。该动作属于 App 外副作用，不能计投递/PDF 路线通过。本轮不继续网站探索。
- 探索复用：Jobs 已有官方 Lead/Profile 绑定，Agent 已有快照、审批续跑和持久化防重，缺口是 App 内创建真实默认简历审批任务的入口。现增加 `run.agent.prepareLiepinDefault`，前端仅传 Lead ID；后端先审核/排除/防重，重读 JD 与平台简历，固定文本观测快照，写入 pending 队列和运行。准备不发送，批准后才由已有通道执行；相同未变化 pending 复用，跳转精确 run_id。未评估分数为 null，不把缺证据当低匹配。
- 结果分别计实际确认、App 自行确认、外部观察确认；历史网站观察读回为 `EXTERNAL_CONFIRMATION_ONLY`，原始事件不重写，未知来源成功保持阻断。外部核验工具明确为历史人工事实入口，不提供产品 RPC；共享 SubmissionRecorder/L3 成功门禁拒绝用外部观察证明 App 自动回执。
- 验证按先红后绿完成：65 项相关后端、组件及验收契约回归通过，前端构建及 v2/路线图/AIEF 检查通过。原生调试 App 重启后实测历史显示 App 0 / 外部 1、已投递岗位准备被拦截、未审核岗位按钮禁用；未读取招聘网站。准备成功/精确导航目前只有隔离后端与组件测试证据，不宣称原生成功链已通过。记录在 `outputs/acceptance/official_delivery_prerequisites/app-review-boundary-20260929.json`。
- 当前实际确认 1 次，其中 App 自行确认 0 次、外部观察确认 1 次；10 岗位 App 闭环仍为 0/10。原生新岗位准备成功链、未知字符串业务回执的程序核验、生成 PDF 附件绑定仍待完成；P0-017A 保持唯一 next，P0-017 保持 blocked。

## 2026-09-28 审批快照、恢复执行与投递防重

- 用户继续推进 P0-017A。已先探索 AgentLoop、原审批队列/RPC、PDF exporter、通道路由与 SubmissionRecorder；复用原队列和页面，补齐“只有版本名称、批准仅改状态”的缺口，没有另建投递引擎或开启官方写接口。
- 手动 REVIEW 入队前固定 Markdown/PDF 与目标清单，保存 run/candidate、平台 ID/type、JD 指纹和文件指纹。恢复时验证目标及文件，审批后不重新生成；损坏/缺失的旧队列不能批准，仍可拒绝/跳过。UI 展示固定版本正文与校验状态，重开页按最近更新时间恢复正确队列。
- 审批整批先校验再原子持久化，增加进程互斥、重复批准幂等、拒绝/跳过不可改回批准、已有队列不可覆盖。批准后从快照恢复执行，并把检查/阻断/未知/成功分别写回运行状态与页面；检查批次不能升格为发送。恢复前重查企业/主体排除名单，guided batch 也不再忽略已保存名单。
- 实际通道调用前按稳定平台岗位键写 SQLite `in_flight` 占位，键不含运行编号或简历版本；成功/明确失败/未知持久保存，重启或换版本不自动重发。只有明确 `not_submitted` 的本地检查结果释放占位；异常、缺回执或已有未决记录暂停后续岗位。官方写契约未验证时在占位前阻断，审批恢复不降级邮件。
- 严格先红后绿覆盖正文/PDF/目标变更、导出失败、并发占位、重复批准、整批非法输入、名单变化、未知后暂停、队列覆盖和恢复排序；120 项相关单测/组件回归、前端构建、v2/路线图/AIEF/差异检查通过。测试数据为隔离合成样本，未将 mock 或通道 spy 当真实投递。
- 外部 CUA 在真实调试 App 验证自动恢复队列、展开固定正文、批准后“检查通过，未发送”、官方契约未核实时“未发送”，离开再进入后两项结果保留。样本明确标注非真实企业，使用真实本机 PDF 导出，但不是用户简历，未访问平台发送接口；运行 `ar_20260928_review_snapshot_acceptance` 的成功数为 0。证据为 `outputs/acceptance/official_delivery_prerequisites/review-resume-20260928.json`。
- 再次只读核对官方仓库 HEAD 仍为 `858a62bd839d490e8745b7503961e4676a54b9d7`（2026-04-13），`ApplyJobInput` 仍仅 `jobId/jobKind`，未见指定附件/版本入参：[官方模型](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/liepin_cli/models/job.py)。已向用户明确两条下一步路线：接受平台接口默认发送的简历，先测试既定上海帝奥微岗位；或坚持项目生成 PDF，继续补附件路线。选择尚待回复，不将此问题解释为已获默认简历发送授权。
- 本地审批前置切片完成；实际岗位审核/简历准备、发送内容与权威回执绑定、API L3 仍待收口。P0-017A 保持 next，P0-017 仍 blocked，十岗位真实投递继续为 0/10；本轮没有删除或改写真实 Token。

## 2026-09-28 本机凭据真实恢复与高薪测试候选准备

- 用户已在 App 保存真实 Token。原生设置页显示只读连接有效；独立后端进程从本机权限文件恢复为 `unverified`，仅返回配置状态，核对目录 `0700`、文件 `0600`。随后重启当前调试 App，原生状态自动恢复为待验证，点击验证后再次成功；没有要求重填、没有清理或修改保存项，也未访问钥匙串。
- 通过原生 Jobs 搜索“芯片验证”得到 20 条真实官方线索，并实际载入帝奥微完整 JD。真实接口已返回 `salary/location`，原有导入实现丢弃这两项；本轮先复现失败测试，再补导入、落盘、回读及列表/详情展示。缺失显示未提供，不猜薪资；错误类型在写入前拒绝；重搜保留完整 JD、审核与画像关联。规范、RPC、DESIGN、`.pen` 与中英文同步。
- 三页官方只读搜索共观察 60 条岗位，按标注月薪下限至少 35k 初筛 12 条，再由现有公开详情适配器取得 7 份完整 JD、5 份明确不可用。候选仍未完成全量匹配评分、审核或授权版本准备，不能把此列表称为已批准的 10 个投递目标；资料在 `outputs/acceptance/official_delivery_prerequisites/ten-job-candidates-20260928.json`。
- 重载后的原生列表与详情已显示官方薪资/地区。上海帝奥微“高级数字验证工程师（高速）”（40–70k·15薪、上海-航华）已通过真实 App 读取 502 字完整 JD、调用本地模型解析并点击保存未完整；原 Lead 关联 `jp_7d29bd35`，状态 `saved_incomplete`，无批准标记，原文/指纹一致。没有把模型解析或草稿保存当作人工审核通过。
- 原生读取解析结果的 AX 曾超时，改用实际截图确认结果并保存草稿；未重复点击提交、未将超时当作解析失败。相关导入/绑定/UI 回归 54 项、前端构建、v2/路线图/AIEF/差异检查通过。本轮无平台写请求，十岗位批次仍为 0/10；审批续跑、实际发送版本和回执契约仍待 P0-017A 收口。

## 2026-09-28 猎聘凭据保存约束

- 用户明确要求不接入钥匙串，并选择“本地权限文件，接受明文保存”；既有 OS credential store 规划不作为启用钥匙串的授权。此前只有内存会话，而且只读验收主动清理过凭据，不能把未配置归因于平台 Token 过期。
- 已实现专用本地文件存储：macOS 固定 `~/Library/Application Support/PiProofForge/credentials/liepin-token`，目录 `0700`、文件 `0600`。不随仓库、工作目录或调试 App 标识变化，不写普通配置、前端持久化或日志；未新增依赖或改全局工具配置。
- 保存先校验再原子替换，失败保留旧凭据；拒绝符号链接、不正确权限/属主、非普通文件及硬链接。后端构造无文件读取，首次使用恢复为 `unverified`；真实只读请求才能确认有效。正常 shutdown 和 EOF 退出只释放内存，用户主动删除才移除文件；存储失败返回固定安全错误，不假报成功。
- UI 同步本机保存路径、明文权限说明、“保存到本机”与“删除已保存凭据”。读取/删除失败仍保留可操作的删除入口；后端状态与输入均不回显 Token。规范、RPC、DESIGN 与 `.pen` 已同步。
- 先红后绿验证文件权限、保存/删除失败、恢复及非法输入保留旧值；隔离目录与合成 Token 的真实 stdio 跨进程验证覆盖 shutdown、EOF、新进程恢复及主动删除。pytest 全局隔离凭据单例，禁止测试读取或删除真实用户保存项。118 项相关测试、前端构建、v2/路线图/AIEF/差异检查及独立审查通过。
- 已通过外部 CUA 重载当前调试 App，并在原生通道页核对新路径、按钮与未配置状态。原生验证只证明部署/回读生效，保存/重启恢复证据来自隔离目录的真实后端进程；没有用真实用户 Token 做删除测试，也未发平台请求。当前仍需用户在 App 保存一次真实 Token；不会把本次持久化修复算作十岗位批次成功或 P0-017A 整体完成。

## 2026-09-28 十岗位真实闭环验证批次：前置检查

- 用户要求投递 10 个岗位，明确筛选偏好是低 JD 匹配度、高薪待遇；随后说明目的为验证闭环，尽量避免影响未来正式求职。记录为本次验证批次目标，不把低匹配解释为高匹配，不修改长期每日 3 次的自动投递计划。低匹配仍可能留下平台与企业投递记录，不能保证无后续影响。
- 执行顺序为先取得第 1 条真实闭环证据，再继续至本批次 10 条；未知结果停下核验，不重复发送。使用真实个人经历与证据，保留匹配分和缺口，不伪造能力、不把模拟/检查模式计入成功；网页代投也不能证明项目自身链路通过。
- 只读盘点现有 19 条官方线索：均未保存薪资、城市；18 条仅摘要，唯一完整 JD 快照未审核且此前刷新不可用。现有旧匹配分不能移用于这些新线索，因此尚未产出可信的十岗位排序或选择投递目标。
- 本轮原生 App 已确认猎聘官方 Token 为未配置，旧浏览器投递会话也缺失；已将 App 留在系统设置通道页，请用户在本机配置并验证凭据，未读取网站 Token 或要求在聊天发送密钥。模型配置仍为已配置的本地 Qwen3.8。
- 已复核实际发送入口：官方来源仍返回 `official_delivery_contract_unverified`，旧浏览器聊天发送仍受 `resume_attachment_binding_unverified` 保护。发送版本、真实回执、审批续跑与持久化防重仍按 P0-017A 补齐，未绕过阻断或将既有验收状态提升。
- 本轮尚未发起真实提交，已确认成功数为 0/10；P0-017A 保持当前任务，P0-017 继续 blocked。

## 2026-09-28 配置本地 LM Studio Qwen3.8

- 用户指定本地 LM Studio 的 Qwen3.8。已只读确认服务在 `127.0.0.1:1234`，并复用已加载的 `qwen/qwen3.8-27b`（MLX/safetensors、4bit），没有下载、加载替代模型、升级工具或改全局配置。
- 通过真实 App 模型页配置并保存 `provider=lm_studio`、`base_url=http://127.0.0.1:1234/v1`、上述模型 ID、120 秒超时与原温度 0.2；使用本地占位凭据。连接检查返回 14 个模型，重启调试后端后的原生回读一致；非 LLM 配置的规范化指纹保持不变。
- 真实调用定位并最小修复兼容问题：本机 LM Studio 拒绝 `json_object`，改为其支持的对象 `json_schema`；仅对已验证的精确 Qwen3.8 ID、旧 JSON 模式转换且调用方未显式指定时，在本次请求加入 `reasoning_effort=none`。不改服务器默认高推理配置，不读取 reasoning 充当业务结果，不自动重试或放宽校验。依据：[LM Studio 结构化输出](https://lmstudio.ai/docs/developer/openai-compat/structured-output)。
- 真实 JD 输出又暴露 optional 字段类型不明确的问题；已为 Jobs 提供现有字段契约的 schema 并明确 prompt 类型，原必需字段和业务验证保持不变。Jobs/Evidence 使用共享 provider 兼容层，其他服务商/显式格式/输入字典不变；新增测试先红后绿，110 项单测、18 项子测试及独立复核通过，v2/路线图/差异检查通过。
- 使用真实生产 Jobs handler 调用本地 Qwen3.8，已保存的 294 字 JD 在 10.62 秒返回 `draft_ready_for_review/OK`：9 条 must-have、14 个关键词，数组类型有效、原文和原岗位引用保持一致，缺项为空；没有保存或批准草稿，`active_target_eligible=false`。
- 本轮原岗位网页刷新返回不可用，故推理验证明确使用已有 JD 快照；配置保存/回读为原生验收，实际推理为真实后端调用，不冒充原生解析→审核→保存全链通过。证据：`outputs/acceptance/official_delivery_prerequisites/lmstudio-qwen38-20260928.json`，不含密钥、JD 正文或模型原始输出。P0-017A 仍未完成，真实投递继续阻断。

## 2026-09-28 P0-017A 首片：完整 JD 与原岗位绑定

- 沿已有 Jobs 草稿审核、原 Lead/Profile、Candidate 和投递通道实施，没有开启平台写接口。公开详情新增 `tools/infra/liepin_job_detail.py`：匿名 HTTPS、无 Token/Cookie、拒绝重定向/验证码/登录/下架页、20 秒/2 MB 上限；精确选 JobPosting，核对其原始 identifier 与 DOM 正文，不从 URL 展示数字猜岗位 ID，也不把 SEO 描述当完整 JD。
- 已接 `jobs.fetchLiepinDetail` 与原生 Jobs“获取完整 JD”，把正文/指纹写回原 Lead 并填入原审核区。生成/保存传原 Lead/Profile 引用，后端保留平台身份和来源公司；重复转换/保存复用稳定关联，不另建 manual Lead。普通编辑保留来源，关键内容变更撤销审核，重搜保留正文和关联；仅跟踪参数变化不使审核失效，不同职位路径仍阻断。
- 新增共享绑定校验，官方候选需完整已审画像、来源身份/JD 指纹和本次运行画像一致；App 与 CLI 都消费相同边界，显式无合格已选项不回退其他岗位，REVIEW 保留原身份/画像/JD 指纹。独立审查发现 CLI 自动发现错配画像和 URL 跟踪参数误使审核失效，均先复现后修复并复核通过。
- 通道按明确平台/已知 HTTPS 主机选择，不再用职位方向当渠道；一次只调用匹配通道，结果未知不重试、不转邮件。官方来源在 PDF/浏览器之前返回 `official_delivery_contract_unverified`，防止只读来源误走旧投递。设置页同步为可选通道，不再宣告自动邮件降级。
- 外部 CUA 在真实调试 App 选择一条已保存的官方 Java 线索并点击获取：294 字规范化正文成功载入，职责/要求存在，原岗位来源绑定可见。当前记录为 `full_unreviewed`，正文 hash 与落盘值一致，尚无已审核关联画像，候选门禁为 false；没有将该岗位批准投递。
- 真实点击“解析岗位描述”返回模型配置阻断（当前 provider 地址/凭据未配置），原文与绑定保留。已请用户在 App 配置现有模型；本轮未擅自选择付费模型、安装工具或填写密钥。完整解析→人工审核的真实链仍待验证，单测通过不代替该步骤。
- 有关原岗位绑定/编辑/重搜、CLI/App 画像一致性、严格路由和失败处理的相关回归共 235 项通过；前端构建、v2/路线图/AIEF/差异检查通过。DESIGN、`.pen` 与 RPC 契约已同步。原生首片证据：`outputs/acceptance/official_delivery_prerequisites/input-binding-20260928.json`，明确 `p0_017a_complete=false`，不保存 Token、原始岗位 ID 或 JD 正文到审计；正文只保存在业务 Lead 中。
- 本轮再次核对公开官方 CLI/MCP 仓库，未发现指定附件版本或真实成功/重复/未知回执的新契约。审批执行续跑、批准版本快照、持久化投递防重与 API recorder/L3 仍未实施/验收；当前只完成可独立推进的输入与通道路由切片。P0-017A 保持唯一 `next`，P0-017 继续 `blocked`；未发起真实投递或修改平台简历。

## 2026-09-28 P0-011 真实原生只读验收完成

- 用户要求继续后，外部 CUA 承接 App 中已配置的有效会话；本轮未亲自输入/读取 Token，也未把用户此前的输入动作写成自动化亲见。通过原生按钮重新验证连接成功，最近检查时间实际更新；读取平台简历并展开纯文本预览，只记录存在性/章节数，不保存正文。
- 在 Jobs 原生页面搜索 `Java`，实际返回 19 条、新增 19 条草稿线索；选中线索并刷新后仍从持久化记录回读。岗位库由原有 3 条变为 22 条，其中官方来源 19 个不同岗位 ID/type 键，全部 `summary_only`，来源 URL/平台身份/获取时间齐备；它们不是已审核完整 JD 或已批准投递目标。
- 最后通过原生按钮清理本地凭据：状态恢复未配置、临时简历预览消失，读取/验证按钮禁用。回 Jobs 再搜索明确显示 `AUTH_REQUIRED` 对应提示，已有线索保留；仅清除 App 内存凭据，未撤销官网 Token。窗口现停留系统设置，后续查询需用户重新配置 Token。
- 脱敏原生动作记录与落盘字段审计：`outputs/acceptance/liepin_official_readonly/native-readonly-live-20260928.json`。先前 `native-readonly.json` 保留为实施阶段的未完成快照，不回写历史；本次记录明确 P0-011 已完成，未保存 Token、简历正文、原始 AX 树或截图。业务岗位摘要保存在现有 `job_leads` 中，验收摘要不含原始岗位 ID/正文。
- P0-011 更新为 `deep_verified`。既定 S2 前置能力单列为 P0-017A `official_delivery_prerequisites`，成为唯一 `next`；P0-017 仍 `blocked`，阻断项更新为完整 JD、实际发送版本、回执、审批续跑、防重及 API 证据契约。仅登记下一步，未开始 S2 或真实投递；order 调整只改变排序，既有 P0 编号不变。
- 已先复现矩阵测试对旧 P0-017 next 的硬编码失败，再改为验证唯一 next 与 current_focus 一致；7 项矩阵验收测试、路线图与差异检查通过。HTTP 401/429/非 JSON 仍属于此前本地契约证据，本轮没有故意使真实 Token 失效，也未把这些情形声称为原生账号实测。

## 2026-09-28 猎聘授权入口修复

- 用户反馈“前往猎聘官方授权页打不开”。原入口仅 `target=_blank`，没有系统浏览器桥接；另已核对官方 CLI `liepin_cli/core/browser.py`，固定授权地址为 `https://www.liepin.com/mcp/auth`。
- 已改为无参数 Tauri host command，固定官方 HTTPS 地址并调用系统浏览器，不新增插件/依赖、不开放任意 URL。打开失败显示本地化错误和可复制地址；不触碰 Token 或浏览器安全/调试设置。
- 桥接测试先红后绿；3 项原生 launcher 测试、3 项桥接/i18n 检查、前端构建及独立审查通过。仅更新独立调试窗口，重启前确认未配置凭据且输入为空，没有替换安装版。
- 外部 CUA 已实际点击新按钮，浏览器标签页元数据确认 Chrome 打开 `https://www.liepin.com/mcp/auth`，标题“授权配置 — 猎聘 CLI”；没有读取页面内凭据。证据：`outputs/acceptance/liepin_official_readonly/authorization-link-20260928.json`。此入口切片通过，不等于网站登录或 P0-011 账号只读验收完成。

## 2026-09-28 P0-011 官方只读接入实施

- 用户明确“开工”后仅实施 P0-011。复用现有 Settings/Jobs、stdio RPC 与 Job Lead 文件；新增 `tools/infra/liepin_api.py` 标准库只读客户端和 `liepin_readonly.py` 会话内凭据状态，没有新增依赖或并行编排。
- 固定官方 HTTPS，只暴露简历读取和岗位搜索，搜索映射为 `jobName/page`；拒绝重定向、限定超时与响应大小，不自动重试。分别校验简历 `errCode/data.result` 与搜索 `code/data.list`；HTTP、业务码和结构失败返回脱敏错误，不回显原始响应或 Token。
- 原生设置页已接 Token 保存/验证/清理与平台简历纯文本临时预览；凭据只保留当前 sidecar 内存，设置回读无密钥，shutdown 清理。官方只读状态与旧浏览器投递状态独立，不开放投递。
- Jobs 已接在线搜索→既有岗位库/列表，保留平台原始 ID/type、来源 URL 与获取时间，重复搜索保留本地状态并避免重复记录。列表仅有摘要时标记 `summary_only`，转画像保存为 `saved_incomplete`，不把 URL 当完整 JD；真实详情/附件/投递仍属后续阶段。
- TDD 先红后绿覆盖 HTTP/凭据/RPC/岗位导入；独立审查发现非字符串 `jobDetailUrl` 会误保留有效状态，补复现测试后修复，并复核通过。DESIGN、`.pen`、中英 UI 与 RPC 契约已同步。
- 本地验证：sidecar、HTTP 与相关 GUI/RPC 回归 263 项通过；另 3 项既有 PDF 渲染测试在沙盒内失败，使用正常本机权限逐项复跑均通过，未修改 PDF 代码。前端构建、v2/路线图/AIEF/差异检查通过；未运行全量平台验收。
- 复用现有锁定依赖以 `--locked --offline` 编译独立 Tauri 调试窗口，没有替换安装版。外部 CUA 已看到真实后端 ready 和官方只读设置卡；未取得本次用户 Token，账号验证、简历读取、真实搜索入库及清理动作链仍待完成。分层证据位于 `outputs/acceptance/liepin_official_readonly/native-readonly.json`，明确 `complete=false`，不保存凭据或简历正文。
- P0-011 保持唯一 `next`；P0-017 继续 `blocked`。本轮未访问真实账号业务接口、修改平台简历或发起投递；用户可在已打开的「PiProofForge P0-011」窗口配置 Token 后继续只读验收。

## 2026-09-28 六平台规划落盘（用户已确认范围）

- 用户同意“猎聘、BOSS直聘、智联招聘、前程无忧 51job 四家核心 + 脉脉、拉勾两家补充”的分层建议，并明确要求六家的对接进入项目规划和目标。补充来源也属于正式交付范围，不再仅列候选或按需决定是否纳入。
- 已同步 PLAN 的量化目标/产品范围/里程碑/成功标准、现有接入方案、核心 OpenSpec、执行路线图、验收矩阵及投递流程入口；沿现有文档增量更新，没有另建平台任务台账。
- 六平台来源覆盖按每家至少 1 个真实完整 JD 样本及画像→匹配/生成→版本关联→结果追踪验收；四家核心平台的在线只读接入另验，脉脉/拉勾首版为链接+完整 JD 导入。人工导入不算 API/CLI 已接入，规划纳入不等于自动投递通过。
- 当前仍为 P0-011 唯一 `next`、P0-017 `blocked`；新增 P0-018 每日目标、P0-019–023 五个平台任务及 P0-024 六平台覆盖验收均为 `not_started`。默认顺序为猎聘闭环→BOSS→智联/51job→脉脉/拉勾，平台阻塞可以重排但保留目标。
- 每日成功投递上限在多平台启用后仍为上海自然日跨平台合计 3 次；未扩大投递授权、未开启定时任务、未安装依赖、未改业务代码或验收完成状态。
- 文档验证通过：路线图检查、AIEF L3、新增本地链接、YAML/任务依赖与差异检查；独立复核通过。原 17 个步骤内容与状态保持不变，7 个新增任务均待实施且没有声明产物存在；本轮 8 个文档文件之外的既有 WIP 未变化，未运行真实平台或业务全量验收。

## 2026-09-27 招聘平台重新调研与方案更新

以下保留本次六平台范围确认前的三平台技术调研事实；当前总体范围与顺序以上节及路线图为准。

- 本轮只更新调研、方案、规范和排期，保留现有未提交 WIP；没有实施平台业务迁移、安装/升级工具、使用账号凭据、修改在线简历或投递。
- 最新方案见 `AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md`。猎聘官方 CLI 当前公开 HEAD 仍为 `858a62b`（2026-04-13）；本轮无凭据 MCP 初始化/工具发现可用，仍为服务 1.26.0、14 个工具，投递仅 jobId/jobKind、无 outputSchema。官方声明的岗位详情尚未落到已核实的调用契约；指定附件版本和回执/反馈仍未闭合。
- 9 月 9 日官方带 Token 只读成功样本继续有效地证明当时查询成功；本轮未复验账号或凭据，不把旧样本当作当前 App 接入验收。
- BOSS/智联现有社区 CLI 骨架与上游 2.0.0 的命令、平台名、详情参数、岗位字段及错误信封不兼容。2.0.0（2026-09-15）发布包仍含 zhipin/zhilian；当前 master `cf38175`（2026-09-27）已删除智联，只留 zhipin。主线源码与发布包已分别核对，未执行上游代码；社区工具不作为平台官方 API。
- 决策：猎聘官方 HTTP 只读优先；BOSS 后续固定版本修复只读 adapter；智联独立评估维护路线，当前保留人工 JD/Job Lead。暂停 Firefox/调试浏览器兼容性主线，不引入新的云端求职编排。
- 复用现有模型、生成/PDF、Gate/Review、SubmissionRecorder 和反馈。实施缺口包括原始岗位 ID/type 与完整 JD、实际平台路由、审批续跑、API 证据契约，首次提交前最小持久化防重，以及后续上海日界成功计数/持续授权；不能把 source URL、CLI exit 0 或默认平台简历当作这些能力已完成。
- 排期同步：唯一 `next` 调整为 P0-011 `channel_session_setup`（官方凭据与只读接入）；P0-017 改为 `blocked`，依赖 P0-011 及版本/回执契约。状态变化是重新排程，不提升任何真实验收结论；旧 P0-012/013/015/016 证据只代表旧实现。
- 本轮文档验证通过：路线图检查、AIEF L3、git diff --check 与新增本地链接存在性检查；独立审查修正认证头脱敏表述、防重前置顺序和来源链接。项目 .venv 缺 PyYAML，路线图检查使用本机已有 python3/PyYAML 完成，没有安装依赖。真实 App 接入与平台读写验收留待相应实施批次。

## 已确认方向与实施边界

以下为截至 9 月 9 日的历史事实；最新任务顺序以本页 2026-09-27 记录和路线图为准。

- 2026-09-05：用户确认效率、质量与性价比约束，并要求新增内容或功能前先探索已有设计和实现；规则以仓库根 `AGENTS.md` 和 `constitution.md` 第 6、7 条为准。
- 用户同意先以猎聘单平台推进每天 3 个不同岗位的自动投递。目标边界、已有能力探索和分阶段路线见 `docs/execution-roadmap.md`；当前记录的是已确认方向，P0-017 仍待真实验收，每日定时投递尚未实现或启用。
- 2026-09-05 首批实现：复用 `SubmissionRecorder` 与 External L3 的成功步骤检查，`LiepinChannel` 仅在本次真实提交成功记录已落盘时返回 `success=true`；检查模式、dry-run 和简化模拟不消耗真实成功额度，缺少浏览器依赖明确失败。Job Lead bridge 已修复 shell 子进程传参、人工 session 确认默认值和岗位 ID 不一致阻断。
- 独立审查补齐：完整 dry-run 的模拟计数与真实成功计数分离；Job Lead bridge 按源列表原始索引选择岗位，过滤无 URL 条目后不会错选。
- 本地验证：全量 Python 测试 533 项通过；v2、路线图和 AIEF 静态检查通过；独立审查发现的两项问题已修复并复核。以上为代码/契约验证，未发生真实投递。真实验收前应先从系统已有资料与生成产物准备具体候选简历，补齐生成输入消费、PDF 版本传递及聊天附件绑定，再完成内容审核、目标授权与会话验证，不能默认要求用户在系统外提供成品 PDF。
- 简历来源复核：`PLAN.md` 第 7 节、核心规范 generation 阶段及生成/投递 workflow 明确主线为证据驱动生成；Resumes 页同时管理上传版和生成版。本地已有 `personal_profile.yaml`、材料、证据卡、生成 Markdown 和历史 PDF，但“产物存在”不等于已达投递质量。当前 GUI profile 与投递 profile 分离，legacy generation 未完整接入 Personal Profile/JD，Agent template 仅拼装证据亮点，Agent 投递端仍传 Markdown；这些是应沿原设计补齐的缺口。

## 2026-09-05 定制简历生成进展

- Quick Run 现有链路已接入简历中心个人资料、目标公司/Job Profile/JD 和定位；多行 JD 通过现有 YAML reader 完整读取。生成器只消费匹配选中的合格证据；LLM 返回证据选择，正文从事实字段拼装。
- 生成 A/B Markdown 与独立 `.trace.json`，规则评测补充正文指纹绑定的 JSON；正文不再携带内部 ID、本机路径或 source report，Quick Run 通过独立文件验证追溯，并在现有日志区展示待审核/待补充状态。无缺口提示不再误计为待办。
- 复用 PDF exporter，修复基础 writer 的 ASCII 字宽与换行不一致问题；简历中心预览已识别新生成的中文结构和联系方式。
- 已使用 `personal_profile.yaml`、三张现有业务证据卡和 `job_profiles/jp-2026-002.yaml` 的存量得物 JD，生成 `outputs/candidate_dewu_20260905/` 下的候选 A/B 版本及评测；候选 PDF 位于 `outputs/quick_runs/candidate_dewu_20260905/exports/`，一页，已渲染检查。规则评分 71/100、状态 `NEEDS_REVIEW`，不得当作已批准投递版本；规则分数主要反映字面匹配，不能据此判定用户缺乏对应能力。
- 本轮验证范围为本地真实规则 pipeline、合成数据的 LLM HTTP 协议 stub、源字段/输入指纹和 PDF 渲染；没有完成真实模型效果评估、原生 GUI 全旅程验收或实际投递。存量 JD 的当前招聘有效性未核实，原始证据卡审核状态未被自动改写。
- 用户视觉反馈：基础 writer 的纯文本排版不合格，字形不越界不等于简历版式通过。已用同一份 Markdown 和现有预览解析器生成 `outputs/candidate_dewu_20260905/layout-study/clean-resume.html`，通过已安装 Chrome 输出 `clean-resume.pdf`；样稿采用单栏、明确字重层级、项目/日期对齐及克制留白，已验证一页、全部源声明保留和可提取文本。
- HTML/CSS 样稿仍属排版方案验证，尚未切换默认 exporter。本机 Chrome 打印完成后未自行退出，本次已结束仅使用临时隔离配置的渲染进程；正式集成需补超时、进程清理及失败可见性。研究与选择依据追加在本轮生成计划中。
- 最终代码回归：544 项通过，常规 Python 环境跳过 1 项 PDFium 字形边界测试，该项已在现有文档运行时单独通过；前端构建及 v2/路线图/AIEF 静态检查通过。HTML 样稿另以 PDFium 检查视觉与文本完整性，不将这些结果记作原生 GUI 或真实投递验收。

## 2026-09-05 共享 HTML 正式接入

- 代码中的 `resume.getPreview` 与 `resume.exportPdf` 已共用 `tools/infra/export/resume_html.py` / `resume.css`；旧结构化预览仍兼容，当前前端在原预览区以 sandbox iframe 显示共享 HTML。设计文档、RPC 契约与 `.pen` 预览容器说明已同步。
- 正式 exporter 优先复用本机已有 Chromium Headless Shell，其次既有 Chrome/WeasyPrint；不自动安装依赖，不再提供静默纯文本降级。渲染在临时目录完成，校验完整输出后替换目标，失败保留旧 PDF；对超时、进程组权限限制和父进程已退出的情况已补测试。
- 当前真实 stdio JSON-RPC 已完成预览与正式导出，确认两者 HTML 完全一致；产物及证明位于 `outputs/candidate_dewu_20260905/formal-export/`。导出仍为一页，源声明完整保留，文本可提取。
- 用户授权继续后，已用 `cargo fetch --locked` 补齐锁定依赖，以 `--locked --offline` 完成桌面调试版编译；Cargo.lock 与 Node 锁文件未变化，没有升级全局工具。旧安装版与调试版同时存在，因此使用临时独立应用标识 `com.piproofforge.desktop.preview` 验收新二进制，没有替换已安装版本。
- 外部 CUA 已实际操作新 Tauri 窗口（`127.0.0.1:1420/resumes`）：读取真实个人资料、选择候选 A、查看 `about:srcdoc` 预览、填写导出路径并点击“导出 PDF”，页面返回成功路径。产物为 `outputs/candidate_dewu_20260905/formal-export/from-native-ui.pdf` 及同名 HTML；PDFium 检查一页、可提取文本和全部来源声明保留，HTML 与此前 stdio RPC 导出完全一致。结果与页面动作摘要记录在同目录 `native-file-check.json`。
- 原生验证发现并最小修复：生成文件名中的 report ID 含下划线时丢失岗位/公司关联，已先以失败测试复现再修复；历史版本列表推挤预览，已限制为 256px 独立滚动并保留原设计上下布局。实际窗口已验证滚动时预览位置稳定，设计说明和 `.pen` 同步。
- 最新全量 Python 回归 552 项通过，前端构建、路线图及差异检查通过；独立审查未发现本次切片的阻断问题。真实 PDF 测试需要正常本机进程权限，受限沙盒下的渲染启动失败已与代码回归区分。本次仅完成原生简历预览/导出切片，不代表 Quick Run 全旅程或安装包发布验收。候选仍为 71/100、`NEEDS_REVIEW`；P0-017 和每日自动投递仍未完成，未发生真实投递。

## 2026-09-05 Agent PDF 交接与附件阻断

- 探索复用：`AgentLoop._run_delivery` 原先写入共享的 `outputs/{version}.md`；已有 `ResumeExporter.export_markdown` 和共享 `markdown_to_pdf` 可直接复用。现已在每次投递尝试的独立目录保存 Markdown/HTML/PDF，并把 PDF 路径传入 `DeliveryRequest`；版本、Markdown/PDF SHA256 与路径同时写入请求 metadata 和现有 run event。导出或文件落盘失败返回 `resume_pdf_export_failed`，不进入通道、不拿旧附件补位。
- 猎聘 `_send_resume_via_chat` 原流程不消费 `resume_path`；默认“发简历”无法证明发送本次本地 PDF。真实附件入口验证和接通之前，`submit=True` 会在打开聊天前停止，记录 `resume_attachment_binding_unverified` / `blocked`，返回 16；通道和 External L3 能识别原因，不回退邮件。此处是阻断错误发送，不是附件上传能力已完成。
- 已检查存量上传 helper 与本地历史 HTML：helper 会跨页面/iframe 搜索通用 file input 和申请按钮，历史 HTML 未提供明确附件绑定证据，因此本轮没有盲接 helper。Chrome DevTools 连接器仍报 `DevToolsActivePort` 缺失；本机只读检查显示调试已启用且文件存在，尚未定位连接器与本机读取结果不一致的原因。Chrome/全局配置未修改，浏览器设置调整确认仍待用户回复。
- 本地实证：通过真实 `_run_delivery`、现有候选内容与本机 PDF 渲染器，把附件交给只捕获文件的本地通道；记录在 `outputs/agent_runs/pdf_handoff_20260905/handoff-check.json`。PDFium 检查一页、全部来源声明保留，HTML 与原生桌面导出一致。没有上传或发送简历，候选仍为 `NEEDS_REVIEW`。
- 验证：先红后绿覆盖 PDF 交接、独立目录、指纹、导出失败、未绑定附件时不点击发送和不回退邮件；单测只替代最底层渲染进程，真实本机渲染另行验证。全量 557 项通过，v2/路线图/差异检查通过，独立审查已复核。P0-017、真实附件绑定、审批续跑和每日自动投递仍未完成。

## 2026-09-06 至 09-07 App 自有会话接通

- 调整推进依据：Chrome DevTools MCP 是开发时的页面检查工具，不是 App 运行依赖；不再将修复该工具连接或修改日常 Chrome 配置列为项目门禁。沿现有 Tauri → Python sidecar → Playwright 持久化浏览器推进，复用本机已有 `.venv` 和 Chrome，没有安装或升级工具。
- 实际探索发现 `channelSession.start` 原先只写“打开登录页”记录，`check` 采信请求中的登录信号。现已由 `tools/infra/browser/liepin_session.py` 持有真实浏览器；开始配置实际导航到登录页，检查只读取后端页面信号，前端不再提交账号身份或登录结论。启动/检查失败撤销旧有效状态，历史未验证的 `session_valid` 按 `session_unknown` 读取。
- 共享正向登录判断用于 App、CLI 会话脚本和猎聘投递；职位 URL、申请按钮或登录弹窗缺席不足以判定已登录。成功检查保存并释放 profile，投递通道默认复用 App 的 `browser_profile`；显式会话环境配置仍优先。人工关窗、清理、正常关闭 sidecar 均释放对应资源。
- 审查发现同步 Playwright 在 stdio 等待期间缓存导航事件，已先复现再修复：读取缓存 URL 前通过有界 IPC 刷新。使用现有真实无界面浏览器和全请求本地拦截的页面夹具验证，修复前错误停留在登录 URL，修复后读取正向信号并释放上下文；该夹具不是猎聘真实登录验证。
- 原生 CUA 已实际点击 App 的开始配置和检查，确认专用有界面 Chrome 进程使用项目 profile。2026-09-07 再次执行 `outputs/acceptance/app_session_20260906/native-session.cua.js`，当前仍显示“需要登录”；证据和会话快照位于同目录。账号登录、短信及验证码由用户手动完成；没有上传或发送简历。
- 已完成 576 项回归、前端构建及 v2/路线图/差异检查，独立审查问题已修复并复核，设计/RPC 契约同步。P0-011 从历史 `deep_verified` 校正为本轮实际范围的 `verified_native`；真实人工登录成功、跨启动会话复用、附件绑定、审批续跑和每日 3 次投递仍未完成。原安装包未替换，本次使用重建的调试 App 和现有项目 Python 环境。
- 登录成功后继续核对系统设置页的会话状态展示：它当前仍主要依据环境变量判断配置，尚未同步 App 会话状态，不能把其“凭证缺失”与新的真实检查结果混为一谈。

## 2026-09-07 开始配置无法登录修复

- 用户实际反馈后复现两处问题：普通打开调试 App 未携带临时 Python 覆盖，回退系统 Python 后缺少 Playwright；原配置 `https://passport.liepin.com/login/` 显示“此页面似乎不存在”，可见输入框数为 0。此前只验证导航完成与未登录状态，没有覆盖普通启动和登录表单可用性，这部分验收不足。
- Rust 调试启动改为无覆盖时优先仓库已有 `.venv`；显式覆盖和发布内置 runtime 保持原逻辑。登录入口改为官网首页的实际表单，必要时点击页面已确认的登录按钮；HTTP 错误或表单缺失不再返回等待登录，已登录时复用检查。前端在失败后读回真实后端状态，避免残留“等待登录”。
- 已重建带内嵌前端的调试二进制，更新本任务的临时 `PiProofForge Dev.app`。通过 CUA 普通打开，没有提供 Python 覆盖环境变量，页面从 `tauri://localhost` 加载；实际点击开始配置成功进入等待登录。空白 profile 实测手机号和短信验证码输入框可见、可编辑，截图确认可读；没有输入凭据、验证码或发送简历。
- 证明记录：`outputs/acceptance/login_entry_fix_20260907/verification.json` 与 `login-page.png`。Rust 7 项测试通过；Python 回归与前端构建通过，独立审查未发现阻断问题；Cargo.lock 未变化，未安装或升级工具。真实账号登录和后续投递尚待用户操作后继续验证，原安装包未替换。

## 2026-09-07 至 09-08 登录页延迟跳空白

- 已按用户反馈复现：同一 main frame 从官网导航到 `about:blank`，没有新标签页、上下文关闭或 App 重启。默认 Chrome、原生窗口视口及项目原有 `make_context` 均出现；独立于 App 的浏览器同样复现。
- 只读定位到猎聘公开 `fe-lib-pc/v6/security/1.0.0/security.min.js` 的开发工具/console 检测与空白页导航逻辑；未屏蔽、改写或解锁网站脚本。之前只确认登录表单一时可见，不能证明用户有时间完成登录，先前的可用性结论已撤回。
- 已补失败识别：加载后观察 4 秒并拒绝空白重定向；检查现有空白页面明确报 `LOGIN_PAGE_REDIRECTED_TO_BLANK`，不静默重载；新上下文初始空白仍允许正常导航。独立真实浏览器确认错误被报告、上下文释放；583 项回归通过，独立审查未发现阻断问题。这只是失败处理改进，未解决兼容性。
- 兼容验证候选为现有 Playwright 1.59.0 配套 Firefox 148.0.2（v1511）。本机未安装，已执行 `install --dry-run firefox` 核对版本与缓存位置，尚未收到下载授权；没有安装或升级。下一步取得授权后先实测，再决定接入方式。
- 证据补充在 `outputs/acceptance/login_entry_fix_20260907/blank-redirect.json`。P0-011 当前状态校正为 `blocked`，真实登录、附件绑定及每日投递均未完成；App 重启后的 CUA 复核遇到 `cgWindowNotFound`，不记为新错误提示已完成原生验收。

## 2026-09-09 猎聘官方接入调研

- 已确认官方 Token + MCP/CLI 入口，调研记录在 `docs/reports/2026-09-08-liepin-integration-research.md`。用户完成普通 Chrome 人工登录并取得 Token；临时关闭远程调试后登录页稳定可见。本轮未替换 App 的 Playwright 登录实现。
- 用户在本机隐藏输入 Token 执行只读探针；`readonly-20260909T141232268064Z.json` 显示简历与搜索均返回 HTTP 200 JSON，分别为 2901 字符的 `data.result` 和 20 条 `data.list`。业务码键分别为 `errCode`、`code`；V1 脱敏未保存具体数值，已修正探针并通过本地检查，补充联网采集尚待执行。
- V2 补证据已完成：`readonly-20260909T142034159157Z.json` 确认两接口业务码均为 0；简历为 2901 字符非 JSON 文本，包含五类简历章节，未命中附件关键词；20 个岗位 ID 无重复，类型均为 `"2"`，全部字段并集仍无独立 JD 正文。只读查询成功样本已核实，不再重复跑当前探针；正式 App 集成、附件版本绑定和投递回执仍未验证。
- 搜索返回 `jobType` 而投递要求 `jobKind`；本批编码与官方枚举一致，可按原值映射，不能硬编码 `"2"`。网页支持多份附件，不等于官方 API 已能绑定特定 PDF。真实简历版本、投递回执及反馈链仍未验收，P0-011 / P0-017 状态不提升；未修改平台简历或发起投递。

## Current Acceptance Policy

- Scenario acceptance for GUI behavior must be driven by external automation against the real page, real browser boundary, or real Tauri desktop shell.
- Production pages must not contain acceptance-only environment branches, self-starting flows, page event logging hooks, or verifier controllers.
- Repository scripts must not expose embedded GUI acceptance entrypoints.
- Audit code may aggregate real artifacts, but it must not substitute for real-page scenario automation.

## Current Mainline

- System Settings: LLM provider defaults, model discovery, save/reload, masked secret behavior, and blocked local-provider failure path are covered by scenario and contract tests.
- Resumes and Evidence: material library inputs feed the evidence-first workflow and Evidence Card review contracts.
- Resumes upload UX: Resumes 页上传简历和工作材料必须支持系统文件选择器读取文件内容后上传；手填绝对路径只作为高级兜底，不能成为普通用户完成上传的唯一方式。
- Jobs: pasted JD text can create reviewed job targets for downstream matching and runs.
- Quick Run: selected eligible Evidence Cards and complete Job Profiles produce matching, resume, PDF, scorecard, and gap artifacts with traceability.
- Targeted resume product rule: 系统生成的候选人简历必须由 Personal Profile、目标公司/岗位 JD、resume positioning 和 selected Evidence Cards 共同驱动；同一版本可复用于同类岗位簇，但不是所有公司/岗位通投版本；候选人 PDF 不得包含 `Evidence trace`、本机路径、source report、内部 evidence id 或系统版本标题，追溯信息必须进入 run record / `resume_trace` / scorecard。
- Resume PDF export: Resumes 页的 `resume.exportPdf` 接受 `.pdf` 文件路径或目录路径；目录路径会自动生成 `<简历源文件名>.pdf` 并在返回值和页面提示中展示最终路径，避免把用户填写的导出目录误写成无后缀 PDF 文件。
- Agent Run: guided batch stops at review state, writes review queue artifacts, and keeps delivery disabled before approval.
- Submissions: channel session setup, check mode, submit-skipped logging, and feedback iteration are represented by sidecar contracts and real artifacts.
- Closed-loop audit reads durable artifacts from `outputs/quick_runs`, `outputs/agent_runs`, `outputs/submissions`, and `outputs/feedback_iterations`.
- External L3: `run-acceptance --level L3` now writes a guarded live blocker or real-channel result record; missing explicit authorization or missing separate final-submit confirmation never attempts external submission.
- External L3 handoff: validation records include an `operator_handoff` package with required env presence, pre-run checklist, forbidden inputs, and a redacted command template for a future authorized live run.
- External L3 authorization packet: `operator_handoff.authorization_packet` records required confirmation statements, evidence, abort conditions, redaction policy, and prohibited inputs without persisting raw confirmation values.
- External L3 pre-submit blocker diagnostics: pre-submit live blockers directly include missing readiness gates, full readiness gate results, and live input audit summaries；Markdown 报告同步展示 submit 是否允许启动、missing gates 和输入审计摘要，journey validation 会拒绝 Markdown/JSON blocker 诊断漂移。
- External L3 readiness: validation records include `live_run_readiness` gates and keep `submit_command_allowed=false` until every authorization gate and real-input validation gate passes, including URL format and local resume/profile file type checks.
- External L3 readiness semantics: post-command traceability blockers do not rewrite pre-run readiness; they are recorded in `submit_safety_decision.post_run_blocker_reason` and `live_blocker`.
- External L3 input audit: validation records include `live_input_artifacts`，用 Job URL scheme/host、文件扩展名、大小与 resume/profile SHA256 指纹绑定输入产物，同时不持久化原始 URL、确认值、文件内容或 resume/profile 文件名；人读 Markdown 报告也展示 `basename_persisted=false` 与 `raw_content_persisted=false`。
- External L3 rate limiting: validation records include `rate_limit_policy` and pass explicit rate-limit arguments to live submit commands; disabled rate limits are blocked before any external command starts.
- External L3 session readiness: validation records include `session_readiness`、`manual_session_ready_confirmed` gate 和 `manual_session_storage_ready` gate；共享渠道 session 未经人工登录或刷新确认可用，或 session 根目录不存在、Liepin 持久化会话目录不存在、目录内没有非空可识别浏览器状态标记时，真实 submit 命令不会启动，且自动化仍不得接收或保存密码、验证码或短信码。
- External L3 forbidden input audit: validation records include `forbidden_input_audit`；密码、验证码、短信码和原始密钥类 env 值永不持久化，且一旦出现就阻断在任何真实 submit 命令启动前。
- External L3 target confirmation audit: validation records include `target_confirmation_audit`；只记录 URL 岗位 ID 是否可解析、确认岗位 ID 是否提供和二者是否一致、确认 recruiter 是否提供，以及 recruiter 页面匹配必须由 `target_verify` 证明的边界；不持久化原始 ID 或 recruiter 原值，且岗位 ID 不一致时阻断在 submit 命令启动前。
- External L3 command/output audit: validation records only persist redacted live submission command and redacted stdout/stderr tails；原始 Job URL、resume/profile 路径、确认 job id 和 recruiter 不写入 command 或 output tail 证据。
- External L3 submit safety: validation records include `submit_safety_decision`；真实渠道命令是否阻断、允许待执行或已执行，必须在信任结果前成为显式可审计状态；`blocking_reason`/`post_run_blocker_reason` 必须与 `live_blocker.reason` 保持一致。
- External L3 authorization acknowledgement checklist: `operator_handoff.authorization_packet.acknowledgement_checklist` 把外部渠道授权、最终提交确认、人工 session、真实输入产物、目标确认和禁止输入映射到 env、gate、证据来源、当前状态和原值不落盘边界；`pending_acknowledgement_count` 必须在模板发布、Go/No-Go 放行和授权模板执行前清零，授权确认不再只是声明文本，未满足项不能被当作模板发布证据。
- External L3 authorization packet verifier coverage: `external_l3_authorization_packet_recorded` 同时验证无授权 no-go 态、签核清零的授权待执行态和真实渠道命令已执行态；journey report 会拒绝签核状态、0/6 计数、Markdown 展示或 runbook 指纹漂移，避免把已执行授权模板后的确认包误判为缺失。
- External L3 handoff runtime policy: `operator_handoff.runtime_options` 记录当前 channel、session/output 目录、timeout 和 headless 配置；`operator_handoff.preflight_command_template` 保持 `AUTHORIZED=false` 与 `FINAL_SUBMIT_CONFIRMED=false`，用于无授权本地预检；`operator_handoff.command_template` 使用 shell-safe 的 live 输入占位符，并写入当前运行配置与有效频控参数；Markdown 报告分开展示本地预检模板和授权真实运行模板，避免操作者覆盖 env 后交接模板回退成旧默认值或被 shell 误解析。
- External L3 preflight expectation: `operator_handoff.preflight_result_expectation` 记录本地预检的正常结果应为 `live_blocker_recorded` / `explicit_user_authorization_required`，且 `external_submission_attempted=false`、`submit_command_allowed=false`、`p0_017_complete=false`，避免操作者把预检 blocker 误判为真实失败或完成。
- External L3 preflight review checklist: `operator_handoff.preflight_review_checklist` 记录授权模板执行前必须复核的结构化清单，覆盖 validation 状态、blocker reason、外部提交未启动、submit 命令未允许、P0-017 未完成、输入审计脱敏、session、频控、证据清单、runbook 指纹和反馈追溯；Markdown 报告同步展示该清单，避免操作者只凭散落字段判断可授权执行。
- External L3 preflight review result: `operator_handoff.preflight_review_result` 根据本次 validation 实际字段逐项写出 observed 值和 pass/fail；无授权本地预检复核项全部通过时仍会把缺失的真实运行输入、session 或目标确认 gate 记录为 `authorization_decision_blockers`，并保持 `ready_for_authorization_decision=false` 与 `authorized_template_execution_allowed=false`，避免把预检通过误读成可直接请求授权或执行授权模板。
- External L3 authorization readiness action plan: `operator_handoff.authorization_readiness_action_plan` 把 `authorization_decision_blockers` 转成待补行动，覆盖人工 session、Job URL、resume PDF、profile YAML 和目标确认；每个行动都记录阻断 gate、必需证据、`blocks_authorization_decision=true` 与 `raw_live_inputs_persisted=false`，让操作者按行动补齐而不是反查 gate 名称。
- External L3 authorization intake checklist: `operator_handoff.authorization_intake_checklist` 把每个真实运行输入或确认映射到具体 env、占位符、gate、当前状态和原值不落盘边界；模板发布前必须清零，避免操作者在行动计划、env 表和命令模板之间人工拼接。
- External L3 authorized template release decision: `operator_handoff.authorized_template_release_decision` 把授权真实运行模板的展示和发布分开；待补行动未清零、授权输入接收清单未清零、授权签核待补数未清零、预检复核未允许进入授权决策、authorization packet 未就绪、显式授权或最终提交确认缺失时，保持 `template_released_to_operator=false` 与 `copy_execution_allowed=false`，并列出发布阻断项和发布前必需条件。
- External L3 live run Go/No-Go decision: `operator_handoff.live_run_go_no_go_decision` 汇总 readiness、submit safety、授权行动计划、授权输入清单、授权签核计数、模板发布决策和 P0-017 完成门禁；授权签核待补数未清零、授权模板未发布或 submit 命令未允许前保持 `go_for_live_run=false`、`submit_command_may_start=false` 与 `copy_authorized_template_allowed=false`，并把每个 no-go blocker 映射到 resolution route、证据来源和必需证据，让操作者不再跨段拼接能否启动真实运行或下一步怎么处理。
- External L3 live run execution sequence: `operator_handoff.live_run_execution_sequence` 把本地预检、预检复核、No-Go 路线处理、授权行动、授权输入、授权签核、模板发布、Go/No-Go、授权模板执行和 P0-017 完成验证排成结构化门禁；当前无授权交接包会把 `next_executable_step` 固定在 `resolve_no_go_routes`，防止操作者跳过前置步骤直接复制授权模板。
- External L3 post-command execution status: 授权真实运行模板已执行但真实渠道结果仍是 blocker 时，`operator_handoff.live_run_execution_sequence.status` 使用 `authorized_live_run_executed_pending_p0_verification`，且 `next_executable_step=verify_p0_017_completion`；这把 post-command blocker 与“尚未执行授权模板”的 ready 状态分开。
- External L3 handoff verifier coverage: `external_l3_handoff_command_template_review_recorded` 不只验证无授权 no-go 交接态，也验证真实渠道成功态和 post-command blocker 态；journey report 会拒绝 release、Go/No-Go、执行顺序或 P0-017 下一步语义回退。
- External L3 live run runbook: `operator_handoff.runbook.path` 指向 `docs/runbooks/external-l3-live-run.md`，并记录存在状态、SHA256 指纹和必需章节完整性；该中文 runbook 固化 P0-017 的授权边界、人工 session preflight、live 输入替换、blocker triage 和运行后证据复核，且声明不持久化原始 live 输入。
- External L3 handoff command review: `operator_handoff.command_template_review` 记录 `copy_paste_ready=false`、占位符替换、显式授权、独立最终提交确认、人工会话可用、session 存储就绪确认、执行顺序、预检模板不启用授权/最终提交，以及授权模板执行前必须复核预检证据；Markdown 报告同步展示命令模板复核，避免带 `AUTHORIZED=true`、`FINAL_SUBMIT_CONFIRMED=true` 与 `SESSION_READY_CONFIRMED=true` 的模板在 session 根目录不存在或 Liepin 持久化会话目录没有非空可识别状态标记时被盲贴执行。
- External L3 evidence manifest: validation records include `evidence_manifest`，统一列出 validation JSON/Markdown、关键嵌入段、中文真实运行 runbook、authorization packet、authorized template release decision、live run Go/No-Go decision、live run execution sequence、P0-017 completion gate、live blocker 或 submission log、feedback source 的必需性、存在状态和脱敏边界；authorization packet 清单项必须证明签核计数与签核清单自洽；template release、Go/No-Go 和执行顺序清单项必须同时支持 no-go 阻断态和真实渠道成功态，不能在模板已发布、Go 已放行或授权运行已执行后把有效段误标为缺失；runbook 清单项必须与 `operator_handoff.runbook` 的路径、指纹和章节完整性一致；Markdown 报告必须逐项同步展示证据清单，journey contract 会拒绝 Markdown 与 JSON 清单不一致的报告，避免人工复核时跨段拼接证据。
- External L3 outcome summary: validation records include `outcome_summary`，把 acceptance `pass` 与真实业务结果分开，区分 pre-submit blocker、post-command blocker 和 `external_validated`；顶层 acceptance step message 也区分 submit 命令未启动与命令后 blocker；真实外部验证成功前 `p0_017_complete=false`；blocker next action 必须与 `live_blocker.next_action` 一致，Markdown 结果分级必须与 JSON 结果分级一致。
- External L3 P0-017 completion gate: validation records include `p0_017_completion_gate`，把路线图完成口径结构化为 required evidence；显式授权、最终提交确认、人工 session、真实输入、外部提交、submission log 反向链接、submission log success、反馈追溯和 external_validated outcome 未全部满足前，`acceptance_pass_is_completion=false`。
- External L3 traceability: successful external commands must link `external-l3-validation.json` to persisted `submission_log.yaml/json`, and submission logs must write back `external_l3_validation_run_id/path`; missing or one-way-only links are recorded as `submission_log_not_linked`; returncode 0 with a non-success submission log is recorded as `external_channel_submission_not_success`, not `external_validated`; nonzero external commands with parseable known `submission_log_summary.error`, including `batch_cooldown`/`daily_limit_exceeded`, are promoted to exact `external_channel_*` business blockers before falling back to `external_channel_command_returned_nonzero`, and journey report validation fails if that precise mapping regresses.
- External L3 submission log path guard: validation only reads submission logs under the allowed submission output root；越界路径会记录 `outside_allowed_submission_root`，Markdown 只展示允许根目录、路径边界结论和拒绝原因，不泄露被拒绝的原始路径。
- External L3 submission log audit: submission log 会写入自身 `input_artifacts`；L3 成功要求这些指纹与 validation record 匹配，且 External L3 关联日志必须声明 `live_inputs_redacted=true` 与 `input_artifacts.job_url.raw_value_persisted=false`，原始 Job URL、resume/profile 路径字段、resume/profile 文件名、steps.detail 原文、截图路径和 HTML snapshot 引用都必须脱敏或不落盘；validation 会递归拒绝截图/HTML snapshot 字段、嵌套诊断字段或路径片段。
- External L3 trace diagnostics: `submission_traceability` 写入逐项检查结果和 `failed_checks`，Markdown 报告同步展示同一 failed checks 与 checks 表，journey validation 会拒绝 Markdown/JSON 检查表漂移，让 `submission_log_not_linked` 指向具体缺失或不匹配的证据。
- External L3 submission log summary: parsed submission logs promote status, error, mode, and a redacted last step into validation、Markdown 和 post-command blocker diagnostics so business blockers are actionable；journey validation rejects missing mode or Markdown/JSON summary drift；unsafe target_verify observed values or HTML snapshot details are replaced with a redacted placeholder before entering validation summaries.
- External L3 submission log required steps: 成功 submission log 必须包含并通过 `rate_limit`、`login_check`、`target_verify`、`submit_safety`、`chat_send_resume` 和 `submit` 步骤；否则 validation 记录 traceability blocker，而不是信任 returncode 0。
- External L3 blocker diagnostics: post-command live blockers directly include failed traceability checks, returncode, and related submission log paths so the blocker record is actionable without deep JSON lookup.
- External L3 timeout handling: timed-out live commands are recorded as `external_channel_command_timed_out` blockers with timeout seconds, redacted output tails, feedback traceability, and matching Markdown timeout diagnostics instead of failing before evidence is written.
- External L3 command launch errors: browser/driver/permission/runtime launch failures are recorded as `external_channel_command_launch_failed` blockers with redacted error type/message in JSON and Markdown, without leaking Job URL or local file paths.
- External L3 feedback trace: validation records now write `post_submit_feedback_traceability`; 真实投递结果或 live blocker 都必须成为下一步反馈动作的可追溯来源产物；blocker source reason 必须与 `live_blocker.reason` 一致，Markdown 反馈追溯必须与 JSON 的 source status/reason/next action 一致。
- External L3 Job Lead bridge: `tools.acceptance.external_l3_job_lead_bridge` can turn a validated `job_leads` candidate plus check-mode `submission_log` target-verify evidence into a redacted confirmation packet and shell-safe External L3 env template；默认保持 `PIPF_EXTERNAL_L3_AUTHORIZED=false` 与 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false`，让用户审批授权而不是手工拼接 Job URL、job id、recruiter、resume/profile 和 session 参数。

## Verification Anchors

- `constitution.md`
- `docs/acceptance-depth.md`
- `docs/execution-roadmap.md`
- `acceptance/journey_implementation_matrix.yaml`
- `tools/acceptance/acceptance_runner.py`
- `tests/acceptance/test_acceptance_runner.py`
- `tests/unit/gui/test_native_verifier_contract.py`

## Last Verified Commands

- `python3 -m pytest tests/ -q`
- `pnpm --dir ui build`
- `cargo check --manifest-path ui/src-tauri/Cargo.toml`
- `python3 tools/check_execution_roadmap.py --root .`
