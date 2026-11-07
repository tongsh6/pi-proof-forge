"""PDF 上传/投递状态的只读归一（跨 handler 共享）。

``native_pdf`` 与 ``daily_delivery`` 需要完全相同的判定，避免一处认为
"已派发"、另一处认为"未提交"。
"""
from __future__ import annotations

import json

_UPLOAD_WRITE_METHODS={'POST','PUT','PATCH'}


def upload_dispatched(observation):
    """上传脚本只采集上传/附件请求；出现写方法响应说明已派发，结果不能算确定未提交。"""
    if not isinstance(observation,dict):return False
    responses=observation.get('responses')
    if isinstance(responses,str):
        try:responses=json.loads(responses)
        except ValueError:return False
    if not isinstance(responses,list):return False
    return any(isinstance(item,dict) and str(item.get('method') or '').strip().upper() in _UPLOAD_WRITE_METHODS
               for item in responses)


def upload_effective_state(queue):
    """旧队列已证明未派发却写成 unknown 时只读归一为 not_submitted；不改写原文件。"""
    upload=queue.get('pdf_upload') if isinstance(queue,dict) else None
    if not isinstance(upload,dict):return ''
    state=upload.get('state') if isinstance(upload.get('state'),str) else ''
    observation=upload.get('observation')
    if (state=='unknown' and isinstance(observation,dict) and observation.get('status')=='not_submitted'
            and not upload_dispatched(observation)):
        return 'not_submitted'
    return state
