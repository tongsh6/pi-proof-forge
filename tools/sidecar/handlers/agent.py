"""Agent run / REVIEW RPC handlers (stub until run_agent is wired)."""

from __future__ import annotations

from typing import Any


def handle_get_pending_review(params: dict[str, Any]) -> dict[str, Any]:
    """Return pending REVIEW candidates; stub: no active run → empty list."""
    correlation_id = params["meta"]["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "candidates": [],
    }


def handle_submit_review(params: dict[str, Any]) -> dict[str, Any]:
    """Accept review decisions; stub: no active run → accept count 0."""
    correlation_id = params["meta"]["correlation_id"]
    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": 0,
    }
