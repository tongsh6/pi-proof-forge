from __future__ import annotations

import json
from typing import Any, Mapping, cast
from urllib import request
from http.client import HTTPResponse


class LLMClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def chat_completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

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

    def post_json(self, url: str, payload: Mapping[str, object]) -> dict[str, Any]:
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
