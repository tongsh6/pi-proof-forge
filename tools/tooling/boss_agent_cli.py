#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.infra.discovery import boss_agent_cli


@dataclass(frozen=True)
class SmokeStep:
    name: str
    status: str
    message: str
    evidence: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class SmokeReport:
    status: str
    generated_at: str
    cli: str
    keyword: str
    city: str
    platforms: tuple[str, ...]
    steps: tuple[SmokeStep, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "cli": self.cli,
            "keyword": self.keyword,
            "city": self.city,
            "platforms": list(self.platforms),
            "steps": [step.to_json() for step in self.steps],
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only live smoke check for the optional BOSS/Zhilian discovery CLI."
    )
    _ = parser.add_argument(
        "--cli",
        default=os.getenv("PPF_BOSS_AGENT_CLI", "boss"),
        help="External CLI command, also written to PPF_BOSS_AGENT_CLI for this run.",
    )
    _ = parser.add_argument("--keyword", default="Java Redis")
    _ = parser.add_argument("--city", default="上海")
    _ = parser.add_argument("--platforms", default="boss,zhilian")
    _ = parser.add_argument("--limit", type=int, default=3)
    _ = parser.add_argument("--detail-url", default="")
    _ = parser.add_argument("--timeout-seconds", type=int, default=30)
    _ = parser.add_argument(
        "--allow-empty-search",
        action="store_true",
        help="Allow schema/status to pass even if search returns no jobs.",
    )
    _ = parser.add_argument(
        "--output",
        default="outputs/discovery/boss-agent-live-smoke.json",
        help="JSON report path.",
    )
    return parser.parse_args(argv)


def run_smoke(
    *,
    cli: str,
    keyword: str,
    city: str,
    platforms: tuple[str, ...],
    limit: int,
    detail_url: str,
    timeout_seconds: int,
    allow_empty_search: bool,
) -> SmokeReport:
    previous_cli = os.environ.get("PPF_BOSS_AGENT_CLI")
    os.environ["PPF_BOSS_AGENT_CLI"] = cli
    try:
        steps = _run_steps(
            cli=cli,
            keyword=keyword,
            city=city,
            platforms=platforms,
            limit=limit,
            detail_url=detail_url,
            timeout_seconds=timeout_seconds,
            allow_empty_search=allow_empty_search,
        )
    finally:
        if previous_cli is None:
            os.environ.pop("PPF_BOSS_AGENT_CLI", None)
        else:
            os.environ["PPF_BOSS_AGENT_CLI"] = previous_cli

    status = "pass" if all(step.status in {"pass", "skip"} for step in steps) else "fail"
    return SmokeReport(
        status=status,
        generated_at=_utcnow(),
        cli=cli,
        keyword=keyword,
        city=city,
        platforms=platforms,
        steps=tuple(steps),
    )


def write_report(path: Path, report: SmokeReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    platforms = _parse_platforms(str(args.platforms))
    report = run_smoke(
        cli=str(args.cli),
        keyword=str(args.keyword),
        city=str(args.city),
        platforms=platforms,
        limit=int(args.limit),
        detail_url=str(args.detail_url).strip(),
        timeout_seconds=int(args.timeout_seconds),
        allow_empty_search=bool(args.allow_empty_search),
    )
    output = Path(str(args.output))
    write_report(output, report)

    print(f"[boss-agent-smoke] status: {report.status}")
    print(f"[boss-agent-smoke] report: {output}")
    for step in report.steps:
        print(f"[boss-agent-smoke] {step.name}: {step.status} - {step.message}")
    return 0 if report.status == "pass" else 1


def _run_steps(
    *,
    cli: str,
    keyword: str,
    city: str,
    platforms: tuple[str, ...],
    limit: int,
    detail_url: str,
    timeout_seconds: int,
    allow_empty_search: bool,
) -> list[SmokeStep]:
    steps: list[SmokeStep] = []
    schema = _capture(
        "schema",
        lambda: boss_agent_cli.read_schema(timeout_seconds=timeout_seconds),
        summarize=_summarize_payload,
    )
    steps.append(schema)
    if schema.status == "fail":
        return steps

    status = _capture(
        "status",
        lambda: boss_agent_cli.read_status(timeout_seconds=timeout_seconds),
        summarize=_summarize_payload,
    )
    steps.append(status)
    if status.status == "fail":
        return steps

    search_items: list[dict[str, Any]] = []

    def search() -> dict[str, Any]:
        nonlocal search_items
        search_items = boss_agent_cli.search_jobs(
            [keyword],
            city=city,
            platforms=platforms,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        if not search_items and not allow_empty_search:
            raise boss_agent_cli.BossAgentCliError("search returned no jobs")
        return {"count": len(search_items), "sample": search_items[:2]}

    search_step = _capture("search", search, summarize=lambda payload: payload)
    steps.append(search_step)
    if search_step.status == "fail":
        return steps

    detail_target_url = detail_url or _first_job_url(search_items)
    detail_platform = _first_platform(search_items, default=platforms[0] if platforms else "boss")
    if not detail_target_url:
        steps.append(
            SmokeStep(
                name="detail",
                status="skip",
                message="No job URL available for detail smoke.",
                evidence={},
            )
        )
        return steps

    detail = _capture(
        "detail",
        lambda: boss_agent_cli.read_detail(
            detail_target_url,
            platform=detail_platform,
            timeout_seconds=timeout_seconds,
        ),
        summarize=_summarize_payload,
    )
    steps.append(detail)
    return steps


def _capture(
    name: str,
    action: Any,
    *,
    summarize: Any,
) -> SmokeStep:
    try:
        payload = action()
    except boss_agent_cli.BossAgentCliError as exc:
        return SmokeStep(name=name, status="fail", message=str(exc), evidence={})
    except Exception as exc:
        return SmokeStep(
            name=name,
            status="fail",
            message=f"unexpected {exc.__class__.__name__}: {exc}",
            evidence={},
        )
    return SmokeStep(
        name=name,
        status="pass",
        message="read-only command returned JSON.",
        evidence=summarize(payload),
    )


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(str(key) for key in payload.keys())
    return {
        "keys": keys[:20],
        "key_count": len(keys),
    }


def _first_job_url(items: list[dict[str, Any]]) -> str:
    for item in items:
        value = item.get("job_url") or item.get("url")
        if value:
            return str(value)
    return ""


def _first_platform(items: list[dict[str, Any]], *, default: str) -> str:
    for item in items:
        value = item.get("platform")
        if value:
            return str(value)
    return default


def _parse_platforms(raw: str) -> tuple[str, ...]:
    platforms = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not platforms:
        raise SystemExit("--platforms must contain at least one platform")
    return platforms


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


if __name__ == "__main__":
    raise SystemExit(main())
