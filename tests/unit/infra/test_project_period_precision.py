import pytest
from tools.infra.career_profile import parse_project_period, career_generation_issues


def profile(start='2021-03', end='', current=True):
    return {'career_status': {'reviewed': True, 'missing': []}, 'career': {'work': [
        {'id': 'w', 'start': start, 'end': end, 'current': current, 'evidence_ids': ['c']}]}}


def issues(period, **kwargs):
    return career_generation_issues(profile(**kwargs), [{'id': 'c', 'title': '平台', 'time_range': period}])


def test_year_precision_is_kept_and_supported_when_inside_employment():
    assert parse_project_period('2022 – 至今') == ('2022', None)
    assert issues('2022 – 至今') == []
    assert issues('2022 – 2024', end='2025-06', current=False) == []


@pytest.mark.parametrize('period', ['2020–至今', '2021–至今', '2022–2025'])
def test_year_precision_cannot_hide_employment_conflict_or_uncertainty(period):
    assert issues(period, end='2025-06', current=period.endswith('至今'))


@pytest.mark.parametrize('period', ['2026-08-03', '2022-13 – 至今', '2024–2022', '2022–至今并已完成'])
def test_milestones_invalid_months_and_reverse_periods_are_not_accepted(period):
    assert issues(period)


def test_exact_month_boundary_keeps_existing_behavior():
    assert issues('2021-03 ~ 至今') == []
    assert issues('2021-02 ~ 至今')


def test_autolink_does_not_assign_uncertain_year_to_previous_employer():
    from tools.infra.career_profile import suggest_evidence_links
    career={'work':[
        {'id':'old','company':'旧公司','start':'2019-01','end':'2022-06','current':False,'evidence_ids':[]},
        {'id':'new','company':'新公司','start':'2022-07','end':'','current':True,'evidence_ids':[]}]}
    card={'id':'c','title':'平台','time_range':'2022–至今','source_material_ids':[]}
    assert suggest_evidence_links(career,[card],{})['suggestions']==[]
    card['time_range']='2022-08–至今'
    assert suggest_evidence_links(career,[card],{})['suggestions'][0]['work_id']=='new'
