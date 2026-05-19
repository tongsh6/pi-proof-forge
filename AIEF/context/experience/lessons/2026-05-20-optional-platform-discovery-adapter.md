# Optional Platform Discovery Adapter

## 问题

多平台职位发现需要接入外部 BOSS/智联 CLI，但默认 discovery、dry-run 和单元测试不能意外启动外部浏览器或平台访问。

## 原因

现有 Liepin 搜索已经通过显式环境开关保护真实平台访问。BOSS/智联扩展也应遵守同一边界：外部 subprocess 属于 infra adapter，业务层只消费规范化结果并映射为 `Candidate`。

## 解决

- 新增 `tools/infra/discovery/boss_agent_cli.py`，把 `schema/status/search/detail --json` 类只读 CLI 调用隔离到 infra 层。
- `tools/engines/discovery/job_leads_loader.py` 只在 `PPF_ENABLE_BOSS_AGENT_SEARCH=1` 或显式参数 `enable_boss_agent_search=True` 时调用 adapter。
- 默认路径仍是 `job_leads` / `jd_inputs` / `job_profiles` fallback，不访问外部平台。
- 只读结果映射为 `Candidate(source="boss_agent:<platform>")`；投递或沟通写操作保持未启用。

## 复现/验证

```bash
python3 -m pytest tests/unit/domain/test_discovery_engine.py tests/unit/infra/test_boss_agent_cli.py -q
python3 tools/check_v2_constraints.py --root .
```

外部 CLI live smoke 需要本机安装并配置：

```bash
PPF_ENABLE_BOSS_AGENT_SEARCH=1 PPF_BOSS_AGENT_CLI="<cmd>" \
python3 -m tools.cli.entrypoints agent --policy policy.yaml --dry-run --run-id boss-agent-discovery-smoke --output-dir outputs/agent_runs --evidence-dir evidence_cards --job-profile job_profiles/jp-2026-001.yaml
```
