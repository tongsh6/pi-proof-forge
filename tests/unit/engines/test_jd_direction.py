"""JD 方向判定：芯片岗必须由正文术语识别，不能被标题骗过。"""
from tools.engines.matching.jd_direction import detect_direction_mismatch


def test_chip_backend_jd_is_flagged():
    jd = (
        "负责芯片后端实现：布局规划（Floorplan）、时钟树综合、布线拥塞优化；"
        "统筹 Placement → CTS → Routing 全流程，做 PPA 分析。"
    )
    mismatch, hits = detect_direction_mismatch(jd)
    assert mismatch is True
    assert "Floorplan" in hits and "CTS" in hits


def test_chip_dft_jd_is_flagged():
    jd = "负责综合、一致性检查、低功耗检查、STA 等实现流程；DFT spec 与 ATPG。"
    mismatch, _ = detect_direction_mismatch(jd)
    assert mismatch is True


def test_internet_backend_jd_is_not_flagged():
    jd = (
        "负责投研平台、数据服务及内部业务系统的后端设计、开发与维护；"
        "要求熟悉 Java、Spring Boot、MySQL、Redis，具备微服务经验。"
    )
    mismatch, hits = detect_direction_mismatch(jd)
    assert mismatch is False
    assert hits == ()


def test_single_ambiguous_term_is_not_enough():
    # "综合能力"里的"综合"不在 CHIP_TERMS 中；单个 STA/PPA 也不足以判定
    mismatch, hits = detect_direction_mismatch("要求较强的综合能力，熟悉 PPA 相关指标")
    assert mismatch is False
    assert len(hits) == 1
