# 发布 Skill 要有可直接调用入口

**日期**：2026-03-04
**场景**：项目已定义 `github-repo-publish` skill，但运行环境不一定支持动态加载仓库技能。

## 问题

仅有 skill 文档时，部分运行时无法直接调用新 skill，导致实际执行退化为手工命令串。

## 原因

- skill loader 在不同客户端能力不一致
- 缺少统一的可执行入口脚本

## 解决

- 新增一键发布脚本：`tools/run_github_publish.py`
- 新增直接调用命令：`/publish-release`（opencode/claude/cursor）
- 统一把发布动作收敛为：GitFlow -> tag -> GitHub Release

## 复现/验证

```bash
python3 tools/run_github_publish.py --help
python3 tools/run_github_publish.py --feature demo --release v0.1.1 --version v0.1.1 --dry-run
python3 tools/check_aief_l3.py --root . --base-dir AIEF
```
