# GitHub 发布能力

## 目标
提供项目级发布路径：仓库公开、分支流转、版本标签、Release 发布。

## 工具与脚本
- GitHub CLI：`gh`
- Git：`git`
- AIEF 校验：`python3 tools/check_aief_l3.py --root . --base-dir AIEF`
- GitFlow 自动化：`python3 tools/run_gitflow_release.py`
- Submission 门禁：`python3 tools/check_submission_readiness.py`

## AIEF 单目录模式（--base-dir）

当需要把 AIEF 资产集中到独立目录（例如 `AIEF/`）时，使用：

```bash
npx --yes @tongsh6/aief-init@latest retrofit --level L1 --base-dir AIEF
```

会在 `AIEF/` 下生成：
- `AIEF/context/`
- `AIEF/workflow/`
- `AIEF/docs/standards/`
- `AIEF/templates/`
- `AIEF/scripts/`

## 标准发布流程
1. 本地质量检查
2. 使用 GitFlow 脚本推进 `main -> feature -> develop -> release -> main`
3. 编写 release notes（`release-notes/vX.Y.Z.md`）
4. 在 `main` 打 tag（`vX.Y.Z`）
5. 创建 GitHub Release

## GitHub Actions 门禁

- `aief-l3-check.yml`
  - 触发：`pull_request`、`push` 到 `develop/main/master`
  - 路径范围：`.github/workflows/aief-l3-check.yml`、`AIEF/**`、`tools/check_aief_l3.py`
  - 目的：仅在 AIEF 资产或 checker 本身变化时运行 L3 结构校验
- `ui-packaged-smoke.yml`
  - 触发：`pull_request`、`push` 到 `develop/main/master`
  - 路径范围：`.github/workflows/ui-packaged-smoke.yml`、`ui/**`、`tools/**`、`tests/**`、`evidence_cards/**`、`matching_reports/**`、`job_profiles/**`
  - 目的：仅在可能影响 Tauri 打包、Python sidecar、bundled assets 或 smoke verifier 的改动发生时运行 macOS 打包验收
- `release-notes/**` 默认不触发上述 workflow；发布说明独立修改不应消耗重型 CI 资源

## 一键发布入口

```bash
python3 tools/run_github_publish.py --feature <feature> --release <release> --version <version> --release-notes-file release-notes/<version>.md

# 如果发布必须绑定自动投递成功证据，增加门禁参数
python3 tools/run_github_publish.py --feature <feature> --release <release> --version <version> --release-notes-file release-notes/<version>.md --require-submission-ready --submission-platform liepin
```

## 命令示例

```bash
# 1) 质量检查
python3 tools/check_aief_l3.py --root . --base-dir AIEF

# 1.1) 自动投递门禁（可选但推荐）
python3 tools/check_submission_readiness.py --root outputs/submissions --platform liepin --require-status success --min-screenshots 1

# 2) GitFlow 推进（feature 合并后删除，release 保留）
python3 tools/run_gitflow_release.py --feature auto-submission-liepin --release v0.3.0 --create-feature

# 3) 打 tag 并推送
git checkout main
git pull --ff-only origin main
git tag v0.3.0
git push origin v0.3.0

# 4) 编写 release notes
# release-notes/v0.3.0.md

# 5) 创建 GitHub Release
gh release create v0.3.0 --title "v0.3.0" --notes-file release-notes/v0.3.0.md
```

## 安全约束
- 禁止强推 `main`
- 发布前必须确保工作区干净
- 禁止提交 `.env*`、凭据文件和本地构建产物
