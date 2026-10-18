"""LLM 受控改写（D2）：不得提高角色强度或时间精度，违规回退模板句。"""
from __future__ import annotations

import re

from tools.domain.models import ResumeOutput
from tools.infra.llm.client import LLMClient

_STRONG_ROLE_RE = re.compile(r"独立负责|全权负责|设计并落地|负责|主导|牵头")
_MONTH_RE = re.compile(r"(?:19|20)\d{2}\s*[-./年]\s*(?:0?[1-9]|1[0-2])(?!\d)")


class LLMRewriter:
    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    def rewrite(
        self,
        resume: ResumeOutput,
        jd_context: str,
        company_context: str,
        *,
        level_context: dict[str, str] | None = None,
    ) -> ResumeOutput:
        constraints = ""
        if level_context:
            constraints = (
                "Do not strengthen role wording beyond the resume: never introduce 独立负责/全权负责/"
                "设计并落地/负责/主导 when the original uses 参与/推动/协同. "
                "Do not increase time precision (do not add month/day if the original only states a year). "
            )
        prompt = (
            "Rewrite wording only. Do not add new facts. "
            f"{constraints}"
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
        if level_context and self._violates_limits(resume.content, rewritten, level_context):
            rewritten = resume.content

        return ResumeOutput(
            version=resume.version,
            job_profile_id=resume.job_profile_id,
            content=rewritten,
            format=resume.format,
        )

    @staticmethod
    def _violates_limits(original: str, rewritten: str, level_context: dict[str, str]) -> bool:
        max_role_level = str(level_context.get("max_role_level", "L1"))
        if max_role_level in {"L3", "L5"}:
            if len(_STRONG_ROLE_RE.findall(rewritten)) > len(_STRONG_ROLE_RE.findall(original)):
                return True
        precision = str(level_context.get("time_precision", "day"))
        if precision == "year" and len(_MONTH_RE.findall(rewritten)) > len(_MONTH_RE.findall(original)):
            return True
        return False
