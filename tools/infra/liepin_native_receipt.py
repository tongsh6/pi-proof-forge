"""仅解析 App 实际采集的指定附件发送业务回执；无网络和重发能力。"""
import hashlib
import json
import re

SEND_RESUME_URL='https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume'


def classify_native_resume_receipt(item,attachment_id):
    unknown={'status':'unknown','parser_version':1}
    if item.get('method')!='POST' or item.get('url')!=SEND_RESUME_URL or item.get('http_status')!=200:return unknown
    try:
        request=json.loads(item['request']);response=json.loads(item['response'])
        if (not isinstance(request,dict) or request.get('attachmentId')!=attachment_id
            or request.get('imUserType')!='0' or request.get('imApp')!='1'
            or not all(isinstance(request.get(k),str) and re.fullmatch(r'[0-9a-f]{32}',request[k]) for k in ['imId','oppositeImId'])
            or request['imId']==request['oppositeImId']):return unknown
        # 本次真实端点的成功形状为 flag=1/data={}；其他形状保留未知，不外推通用成功规则。
        if type(response.get('flag')) is not int or response.get('flag')!=1 or response.get('data')!={} or set(response)!={'flag','data'}:
            return unknown
        canonical=json.dumps({'request':request,'response':response,'url':SEND_RESUME_URL},ensure_ascii=False,sort_keys=True).encode()
        return {'status':'success','parser_version':1,'http_status':200,'business_flag':1,
                'attachment_id':attachment_id,'opposite_im_id':request['oppositeImId'],
                'receipt_sha256':hashlib.sha256(canonical).hexdigest(),'request':request,'response':response}
    except (KeyError,TypeError,ValueError,AttributeError):return unknown
