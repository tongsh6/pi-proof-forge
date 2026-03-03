# Command 规范

## 目标
统一 CLI 命令接口，便于自动化与流水线调用。

## 命令约定
- 所有脚本使用 `python3 tools/<script>.py`
- 输入参数命名统一使用 `--input/--output/--output-dir`
- LLM 模式统一使用 `--use-llm`

## 标准命令
- 提炼：`tools/run_evidence_extraction.py`
- 匹配：`tools/run_matching_scoring.py`
- 生成：`tools/run_generation.py`
- 评测：`tools/run_evaluation.py`
- 一键：`tools/run_pipeline.py`
