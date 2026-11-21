"""Independent pending-order regressions, synthetic responses only."""
import json
from tools.engines.matching import semantic_matching as m


def fixture(tmp_path):
    job=tmp_path/"jp.yaml"
    terms=[prefix+" "+("x"*5400) for prefix in ("5 years related experience", "Bachelor education", "Java engineering", "C++ or Go or Rust")]
    job.write_text("target_role: Engineer\nmust_have:\n"+"".join("  - "+json.dumps(t)+"\n" for t in terms))
    card=tmp_path/"ec.yaml"
    card.write_text('title: Service\nrole_scope: Developer\nresults:\n  - Built services\nartifacts:\n  - Report\n')
    return dict(job_path=job,evidence_files=[card],personal_profile=None,model="fixture",cache_dir=tmp_path/"cache"),terms


class Client:
    chat_completions_url="http://synthetic.invalid/chat/completions"
    def __init__(self):self.seen=[]
    def post_json(self,url,payload,**kw):
        d=json.loads(payload["messages"][1]["content"]);self.seen.append(d)
        fid=next(k for k in d["facts"] if ":results:" in k)
        if d["stage"]=="recall":
            r={"cards":[{"id":c["id"],"score":80,"requirement_ids":["r1"],"citations":[{"fact_id":fid}],"reason":"Relevant"} for c in d["cards"]]}
        else:
            r={"assessments":[{"requirement_id":q["id"],"status":"supported","citations":[{"fact_id":fid}],"reason":"Fixture"} for q in d["requirements"]]}
        return {"choices":[{"message":{"content":json.dumps(r)},"finish_reason":"stop"}]}
    def extract_content(self,r):return r["choices"][0]["message"]["content"]


def assess_order(client):
    return [q["id"] for d in client.seen if d["stage"]=="assess" for q in d["requirements"]]


def test_completed_hint_reorders_pending_without_deleting_hard_requirements(tmp_path):
    kw,terms=fixture(tmp_path);c=Client()
    result=m.run_semantic_matching(**kw,client=c,advisory=True,previous_completed_check_ids=("r1","r2"))
    assert assess_order(c)==["r3","r4","r1","r2"]
    assert set(result["completed_check_ids"])=={"r1","r2","r3","r4"}
    # Existing parser preserves alternatives as one whole check, not three requirements.
    actual=next(q for d in c.seen if d["stage"]=="assess" for q in d["requirements"] if q["id"]=="r4")
    assert actual["criterion"]==terms[3]


def test_no_hint_keeps_hard_education_and_experience_in_source_order(tmp_path):
    kw,_=fixture(tmp_path);c=Client()
    m.run_semantic_matching(**kw,client=c,advisory=True,previous_completed_check_ids=())
    assert assess_order(c)==["r1","r2","r3","r4"]


def test_canonical_default_still_source_order(tmp_path):
    kw,_=fixture(tmp_path);c=Client()
    m.run_semantic_matching(**kw,client=c)
    assert assess_order(c)==["r1","r2","r3","r4"]


def test_all_validated_cache_precedes_network_even_with_new_order(tmp_path):
    kw,_=fixture(tmp_path);first=Client()
    m.run_semantic_matching(**kw,client=first)
    second=Client()
    def no_call(stage):raise AssertionError("Cache hit must not enter network hook")
    result=m.run_semantic_matching(**kw,client=second,advisory=True,
        previous_completed_check_ids=("r1","r2"),before_model_call=no_call)
    assert second.seen==[]
    assert all(e["cache_hit"] for e in result["assessment_schedule"]["entries"])
    assert set(result["completed_check_ids"])=={"r1","r2","r3","r4"}


