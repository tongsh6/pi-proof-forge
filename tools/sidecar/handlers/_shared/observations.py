"""浏览器观测结果脱敏（跨 handler 共享）。"""
from __future__ import annotations

import json
import re


def sanitize_observation(value, depth=0):
    """签名只用于当次内存中的读取；连同嵌套 JSON 字符串在入库前统一脱敏。"""
    if depth>24:return None
    if isinstance(value,dict):
        return {k:sanitize_observation(v,depth+1) for k,v in value.items()
                if not re.search(r'token|cookie|secret|password|authorization|signature|csrf|credential|accesskey|^tk$',k,re.I)}
    if isinstance(value,list):return [sanitize_observation(v,depth+1) for v in value]
    if isinstance(value,str):
        if value.lstrip().startswith(('{','[')):
            try:return json.dumps(sanitize_observation(json.loads(value),depth+1),ensure_ascii=False,separators=(',',':'))
            except (ValueError,RecursionError):pass
        if re.match(r'^(?:https?://|/)',value,re.I):return re.split(r'[?#]',value,maxsplit=1)[0]
    return value
