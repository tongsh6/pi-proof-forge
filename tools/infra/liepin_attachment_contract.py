"""已实测官方静态资源的有界契约核验；不执行下载的脚本、不接触凭据。"""
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener
from urllib.parse import urlsplit
from tools.infra.liepin_api import _NoRedirect

CONTRACT_URL='https://concat.lietou-static.com/fe-c-pc/v6/js/view-resume-edit.9ab52e5d.js'
CONTRACT_SHA256='a018f2608b75221f743360da78a3d0e98f661105b6b48bdea4043b42d63108f3'


def _read_contract():
    try:
        with build_opener(_NoRedirect()).open(CONTRACT_URL,timeout=15) as response:
            data=response.read(2_000_001)
        if hashlib.sha256(data).hexdigest()!=CONTRACT_SHA256:return None
        text=data.decode()
        if 'r.length<=24||(H.default.error("附件名称为1-20个字"),!1)' not in text or 'beforeUpload:G' not in text:return None
        return {'url':CONTRACT_URL,'sha256':CONTRACT_SHA256}
    except (OSError,ValueError):return None


def verify_legacy_filename_rejection(upload,observation):
    if (upload.get('state')!='unknown' or upload.get('filename')!='resume_'+upload.get('pdf_sha256','')[:16]+'.pdf'
        or len(upload.get('filename',''))!=27 or upload.get('observation',{}).get('status')!='unknown'
        or upload.get('observation',{}).get('responses')!=[]):return None
    try:
        resources=[]
        for response in observation.get('responses',[]):
            if response.get('method')=='OBSERVE':resources+=json.loads(response['payload']).get('script_resources',[])
        if CONTRACT_URL not in resources:return None
    except (ValueError,TypeError,KeyError):return None
    proof=_read_contract()
    if not proof:return None
    return {**proof,'reason':'platform_client_filename_rejected','filename_length':27,'maximum_length':24,
            'evidence_kind':'versioned_before_upload_contract','original_observation_preserved':True}


def _download_attachment(access_path):
    parsed=urlsplit(access_path)
    if (parsed.scheme or parsed.netloc or parsed.fragment or '..' in parsed.path
            or not parsed.path.startswith('/recruit-auth/resume/attachment-res/c/') or not parsed.path.endswith('.pdf')):
        raise ValueError('attachment_download_origin_invalid')
    try:
        with build_opener(_NoRedirect()).open('https://tdoss.liepin.com/o'+access_path,timeout=20) as response:
            data=response.read(10_000_001)
        if len(data)>10_000_000:raise ValueError('attachment_download_too_large')
        return data
    except OSError:raise ValueError('attachment_download_failed') from None


def attachment_filename_matches(record,filename):
    return (record.get('fileName')==Path(filename).stem
            and str(record.get('originalExtension','')).lower()==Path(filename).suffix[1:].lower()=='pdf')


