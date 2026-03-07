# Liepin 自动投递要先做职位页健康检查

**日期**：2026-03-04
**场景**：使用占位 URL（`/job/xxxx`）进行 submit 验证时，流程误判为“上传失败”。

## 问题

若页面实际是错误页（404/不可访问），上传与提交步骤都不应执行。否则会把根因误报成选择器问题，增加排障成本。

## 解决

- 在打开职位页后、登录检查前，新增 `page_health` 检查。
- 命中错误页特征（URL token 或错误页 selector）时直接 `blocked`，错误码为 `job_page_unavailable`。
- 同时导出 DOM 快照到 run 目录，保留证据用于后续复盘。

## 复现/验证

```bash
python3 -m tools.submission.run_submission --platform liepin --job-url https://www.liepin.com/job/xxxx --resume outputs/test_resume.pdf --profile profiles/candidate_profile.yaml --session-dir .sessions --output-dir outputs/submissions --timeout-ms 5000 --submit
python3 tools/check_submission_readiness.py --root outputs/submissions --platform liepin --require-status success --min-screenshots 1
```

预期：`submission_log.yaml` 显示 `status: blocked`、`error: job_page_unavailable`，并包含 `page_health` 与 `dom_snapshot` 步骤。
