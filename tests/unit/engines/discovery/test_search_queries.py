import pytest
from tools.engines.discovery.search_queries import build_search_query_plan


def prefs(text):
    return {'confirmed_at':'now','revision':'revision','items':[{'kind':'primary','text':text,'quote':'source'}]}


def test_role_span_and_no_technology_inference():
    text='产品型公司 Tech Lead，负责长期技术演进'
    plan=build_search_query_plan(prefs(text),'上海市-浦东')
    row=plan['queries'][0]
    assert row['query']=='Tech Lead'
    assert row['address']=='上海'
    role=row['role']
    assert text[role['start']:role['end']]==role['text']=='Tech Lead'
    assert plan['technology'] is None


@pytest.mark.parametrize('text',['Tech Lead，联系15021128755','Tech Lead，https://example.com','Tech Lead\n平台负责人'])
def test_unsafe_suffix_not_laundered(text):
    with pytest.raises(ValueError,match='safe_primary_query_missing'):
        build_search_query_plan(prefs(text),'上海')
