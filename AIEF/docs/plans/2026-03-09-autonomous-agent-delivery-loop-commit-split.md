# autonomous-agent-delivery-loop 提交拆分建议

目标：在不改变现有代码结果的前提下，把当前改动拆成 4 个语义清晰的 commit，便于 review 与回滚。

## Commit 1 - core(engine/orchestration/config/errors)

建议 message：

`feat(core): implement unified v2 engine/orchestration foundation`

建议纳入文件：

- `tools/domain/invariants.py`
- `tools/domain/events.py`
- `tools/domain/run_state.py`
- `tools/errors/__init__.py`
- `tools/errors/exceptions.py`
- `tools/errors/handler.py`
- `tools/infra/logging.py`
- `tools/infra/persistence/file_run_store.py`
- `tools/config/fragments.py`
- `tools/config/loader.py`
- `tools/config/validator.py`
- `tools/config/composer.py`
- `tools/engines/**`
- `tools/orchestration/**`
- `tools/channels/**`
- `tools/check_v2_constraints.py`

命令参考：

```bash
git add tools/domain/invariants.py tools/domain/events.py tools/domain/run_state.py
git add tools/errors/__init__.py tools/errors/exceptions.py tools/errors/handler.py
git add tools/infra/logging.py tools/infra/persistence/file_run_store.py
git add tools/config/fragments.py tools/config/loader.py tools/config/validator.py tools/config/composer.py
git add tools/engines tools/orchestration tools/channels
git add tools/check_v2_constraints.py
git commit -m "feat(core): implement unified v2 engine/orchestration foundation"
```

## Commit 2 - cli compatibility and migration

建议 message：

`feat(cli): add v2 entrypoints and legacy command redirection`

建议纳入文件：

- `tools/cli/**`
- `tools/run_agent.py`
- `tools/run_evidence_extraction.py`
- `tools/run_matching_scoring.py`
- `tools/run_generation.py`
- `tools/run_evaluation.py`
- `tools/run_pipeline.py`
- `tools/extract_evidence_llm.py`

命令参考：

```bash
git add tools/cli
git add tools/run_agent.py tools/run_evidence_extraction.py
git add tools/run_matching_scoring.py tools/run_generation.py tools/run_evaluation.py tools/run_pipeline.py
git add tools/extract_evidence_llm.py
git commit -m "feat(cli): add v2 entrypoints and legacy command redirection"
```

## Commit 3 - tests and quality gates

建议 message：

`test: cover v2 flow, gate modes, fallback channels and constraints`

建议纳入文件：

- `tests/domain/test_invariants.py`
- `tests/domain/test_registry.py`
- `tests/domain/test_run_state.py`
- `tests/unit/domain/test_agent_loop.py`
- `tests/unit/domain/test_channels.py`
- `tests/unit/domain/test_check_v2_constraints.py`
- `tests/unit/domain/test_cli_entrypoints.py`
- `tests/unit/domain/test_composer.py`
- `tests/unit/domain/test_config_loader.py`
- `tests/unit/domain/test_discovery_engine.py`
- `tests/unit/domain/test_error_handler.py`
- `tests/unit/domain/test_evaluation_engines.py`
- `tests/unit/domain/test_evidence_engines.py`
- `tests/unit/domain/test_gate_review.py`
- `tests/unit/domain/test_generation_engines.py`
- `tests/unit/domain/test_legacy_entrypoint_redirect.py`
- `tests/unit/domain/test_matching_engines.py`
- `tests/unit/domain/test_orchestration.py`
- `tests/unit/domain/test_value_objects.py`
- `tests/unit/infra/test_file_run_store.py`
- `tests/unit/infra/test_logging.py`

命令参考：

```bash
git add tests/domain/test_invariants.py tests/domain/test_registry.py tests/domain/test_run_state.py
git add tests/unit/domain/test_agent_loop.py tests/unit/domain/test_channels.py tests/unit/domain/test_check_v2_constraints.py
git add tests/unit/domain/test_cli_entrypoints.py tests/unit/domain/test_composer.py tests/unit/domain/test_config_loader.py
git add tests/unit/domain/test_discovery_engine.py tests/unit/domain/test_error_handler.py tests/unit/domain/test_evaluation_engines.py
git add tests/unit/domain/test_evidence_engines.py tests/unit/domain/test_gate_review.py tests/unit/domain/test_generation_engines.py
git add tests/unit/domain/test_legacy_entrypoint_redirect.py tests/unit/domain/test_matching_engines.py tests/unit/domain/test_orchestration.py
git add tests/unit/domain/test_value_objects.py tests/unit/infra/test_file_run_store.py tests/unit/infra/test_logging.py
git commit -m "test: cover v2 flow, gate modes, fallback channels and constraints"
```

## Commit 4 - docs and release artifacts

建议 message：

`docs: finalize openspec task completion and v0.1.9 notes`

建议纳入文件：

- `openspec/changes/autonomous-agent-delivery-loop/tasks.md`
- `README.md`
- `tools/README.md`
- `AIEF/context/tech/GUI_ARCHITECTURE.md`
- `AIEF/docs/plans/2026-03-09-autonomous-agent-delivery-loop-impl.md`
- `AIEF/docs/plans/2026-03-09-autonomous-agent-delivery-loop-commit-split.md`
- `release-notes/v0.1.9.md`

命令参考：

```bash
git add openspec/changes/autonomous-agent-delivery-loop/tasks.md
git add README.md tools/README.md AIEF/context/tech/GUI_ARCHITECTURE.md
git add AIEF/docs/plans/2026-03-09-autonomous-agent-delivery-loop-impl.md
git add AIEF/docs/plans/2026-03-09-autonomous-agent-delivery-loop-commit-split.md
git add release-notes/v0.1.9.md
git commit -m "docs: finalize openspec task completion and v0.1.9 notes"
```

## 提交前统一验证

```bash
python3 -m pytest tests/unit/domain tests/unit/infra tests/domain tests/unit/pipeline tests/unit/matching -q
python3 tools/check_aief_l3.py --root . --base-dir AIEF
python3 tools/check_v2_constraints.py --root .
python3 tools/run_agent.py --policy /tmp/ppf_policy.yaml --dry-run --run-id run-final-check --output-dir /tmp/ppf_agent_runs_final
python3 -m tools.cli.entrypoints pipeline --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --run-id run-final-pipeline-2
```
