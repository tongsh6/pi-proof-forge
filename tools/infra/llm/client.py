from __future__ import annotations

import json
from typing import Any, Mapping, cast
from urllib import request
from http.client import HTTPResponse


class LLMClient:
    def __init__(
        self, base_url: str, api_key: str, timeout: int = 120, *, provider: str = ""
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._provider = provider

    @property
    def chat_completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self._base_url}/models"

    def build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

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
                payload.get("model") == "qwen/qwen3.8-27b"
                and "reasoning_effort" not in payload
            ):
                # 该模型结构化提取已实测需关闭推理，仅设置本次请求，不改变 LM Studio 全局配置。
                payload = {**payload, "reasoning_effort": "none"}
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
