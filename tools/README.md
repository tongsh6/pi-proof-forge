# 工具说明

## 证据提炼 CLI

从原始语料提炼 evidence card（基于规则的最小实现）。

说明：
- `tools/run_evidence_extraction.py` 是推荐工作流入口。
- `tools/extract_evidence.py` 是底层规则脚本，适合直接调试或最小调用。

### 用法
```bash
python3 tools/extract_evidence.py --input tools/sample_raw.txt --id ec-2026-010 --output evidence_cards/ec-2026-010.yaml
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
python3 tools/extract_evidence_llm.py --input tools/sample_raw.txt --output evidence_cards/ec-2026-011.yaml
```

### 参数
- `--input` 原始语料文件路径（或 `-` 读取 stdin）
- `--prompt` 提示词模板路径（默认 `tools/prompts/evidence-extraction.md`）
- `--model` 模型名（或环境变量 `LLM_MODEL`）
- `--base-url` OpenAI-compatible 基础地址（默认 `https://api.openai.com/v1`，或 `LLM_BASE_URL`）
- `--api-key` API Key（或环境变量 `LLM_API_KEY`）
- `--output` 输出 YAML（可选，缺省打印到 stdout）

## Workflow 脚本

## 企业例外清单

可以在仓库根目录放置 `policy.yaml`（或设置环境变量 `PPF_POLICY_PATH` 指向文件）来定义需要排除的企业名单。

支持以下字段（均为字符串列表）：

- `exclusion_list`: 简单名单，按精确匹配处理。
- `excluded_companies`: 支持 `exact:` / `contains:` 前缀。
- `excluded_legal_entities`: 简单名单，按精确匹配处理。
- 也兼容 OpenSpec 中的 `filters.excluded_companies` / `filters.excluded_legal_entities` 结构。

匹配优先级：

- `excluded_legal_entities` 优先于企业展示名/别名匹配。
- `excluded_companies` / `exclusion_list` 用于展示名、常用名、别名过滤。

示例：

```yaml
excluded_companies:
  - "exact:Acme Inc"
  - "contains:外包"
excluded_legal_entities:
  - "某某人力资源有限公司"
```

也支持：

```yaml
filters:
  excluded_companies:
    - match: exact
      value: "示例科技有限公司"
    - match: contains
      value: "外包"
  excluded_legal_entities:
    - "某某人力资源有限公司"
```

退出码约定：

- `tools/run_pipeline.py` 与 `tools/run_matching_scoring.py` 若命中企业例外清单，返回退出码 `2`。
- 命中排除时会在 `outputs/<run_id>/run_log.json`（pipeline）或 `matching_reports/run_log.json`（matching）写入 `excluded_by_policy` 事件。

## 打包副本约定

- `tools/README.md` 是工具文档的 source of truth。
- `ui/src-tauri/resources/tools/README.md` 是由 `python3 ui/scripts/stage_python_runtime.py` 在打包前 staging 出来的资源副本。
- 需要更新工具说明时，只修改 `tools/README.md`，然后重新执行 staging / build；不要直接修改 `ui/src-tauri/resources/tools/README.md`。

```bash
# 职位发现（规划，多源渠道）
python3 -m tools.discovery.run_job_discovery --city 上海 --cbd "陆家嘴,漕河泾" --output job_leads/jl-2026-001.yaml

# 证据提炼
python3 tools/run_evidence_extraction.py --input tools/sample_raw.txt --output evidence_cards/ec-2026-010.yaml

# 匹配评分
python3 tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-002.yaml

# 说明：默认规则打分（K/D/S/Q/E/R），可复现

# 匹配评分（LLM 版）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python3 tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-003.yaml --use-llm

# 匹配评分（严格 LLM，不允许回退）
python3 tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-003.yaml --use-llm --require-llm

# 简历生成（模板输出）
python3 tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs

# 简历生成（LLM 版）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python3 tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs --use-llm

# 简历生成（严格 LLM，不允许回退）
python3 tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs --use-llm --require-llm

# 质量评测（占位输出）
python3 tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml

# 质量评测（LLM 版）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python3 tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml --use-llm

# 质量评测（严格 LLM，不允许回退）
python3 tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml --use-llm --require-llm

# 自动投递（Liepin）
# 参考流程文档：AIEF/workflow/phases/submission.md
# dry-run：仅生成执行计划与日志，不打开浏览器
python3 -m tools.submission.run_submission --platform liepin --job-url "https://www.liepin.com/job/xxxx" --resume outputs/resume_mr-2026-005_A.pdf --profile profiles/candidate_profile.yaml --dry-run

# check mode：打开页面、校验登录态并执行上传/填表，但不点击提交
python3 -m tools.submission.run_submission --platform liepin --job-url "https://www.liepin.com/job/xxxx" --resume outputs/resume_mr-2026-005_A.pdf --profile profiles/candidate_profile.yaml --session-dir .sessions --output-dir outputs/submissions --timeout-ms 45000

# submit mode：真实点击投递（要求 --resume 为 PDF）
python3 -m tools.submission.run_submission --platform liepin --job-url "https://www.liepin.com/job/xxxx" --resume outputs/resume_mr-2026-005_A.pdf --profile profiles/candidate_profile.yaml --session-dir .sessions --output-dir outputs/submissions --submit

# 投递就绪门禁（要求最新一次 run 为 submit + success + 至少 1 张截图）
python3 tools/check_submission_readiness.py --root outputs/submissions --platform liepin --require-status success --min-screenshots 1

# 一键流水线（rule 模式）
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml

# 一键流水线（LLM 模式）
export LLM_API_KEY="your_key"
export LLM_MODEL="gpt-4o-mini"
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --use-llm

# 一键流水线（严格 LLM，不允许任何阶段回退）
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --use-llm --require-llm

# AIEF L3 检查
python3 tools/check_aief_l3.py --root . --base-dir AIEF

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

# 一键发布（启用自动投递门禁）
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.3.0 --version v0.3.0 --release-notes-file release-notes/v0.3.0.md --require-submission-ready --submission-platform liepin

# 一键发布预演
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.3.0 --version v0.3.0 --release-notes-file release-notes/v0.3.0.md --dry-run

# 无 notes 文件时可显式允许自动生成（不推荐）
python3 tools/run_github_publish.py --feature auto-submission-liepin --release v0.3.0 --version v0.3.0 --allow-generate-notes
```

## CI 校验

- GitHub Actions:
  - `.github/workflows/aief-l3-check.yml`
  - `.github/workflows/ui-packaged-smoke.yml`
- `aief-l3-check.yml`：在 `pull_request` 与 `develop/main/master` push 时触发；仅当 `.github/workflows/aief-l3-check.yml`、`AIEF/**`、`tools/check_aief_l3.py` 变更时运行 `python3 tools/check_aief_l3.py --root . --base-dir AIEF`
- `ui-packaged-smoke.yml`：在 `pull_request` 与 `develop/main/master` push 时触发；仅当 `ui/**`、`tools/**`、`tests/**`、`evidence_cards/**`、`matching_reports/**`、`job_profiles/**` 或 workflow 自身变更时运行 `npm run smoke:app`
- `release-notes/**` 变更不会单独触发上述 workflow；当前策略默认只对会影响门禁结果的路径执行 CI
