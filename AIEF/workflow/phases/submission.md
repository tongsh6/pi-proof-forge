# 自动投递流程

## 目的
将已完成匹配与生成的简历，自动转换为投递附件并完成平台投递闭环。

## 范围
- 规划平台：猎聘、BOSS直聘、智联招聘、前程无忧 51job、脉脉、拉勾均纳入项目目标；顺序和接入深度以 [执行路线图](../../../docs/execution-roadmap.md) 为准。猎聘先完成闭环，BOSS 次之，智联/51job 后续只读接入，脉脉/拉勾首版链接与完整 JD 导入。
- 输入：`outputs/resume_*.pdf`、`profiles/candidate_profile.yaml`、目标 JD URL（可来自 `job_leads/*.yaml`）
- 输出：按 run 归档的投递日志与截图（`outputs/submissions/<platform>/<run_id>/`）

> 六平台覆盖不代表六家自动投递已开放。以下浏览器流程属于既有适配路径；新接入按核心规范逐平台验证版本绑定、授权和回执，未知结果不自动重试。所有启用平台共享上海自然日内合计最多 3 次确认成功投递上限。

> 上游建议先执行 `workflow/phases/job-discovery.md`，再进入自动投递。

## 前置条件
1. 已完成 `evidence-extraction -> matching-scoring -> generation -> evaluation`
2. 候选人个人信息已结构化（建议文件：`candidate_profile.yaml`）
3. 目标平台账号可登录，浏览器会话可复用
4. 目标 JD URL 已确认且可访问（支持从 `job_leads` 批量导入）

## 步骤

### Auto 模式（默认）
1. 个人信息与事实来源：生成阶段读取简历中心个人资料、目标 JD 与选定 Evidence Cards；用户上传简历可作为导入/基准资产，不要求用户在系统外制作成品 PDF
2. 附件生成：复用 `resume.exportPdf` / `tools.infra.export.pdf_exporter.markdown_to_pdf`，将已生成的 Markdown 按共享 HTML/CSS 模板导出 PDF；此阶段只排版，不额外推断或添加事实
   - Agent 按投递尝试保存独立文件，将 PDF 路径与 Markdown/PDF 指纹交给通道；导出或落盘失败不进入渠道，也不使用旧附件。
3. 任务装配：创建投递任务（平台、JD URL、简历版本、投递策略）
4. 自动投递：通过 Playwright 执行登录态校验、职位页打开、简历上传、表单填写、点击投递
5. 结果记录：写入 `submission_log.yaml` 与 `submission_log.json`（时间、平台、岗位、状态、截图、错误信息）
6. 失败重试：按错误类型进入重试队列（网络抖动/元素变化/登录失效）

### Manual 模式
1. 系统完整执行 DISCOVER→SCORE→GENERATE→EVALUATE→GATE 五个阶段，产出 TopN 候选投递目标
2. 状态机进入 **REVIEW** 状态后暂停，等待用户在 Agent Run 页面进行审批
3. 审批面板展示每个候选的 JD 摘要、匹配分、生成简历版本等信息
4. 用户操作：
   - **approve**：候选进入自动投递队列，复用现有 Playwright 流程完成投递
   - **reject / skip**：候选标记为 `skipped`，不进入投递队列，记录原因
5. 批量审批（`batch_review=true`）：系统跑完所有轮次后统一呈现候选列表，用户一次性决策
6. 逐轮审批（`batch_review=false`）：每轮产出候选后即暂停等待审批，用户审批后继续下一轮
7. 所有候选审批完成后，状态机从 REVIEW 推进到 DELIVER，执行已批准的投递任务
## 产出
- `outputs/resume_*.pdf`
- `outputs/submissions/liepin/<run_id>/submission_log.yaml`
- `outputs/submissions/liepin/<run_id>/submission_log.json`
- `outputs/submissions/liepin/<run_id>/screenshots/*.png`

## CLI 约定
```bash
# 1) 在简历中心选择系统生成版本，使用“导出 PDF”（resume.exportPdf）
# 预览与导出共用 HTML；无可用渲染器时明确失败，不降级为纯文本简历

# 2) 自动投递（dry-run）
python3 -m tools.submission.run_submission \
  --platform liepin \
  --job-url "https://www.liepin.com/job/xxxx" \
  --resume outputs/resume_mr-2026-005_A.pdf \
  --profile profiles/candidate_profile.yaml \
  --dry-run

# 3) 自动投递（check mode，不点击提交）
python3 -m tools.submission.run_submission \
  --platform liepin \
  --job-url "https://www.liepin.com/job/xxxx" \
  --resume outputs/resume_mr-2026-005_A.pdf \
  --profile profiles/candidate_profile.yaml \
  --session-dir .sessions \
  --output-dir outputs/submissions \
  --timeout-ms 45000

# 4) 自动投递（submit mode，真实提交）
python3 -m tools.submission.run_submission \
  --platform liepin \
  --job-url "https://www.liepin.com/job/xxxx" \
  --resume outputs/resume_mr-2026-005_A.pdf \
  --profile profiles/candidate_profile.yaml \
  --session-dir .sessions \
  --output-dir outputs/submissions \
  --submit

# 5) 发布前门禁
python3 tools/check_submission_readiness.py \
  --root outputs/submissions \
  --platform liepin \
  --require-status success \
  --min-screenshots 1
```

## 验收标准
- 至少 1 个平台完成端到端自动投递（首期：Liepin）
- 投递日志可追踪（成功/失败/重试）
- 平台页面关键动作均有截图证据
- 失败任务可重放，不丢失上下文

## 边界与风险
- 平台反自动化策略可能导致流程中断（验证码、行为风控）
- 页面结构改版会影响选择器稳定性，需要定期维护
- 自动投递涉及账号安全与隐私，默认本地运行，不上传敏感信息

## 当前状态
支持 **auto/manual 双模式设计**，代码完成与真实渠道闭环分别判断。

- **App 会话**：开始配置会真实打开专用 Playwright 登录窗口；用户手动登录后点检查，由后端正向 UI 信号判定，成功保存并释放 profile。前端提供的登录信号/身份不再生效，旧的未验证有效记录降为未知。当前已验证原生打开与未登录检查，真实人工登录成功尚待验证；不依赖 Chrome DevTools MCP。

- **Auto 模式**：Liepin 单平台 CLI 保留 `dry-run`、`check mode`、`submit mode`；当前聊天入口未绑定本次 PDF，真实发送会以 `resume_attachment_binding_unverified` 明确阻断，不能使用平台默认“发简历”替代本地附件。
- **Manual 模式**：2026-09-28 已接入审批前 Markdown/PDF 固定快照、预览/校验、批准后的恢复执行及结果回读；重复批准幂等，未知结果暂停剩余项，现有队列不能被重新创建覆盖。检查模式明确未发送；官方来源仍因实际发送版本/回执契约未确认而阻断，聊天附件绑定亦未放开，不能将本地续跑检查当作真实投递成功。
- 共享 HTML 预览/正式 PDF 导出已接入当前代码并通过本地 RPC 验证；具体状态、桌面壳重建与每日 3 次投递进度以 `docs/project-ledger.md`、`docs/execution-roadmap.md` 为准。
