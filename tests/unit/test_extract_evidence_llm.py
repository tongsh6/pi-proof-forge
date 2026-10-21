"""证据提炼 CLI 的 keyless/base_url 安全：本地 provider 不能悄悄落到 OpenAI 默认地址。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

from tools import extract_evidence_llm


def _main(argv: list[str], env: dict[str, str]) -> int:
    with (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch.object(sys, "argv", ["extract_evidence_llm.py", *argv]),
    ):
        return extract_evidence_llm.main()


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    input_path = tmp_path / "raw.txt"
    input_path.write_text("个人工作汇总：负责订单改造。", encoding="utf-8")
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("证据提炼：<RAW_MATERIAL>", encoding="utf-8")
    return input_path, prompt_path


def test_keyless_without_base_url_does_not_fall_back_to_openai(
    tmp_path: Path, capsys
) -> None:
    input_path, prompt_path = _inputs(tmp_path)
    argv = ["--input", str(input_path), "--prompt", str(prompt_path)]
    env = {"LLM_PROVIDER": "strata", "LLM_MODEL": "qwen3.8-flash-next-q2_0"}

    with mock.patch(
        "tools.extract_evidence_llm.LLMClient",
        side_effect=AssertionError(
            "keyless provider without base_url must not construct LLMClient"
        ),
    ) as client_class:
        code = _main(argv, env)

    captured = capsys.readouterr()
    assert code == 1
    assert "base URL" in captured.err
    assert "api.openai.com" not in captured.err
    assert client_class.call_count == 0


def test_keyless_with_base_url_runs_without_api_key(tmp_path: Path) -> None:
    input_path, prompt_path = _inputs(tmp_path)
    output_path = tmp_path / "evidence.yaml"
    captured: list[dict[str, object]] = []

    class FakeClient:
        chat_completions_url = "http://fake/v1/chat/completions"

        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

        def post_json(self, url: str, payload: dict) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

        @staticmethod
        def extract_content(response: dict) -> str:
            return response["choices"][0]["message"]["content"]

    argv = [
        "--input",
        str(input_path),
        "--prompt",
        str(prompt_path),
        "--output",
        str(output_path),
    ]
    env = {
        "LLM_PROVIDER": "strata",
        "LLM_MODEL": "qwen3.8-flash-next-q2_0",
        "LLM_BASE_URL": "http://127.0.0.1:8081/v1",
    }

    with mock.patch("tools.extract_evidence_llm.LLMClient", FakeClient):
        code = _main(argv, env)

    assert code == 0
    assert captured[0]["api_key"] == ""
    assert captured[0]["base_url"] == "http://127.0.0.1:8081/v1"
    assert output_path.read_text(encoding="utf-8") == "{}"


def test_online_provider_without_api_key_reports_missing_key(
    tmp_path: Path, capsys
) -> None:
    input_path, prompt_path = _inputs(tmp_path)
    argv = ["--input", str(input_path), "--prompt", str(prompt_path)]
    env = {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4"}

    with mock.patch(
        "tools.extract_evidence_llm.LLMClient",
        side_effect=AssertionError("missing key must not construct LLMClient"),
    ) as client_class:
        code = _main(argv, env)

    captured = capsys.readouterr()
    assert code == 1
    assert "Missing API key" in captured.err
    assert client_class.call_count == 0


def test_online_provider_with_api_key_keeps_openai_default_base_url(
    tmp_path: Path,
) -> None:
    input_path, prompt_path = _inputs(tmp_path)
    captured: list[dict[str, object]] = []

    class FakeClient:
        chat_completions_url = "http://fake/v1/chat/completions"

        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

        def post_json(self, url: str, payload: dict) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

        @staticmethod
        def extract_content(response: dict) -> str:
            return response["choices"][0]["message"]["content"]

    argv = ["--input", str(input_path), "--prompt", str(prompt_path)]
    env = {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "gpt-4",
        "LLM_API_KEY": "sk-test-only",
    }

    with mock.patch("tools.extract_evidence_llm.LLMClient", FakeClient):
        code = _main(argv, env)

    assert code == 0
    assert captured[0]["base_url"] == extract_evidence_llm.DEFAULT_BASE_URL
    assert captured[0]["api_key"] == "sk-test-only"
