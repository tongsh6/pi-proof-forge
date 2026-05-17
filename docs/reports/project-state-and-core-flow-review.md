# Project State and Core Flow Review

Date: 2026-05-17

## 总体结论

项目当前真实状态是：核心 evidence-first CLI 主链路已经可以跑通，但仍处在“工程骨架和规则模式可用、产品化闭环未收束”的阶段。

本轮实际验证显示，`tools/run_pipeline.py` 可以从原始材料和 Job Profile 生成 Evidence Card、Matching Report、Markdown Resume、Evaluation Scorecard。Agent CLI 也可以生成 10 状态 run log。但是普通 `run_pipeline.py` 本身没有写入统一 Run Record，PDF 导出代码存在但当前运行环境缺少 `weasyprint/markdown` 依赖，GUI Quick Run 也还不是直接运行主链路，只展示和复制 CLI 命令。

最需要先收束的是状态清理：README、project-ledger、OpenSpec、GitHub issues 对“完成”的定义不一致，尤其是 v2 架构、Quick Run、PDF runtime、Agent REVIEW 的状态混在一起，已经影响下一轮优先级判断。

## 当前真实完成项

- Evidence Card 规则提炼可运行：样例 raw material 生成了 `ec-state-review-20260517`，包含 title、time_range、context、actions、results、stack、artifacts。
- Matching Report 规则评分可运行：样例生成 `mr-state-review-20260517`，包含 `score_total: 95`、K/D/S/Q/E/R 分项、top_cards、gaps、gap_tasks。
- Resume Output 可运行：样例生成 A/B 两版 Markdown 简历。
- Evaluation Scorecard 可运行：样例生成 scorecard，总分 73/100，包含关键词覆盖、量化占比、空话/重复度、篇幅、证据引用检查和补证据任务。
- Agent dry-run 可运行：`python3 -m tools.cli.entrypoints agent ... --dry-run` 生成 INIT、DISCOVER、SCORE、GENERATE、EVALUATE、GATE、REVIEW、DELIVER、LEARN、DONE 事件。
- Sidecar Resumes 页已有 `resume.exportPdf` RPC，能复制已上传 PDF，并在依赖可用时把 Markdown 转 PDF。
- 全量测试通过：`336 passed`。
- v2 静态约束检查和 AIEF L3 检查通过。

## 当前真实未完成项

- `tools/run_pipeline.py` 仍通过 subprocess 串联四个 legacy 脚本；并非 README/project-ledger 暗示的纯 Composer/LinearPipeline 主链路。
- `run_pipeline.py` 的 matching 阶段读取整个 `evidence_cards/` 目录，样例新生成的 raw material card 进入了报告，但最终 Top 3 和简历内容来自已有 evidence cards。这说明“单份原始材料 -> 该材料驱动的简历”链路不是严格闭环。
- 普通 pipeline 没有统一 Run Record；Run Record 当前主要存在于 Agent Loop 的 `outputs/agent_runs/<run_id>/run_log.json`。
- PDF Markdown 转换代码存在，但当前环境无法实际导出，错误为缺少 `weasyprint`/`markdown`。
- GUI Quick Run 没有 `run.quick.start` / `run.quick.cancel` 路由，也没有前端直接启动 pipeline 的 RPC 调用。
- Agent REVIEW backend 有 queue handler，但 AgentLoop 当前没有真正暂停等待 GUI 审批；`ReviewStage` 返回 waiting 状态后，AgentLoop 仍直接按 approve 路径继续。
- GitHub issues #21-#27 多数仍按 2026-03-12 的“未实现”口径打开，和当前代码/ledger 状态冲突。

## 主链路验收结果

验收命令：

```bash
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --run-id state-review-20260517
```

结果：通过，退出码 0。

实际输出：

- Evidence Card: `evidence_cards/ec-state-review-20260517.yaml`
- Matching Report: `matching_reports/mr-state-review-20260517.yaml`
- Resume Output: `outputs/state-review-20260517/resume_mr-state-review-20260517_A.md`
- Resume Output: `outputs/state-review-20260517/resume_mr-state-review-20260517_B.md`
- Evaluation Scorecard: `outputs/scorecards/scorecard_mr-state-review-20260517_A.md`

主链路判断：

