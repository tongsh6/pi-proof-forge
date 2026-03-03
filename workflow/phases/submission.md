# 自动投递流程

## 目的
将已完成匹配与生成的简历，自动转换为投递附件并完成平台投递闭环。

## 范围
- 平台：优先支持猎聘（Liepin），后续扩展 51job / 拉勾 / Boss 直聘
- 输入：`job_profiles/*.yaml`、`matching_reports/*.yaml`、`outputs/resume_*.md`
- 输出：可投递 PDF、投递日志、失败重试任务

## 前置条件
1. 已完成 `evidence-extraction -> matching-scoring -> generation -> evaluation`
2. 候选人个人信息已结构化（建议文件：`candidate_profile.yaml`）
3. 目标平台账号可登录，浏览器会话可复用
4. 目标 JD URL 已确认且可访问

## 步骤
1. 个人信息归档：从候选人简历主文档抽取姓名/联系方式/教育/工作经历概览，写入 `candidate_profile.yaml`
2. 附件生成：将 `outputs/resume_*.md` 与 `candidate_profile.yaml` 合并，生成标准 PDF
3. 任务装配：创建投递任务（平台、JD URL、简历版本、投递策略）
4. 自动投递：通过 Playwright 执行登录态校验、职位页打开、简历上传、表单填写、点击投递
5. 结果记录：写入 `submission_log.yaml`（时间、平台、岗位、状态、截图、错误信息）
6. 失败重试：按错误类型进入重试队列（网络抖动/元素变化/登录失效）

## 产出
- `outputs/resume_*.pdf`
- `outputs/submissions/submission_log.yaml`
- `outputs/submissions/screenshots/*.png`
- `outputs/submissions/retry_tasks.yaml`

## CLI 约定（规划）
```bash
# 1) 生成 PDF（规划）
python tools/run_pdf_generation.py \
  --profile candidate_profile.yaml \
  --input outputs/resume_mr-2026-005_A.md \
  --output outputs/resume_mr-2026-005_A.pdf

# 2) 自动投递（规划）
python tools/submission/run_submission.py \
  --platform liepin \
  --job-url "https://www.liepin.com/job/xxxx" \
  --resume outputs/resume_mr-2026-005_A.pdf \
  --profile candidate_profile.yaml
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
设计已落地到文档；代码实现排期：先 Liepin，后 51job。
