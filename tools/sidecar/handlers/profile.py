from __future__ import annotations

import re
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.career_profile import inspect_career, normalize_career, suggest_evidence_links, eligible_cards_for_linking
from tools.sidecar.handlers import materials as materials_handler
from tools.infra.persistence.review_queue import locked_review_queue

_PROFILE_PATH = Path("personal_profile.yaml")
_PROFILE_FIELDS = ("name", "phone", "email", "city", "current_position")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _load_profile() -> dict[str, str]:
    if not _PROFILE_PATH.exists():
        return {}
    doc = parse_simple_yaml(_PROFILE_PATH.read_text(encoding="utf-8"))
    return dict(doc["scalars"])


def _write_profile(fields: dict[str, str]) -> None:
    owned=set(_PROFILE_FIELDS)|{'updated_at','career_json','career_review_json'}
    original=_PROFILE_PATH.read_text(encoding='utf-8') if _PROFILE_PATH.is_file() else ''
    blocks=re.split(r'(?m)(?=^[A-Za-z_][A-Za-z0-9_-]*\s*:)',original)
    kept=[]
    for block in blocks:
        match=re.match(r'^([A-Za-z_][A-Za-z0-9_-]*)\s*:',block)
        if not match or match.group(1) not in owned:kept.append(block)
    lines=[f'{key}: '+json.dumps(str(fields.get(key,'')),ensure_ascii=False) for key in (*_PROFILE_FIELDS,'updated_at','career_json','career_review_json') if key in fields or key in _PROFILE_FIELDS]
    _PROFILE_PATH.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.profile-',dir=_PROFILE_PATH.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(''.join(kept).rstrip()+'\n'+'\n'.join(lines)+'\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,_PROFILE_PATH)
    finally:temporary.unlink(missing_ok=True)


def _profile_payload(fields: dict[str, str]) -> dict[str, Any]:
    missing_fields = [
        field for field in _PROFILE_FIELDS if not fields.get(field, "").strip()
    ]
    completeness = int(
        ((len(_PROFILE_FIELDS) - len(missing_fields)) / len(_PROFILE_FIELDS)) * 100
    )
    return {
        "name": fields.get("name", ""),
        "phone": fields.get("phone", ""),
        "email": fields.get("email", ""),
        "city": fields.get("city", ""),
        "current_position": fields.get("current_position", ""),
        "completeness": completeness,
        "missing_fields": missing_fields,
        "updated_at": fields.get("updated_at", ""),
    }


def handle_profile_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    fields=_load_profile()
    profile = {**_profile_payload(fields),**inspect_career(fields,_PROFILE_PATH.parent/"evidence_cards")}
    return {
        "meta": {"correlation_id": correlation_id},
        "profile": profile,
    }


def handle_profile_update(params: dict[str, Any]) -> dict[str, Any]:
    patch=params.get('patch',{})
    if not isinstance(patch,dict) or set(patch)-set(_PROFILE_FIELDS)-{'career'}:raise ValueError('unsupported_profile_fields')
    with locked_review_queue(_PROFILE_PATH):
        fields=_load_profile();current=inspect_career(fields,_PROFILE_PATH.parent/'evidence_cards')
        expected=params.get('expected_revision')
        if expected!=current['revision']:raise ValueError('profile_changed')
        for key in _PROFILE_FIELDS:
            if key in patch:
                if not isinstance(patch[key],str) or len(patch[key])>1000:raise ValueError('invalid_profile_field')
                fields[key]=patch[key].strip()
        if fields.get('email') and not _EMAIL_PATTERN.fullmatch(fields['email']):raise ValueError('email must be a valid email address')
        if 'career' in patch:fields['career_json']=json.dumps(normalize_career(patch['career']),ensure_ascii=False,separators=(',',':'))
        fields['updated_at']=_utcnow_iso();_write_profile(fields)
    return {'meta':params['meta'],'saved':True,'updated_at':fields['updated_at']}


def handle_profile_review(params):
    if params.get('confirmed') is not True:raise ValueError('career_confirmation_required')
    with locked_review_queue(_PROFILE_PATH):
        fields=_load_profile();current=inspect_career(fields,_PROFILE_PATH.parent/'evidence_cards')
        if params.get('expected_revision')!=current['revision']:raise ValueError('profile_changed')
        if current['career_status']['missing']:raise ValueError('career_profile_incomplete')
        fields['career_review_json']=json.dumps({'revision':current['revision'],'reviewed_at':_utcnow_iso()},ensure_ascii=False)
        fields['updated_at']=_utcnow_iso();_write_profile(fields)
    return handle_profile_get(params)


def handle_profile_auto_link_evidence(params):
    """按材料来源 / 已关联材料 / 项目时间把尚未关联的可用证据卡挂到唯一工作经历；apply 为真时写入并使档案回到待确认。"""
    apply=params.get('apply') is True
    evidence_dir=_PROFILE_PATH.parent/'evidence_cards'
    with locked_review_queue(_PROFILE_PATH):
        fields=_load_profile();current=inspect_career(fields,evidence_dir)
        if apply and params.get('expected_revision')!=current['revision']:raise ValueError('profile_changed')
        labels={str(item.get('material_id','')):str(item.get('label','')) for item in materials_handler.list_material_source_items()}
        result=suggest_evidence_links(current['career'],eligible_cards_for_linking(evidence_dir),labels)
        result['applied']=0;result['revision']=current['revision'];result['career_status']=current['career_status']
        if apply and result['suggestions']:
            career=current['career']
            for item in result['suggestions']:
                for work in career['work']:
                    if work['id']==item['work_id']:work['evidence_ids']=list(dict.fromkeys([*work.get('evidence_ids',[]),item['evidence_id']]))
            fields['career_json']=json.dumps(normalize_career(career),ensure_ascii=False,separators=(',',':'))
            fields['updated_at']=_utcnow_iso();_write_profile(fields)
            after=inspect_career(fields,evidence_dir)
            result['applied']=len(result['suggestions']);result['revision']=after['revision'];result['career_status']=after['career_status']
    return {'meta':params['meta'],**result}

