from __future__ import annotations

import json
from collections.abc import Sequence

from tools.domain.models import EvidenceCard, JobProfile, MatchingReport
from tools.infra.llm.client import LLMClient


class LLMMatchingEngine:
    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    def score(
        self,
        evidence_cards: Sequence[EvidenceCard],
        profile: JobProfile,
    ) -> MatchingReport:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": _build_prompt(evidence_cards, profile),
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

        card_ids = tuple(str(v) for v in _as_list(parsed.get("evidence_card_ids")))
        gap_tasks = tuple(str(v) for v in _as_list(parsed.get("gap_tasks")))
        breakdown_raw = parsed.get("score_breakdown")
        breakdown: dict[str, float] = {}
        if isinstance(breakdown_raw, dict):
            for key, value in breakdown_raw.items():
                breakdown[str(key)] = float(value)

        return MatchingReport(
            job_profile_id=profile.id,
            evidence_card_ids=card_ids,
            score_breakdown=breakdown,
            gap_tasks=gap_tasks,
        )


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _build_prompt(evidence_cards: Sequence[EvidenceCard], profile: JobProfile) -> str:
    lines = [
        "Return JSON with keys: evidence_card_ids, score_breakdown, gap_tasks.",
        f"JobProfile: {profile.title}; keywords={list(profile.keywords)}; must_have={list(profile.must_have)}",
        "EvidenceCards:",
    ]
    for card in evidence_cards:
        lines.append(
            f"- id={card.id}, title={card.title}, tags={list(card.tags)}, results={list(card.results)}"
        )
    return "\n".join(lines)
