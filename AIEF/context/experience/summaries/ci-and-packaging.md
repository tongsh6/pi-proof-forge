# CI 与打包约定摘要

## 适用场景
- 需要调整 GitHub Actions 触发范围、减少无效 CI 消耗。
- 需要维护 Tauri 打包资源目录中的文档或工具副本。

## 关键结论
- 对 workflow 使用 `paths` 白名单，比叠加 `paths-ignore` 更短、更稳定，也更容易看出哪些改动真的会触发门禁。
- `release-notes/**` 这类不会影响门禁结果的改动，应通过不进入 `paths` 白名单的方式自然排除，而不是单独再写一层排除规则。
- `tools/README.md` 是工具文档主线；`ui/src-tauri/resources/tools/README.md` 只是 `ui/scripts/stage_python_runtime.py` staging 出来的打包副本，修改说明应回到源文档再重新 staging。

## 关联经验
- context/experience/lessons/2026-03-08-ci-path-filters-and-packaged-doc-copies.md
