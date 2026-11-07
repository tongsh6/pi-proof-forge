# Command 规范

## 目标
统一 CLI 命令接口，便于自动化与流水线调用。

## 命令约定
- 所有脚本使用 `python3 tools/<script>.py`
- 输入参数命名统一使用 `--input/--output/--output-dir`
- LLM 模式统一使用 `--use-llm`

## 标准命令
- 提炼：`python3 -m tools.cli.entrypoints extract`
- 匹配：`python3 -m tools.cli.entrypoints match`
- 生成：`python3 -m tools.cli.entrypoints generate`
- 评测：`python3 -m tools.cli.entrypoints evaluate`
- 一键：`python3 -m tools.cli.entrypoints pipeline`
- GitFlow：`tools/run_gitflow_release.py`
- 发布：`tools/run_github_publish.py`
