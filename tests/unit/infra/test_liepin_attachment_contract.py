import json
import pytest


def test_only_version_proven_invalid_legacy_filename_can_be_reconciled(monkeypatch):
    from tools.infra import liepin_attachment_contract as contract
    upload={'state':'unknown','filename':'resume_'+'a'*16+'.pdf','pdf_sha256':'a'*64,
            'observation':{'status':'unknown','responses':[]}}
    observation={'responses':[{'method':'OBSERVE','payload':json.dumps({'script_resources':[contract.CONTRACT_URL]})}]}
    monkeypatch.setattr(contract,'_read_contract',lambda:None)
    assert contract.verify_legacy_filename_rejection(upload,observation) is None
    monkeypatch.setattr(contract,'_read_contract',lambda:{'url':contract.CONTRACT_URL,'sha256':contract.CONTRACT_SHA256})
    assert contract.verify_legacy_filename_rejection(upload,observation)['reason']=='platform_client_filename_rejected'
    upload['observation']['responses']=[{'http_status':200}]
    assert contract.verify_legacy_filename_rejection(upload,observation) is None
    upload['observation']['responses']=[];upload['filename']='cv_'+'a'*16+'.pdf'
    assert contract.verify_legacy_filename_rejection(upload,observation) is None
