"""Pure source-traceable search terms, not fit assessment or a primary stack inference."""
import re


def build_search_query_plan(preferences, city_value):
    if not preferences or not preferences.get('confirmed_at'):
        raise ValueError('preferences_not_confirmed')
    city = re.split(r'[-·/，,\s]', str(city_value).strip(), maxsplit=1)[0].removesuffix('市')
    if not re.fullmatch(r'[\u4e00-\u9fff]{2,10}', city):
        raise ValueError('city_unknown')
    rows, seen = [], set()
    for index, item in enumerate(preferences['items']):
        if item.get('kind') != 'primary':
            continue
        original = item['text']
        # Check the whole preference before shortening: a suffix must not launder contacts.
        if (not isinstance(original, str) or len(original) > 400
                or not re.fullmatch(r'[A-Za-z\u4e00-\u9fff +#./，,-]+', original)
                or any(token in original.casefold() for token in ('www.', 'http'))):
            continue
        first = re.split('[，,]', original, maxsplit=1)[0].strip()
        if not 2 <= len(first) <= 60:
            continue
        match = re.search(r'(?<![A-Za-z])Tech Lead(?![A-Za-z])|平台负责人', first, re.IGNORECASE)
        role = match.group(0) if match else first
        start = original.index(first) + (match.start() if match else 0)
        query = role
        if query.casefold() in seen:
            continue
        seen.add(query.casefold())
        rows.append({'query':query, 'address':city, 'role':{'text':role, 'preference_index':index,
            'preference_revision':preferences.get('revision',''), 'quote':item.get('quote',''),
            'start':start, 'end':start+len(role)},
            'city_source':{'field':'city','value':city_value}})
        if len(rows) == 2:
            break
    if not rows:
        raise ValueError('safe_primary_query_missing')
    return {'city':city, 'technology':None, 'technology_reason':'primary_stack_not_structured', 'queries':rows}


_SOFTWARE_ROLE = re.compile(
    r"(?<![A-Za-z])(?:tech lead|java|python|golang|django|backend|frontend)(?![A-Za-z])"
    r"|软件|后端|前端|全栈|研发效能|(?:应用|系统|程序|Web)开发", re.IGNORECASE)
_NON_SOFTWARE_ROLE = re.compile(r"抗体|蛋白|病毒|肿瘤|医药|制药|生物|销售|保险.*运营|电驱|电控|芯片|物理设计")


def prioritize_search_results(items, queries):
    """Stable detail-budget priority, not matching, exclusion or claimed suitability.

    Only confirmed software-role queries enable this hint. Unknown roles remain
    ahead of explicit unrelated domains; software work wins over domain words.
    Do not look at company industry or candidate skills, or modify stored leads.
    """
    if not any(_SOFTWARE_ROLE.search(query) for query in queries):
        return list(items)

    def priority(row):
        title = str(row.get('position') or '')
        # Semiconductor backend means physical implementation, not web services.
        if '数字后端' in title and '物理设计' in title:
            return 2
        if _SOFTWARE_ROLE.search(title):
            return 0
        if _NON_SOFTWARE_ROLE.search(title):
            return 2
        return 1

    return sorted(items, key=priority)
