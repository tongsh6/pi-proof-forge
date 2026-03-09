from __future__ import annotations

from tools.domain.models import ResumeOutput
from tools.infra.llm.client import LLMClient


class LLMRewriter:
    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    def rewrite(
        self,
        resume: ResumeOutput,
        jd_context: str,
        company_context: str,
    ) -> ResumeOutput:
        prompt = (
            "Rewrite wording only. Do not add new facts. "
            f"JD Context: {jd_context}\n"
            f"Company Context: {company_context}\n"
            f"Resume:\n{resume.content}"
        )
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._client.post_json(self._client.chat_completions_url, payload)
        rewritten = self._client.extract_content(response)
        if not rewritten.strip():
            rewritten = resume.content

        return ResumeOutput(
            version=resume.version,
            job_profile_id=resume.job_profile_id,
            content=rewritten,
            format=resume.format,
        )
