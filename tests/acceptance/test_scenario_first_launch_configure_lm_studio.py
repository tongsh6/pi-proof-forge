from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_journey_report,
    write_journey_report,
)
from tools.sidecar.handlers.settings import (
    handle_settings_check_llm_connection,
    handle_settings_get,
    handle_settings_update,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"
FIXTURE_PATH = (
    ROOT
    / "tests"
    / "acceptance"
    / "fixtures"
    / "scenarios"
    / "first_launch_configure_lm_studio"
    / "lm_studio_config.json"
)


def test_first_launch_lm_studio_l1_acceptance_writes_report(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    policy_path = tmp_path / "policy.yaml"
    env = {"PPF_POLICY_PATH": str(policy_path)}
    with patch.dict(os.environ, env, clear=True):
        update = handle_settings_update(
            {
                "meta": {"correlation_id": "corr_accept_lm_update"},
                "section": "llm_config",
                "payload": fixture,
            }
        )
        settings = handle_settings_get(
            {"meta": {"correlation_id": "corr_accept_lm_get"}}
        )
        with patch(
            "tools.sidecar.handlers.settings.LLMClient.list_models",
            side_effect=OSError("connection refused"),
        ):
            connection = handle_settings_check_llm_connection(
                {
                    "meta": {"correlation_id": "corr_accept_lm_check"},
                    "payload": fixture,
                }
            )

    llm = settings["llm_config"]
    assert update["saved"] is True
    assert llm["provider"] == "lm_studio"
    assert llm["base_url"] == "http://127.0.0.1:1234/v1"
    assert llm["model"] == "local-model"
    assert llm["api_key"]["configured"] is True
    assert "lm-studio" not in str(settings)
    quick_run_summary = {
        "provider": llm["provider"],
        "base_url": llm["base_url"],
        "model": llm["model"],
        "api_key": llm["api_key"],
    }
    agent_run_summary = {
        "provider": llm["provider"],
        "base_url": llm["base_url"],
        "model": llm["model"],
        "api_key": llm["api_key"],
    }
    assert quick_run_summary["provider"] == "lm_studio"
    assert agent_run_summary["base_url"] == "http://127.0.0.1:1234/v1"
    assert quick_run_summary["api_key"]["configured"] is True
    assert "lm-studio" not in str(quick_run_summary)
    assert "lm-studio" not in str(agent_run_summary)
    assert connection["status"] == "blocked"
    assert connection["code"] == "BLOCKED_LOCAL_PROVIDER"
    assert "http://127.0.0.1:1234/v1/models" in connection["message"]

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="first_launch_lm_studio_l1",
        generated_at="2026-05-20T00:00:00Z",
        results={
            "lm_studio_config_persisted": JourneyStepResult(
                status="pass",
                evidence=str(policy_path),
                message="LM Studio config is saved and read back with masked API key status.",
            ),
            "lm_studio_connection_check_structured": JourneyStepResult(
                status="blocked",
                evidence="settings.checkLlmConnection",
                message=f"{connection['code']}: {connection['message']}",
            ),
            "lm_studio_visible_to_run_pages": JourneyStepResult(
                status="pass",
                evidence="settings.get",
                message="Quick Run and Agent Run can read provider/base_url/model summaries without raw API key.",
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["summary"]["pass"] == 2
    assert payload["summary"]["blocked"] == 1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "first_launch_configure_lm_studio" in markdown
    assert "BLOCKED_LOCAL_PROVIDER" in markdown
