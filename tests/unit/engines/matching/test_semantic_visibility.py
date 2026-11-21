"""Assessed input scope is explicit, never inferred from all recalled cards."""
import json
from tools.engines.matching import semantic_matching as m
from tools.infra.llm.client import LLMClient

def test_bounded_selection_deterministic_despite_input_insertion_order():
    facts={key:{"source_id":key.split(":")[0],"field":"results","text":"a"*40} for key in ("z:results:0","a:results:0","b:results:0")}
    fits=lambda selected: len(m._json(m._wire_facts(selected, assessment=True))) <= 100
    selected=m._bounded_assessment_facts(facts,{"z:results:0","a:results:0"},fits)
    reverse=m._bounded_assessment_facts(dict(reversed(list(facts.items()))),set(reversed(["z:results:0","a:results:0"])),fits)
    assert selected==reverse
    assert list(selected)==["a:results:0"]

def test_result_scope_matches_actual_assess_payload(tmp_path):
    job=tmp_path/"jp.yaml"
    job.write_text('target_role: "Engineer"\nmust_have:\n  - "Java services"\n')
    paths=[]
    for index in range(3):
        path=tmp_path/f"ec_{index}.yaml"
        path.write_text(f'title: "Service"\nrole_scope: "Developer"\nresults:\n  - "Built Java services"\nartifacts:\n  - "Report"\nactions:\n  - "Implemented reliable services"\n')
        paths.append(path)
    class Client(LLMClient):
        def __init__(self):
            super().__init__("http://local.invalid", "", provider="openai_compatible")
            self.seen=[]
        def send_request(self, request):
            payload=json.loads(request.data)
            data=json.loads(payload["messages"][1]["content"])
            if data["stage"]=="recall":
                rows=[]
                for card in data["cards"]:
                    fid=next(k for k in card["facts"] if ":results:" in k)
                    rows.append({"id":card["id"],"score":80,"requirement_ids":["r1"],"citations":[{"fact_id":fid}],"reason":"Relevant"})
                response={"cards":rows}
            else:
                self.seen.append(set(data["facts"]))
                fid=next(k for k in data["facts"] if ":results:" in k)
                response={"assessments":[{"requirement_id":r["id"],"status":"supported","citations":[{"fact_id":fid}],"reason":"Built services"} for r in data["requirements"]]}
            return {"choices":[{"message":{"content":json.dumps(response)},"finish_reason":"stop"}]}
        def extract_content(self,response):return response["choices"][0]["message"]["content"]
    client=Client()
    result=m.run_semantic_matching(job_path=job,evidence_files=paths,personal_profile=None,client=client,model="fixture",cache_dir=tmp_path/"cache")
    visible=result["assessment_visibility"]
    assert set(visible["visible_fact_ids"])==client.seen[0]
    assert visible["visible_fact_count"]==len(client.seen[0])
    assert visible["total_fact_count"]==len(result["facts"])
    assert visible["omitted_fact_count"]>0
    assert set(visible["omitted_fact_ids"])==set(result["facts"])-client.seen[0]
    assert visible["scope"]=="bounded_fact_subset_not_exhaustive"
    assert visible["visible_card_ids"]==["ec_0","ec_1","ec_2"]
    assert visible["total_card_count"]==3


def test_advisory_assessment_admits_late_complete_facts_before_deepening_early_cards():
    facts = {}
    for idx in range(114):
        cid = f"ec_{idx:03}"
        role = "" if idx == 17 else ("仅参加评审，不负责实现" if idx == 8 else "负责后端服务开发")
        work = "保障跨系统状态一致，处理异步重放" if idx in (48, 95) else "改进数据接收与处理链路" * (1 + idx % 5)
        if idx == 3:
            work = "有出处但无法在窗口完整传输的长行动" * 1500
        for field, text in (
            ("actions", work), ("results", "验证链路结果并记录边界" * (2 + idx % 4)),
            ("context", "只涵盖已验收的本阶段模块"), ("time_range", "2023至2024"),
        ):
            facts[f"{cid}:{field}:0"] = dict(source_id=cid, field=field, text=text, source_role=role,
                                             source_qualifiers=["本人所做仅限后端"])
    measure = lambda value: len(m._json(m._json(value))) - 2
    budget = 22_000
    cited = {"ec_000:results:0"}
    fits = lambda selected: measure(m._wire_facts(selected, assessment=True)) <= budget
    old = m._bounded_assessment_facts(facts, cited, fits)
    new = m._bounded_assessment_facts(facts, cited, fits, breadth_first=True)
    reversed_new = m._bounded_assessment_facts(dict(reversed(list(facts.items()))), cited, fits,
                                               breadth_first=True)
    work_cards = lambda selection: {row["source_id"] for row in selection.values()
                                    if row["field"] in ("actions", "results")}
    assert new == reversed_new
    assert measure(m._wire_facts(new, assessment=True)) <= budget
    assert cited <= new.keys()
    assert len(work_cards(new)) > len(work_cards(old))
    assert "ec_048" in work_cards(new) - work_cards(old)
    assert "ec_095" not in work_cards(new)  # bounded, not all cards represented
    assert new["ec_048:actions:0"] == facts["ec_048:actions:0"]
    assert {"ec_048:context:0", "ec_048:time_range:0"} <= new.keys()
    assert new["ec_008:actions:0"]["source_role"] == "仅参加评审，不负责实现"
    assert new["ec_008:actions:0"]["source_qualifiers"] == ["本人所做仅限后端"]
    assert "ec_017" not in work_cards(new)
    assert "ec_003:actions:0" not in new and "ec_003:results:0" in new