def test_changed_facts_miss_cache_old_completed_ids_never_supply_results(tmp_path):
    kw,_=fixture(tmp_path);first=Client()
    m.run_semantic_matching(**kw,client=first)
    card=kw["evidence_files"][0]
    card.write_text(card.read_text().replace("Built services","Built changed services"))
    second=Client()
    result=m.run_semantic_matching(**kw,client=second,advisory=True,
        previous_completed_check_ids=("r1","r2","r1","unknown"))
    assert assess_order(second)==["r3","r4","r1","r2"]
    assert all(not e["cache_hit"] for e in result["assessment_schedule"]["entries"])
    assert all(row["citations"][0]["quote"]=="Built changed services"
               for row in result["criterion_assessments"])


def test_three_rounds_accumulate_order_history_without_reusing_conclusions(tmp_path):
    kw,_=fixture(tmp_path)
    terms=["Requirement "+str(i)+" "+("x"*3700) for i in range(6)]
    kw["job_path"].write_text("target_role: Engineer\nmust_have:\n"+"".join("  - "+json.dumps(t)+"\n" for t in terms))
    prior=()
    for turn,expected in enumerate((["r1","r2"],["r3","r4"],["r5","r6"])):
        client=Client()
        # Cache loss/eviction must not cause schedule oscillation. It must also
        # never permit ordering history to stand in for an assessment response.
        round_kw={**kw,"cache_dir":tmp_path/f"cache_round_{turn}"}
        def one_assess(stage):
            if stage=="assess" and any(d["stage"]=="assess" for d in client.seen):
                raise ValueError("semantic_stage_budget_deferred")
        result=m.run_semantic_matching(**round_kw,client=client,advisory=True,
            previous_completed_check_ids=prior,before_model_call=one_assess)
        assert assess_order(client)==expected
        assert result["completed_check_ids"]==expected
        assert [r["requirement_id"] for r in result["criterion_assessments"]
                if r["status"]=="supported"]==expected
        prior=result["assessment_schedule"]["checked_check_ids"]
        assert set(prior)=={f"r{i}" for i in range(1,2*(turn+1)+1)}


def test_snapshot_change_discards_cumulative_order_history(tmp_path,monkeypatch):
    from tools.sidecar.handlers import preparation_semantic as handler
    path=tmp_path/"audit.json"
    monkeypatch.setattr(handler,"_audit_path",lambda _:path)
    record={"schema_version":1,"snapshot":{"input":"old"},"summary":{"input_fresh":True},
            "result":{"completed_check_ids":["r3","r4"],
                      "assessment_schedule":{"policy":"pending_source_requirements_v1",
                                             "checked_check_ids":["r1","r2","r3","r4"]}}}
    record["digest"]=handler._record_digest(record)
    path.write_text(json.dumps(record))
    assert handler._previous_completed_hint("jp",{"input":"old"})==["r1","r2","r3","r4"]
    assert handler._previous_completed_hint("jp",{"input":"new"})==[]



