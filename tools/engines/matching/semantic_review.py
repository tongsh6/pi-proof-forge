"""语义判断的来源校验与简历覆盖计算；不执行外部 IO。"""
from __future__ import annotations

from tools.domain.assessment_support import candidate_citations, positive_citations
from tools.engines.matching.quote_locator import locate_fact_by_quote

import re
from tools.domain.quality_text import render_fact_text

STATUSES = ('supported', 'partial', 'insufficient', 'conflict')
STATUS_LABELS = {'supported': '有证据支持', 'partial': '部分支持', 'insufficient': '证据不足',
                 'conflict': '存在冲突', 'not_present': '简历未呈现', 'unassessed': '正文覆盖未核验'}


def _rows(response, key, identity, expected):
    rows = response.get(key) if isinstance(response, dict) else None
    if rows is None and isinstance(response, dict):
        rows = response
    if isinstance(rows, dict) and rows and set(rows) == set(expected) and all(
        isinstance(row, dict) for row in rows.values()
    ):
        # 本地模型偶发把"每项一行"直接输出为以 id 为键的对象；结构等价时归一为数组，
        # 仍逐项校验覆盖、分数、引用与理由，不放宽语义标准。
        rows = [{**row, identity: row_id} for row_id, row in rows.items()]
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
    """引用核实：模型给「原文摘录」或事实编号，程序负责定位与转录。

    职责分配（见 docs/reports/llm-task-contract-design-20261110.md）：
    - 模型：判断相关性 + 摘录支撑结论的原文片段（自然语言，模型擅长）；
    - 程序：把片段精确定位回事实编号并转录原文（精确匹配，程序擅长）。

    模型不再被要求抄写 `ec_xxx:actions:1` 这类标识——实测这是整批评审失败的主因。
    定位失败不抛异常，而是进入 `unresolved` 由上层按"该条不可核实"处理。
    """
    resolved: list[dict] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    if not isinstance(citations, list):
        # 单条引用写坏（或整组写成字符串）只影响可核实性，不该让整批评审失败。
        return resolved, [str(citations)[:120]]
    for citation in citations[:64]:
        if not isinstance(citation, dict):
            unresolved.append(str(citation)[:120])
            continue
        fact_id = citation.get('fact_id')
        fact = facts.get(fact_id) if isinstance(fact_id, str) else None
        if fact is None:
            quote = citation.get('quote')
            located = locate_fact_by_quote(quote, facts) if isinstance(quote, str) else None
            if located is None:
                unresolved.append(str(quote if isinstance(quote, str) else fact_id)[:120])
                continue
            fact_id = located
            fact = facts[fact_id]
        if source_id is not None and fact.get('source_id') != source_id:
            raise ValueError(f'semantic_wrong_source:{fact_id[:160]}:expected={str(source_id)[:160]}')
        if fact_id in seen:
            continue
        seen.add(fact_id)
        item = {'fact_id': fact_id, 'quote': str(fact['text']).strip()[:160]}
        if fact.get('candidate_support') is False:
            item['candidate_support'] = False
        resolved.append(item)
    return resolved, unresolved


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
        citations, unresolved = validate_citations(row.get('citations'), facts, row['id'])
        row['citations'] = citations
        if unresolved:
            # 摘录无法定位：该卡结论不可核实。局部降级为 0 分并留痕，
            # 不再让整批评审失败——这是"复核失败"而不是"模型没按要求做"。
            row['unresolved_quotes'] = unresolved
            row['score'] = 0
            row['requirement_ids'] = []
            continue
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
        try:
            _validate_assessment_reason(row,by_id[row['requirement_id']]['text'])
        except ValueError as exc:
            # 单条结论的内部矛盾/加码不足以否定整批：按"不可核实"降级并留痕，
            # 同批其他要求的结论照常生效（失败是状态，不是异常）。
            row.update(status='insufficient', citations=[],
                       reason=('评审结论不可核实：' + str(exc))[:1000])
            continue
        citations, unresolved = validate_citations(row.get('citations'), facts)
        row['citations'] = citations
        if unresolved:
            # 该项的摘录无法在事实库定位：按"证据不足"处理并留痕，不整批失败。
            row['unresolved_quotes'] = unresolved
            if row['status'] == 'supported':
                row['status'] = 'insufficient'
                row['reason'] = (row['reason'] + '（引用片段无法在证据库定位，按不可核实处理）')[:1000]
        if row['status'] != 'insufficient' and not row['citations']:
            missing_citations.append(row['requirement_id'])
        usable = list(candidate_citations(row['citations']))
        if row['status'] in {'supported', 'partial'} and len(usable) < len(row['citations']):
            row.update(status='partial' if usable else 'insufficient',
                       reason='复审限定的参与归属不能证明本人实践。')
        cited=[facts[c['fact_id']] for c in usable]
        quoted='；'.join([*(c['quote'] for c in usable),*(q for f in cited for q in f.get('source_qualifiers',[]))])
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
    for requirement_id in missing_citations:
        for row in rows:
            if row['requirement_id'] == requirement_id:
                row.update(status='insufficient', citations=[],
                           reason=(str(row.get('reason') or '') + '（缺少可核实引用，按证据不足处理）')[:1000])
    return rows


