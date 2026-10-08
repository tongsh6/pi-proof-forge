# 定制生成的输入、事实与渲染验证

## 问题

已有生成入口未消费个人资料/完整 JD；正文用内部 ID 充当追溯；GUI 保存的多行 JD 被 reader 截断；基础 PDF writer 以半角估算换行，却按全角宽度绘制英文，导致裁切。

## 解决

- 扩展现有 generation/pipeline 参数，不另建生成器。模型只选择已有证据，正文锁定源字段；独立追溯绑定正文和输入指纹。
- 测试实际 GUI writer → reader，而非仅手写单行 YAML；保留多行、转义和行内注释的兼容性。
- 区分无缺口建议与实际待办，规则高分也保持人工审核边界。
- PDF 换行估算与实际 CID 字宽一致；通过真实渲染和字形边界检查验证，文件头有效不等于内容可读。

## 验证

`python3 -m pytest tests/unit/domain/test_targeted_generation.py tests/unit/infra/test_yaml_io.py tests/unit/infra/test_pdf_exporter.py tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py -q`

HTTP stub 需要本机监听权限；PDF 字形边界用已有 PDFium 文档运行时单独验证。规则 pipeline、协议 stub、PDF 渲染和真实平台投递分别报告。
