from __future__ import annotations

import json

from tools.domain.models import EvidenceCard
from tools.infra.llm.client import LLMClient


class LLMEvidenceExtractor:
    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    def extract(self, raw_material: str) -> EvidenceCard:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Extract evidence card JSON with keys: "
                        "id,title,raw_source,results,artifacts,tags. "
                        f"Input:\n{raw_material}"
                    ),
                }
            ],
        }
        response = self._client.post_json(self._client.chat_completions_url, payload)
        content = self._client.extract_content(response)

        parsed: dict[str, object]
        try:
            loaded = json.loads(content)
            parsed = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed = {}

        return EvidenceCard(
            id=str(parsed.get("id", "ec-llm-generated")),
            title=str(parsed.get("title", "LLM Evidence")),
            raw_source=str(parsed.get("raw_source", raw_material)),
            results=tuple(_ensure_str_list(parsed.get("results"))),
            artifacts=tuple(_ensure_str_list(parsed.get("artifacts"))),
            tags=tuple(_ensure_str_list(parsed.get("tags"))),
        )


def _ensure_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        output.append(str(item))
    return output
