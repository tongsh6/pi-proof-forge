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
                try:
                    breakdown[str(key)] = float(value)
                except (TypeError, ValueError):
                    if isinstance(value, dict):
                        inner_total = value.get("total") or value.get("score") or value.get("value") or 0
                        try:
                            breakdown[str(key)] = float(inner_total)
                        except (TypeError, ValueError):
                            breakdown[str(key)] = 0.0
                    else:
                        breakdown[str(key)] = 0.0

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
        "You are a resume matching expert. For each evidence card, evaluate how well it matches the job profile.",
        "Return ONLY valid JSON (no markdown, no explanation) with keys: evidence_card_ids (list of selected card ids, sorted by relevance desc), score_breakdown (object with K/Q/E/total scores 0-1), gap_tasks (list of missing skill/experience areas).",
        f"Job Title: {profile.title}",
        f"Required Keywords: {list(profile.keywords)}",
        f"Must-Have: {list(profile.must_have)}",
        f"Nice-to-Have: {list(profile.nice_to_have)}",
        "",
        "Evidence Cards:",
    ]
    for card in evidence_cards:
        lines.append(
            f"- id={card.id}, title={card.title}, stack={list(card.stack)}, tags={list(card.tags)}, results={list(card.results)}"
        )
    return "\n".join(lines)
