# 2026-03-08 企业例外清单落地与门禁兜底

## 问题

- 企业例外清单仅在 settings.get 返回空数组，缺少持久化与可操作入口。
- CLI 流水线缺少 discovery 过滤与 gate 兜底，命中排除规则的公司仍可能进入匹配链路。

## 原因

- sidecar 未实现 settings.update，排除清单无法写入。
- 缺少可复用的排除过滤与 gate 判定逻辑，入口脚本各自为政。

## 解决

- 在 sidecar 增加 settings.update 支持 exclusion_list，并写入 policy.yaml / PPF_POLICY_PATH。
- 新增 discovery 过滤与 gate 兜底的共享逻辑，并在 run_pipeline / run_matching_scoring 接入。
- 明确退出码 2 表示命中企业例外清单。

## 复现/验证

1. 设置排除清单：

```bash
export PPF_POLICY_PATH="/tmp/policy.yaml"
cat <<'EOF' > /tmp/policy.yaml
exclusion_list:
  - "Acme Inc"
  - "contains:Outsource"
EOF
```

2. 运行单元测试：

```bash
python3 -m pytest tests/unit/policy/test_gate.py tests/unit/discovery/test_filters.py tests/unit/sidecar/test_settings_handler.py
```

3. 使用包含排除公司名的 job_profile，运行 `tools/run_pipeline.py` 或 `tools/run_matching_scoring.py`，应返回退出码 2。
