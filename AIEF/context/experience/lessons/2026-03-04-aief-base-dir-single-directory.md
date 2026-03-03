# AIEF 初始化要支持单目录模式说明

**日期**：2026-03-04
**场景**：发布与开源文档中需要明确 `aief-init retrofit` 的 `--base-dir` 单目录模式，避免用户误以为资产总是写入仓库根目录。

## 问题

未明确 `--base-dir` 时，用户容易在现有仓库根目录直接生成 AIEF 资产，导致与原有结构混排，迁移成本上升。

## 原因

- 现有文档强调了 retrofit，但未集中说明单目录落盘能力
- skills 与技术文档缺少统一示例，跨客户端口径不一致

## 解决

- 在发布技术文档 `context/tech/GITHUB_RELEASE.md` 增加单目录模式章节
- 在四套 `github-repo-publish` skill 中加入同一命令与目录结果说明
- 在根 `README.md` 中加入中英双语示例

## 复现/验证

```bash
npx --yes @tongsh6/aief-init@latest retrofit --level L1 --base-dir AIEF
python3 tools/check_aief_l3.py --root .
```
