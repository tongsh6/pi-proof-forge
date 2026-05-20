# 验收 runner 必须按 level 保持门禁边界

**日期**：2026-05-21
**场景**：新增 `scripts/acceptance/run-acceptance.sh` 作为用户旅程验收统一入口。

## 问题

默认 L1 runner 只执行 headless 场景/API 验证。如果同步生成 journey report 时把 L2/L3 规则也标成通过，会夸大真实验收范围，影响后续优先级判断。

## 解决

- runner 的 `acceptance-report` 记录本次实际请求的 level 状态。
- `journey-report` 只覆盖已执行 level 的规则；L2/L3 当前保持 `not_started`，直到对应实现和 verifier 接入。
- shell 入口失败时退出非零；gated `not_started` 不等同于失败。

## 复现/验证

```bash
python3 -m pytest tests/acceptance/test_acceptance_runner.py tests/acceptance/test_acceptance_runner_script.py -q
bash scripts/acceptance/run-acceptance.sh --run-id acceptance_verify_20260521 --level L1
```
