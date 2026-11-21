"""Independent expectations: use limited detail slots well, never decide eligibility."""
from tools.engines.discovery.search_queries import prioritize_search_results

def rows(*titles):
    return [{'position':title, 'job_lead_id':str(i)} for i,title in enumerate(titles)]

def test_software_context_keeps_unknown_platform_ownership_and_non_java():
    data=rows('抗体平台负责人','企业内部平台负责人','Go 后端负责人','软件研发负责人','创新服务销售总监')
    ranked=prioritize_search_results(data,['Tech Lead','平台负责人'])
    assert [x['job_lead_id'] for x in ranked]==['2','3','1','0','4']
    assert len(ranked)==len(data) and data[0]['position']=='抗体平台负责人'

def test_no_software_direction_leaves_explicit_and_old_generic_queries_unchanged():
    data=rows('抗体平台负责人','Java 后端负责人','平台负责人')
    for queries in ([],['平台负责人'],['抗体平台负责人'],['销售负责人']):
        assert prioritize_search_results(data,queries)==data

def test_unknown_titles_and_no_hints_are_preserved_stably():
    data=[{}, {'position':None}, {'position':'内部平台所有者'}]
    assert prioritize_search_results(data,['Tech Lead'])==data

def test_software_work_in_pharma_is_not_demoted_or_filtered():
    data=rows('制药 Java 软件工程师','销售系统 Python 开发','内部业务平台负责人')
    assert prioritize_search_results(data,['Tech Lead'])==data

def test_not_a_keyword_substring_classifier():
    data=rows('Golang 后端开发','Google销售总监','Django开发工程师','内部平台负责人')
    assert [r['job_lead_id'] for r in prioritize_search_results(data,['Tech Lead'])]==['0','2','3','1']

def test_biological_development_does_not_mean_software_development():
    data=rows('抗体开发工程师','内部平台负责人','Python 工程师')
    assert [r['job_lead_id'] for r in prioritize_search_results(data,['Tech Lead'])]==['2','1','0']

def test_chip_physical_design_backend_is_not_software_backend():
    data=rows('数字后端经理（物理设计）','内部平台负责人','芯片公司软件后端工程师')
    assert [r['job_lead_id'] for r in prioritize_search_results(data,['Tech Lead'])]==['2','1','0']
