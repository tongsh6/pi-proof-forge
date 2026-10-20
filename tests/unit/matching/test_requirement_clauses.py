import pytest
from tools.engines.matching import semantic_review as engine


def test_responsibilities_are_included_and_bonus_is_not_mandatory():
    jd='岗位定位\n负责平台\n工作职责\n1. 平台建设\n建立统一接口；推动实际接入。\n2. AI工程\n建立评估与权限边界。\n任职要求\n本科\n加分项\n医疗经验'
    rows=engine.job_requirements(['本科'],jd)
    assert [r['kind'] for r in rows]==['must_have','responsibility','responsibility']
    assert '医疗经验' not in str(rows)
    assert '推动实际接入' in rows[1]['text']


def test_compound_checks_keep_alternatives_and_full_context():
    req={'id':'r1','text':'熟悉 LLM、Agent、RAG 中的若干环节，并有真实项目实践','kind':'must_have'}
    parts=engine.requirement_checks([req])
    assert len(parts)==2
    assert parts[0]['criterion']=='熟悉 LLM、Agent、RAG 中的若干环节'
    assert all(p['text']==req['text'] for p in parts)
    parts=engine.requirement_checks([{'id':'r2','text':'熟悉微服务、缓存、数据库','kind':'must_have'}])
    assert len(parts)==3


def test_partial_child_cannot_be_rolled_up_as_full_support():
    req=[{'id':'r1','text':'熟悉微服务、缓存','kind':'must_have'}]
    checks=engine.requirement_checks(req)
    rows=[{'requirement_id':c['id'],'status':'supported' if i==0 else 'insufficient','reason':'有直接实践' if i==0 else '未找到相关证据','citations':[]} for i,c in enumerate(checks)]
    result=engine.aggregate_assessments(req,checks,rows)
    assert result[0]['status']=='partial'
    assert len(result[0]['checks'])==2


@pytest.mark.parametrize('field,role', [('stack','负责人'),('role_scope','负责人'),('context','')])
def test_names_and_unowned_context_are_not_full_personal_support(field,role):
    facts={'f':{'source_id':'e','field':field,'text':'项目采用MongoDB','source_role':role}}
    row={'requirement_id':'r','status':'supported','reason':'具备对应实践','citations':[{'fact_id':'f','quote':'项目采用MongoDB'}]}
    result=engine.validate_assessments({'assessments':[row]},facts,[{'id':'r','text':'具备数据库架构实践'}])
    assert result[0]['status']=='partial'
    assert result[0]['cautions']


def test_qualified_ownership_cannot_be_summarized_as_all_led():
    quote='带领5–8人团队，参与或负责15+系统从0到1。'
    facts={'f':{'source_id':'personal_profile','field':'career.work.w.contributions','text':quote}}
    row={'requirement_id':'r','status':'supported','reason':'主导15+系统从0到1','citations':[{'fact_id':'f','quote':quote}]}
    checked=engine.validate_assessments({'assessments':[row]},facts,[{'id':'r','text':'有从0到1的平台建设实践'}])[0]
    assert checked['status']=='partial' and checked['cautions']
    assert '主导15+' not in checked['reason']


def test_ownership_limit_survives_citing_only_a_result_from_the_same_card():
    facts={'f':{'source_id':'e','field':'results','source_role':'Tech Lead','text':'15+ 个独立业务系统完整搭建',
                'source_qualifiers':['主导或深度参与']}}
    row={'requirement_id':'r','status':'supported','reason':'主导15+系统','citations':[{'fact_id':'f','quote':facts['f']['text']}]}
    result=engine.validate_assessments({'assessments':[row]},facts,[{'id':'r','text':'平台实践'}])[0]
    assert result['status']=='partial'
    assert '主导或深度参与' in result['reason']


@pytest.mark.parametrize('status',['insufficient','conflict'])
def test_ownership_calibration_never_increases_support(status):
    q='参与或负责15+系统';facts={'f':{'source_id':'personal_profile','field':'career.work.w.contributions','text':q}}
    row={'requirement_id':'r','status':status,'reason':'主导15+系统但证据不足','citations':[{'fact_id':'f','quote':q}]}
    result=engine.validate_assessments({'assessments':[row]},facts,[{'id':'r','text':'平台实践'}])[0]
    assert result['status']==status


def test_stack_can_be_visible_in_same_project_action_but_not_other_project():
    fact={'source_id':'e','field':'stack','text':'Java'}
    review={'facts':{'f':fact},'requirements':[{'id':'r','text':'Java实践'}], 'assessments':[{'requirement_id':'r','status':'supported','reason':'有实践','citations':[{'fact_id':'f','quote':'Java'}]}]}
    claim={'source_kind':'evidence','evidence_id':'e','field':'actions','text':'使用Java实现接口。'}
    assert engine.resume_assessment(review,[claim])['resume_score']==100
    assert engine.resume_assessment(review,[{**claim,'evidence_id':'other'}])['resume_score']==0
    assert engine.resume_assessment(review,[{**claim,'text':'使用JavaScript实现接口。'}])['resume_score']==0


