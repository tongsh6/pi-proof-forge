# CI 与打包约定摘要

## 适用场景
- 需要调整 GitHub Actions 触发范围、减少无效 CI 消耗。
- 需要维护 Tauri 打包资源目录中的文档或工具副本。

## 关键结论
- 对 workflow 使用 `paths` 白名单，比叠加 `paths-ignore` 更短、更稳定，也更容易看出哪些改动真的会触发门禁。
- `release-notes/**` 这类不会影响门禁结果的改动，应通过不进入 `paths` 白名单的方式自然排除，而不是单独再写一层排除规则。
- `tools/README.md` 是工具文档主线；`ui/src-tauri/resources/tools/README.md` 只是 `ui/scripts/stage_python_runtime.py` staging 出来的打包副本，修改说明应回到源文档再重新 staging。

- 待本次独立打包切片实现：桌面包只携带应用代码与依赖；不复制 `evidence_cards`、`job_profiles`、`matching_reports` 等运行数据，也不携带 `tools/sample_raw.txt`。源码中的合成示例继续供显式 CLI 演示使用。应用资产基线本身不代表该打包目标已经完成。
- 该切片应由现有 sidecar 的空库行为承接首次启动，并让 staging 清除先前生成的资源副本，避免旧数据随新包残留。实施后分别记录打包检查与真实原生页面验收，构建成功不代表界面已验收。

## 关联经验
- context/experience/lessons/2026-03-08-ci-path-filters-and-packaged-doc-copies.md
