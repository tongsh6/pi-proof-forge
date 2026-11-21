"""Independent source-section binding and advisory-order counterexamples."""
import hashlib
import importlib
import json

import pytest

from tools.engines.matching import semantic_matching as engine
from test_advisory_pending_order import Client, assess_order, fixture as engine_fixture


BODY = "任职要求：\n1. 本科及以上\n2. 核心技术栈硬性要求\n（1）精通Java或Python\n（2）精通C++或Go或Rust；底层服务经验优先\n3. 综合能力\n（1）沟通能力\n"


def bind(body, sources):
    module = importlib.import_module("tools.engines.matching.requirement_sections")
    return module.bind_explicit_requirement_sections(body, sources)


def source(body, quote, index=0, kind="must_have"):
    start=body.index(quote)
    return {"kind":kind,"index":index,"quote":quote,"start":start,"end":start+len(quote)}


def test_exact_child_span_carries_original_header_and_hash():
    quote="精通C++或Go或Rust"
    result=bind(BODY,[source(BODY,quote)])
    assert len(result)==1
    item=result[0]
    assert item["quote"]==quote
    assert item["source_jd_sha256"]==hashlib.sha256(BODY.encode()).hexdigest()
    assert item["binding_scope"]=="explicit_numbered_section_only"
    for key in ("heading","child"):
        span=item[key]
        assert BODY[span["start"]:span["end"]]==span["quote"]
    assert "核心技术栈硬性要求" in item["heading"]["quote"]
    assert "（2）" in item["child"]["quote"]


@pytest.mark.parametrize("body,quote,kind",[
    (BODY.split("3. 综合能力")[0],"精通Java或Python","must_have"),
    (BODY.replace("（2）","(2)"),"精通Java或Python","must_have"),
    (BODY.replace("（2）","\n（2）"),"精通Java或Python","must_have"),
    (BODY,"底层服务经验优先","nice_to_have"),
    (BODY,"沟通能力","must_have"),
    (BODY.replace("核心技术栈硬性要求","任职要求"),"精通Java或Python","must_have"),
    (BODY.replace("（1）精通Java或Python\n","普通说明\n（1）精通Java或Python\n"),"精通Java或Python","must_have"),
    (BODY,"精通Java或Python\n（2）精通C++或Go或Rust","must_have"),
    (BODY+"补充：精通Java或Python\n","精通Java或Python","must_have"),
    (BODY+"4. 核心技术栈硬性要求\n（1）其他要求\n","精通Java或Python","must_have"),
    (BODY.replace("（2）","（3）"),"精通C++或Go或Rust","must_have"),
])
def test_ambiguous_preferred_outside_or_broken_structure_never_upgrades(body,quote,kind):
    assert bind(body,[source(body,quote,kind=kind)])==[]


def test_wrong_offset_cannot_rebind_to_same_text_elsewhere():
    row=source(BODY,"精通Java或Python")
    row["start"]+=1;row["end"]+=1
    assert bind(BODY,[row])==[]


def test_advisory_section_priority_cache_and_checked_demotion(tmp_path):
    kw,terms=engine_fixture(tmp_path)
    body="1. 普通资格\n"+terms[0]+"\n"+terms[1]+"\n2. 核心技术栈硬性要求\n（1）"+terms[2]+"\n（2）"+terms[3]+"\n3. 综合要求\n"
    kw["job_path"].write_text(kw["job_path"].read_text()+"source_jd: "+json.dumps(body)+"\n")
    bindings=bind(body,[source(body,terms[2],2),source(body,terms[3],3)])
    assert len(bindings)==2
    c=Client()
    result=engine.run_semantic_matching(**kw,client=c,advisory=True,requirement_section_bindings=bindings)
    assert assess_order(c)==["r3","r4","r1","r2"]
    assert len(result["requirements"])==4

    # Fully validated cache stays first and requires no network, regardless of scheduling.
    cached=Client()
    def forbidden(stage):raise AssertionError("cache hit requested network")
    engine.run_semantic_matching(**kw,client=cached,advisory=True,
        requirement_section_bindings=bindings,before_model_call=forbidden)
    assert cached.seen==[]

    # Evicted cache: checked hard-section clauses move behind still-unchecked ordinary requirements.
    fresh=Client()
    engine.run_semantic_matching(**{**kw,"cache_dir":tmp_path/"evicted"},client=fresh,advisory=True,
        requirement_section_bindings=bindings,previous_completed_check_ids=("r3","r4"))
    assert assess_order(fresh)==["r1","r2","r3","r4"]
