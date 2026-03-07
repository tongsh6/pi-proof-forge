# 职位发现流程（多源渠道）

## 目的
将“仅依赖招聘网站搜岗”升级为“多源岗位线索发现”，先找到高价值公司与岗位线索，再进入后续 JD 匹配与投递。

## 范围
- 来源渠道（首批）：
  - 地图 CBD 区域公司（按城市/商圈扫描）
  - 聚合清单网站（如 A 股上市公司名录）
  - 瞪羚/高成长企业清单
  - 大厂子公司/生态公司清单
  - 企业信息平台（如企查查）用于主体校验与关系补全
- 输入：目标岗位画像、目标城市/商圈、偏好行业、公司规模约束
- 输出：标准化岗位线索清单（`job_leads/jl-YYYY-NNN.yaml`）

## 核心思路
1. 先找公司，再找岗：优先定位“公司池”，再映射到公开职位与投递入口
2. 多源交叉验证：同一公司至少保留一个来源证据，降低脏数据
3. 公司主体归一：公司名、简称、历史名统一到 legal entity
4. 先线索评分再投递：避免把自动投递资源浪费在低相关岗位

## 步骤
1. 渠道采集：按城市与目标角色，从地图/CBD、上市清单、瞪羚清单、子公司关系网采集公司
2. 主体清洗：去重、别名归一、行业标签补全、规模区间补全
3. 关系补全：通过企业信息平台补全母子公司关系、经营状态、融资/上市信息
4. 岗位映射：为每个公司补齐招聘入口（官网招聘页、招聘平台公司页、目标 JD URL）
5. 线索评分：按岗位匹配度、公司匹配度、可达性打分并分级
6. 入池产出：生成 `job_leads/*.yaml`，供 matching/submission 阶段消费

## 数据模型（建议）
```yaml
id: jl-2026-001
generated_at: "2026-03-05T10:00:00+08:00"
filters:
  city: "上海"
  cbd: ["陆家嘴", "漕河泾"]
  role_keywords: ["后端", "平台工程"]
items:
  - company_name: "示例科技有限公司"
    legal_entity: "示例科技有限公司"
    source_types: ["map_cbd", "a_share_list", "qcc"]
    source_urls:
      - "https://example.com/source1"
      - "https://example.com/source2"
    relation:
      parent_company: "某某集团"
      relation_type: "subsidiary"
    hiring_entries:
      - platform: "official"
        url: "https://example.com/careers"
      - platform: "liepin"
        url: "https://www.liepin.com/company/xxxx"
    score:
      role_fit: 0.82
      company_fit: 0.76
      reachability: 0.68
      total: 0.77
    tier: "A"
```

## 与现有流程衔接
- 对 `matching-scoring`：为 JD 输入池提供高质量候选来源，减少低质量 JD
- 对 `submission`：由“给定单条 JD URL”升级为“从 `job_leads` 批量编排投递任务”
- 对 `evaluation`：增加来源质量回看（高分线索的面试转化率）

## 验收标准
- 至少覆盖 3 类非招聘网站来源（CBD、清单、企业关系）
- 线索去重准确率可复核（同主体不重复）
- 每条高优线索包含可追溯来源 URL 与主体证据
- 可产出可消费的 `job_leads/*.yaml` 给下游脚本

## 边界与风险
- 站点协议与反爬限制：默认优先公开可访问页面与手工导入，不绕过登录保护
- 企业关系数据存在时延：需要标记“数据时间戳”与“可信度等级”
- 公司有岗不等于岗位匹配：必须经过 job profile 评分门禁

## 当前状态
流程定义完成，CLI 与自动化采集适配待实现。
