import json
from copy import deepcopy


def test_native_resume_receipt_requires_exact_endpoint_attachment_and_business_flag():
    from tools.infra.liepin_native_receipt import classify_native_resume_receipt
    item={'method':'POST','url':'https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume','http_status':200,
          'request':json.dumps({'imUserType':'0','imId':'a'*32,'imApp':'1','oppositeImId':'b'*32,'attachmentId':'attachment-x'}),
          'response':'{"flag":1,"data":{}}'}
    result=classify_native_resume_receipt(item,'attachment-x')
    assert result['status']=='success'
    assert result['opposite_im_id']=='b'*32
    assert classify_native_resume_receipt(item,'other')['status']=='unknown'
    for patch in [{'http_status':500},{'response':'{"flag":0,"data":{}}'}, {'response':'{"flag":true,"data":{}}'},
                  {'response':'{"flag":1,"data":{"success":false}}'}, {'url':'https://api-c.liepin.com/api/list-resume'}]:
        changed=deepcopy(item);changed.update(patch)
        assert classify_native_resume_receipt(changed,'attachment-x')['status']!='success'
