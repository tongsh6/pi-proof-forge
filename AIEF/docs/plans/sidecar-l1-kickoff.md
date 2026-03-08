# Sidecar L1 实施清单

> 状态：draft
> 用途：定义 Sidecar Bridge Layer 的第一批最小实现范围，使 GUI 可以连接本地 sidecar 并读取只读数据。
> 依据：`AIEF/docs/plans/backend-ui-bridge-plan.md`、`ui/design/contracts/sidecar-rpc.md`、`ui/design/DESIGN.md`

## 1. 目标

Sidecar L1 只解决一件事：

- 让 GUI 能通过 `JSON-RPC 2.0 over stdio` 与本地 Python sidecar 建立稳定连接
- 让 GUI 能调用最小只读方法，验证 bridge、错误码、生命周期和基础数据契约成立

本批次完成后，GUI 应至少具备：

- sidecar 启动 / 握手 / 心跳 / 关闭
- Evidence 页面只读列表与详情
- Policy / System Settings 的只读配置查看
- 全局 sidecar 连接状态展示

## 2. 本批次明确要做

仅允许实现以下内容：

1. `tools/sidecar/server.py`
   - stdio 主循环
   - request 读取与 response 写出
2. `tools/sidecar/router.py`
   - `method -> handler` 路由注册
3. `tools/sidecar/lifecycle.py`
   - `system.handshake`
   - `system.ping`
   - `system.shutdown`
4. `tools/sidecar/error_mapper.py`
   - 最小错误码映射：`UNSUPPORTED_VERSION` / `SIDECAR_UNAVAILABLE` / `TIMEOUT` / `VALIDATION_ERROR` / `NOT_FOUND` / `INTERNAL_ERROR`
5. `tools/sidecar/handlers/evidence.py`
   - `evidence.list`
   - `evidence.get`
6. `tools/sidecar/handlers/settings.py`
   - `settings.get`
7. 与以上文件对应的 unit tests

## 3. 本批次明确不做

以下内容不得混入 L1：

- 任意写操作：`evidence.create/update/delete/import`、`settings.update`
- 任意运行时方法：`run.quick.*`、`run.agent.*`
- 任意事件推送：`event_bus.py`、notification 广播
- Job / Resume / Submission handler
- OS credential store 真正接线
- PDF 导出
- Artifacts 与截图存储
- Rust 侧复杂进程管理增强

## 4. 允许创建的文件范围

```text
tools/
  sidecar/
    __init__.py
    server.py
    router.py
    lifecycle.py
    error_mapper.py
    handlers/
      __init__.py
      evidence.py
      settings.py
tests/
  unit/
    sidecar/
      test_server.py
      test_router.py
      test_lifecycle.py
      test_error_mapper.py
      test_evidence_handler.py
      test_settings_handler.py
```

说明：

- 若需要复用 YAML 解析逻辑，应优先调用 `tools/infra/persistence/yaml_io.py`；若 M1 尚未落地，只允许短期兼容包装，不得复制出第三份解析实现
- handler 返回结构必须与 `ui/design/contracts/sidecar-rpc.md` 完全一致

## 5. L1 方法范围

### 必做方法

| Method | 说明 |
|---|---|
| `system.handshake` | 协议版本协商、capabilities 回传 |
| `system.ping` | 返回当前 sidecar state 与时间戳 |
| `system.shutdown` | 接受优雅关闭请求 |
| `evidence.list` | 只读列表，支持最小分页/排序/筛选语义 |
| `evidence.get` | 只读详情，返回完整 `EvidenceCard + artifacts[]` |
| `settings.get` | 返回 `gate_policy` / `exclusion_list` / `channels` / `llm_config` 的只读聚合载荷 |

### 可接受的临时实现

- `evidence.list` / `evidence.get` 可直接读现有 `evidence_cards/*.yaml`
- `settings.get` 可先从环境变量与静态默认值拼装
- `channels`、`llm_config` 可先返回最小占位结构，但字段不得缺失

## 6. 设计与契约要求

- JSON-RPC envelope 必须严格遵循 `ui/design/contracts/sidecar-rpc.md`
- 所有 request 都必须要求 `params.meta.correlation_id`
- 所有 success response 都必须回传相同的 `meta.correlation_id`
- 不允许前端自己猜测缺失字段；若暂未实现数据源，也必须返回 contract 允许的空结构
- `settings.get` 中的 secret 状态必须遵守 `configured / masked / updated_at` 结构，不得返回明文

## 7. 推荐实施顺序

1. `test_router.py` -> `router.py`
2. `test_error_mapper.py` -> `error_mapper.py`
3. `test_lifecycle.py` -> `lifecycle.py`
4. `test_evidence_handler.py` -> `handlers/evidence.py`
5. `test_settings_handler.py` -> `handlers/settings.py`
6. `test_server.py` -> `server.py`

原因：

- 先锁 method 路由与错误映射，避免 server 主循环里混入业务判断
- 先锁 lifecycle，再进入具体 handler
- 最后才组装 server，可减少主循环反复返工

## 8. 退出条件

满足以下条件，Sidecar L1 才算完成：

1. GUI 可以成功完成 `system.handshake` 与 `system.ping`
2. `evidence.list` 可返回分页结果，且字段与 contract 一致
3. `evidence.get` 可返回详情与 `artifacts[]`
4. `settings.get` 可返回完整聚合载荷，secret 字段为 mask 状态
5. 所有 L1 handler 的 unit tests 通过
6. 未新增与 `sidecar-rpc.md` 冲突的字段或错误码

## 9. 不通过条件

出现以下任一情况，本批次不算完成：

- server 主循环可运行，但 response 结构不满足 contract
- `correlation_id` 未透传
- 把 YAML 解析、错误码映射、路由逻辑散落到多个文件
- `settings.get` 返回 secret 明文
- 为了赶工，提前混入写操作或事件流逻辑

## 10. 完成后的直接下一步

Sidecar L1 完成后，按以下顺序进入后续工作：

1. Sidecar L2：Evidence 写操作、Jobs / Resume / Submission 只读管理方法、`settings.update`
2. GUI Page shell batch：Evidence / Overview / Jobs 主态页面接真实只读数据
3. Sidecar L3：`run.quick.*` / `run.agent.*` + event stream

说明：

- 未完成 L1 前，不得进入 GUI 真实数据接线
- 未完成 L2 前，不得把 Resumes / Jobs / Settings 做成可提交的“半真半假”页面
