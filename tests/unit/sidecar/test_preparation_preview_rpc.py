from tools.sidecar import server
from tools.sidecar.handlers import preparation_preview


def test_preview_preparation_registered_without_delivery(monkeypatch):
    calls=[]
    def handle(params):
        calls.append(params['job_profile_id'])
        return {'meta':params['meta'],'status':'blocked','scope':'internal_targeted_excerpt',
                'code':'no_presentable_supported_work','deliverable':False,'send_ready':False}
    monkeypatch.setattr(preparation_preview,'handle_preview_preparation',handle)
    monkeypatch.setattr(server,'_router',server._create_router())
    response=server.process_request({'jsonrpc':'2.0','id':'preview-test','method':'jobs.previewPreparation',
        'params':{'meta':{'correlation_id':'preview-test'},'job_profile_id':'jp_test'}})
    assert 'error' not in response,response
    assert calls==['jp_test']
    assert response['result']['scope']=='internal_targeted_excerpt'
    assert response['result']['send_ready'] is False
