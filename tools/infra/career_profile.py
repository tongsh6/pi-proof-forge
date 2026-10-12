"""完整职业档案的校验与指纹；复用原个人资料文件和证据库。"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from tools.infra.persistence.yaml_io import parse_simple_yaml

BASIC_FIELDS=('name','phone','email','city','current_position')


def empty_career():
    return {'schema_version':1,'summary':'','work':[],'education_visibility':'show','education':[],'skills':[],'extras':[]}


def _text(value,limit=4000):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('career_invalid_text')
    return value.strip()


def _strings(value,limit=30):
    if not isinstance(value,list) or len(value)>limit:raise ValueError('career_invalid_list')
    return list(dict.fromkeys(_text(v) for v in value if _text(v)))


def normalize_career(value):
    if not isinstance(value,dict) or set(value)-set(empty_career()) or value.get('schema_version',1)!=1:
        raise ValueError('career_invalid_schema')
    result=empty_career();result['summary']=_text(value.get('summary',''))
    visibility=value.get('education_visibility','show')
    if visibility not in {'show','omit'}:raise ValueError('career_invalid_education_visibility')
    result['education_visibility']=visibility
    schemas={'work':('company','department','title','start','end','scope'),
             'education':('school','major','degree','start','end'),
             'skills':('category','description'),'extras':('title','description','url')}
    for group,fields in schemas.items():
        rows=value.get(group,[])
        if not isinstance(rows,list) or len(rows)>30:raise ValueError('career_invalid_list')
        ids=set()
        for row in rows:
            allowed={'id',*fields}
            if group in {'work','education'}:allowed.add('current')
            if group in {'work','skills'}:allowed.add('evidence_ids')
            if group=='work':allowed.add('contributions')
            if not isinstance(row,dict) or set(row)-allowed:raise ValueError('career_invalid_entry')
            identity=row.get('id','')
            if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',identity) or identity in ids:raise ValueError('career_invalid_entry_id')
            ids.add(identity);item={'id':identity,**{f:_text(row.get(f,'')) for f in fields}}
            if group in {'work','education'}:
                current=row.get('current',False)
                if type(current) is not bool:raise ValueError('career_invalid_current')
                item['current']=current
                for field in ('start','end'):
                    if item[field] and not re.fullmatch(r'(?:19|20)\d{2}-(?:0[1-9]|1[0-2])',item[field]):raise ValueError('career_invalid_date')
                if (current and item['end']) or (item['start'] and item['end'] and item['start']>item['end']):raise ValueError('career_date_order')
            if group in {'work','skills'}:
                refs=_strings(row.get('evidence_ids',[]),limit=200)  # 证据池扩大后一段工作可关联上百张卡
                if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',ref) for ref in refs):raise ValueError('career_invalid_evidence_id')
                item['evidence_ids']=refs
            if group=='work':item['contributions']=_strings(row.get('contributions',[]))
            if group=='extras' and item['url']:
                url=urlsplit(item['url'])
                if url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('career_invalid_url')
            result[group].append(item)
    return result


def career_from_scalars(fields):
    try:return normalize_career(json.loads(fields.get('career_json') or '{}'))
    except (ValueError,TypeError):raise ValueError('career_profile_invalid') from None


def inspect_career(fields, evidence_dir:Path):
    career=career_from_scalars(fields);missing=[];hashes={}
    def gap(field,label):missing.append({'field':field,'label':label})
    for field in BASIC_FIELDS:
        if not fields.get(field,'').strip():gap(field,{'name':'姓名','phone':'手机号','email':'邮箱','city':'城市','current_position':'当前职位'}[field]+'未填写')
    if not career['work']:gap('work','尚未建立工作或合作经历')
    if not career['skills']:gap('skills','尚未整理核心能力及其证据')
    if career['education_visibility']=='show' and not career['education']:gap('education','教育背景待补充，或明确选择不展示')
    labels={'company':'任职公司','title':'职务','start':'开始年月','end':'结束年月','scope':'业务与职责范围','contributions':'个人贡献','evidence_ids':'关联证据','school':'学校','major':'专业','degree':'学历/学位','category':'能力分类','description':'内容说明'}
    required={'work':('company','title','start','scope','contributions','evidence_ids'),'education':('school','major','degree','start'),'skills':('category','description','evidence_ids'),'extras':('title','description')}
    for group,keys in required.items():
        # 不展示的教育仍保存草稿，但不生成或要求它完整。
        if group=='education' and career['education_visibility']=='omit':continue
        for index,row in enumerate(career[group]):
            for key in (*keys,*(() if row.get('current') or group not in {'work','education'} else ('end',))):
                if not row[key]:gap(f'{group}.{row["id"]}.{key}',f"{ {'work':'工作经历','education':'教育经历','skills':'核心能力','extras':'补充成果'}[group]} 第 {index+1} 条：{labels[key]}未填写")
            for ref in row.get('evidence_ids',[]):
                if ref in hashes:continue
                path=evidence_dir/f'{ref}.yaml';valid=False;hashes[ref]=''
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(evidence_dir.resolve()):
                    raw=path.read_bytes();hashes[ref]=hashlib.sha256(raw).hexdigest();doc=parse_simple_yaml(raw.decode());s=doc['scalars'];l=doc['lists']
                    valid=s.get('status')=='saved_eligible' and s.get('candidate_pool_eligible')=='true' and bool(l.get('results')) and bool(l.get('artifacts'))
                if not valid:gap('evidence.'+ref,'关联证据不可用或尚未审核：'+ref)
    body={'basic':{k:fields.get(k,'') for k in BASIC_FIELDS},'career':career,'evidence_hashes':hashes}
    revision=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    try:review=json.loads(fields.get('career_review_json') or '{}')
    except ValueError:review={}
    reviewed=not missing and review.get('revision')==revision
    return {'career':career,'revision':revision,'career_status':{'reviewed':reviewed,'missing':missing,'reviewed_at':review.get('reviewed_at',''),'ready':reviewed},'evidence_hashes':hashes}


def load_career_profile(path:Path):
    fields=dict(parse_simple_yaml(path.read_text(encoding='utf-8'))['scalars']) if path.is_file() else {}
    return {**fields,**inspect_career(fields,path.parent/'evidence_cards')}


def career_generation_issues(profile, cards):
    status=profile.get('career_status',{})
    reasons=[item['label'] for item in status.get('missing',[])]
    if not status.get('reviewed'):reasons.append('职业档案尚未确认，或资料/关联证据已变化')
    work=profile.get('career',{}).get('work',[])
    for card in cards:
        if 'evidence_hashes' in profile and card.get('source_sha256')!=profile['evidence_hashes'].get(card['id']):
            reasons.append(card['title']+'：证据版本与已确认职业档案不一致')
        linked=[item for item in work if card['id'] in item.get('evidence_ids',[])]
        if len(linked)!=1:
            reasons.append(card['title']+'：需关联唯一的工作或合作经历')
        else:
            item=linked[0];period=parse_project_period(card.get('time_range',''))
            if period is None:
                reasons.append(card['title']+'：项目时间需填写明确的开始和结束年月（或至今）')
                continue
            start,end=period
            if (start<(item.get('start') or '') or (end and end<start)
                    or (item.get('end') and (not end or start>item['end'] or end>item['end']))
                    or (not end and not item.get('current'))):
                reasons.append(card['title']+'：项目时间与所关联任职时间不一致')
    return reasons


def parse_project_period(value):
    """只接受完整年月区间，不将验收日期或文中的零散月份当成项目任期。"""
    month=r'(?:19|20)\d{2}(?:[-./](?:0?[1-9]|1[0-2])|年(?:0?[1-9]|1[0-2])月)'
    match=re.fullmatch(rf'\s*({month})\s*(?:~|～|至|到|—|–|-)\s*({month}|至今|现在|present)\s*',value,re.I)
    if not match:return None
    def canonical(text):
        parts=re.findall(r'\d+',text)
        return f'{parts[0]}-{int(parts[1]):02}' if len(parts)==2 else None
    return canonical(match[1]),canonical(match[2])


# ---- 证据卡自动关联工作经历（按材料来源、已关联材料、项目时间三类信号；冲突不自动决定） ----
_GENERIC_COMPANY_TOKENS={'上海','北京','深圳','广州','杭州','南京','成都','武汉','苏州','重庆','天津','西安','中国','有限公司','股份有限公司','股份','公司','集团','科技','信息技术','信息服务','金融','保险','网络','数字','技术','服务','信息'}
_CITY_PREFIX=re.compile(r'^(上海|北京|深圳|广州|杭州|南京|成都|武汉|苏州|重庆|天津|西安)')
_COMPANY_SUFFIX=re.compile(r'(股份有限公司|有限责任公司|有限公司|股份|集团|公司|科技|信息技术|金融信息服务|信息服务|金融|保险|网络|数字|技术|服务|信息)$')


def company_aliases(company):
    """公司全称、去掉城市前缀与行业/组织形式后缀的核心名、括号里的简称（如 EC+）；过滞泛词。"""
    text=(company or '').strip()
    if not text:return []
    aliases=[text]
    brackets=re.findall(r'[（(]([^（）()]+)[）)]',text)
    core=_CITY_PREFIX.sub('',re.sub(r'[（(][^（）()]*[）)]','',text).strip())
    previous=None
    while core and core!=previous:
        previous=core;core=_COMPANY_SUFFIX.sub('',core).strip()
    for alias in (core,*brackets):
        alias=alias.strip()
        if len(alias)>=2 and alias not in _GENERIC_COMPANY_TOKENS and alias not in aliases:aliases.append(alias)
    return aliases


def _work_contains(work,start):
    return bool(work.get('start')) and work['start']<=start and (work.get('current') or not work.get('end') or start<=work['end'])


def suggest_evidence_links(career,cards,material_labels):
    """为尚未关联的卡给出唯一工作经历建议；多条信号指向不同工作时不决定，交给用户。"""
    works=[w for w in career.get('work',[]) if w.get('company')]
    linked={ref:w['id'] for w in works for ref in w.get('evidence_ids',[])}
    by_id={card['id']:card for card in cards}
    material_work={}
    for work in works:
        for ref in work.get('evidence_ids',[]):
            for mid in by_id.get(ref,{}).get('source_material_ids',[]):material_work.setdefault(mid,set()).add(work['id'])
    aliases={w['id']:company_aliases(w['company']) for w in works}
    company={w['id']:w['company'] for w in works}
    suggestions=[];unresolved=[]
    for card in cards:
        if card['id'] in linked:continue
        votes={}
        for mid in card.get('source_material_ids',[]):
            for wid in material_work.get(mid,()):votes.setdefault(wid,set()).add('linked_material')
            label=str(material_labels.get(mid,'')).casefold()
            for work in works:
                if label and any(alias.casefold() in label for alias in aliases[work['id']]):votes.setdefault(work['id'],set()).add('material_label')
        period=parse_project_period(card.get('time_range',''))
        if period:
            for work in works:
                if _work_contains(work,period[0]):votes.setdefault(work['id'],set()).add('time_range')
        if not votes:unresolved.append({'evidence_id':card['id'],'title':card.get('title',''),'reason':'no_signal'})
        elif len(votes)==1:
            wid=next(iter(votes));suggestions.append({'evidence_id':card['id'],'title':card.get('title',''),'work_id':wid,'company':company[wid],'basis':sorted(votes[wid])})
        else:unresolved.append({'evidence_id':card['id'],'title':card.get('title',''),'reason':'ambiguous','candidates':sorted(votes)})
    return {'suggestions':suggestions,'unresolved':unresolved,'already_linked':sum(1 for card in cards if card['id'] in linked)}


def eligible_cards_for_linking(evidence_dir:Path):
    cards=[]
    if not evidence_dir.is_dir():return cards
    for path in sorted(evidence_dir.glob('*.yaml')):
        try:doc=parse_simple_yaml(path.read_text(encoding='utf-8'))
        except (OSError,UnicodeDecodeError,ValueError):continue
        s=doc['scalars'];l=doc['lists']
        if not (s.get('status')=='saved_eligible' and s.get('candidate_pool_eligible')=='true' and l.get('results') and l.get('artifacts')):continue
        cards.append({'id':s.get('id',path.stem),'title':s.get('title',''),'time_range':s.get('time_range',''),'source_material_ids':[str(x) for x in l.get('source_material_ids',[])]})
    return cards

