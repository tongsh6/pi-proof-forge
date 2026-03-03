# GitFlow 规范

## 目的
统一分支策略、发布节奏与热修流程，确保多人协作下变更可追踪、可回滚、可审计。

## 范围
- 适用于本仓库所有代码、文档、schema 与 workflow 变更
- 适用于本地开发、PR 合并、版本发布与生产热修

## 规则

### 分支模型
- `main`：生产稳定分支，只接收 `release/*` 和 `hotfix/*` 合并
- `develop`：日常集成分支，所有 `feature/*` 先合并到此
- `feature/*`：功能或文档变更分支，从 `develop` 创建
- `release/*`：发布准备分支，从 `develop` 创建
- `hotfix/*`：线上紧急修复分支，从 `main` 创建

本项目自动化发布主流程约定为：

```text
main -> feature -> develop -> release -> main
```

分支保留策略：
- `feature/*` 合并后删除（本地 + 远端）
- `release/*` 合并后保留

### 命名规范
- `feature/<short-topic>`，例如：`feature/auto-submission-liepin`
- `release/<version>`，例如：`release/v0.2.0`
- `hotfix/<short-topic>`，例如：`hotfix/readme-link-fix`

### 提交流程
- Commit message 采用语义化前缀：`feat|fix|docs|refactor|test|chore`
- 一个 PR 对应一个明确目标；禁止把无关改动混入同一个 PR
- 合并策略默认 `squash merge`

### PR 与质量门禁
- 所有 `feature/*` 必须通过 PR 合并到 `develop`
- 所有 `release/*` / `hotfix/*` 必须通过 PR 合并到 `main`
- 合并前至少满足：
  1. `python3 tools/check_aief_l3.py --root .` 通过
  2. 相关脚本验证通过（如匹配/生成/评测路径）
  3. 文档与索引更新完整（涉及新流程或新标准时）

### 发布流程
1. 从 `develop` 切 `release/<version>`
2. 仅允许修复发布阻塞问题、文档校正、版本信息更新
3. `release/*` 合并到 `main`
4. 在 `main` 打 tag：`vX.Y.Z`
5. 将 `release/*` 回合并到 `develop`（防止发布修复丢失）

### 热修流程
1. 从 `main` 切 `hotfix/<topic>`
2. 修复后 PR 合并到 `main` 并打补丁 tag（如 `v0.2.1`）
3. 将 `hotfix/*` 回合并到 `develop`

### 保护与禁止项
- 禁止直接 push 到 `main`
- 禁止未评审合并到 `main`
- 禁止 `--force` 推主分支（如需修复历史，使用 `--force-with-lease` 且仅限非主分支）

## 输出
- 可追溯分支历史（feature -> develop -> release/hotfix -> main）
- 可审计版本标签（`vX.Y.Z`）
- 可回放发布路径（每个版本可定位到 release/hotfix PR）

## 示例

```bash
# 1) 新功能
git checkout develop
git pull
git checkout -b feature/gitflow-doc
# ... edit ...
git commit -m "docs: define gitflow process"
git push -u origin feature/gitflow-doc
# Create PR: feature/gitflow-doc -> develop

# 2) 发布
git checkout develop
git pull
git checkout -b release/v0.2.0
# ... release fixes only ...
git commit -m "chore: prepare release v0.2.0"
git push -u origin release/v0.2.0
# Create PR: release/v0.2.0 -> main
# After merge on main:
git checkout main
git pull
git tag v0.2.0
git push origin v0.2.0
# Back-merge release -> develop

# 3) 热修
git checkout main
git pull
git checkout -b hotfix/critical-eval-bug
# ... hotfix ...
git commit -m "fix: handle scorecard empty input"
git push -u origin hotfix/critical-eval-bug
# Create PR: hotfix/critical-eval-bug -> main
# Tag patch release, then back-merge hotfix -> develop
```

## 自动化脚本（跨平台）

脚本：`tools/run_gitflow_release.py`

```bash
# 从 main 开始，推动 main -> feature -> develop -> release -> main
# 默认：删除 feature，保留 release
python3 tools/run_gitflow_release.py \
  --feature auto-submission-liepin \
  --release v0.3.0 \
  --create-feature

# 仅预演，不执行
python3 tools/run_gitflow_release.py \
  --feature auto-submission-liepin \
  --release v0.3.0 \
  --create-feature \
  --dry-run
```

参数说明：
- `--feature`：支持 `feature/<name>` 或 `<name>`
- `--release`：支持 `release/<name>` 或 `<name>`
- `--create-feature`：从 `main` 创建/切换 feature 分支
- `--delete-feature` / `--no-delete-feature`：是否删除 feature（默认删除）
- `--keep-release` / `--no-keep-release`：是否保留 release（默认保留）
- `--no-push`：只做本地操作，不推送远端
