# Liepin 上传链路需要多路径回退与结构化诊断

**日期**：2026-03-04
**场景**：真实 `--submit` 运行时，页面可打开且登录态有效，但上传简历阶段频繁失败。

## 问题

仅依赖 `input[type='file']` 单一选择器会在不同 DOM 结构下失效，失败时缺少阶段级诊断信息，难以判断是未触发弹层、无 file chooser，还是 frame 内控件未暴露。

## 解决

- 上传流程改为三阶段回退：`direct -> upload_trigger -> apply_dialog`。
- 每阶段同时尝试两条路径：`expect_file_chooser` 与 file input 扫描。
- file input 扫描覆盖主页面与 `page.frames`。
- 日志 detail 汇总每阶段失败原因，便于复盘与选择器修复。

## 复现/验证

```bash
python3 -m tools.submission.run_submission --platform liepin --job-url https://www.liepin.com/job/xxxx --resume outputs/test_resume.pdf --profile profiles/candidate_profile.yaml --session-dir .sessions --output-dir outputs/submissions --timeout-ms 5000 --submit
python3 tools/check_submission_readiness.py --root outputs/submissions --platform liepin --require-status success --min-screenshots 1
```

预期：若页面结构仍不匹配，`submission_log.yaml` 中 `upload_resume.detail` 会输出各阶段诊断串，而不是单一 `upload_input_not_found`。
