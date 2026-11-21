from unittest.mock import Mock
import pytest
from tools.infra.liepin_api import LiepinReadOnlyClient, LiepinApiError
from tools.infra.liepin_readonly import LiepinReadOnlySession


def test_city_is_separate_official_payload_and_legacy_unchanged():
    c=LiepinReadOnlyClient();c._request=Mock(return_value={'list':[]})
    c.search_jobs('synthetic','Tech Lead',0,address=' 上海 ')
    assert c._request.call_args.args[-1]=={'jobName':'Tech Lead','page':0,'address':'上海'}
    c.search_jobs('synthetic','Tech Lead',1)
    assert c._request.call_args.args[-1]=={'jobName':'Tech Lead','page':1}


@pytest.mark.parametrize('address',['', ' ', 123, False, '上海\n', 'x'*101])
def test_invalid_address_never_calls_network(address):
    c=LiepinReadOnlyClient();c._request=Mock()
    with pytest.raises(LiepinApiError) as e:c.search_jobs('synthetic','Tech Lead',address=address)
    assert e.value.code=='INVALID_INPUT'
    c._request.assert_not_called()


def test_session_forwards_only_explicit_address():
    s=LiepinReadOnlySession(store=Mock());s._invoke=Mock(return_value={})
    s.search('Tech Lead',0,address='上海')
    s._invoke.assert_called_with('search',keyword='Tech Lead',page=0,address='上海')
    s.search('Tech Lead',0)
    s._invoke.assert_called_with('search',keyword='Tech Lead',page=0)
