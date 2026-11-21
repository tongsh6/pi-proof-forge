"""Project positive evidence from assessments without modifying audit citations."""


def candidate_citations(citations):
    """Candidate evidence only; source-derived limits stay visible in audit citations."""
    if isinstance(citations, list):
        yield from (c for c in citations if isinstance(c, dict) and c.get("candidate_support") is not False)


def positive_citations(assessment: dict):
    """Yield (citation, support status), bounded by both parent and child status."""
    parent = assessment.get("status")
    if parent not in ("supported", "partial"):
        return
    rows = assessment.get("checks") if "checks" in assessment else [assessment]
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        if status not in ("supported", "partial"):
            continue
        citations = row.get("citations")
        if not isinstance(citations, list):
            continue
        for citation in candidate_citations(citations):
            yield citation, "partial" if "partial" in (parent, status) else "supported"
