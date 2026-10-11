"""官方来源 URL 身份：企业岗位 /job/ 与猎头岗位 /a/ 都是猎聘官方详情路径。"""
import pytest

from tools.infra.persistence.job_lead_binding import same_official_source_url


@pytest.mark.parametrize("left,right", [
    ("https://www.liepin.com/job/1985846765.shtml", "https://www.liepin.com/job/1985846765.shtml?mscid=soai_pc_001"),
    ("https://www.liepin.com/a/79859227.shtml", "https://www.liepin.com/a/79859227.shtml?mscid=soai_pc_001"),
])
def test_tracking_query_does_not_change_identity(left, right):
    assert same_official_source_url(left, right)


@pytest.mark.parametrize("left,right", [
    ("https://www.liepin.com/a/79859227.shtml", "https://www.liepin.com/job/79859227.shtml"),
    ("https://www.liepin.com/a/79859227.shtml", "https://www.liepin.com/a/79859228.shtml"),
    ("https://www.liepin.com/a/not-an-id.shtml", "https://www.liepin.com/a/not-an-id.shtml"),
    ("https://www.liepin.com/company/79859227.shtml", "https://www.liepin.com/company/79859227.shtml"),
    ("http://www.liepin.com/a/79859227.shtml", "http://www.liepin.com/a/79859227.shtml"),
])
def test_other_paths_or_mismatched_ids_are_not_the_same_source(left, right):
    assert not same_official_source_url(left, right)
