from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_journey_report,
    write_journey_report,
)
from tools.sidecar.handlers.agent import handle_quick_start


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def _write_policy(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                'llm_provider: "lm_studio"',
                'llm_model: "local-model"',
                'llm_base_url: "http://127.0.0.1:1234/v1"',
                'llm_timeout: "60"',
                'llm_temperature: "0.2"',
                'llm_api_key_configured: "true"',
                'llm_api_key_placeholder: "lm-studio"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_active_job_profile(project_root: Path) -> None:
    profile_dir = project_root / "job_profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "jp_quick_acceptance.yaml").write_text(
        "\n".join(
            [
                'target_role: "Backend Tech Lead"',
                'company: "Acme"',
                'source_jd: "Own inventory reliability for peak traffic."',
                'status: "active"',
                "keywords:",
                '  - "Java"',
                '  - "Kafka"',
                '  - "Redis"',
                "must_have:",
                '  - "Distributed systems"',
                "seniority_signal:",
                '  - "Owner"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_material_and_evidence(project_root: Path) -> None:
    materials_dir = project_root / "materials"
    evidence_dir = project_root / "evidence_cards"
    materials_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    material_path = materials_dir / "mat_quick_acceptance.md"
    material_path.write_text(
        "Java Kafka inventory sync reduced P95 latency from 6s to 1.8s.\n",
        encoding="utf-8",
    )
    (materials_dir / "mat_quick_acceptance.meta.yaml").write_text(
        "\n".join(
            [
                'material_id: "mat_quick_acceptance"',
                'resource_id: "res_quick_acceptance"',
                'label: "Quick acceptance material"',
                'kind: "raw_work_material"',
                'filename: "mat_quick_acceptance.md"',
                'extension: ".md"',
                'uploaded_at: "2026-05-21T00:00:00Z"',
                'preview: "Java Kafka inventory sync reduced P95 latency."',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (evidence_dir / "ec_quick_acceptance.yaml").write_text(
        "\n".join(
            [
                'id: "ec_quick_acceptance"',
                'title: "Inventory reliability platform"',
                'time_range: "2025-06 ~ 2025-09"',
                'context: "Peak traffic inventory consistency"',
                'role_scope: "Backend Tech Lead / Owner"',
                'status: "saved_eligible"',
                'candidate_pool_eligible: "true"',
                "actions:",
                '  - "Built Java Kafka inventory sync"',
                "results:",
                '  - "P95 latency dropped from 6s to 1.8s"',
                '  - "Inventory incidents dropped 42%"',
                "stack:",
                '  - "Java"',
                '  - "Kafka"',
                '  - "Redis"',
                "artifacts:",
                '  - "latency-review.md"',
                "tags:",
                '  - "inventory"',
                f'raw_source: "{material_path}"',
                "source_material_ids:",
                '  - "mat_quick_acceptance"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _completed_process() -> object:
    return type(
        "Completed",
        (),
        {"returncode": 0, "stdout": "[pipeline] done\n", "stderr": ""},
    )()


def test_quick_run_legacy_body_markers_do_not_prove_traceability(
    tmp_path: Path,
) -> None:
    project_root = tmp_path
    quick_dir = project_root / "outputs" / "quick_runs"
    policy_path = project_root / "policy.yaml"
    _write_policy(policy_path)
    _write_active_job_profile(project_root)
    _write_material_and_evidence(project_root)

    def create_pipeline_outputs(*_args: object, **_kwargs: object) -> object:
        run_id = "qr_quick_acceptance"
        matching_dir = project_root / "matching_reports"
        resume_dir = project_root / "outputs" / run_id
        scorecard_dir = project_root / "outputs" / "scorecards"
        summary_dir = project_root / "outputs" / "agent_runs" / run_id
        matching_dir.mkdir(parents=True, exist_ok=True)
        resume_dir.mkdir(parents=True, exist_ok=True)
        scorecard_dir.mkdir(parents=True, exist_ok=True)
        summary_dir.mkdir(parents=True, exist_ok=True)
        (matching_dir / f"mr-{run_id}.yaml").write_text(
            "\n".join(
                [
                    'job_profile_id: "jp_quick_acceptance"',
                    "evidence_card_ids:",
                    '  - "ec_quick_acceptance"',
                    "score_total: 92",
                    "score_breakdown:",
                    '  K: { score: 24, reason: "stack match" }',
                    '  D: { score: 14, reason: "domain match" }',
                    '  S: { score: 14, reason: "owner match" }',
                    '  Q: { score: 18, reason: "quantified impact" }',
                    '  E: { score: 12, reason: "artifact present" }',
                    '  R: { score: 10, reason: "recent" }',
                    "gaps:",
                    '  - "缺少成本优化证据"',
                    "gap_tasks:",
                    '  - "补充容量或成本治理指标"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (resume_dir / f"resume_mr-{run_id}_A.md").write_text(
            "\n".join(
                [
                    "# Resume Version A",
                    "- Java Kafka inventory sync reduced P95 latency from 6s to 1.8s.",
                    "- Evidence trace: id=ec_quick_acceptance",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (scorecard_dir / f"scorecard_mr-{run_id}_A.md").write_text(
            "# Scorecard\n\n- 总分: 88/100\n- 补证据任务: 补充容量指标\n",
            encoding="utf-8",
        )
        (summary_dir / "summary.json").write_text(
            json.dumps(
                {
                    "status": "DONE",
                    "artifacts": {
                        "evidence": f"outputs/quick_runs/{run_id}/evidence_cards",
                        "matching": f"matching_reports/mr-{run_id}.yaml",
                        "resume_dir": f"outputs/{run_id}",
                        "scorecard": f"outputs/scorecards/scorecard_mr-{run_id}_A.md",
                    },
                }
            ),
            encoding="utf-8",
        )
        return _completed_process()

    with (
        patch("tools.sidecar.handlers.agent._PROJECT_ROOT", project_root),
        patch("tools.sidecar.handlers.agent._QUICK_RUN_DIR", quick_dir),
        patch(
            "tools.sidecar.handlers.agent._build_quick_run_id",
            return_value="qr_quick_acceptance",
        ),
        patch(
            "tools.sidecar.handlers.settings._resolve_policy_path",
            return_value=policy_path,
        ),
        patch(
            "tools.sidecar.handlers.agent.subprocess.run",
            side_effect=create_pipeline_outputs,
        ) as run_mock,
    ):
        result = handle_quick_start(
            {
                "meta": {"correlation_id": "corr_quick_acceptance"},
                "job_profile_id": "jp_quick_acceptance",
                "options": {
                    "evidence_ids": ["ec_quick_acceptance"],
                    "resume_positioning": "technical_depth",
                    "use_llm": True,
                    "require_llm": True,
                },
            }
        )
        run_payload = json.loads(
            (quick_dir / "qr_quick_acceptance.json").read_text(encoding="utf-8")
        )

    command = run_mock.call_args.args[0]
    assert "--skip-evidence-extraction" in command
    assert "--use-llm" in command
    assert "--require-llm" in command
    assert result["status"] == "DONE"
    assert result["job_profile"]["active_target_eligible"] is True
    assert result["selected_evidence_card_ids"] == ["ec_quick_acceptance"]
    assert result["resume_positioning"]["mode"] == "technical_depth"
    assert result["artifacts"]["matching"].endswith("mr-qr_quick_acceptance.yaml")
    assert result["resume_pdf"].endswith(".PDF")
    assert (project_root / result["resume_pdf"]).read_bytes().startswith(b"%PDF-")
    assert result["gap_tasks"] == ["补充容量或成本治理指标"]
    assert result["traceability"]["matching_uses_selected_evidence"] is True
    assert result["traceability"]["resume_traceable"] is False
    assert result["traceability"]["fact_preserving_traceability"] is False
    assert result["resume_readiness"]["quality_passed"] is False
    assert run_payload["run"]["job_profile"]["status"] == "active"
    assert run_payload["run"]["selected_evidence_card_ids"] == ["ec_quick_acceptance"]

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="quick_run_generate_and_evaluate_resume_l1",
        generated_at="2026-05-21T00:00:00Z",
        results={
            "quick_run_outputs_are_traceable": JourneyStepResult(
                status="blocked",
                evidence=str(tmp_path),
                message=(
                    "旧版正文中的 evidence id 不能替代独立追溯；需重新生成和审核。"
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["blocked"] == 1
    assert "quick_run_outputs_are_traceable" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_quick_run_real_pipeline_generates_pdf_and_independent_trace(tmp_path, monkeypatch):
    from tools.sidecar.handlers import agent

    shutil.copytree(ROOT / "tools", tmp_path / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    _write_active_job_profile(tmp_path)
    _write_material_and_evidence(tmp_path)
    _write_policy(tmp_path / "policy.yaml")
    (tmp_path / "personal_profile.yaml").write_text(
        'name: "候选人甲"\nphone: "13800000000"\nemail: "candidate@example.com"\n'
        'city: "上海"\ncurrent_position: "后端工程师"\n', encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PPF_POLICY_PATH", str(tmp_path / "policy.yaml"))
    monkeypatch.setattr(agent, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent, "_QUICK_RUN_DIR", tmp_path / "outputs/quick_runs")
    result = agent.handle_quick_start({
        "meta": {"correlation_id": "real-local-pipeline"},
        "job_profile_id": "jp_quick_acceptance",
        "options": {"evidence_ids": ["ec_quick_acceptance"], "use_llm": False},
    })
    assert result["status"] == "DONE", result
    resume = tmp_path / result["traceability"]["resume_a"]
    text = resume.read_text()
    assert "候选人甲" in text
    assert "Acme" in text
    assert "candidate@example.com" in text
    assert "Evidence trace" not in text
    assert "ec_quick_acceptance" not in text
    assert result["traceability"]["resume_traceable"] is True
    assert "resume_readiness" in result
    # 此样例只有五个基本字段，缺完整职业档案，不能因 PDF/追溯生成成功而提升就绪状态。
    assert result["resume_readiness"]["status"] == "NEEDS_EVIDENCE"
    assert result["resume_readiness"]["missing_career_fields"]
    assert result["resume_readiness"]["content_ready"] is False
    assert result["resume_readiness"]["deliverable"] is False
    assert isinstance(result["resume_readiness"]["evaluation_score"], int)
    assert (tmp_path / result["resume_pdf"]).read_bytes().startswith(b"%PDF-")
    resume.write_text(text + "- 未经证据支持的新声明\n", encoding="utf-8")
    changed = agent._quick_run_result_details(
        result["run_id"], "", "", selected_evidence_card_ids=["ec_quick_acceptance"],
    )
    assert changed["traceability"]["resume_traceable"] is False
    assert changed["resume_readiness"]["quality_passed"] is False
