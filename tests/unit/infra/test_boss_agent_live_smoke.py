import json
from pathlib import Path
from unittest.mock import patch

from tools import check_boss_agent_cli
from tools.infra.discovery.boss_agent_cli import BossAgentCliError


def test_live_smoke_runs_read_only_schema_status_search_and_detail(tmp_path: Path) -> None:
    output = tmp_path / "boss-agent-smoke.json"

    with patch.object(check_boss_agent_cli.boss_agent_cli, "read_schema") as schema:
        with patch.object(check_boss_agent_cli.boss_agent_cli, "read_status") as status:
            with patch.object(check_boss_agent_cli.boss_agent_cli, "search_jobs") as search:
                with patch.object(check_boss_agent_cli.boss_agent_cli, "read_detail") as detail:
                    schema.return_value = {"commands": ["schema", "status", "search", "detail"]}
                    status.return_value = {"ready": True}
                    search.return_value = [
                        {
                            "job_url": "https://www.zhipin.com/job_detail/1.html",
                            "company": "Example",
                            "position": "Backend",
                            "platform": "boss",
                        }
                    ]
                    detail.return_value = {"job_url": "https://www.zhipin.com/job_detail/1.html"}

                    exit_code = check_boss_agent_cli.main(
                        [
                            "--cli",
                            "boss-agent",
                            "--keyword",
                            "Java",
                            "--city",
                            "北京",
                            "--platforms",
                            "boss",
                            "--limit",
                            "2",
                            "--output",
                            str(output),
                        ]
                    )

    assert exit_code == 0
    search.assert_called_once_with(
        ["Java"],
        city="北京",
        platforms=("boss",),
        limit=2,
        timeout_seconds=30,
    )
    detail.assert_called_once_with(
        "https://www.zhipin.com/job_detail/1.html",
        platform="boss",
        timeout_seconds=30,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert [step["name"] for step in report["steps"]] == [
        "schema",
        "status",
        "search",
        "detail",
    ]


def test_live_smoke_fails_when_search_returns_empty_by_default(tmp_path: Path) -> None:
    output = tmp_path / "boss-agent-smoke.json"

    with patch.object(
        check_boss_agent_cli.boss_agent_cli,
        "read_schema",
        return_value={"ok": True},
    ):
        with patch.object(
            check_boss_agent_cli.boss_agent_cli,
            "read_status",
            return_value={"ready": True},
        ):
            with patch.object(
                check_boss_agent_cli.boss_agent_cli,
                "search_jobs",
                return_value=[],
            ):
                exit_code = check_boss_agent_cli.main(
                    [
                        "--cli",
                        "boss-agent",
                        "--platforms",
                        "boss",
                        "--output",
                        str(output),
                    ]
                )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "fail"
    assert report["steps"][-1]["name"] == "search"
    assert report["steps"][-1]["message"] == "search returned no jobs"


def test_live_smoke_can_allow_empty_search_and_skip_detail(tmp_path: Path) -> None:
    output = tmp_path / "boss-agent-smoke.json"

    with patch.object(
        check_boss_agent_cli.boss_agent_cli,
        "read_schema",
        return_value={"ok": True},
    ):
        with patch.object(
            check_boss_agent_cli.boss_agent_cli,
            "read_status",
            return_value={"ready": True},
        ):
            with patch.object(
                check_boss_agent_cli.boss_agent_cli,
                "search_jobs",
                return_value=[],
            ):
                exit_code = check_boss_agent_cli.main(
                    [
                        "--cli",
                        "boss-agent",
                        "--platforms",
                        "boss",
                        "--allow-empty-search",
                        "--output",
                        str(output),
                    ]
                )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["status"] == "pass"
    assert report["steps"][-1]["name"] == "detail"
    assert report["steps"][-1]["status"] == "skip"


def test_live_smoke_reports_adapter_error(tmp_path: Path) -> None:
    output = tmp_path / "boss-agent-smoke.json"

    with patch.object(
        check_boss_agent_cli.boss_agent_cli,
        "read_schema",
        side_effect=BossAgentCliError("boss-agent-cli command was not found"),
    ):
        exit_code = check_boss_agent_cli.main(
            [
                "--cli",
                "missing-boss-agent",
                "--platforms",
                "boss",
                "--output",
                str(output),
            ]
        )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "fail"
    assert report["steps"] == [
        {
            "name": "schema",
            "status": "fail",
            "message": "boss-agent-cli command was not found",
            "evidence": {},
        }
    ]
