# 工具说明

## 证据提炼 CLI

从原始语料提炼 evidence card（基于规则的最小实现）。

### 用法
```bash
python tools/extract_evidence.py --input tools/sample_raw.txt --id ec-2026-010 --output evidence_cards/ec-2026-010.yaml
```

### 参数
- `--input` 原始语料文件路径（或 `-` 读取 stdin）
- `--id` 证据卡 id（可选）
- `--title` 标题覆盖（可选）
- `--output` 输出 YAML（可选，缺省打印到 stdout）

## 证据提炼 CLI（LLM 版）

基于 OpenAI-compatible 接口调用 LLM 生成结构化 YAML。

### 用法
```bash
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python tools/extract_evidence_llm.py --input tools/sample_raw.txt --output evidence_cards/ec-2026-011.yaml
```

### 参数
- `--input` 原始语料文件路径（或 `-` 读取 stdin）
- `--prompt` 提示词模板路径（默认 `tools/prompts/evidence-extraction.md`）
- `--model` 模型名（或环境变量 `LLM_MODEL`）
- `--base-url` OpenAI-compatible 基础地址（默认 `https://api.openai.com/v1`，或 `LLM_BASE_URL`）
- `--api-key` API Key（或环境变量 `LLM_API_KEY`）
- `--output` 输出 YAML（可选，缺省打印到 stdout）

## Workflow 脚本

```bash
# 证据提炼
python tools/run_evidence_extraction.py --input tools/sample_raw.txt --output evidence_cards/ec-2026-010.yaml

# 匹配评分
python tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-002.yaml

# 说明：默认规则打分（K/D/S/Q/E/R），可复现

# 匹配评分（LLM 版）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-003.yaml --use-llm

# 匹配评分（严格 LLM，不允许回退）
python tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-003.yaml --use-llm --require-llm

# 简历生成（模板输出）
python tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs

# 简历生成（LLM 版）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs --use-llm

# 简历生成（严格 LLM，不允许回退）
python tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs --use-llm --require-llm

# 质量评测（占位输出）
python tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml

# 质量评测（LLM 版）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml --use-llm

# 质量评测（严格 LLM，不允许回退）
python tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml --use-llm --require-llm

# 自动投递（规划中，尚未实现）
# 参考流程文档：AIEF/workflow/phases/submission.md
# python tools/run_pdf_generation.py --profile candidate_profile.yaml --input outputs/resume_mr-2026-002_A.md --output outputs/resume_mr-2026-002_A.pdf
# python tools/submission/run_submission.py --platform liepin --job-url "https://www.liepin.com/job/xxxx" --resume outputs/resume_mr-2026-002_A.pdf --profile candidate_profile.yaml

# 一键流水线（rule 模式）
python tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml

# 一键流水线（LLM 模式）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --use-llm

# 一键流水线（严格 LLM，不允许任何阶段回退）
python tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --use-llm --require-llm

# AIEF L3 检查
python tools/check_aief_l3.py --root . --base-dir AIEF

# GitFlow 自动发布（跨平台）
# 流程：main -> feature -> develop -> release -> main
# 默认策略：feature 合并后删除，release 保留
python3 tools/run_gitflow_release.py --feature auto-submission-liepin --release v0.3.0 --create-feature

# 预演模式（不执行）
python3 tools/run_gitflow_release.py --feature auto-submission-liepin --release v0.3.0 --create-feature --dry-run

# GitHub 版本发布（打 tag + 创建 release）
git checkout main
git pull --ff-only origin main
git tag v0.3.0
git push origin v0.3.0
gh release create v0.3.0 --title "v0.3.0" --notes-file release-notes/v0.3.0.md

# 一键发布（GitFlow + tag + GitHub Release + release notes）
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.3.0 --version v0.3.0 --release-notes-file release-notes/v0.3.0.md

# 一键发布预演
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.3.0 --version v0.3.0 --release-notes-file release-notes/v0.3.0.md --dry-run

# 无 notes 文件时可显式允许自动生成（不推荐）
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.3.0 --version v0.3.0 --allow-generate-notes
```

## CI 校验

- GitHub Actions: `.github/workflows/aief-l3-check.yml`
- 在 PR 与 main/master push 时自动执行 `tools/check_aief_l3.py --root . --base-dir AIEF`
