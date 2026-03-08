# 自动投递流程

## 目的
将已完成匹配与生成的简历，自动转换为投递附件并完成平台投递闭环。

## 范围
- 平台：优先支持猎聘（Liepin），后续扩展 51job / 拉勾 / Boss 直聘
- 输入：`outputs/resume_*.pdf`、`profiles/candidate_profile.yaml`、目标 JD URL（可来自 `job_leads/*.yaml`）
- 输出：按 run 归档的投递日志与截图（`outputs/submissions/<platform>/<run_id>/`）

> 上游建议先执行 `workflow/phases/job-discovery.md`，再进入自动投递。

## 前置条件
1. 已完成 `evidence-extraction -> matching-scoring -> generation -> evaluation`
2. 候选人个人信息已结构化（建议文件：`candidate_profile.yaml`）
3. 目标平台账号可登录，浏览器会话可复用
4. 目标 JD URL 已确认且可访问（支持从 `job_leads` 批量导入）

## 步骤

### Auto 模式（默认）
1. 个人信息归档：从候选人简历主文档抽取姓名/联系方式/教育/工作经历概览，写入 `candidate_profile.yaml`
2. 附件生成：将 `outputs/resume_*.md` 与 `candidate_profile.yaml` 合并，生成标准 PDF
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
# 1) 生成 PDF（规划）
python3 tools/run_pdf_generation.py \
  --profile candidate_profile.yaml \
  --input outputs/resume_mr-2026-005_A.md \
  --output outputs/resume_mr-2026-005_A.pdf

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
支持 **auto/manual 双模式**（设计完成，实现待落地）。

- **Auto 模式**：Liepin 单平台 CLI 已进入可执行阶段，支持 `dry-run`、`check mode`、`submit mode`，并提供发布前门禁脚本。
- **Manual 模式**：状态机 REVIEW 状态已设计，Policy 新增 `delivery_mode`（auto|manual）和 `batch_review`（bool）配置项，代码实现待落地。
