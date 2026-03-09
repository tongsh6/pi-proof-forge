from __future__ import annotations

from pathlib import Path

from tools.domain.models import EvidenceCard
from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml


class EvidenceStore:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    def save(self, card: EvidenceCard) -> Path:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        path = self._base_dir / f"{card.id}.yaml"
        text = dump_yaml(
            {
                "id": card.id,
                "title": card.title,
                "raw_source": card.raw_source,
            },
            {
                "results": list(card.results),
                "artifacts": list(card.artifacts),
                "tags": list(card.tags),
            },
        )
        path.write_text(text, encoding="utf-8")
        return path

    def get(self, card_id: str) -> EvidenceCard | None:
        path = self._base_dir / f"{card_id}.yaml"
        if not path.exists():
            return None
        parsed = parse_simple_yaml(path.read_text(encoding="utf-8"))
        scalars = parsed.get("scalars", {})
        lists = parsed.get("lists", {})
        return EvidenceCard(
            id=scalars.get("id", ""),
            title=scalars.get("title", ""),
            raw_source=scalars.get("raw_source", ""),
            results=tuple(lists.get("results", [])),
            artifacts=tuple(lists.get("artifacts", [])),
            tags=tuple(lists.get("tags", [])),
        )
