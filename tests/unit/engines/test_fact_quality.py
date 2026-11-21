"""事实可用性闸门契约：拒绝内部碎片，但不否定事实真实性。"""
from tools.engines.generation.fact_quality import judge_fact_text, presentable


def test_accepts_normal_experience_facts():
    assert presentable("将订单存储从 SQLite 迁移至 PostgreSQL，重写数据访问与索引初始化")
    assert presentable("带领 3–5 人团队，参与或负责 6 个系统从 0 到 1 建设")
    assert presentable("在测试机构造 200 万条库存数据，修复统计查询未使用索引导致的响应延迟")


def test_rejects_code_identifiers():
    assert not presentable("在ORD_ORDER_STATE_TOTAL、ORD_ORDER_STATE_GROUP中添加改造逻辑")
    assert not presentable("调用 buildTemplateResume() 生成正文")
    assert judge_fact_text("在 ORD_IMPORT_DATA_FROM_LOG 存储过程中添加判断").reason == "code_identifier"


def test_rejects_internal_self_reference():
    assert not presentable("此卡为个人任职期间的跨项目工作汇总")
    assert not presentable("本次盘点覆盖客户甲目录下 12 个项目文档")
    assert judge_fact_text("本卡记录用户在示例公司的工作内容").reason == "internal_meta"


def test_rejects_table_and_numeric_fragments():
    assert not presentable("token 失效导致 401 | 刷新 token 后重试，超过 3 次不再回调")
    assert not presentable("5-200人")
    assert not presentable("20-29 占人数25%以下，超过，无法报名")


def test_rejects_negative_fragments():
    assert not presentable("无需改造")
    assert not presentable("该存储过程不需要改造")


def test_rejects_too_short_text():
    assert judge_fact_text("无需改造", field="actions").reason in {"too_short", "negative_fragment"}
    assert judge_fact_text("短", field="actions").reason == "too_short"


def test_structural_fields_are_lenient():
    for field in ("title", "stack", "time_range", "role_scope", "tags"):
        assert presentable("Java", field=field)
        assert presentable("2024-01 ~ 2024-06", field=field)


def test_accepts_english_project_titles_and_sentences():
    assert presentable("Service Deployment Strategy Update")
    assert presentable("Payment Provider Integration Configuration")


def test_verdict_is_explainable():
    verdict = judge_fact_text("在ORD_ORDER_STATE_TOTAL中添加改造逻辑")
    assert verdict.presentable is False
    assert verdict.reason == "code_identifier"


def test_business_rule_fragment_is_rejected():
    from tools.engines.generation.fact_quality import judge_fact_text

    verdict = judge_fact_text("未完成核验的账户，单笔转账金额不能超过5000元", field="results")

    assert verdict.presentable is False
    assert verdict.reason == "business_rule_fragment"


def test_param_level_change_is_rejected():
    from tools.engines.generation.fact_quality import judge_fact_text

    verdict = judge_fact_text("查询条件增加“订单号”字段，可支持多个编号（80条）同时查询；", field="actions")

    assert verdict.presentable is False
    assert verdict.reason == "param_change"


def test_storage_migration_is_still_presentable():
    from tools.engines.generation.fact_quality import judge_fact_text

    verdict = judge_fact_text("将订单存储从 SQLite 迁移至 PostgreSQL，重写数据访问、事务与索引初始化", field="actions")

    assert verdict.presentable is True
