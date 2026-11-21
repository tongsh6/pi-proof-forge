"""线索 JD 完整性判定：依据 JD 正文与 jd_status，而非来源渠道。"""
from tools.domain.job_lead_state import lead_has_complete_jd


def test_lead_with_complete_jd_is_not_summary_only():
    assert lead_has_complete_jd(
        {"source": "liepin_official", "source_jd": "jd_inputs/jd-x.txt", "jd_status": "complete_unreviewed"}
    )


def test_summary_only_lead_without_jd_body():
    assert not lead_has_complete_jd(
        {"source": "liepin_official", "source_jd": "", "jd_status": "summary_only"}
    )


def test_lead_with_jd_path_but_incomplete_state_is_rejected():
    assert not lead_has_complete_jd(
        {"source_jd": "jd_inputs/jd-x.txt", "jd_status": "summary_only"}
    )
