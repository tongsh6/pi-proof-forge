# 简历生成流程

## 目的
基于证据拼装并生成两版简历。

## 步骤
1. 选 Top N 证据卡
2. 模板拼装（事实字段锁定）
3. 受控改写（不新增事实）
4. 输出版本 A/B
5. 生成版本号

## 产出
- outputs/resume_*.md
- resume_version_id

注：PDF/DOCX 导出属于后置发布/投递阶段能力，不是当前 generation 阶段默认产物。
