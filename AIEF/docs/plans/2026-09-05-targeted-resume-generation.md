# Quick Run 定制简历生成补齐

> 公开文档中的 `<local-candidate>` 为脱敏占位；真实候选名称、路径与执行安排仅保存在本机记录。

## 范围与复用

用户已授权：利用项目已有资料，为一个已有目标岗位生成可审核简历、PDF、评测与追溯记录。

- 复用 `personal_profile.yaml`、`job_profiles/` 与已有 JD、Evidence Cards。
- 复用 `tools/run_generation.py`、`tools/run_pipeline.py`、Quick Run handler、PDF exporter 和当前预览页面。
- 本轮只修 Quick Run 生成路径及其输入/产物契约；Agent 生成引擎统一、定时投递和真实渠道操作后续推进。

## 最小改动

1. generation 接收个人资料、岗位上下文与定位；只消费匹配报告选中的合格证据，缺失时不得静默替换为其他卡。
2. 模板输出姓名/联系方式/当前定位/求职意向/有证据的技能与经历。LLM 仅辅助选材排序，正文事实字段锁定。
3. `.trace.json` 独立保存正文指纹与字段来源；Quick Run 通过它验证追溯，不再修改生成后的正文或要求正文出现内部 ID。
4. 复用规则评分与 PDF 导出，返回待审核/待补充状态；历史样例未审核或岗位信息陈旧必须保留为待确认事项。

## 验收

- 先以失败测试证明个人资料/岗位未消费、内部追溯泄漏、未知证据和模型自由生成正文等缺口，再实施。
- 真实本地 generation/pipeline 与真实 PDF writer 生成产物；协议 stub 验证 LLM required 路径，不能以 mock 返回文件代替这条集成验证。
- 正文无内部 ID、source report、本机路径；追溯指纹匹配，缺资料/低分/缺口不能标记为可投递。
- 最终使用现有用户资料和仓库保存的目标 JD 生成候选版本，并核查 PDF 渲染。此结果供审核，不代表当前岗位仍开放或已完成投递。

## 用户反馈后的排版方案验证

用户要求美观大方、整洁干净、高阅读友好度。当前基础 writer 将 Markdown 压平成普通文本，即使修复字宽也没有足够的版式层级，不能作为正式简历的默认视觉方案。

- 推荐链路：Markdown 内容 → 受控的简历 HTML/CSS → 浏览器打印 PDF。复用现有 `_parse_preview_markdown` 解析结构，避免另写内容生成器。
- 已有备选：exporter 中的 Markdown → HTML → WeasyPrint 路径存在，但当前系统 Python 与项目 venv 都缺少 markdown/weasyprint。WeasyPrint 可支持 CSS 分页和字体，后续按打包成本选择；本轮不安装依赖。
- 已验证路径：本机现有 Chrome 152 通过隔离临时配置打印本地 HTML，删除默认打印页眉页脚。没有访问招聘平台或上传简历。
- 样式：A4 单栏、黑灰为主；姓名 24pt、项目标题 11pt、正文 10.4pt；时间右对齐；轻量章节线与适度段间距；无照片、装饰侧栏、技能进度条。
- 样稿：`outputs/<local-candidate>/layout-study/clean-resume.html` 与 `clean-resume.pdf`。PDFium 渲染确认一页且清晰；源 trace 的全部声明均可从 PDF 文本中找到，没有本机 URL 页脚。
- 集成边界：当前样稿不改变默认导出路径。下一步在现有 exporter 中接入模板与可用渲染器，不能静默降级为视觉不合格的正式简历；本机 headless 打印存在完成后进程不退出的情况，需有界超时与清理。

参考：[Chrome 原生打印 PDF](https://developer.chrome.com/docs/automation-and-testing/headless-cli#--print-to-pdf)、[WeasyPrint CSS 分页与 PDF 输出](https://doc.courtbouillon.org/weasyprint/latest/common_use_cases.html)。

## 正式接入范围

用户已要求继续：将样稿模板接入原 exporter 与 Resumes 预览。提取现有预览解析器到共享 HTML 模块，CSS 单独维护；退休纯文本 PDF 默认路径。优先复用本机已存在的 Chromium Headless Shell，保留普通 Chrome/已安装 WeasyPrint 的发现路径。需要覆盖缺少渲染器、半写入/损坏文件、超时清理、输入转义、预览与导出使用相同 HTML、附加章节保留，并用本机实际渲染验证最终稿。

正式接入已完成，并在用户授权补齐 Cargo 锁定依赖后通过真实 Tauri 调试窗口验证选择、共享 HTML 预览和导出。原生导出 `outputs/<local-candidate>/formal-export/from-native-ui.pdf` 为一页 A4，全部来源声明保留；同名 HTML 与 stdio RPC 导出一致。历史版本列表采用 256px 高度上限并独立滚动，避免挤走预览。最新回归 552 项通过，前端构建与小范围独立审查通过；不将调试窗口切片验收扩大为安装包发布、候选审核通过或真实渠道投递完成。
