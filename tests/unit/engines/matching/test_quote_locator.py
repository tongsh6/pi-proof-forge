"""摘录片段定位：只认原文，不做相似度近似。"""
from tools.engines.matching.quote_locator import locate_fact_by_quote

FACTS = {
    "f1": {"text": "实现多实例任务抢占与故障恢复", "source_id": "e1"},
    "f2": {"text": "将核心存储从 MySQL/Redis 迁移至 MongoDB", "source_id": "e2"},
}


def test_exact_substring_locates_fact():
    assert locate_fact_by_quote("多实例任务抢占", FACTS) == "f1"


def test_punctuation_and_space_drift_still_locates():
    assert locate_fact_by_quote("实现多实例任务抢占，与故障恢复。", FACTS) == "f1"
    assert locate_fact_by_quote("将核心存储从MySQL/Redis迁移至MongoDB", FACTS) == "f2"


def test_truncated_quote_locates_by_prefix():
    assert locate_fact_by_quote("实现多实例任务抢占与故障", FACTS) == "f1"


def test_unrelated_quote_is_not_forced_to_match():
    assert locate_fact_by_quote("负责芯片物理设计与时序收敛", FACTS) is None


def test_too_short_quote_is_rejected():
    assert locate_fact_by_quote("多实", FACTS) is None
