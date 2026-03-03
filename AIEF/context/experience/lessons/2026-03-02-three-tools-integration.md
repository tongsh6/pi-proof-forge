# 经验：三工具链集成（OpenSpec + superpowers + spec-kit）

**日期**: 2026-03-02  
**类别**: toolchain-integration  
**影响范围**: 全局工程流程

---

## 背景

在 AIEF L3 retrofit 完成后，进一步集成三个工具以建立完整的规范驱动开发闭环：
- **OpenSpec**：规范驱动开发（先写 spec，再实现）
- **superpowers**：AI 执行质量（brainstorm → TDD → review）
- **spec-kit**：项目原则守护（constitution.md 为违规红线）

---

## 关键决策与坑

### 1. OpenSpec CLI 方式
- **方式**: `npx @fission-ai/openspec@latest init --tools opencode,claude,cursor,github-copilot`
- **结果**: 一次生成 4 个 AI 工具的 skills + commands，无需手动创建
- **注意**: 如果已有 `.opencode/` 目录，命令会合并而不是覆盖

### 2. superpowers 无官方 CLI
- superpowers 没有安装命令，只是一个 SKILL.md 集合
- **正确做法**: 克隆 `https://github.com/obra/superpowers`，手动 cp SKILL.md 到各 AI 工具的 skills 目录
- **目标路径**: `.opencode/skills/<skill-name>/SKILL.md`（opencode/claude/cursor/github 各一份）
- 4 个核心技能：brainstorming、writing-plans、test-driven-development、requesting-code-review

### 3. spec-kit 的 TTY 问题
- `specify init` 需要交互式 TTY，`echo "y" | specify init` 报 `termios.error`
- **绕过方案**: 手动创建 `constitution.md` + `.specify/config.yaml`
- constitution.md 要点：使命、不可妥协原则、工具链约定、工作流入口、违规处理

### 4. SKILL.md 格式约定
```yaml
---
name: <skill-name>
description: "Use when ..."
---
# Skill Title
...
```
- description 必须以 "Use when..." 开头（AI 路由依赖这个）
- YAML frontmatter 只需 `name` + `description`，不要多余字段

### 5. 三工具统一路由
- 新功能：`/opsx:propose` → brainstorming → writing-plans → 实现
- 实现：test-driven-development skill（硬性要求）
- 完成：requesting-code-review skill
- 归档：`/opsx:archive`

---

## 成果

| 工具 | 状态 | 验证 |
|------|------|------|
| OpenSpec | ✅ 完整安装 | 4 AI 工具适配，`/opsx:propose` 可用 |
| superpowers | ✅ 4技能部署 | 所有 AI 工具的 skills 目录均已写入 |
| spec-kit | ✅ 手动初始化 | constitution.md + .specify/config.yaml 创建 |

---

## 经验总结

1. **工具选择顺序**：有 CLI 的先跑 CLI（OpenSpec），无 CLI 的手动复制（superpowers），需要 TTY 的绕过（spec-kit）
2. **skills 目录要同步**：四个 AI 工具（opencode/claude/cursor/github）的 skills 要保持一致，否则切换工具时体验不同
3. **constitution.md 是项目原则的锚**：放根目录，AI 每次看到它就知道红线在哪
4. **OpenSpec spec 先于代码**：新功能的第一步是在 `openspec/specs/` 写 spec，不是打开编辑器写代码
