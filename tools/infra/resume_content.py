"""为现有投递审批校验完整内容；复用职业档案、trace 与投递快照。"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from tools.infra.career_profile import load_career_profile,career_generation_issues
from tools.infra.persistence.review_snapshot import read_generation_trace,ReviewSnapshotStore


def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value):raise ValueError('invalid_content_run_id')
    return value


def _file(root,value):
    path=Path(value);path=path if path.is_absolute() else root/path
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():raise ValueError('resume_content_artifact_invalid')
    return path


# 系统生成的简历必须完整覆盖已确认事实；用户在自己平台上维护的简历只校验
# 核心事实——平台脱敏（姓名显示「童先生」）与人工省略（技能只写标签）会让
# 投递永远无法通过，而那不是事实造假风险。
_CORE_FIELDS = {'work': ('company', 'title', 'start', 'end'),
                'education': ('school', 'degree', 'start', 'end')}
_FULL_FIELDS = {'work': ('company', 'title', 'start', 'end', 'scope'),
                'skills': ('category', 'description'),
                'education': ('school', 'degree', 'start', 'end'),
                'extras': ('title', 'description')}
CONTENT_POLICIES = frozenset({'strict', 'user_maintained'})


def _compact_for_compare(value) -> str:
    """比较用归一化：去空白/标点，年月统一成 6 位数字。"""
    text = str(value or "")
    text = re.sub(
        r"(\d{4})\s*[-/年.]\s*(\d{1,2})",
        lambda match: f"{match.group(1)}{int(match.group(2)):02d}",
        text,
    )
    return re.sub(r"[\s#*|·、（）()：:—\-]", "", text).casefold()


def _degree_key(value) -> str:
    """学位比较键：允许学习形式与括号说明差异（全日制大专 vs 大专）。"""
    text = re.sub(r"（[^）]*）|\([^)]*\)", "", str(value or ""))
    return re.sub(r"(?:非)?全日制", "", text).strip()


def content_body_issues(profile,text,*,display_policy='complete_v1',policy='strict'):
    """只检查已确认事实是否覆盖；不推断年限、技术水平或业务成果。"""
    if policy not in CONTENT_POLICIES:
        raise ValueError('invalid_content_policy')
    body=_compact_for_compare(text);career=profile['career']
    if policy=='user_maintained':
        values=[];fields=_CORE_FIELDS;include_contributions=False
    elif display_policy=='targeted_v1':
        values=[profile.get(k,'') for k in ('name','phone','email','city','current_position')]
        fields={'work':('company','title','start','end'),'education':('school','major','degree','start','end')}
        include_contributions=False
    else:
        values=[profile.get(k,'') for k in ('name','phone','email','city','current_position')]
        fields=_FULL_FIELDS;include_contributions=True
    for group,keys in fields.items():
        if group=='education' and career['education_visibility']=='omit':continue
        for row in career[group]:
            for key in keys:
                value=row.get(key,'')
                for item in (value if isinstance(value,list) else [value]):
                    if not item:continue
                    values.append(_degree_key(item) if key=='degree' else str(item))
            if group=='work' and include_contributions:
                values.extend(row.get('contributions',[]))
    return ['批准正文缺少已确认职业档案中的内容'] if any(_compact_for_compare(v) not in body for v in values if v) else []


def current_career(root):
    profile=load_career_profile(root/'personal_profile.yaml')
    if not profile['career_status']['reviewed']:raise ValueError('career_profile_unconfirmed')
    return profile


def _load_evidence_cards(evidence_dir,card_ids):
    """只读加载已落盘证据卡，供内容完整性校验；不依赖生成引擎。"""
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    cards=[]
    for card_id in card_ids:
        path=evidence_dir/f'{card_id}.yaml'
        if not path.is_file():raise ValueError('resume_evidence_changed')
        doc=parse_simple_yaml(path.read_text(encoding='utf-8'))
        cards.append({**doc['scalars'],**doc['lists'],'id':card_id,
                      'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return cards


def _inspect(root,run_id):
    root=Path(root).resolve();run_id=_id(run_id)
    record_path=_file(root,f'outputs/quick_runs/{run_id}.json');record=json.loads(record_path.read_text())
    if record.get('run',{}).get('run_id')!=run_id or record['run'].get('status')!='DONE':raise ValueError('resume_generation_required')
    md=_file(root,f'outputs/{run_id}/resume_mr-{run_id}_A.md');trace,valid=read_generation_trace(md)
    if not valid:raise ValueError('resume_generation_changed')
    if trace.get('content_schema_version')!=1:raise ValueError('resume_regeneration_required')
    profile=current_career(root)
    if trace.get('career_revision')!=profile['revision']:raise ValueError('resume_generation_changed')
    if any(trace['inputs'][ref].get('sha256')!=profile['evidence_hashes'].get(ref) for ref in trace['evidence_card_ids']):
        raise ValueError('resume_evidence_changed')
    cards=_load_evidence_cards(root/f'outputs/quick_runs/{run_id}/evidence_cards',trace['evidence_card_ids'])
    if career_generation_issues(profile,cards) or any(not c[k] for c in cards for k in ('context','role_scope','time_range','actions','results','artifacts')):
        raise ValueError('resume_content_incomplete')
    readiness=trace.get('readiness',{})
    if readiness.get('content_ready') is not True or any(readiness.get(k) for k in ('missing_profile_fields','missing_target_fields','missing_evidence_fields','missing_career_fields')):raise ValueError('resume_content_incomplete')
    text=md.read_text();sections=['职业概述','核心能力','工作经历','项目经历']
    if profile['career']['education_visibility']=='show':sections.append('教育经历')
    if any('## '+section not in text for section in sections) or content_body_issues(profile,text,display_policy=trace.get('display_policy','complete_v1')):raise ValueError('resume_content_incomplete')
    pdf=_file(root,record.get('resume_pdf',''));pdf_bytes=pdf.read_bytes()
    if len(pdf_bytes)>10_000_000 or not pdf_bytes.startswith(b'%PDF-'):raise ValueError('resume_content_artifact_invalid')
    pdf_sha=hashlib.sha256(pdf_bytes).hexdigest()
    if record.get('artifacts',{}).get('resume_pdf_sha256')!=pdf_sha:raise ValueError('resume_pdf_changed')
    md_sha=hashlib.sha256(md.read_bytes()).hexdigest();trace_sha=hashlib.sha256(md.with_suffix('.trace.json').read_bytes()).hexdigest()
    if (record.get('artifacts',{}).get('resume_pdf_source_sha256')!=md_sha
            or record.get('artifacts',{}).get('resume_pdf_trace_sha256')!=trace_sha):raise ValueError('resume_pdf_source_changed')
    target=trace.get('target',{})
    if not target.get('job_lead_id') or not target.get('source_jd_sha256'):raise ValueError('resume_target_unreviewed')
    proof={'schema_version':1,'quick_run_id':run_id,'resume_version':'gen_'+md.stem,'markdown_sha256':md_sha,
           'pdf_sha256':pdf_sha,'trace_sha256':trace_sha,
           'career_revision':profile['revision'],'job_lead_id':target['job_lead_id'],'source_jd_sha256':target['source_jd_sha256']}
    return record_path,record,proof


def validate_generated_content(root,run_id):
    _,_,proof=_inspect(root,run_id)
    return proof


def require_queue_content(root,q,*,require_approval=False):
    proof=validate_generated_content(root,q.get('quick_run_id'))
    if len(q.get('candidates',[]))!=1:raise ValueError('resume_content_review_required')
    c=q['candidates'][0];sealed=ReviewSnapshotStore(Path(root)/'outputs/agent_runs').load(q['run_id'],c)
    if (c.get('content_basis')!=proof or sealed['pdf_sha256']!=proof['pdf_sha256']
        or sealed['markdown_sha256']!=proof['markdown_sha256'] or c.get('job_lead_id')!=proof['job_lead_id']
        or c.get('source_jd_sha256')!=proof['source_jd_sha256'] or c.get('resume_version')!=proof['resume_version']):
        raise ValueError('resume_generation_changed')
    approval=q.get('content_review',{})
    if require_approval and (approval.get('confirmed') is not True or approval.get('basis')!=proof or c.get('status')!='approved'):
        raise ValueError('resume_content_review_required')
    return proof


def require_default_content(root,metadata,text=None):
    profile=current_career(Path(root))
    if metadata.get('content_schema_version')!=1 or metadata.get('career_revision')!=profile['revision'] or (text is not None and content_body_issues(profile,text)):
        raise ValueError('resume_content_unverified')
    return profile['revision']

def _compact_for_compare(value) -> str:
    """比较用归一化：去空白/标点，年月统一成 6 位数字。

    人工维护的简历常把 "2021-03" 写成「2021年3月」，严格子串匹配会把格式
    差异误判成内容缺失。
    """
    text = str(value or "")
    text = re.sub(
        r"(\d{4})\s*[-/年.]\s*(\d{1,2})",
        lambda match: f"{match.group(1)}{int(match.group(2)):02d}",
        text,
    )
    return re.sub(r"[\s#*|·、（）()：:—\-]", "", text).casefold()


def content_body_gaps(profile, text, *, display_policy="complete_v1"):
    """列出简历相对已确认档案省略了哪些字段（只报告，不判定通过与否）。

    与 `content_body_issues` 的分工：后者是投递闸门（有则阻断），本函数是
    诊断报告（列出省略项，供人决定补内容还是接受省略）。两者共用同一套
    字段范围，避免"闸门说不行但不知差在哪"。
    """
    career = profile["career"]
    targeted = display_policy == "targeted_v1"
    fields = (
        {"work": ("company", "title", "start", "end"), "education": ("school", "major", "degree", "start", "end")}
        if targeted
        else {
            "work": ("company", "title", "start", "end", "scope"),
            "skills": ("category", "description"),
            "education": ("school", "major", "degree", "start", "end"),
            "extras": ("title", "description"),
        }
    )
    body = _compact_for_compare(text)
    gaps: list[dict[str, str]] = []
    for group, keys in fields.items():
        if group == "education" and career["education_visibility"] == "omit":
            continue
        for row in career[group]:
            for key in keys:
                value = row.get(key, "")
                for item in value if isinstance(value, list) else [value]:
                    if item and _compact_for_compare(item) not in body:
                        gaps.append({"group": group, "row": str(row.get("id") or ""), "field": key, "text": str(item)[:80]})
            if group == "work" and not targeted:
                for item in row.get("contributions") or []:
                    if _compact_for_compare(item) not in body:
                        gaps.append({"group": group, "row": str(row.get("id") or ""), "field": "contributions", "text": str(item)[:80]})
    for key in ("name", "phone", "email", "city", "current_position"):
        value = profile.get(key, "")
        if value and _compact_for_compare(value) not in body:
            gaps.append({"group": "basic", "row": "profile", "field": key, "text": str(value)[:80]})
    return gaps
