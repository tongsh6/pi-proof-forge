from tools.sidecar import server
from tools.sidecar.handlers import preparation_semantic


def test_match_preparation_registered_without_delivery(monkeypatch):
    calls=[]
    def handle(params):
        calls.append(params['job_profile_id'])
        return {'meta':params['meta'],'status':'partial','scope':'advisory_partial','send_ready':False}
    monkeypatch.setattr(preparation_semantic,'handle_match_preparation',handle)
    monkeypatch.setattr(server,'_router',server._create_router())
    response=server.process_request({'jsonrpc':'2.0','id':'semantic-test','method':'jobs.matchPreparation',
        'params':{'meta':{'correlation_id':'semantic-test'},'job_profile_id':'jp_test'}})
    assert 'error' not in response, response
    assert calls==['jp_test']
    assert response['result']['send_ready'] is False
