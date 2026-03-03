# AIEF L1 Retrofit：对齐官方框架标准

**日期**：2026-03-02  
**触发**：用户要求对当前项目执行 AIEF L3 retrofit

---

## 背景

项目已声明 L3 等级，但对比官方 AIEF 框架（https://github.com/tongsh6/ai-engineering-framework）发现存在结构性缺口：缺少 L1 标准规定的通用 workflow phases 和部分 pattern 文件。

## 问题

`npx @tongsh6/aief-init@latest retrofit --level L1` 在已有 AGENTS.md 时直接失败（`EEXIST`），无法直接执行。`--force` 会覆盖已有的定制 L3 内容。

## 根因

官方 CLI 没有"仅新增，跳过已有文件"的选项。项目的命名约定与官方 L1 模板存在差异（如 `phase-routing.md` vs `phase-router.md`）。

## 解决方案

1. 先执行 `--dry-run` 确认变更范围
2. 识别"真正新增"与"会覆盖"的文件
3. 手动创建缺失文件，保留已有定制内容
4. 对官方命名与项目命名不同的文件，创建别名文件并引用原文件

## 新增文件清单

- `workflow/phases/proposal.md`
- `workflow/phases/design.md`
- `workflow/phases/implement.md`
- `workflow/phases/review.md`
- `docs/standards/patterns/phase-router.md`（别名）
- `docs/standards/patterns/experience-mgmt.md`（别名）
- `templates/minimal/AGENTS.md`
- `templates/minimal/context/INDEX.md`
- `context/tech/REPO_SNAPSHOT.md`（补充 `.github/` 条目）

## 验证方式

```bash
ls workflow/phases/
# 应看到: evidence-extraction.md matching-scoring.md generation.md evaluation.md
#         proposal.md design.md implement.md review.md

ls docs/standards/patterns/
# 应看到: phase-routing.md phase-router.md experience-management.md experience-mgmt.md context-loading.md INDEX.md

ls templates/minimal/
# 应看到: AGENTS.md context/
```

## 可复用结论

- **规则**：对已有 AIEF 项目执行官方 CLI retrofit，必须先 `--dry-run`，再选择性手动应用
- **规则**：命名不同但语义相同的文件，用别名文件引用，不覆盖原文件
- **规则**：L3 项目应始终保留 workflow/phases/ 下的通用阶段（proposal/design/implement/review）作为变更管理骨架
