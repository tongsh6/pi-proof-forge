# Repo Snapshot

## Tech Stack
- Language: Markdown + YAML + Python (tools)
- Framework: n/a
- Build Tool: n/a
- Runtime: Python 3

## Repo Layout (Top Level)
- /
  - .github/
  - .opencode/         # OpenSpec commands + superpowers/openspec skills (opencode)
  - .claude/            # OpenSpec commands + superpowers/openspec skills (claude)
  - .cursor/            # OpenSpec commands + superpowers/openspec skills (cursor)
  - .specify/           # spec-kit 配置
  - AGENTS.md
  - constitution.md    # spec-kit 项目宪法
  - PLAN.md
  - openspec/           # OpenSpec 规范与变更归档
  - AIEF/
  - evidence_cards/
  - job_profiles/
  - jd_inputs/
  - matching_reports/
  - outputs/
  - templates/
  - tools/
  - ui/

## Modules / Services
- name: core-docs
  - path: AIEF/context/
  - responsibility: 项目知识与技术文档入口
- name: implementation-plans
  - path: AIEF/docs/plans/
  - responsibility: 实施前计划、里程碑与任务拆分
- name: data-samples
  - path: evidence_cards/, job_profiles/, jd_inputs/, matching_reports/
  - responsibility: Phase 0 样例数据
- name: tools
  - path: tools/
  - responsibility: v2 目标结构为 domain/infra/engines/orchestration/config/channels/cli
- name: workflow
  - path: AIEF/workflow/
  - responsibility: 阶段流程定义与执行顺序
- name: standards
  - path: AIEF/docs/standards/
  - responsibility: 命名、文档、输出规范与模式沉淀
- name: ui-design
  - path: ui/design/
  - responsibility: GUI 终版设计资产与产品规范
- name: toolchain-integration
  - path: .opencode/, .claude/, .cursor/, .github/, openspec/, .specify/
  - responsibility: 三工具集成（OpenSpec + superpowers + spec-kit）

## Infra & CI
- CI: GitHub Actions (`.github/workflows/aief-l3-check.yml`)
- Docker: n/a
- Deploy: n/a

## Commands (If Known)
- build: n/a
- test: n/a
- run: python3 tools/run_evidence_extraction.py --input <file>
- run-pipeline: python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml
- run-pipeline-llm: python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --use-llm
- run-pipeline-llm-strict: python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --use-llm --require-llm
- run-agent-dry: python3 tools/run_agent.py --policy profiles/agent_policy.example.yaml --dry-run

## AIEF Entry
- AGENTS.md
- AIEF/context/INDEX.md
- AIEF/context/tech/REPO_SNAPSHOT.md
- AIEF/context/tech/architecture.md
- AIEF/workflow/INDEX.md
- AIEF/docs/standards/INDEX.md

## AIEF Level
- Current: L3 (continuous operation)
- Evidence:
  - cross-cutting patterns: AIEF/docs/standards/patterns/
  - continuous lessons: AIEF/context/experience/lessons/
  - summaries: AIEF/context/experience/summaries/