def verify_uploaded_attachment(upload,observation,expected_sha256,expected_size):
    if upload.get('state')!='uploaded_unverified' or upload.get('pdf_sha256')!=expected_sha256:
        raise ValueError('attachment_upload_ack_missing')
    replies={}
    upload_responses=upload.get('observation',{}).get('responses',[])
    for response in upload_responses:
        if response.get('http_status')==200:
            try:replies[response['url']]=json.loads(response['payload'])
            except (ValueError,KeyError):pass
    saved=replies.get('https://api-c.liepin.com/api/com.liepin.cresume.attachment.save-attachment-resume',{})
    sent=replies.get('https://tdoss.liepin.com/o/recruit-auth/auth-upload',{})
    list_url='https://api-c.liepin.com/api/com.liepin.cresume.attachment.list-attachment-resume'
    has_list_reply=any(r.get('url')==list_url for r in upload_responses)
    listed=replies.get(list_url,{})
    if any(r.get('flag')!=1 for r in [sent,saved]) or (has_list_reply and listed.get('flag')!=1):
        raise ValueError('attachment_upload_ack_missing')
    observed=[];counts=[];observation_urls=[]
    for response in observation.get('responses',[]):
        if response.get('method')=='OBSERVE':
            data=json.loads(response['payload'])
            if type(data.get('attachment_count')) is int and 1<=data['attachment_count']<=50:
                observed+=data.get('attachments',[]);counts.append(data['attachment_count']);observation_urls.append(response.get('url'))
    if has_list_reply:
        records=listed.get('data',{}).get('list',[])
    else:
        # 新版列表合并到简历详情；当前页面可能有同名同字节的重复附件（App 重传/历史重复），
        # 只要求所有观测行都是同一份 PDF 字节，且恰好一行对应本次上传 ack 的 filePath。
        if len(counts)!=1 or observation_urls!=['https://c.liepin.com/resume/edit'] or not observed or len(observed)>50:
            raise ValueError('attachment_current_state_mismatch')
        if any(not isinstance(row,dict) or row.get('fileSize')!=expected_size
               or str(row.get('originalExtension','')).lower()!='pdf' for row in observed):
            raise ValueError('attachment_current_state_mismatch')
        records=observed
    if not isinstance(records,list) or not 1<=len(records)<=50:raise ValueError('attachment_target_not_unique')
    matches=[r for r in records if isinstance(r,dict) and r.get('fileId')==sent.get('data',{}).get('filePath')]
    if len(matches)!=1:raise ValueError('attachment_target_not_unique')
    record=matches[0]
    if (not attachment_filename_matches(record,upload['filename'])
        or record.get('fileId')!=sent.get('data',{}).get('filePath') or record.get('fileSize')!=expected_size
        or sent.get('data',{}).get('fileLength')!=expected_size or not record.get('encryAttachmentId')
        or record.get('auditStatus')==2):raise ValueError('attachment_identity_mismatch')
    if has_list_reply:
        if len(observed)!=1 or any(observed[0].get(k)!=record.get(k) for k in ['fileId','encryAttachmentId','fileName','fileSize','originalExtension']):
            raise ValueError('attachment_current_state_mismatch')
        browser_download=observed[0].get('download')
    else:
        matched_local=any(isinstance(row,dict) and all(row.get(k)==record.get(k) for k in ['fileId','encryAttachmentId','fileName','fileSize','originalExtension']) for row in observed)
        if not matched_local:
            raise ValueError('attachment_current_state_mismatch')
        # 同字节重复行各自带有自己的 download 观测；使用与 ack filePath 匹配的那一行校验字节。
        browser_download=record.get('download')
        if not isinstance(browser_download,dict) or browser_download.get('http_status')!=200:
            raise ValueError('attachment_content_unverified')
    downloaded_sha256=''
    if browser_download is not None:
        if browser_download.get('http_status')==200:
            if browser_download.get('byte_length')!=expected_size or browser_download.get('sha256')!=expected_sha256:
                raise ValueError('attachment_content_mismatch')
            downloaded_sha256=browser_download['sha256']
    else:
        content=_download_attachment(record.get('accessPath') or (observed[0] if observed else {}).get('accessPath',''))
        if len(content)!=expected_size or hashlib.sha256(content).hexdigest()!=expected_sha256:
            raise ValueError('attachment_content_mismatch')
        downloaded_sha256=hashlib.sha256(content).hexdigest()
    return {'pdf_sha256':expected_sha256,'file_size':expected_size,'filename':upload['filename'],
            'file_id':record['fileId'],'attachment_id':record['encryAttachmentId'],
            'download_sha256':downloaded_sha256,'attachment_count':len(records) if has_list_reply else counts[0],
            'identity_basis':'legacy_list_and_current_card' if has_list_reply else 'current_card_with_exact_download',
            'binding_kind':'upload_response_current_card_download_exact_bytes' if downloaded_sha256 else 'exact_upload_bytes_acknowledged_and_current_attachment_id',
            'download_http_status':browser_download.get('http_status') if browser_download else 200}
