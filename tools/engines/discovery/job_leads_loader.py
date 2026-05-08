"""Load job leads from job_leads/*.yaml into Candidate objects."""

from __future__ import annotations

from pathlib import Path

from tools.domain.value_objects import Candidate
from tools.infra.persistence.yaml_io import parse_simple_yaml

JOB_LEADS_DIR = Path("job_leads")


def load_candidates_from_job_leads(base_dir: Path | None = None) -> list[Candidate]:
    """Scan job_leads/ directory and convert to Candidate objects.

    Each .yaml file can contain one or more job items with:
      company_name, position, job_url, direction, confidence
    """
    leads_dir = base_dir or JOB_LEADS_DIR
    if not leads_dir.exists():
        return []

    candidates: list[Candidate] = []
    for path in sorted(leads_dir.glob("*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        items = doc.get("lists", {}).get("items", [])
        if not items:
            # Try single-item format
            scalars = doc.get("scalars", {})
            if scalars.get("job_url"):
                candidates.append(_to_candidate(scalars, path.stem, 0))
            continue

        for idx, item in enumerate(items):
            if isinstance(item, dict) and item.get("job_url"):
                candidates.append(_to_candidate(item, path.stem, idx))

    return candidates


def _to_candidate(data: dict, source_id: str, index: int) -> Candidate:
    return Candidate(
        candidate_id=f"{source_id}-{index}",
        direction=data.get("direction", data.get("role_keyword", "backend")),
        company=data.get("company_name", data.get("company", "")),
        job_url=data.get("job_url", ""),
        confidence=float(data.get("confidence", 0.7)),
        source=f"job_leads:{source_id}",
        merged_sources=(f"job_leads:{source_id}",),
    )
