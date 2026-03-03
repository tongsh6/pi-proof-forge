# GitHub 发布能力

## 目标
提供项目级发布路径：仓库公开、分支流转、版本标签、Release 发布。

## 工具与脚本
- GitHub CLI：`gh`
- Git：`git`
- AIEF 校验：`python3 tools/check_aief_l3.py --root .`
- GitFlow 自动化：`python3 tools/run_gitflow_release.py`

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
3. 在 `main` 打 tag（`vX.Y.Z`）
4. 创建 GitHub Release

## 命令示例

```bash
# 1) 质量检查
python3 tools/check_aief_l3.py --root .

# 2) GitFlow 推进（feature 合并后删除，release 保留）
python3 tools/run_gitflow_release.py --feature auto-submission-liepin --release v0.3.0 --create-feature

# 3) 打 tag 并推送
git checkout main
git pull --ff-only origin main
git tag v0.3.0
git push origin v0.3.0

# 4) 创建 GitHub Release
gh release create v0.3.0 --title "v0.3.0" --generate-notes
```

## 安全约束
- 禁止强推 `main`
- 发布前必须确保工作区干净
- 禁止提交 `.env*`、凭据文件和本地构建产物
