from __future__ import annotations

import json
from typing import Any, Mapping, cast
from urllib import request
from urllib.parse import urlsplit
import re
from http.client import HTTPResponse
from tools.prompts.context import with_job_search_context


KEYLESS_PROVIDERS = frozenset({"lm_studio", "strata"})

# 推理后台瞬时 5xx（如 Strata App Host 在并发长请求下 300s fetch 超时返回 502）：
# 有限重试，不重试 4xx，也不改变调用方业务契约。
_RETRYABLE_HTTP_STATUS = frozenset({502, 503, 504})
_RETRY_DELAYS_SECONDS = (2.0, 5.0)

# Strata App 管理的统一推理后台：产品侧只连这一个 OpenAI 兼容入口，
# 模型由 App 加载/切换，端点固定，不在设置页另行配置。
STRATA_UNIFIED_BASE_URL = "http://127.0.0.1:47831/v1"


def default_base_url(provider: str = "", fallback: str = "") -> str:
    """按 provider 选择缺省地址：Strata 统一后台固定入口，其他 provider 用调用方默认。"""
    import os

    value = (provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
    return STRATA_UNIFIED_BASE_URL if value == "strata" else fallback


def provider_is_keyless(provider: str = "") -> bool:
    """本地 OpenAI 兼容 provider 默认无鉴权；未显式传 provider 时读 LLM_PROVIDER。"""
    import os

    value = (provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
    return value in KEYLESS_PROVIDERS


def is_loopback_base_url(base_url: str = "") -> bool:
    """Only explicitly spelled HTTP(S) loopback authorities permit keyless compatible requests."""
    if not isinstance(base_url, str) or any(c.isspace() or ord(c) < 32 for c in base_url) or "\\" in base_url:
        return False
    try:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not re.fullmatch(
            r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]+)?", parsed.netloc, re.I
        ):
            return False
        return parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        return False


def llm_request_available(
    *,
    provider: str = "",
    api_key: str = "",
    model: str = "",
    base_url: str = "",
) -> bool:
    """判断当前配置能否发起 LLM 请求：必须有 model；keyless 本地 provider 无需 API Key。"""
    if not str(model or "").strip():
        return False
    if str(api_key or "").strip():
        return True
    import os
    value = (provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
    return provider_is_keyless(provider) or (
        value == "openai_compatible" and is_loopback_base_url(base_url)
    )


def llm_timeout_from_env(default: int = 120) -> int:
    """管线子进程从 `LLM_TIMEOUT`（App 系统设置的超时秒数，由 sidecar 注入）读取；缺失或非法时回退默认值。"""
    import os

    raw = os.getenv("LLM_TIMEOUT", "")
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _thinking_enabled_from_env() -> bool | None:
    import os

    value = os.getenv("LLM_THINKING", "").strip().lower()
    if value in ("on", "1", "true", "yes"):
        return True
    if value in ("off", "0", "false", "no"):
        return False
    return None


_THINKING_EFFORTS = ("low", "high", "max")
# Omission reads the CLI environment; explicit None keeps the provider default.
_THINKING_UNSET = object()


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
        thinking_enabled: bool | None = cast(bool | None, _THINKING_UNSET),
        reasoning_effort: str | None = None,
    ) -> None:
        import os

        self._provider = (provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
        effective_base_url = str(base_url or "").strip()
        if not effective_base_url and self._provider == "strata":
            # Strata 统一推理后台有唯一入口；未显式给地址时不落到 OpenAI 默认地址。
            effective_base_url = STRATA_UNIFIED_BASE_URL
        self._base_url = effective_base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._thinking_enabled = (
            _thinking_enabled_from_env()
            if thinking_enabled is _THINKING_UNSET
            else thinking_enabled
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

    def _open_with_retry(self, req: request.Request) -> HTTPResponse:
        """对瞬时 502/503/504 做有限重试；本地/远程 provider 通用，4xx 不重试。"""
        import time
        from urllib.error import HTTPError

        for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
            try:
                return cast(HTTPResponse, request.urlopen(req, timeout=self._timeout))
            except HTTPError as exc:
                if (
                    exc.code not in _RETRYABLE_HTTP_STATUS
                    or attempt >= len(_RETRY_DELAYS_SECONDS)
                ):
                    raise
                time.sleep(_RETRY_DELAYS_SECONDS[attempt])
        raise RuntimeError("unreachable")

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
        return self.send_request(self.prepare_request(url, payload, response_schema=response_schema))

    def prepare_request(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> request.Request:
        """Assemble and serialize once, without transport or caller-data mutation."""
        payload = with_job_search_context(payload)
        if self._provider == "deepseek":
            if "thinking" not in payload:
                payload = {
                    **payload,
                    "thinking": {
                        "type": "enabled" if self._thinking_enabled is True else "disabled"
                    },
                }
                if self._thinking_enabled is True and "reasoning_effort" not in payload:
                    payload = {**payload, "reasoning_effort": self._reasoning_effort}
        elif self._provider == "strata":
            if "reasoning_effort" not in payload:
                effort = "none"
                if self._thinking_enabled is True:
                    effort = "high" if self._reasoning_effort == "max" else self._reasoning_effort
                payload = {**payload, "reasoning_effort": effort}
        elif self._thinking_enabled is not None and "reasoning_effort" not in payload:
            effort = self._reasoning_effort if self._thinking_enabled is True else "none"
            payload = {**payload, "reasoning_effort": effort}
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
        if response_schema is not None and payload.get("response_format") == {"type": "json_object"}:
            # JSON-object providers still need the complete caller-owned output contract.
            # Native schema requests above, and explicit formats, keep their wire protocol.
            instruction = (
                "输出必须符合以下 JSON Schema；仅返回符合该结构的 JSON 对象，不输出 schema 本身：\n"
                + json.dumps(dict(response_schema), ensure_ascii=False, sort_keys=True)
            )
            messages = cast(list[dict[str, Any]], payload.get("messages", []))
            first = messages[0] if messages else None
            if isinstance(first, dict) and first.get("role") == "system" and isinstance(first.get("content"), str):
                messages = [{**first, "content": first["content"] + "\n\n" + instruction}, *messages[1:]]
            else:
                messages = [{"role": "system", "content": instruction}, *messages]
            payload = {**payload, "messages": messages}
        data = json.dumps(payload).encode("utf-8")
        return request.Request(url, data=data, headers=self.build_headers(), method="POST")

    def send_request(self, req: request.Request) -> dict[str, Any]:
        """Send the accepted URL/body unchanged through the existing transport."""
        resp = self._open_with_retry(req)
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
        resp = self._open_with_retry(req)
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
