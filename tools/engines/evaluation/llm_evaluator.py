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

        kw_list = ", ".join(profile.keywords) if profile.keywords else "none"
        mh_list = ", ".join(profile.must_have) if profile.must_have else "none"
        prompt = (
            "You are a resume quality evaluator. Analyze the resume below against the job requirements.\n\n"
            f"Job Title: {profile.title}\n"
            f"Required Keywords: {kw_list}\n"
            f"Must-Have Skills: {mh_list}\n\n"
            "Return ONLY valid JSON (no markdown) with these keys:\n"
            '- "semantic_coverage" (0.0-1.0): how well does the resume SEMANTICALLY cover the keywords, '
            "even if the exact word is not used? (e.g. 'stability governance' covers 'SLA')\n"
            '- "keyword_gaps" (list[str]): specific keywords with weak or missing evidence\n'
            '- "strengths" (list[str]): what the resume does well\n'
            '- "improvements" (list[str]): actionable suggestions\n'
            '- "fabrication_risk" (0.0-1.0): likelihood of unsupported claims (lower is better)\n'
            f"\nResume:\n{resume.content}"
        )
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._client.post_json(self._client.chat_completions_url, payload)
        content = self._client.extract_content(response)

        semantic_coverage = base.dimension_scores.get("coverage", 0.0)
        keyword_gaps: list[str] = []
        strengths: list[str] = []
        improvements: list[str] = []
        fabrication_risk = 0.0

        try:
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                sc = loaded.get("semantic_coverage")
                if isinstance(sc, (int, float)):
                    semantic_coverage = float(sc)
                kg = loaded.get("keyword_gaps")
                if isinstance(kg, list):
                    keyword_gaps = [str(v) for v in kg]
                st = loaded.get("strengths")
                if isinstance(st, list):
                    strengths = [str(v) for v in st]
                imp = loaded.get("improvements")
                if isinstance(imp, list):
                    improvements = [str(v) for v in imp]
                fr = loaded.get("fabrication_risk")
                if isinstance(fr, (int, float)):
                    fabrication_risk = float(fr)
        except json.JSONDecodeError:
            pass

        dimensions = dict(base.dimension_scores)
        dimensions["coverage"] = round(
            base.dimension_scores.get("coverage", 0.0) * 0.3 + semantic_coverage * 0.7, 4
        )
        dimensions["llm_semantic_coverage"] = round(semantic_coverage, 4)
        dimensions["llm_fabrication_risk"] = round(fabrication_risk, 4)
        dimensions["llm_gaps_count"] = float(len(keyword_gaps))
        dimensions["llm_strengths_count"] = float(len(strengths))
        dimensions["llm_improvements_count"] = float(len(improvements))

        total = round(
            dimensions["coverage"] * 0.35
            + dimensions["quant"] * 0.2
            + dimensions["clarity"] * 0.2
            + dimensions["length"] * 0.15
            + dimensions["citation"] * 0.1,
            4,
        )

        return Scorecard(
            resume_version=base.resume_version,
            job_profile_id=base.job_profile_id,
            total_score=total,
            dimension_scores=dimensions,
        )
