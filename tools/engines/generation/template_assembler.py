from __future__ import annotations

from collections.abc import Sequence

from tools.domain.invariants import check_no_fabrication
from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.errors.exceptions import FabricationGuardError


class TemplateAssembler:
    def assemble(
        self,
        report: MatchingReport,
        cards: Sequence[EvidenceCard],
        version: str,
    ) -> ResumeOutput:
        if not cards:
            raise FabricationGuardError(version)

        lines = [f"# Resume {version}", "", "## Highlights"]
        for card in cards:
            lines.append(f"- {card.title}")
            for result in card.results:
                lines.append(f"  - {result}")

        content = "\n".join(lines).strip() + "\n"
        check_no_fabrication(content, cards)

        return ResumeOutput(
            version=version,
            job_profile_id=report.job_profile_id,
            content=content,
            format="markdown",
        )
