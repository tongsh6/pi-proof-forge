from __future__ import annotations

from tools.domain.models import EvidenceCard


class RuleEvidenceExtractor:
    def extract(self, raw_material: str) -> EvidenceCard:
        lines = [line.strip() for line in raw_material.splitlines() if line.strip()]
        title = lines[0] if lines else "Untitled Evidence"
        results: list[str] = []
        artifacts: list[str] = []
        tags: list[str] = []

        for line in lines:
            lowered = line.lower()
            if lowered.startswith("result:") or lowered.startswith("结果:"):
                value = line.split(":", 1)[1].strip() if ":" in line else ""
                if value:
                    results.append(value)
            elif lowered.startswith("artifact:"):
                value = line.split(":", 1)[1].strip() if ":" in line else ""
                if value:
                    artifacts.append(value)
            elif lowered.startswith("tag:"):
                value = line.split(":", 1)[1].strip() if ":" in line else ""
                if value:
                    tags.append(value)

        if not results:
            results.append("pending-result")
        if not artifacts:
            artifacts.append("pending-artifact")

        return EvidenceCard(
            id=f"ec-rule-{abs(hash(raw_material))}",
            title=title,
            raw_source=raw_material,
            results=tuple(results),
            artifacts=tuple(artifacts),
            tags=tuple(tags),
        )
