# 发布流程要把 release notes 作为必选输入

**日期**：2026-03-04
**场景**：项目已有一键发布流程，但默认使用 GitHub 自动生成 notes，无法保证发布说明质量与可审阅性。

## 问题

仅依赖 `--generate-notes` 会导致发布说明不可控，关键变更、迁移指引和验证结果可能缺失。

## 解决

- `tools/run_github_publish.py` 增加 `--release-notes-file`
- 默认查找 `release-notes/<version>.md`，未找到则阻断发布
- 仅在显式传入 `--allow-generate-notes` 时允许回退自动生成
- `/publish-release` 命令与 skills 示例统一要求 notes 文件参数

## 复现/验证

```bash
python3 tools/run_github_publish.py --help
python3 tools/run_github_publish.py --feature demo --release v0.1.3 --version v0.1.3 --release-notes-file release-notes/v0.1.3.md --dry-run
python3 tools/check_aief_l3.py --root . --base-dir AIEF
```