def job_requirements(terms, jd='', kind='must_have'):
    """只按已审核原文的明确章节/编号补充职责，不把加分项变为门槛。"""
    rows=[{'id':f'r{i+1}','text':text,'kind':kind} for i,text in enumerate(terms)]
    active=False;groups=[];current=[]
    for raw in jd.splitlines():
        line=raw.strip().strip('#* ：:【】「」').strip()
        if re.fullmatch(r'工作职责|岗位职责|岗位描述|Job responsibilities|Responsibilities',line,re.I):
            active=True;continue
        if active and re.fullmatch(r'任职要求|职位要求|任职资格|任职条件|岗位要求|背景与能力要求|加分项|加分经历|Requirements|Qualifications',line,re.I):break
        if not active or not line:continue
        # 项目符号不只数字编号：英文 JD 常用 ◦ / • / - / *，之前只认数字导致
        # 职责条目全部丢失（R2.2「语义评审未提供岗位职责条目」的直接原因）。
        if re.match(r'^(?:\d+[.、)）]|[◦•·▪]|[-*])\s*', line):
            if current:groups.append('\n'.join(current))
            current=[line]
        elif current:current.append(line)
    if current:groups.append('\n'.join(current))
    # 职责条目过多时截断而不是拒绝：条目越多只是需要更多批，
    # 整份评审不该因为 JD 写得更详细而失败。
    groups = groups[:40]
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
                        for parent in assessments for c, _ in positive_citations(parent)}
    candidates=[r for r in reviews if (r['score']>0 or r['id'] in positive_sources)
                and (eligible_ids is None or r['id'] in eligible_ids)]
    coverage={r['id']:{} for r in candidates}
    for index,row in enumerate(assessments):
        for citation, status in positive_citations(row):
            ref=facts[citation['fact_id']]['source_id']
            if ref in coverage:
                key = (index, citation['fact_id'])
                coverage[ref][key] = max(coverage[ref].get(key, 0), {'supported':2,'partial':1}[status])
    if not any(coverage.values()):
        return [r['id'] for r in sorted(candidates,key=lambda r:(-r['score'],r['id']))][:(1 if assessments else 3)]
    chosen=[];seen=set()
    while candidates and len(chosen)<3:
        gain=lambda row:sum(v for k,v in coverage[row['id']].items() if k not in seen)
        best=min(candidates,key=lambda r:(-gain(r),-r['score'],r['id']))
        if not gain(best):break
        chosen.append(best['id']);seen.update(coverage[best['id']]);candidates.remove(best)
    return chosen


def resume_assessment(review, claims, *, occurrence_coverage_known=None):
    def positions(citation):
        fact_id = citation["fact_id"]
        fact = review["facts"][fact_id]
        source = fact["source_id"]
        kind = "personal_profile" if source == "personal_profile" else "evidence"
        return sorted({claim["render_line"] for claim in claims
                       if claim.get("fact_id") == fact_id and claim.get("field") == fact["field"]
                       and claim.get("source_kind") == kind
                       and (kind != "evidence" or claim.get("evidence_id") == source)
                       and type(claim.get("render_line")) is int and claim["render_line"] > 0
                       and claim.get("text") == render_fact_text(fact["text"])})

    if occurrence_coverage_known is None:
        occurrence_coverage_known = any("fact_id" in c and "render_line" in c for c in claims)
    def present(citation):
        return bool(positions(citation)) if occurrence_coverage_known and citation.get('candidate_support') is not False else False

    def covered(citations):
        usable = list(candidate_citations(citations))
        return bool(usable) and all(present(c) for c in usable)

    requirements = {r['id']: r for r in review['requirements']}
    rows = []
    for assessment in review['assessments']:
        visible = covered(assessment['citations'])
        resume_status = assessment['status']
        if resume_status in {'supported', 'partial'} and not visible:
            resume_status = 'not_present'
        citations = [{**c, **review['facts'][c['fact_id']], 'in_resume': present(c), 'render_lines': positions(c) if present(c) else []} for c in assessment['citations']]
        children=[]
        for child in assessment.get('checks',[]):
            state=child['status']
            if state in {'supported','partial'} and not covered(child['citations']):state='not_present'
            children.append({**child,'resume_status':state})
        if children:
            resume_status=combined_status(c['resume_status'] for c in children)
            if resume_status=='insufficient' and any(c['resume_status']=='not_present' for c in children):resume_status='not_present'
        if not occurrence_coverage_known:
            resume_status = 'unassessed'
            children = [{**c, 'resume_status': 'unassessed'} for c in children]
        rows.append({**assessment, 'text': requirements[assessment['requirement_id']]['text'],
                     'kind':requirements[assessment['requirement_id']].get('kind','must_have'),
                     'resume_status': resume_status, 'citations': citations, 'checks':children})
    return {'mode': 'semantic', 'fit_score': support_score(r['status'] for r in rows),
            'resume_score': support_score(r['resume_status'] for r in rows) if occurrence_coverage_known else None,
            'occurrence_coverage_known': occurrence_coverage_known, 'requirements': rows,
            'all_requirements_supported': bool(rows) and all(r['resume_status'] == 'supported' for r in rows)}
