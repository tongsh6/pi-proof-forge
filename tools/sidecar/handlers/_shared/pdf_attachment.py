"""原生回执与提交日志的附件身份校正（跨 handler 共享）。"""
from __future__ import annotations

from tools.sidecar.handlers._shared import agent_state


def record_verified_attachment_identity(saved, binding):
    """把原生回执已验证的实际发送附件身份写入提交日志；只补回执证明的字段，返回是否发生变化。"""
    try:
        inputs=saved['input_artifacts'];attachment_id=binding['attachment_id'];file_id=binding['file_id']
    except (KeyError,TypeError):return False
    if (not isinstance(inputs,dict) or not isinstance(attachment_id,str) or not attachment_id
            or not isinstance(file_id,str) or not file_id):return False
    changed=False
    if inputs.get('attachment_file_id')!=file_id:
        inputs['attachment_file_id']=file_id;changed=True
    if inputs.get('attachment_id')!=attachment_id:
        # 发送前重传会让开始投递时的旧附件身份过期；保留旧值供审计，不删除任何既有证据。
        history=inputs.get('attachment_id_history')
        history=history if isinstance(history,list) else []
        inputs['attachment_id_history']=history+[{'attachment_id':inputs.get('attachment_id',''),
            'source':'native_receipt','reconciled_at':agent_state.utcnow_iso()}]
        inputs['attachment_id']=attachment_id;changed=True
    return changed
