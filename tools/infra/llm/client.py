from __future__ import annotations

import json
from typing import Any, Mapping, cast
from urllib import request
from http.client import HTTPResponse
from tools.prompts.context import with_job_search_context


KEYLESS_PROVIDERS = frozenset({"lm_studio", "strata"})


def provider_is_keyless(provider: str = "") -> bool:
    """本地 OpenAI 兼容 provider 默认无鉴权；未显式传 provider 时读 LLM_PROVIDER。"""
    import os

    value = (provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
    return value in KEYLESS_PROVIDERS


def llm_request_available(
    *,
    provider: str = "",
    api_key: str = "",
    model: str = "",
) -> bool:
    """判断当前配置能否发起 LLM 请求：必须有 model；keyless 本地 provider 无需 API Key。"""
    if not str(model or "").strip():
        return False
    if str(api_key or "").strip():
        return True
    return provider_is_keyless(provider)


def llm_timeout_from_env(default: int = 120) -> int:
    """管线子进程从 `LLM_TIMEOUT`（App 系统设置的超时秒数，由 sidecar 注入）读取；缺失或非法时回退默认值。"""
    import os

    raw = os.getenv("LLM_TIMEOUT", "")
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _thinking_enabled_from_env() -> bool:
    import os

    return os.getenv("LLM_THINKING", "").strip().lower() in ("on", "1", "true", "yes")


_THINKING_EFFORTS = ("low", "high", "max")


def _normalize_thinking_effort(value: object) -> str:
    effort = str(value or "").strip().lower()
    return effort if effort in _THINKING_EFFORTS else "high"


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 120,
        *,
        provider: str = "",
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        import os

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._provider = (provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
        self._thinking_enabled = (
            _thinking_enabled_from_env()
            if thinking_enabled is None
            else bool(thinking_enabled)
        )
        self._reasoning_effort = _normalize_thinking_effort(
            reasoning_effort
            if reasoning_effort is not None
            else os.getenv("LLM_THINKING_EFFORT", "high")
        )

    @property
    def chat_completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self._base_url}/models"

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def extract_content(response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if not isinstance(content, str):
            return ""
        return content

    def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        payload = with_job_search_context(payload)
        if self._provider == "deepseek":
            # DeepSeek 的 json_object 请求若开启 thinking，推理会耗尽较小的输出预算，
            # 导致结构化正文为空；结构化输出默认关闭思考，显式 thinking 仍由调用方决定。
            if (
                payload.get("response_format") == {"type": "json_object"}
                and "thinking" not in payload
            ):
                payload = {**payload, "thinking": {"type": "disabled"}}
            if "thinking" not in payload:
                payload = {
                    **payload,
                    "thinking": {
                        "type": "enabled" if self._thinking_enabled else "disabled"
                    },
                }
                if self._thinking_enabled and "reasoning_effort" not in payload:
                    payload = {**payload, "reasoning_effort": self._reasoning_effort}
        if (
            self._provider == "lm_studio"
            and payload.get("response_format") == {"type": "json_object"}
        ):
            # LM Studio 使用对象 schema 表达 JSON 模式，不修改调用方的业务契约。
            payload = {
                **payload,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "json_object",
                        "schema": dict(response_schema) if response_schema is not None else {"type": "object"},
                    },
                },
            }
            if (
                payload.get("model") in ("qwen/qwen3.8-27b", "qwen3.8-flash-next@q2_k")
                and "reasoning_effort" not in payload
            ):
                # 已定位这些型号会把结构化输出预算耗在推理中；仅调整本次请求。
                payload = {**payload, "reasoning_effort": "none"}
        if self._provider == "strata" and "reasoning_effort" not in payload:
            # Strata（Qwen3.8 本地 OpenAI 兼容服务）用请求顶层 reasoning_effort 控制思考，
            # 不识别 DeepSeek 风格 thinking 对象；结构化 JSON 请求把输出预算留给正文。
            if (
                payload.get("response_format") == {"type": "json_object"}
                or not self._thinking_enabled
            ):
                reasoning_effort = "none"
            else:
                reasoning_effort = (
                    "high" if self._reasoning_effort == "max" else self._reasoning_effort
                )
            payload = {**payload, "reasoning_effort": reasoning_effort}
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers=self.build_headers(), method="POST")
        resp = cast(HTTPResponse, request.urlopen(req, timeout=self._timeout))
        try:
            body = resp.read().decode("utf-8")
        finally:
            resp.close()
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
        return {}

    def list_models(self) -> list[str]:
        req = request.Request(
            self.models_url,
            headers=self.build_headers(),
            method="GET",
        )
        resp = cast(HTTPResponse, request.urlopen(req, timeout=self._timeout))
        try:
            body = resp.read().decode("utf-8")
        finally:
            resp.close()
        parsed = json.loads(body or "{}")
        if not isinstance(parsed, dict):
            return []
        data = parsed.get("data")
        if not isinstance(data, list):
            return []
        models: list[str] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
        return models
