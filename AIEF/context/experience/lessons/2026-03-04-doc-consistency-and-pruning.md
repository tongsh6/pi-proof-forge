# 单目录迁移后要先做文档对齐再做冗余清理

**日期**：2026-03-04
**场景**：AIEF 迁移到 `AIEF/` 后，出现流程文档、标准文档与工具说明间的口径差异，并存在重复模式文件。

## 问题

- generation 阶段产出描述与实际脚本不一致（PDF/DOCX vs Markdown）
- `results/artifacts` 的结构约束与候选池门控混在一起，表述冲突
- patterns 目录保留了重复别名文件，增加维护噪音

## 解决

- 明确 generation 默认产出为 `outputs/resume_*.md`，PDF/DOCX 归为后置阶段
- 统一规则：提炼阶段要求字段存在；候选池阶段要求 `results/artifacts` 非空
- 删除重复文件：
  - `AIEF/docs/standards/patterns/phase-router.md`
  - `AIEF/docs/standards/patterns/experience-mgmt.md`

## 复现/验证

```bash
python3 tools/check_aief_l3.py --root . --base-dir AIEF
```
