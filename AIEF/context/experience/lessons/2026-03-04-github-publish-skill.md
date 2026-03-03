# GitHub 发布能力应沉淀为项目专用 Skill

**日期**：2026-03-04
**场景**：需要为仓库开源与版本发布提供可复用执行规范，避免每次临时拼接命令。

## 问题

发布流程分散在对话与文档片段中，缺少可复用技能定义，导致不同客户端（opencode/claude/cursor/github）执行口径不一致。

## 原因

- 缺少统一的项目专用 skill
- 缺少 skill 与技术文档、脚本、README 示例的同步约束落地

## 解决

- 新增 `github-repo-publish` skill 到四套目录：
  - `.opencode/skills/github-repo-publish/SKILL.md`
  - `.claude/skills/github-repo-publish/SKILL.md`
  - `.cursor/skills/github-repo-publish/SKILL.md`
  - `.github/skills/github-repo-publish/SKILL.md`
- 新增技术文档：`context/tech/GITHUB_RELEASE.md`
- 更新 `docs/standards/skill-spec.md` 与 `tools/README.md`，完成“文档 + 脚本 + 示例”闭环

## 复现/验证

```bash
python3 tools/run_gitflow_release.py --help
python3 tools/run_gitflow_release.py --feature demo-skill --release v0.0.2 --create-feature --dry-run
python3 tools/check_aief_l3.py --root .
```
