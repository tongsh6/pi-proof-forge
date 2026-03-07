# 自动投递发布前必须加门禁

**日期**：2026-03-04
**场景**：自动投递从 dry-run 升级到真实提交后，需要防止未验证结果被直接发布。

## 问题

仅依赖人工检查容易遗漏关键证据（例如最新 run 不是 submit、没有截图、状态不是 success），导致发布质量不可控。

## 解决

- 新增 `tools/check_submission_readiness.py`，校验最新 run 的 `status`、`mode` 和截图数量。
- 在 `tools/run_github_publish.py` 增加 `--require-submission-ready` 与 `--submission-platform`，把门禁前置到发布流水线。
- 同步 `tools/README.md` 与 `AIEF/workflow/phases/submission.md`，确保命令与参数文档一致。

## 复现/验证

```bash
python3 -m tools.submission.run_submission --platform liepin --job-url https://www.liepin.com/job/xxxx --resume outputs/resume_mr-2026-005_A.pdf --profile profiles/candidate_profile.yaml --dry-run
python3 tools/check_submission_readiness.py --root outputs/submissions --platform liepin --require-status success --min-screenshots 1
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.1.5 --version v0.1.5 --release-notes-file release-notes/v0.1.5.md --require-submission-ready --submission-platform liepin --dry-run
```