def test_warning_against_ownership_escalation_is_allowed():
    q='参与或负责15+系统从0到1。'
    facts={'f':{'source_id':'personal_profile','field':'career.work.w.contributions','text':q}}
    row={'requirement_id':'r','status':'partial','reason':'不能认定主导全部系统','citations':[{'fact_id':'f','quote':q}]}
    assert engine.validate_assessments({'assessments':[row]},facts,[{'id':'r','text':'平台建设经历'}])[0]['status']=='partial'


def test_responsibility_checks_keep_complete_action_sentences():
    req={'id':'d1','kind':'responsibility','text':'1. 云治理\n建设账号、网络、权限、容器的治理标准。\n建立告警和应急预案。'}
    checks=engine.requirement_checks([req])
    assert len(checks)==3
    assert checks[1]['criterion']=='建设账号、网络、权限、容器的治理标准'


def test_numbered_responsibility_line_is_not_discarded_as_a_heading():
    checks=engine.requirement_checks([{'id':'d','kind':'responsibility','text':'1. 负责平台架构设计\n推动接口接入。'}])
    assert [c['criterion'] for c in checks]==['负责平台架构设计','推动接口接入']


@pytest.mark.parametrize('text',['熟悉 Java, Python, Go 中任一语言','熟悉 Python, Java or Go','熟悉Java、Python、Go中至少一门语言'])
def test_alternative_language_lists_remain_one_check(text):
    assert len(engine.requirement_checks([{'id':'r','text':text,'kind':'must_have'}]))==1


@pytest.mark.parametrize('reason',['没有证据证明主导全部系统','仅有参与证据，未明确主导职责'])
def test_negative_ownership_statements_do_not_trigger_repair(reason):
    q='参与或负责15+系统从0到1。';facts={'f':{'source_id':'personal_profile','field':'career.work.w.contributions','text':q}}
    row={'requirement_id':'r','status':'partial','reason':reason,'citations':[{'fact_id':'f','quote':q}]}
    assert engine.validate_assessments({'assessments':[row]},facts,[{'id':'r','text':'平台建设经历'}])[0]['status']=='partial'


@pytest.mark.parametrize('text',['具备计算机相关本科学历；或具备五年以上后端开发经验','满足以下任一条件：\n熟悉Java\n熟悉Python'])
def test_alternatives_across_semicolons_and_lines_remain_alternatives(text):
    assert len(engine.requirement_checks([{'id':'r','text':text,'kind':'must_have'}]))==1
@pytest.mark.parametrize('heading', ['背景与能力要求', '任职条件', '加分经历'])
def test_responsibility_section_ends_before_qualification_and_bonus_aliases(heading):
    from tools.engines.matching.semantic_review import job_requirements
    jd=f'**岗位职责**\n1. 负责自有产品平台设计与研发。\n2. 完善发布验证与恢复流程。\n**{heading}**\n1. 熟悉 Python 和 SQL。\n2. 有五年研发经验。'
    rows=job_requirements(['本科及以上学历'],jd)
    duties=[r for r in rows if r['kind']=='responsibility']
    assert len(duties)==2
    assert duties[-1]['text']=='2. 完善发布验证与恢复流程。'

def test_listed_related_majors_are_examples_not_three_required_degrees():
    from tools.engines.matching.semantic_review import requirement_checks
    text = "本科及以上学历，计算机、软件工程、数学、电子信息等相关专业"
    checks = requirement_checks([{"id": "r1", "kind": "must_have", "text": text}])
    assert len(checks) == 1
    assert checks[0]["criterion"] == text


def test_named_ai_tools_are_examples_with_spaces_and_qualifiers():
    text = "经常使用 Codex、Claude Code、Cursor 等 AI 编程工具，能够理解和审查代码"
    checks = engine.requirement_checks([{"id": "r1", "kind": "must_have", "text": text}])
    assert checks[0]["criterion"] == "经常使用 Codex、Claude Code、Cursor 等 AI 编程工具"
    assert len(checks) == 2


@pytest.mark.parametrize("reason", [
    "有个人开源AI项目，但非企业生产落地，属部分支撑。",
    "全栈交付，但JD要求TypeScript/React/Next.js，技术栈不匹配。",
])
def test_assessment_rejects_explicit_extra_conditions_from_other_requirements(reason):
    with pytest.raises(ValueError, match="semantic_added_requirement"):
        engine._validate_assessment_reason(
            {"requirement_id": "d1", "status": "partial", "reason": reason},
            "有实际项目经历，能完成全栈交付与工具调用")


@pytest.mark.parametrize("requirement,reason", [
    ("熟悉React或Next.js", "JD要求React或Next.js而现有证据只有Vue开发经验，故部分支持。"),
    ("熟悉TypeScript", "JD要求TypeScript但候选人主要使用Java，故部分支持。"),
    ("熟悉PostgreSQL", "JD要求PostgreSQL而已有经验是MySQL，故部分支持。"),
])
def test_assessment_allows_comparing_required_and_existing_technologies(requirement, reason):
    engine._validate_assessment_reason({"requirement_id": "r1", "status": "partial", "reason": reason}, requirement)

