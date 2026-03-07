# Skill 规范

## 目标
定义技能文档与执行脚本之间的映射，减少实现歧义。

## 技能项
- evidence-extraction
  - 文档：context/tech/EVIDENCE_EXTRACTION.md
  - 脚本：tools/run_evidence_extraction.py（推荐入口）, tools/extract_evidence.py（底层规则脚本）, tools/extract_evidence_llm.py
- matching-scoring
  - 文档：context/tech/SCORING.md
  - 脚本：tools/run_matching_scoring.py
- generation
  - 文档：context/tech/GENERATION.md
  - 脚本：tools/run_generation.py
- evaluation
  - 文档：context/tech/EVALUATION.md
  - 脚本：tools/run_evaluation.py
- github-release-publishing
  - 文档：context/tech/GITHUB_RELEASE.md
  - 脚本：tools/run_github_publish.py, tools/run_gitflow_release.py

## 规则
- 新增技能必须同步：文档、脚本、README 示例。