| 阶段 | 状态 | 结论 |
|---|---:|---|
| 原始经历材料 | 通过 | `tools/sample_raw.txt` 被读取并生成新 Evidence Card |
| Evidence Card | 通过 | 输出包含结构化 actions/results/artifacts，不是占位 |
| Job Profile / JD 匹配 | 通过 | 使用 `job_profiles/jp-2026-001.yaml` 评分 |
| Matching Report | 通过 | 有分项评分、top_cards、gap_tasks，不是占位 |
| Resume Output | 通过 | 生成 A/B Markdown 简历，不是空文件 |
| Evaluation Scorecard | 通过 | 生成规则分数和补证据任务，不是占位 |
| PDF Export | 部分失败 | 代码支持，但当前环境缺依赖，实际导出失败 |
| Run Record | 部分通过 | Agent CLI 有 run log；普通 pipeline 无统一 run record |

补充风险：pipeline 是可跑通，但 matching/report/resume 默认使用整个 evidence library，不是只使用本次 raw material 生成的 card。

## PDF Export 状态

代码状态：已实现 Markdown -> PDF 转换模块 `tools/infra/export/pdf_exporter.py`，sidecar `resume.exportPdf` 会对 `.md` 调用 `markdown_to_pdf()`，对已上传 `.pdf` 执行 copy。

测试状态：全量测试通过，但 PDF 成功转换测试在 `WEASYPRINT_AVAILABLE=False` 时跳过。

实际运行状态：当前环境不支持 Markdown -> PDF。验证命令：

```bash
python3 -c 'from pathlib import Path; from tools.infra.export.pdf_exporter import is_pdf_export_available, markdown_to_pdf; print("available", is_pdf_export_available()); src=Path("outputs/state-review-20260517/resume_mr-state-review-20260517_A.md"); dst=Path("/private/tmp/pi-proof-forge-state-review-resume.pdf"); markdown_to_pdf(src, dst); print(dst, dst.exists(), dst.stat().st_size)'
```

结果：

```text
available False
RuntimeError: PDF export requires weasyprint and markdown packages.
```

结论：PDF Export 不能算运行闭环完成。更准确的状态是“功能代码已接入，依赖/安装/打包未闭环，当前环境实际不可用”。

## GUI Quick Run 状态

当前 `ui/src/pages/quick-run/index.tsx` 做了三件事：

- 读取 overview/evidence/job profiles。
- 让用户选择 job profile。
- 拼出 `python3 tools/run_pipeline.py ...` 和 `python3 -m tools.cli.entrypoints agent ...` 两条 CLI 命令并提供复制按钮。

它没有直接调用 sidecar 启动主链路。`tools/sidecar/server.py` 当前注册了 `run.agent.start/get/stop`，但没有注册设计文档里的 `run.quick.start` / `run.quick.cancel`。

结论：GUI Quick Run 当前是“命令展示与复制页面”，不是“直接运行主链路”的 GUI。

## 文档与 issue 状态冲突

存在冲突。

主要冲突如下：

- README 说 extraction/matching/generation/evaluation 可端到端运行：本轮验证为真。
- project-ledger 说“旧 CLI 兼容层转调新架构”：和代码不完全一致。`tools/run_pipeline.py` 最终仍进入 `_legacy_main()`，用 subprocess 调 `run_evidence_extraction`、`run_matching_scoring`、`run_generation`、`run_evaluation`。
- OpenSpec design 仍把 `run_pipeline.py` subprocess 串联列为架构问题，并要求旧 CLI 内部转调 Composer + 新编排层；这和当前代码现状一致，但和 project-ledger 的“已完成”口径冲突。
- project-ledger 当前 Top Priority 是 M1 selected-case acceptance test；但从 evidence-first 主链路收束角度看，PDF runtime、Quick Run 直接执行、pipeline run record、文档/issue 状态冲突都比继续扩场景验收更基础。
- GitHub #21-#27 仍打开，其中多个 issue 描述“未实现”，但代码已部分或基本实现；这些 issue 的验收条件也混有一些仍未完成的点，导致不能简单按 open/closed 判断项目状态。
- README 英文末尾仍说 submission automation is documented and planned for implementation，而 project-ledger 声称 Liepin 真实投递/check-mode/频控等大量完成。投递不是本轮主线，但这是明显状态口径冲突。

## 建议关闭的 GitHub Issues

