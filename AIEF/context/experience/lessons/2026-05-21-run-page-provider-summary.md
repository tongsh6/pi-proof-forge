# 运行页展示模型配置摘要应复用 settings.get

**日期**：2026-05-21
**场景**：用户旅程验收要求首次配置 LM Studio 后，Quick Run 与 Agent Run 能读取 provider/base_url/model 摘要。

## 问题

如果把 LLM 配置摘要复制到 `run.quick.*` 或 `run.agent.*` 结果中，运行接口会承担配置展示职责，增加协议漂移和 secret 泄露风险。

## 解决

- System Settings 继续通过 `settings.get` 拥有 `llm_config` 的唯一只读展示合同。
- Quick Run 与 Agent Run 页面只读取 `settings.get.llm_config` 的掩码摘要，不新增 RPC 方法，不展示明文 secret。
- 验收报告将“连接检查 blocked”和“运行页可读 provider summary”拆成独立规则，避免本地模型服务未启动时误判运行页不可见。

## 复现/验证

```bash
python3 -m pytest tests/unit/gui/test_quick_run_page_contract.py tests/unit/gui/test_agent_run_page_contract.py tests/acceptance/test_scenario_first_launch_configure_lm_studio.py tests/acceptance/test_journey_contract.py -q
pnpm --dir ui build
python3 tools/check_v2_constraints.py --root .
python3 tools/check_aief_l3.py --root . --base-dir AIEF
```
