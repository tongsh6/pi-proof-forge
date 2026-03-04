# v0.1.4 顺序执行计划（自动投递单平台）

## 目标
在不破坏现有发布流程的前提下，先交付自动投递能力的最小可用版本（MVP）：
- 先支持单平台（Liepin）
- 先交付可复用 CLI 入口与 dry-run 能力
- 再接真实页面自动化

## 执行顺序

1. 发布准备
   - 创建 `release-notes/v0.1.4.md`
   - 明确本版本范围与非目标

2. 开发分支准备
   - 从 `main` 创建 `feature/auto-submission-liepin-scaffold`
   - 所有自动投递改动仅在 feature 分支完成

3. 提交 MVP 脚手架
   - 新增 `tools/submission/run_submission.py`
   - 新增 `tools/submission/liepin.py`
   - 新增 `tools/submission/__init__.py`
   - `--dry-run` 能输出完整执行计划

4. 文档与规范对齐
   - 更新 `tools/README.md`
   - 增加 lessons 记录（L3 要求）

5. 校验与收口
   - `lsp_diagnostics` 对修改文件零报错
   - `python3 tools/check_aief_l3.py --root . --base-dir AIEF` 通过

## 本轮完成定义
- 可直接运行：
  - `python3 -m tools.submission.run_submission --platform liepin --job-url <url> --resume <pdf> --profile <yaml> --dry-run`
- 输出包含：输入校验结果 + 执行步骤清单 + 明确“真实提交尚未启用”的提示

## 非目标（v0.1.4 不做）
- 多平台并行投递
- 验证码/风控绕过
- 云端托管执行