def test_large_advisory_answer_envelope_cannot_starve_complete_duties(tmp_path):
    for reverse in (False, True):
        local = tmp_path / str(reverse)
        local.mkdir()
        kw, _ = fixture(local)
        required = ["；".join(f"完整验证第{i}项并记录证明" for i in range(20)), "同类服务维护经验"]
        duties = ["实施并验证服务接口", "交付并保留审计过程"]
        if reverse:
            required.reverse()
            duties.reverse()
        body = "岗位职责\n" + "\n".join(f"{i+1}. {text}" for i,text in enumerate(duties)) + "\n任职要求\n"
        if reverse:  # The adversarial giant may itself be explicitly bound as a hard requirement.
            from tools.engines.matching.requirement_sections import bind_explicit_requirement_sections
            giant = required[1]
            body += "1. 普通要求\n2. 核心技术栈硬性要求\n（1）"+giant+"\n3. 综合要求\n"
            start = body.index(giant)
            bindings = bind_explicit_requirement_sections(body, [{"kind":"must_have","index":1,
                "quote":giant,"start":start,"end":start+len(giant)}])
            assert len(bindings)==1
            kw["requirement_section_bindings"] = bindings
        kw["job_path"].write_text("target_role: Engineer\nsource_jd: "+json.dumps(body)+"\nmust_have:\n"+
                                  "".join("  - "+json.dumps(text)+"\n" for text in required))
        kw["evidence_files"][0].write_text(
            'title: A service\nrole_scope: 本人负责后端实施\ncontext: 仅限本地验收\n'
            'time_range: 2023-2024\nactions:\n  - 完成关联接口与异常测试\nresults:\n  - Built services\nartifacts:\n  - Report\n'
        )
        first = Client()

        def one_assess(stage):
            if stage == "assess" and assess_order(first):
                raise ValueError("semantic_stage_budget_deferred")

        initial = m.run_semantic_matching(**kw, client=first, advisory=True, before_model_call=one_assess)
        tall = "r2" if reverse else "r1"
        assert set(initial["completed_check_ids"]) == {"d1","d2", "r1" if reverse else "r2"}
        assert {f"{tall}.c{i}" for i in range(1,21)} == set(initial["budget_deferred_check_ids"])
        segmented_reason = 'pending_segmented_hard_parent' if reverse else 'pending_segmented_parent'
        assert all(e['reason']==segmented_reason for e in initial['assessment_schedule']['entries']
                   if e['outcome']=='budget_deferred')
        # Existing parent rollup must keep partially dispatched compound requirements unknown.
        from tools.sidecar.handlers.preparation_semantic import _safe_summary
        from types import SimpleNamespace
        flags = SimpleNamespace(model_calls=0, budget_exhausted=True, provider_timeout=False)
        inputs = {"direction":None,"evidence_files":kw["evidence_files"],"pool":{}}
        assert next(a for a in _safe_summary("jp",inputs,flags,initial,"")["assessments"]
                    if a["requirement_id"]==tall)["status"] == "unassessed"
        second = Client()
        def one_segment(stage):
            if stage == "assess" and assess_order(second):
                raise ValueError("semantic_stage_budget_deferred")
        partial = m.run_semantic_matching(**kw, client=second, advisory=True,
            before_model_call=one_segment,
            previous_completed_check_ids=initial["assessment_schedule"]["checked_check_ids"])
        child_ids = {f"{tall}.c{i}" for i in range(1,21)}
        assert set(assess_order(second)) < child_ids and assess_order(second)
        assert next(a for a in _safe_summary("jp",inputs,flags,partial,"")["assessments"]
                    if a["requirement_id"]==tall)["status"] == "unassessed"
        third = Client()
        improved = m.run_semantic_matching(**kw, client=third, advisory=True,
            previous_completed_check_ids=partial["assessment_schedule"]["checked_check_ids"])
        assert set(assess_order(third)) == child_ids - set(assess_order(second))
        assert len([d for d in third.seen if d["stage"]=="assess"]) <= 4
        assert len(improved["completed_check_ids"]) == 23
        assert any(e["outcome"]=="cache_validated" for e in improved["assessment_schedule"]["entries"])
        first_facts = next(p["facts"] for p in first.seen if p["stage"]=="assess")
        assert all(d["facts"]==first_facts for d in [*second.seen,*third.seen] if d["stage"]=="assess")
        assert first_facts["ec:actions:0"]["source_role"]=="本人负责后端实施"
        assert first_facts["ec:context:0"]["text"]=="仅限本地验收"
        assert first_facts["ec:results:0"]["text"]=="Built services"

def test_answer_work_estimate_reserves_schema_fields_and_known_fact_identifier_size():
    checks = [{"id": "r1", "parent_id": "r1"}, {"id": "d1.c1", "parent_id": "d1"}]
    ordinary = m._assessment_output_estimate(checks, {"ec:actions:0": {}})
    enlarged = m._assessment_output_estimate(checks, {"ec:actions:" + "长"*100: {}})
    assert enlarged > ordinary > 960  # reason and two full optional quote slots per row
