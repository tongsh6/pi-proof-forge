"""Advisory section scheduling is source metadata, never a model match score."""
import json
import pytest
from tools.engines.matching import semantic_matching as m


class Client:
    chat_completions_url="http://synthetic.invalid/chat/completions"
    def __init__(self): self.seen=[]
    def post_json(self,url,payload,**kw):
        data=json.loads(payload["messages"][1]["content"]);self.seen.append(data)
        fact=next(k for k in data["facts"] if ":results:" in k)
        if data["stage"]=="recall":
            answer={"cards":[{"id":c["id"],"score":80,"requirement_ids":["r1"],
                "citations":[{"fact_id":fact}],"reason":"Evidence"} for c in data["cards"]]}
        else:
            answer={"assessments":[{"requirement_id":r["id"],"status":"partial",
                "citations":[{"fact_id":fact}],"reason":"Fixture"} for r in data["requirements"]]}
        return {"choices":[{"message":{"content":json.dumps(answer)},"finish_reason":"stop"}]}
    def extract_content(self,response):return response["choices"][0]["message"]["content"]


def fixture(tmp_path):
    from tools.engines.matching.requirement_sections import bind_explicit_requirement_sections
    terms=[name+" "+("x"*5400) for name in ("Experience","Education","Java","C++ or Go or Rust")]
    body="任职要求：\n1. "+terms[0]+"\n"+terms[1]+"\n2. 核心技术栈硬性要求\n（1）"+terms[2]+"\n（2）"+terms[3]+"\n3. 其他要求\n"
    sources=[dict(kind="must_have",index=i,quote=t,start=body.index(t),end=body.index(t)+len(t)) for i,t in enumerate(terms)]
    bindings=bind_explicit_requirement_sections(body,sources)
    job=tmp_path/"jp.yaml";job.write_text("target_role: Engineer\nsource_jd: "+json.dumps(body,ensure_ascii=False)+"\nmust_have:\n"+"".join("  - "+json.dumps(t)+"\n" for t in terms))
    card=tmp_path/"ec.yaml";card.write_text("title: Project\nrole_scope: Developer\nresults:\n  - Built services\nartifacts:\n  - Report\n")
    return dict(job_path=job,evidence_files=[card],personal_profile=None,model="fixture",cache_dir=tmp_path/"cache"),bindings


def order(client):return [r["id"] for d in client.seen if d["stage"]=="assess" for r in d["requirements"]]


def test_bound_pending_precedes_generic_without_touching_payload(tmp_path):
    kw,bindings=fixture(tmp_path);client=Client()
    result=m.run_semantic_matching(**kw,client=client,advisory=True,requirement_section_bindings=bindings)
    assert order(client)==["r3","r4","r1","r2"]
    assert result["assessment_schedule"]["entries"][0]["reason"]=="pending_explicit_hard_section"
    assert len(result["assessment_schedule"]["section_bindings"])==2
    assert all("source_section" not in r for d in client.seen for r in d["requirements"])


def test_checked_bound_does_not_jump_pending_generic(tmp_path):
    kw,bindings=fixture(tmp_path);client=Client()
    m.run_semantic_matching(**kw,client=client,advisory=True,requirement_section_bindings=bindings,
                            previous_completed_check_ids=["r3","r4"])
    assert order(client)==["r1","r2","r3","r4"]


def test_corrupt_annotation_fails_before_network(tmp_path):
    kw,bindings=fixture(tmp_path);client=Client();bindings[0]["heading"]["start"]+=1
    with pytest.raises(ValueError,match="semantic_requirement_section_invalid"):
        m.run_semantic_matching(**kw,client=client,advisory=True,requirement_section_bindings=bindings)
    assert client.seen==[]


def test_canonical_ignores_absent_section_metadata_and_cache_survives(tmp_path):
    kw,bindings=fixture(tmp_path);first=Client()
    m.run_semantic_matching(**kw,client=first)
    assert order(first)==["r1","r2","r3","r4"]
    second=Client()
    result=m.run_semantic_matching(**kw,client=second,advisory=True,requirement_section_bindings=bindings)
    assert second.seen==[] and all(e["cache_hit"] for e in result["assessment_schedule"]["entries"])
