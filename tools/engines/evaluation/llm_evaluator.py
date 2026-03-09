from __future__ import annotations

import json

from tools.domain.models import JobProfile, ResumeOutput, Scorecard
from tools.infra.llm.client import LLMClient

from .rule_evaluator import RuleEvaluationEngine


class LLMEvaluationEngine:
    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model
        self._rule_engine = RuleEvaluationEngine()

    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard:
        base = self._rule_engine.evaluate(resume, profile)

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Return JSON object with key `notes` (list of strings) for resume quality feedback."
                        f"\nResume:\n{resume.content}"
                    ),
                }
            ],
        }
        response = self._client.post_json(self._client.chat_completions_url, payload)
        content = self._client.extract_content(response)

        notes_count = 0
        try:
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                notes = loaded.get("notes")
                if isinstance(notes, list):
                    notes_count = len(notes)
        except json.JSONDecodeError:
            notes_count = 0

        dimensions = dict(base.dimension_scores)
        dimensions["llm_notes_count"] = float(notes_count)
        return Scorecard(
            resume_version=base.resume_version,
            job_profile_id=base.job_profile_id,
            total_score=base.total_score,
            dimension_scores=dimensions,
        )
