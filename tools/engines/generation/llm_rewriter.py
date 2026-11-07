"""LLM 受控改写（D2）：模板是事实基线，改写只允许措辞层变化。

两道独立防线，都不依赖提示词：
- 等级防线：不得提高角色强度或时间精度（D2），违规回退模板句。
- 事实防线（生成引擎）：数字与英文实体集合必须原样保留、长度变化有界；
  空响应/违规一律回退模板基线（回退即安全）。

``LLMRewriter.generate`` 实现生成引擎接口，供 Agent 编排在 LLM 模式注入；
``rewrite`` 保留给显式调用方（带 level_context 时启用等级防线）。
"""
from __future__ import annotations

import re

from tools.domain.models import EvidenceCard, JobProfile, MatchingReport, ResumeOutput
from tools.infra.llm.client import LLMClient

_STRONG_ROLE_RE = re.compile(r"独立负责|全权负责|设计并落地|负责|主导|牵头")
_MONTH_RE = re.compile(r"(?:19|20)\d{2}\s*[-./年]\s*(?:0?[1-9]|1[0-2])(?!\d)")
_NUMBER_RE = re.compile(r"\d[\d,.]*\+?")
_ENGLISH_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{1,}")
_LENGTH_MIN_RATIO = 0.6
_LENGTH_MAX_RATIO = 1.6


class LLMRewriter:
    """受控改写引擎。

    ``personal_profile`` / ``job_context`` 仅用于生成基线模板与改写上下文；
    ``generate`` 的返回值保证事实集合与基线一致（否则回退基线）。
    """

    def __init__(
        self,
        client: LLMClient,
        model: str,
        personal_profile: dict | None = None,
        job_context: dict | None = None,
        positioning: str = "technical_depth",
    ) -> None:
        self._client = client
        self._model = model
        self._personal_profile = personal_profile or {}
        self._job_context = job_context or {}
        self._positioning = positioning

    # -- 生成引擎接口 -----------------------------------------------------

    def generate(
        self,
        report: MatchingReport,
        cards: list[EvidenceCard] | tuple[EvidenceCard, ...],
        version: str,
    ) -> ResumeOutput:
        """先模板拼装事实基线，再做受控改写；任何事实违规回退基线。"""
        baseline = self._baseline(report, cards or [], version)
        jd_context = str(
            self._job_context.get("jd_text")
            or self._job_context.get("target_role")
            or ""
        )
        company_context = str(self._job_context.get("company") or "")
        rewritten = self._request_rewrite_text(
            baseline.content, jd_context, company_context, level_context=None
        )
        if self._violates_facts(baseline.content, rewritten):
            return baseline
        return ResumeOutput(
            version=baseline.version,
            job_profile_id=baseline.job_profile_id,
            content=rewritten.strip() + "\n",
            format=baseline.format,
        )

    def _baseline(
        self,
        report: MatchingReport,
        cards: list[EvidenceCard] | tuple[EvidenceCard, ...],
        version: str,
    ) -> ResumeOutput:
        from .template_assembler import TemplateAssembler

        assembler = TemplateAssembler(
            self._personal_profile, self._job_context, self._positioning
        )
        return assembler.generate(report, cards, version)

    # -- 显式改写接口（保留既有契约） -------------------------------------

    def rewrite(
        self,
        resume: ResumeOutput,
        jd_context: str,
        company_context: str,
        *,
        level_context: dict[str, str] | None = None,
    ) -> ResumeOutput:
        rewritten = self._request_rewrite_text(
            resume.content, jd_context, company_context, level_context
        )
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

    # -- LLM 调用 ---------------------------------------------------------

    def _request_rewrite_text(
        self,
        original: str,
        jd_context: str,
        company_context: str,
        level_context: dict[str, str] | None,
    ) -> str:
        constraints = ""
        if level_context:
            constraints = (
                "Do not strengthen role wording beyond the resume: never introduce 独立负责/全权负责/"
                "设计并落地/负责/主导 when the original uses 参与/推动/协同. "
                "Do not increase time precision (do not add month/day if the original only states a year). "
            )
        prompt = (
            "Rewrite wording only. Do not add new facts. "
            "Keep every number and every English technical term exactly as-is. "
            f"{constraints}"
            f"JD Context: {jd_context}\n"
            f"Company Context: {company_context}\n"
            f"Resume:\n{original}"
        )
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._client.post_json(self._client.chat_completions_url, payload)
        return self._client.extract_content(response)

    # -- 事实保真校验 -----------------------------------------------------

    @classmethod
    def _violates_facts(cls, original: str, rewritten: str) -> bool:
        """改写结果必须保留全部数字与英文实体，且不得新增；长度变化有界。"""
        text = rewritten.strip()
        if not text:
            return True
        original_numbers = set(_NUMBER_RE.findall(original))
        rewritten_numbers = set(_NUMBER_RE.findall(text))
        if original_numbers != rewritten_numbers:
            return True
        original_terms = {term.casefold() for term in _ENGLISH_RE.findall(original)}
        rewritten_terms = {term.casefold() for term in _ENGLISH_RE.findall(text)}
        if original_terms != rewritten_terms:
            return True
        ratio = len(text) / max(len(original), 1)
        return not (_LENGTH_MIN_RATIO <= ratio <= _LENGTH_MAX_RATIO)

    @staticmethod
    def _violates_limits(
        original: str, rewritten: str, level_context: dict[str, str]
    ) -> bool:
        max_role_level = str(level_context.get("max_role_level", "L1"))
        if max_role_level in {"L3", "L5"}:
            if len(_STRONG_ROLE_RE.findall(rewritten)) > len(
                _STRONG_ROLE_RE.findall(original)
            ):
                return True
        precision = str(level_context.get("time_precision", "day"))
        if precision == "year" and len(_MONTH_RE.findall(rewritten)) > len(
            _MONTH_RE.findall(original)
        ):
            return True
        return False