- #15 `feat: implement real Agent Run REVIEW backend`：已关闭，保持关闭。sidecar queue handler 已不是空 stub；但 AgentLoop 尚未真正暂停等待 GUI 审批，应另建更窄的 follow-up，而不是重开 #15。
- #16 `feat: implement Markdown to PDF export for generated resumes`：已关闭，保持关闭。代码层面已实现。另建“PDF runtime dependency / packaging”问题即可。
- #24 `[Architecture] Implement domain/ ReviewCandidate & ReviewDecision value objects`：已于 2026-05-17 关闭。`tools/domain/value_objects.py` 已有 frozen dataclass，测试也覆盖创建和不可变性。
- #26 `[Architecture] Implement channels/ layer - Channel Protocol & Delivery Abstraction`：已于 2026-05-17 关闭。`tools/channels/base.py`、`liepin.py`、`email.py` 已存在，fallback 与 AgentLoop 集成有测试覆盖。
- #27 `[Meta] Architecture Migration v2 - Implementation Tracking`：已于 2026-05-17 关闭。当前 meta issue 的“未实现”视角已经过期，不适合作为下一轮事实源。

## 建议保留或新建的 GitHub Issues

建议保留但改写：

- #21 `run_agent.py`：入口已存在，dry-run 已验证；但 `--run-id` resume capability、manual REVIEW pause、CLI 参数文档仍需收束。建议保留并降级为“Agent CLI semantics cleanup”。
- #22 `orchestration/ layer`：核心类已存在，Agent dry-run 可跑；但 legacy pipeline 仍 subprocess，ReviewStage 未真正阻塞等待审批。建议保留并缩小到这两个缺口。
- #23 `config/ layer`：配置层和 Composer 已存在；但 legacy CLI 仍有 env/path 分散读取。建议保留并降级为 P2 cleanup。
- #25 `EngineRegistry`：Registry 已存在，Composer 使用 registry；但 legacy scripts 仍保留 `if use_llm` 分支。建议保留并改为“legacy CLI strategy cleanup”，不要继续当 P1 架构 blocker。

建议新建：

- `state: reconcile README / ledger / OpenSpec / GitHub issues after core-flow audit`
- `pdf: make Markdown PDF export runtime-complete in local/dev/packaged app`
- `quick-run: implement run.quick.start and bind GUI Quick Run to sidecar pipeline`
- `pipeline: write run record for tools/run_pipeline.py`
- `pipeline: clarify evidence scope for run_pipeline matching stage`

## 下一轮最高优先级任务

下一轮只建议做一件事：状态清理。

验收标准应非常小：

- 关闭或改写 #21-#27 中已经过期的 issue。
- 更新 README、docs/project-ledger、OpenSpec/changes 的状态口径，让它们和本轮实际验证一致。
- 明确写下当前主链路真实边界：CLI Markdown 主链路可跑；PDF runtime 未闭环；GUI Quick Run 不是直接执行；普通 pipeline 无 run record；Agent REVIEW 不是完整人工暂停闭环。

不建议下一轮直接做 PDF、GUI、Demo 或自动投递。原因是当前最大风险不是缺一个功能，而是项目事实源互相冲突，继续实现会扩大状态债务。

## 验证命令记录

```bash
python3 -m pytest tests/ -q
```

结果：`336 passed in 0.43s`

```bash
python3 tools/check_v2_constraints.py --root .
```

结果：`PASS v2 constraints`

```bash
python3 tools/check_aief_l3.py --root . --base-dir AIEF
```

结果：`PASS AIEF L3 checks`

```bash
python3 -m tools.cli.entrypoints agent --help
```

结果：成功显示当前支持参数；不支持 `--max-rounds`。

```bash
python3 -m tools.cli.entrypoints agent --policy policy.yaml --dry-run --evidence-dir evidence_cards --job-profile job_profiles/jp-2026-001.yaml --run-id state-review-agent-20260517
```

结果：成功，输出 `{"run_id": "state-review-agent-20260517", "status": "DONE", "rounds_completed": 1}`。

```bash
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --run-id state-review-20260517
```

结果：成功，生成 Evidence Card、Matching Report、A/B Resume、Scorecard。

```bash
python3 -c 'from pathlib import Path; from tools.infra.export.pdf_exporter import is_pdf_export_available, markdown_to_pdf; print("available", is_pdf_export_available()); src=Path("outputs/state-review-20260517/resume_mr-state-review-20260517_A.md"); dst=Path("/private/tmp/pi-proof-forge-state-review-resume.pdf"); markdown_to_pdf(src, dst); print(dst, dst.exists(), dst.stat().st_size)'
```

结果：失败，`available False`，缺少 `weasyprint/markdown`。
