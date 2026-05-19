import json
import unittest
from unittest.mock import patch

from tools.infra.discovery import boss_agent_cli


class BossAgentCliTests(unittest.TestCase):
    def test_search_jobs_runs_read_only_search_commands(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps(
                    {"data": {"items": [{"url": "https://www.zhipin.com/job_detail/1.html"}]}}
                ),
                "stderr": "",
            },
        )()

        with patch.dict("os.environ", {"PPF_BOSS_AGENT_CLI": "boss-agent"}):
            with patch("subprocess.run", return_value=completed) as run:
                items = boss_agent_cli.search_jobs(
                    ["Java", "Redis"],
                    city="上海",
                    platforms=("boss",),
                    limit=3,
                    timeout_seconds=7,
                )

        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(
            command,
            [
                "boss-agent",
                "search",
                "--platform",
                "boss",
                "--keyword",
                "Java Redis",
                "--city",
                "上海",
                "--limit",
                "3",
                "--json",
            ],
        )
        self.assertEqual(items[0]["url"], "https://www.zhipin.com/job_detail/1.html")
        self.assertEqual(items[0]["platform"], "boss")

    def test_search_jobs_accepts_list_payloads(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps([{"job_url": "https://sou.zhaopin.com/job/1"}]),
                "stderr": "",
            },
        )()

        with patch("subprocess.run", return_value=completed):
            items = boss_agent_cli.search_jobs(
                ["Python"],
                city="北京",
                platforms=("zhilian",),
            )

        self.assertEqual(items[0]["job_url"], "https://sou.zhaopin.com/job/1")
        self.assertEqual(items[0]["platform"], "zhilian")


if __name__ == "__main__":
    unittest.main()
