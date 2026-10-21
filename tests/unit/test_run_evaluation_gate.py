"""质量判项 gate：keyless 本地 provider 放行，在线 provider 缺 Key 时不调用模型。"""

from __future__ import annotations

from tools import run_evaluation


class _FakeJudgeClient:
    chat_completions_url = "http://127.0.0.1:8081/v1/chat/completions"

    def __init__(self) -> None:
        self.calls = 0

    def post_json(self, url: str, payload: dict) -> dict:
        self.calls += 1
        return {"choices": [{"message": {"content": "{}"}}]}

    @staticmethod
    def extract_content(response: dict) -> str:
        return response["choices"][0]["message"]["content"]


def _gate_kwargs() -> dict:
    return {
        "resume_text": "# 张三\n## 项目经历\n- 负责平台交付\n",
        "trace": {},
        "semantic_review": {
            "mode": "semantic",
            "requirements": [
                {"requirement_id": "d1", "kind": "must_have", "text": "负责平台交付"},
            ],
        },
        "job_profile_path": None,
        "use_llm": True,
        "model": "m",
        "api_key": "",
        "base_url": "http://127.0.0.1:8081/v1",
    }


def _patch_judge_deps(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PPF_QUALITY_JUDGE_CACHE_DIR", str(tmp_path / "judge-cache"))
    monkeypatch.setattr(run_evaluation, "_load_quality_cards", lambda trace: {})
    monkeypatch.setattr(
        run_evaluation.quality_judge_cache,
        "load_decisions",
        lambda *args, **kwargs: {"rejected": [], "selected": []},
    )
    monkeypatch.setattr(
        run_evaluation.quality_judge_cache,
        "load_judgment",
        lambda *args, **kwargs: None,
    )


def test_keyless_local_provider_does_not_disqualify_quality_judge(
    tmp_path, monkeypatch
) -> None:
    _patch_judge_deps(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "strata")
    client = _FakeJudgeClient()

    judgments, meta, decisions = run_evaluation._run_quality_judge(
        client_factory=lambda: client, **_gate_kwargs()
    )

    # gate 已放行：meta 进入模型判项路径，而不是因缺 Key 提前 disabled。
    assert meta["cache"] == "miss"
    assert meta.get("reason") != "llm_not_configured_or_no_jd_items"
    assert client.calls == 2  # 空判项触发一次纠错，证明确实调用了模型
    assert judgments is None
    assert decisions == {"rejected": [], "selected": []}


def test_online_provider_without_key_disables_quality_judge(
    tmp_path, monkeypatch
) -> None:
    _patch_judge_deps(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    created: list[dict] = []

    def forbidden_factory() -> _FakeJudgeClient:
        created.append({})
        raise AssertionError("缺 Key 的在线 provider 不得调用模型")

    judgments, meta, decisions = run_evaluation._run_quality_judge(
        client_factory=forbidden_factory, **_gate_kwargs()
    )

    assert judgments is None
    assert meta == {
        "cache": "disabled",
        "reason": "llm_not_configured_or_no_jd_items",
    }
    assert decisions == {"rejected": [], "selected": []}
    assert created == []
