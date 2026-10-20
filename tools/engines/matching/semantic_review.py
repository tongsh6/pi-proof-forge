"""语义判断的来源校验与简历覆盖计算；不执行外部 IO。"""
from __future__ import annotations

import re
from tools.engines.evaluation.keyword_coverage import contains_term

STATUSES = ('supported', 'partial', 'insufficient', 'conflict')
STATUS_LABELS = {'supported': '有证据支持', 'partial': '部分支持', 'insufficient': '证据不足',
                 'conflict': '存在冲突', 'not_present': '简历未呈现'}


def _rows(response, key, identity, expected):
    rows = response.get(key) if isinstance(response, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('semantic_invalid_response')
    ids = [row.get(identity) for row in rows]
    if any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('semantic_incomplete_coverage')
    return rows


def _reason(row):
    if not isinstance(row.get('reason'), str) or not 0 < len(row['reason'].strip()) <= 1000:
        raise ValueError('semantic_reason_required')


def validate_citations(citations, facts, source_id=None):
    if not isinstance(citations, list) or len(citations) > 64:
        raise ValueError('semantic_invalid_citations')
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {'fact_id', 'quote'}:
            raise ValueError('semantic_invalid_citation')
        fact_id, quote = citation['fact_id'], citation['quote']
        if not isinstance(fact_id, str) or fact_id not in facts or not isinstance(quote, str):
            detail = ':' + fact_id[:160] if isinstance(fact_id, str) else ''
            raise ValueError('semantic_unknown_fact' + detail)
        fact = facts[fact_id]
        if source_id is not None and fact['source_id'] != source_id:
            raise ValueError(f'semantic_wrong_source:{fact_id[:160]}:expected={str(source_id)[:160]}')
        if not quote.strip() or quote not in fact['text']:
            raise ValueError('semantic_quote_not_in_source:' + fact_id)
        if len(quote.strip()) < min(8, len(fact['text'].strip())):
            raise ValueError('semantic_quote_too_short:' + fact_id)
    return citations


def validate_cards(response, cards, facts, requirements):
    rows = _rows(response, 'cards', 'id', [card['id'] for card in cards])
    allowed = {r['id'] for r in requirements}
    missing_citations = []
    for row in rows:
        _reason(row)
        if type(row.get('score')) not in (int, float) or not 0 <= row['score'] <= 100:
            raise ValueError('semantic_invalid_score')
        refs = row.get('requirement_ids')
        if not isinstance(refs, list) or any(not isinstance(r, str) or r not in allowed for r in refs):
            raise ValueError('semantic_unknown_requirement')
        validate_citations(row.get('citations'), facts, row['id'])
        if (row['score'] > 0 or refs) and not row['citations']:
            missing_citations.append(row['id'])
    if missing_citations:
        raise ValueError('semantic_support_requires_citation:cards=' + ','.join(missing_citations))
    return rows


def _validate_assessment_reason(row, requirement):
    # 只拒绝可确定的矛盾，不由关键词替代能力的语义判断。
    reason=row['reason'];identity=row['requirement_id']
    pattern=r'(?<![\d.])(\d{1,2}(?:\.\d+)?)\s*年[，,\s]*(?:但|却|仍|尚)?(?:未达|不足|少于|低于|不到|不满)\s*(\d{1,2}(?:\.\d+)?)\s*年'
    for actual, minimum in re.findall(pattern, reason):
        if float(actual)>=float(minimum):
            raise ValueError(f'semantic_numeric_contradiction:{identity}:{actual}>={minimum}')
        if not re.search(r'年|years?',requirement,re.I):
            raise ValueError(f'semantic_added_requirement:{identity}:year_threshold_not_in_requirement')
    if (row['status'] in {'partial','insufficient'}
            and re.search(r'(?:缺乏|缺少|欠缺|没有|未见|但非|并非)[^。；，,;但而\n]{0,24}(?:企业级|生产|商用)',reason)
            and not re.search(r'企业级|生产|商用|production|enterprise',requirement,re.I)):
        raise ValueError(f'semantic_added_requirement:{identity}:production_not_required')
    if row['status'] in {'partial', 'insufficient'}:
        for asserted in re.findall(r'JD\s*要求([^，。；,;\n]{1,100})', reason, re.I):
            asserted = re.split(r'但|而|候选人|现有|已有', asserted, maxsplit=1)[0]
            terms = re.findall(r'[A-Za-z][A-Za-z0-9.+#]*', asserted)
            if terms and any(term.casefold() not in requirement.casefold() for term in terms):
                raise ValueError(f'semantic_added_requirement:{identity}:technology_from_other_item')


def validate_assessments(response, facts, requirements):
    rows = [dict(row) for row in _rows(response, 'assessments', 'requirement_id', [r['id'] for r in requirements])]
    by_id={r['id']:r for r in requirements}
    missing_citations=[]
    for row in rows:
        _reason(row)
        if row.get('status') not in STATUSES:
            raise ValueError('semantic_invalid_status')
        _validate_assessment_reason(row,by_id[row['requirement_id']]['text'])
        validate_citations(row.get('citations'), facts)
        if row['status'] != 'insufficient' and not row['citations']:
            missing_citations.append(row['requirement_id'])
        cited=[facts[c['fact_id']] for c in row['citations']]
        quoted='；'.join([*(c['quote'] for c in row['citations']),*(q for f in cited for q in f.get('source_qualifiers',[]))])
        qualified=r'参与或负责|主导或深度参与|主导或参与'
        asserted=re.sub(r'(?:不能|无法|未能|不足以|不应|尚不能|没有|缺少|缺乏|未)[^。；，,;但而\n]{0,20}(?:主导|独立完成|独立负责|全权负责)', '', row['reason'])
        if re.search(qualified,quoted) and re.search(r'主导|独立完成|独立负责|全权负责',asserted) and not re.search(qualified,row['reason']):
            limits=' / '.join(dict.fromkeys(re.findall(qualified,quoted)))
            row.update(status='partial' if row['status']=='supported' else row['status'],reason=f'原文限定为“{limits}”，本人全部主导的范围仍需核实',
                       cautions=['责任强度已按原文保守校准'])
        if row['status']=='supported' and cited:
            cautions=[]
            if all(f['field'].split('.')[-1] in {'stack','tags','title','category','role_scope','company'} for f in cited):
                cautions.append('仅有技术或职务标签，尚不足以证明完整实践')
            if any(f['source_id']!='personal_profile' and f.get('source_role')=='' for f in cited):
                cautions.append('引用项目的本人职责未确认，不能直接等同个人能力')
            if cautions:
                row.update(status='partial',cautions=cautions,reason='；'.join(cautions))
    if missing_citations:
        raise ValueError('semantic_support_requires_citation:requirements=' + ','.join(missing_citations))
    return rows


def job_requirements(terms, jd='', kind='must_have'):
    """只按已审核原文的明确章节/编号补充职责，不把加分项变为门槛。"""
    rows=[{'id':f'r{i+1}','text':text,'kind':kind} for i,text in enumerate(terms)]
    active=False;groups=[];current=[]
    for raw in jd.splitlines():
        line=raw.strip().strip('#* ：:').strip()
        if re.fullmatch(r'工作职责|岗位职责|岗位描述|Job responsibilities|Responsibilities',line,re.I):
            active=True;continue
        if active and re.fullmatch(r'任职要求|职位要求|任职资格|任职条件|岗位要求|背景与能力要求|加分项|加分经历|Requirements|Qualifications',line,re.I):break
        if not active or not line:continue
        if re.match(r'^\d+[.、)）]\s*',line):
            if current:groups.append('\n'.join(current))
            current=[line]
        elif current:current.append(line)
    if current:groups.append('\n'.join(current))
    if len(groups)>20:raise ValueError('semantic_too_many_responsibility_groups')
    rows.extend({'id':f'd{i+1}','text':text,'kind':'responsibility'} for i,text in enumerate(groups))
    return rows


def requirement_checks(requirements):
    checks=[]
    for req in requirements:
        text=req['text']
        source=re.sub(r'^\d+[.、)）]\s*','',text) if req.get('kind')=='responsibility' else text
        parts=[]
        # 跨逗号的备选关系保留整体，不能误作 AND。
        alternative=r'或|任一|任意|之一|若干|至少.{0,8}(?:种|项|门|个)|等[^，,；;\n]{0,12}(?:专业|工具|框架|技术)|\bor\b|\beither\b'
        if re.search(alternative,source,re.I):
            # 备选可横跨分号和换行；不确定关系留给带完整语境的语义判断。
            clauses=re.split(r'[，,；;\n](?=\s*(?:并且|并有|且|同时|其中|还需|能够|有真实))',source)
        else:clauses=re.split(r'[；;\n]+' if req.get('kind')=='responsibility' else r'[，；;\n]+|(?<!\d),(?!\d)',source)
        for clause in clauses:
            values=[clause] if req.get('kind')=='responsibility' or re.search(alternative,clause,re.I) else clause.split('、')
            parts.extend(v.strip(' \t。；;') for v in values if v.strip(' \t。；;'))
        parts=list(dict.fromkeys(parts)) or [text]
        for i,part in enumerate(parts):
            checks.append({**req,'id':req['id'] if len(parts)==1 else f"{req['id']}.c{i+1}",'parent_id':req['id'],'criterion':part})
    if len(checks)>160:raise ValueError('semantic_too_many_requirement_checks')
    return checks


def combined_status(statuses):
    statuses=list(statuses)
    if statuses and all(s=='supported' for s in statuses):return 'supported'
    if 'conflict' in statuses:return 'conflict'
    if any(s in {'supported','partial'} for s in statuses):return 'partial'
    return 'insufficient'


def aggregate_assessments(requirements,checks,assessments):
    by_id={row['requirement_id']:row for row in assessments};result=[]
    for req in requirements:
        children=[{**by_id[c['id']],'criterion':c['criterion']} for c in checks if c['parent_id']==req['id']]
        status=combined_status(c['status'] for c in children)
        gaps=[c['criterion']+'：'+c['reason'] for c in children if c['status']!='supported']
        citations=[]
        for child in children:
            for cite in child['citations']:
                if cite not in citations:citations.append(cite)
        reason=f'全部{len(children)}个原文子项有证据支持' if not gaps else '；'.join(gaps)[:900]
        result.append({'requirement_id':req['id'],'status':status,'reason':reason,'citations':citations,'checks':children})
    return result


def support_score(statuses):
    values = list(statuses)
    return round(sum({'supported': 1, 'partial': .5}.get(value, 0) for value in values) * 100 / len(values)) if values else 0


def select_cards(reviews, assessments, facts, eligible_ids=None):
    """按逐项引用的新增事实覆盖选材，不用未引用的弱相关项目凑数。"""
    positive_sources = {facts[c['fact_id']]['source_id']
                        for parent in assessments for row in parent.get('checks', [parent])
                        if row['status'] in {'supported', 'partial'} for c in row['citations']}
    candidates=[r for r in reviews if (r['score']>0 or r['id'] in positive_sources)
                and (eligible_ids is None or r['id'] in eligible_ids)]
    coverage={r['id']:{} for r in candidates}
    for index,row in enumerate(assessments):
        weight={'supported':2,'partial':1}.get(row['status'],0)
        for citation in row['citations']:
            ref=facts[citation['fact_id']]['source_id']
            if weight and ref in coverage:coverage[ref][(index,citation['fact_id'])]=weight
    if not any(coverage.values()):
        return [r['id'] for r in sorted(candidates,key=lambda r:(-r['score'],r['id']))][:(1 if assessments else 3)]
    chosen=[];seen=set()
    while candidates and len(chosen)<3:
        gain=lambda row:sum(v for k,v in coverage[row['id']].items() if k not in seen)
        best=min(candidates,key=lambda r:(-gain(r),-r['score'],r['id']))
        if not gain(best):break
        chosen.append(best['id']);seen.update(coverage[best['id']]);candidates.remove(best)
    return chosen


def resume_assessment(review, claims):
    def present(citation):
        fact = review['facts'][citation['fact_id']]
        quote = ' '.join(citation['quote'].split())
        return any((c.get('field') == fact['field'] and quote in ' '.join(c.get('text', '').split()) or
                    fact['field']=='stack' and contains_term(c.get('text',''),quote)) and
                   ((fact['source_id'] == 'personal_profile' and c.get('source_kind') == 'personal_profile') or
                    (c.get('source_kind') == 'evidence' and c.get('evidence_id') == fact['source_id'])) for c in claims)

    requirements = {r['id']: r for r in review['requirements']}
    rows = []
    for assessment in review['assessments']:
        visible = bool(assessment['citations']) and all(present(c) for c in assessment['citations'])
        resume_status = assessment['status']
        if resume_status in {'supported', 'partial'} and not visible:
            resume_status = 'not_present'
        citations = [{**c, **review['facts'][c['fact_id']], 'in_resume': present(c)} for c in assessment['citations']]
        children=[]
        for child in assessment.get('checks',[]):
            state=child['status']
            if state in {'supported','partial'} and not all(present(c) for c in child['citations']):state='not_present'
            children.append({**child,'resume_status':state})
        if children:
            resume_status=combined_status(c['resume_status'] for c in children)
            if resume_status=='insufficient' and any(c['resume_status']=='not_present' for c in children):resume_status='not_present'
        rows.append({**assessment, 'text': requirements[assessment['requirement_id']]['text'],
                     'kind':requirements[assessment['requirement_id']].get('kind','must_have'),
                     'resume_status': resume_status, 'citations': citations, 'checks':children})
    return {'mode': 'semantic', 'fit_score': support_score(r['status'] for r in rows),
            'resume_score': support_score(r['resume_status'] for r in rows), 'requirements': rows,
            'all_requirements_supported': bool(rows) and all(r['resume_status'] == 'supported' for r in rows)}
