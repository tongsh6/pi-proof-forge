import hashlib
import json
import pytest


@pytest.mark.parametrize('extension',['pdf','PDF'])
def test_binding_requires_upload_ack_current_single_attachment_and_exact_bytes(monkeypatch,extension):
    from tools.infra import liepin_attachment_contract as contract
    pdf=b'%PDF-1.7\nfixture\n%%EOF';digest=hashlib.sha256(pdf).hexdigest()
    path='/recruit-auth/resume/attachment-res/c/test.pdf'
    record={'fileName':'cv_'+digest[:16],'originalExtension':'pdf','fileSize':len(pdf),'fileId':path,
            'encryAttachmentId':'attachment-id','accessPath':path+'?tk=synthetic','auditStatus':0}
    upload={'state':'uploaded_unverified','filename':record['fileName']+'.'+extension,'pdf_sha256':digest,
        'observation':{'responses':[{'url':'https://tdoss.liepin.com/o/recruit-auth/auth-upload','http_status':200,
          'payload':json.dumps({'flag':1,'data':{'filePath':path,'fileLength':len(pdf)}})},
          {'url':'https://api-c.liepin.com/api/com.liepin.cresume.attachment.save-attachment-resume','http_status':200,'payload':'{"flag":1}'},
          {'url':'https://api-c.liepin.com/api/com.liepin.cresume.attachment.list-attachment-resume','http_status':200,'payload':json.dumps({'flag':1,'data':{'list':[record]}})}]}}
    obs={'responses':[{'method':'OBSERVE','payload':json.dumps({'attachment_count':1,'attachments':[record]})}]}
    monkeypatch.setattr(contract,'_download_attachment',lambda _:pdf)
    assert contract.verify_uploaded_attachment(upload,obs,digest,len(pdf))['pdf_sha256']==digest
    monkeypatch.setattr(contract,'_download_attachment',lambda _:b'%PDF-other')
    with pytest.raises(ValueError,match='attachment_content_mismatch'):contract.verify_uploaded_attachment(upload,obs,digest,len(pdf))
    record['download']={'http_status':403,'byte_length':0,'sha256':''}
    obs['responses'][0]['payload']=json.dumps({'attachment_count':1,'attachments':[record]})
    proof=contract.verify_uploaded_attachment(upload,obs,digest,len(pdf))
    assert proof['binding_kind']=='exact_upload_bytes_acknowledged_and_current_attachment_id'
    assert proof['download_sha256']==''
    upload['observation']['responses'][0]['http_status']=500
    with pytest.raises(ValueError,match='attachment_upload_ack_missing'):contract.verify_uploaded_attachment(upload,obs,digest,len(pdf))


@pytest.mark.parametrize('count',[2,4])
def test_multiple_attachments_bind_only_the_uploaded_target(monkeypatch,count):
    from tools.infra import liepin_attachment_contract as contract
    pdf=b'%PDF-1.7\nmultiple\n%%EOF';digest=hashlib.sha256(pdf).hexdigest();path='/recruit-auth/resume/attachment-res/c/new.pdf'
    record={'fileName':'cv_'+digest[:16],'originalExtension':'pdf','fileSize':len(pdf),'fileId':path,
        'encryAttachmentId':'new-id','auditStatus':0,'download':{'http_status':200,'byte_length':len(pdf),'sha256':digest}}
    others=[{**record,'fileName':'old-'+str(i),'fileId':'old-'+str(i),'encryAttachmentId':'old-id-'+str(i)} for i in range(count-1)]
    listed={'flag':1,'data':{'list':others+[record]}}
    upload={'state':'uploaded_unverified','filename':record['fileName']+'.pdf','pdf_sha256':digest,'observation':{'responses':[
        {'url':'https://tdoss.liepin.com/o/recruit-auth/auth-upload','http_status':200,'payload':json.dumps({'flag':1,'data':{'filePath':path,'fileLength':len(pdf)}})},
        {'url':'https://api-c.liepin.com/api/com.liepin.cresume.attachment.save-attachment-resume','http_status':200,'payload':'{"flag":1}'},
        {'url':'https://api-c.liepin.com/api/com.liepin.cresume.attachment.list-attachment-resume','http_status':200,'payload':json.dumps(listed)}]}}
    obs={'responses':[{'method':'OBSERVE','payload':json.dumps({'attachment_count':count,'attachments':[record]})}]}
    result=contract.verify_uploaded_attachment(upload,obs,digest,len(pdf))
    assert result['attachment_id']=='new-id' and result['attachment_count']==count
    listed['data']['list'].append(dict(record));upload['observation']['responses'][2]['payload']=json.dumps(listed)
    with pytest.raises(ValueError,match='attachment_target_not_unique'):contract.verify_uploaded_attachment(upload,obs,digest,len(pdf))
