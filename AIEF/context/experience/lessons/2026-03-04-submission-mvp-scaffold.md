# 自动投递应先交付可验证脚手架

**日期**：2026-03-04
**场景**：需要按顺序推进自动投递能力，但真实网页自动化实现周期长。

## 问题

直接实现完整自动投递容易把参数校验、流程编排、平台适配耦合在一起，调试成本高。

## 解决

- 先交付 `tools/submission/run_submission.py` 统一入口
- 平台适配拆到 `tools/submission/liepin.py`
- 先保证 `--dry-run` 可输出完整执行步骤，形成可回归接口

## 复现/验证

```bash
python3 -m tools.submission.run_submission --help
python3 -m tools.submission.run_submission --platform liepin --job-url https://www.liepin.com/job/xxxx --resume release-notes/TEMPLATE.md --profile release-notes/TEMPLATE.md --dry-run
```
