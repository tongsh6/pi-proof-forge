"""从材料库已导入的文本恢复文档边界；不访问内容中提到的路径。"""
from __future__ import annotations
import hashlib
import re
from pathlib import PurePosixPath

MAX_DOCUMENT_CHARS=24000


def split_material_documents(text: str, filename: str) -> list[dict]:
    markers=list(re.finditer(r'^# Source: ([^\n]+)\n',text,re.MULTILINE))
    sources=[(m.group(1).strip(),text[m.end():markers[i+1].start() if i+1<len(markers) else len(text)]) for i,m in enumerate(markers)] if markers else [(filename,text)]
    docs=[]
    for source,body in sources:
        path=PurePosixPath(source)
        if path.name.lower() in {'agents.md','claude.md','index.md','local-paths.md'} or any(p.lower() in {'templates','rules','.git'} for p in path.parts):continue
        body=body.strip()
        parts=[];rest=body
        while rest:
            if len(rest)<=MAX_DOCUMENT_CHARS:parts.append(rest);break
            end=rest.rfind('\n',0,MAX_DOCUMENT_CHARS)
            if end<=0:end=MAX_DOCUMENT_CHARS
            parts.append(rest[:end]);rest=rest[end:].lstrip('\n')
        for index,part in enumerate(parts):
            digest=hashlib.sha256(part.encode()).hexdigest()
            identity=hashlib.sha256(f'{source}\0{index}\0{digest}'.encode()).hexdigest()
            docs.append({'document_id':identity,'label':source+(f' · 片段 {index+1}/{len(parts)}' if len(parts)>1 else ''),
                         'source_name':source,'sha256':digest,'char_count':len(part),'text':part})
    # 相同来源和相同原文字节视为同一文档，不重复选材。
    return list({doc['document_id']:doc for doc in docs}.values())
