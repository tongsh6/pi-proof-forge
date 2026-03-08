# 2026-03-08 CI paths 过滤与打包文档副本约定

## 问题

- GitHub Actions workflow 没有记录清楚触发范围时，团队成员容易从 YAML 猜 CI 行为。
- `ui/src-tauri/resources/tools/README.md` 是打包资源目录里的副本，但它长得像普通源文件，后续维护时容易被误改。

## 原因

- `aief-l3-check.yml` 与 `ui-packaged-smoke.yml` 分别采用了不同的 `paths` 白名单，但这些规则最初只存在于 workflow 文件里。
- `ui/scripts/stage_python_runtime.py` 会把根目录 `tools/` 整体复制到 `ui/src-tauri/resources/tools/`，因此 `resources/tools/README.md` 实际上是 staging 产物，而不是文档主线。

## 解决

- 将 CI 触发规则写入 `tools/README.md` 与 `AIEF/context/tech/GITHUB_RELEASE.md`，并在 `AIEF/context/tech/REPO_SNAPSHOT.md` 反映当前 workflow 概况。
- 在 `tools/README.md` 明确声明：`tools/README.md` 是 source of truth，`ui/src-tauri/resources/tools/README.md` 是由 `python3 ui/scripts/stage_python_runtime.py` 生成的打包副本。
- 对 workflow 使用 `paths` 白名单，而不是额外叠加 `paths-ignore`；这样 `release-notes/**` 会天然被排除，规则更短也更不容易漂移。

## 复现/验证

1. 阅读 `ui/scripts/stage_python_runtime.py`，确认 `_stage_project_assets()` 会把 `tools` 复制到 `ui/src-tauri/resources/tools/`。
2. 阅读 `tools/README.md`，确认文档中已写明 source of truth 与打包副本关系。
3. 阅读 `AIEF/context/tech/GITHUB_RELEASE.md`，确认两个 workflow 的触发分支与 `paths` 范围已被记录。
4. 运行 YAML 解析检查：

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/aief-l3-check.yml"); YAML.load_file(".github/workflows/ui-packaged-smoke.yml"); puts "workflows ok"'
```

5. 确认 `release-notes/**` 不在任何 workflow 的 `paths` 白名单中，因此不会单独触发门禁。
