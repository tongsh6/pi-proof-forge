"""生成阶段 LLM 选择 gate：keyless 本地 provider 放行，在线 provider 缺 Key 阻断。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tools import run_generation
from tools.infra.career_profile import inspect_career

_RUN_ID = "qr_gate"
_CARD = (
    'id: "ec1"\n'
    'title: "交易服务"\n'
    'context: "订单查询慢"\n'
    'role_scope: "模块开发"\n'
    'time_range: "2024-01 ~ 2024-06"\n'
    'status: "saved_eligible"\n'
    'candidate_pool_eligible: "true"\n'
    "actions:\n"
    '  - "实现 Java 接口与 Redis 缓存"\n'
    "results:\n"
    '  - "回归验证通过"\n'
    "stack:\n"
    '  - "Java"\n'
    "artifacts:\n"
    '  - "报告"\n'
)


def _write_generation_fixture(root: Path) -> dict[str, Path]:
    source = root / "evidence_cards"
    source.mkdir(parents=True)
    (source / "ec1.yaml").write_text(_CARD, encoding="utf-8")
    staged = root / "outputs" / "quick_runs" / _RUN_ID / "evidence_cards"
    staged.mkdir(parents=True)
    (staged / "ec1.yaml").write_text(_CARD, encoding="utf-8")

    career = {
        "schema_version": 1,
        "summary": "交易服务开发。",
        "work": [
            {
                "id": "w1",
                "company": "合成公司",
                "department": "研发",
                "title": "工程师",
                "start": "2022-01",
                "end": "2025-01",
                "current": False,
                "scope": "订单服务",
                "contributions": ["承担接口开发"],
                "evidence_ids": ["ec1"],
            }
        ],
        "education_visibility": "omit",
        "education": [],
        "skills": [
            {
                "id": "s1",
                "category": "服务开发",
                "description": "Java 接口与缓存设计",
                "evidence_ids": ["ec1"],
            }
        ],
        "extras": [],
    }
    fields = {
        "name": "测试人",
        "phone": "13800000000",
        "email": "test@example.com",
        "city": "上海",
        "current_position": "工程师",
        "career_json": json.dumps(career, ensure_ascii=False),
    }
    state = inspect_career(fields, source)
    fields["career_review_json"] = json.dumps({"revision": state["revision"]})
    profile = root / "personal_profile.yaml"
    profile.write_text(
        "\n".join(
            f"{key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in fields.items()
        )
        + "\n",
        encoding="utf-8",
    )

    job = root / "job.yaml"
    job.write_text(
        'target_role: "后端工程师"\n'
        'company: "目标公司"\n'
        'source_jd: "负责订单服务与缓存治理"\n'
        "keywords:\n"
        '  - "Java"\n',
        encoding="utf-8",
    )
    report = root / f"mr-{_RUN_ID}.yaml"
    report.write_text(
        'score_total: 80\ntop_cards:\n  - id: "ec1"\n', encoding="utf-8"
    )
    return {
        "profile": profile,
        "job": job,
        "report": report,
        "evidence": staged,
        "output": root / "outputs" / _RUN_ID,
    }


def _argv(paths: dict[str, Path], *extra: str) -> list[str]:
    return [
        "generate",
        "--matching-report",
        str(paths["report"]),
        "--output-dir",
        str(paths["output"]),
        "--evidence-dir",
        str(paths["evidence"]),
        "--personal-profile",
        str(paths["profile"]),
        "--job-profile",
        str(paths["job"]),
        *extra,
    ]


def test_keyless_strata_allows_llm_selection_without_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _write_generation_fixture(tmp_path)
    captured: list[dict] = []

    class FakeClient:
        chat_completions_url = "http://127.0.0.1:8081/v1/chat/completions"

        def __init__(self, **kwargs) -> None:
            captured.append(kwargs)

        def post_json(self, url: str, payload: dict) -> dict:
            content = json.dumps({"evidence_ids": ["ec1"]})
            return {"choices": [{"message": {"content": content}}]}

        @staticmethod
        def extract_content(response: dict) -> str:
            return response["choices"][0]["message"]["content"]

    monkeypatch.setenv("LLM_PROVIDER", "strata")
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-flash-next-q2_0")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8081/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", _argv(paths, "--use-llm", "--require-llm"))
    monkeypatch.setattr(run_generation, "LLMClient", FakeClient)

    assert run_generation._legacy_main() == 0

    assert captured[0]["api_key"] == ""
    assert captured[0]["base_url"] == "http://127.0.0.1:8081/v1"
    trace = json.loads(
        (paths["output"] / f"resume_mr-{_RUN_ID}_A.trace.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["generation_strategy"] == "llm_selection_locked_evidence_fields"


def test_online_provider_without_api_key_blocks_required_llm(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _write_generation_fixture(tmp_path)
    constructed: list[dict] = []

    class ForbiddenClient:
        def __init__(self, **kwargs) -> None:
            constructed.append(kwargs)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", _argv(paths, "--use-llm", "--require-llm"))
    monkeypatch.setattr(run_generation, "LLMClient", ForbiddenClient)

    assert run_generation._legacy_main() == 1
    assert constructed == []
    assert not (paths["output"] / f"resume_mr-{_RUN_ID}_A.md").exists()
