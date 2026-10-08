"""简历对外文件名；复用文件锁保存同一版本的名称与同日序号。"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.infra.export.resume_html import parse_resume_markdown
from tools.infra.persistence.review_queue import atomic_write_json, locked_review_queue


def _today() -> str:
    return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')


def _component(value: str, fallback: str) -> str:
    value = unicodedata.normalize('NFC', value)
    value = ''.join(c for c in value if not unicodedata.category(c).startswith('C'))
    value = re.sub(r'[\\/:*?"<>|]', '_', value).strip(' .')
    # 三个组件留足日期、序号与后缀空间，兼容文件系统的单文件名长度。
    return value.encode('utf-8')[:72].decode('utf-8', errors='ignore').rstrip(' .') or fallback


def _units(value: str) -> int:
    return len(value.encode('utf-16-le')) // 2


def _prefix(value: str, budget: int) -> str:
    return value.encode('utf-16-le')[:budget*2].decode('utf-16-le', errors='ignore')


def _filename(parts: list[str], day: str, number: int) -> str:
    name, company, role = parts
    suffix = f'-{day}.{number}.PDF'
    full = f'{name}-{company}-{role}{suffix}'
    if _units(full)<=24 or company=='未指定公司' or role=='未指定岗位':
        return full
    short_company = re.sub(r'^(?:上海|北京|广州|深圳|杭州|南京|苏州|成都|武汉|天津|重庆|厦门)市?', '', company)
    short_company = re.sub(r'(?:股份有限公司|有限责任公司|有限公司|公司)$', '', short_company) or company
    short_role = re.sub(r'^(?:高级|资深|初级|中级|首席)', '', role)
    short_role = re.sub(r'工程师$', '', short_role) or role
    budget = 24 - _units(name+'--'+suffix)
    if budget < _units(short_company[0])+_units(short_role[0]):
        return full
    company_budget = min(_units(short_company), max(_units(short_company[0]), (budget+1)//2))
    role_budget = min(_units(short_role), budget-company_budget)
    if role_budget < _units(short_role[0]):
        role_budget = _units(short_role[0])
    company_budget = min(_units(short_company), budget-role_budget)
    return f'{name}-{_prefix(short_company,company_budget)}-{_prefix(short_role,role_budget)}{suffix}'


def pdf_filename_for_resume(source: Path, outputs: Path) -> str:
    source = Path(source)
    content = source.read_bytes()
    text = content.decode('utf-8')
    name = parse_resume_markdown(text)['name']
    intention = next((line.removeprefix('求职意向：') for line in text.splitlines() if line.startswith('求职意向：')), '')
    company, separator, role = intention.partition(' · ')
    if not separator:
        company, role = '', ''
    trace_path = source.with_suffix('.trace.json')
    trace_bytes = trace_path.read_bytes() if trace_path.is_file() else b''
    if trace_bytes:
        try:
            trace = json.loads(trace_bytes)
            if trace.get('resume_sha256') == hashlib.sha256(content).hexdigest():
                target = trace.get('target', {})
                company = target.get('company', company)
                role = target.get('target_role', role)
        except (ValueError, AttributeError):
            pass
    parts = [_component(v if isinstance(v, str) else '', fallback) for v, fallback in
             [(name, '未填写姓名'), (company, '未指定公司'), (role, '未指定岗位')]]
    key = hashlib.sha256(str(source.resolve()).encode() + b'\0' + content + b'\0' + trace_bytes).hexdigest()
    registry = Path(outputs) / '.resume_pdf_names.json'
    with locked_review_queue(registry):
        names = json.loads(registry.read_text()) if registry.exists() else {}
        if not isinstance(names, dict) or not all(isinstance(v, str) and Path(v).name==v
                and not re.search(r'[\\/:*?"<>|\x00-\x1f]',v) and v.endswith('.PDF')
                and len(v.encode('utf-8'))<255 for v in names.values()):
            raise ValueError('简历文件命名记录无效')
        if key not in names:
            day, number = _today(), 1
            used = {unicodedata.normalize('NFC',value).casefold() for value in names.values()}
            while unicodedata.normalize('NFC',_filename(parts,day,number)).casefold() in used:
                number += 1
            names[key] = _filename(parts,day,number)
            atomic_write_json(registry, names)
        return names[key]


def check_platform_pdf_filename(filename: str) -> None:
    if (not filename or re.search(r'[\\/:*?"<>|\x00-\x1f]', filename)
            or Path(filename).name != filename or not filename.lower().endswith('.pdf')):
        raise ValueError('PDF 文件名无效')
    if _units(filename) > 24:
        raise ValueError('daily_pdf_filename_too_long: 猎聘附件名含后缀最多 24 个字符，当前名称超限，尚未上传')
