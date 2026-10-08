# 投递成功与候选交接的验证边界

## 问题与原因

- 猎聘检查模式也返回退出码 0，通道据此误报成功；缺少浏览器依赖又回退为模拟成功，Agent 将这些结果累计为已投递。
- Job Lead bridge 只输出 shell 变量赋值，子进程收不到参数；session 文件存在被错误转换为人工确认登录有效。

## 解决

复用 `SubmissionRecorder`，将 External L3 已有的成功步骤检查下沉共享。真实成功同时要求本次记录落盘、submit 模式、成功状态、无错误和全部关键步骤成功；Agent 只累计 `DeliveryResult.success=true`。桥接模板使用安全引用的 `export`，三项人工确认默认关闭，并核对 lead 与日志中的岗位 ID。

## 验证与限制

`python3 -m pytest tests/unit/domain/test_channels.py tests/unit/domain/test_agent_loop.py tests/unit/domain/test_full_pipeline.py tests/acceptance/test_external_l3_job_lead_bridge.py -q`

测试先复现失败，再验证修复；shell 测试使用真实子进程和只读环境探针，浏览器边界使用替身。它们不证明真实招聘平台投递成功；传入 PDF 与平台实际发送附件是否一致，还需真实页面验证。

后续复核发现 `_run_delivery` 仍传 Markdown，平台“发简历”又未使用本地 `resume_path`。现复用共享 exporter 生成每次尝试独立的 PDF，并记录版本/文件指纹；导出失败不进入通道。平台附件绑定没有真实页面依据前，发送必须明确阻断，不能把存在通用上传 helper 当作已接通。普通测试替代渲染进程边界，真实渲染另行验证，避免让未安装可选浏览器的机器无法运行此切片单测。

2026-09-06 会话复核：App 的打开/检查动作必须调用真实浏览器，不能把请求中的 `login_signals` 当作验证证据。同步 Playwright 在 stdio 等待期间不会刷新缓存的 URL、page 列表和关闭状态；复用页面前执行有界真实 IPC 后再判定，成功检查释放 profile 供投递复用。`tests/unit/infra/test_liepin_session_browser.py` 覆盖这些边界，本地真实页面夹具验证导航缓存；原生未登录检查不等同真实人工登录成功。
