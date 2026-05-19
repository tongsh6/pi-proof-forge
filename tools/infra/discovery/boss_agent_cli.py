from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any


class BossAgentCliError(RuntimeError):
    pass


def read_status(timeout_seconds: int = 20) -> dict[str, Any]:
    return _run_json(["status", "--json"], timeout_seconds)


def read_schema(timeout_seconds: int = 20) -> dict[str, Any]:
    return _run_json(["schema", "--json"], timeout_seconds)


def search_jobs(
    keywords: list[str],
    *,
    city: str,
    platforms: tuple[str, ...] = ("boss", "zhilian"),
    limit: int = 5,
    timeout_seconds: int = 30,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    keyword = " ".join(k.strip() for k in keywords if k.strip())
    if not keyword:
        return items

    for platform in platforms:
        payload = _run_json(
            [
                "search",
                "--platform",
                platform,
                "--keyword",
                keyword,
                "--city",
                city,
                "--limit",
                str(limit),
                "--json",
            ],
            timeout_seconds,
        )
        for item in _extract_items(payload):
            normalized = dict(item)
            normalized.setdefault("platform", platform)
            items.append(normalized)
    return items


def read_detail(
    job_url: str,
    *,
    platform: str = "boss",
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    return _run_json(
        ["detail", "--platform", platform, "--url", job_url, "--json"],
        timeout_seconds,
    )


def _run_json(args: list[str], timeout_seconds: int) -> dict[str, Any]:
    command = shlex.split(os.getenv("PPF_BOSS_AGENT_CLI", "boss"))
    if not command:
        raise BossAgentCliError("PPF_BOSS_AGENT_CLI is empty")

    try:
        completed = subprocess.run(
            [*command, *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise BossAgentCliError("boss-agent-cli command was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise BossAgentCliError("boss-agent-cli command timed out") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise BossAgentCliError(
            f"boss-agent-cli exited with {completed.returncode}: {stderr}"
        )

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise BossAgentCliError("boss-agent-cli returned non-JSON output") from exc
    if not isinstance(payload, dict):
        return {"items": payload}
    return payload


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw: Any = payload
    for key in ("data", "result"):
        if isinstance(raw, dict) and key in raw:
            raw = raw[key]

    if isinstance(raw, dict):
        for key in ("items", "jobs", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [raw] if raw else []

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []
