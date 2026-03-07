# Liepin 上传失败时先做页面分型与 DOM 取证

**日期**：2026-03-04
**场景**：真实 `--submit` 连续失败，且错误都集中在上传简历入口不可达。

## 问题

如果只记录一条 `upload_input_not_found`，无法区分是页面仍在职位详情、弹层未打开，还是上传控件在 frame 内/被脚本托管。

## 解决

- 在上传前增加 `page_mode` 判定（`upload_ready` / `upload_entry` / `apply_entry` / `unknown`），并基于模式调整上传阶段顺序。
- 上传失败时自动导出 `main page + frames` 的 HTML 快照到 `outputs/submissions/<platform>/<run_id>/html/`。
- 将阶段级失败串写入 `upload_resume.detail`，包含 chooser 路径与 locator 路径结果。

## 复现/验证

```bash
python3 -m tools.submission.run_submission --platform liepin --job-url https://www.liepin.com/job/xxxx --resume outputs/test_resume.pdf --profile profiles/candidate_profile.yaml --session-dir .sessions --output-dir outputs/submissions --timeout-ms 5000 --submit
python3 tools/check_submission_readiness.py --root outputs/submissions --platform liepin --require-status success --min-screenshots 1
```

预期：当上传失败时，`submission_log.yaml` 中会出现 `page_mode` 与 `dom_snapshot` 步骤，并在 `html/` 目录生成快照用于后续选择器修复。
