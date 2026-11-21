"""Agent 生成适配：从当前来源加载事实，复用唯一计划与渲染实现。"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.infra.material_paths import materials_dir_for


class TemplateAssembler:
    def __init__(self, *, evidence_dir: Path, personal_profile_path: Path,
                 job_profile_path: Path | None = None, material_dir: Path | None = None,
                 positioning: str = "technical_depth") -> None:
        self._evidence_dir = Path(evidence_dir)
        self._profile_path = Path(personal_profile_path)
        self._job_path = Path(job_profile_path) if job_profile_path is not None else None
        self._material_dir = Path(material_dir) if material_dir is not None else materials_dir_for(
            self._profile_path, fallback=self._evidence_dir.parent / "materials")
        self._positioning = positioning

    def generate(self, report: MatchingReport, cards: Sequence[EvidenceCard], version: str) -> ResumeOutput:
        from . import resume_renderer

        allowed = {card.id for card in cards}
        selected = list(report.evidence_card_ids)
        if (not selected or len(set(selected)) != len(selected)
                or not set(selected).issubset(allowed)):
            raise ValueError("selected_evidence_missing_or_invalid")
        if self._job_path is not None and self._job_path.stem != report.job_profile_id:
            raise ValueError("generation_target_changed")
        views = resume_renderer.load_cards(
            self._evidence_dir, selected, self._material_dir, require_saved_eligible=True)
        captured = {}
        profile, target = resume_renderer.load_generation_context(
            self._profile_path, self._job_path, captured_inputs=captured)
        claims = []
        content = resume_renderer.build_template_resume(
            "A", views, personal_profile=profile, job_context=target,
            positioning=self._positioning, claims=claims)
        used = {claim["evidence_id"] for claim in claims if claim.get("source_kind") == "evidence"}
        selected_views = [card for card in views if card["id"] in used]
        paths = {"personal_profile": self._profile_path}
        if self._job_path is not None:
            paths["job_profile"] = self._job_path
        if target.get("jd_source_path"):
            paths["job_description"] = Path(target["jd_source_path"])
        for card in selected_views:
            paths[card["id"]] = self._evidence_dir / (card["id"] + ".yaml")
            paths.update(card["material_inputs"])
        trace = resume_renderer.build_generation_trace(
            version=version, content=content, strategy="locked_evidence_fields", semantic=None,
            profile=profile, target=target, selected_cards=selected_views, claims=claims,
            paths=paths, captured_inputs=captured,
            missing_profile=[key for key in ("name", "phone", "email", "city", "current_position")
                             if not str(profile.get(key) or "").strip()],
            missing_target=[key for key in ("target_role", "company", "jd_text") if not target.get(key)],
        )
        from tools.infra.persistence.review_snapshot import validate_generation_trace
        if not validate_generation_trace(content, trace):
            raise ValueError("generation_input_changed")
        return ResumeOutput(version=version, job_profile_id=report.job_profile_id,
                            content=content, format="markdown", generation_trace=trace)
