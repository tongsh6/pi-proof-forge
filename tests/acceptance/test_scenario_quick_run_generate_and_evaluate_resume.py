from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from tools.sidecar.handlers import agent
from tools.sidecar.handlers.agent import handle_quick_get, handle_quick_start


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"
_PDF_SUPPORT_CACHE: bool | None = None
_QUICK_RUN_TERMINAL_STATUSES = {"DONE", "SKIPPED", "FAILED", "TIMEOUT", "stopped"}


class _FakeQuickRunProcess:
    """subprocess.Popen 替身：让 Quick Run 后台线程在测试内走完生命周期。"""

    def __init__(self, *, returncode: int = 0, stdout_text: str = "") -> None:
        self.returncode = returncode
        self.stdout_text = stdout_text
        self.terminated = 0
        self.killed = 0

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated += 1
        self.returncode = -15

    def kill(self) -> None:
        self.killed += 1
        self.returncode = -9


def _get_quick_run(run_id: str) -> dict:
    return handle_quick_get(
        {"meta": {"correlation_id": "corr_quick_acceptance_get"}, "run_id": run_id}
    )


def _wait_quick_run(run_id: str, *, timeout: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout
    result: dict = {}
    while time.monotonic() < deadline:
        result = _get_quick_run(run_id)
        if result["status"] in _QUICK_RUN_TERMINAL_STATUSES:
            agent._join_quick_run_thread(10.0)
            return result
        time.sleep(0.05)
    agent._join_quick_run_thread(1.0)
    raise AssertionError(f"quick run {run_id} did not finish: {result}")


def _pdf_export_supported() -> bool:
    """探测当前环境能否真正渲染 PDF；沙箱/CI 缺失渲染器时跳过 PDF 相关断言。"""
    global _PDF_SUPPORT_CACHE
    if _PDF_SUPPORT_CACHE is None:
        from tools.infra.export.pdf_exporter import markdown_to_pdf

        try:
            with TemporaryDirectory() as tmp:
                source = Path(tmp) / "probe.md"
                target = Path(tmp) / "probe.pdf"
                source.write_text("# probe\n\n- one\n", encoding="utf-8")
                markdown_to_pdf(source, target)
                _PDF_SUPPORT_CACHE = target.read_bytes().startswith(b"%PDF-")
        except Exception:  # noqa: BLE001 - 任何渲染器异常都按不可用处理
            _PDF_SUPPORT_CACHE = False
    return _PDF_SUPPORT_CACHE


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


def test_quick_run_legacy_body_markers_do_not_prove_traceability(
    tmp_path: Path,
) -> None:
    # journey_contract/journey_report 依赖 PyYAML；最小测试环境未安装时只跳过本报告断言，不阻塞收集。
    pytest.importorskip("yaml", reason="PyYAML is required for journey_contract assertions")
    from tools.acceptance.journey_contract import load_journey_contract
    from tools.acceptance.journey_report import (
        JourneyStepResult,
        build_journey_report,
        write_journey_report,
    )

    project_root = tmp_path
    quick_dir = project_root / "outputs" / "quick_runs"
    policy_path = project_root / "policy.yaml"
    _write_policy(policy_path)
    _write_active_job_profile(project_root)
    _write_material_and_evidence(project_root)

    def create_pipeline_outputs(*_args: object, **_kwargs: object) -> None:
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

    process = _FakeQuickRunProcess()

    def spawn(command, **kwargs):
        if kwargs.get("stdout") is not None:
            kwargs["stdout"].write(b"[pipeline] done\n")
            kwargs["stdout"].flush()
        create_pipeline_outputs(command)
        return process

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
            "tools.sidecar.handlers.agent.Popen",
            side_effect=spawn,
        ) as run_mock,
    ):
        started = handle_quick_start(
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
        assert started["status"] == "RUNNING"
        assert started["progress"]["current_stage"] == "extract"
        result = _wait_quick_run(started["run_id"])
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
    assert all(stage["status"] == "done" for stage in result["progress"]["stages"])
    if _pdf_export_supported():
        assert result["resume_pdf"].endswith(".PDF")
        assert (project_root / result["resume_pdf"]).read_bytes().startswith(b"%PDF-")
    else:
        # 沙箱/CI 没有可用 PDF 渲染器时，run 仍应完成并显式报告导出失败原因。
        assert result["resume_pdf"] == ""
        assert "PDF_RENDER" in result["pdf_export_error"]
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
    started = agent.handle_quick_start({
        "meta": {"correlation_id": "real-local-pipeline"},
        "job_profile_id": "jp_quick_acceptance",
        "options": {"evidence_ids": ["ec_quick_acceptance"], "use_llm": False},
    })
    assert started["status"] == "RUNNING"
    # 真实管线在后台线程执行；轮询 run.quick.get 直到终态。
    result = _wait_quick_run(started["run_id"], timeout=300.0)
    assert result["status"] == "DONE", result
    assert [stage["status"] for stage in result["progress"]["stages"]] == [
        "done",
        "done",
        "done",
        "done",
    ], result["progress"]
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
    if _pdf_export_supported():
        assert (tmp_path / result["resume_pdf"]).read_bytes().startswith(b"%PDF-")
    else:
        assert result["resume_pdf"] == ""
        assert "PDF_RENDER" in result["pdf_export_error"]
    resume.write_text(text + "- 未经证据支持的新声明\n", encoding="utf-8")
    changed = agent._quick_run_result_details(
        result["run_id"], "", "", selected_evidence_card_ids=["ec_quick_acceptance"],
    )
    assert changed["traceability"]["resume_traceable"] is False
    assert changed["resume_readiness"]["quality_passed"] is False


def _write_two_page_career(project: Path) -> list[str]:
    from tools.infra.career_profile import inspect_career
    from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml

    projects = [
        ("fulfilment", "Fulfillment replay ledger", "Tracked delayed inventory updates across store checkout and warehouse workers.",
         ["Introduced an append-only reconciliation ledger for fulfillment events",
          "Isolated retry runs from live stock updates", "Mapped damaged event batches to the original warehouse request"],
         ["Removed redundant fulfillment replays during the morning import", "Reduced damaged batch review time from 55 minutes to 12 minutes"]),
        ("changes", "Deployment rollback controls", "Released inventory API changes through consistent staging and handover windows.",
         ["Defined release hold points for store inventory services",
          "Automated backwards-compatible database checks in the release pipeline", "Recorded reversible configuration for each checkout service"],
         ["Reduced rollback preparation from 30 minutes to 8 minutes", "Passed three release rehearsals with consistent stock reconciliation"]),
        ("routing", "Warehouse allocation safeguards", "Protected inventory reservations during warehouse routing and switchovers.",
         ["Wrote a routing guard for stale warehouse reservations", "Built per-region queue monitoring for the inventory service",
          "Added explicit rollback notes for warehouse operators"],
         ["Limited stale reservation handling to a single delivery route", "Warehouse staff confirmed the route recovery checklist"]),
    ]
    cards = project / "evidence_cards"
    original = "ec_quick_acceptance"
    seed = parse_simple_yaml((cards / f"{original}.yaml").read_text(encoding="utf-8"))
    selected = [original]
    for year, (key, title, context, actions, results) in enumerate(projects, 2022):
        card_id, material_id = f"ec_{key}", f"material_{key}"
        selected.append(card_id)
        source = project / "materials" / f"{material_id}.md"
        source.write_text("\n".join([title, context, *actions, *results]), encoding="utf-8")
        fields = {**seed["scalars"], "id": card_id, "title": title, "context": context,
                  "raw_source": str(source), "time_range": f"{year}-01 ~ {year}-12", "role_scope": "Backend Engineer"}
        lists = {**seed["lists"], "actions": actions, "results": results, "source_material_ids": [material_id]}
        (cards / f"{card_id}.yaml").write_text(dump_yaml(fields, lists), encoding="utf-8")
    work = [
        {"id": "w-new", "company": "Synthetic Retail Labs", "department": "Commerce systems",
         "title": "Backend Tech Lead", "start": "2024-01", "end": "2025-12", "current": False,
         "scope": "Owned store inventory integration and release reliability",
         "contributions": ["Designed Java inventory APIs for peak traffic",
                           "Reduced inventory lookup retries through versioned stock events",
                           "Reviewed release plans with distribution and store engineering"],
         "evidence_ids": [original, "ec_routing"]},
        {"id": "w-old", "company": "Synthetic Warehouse Systems", "department": "Fulfillment Platform",
         "title": "Backend Engineer", "start": "2021-01", "end": "2023-12", "current": False,
         "scope": "Built fulfillment tracking and rollback automation",
         "contributions": ["Implemented recovery tooling for fulfillment event failures",
                           "Verified schema updates against staging inventory snapshots",
                           "Documented handover procedures with warehouse operations"],
         "evidence_ids": ["ec_fulfilment", "ec_changes"]},
    ]
    career = {
        "schema_version": 1, "summary": "Backend engineer focused on stable inventory and fulfillment services.",
        "work": work, "education_visibility": "show",
        "education": [{"id": "education", "school": "Synthetic Institute of Computing", "major": "Software Engineering",
                       "degree": "Bachelor", "start": "2016-09", "end": "2020-06", "current": False}],
        "skills": [{"id": skill_id, "category": category, "description": description, "evidence_ids": [card_id]}
                   for skill_id, category, description, card_id in [
                       ("a", "Backend engineering", "Java and Kafka inventory integration", original),
                       ("b", "Deployment", "Release pipeline checks and rollback coordination", "ec_changes"),
                       ("c", "Reliability", "Monitoring and operational recovery for stock reservations", "ec_routing")]],
        "extras": [],
    }
    profile = {"name": "Test candidate", "phone": "13800000000", "email": "candidate@example.com",
               "city": "Shanghai", "current_position": "Backend Engineer", "career_json": json.dumps(career)}
    profile["career_review_json"] = json.dumps({"revision": inspect_career(profile, cards)["revision"]})
    assert inspect_career(profile, cards)["career_status"]["reviewed"]
    (project / "personal_profile.yaml").write_text(dump_yaml(profile, {}), encoding="utf-8")
    return selected


def test_quick_run_two_page_pdf_has_lead_and_usable_tail(tmp_path, monkeypatch):
    import subprocess
    import sys

    from tools.infra.export.pdf_exporter import _find_chromium

    swift = shutil.which("swift")
    if sys.platform != "darwin" or not swift or _find_chromium() is None:
        pytest.skip("Physical page fixture requires macOS PDFKit and a Chromium renderer")
    # Physical expectations are independent of the logical first-screen Markdown marker.
    lead = ["Designed Java inventory APIs for peak traffic", "Reduced inventory lookup retries through versioned stock events"]
    tail = ["Warehouse allocation safeguards", "Wrote a routing guard for stale warehouse reservations",
            "Warehouse staff confirmed the route recovery checklist", "Synthetic Institute of Computing"]

    shutil.copytree(ROOT / "tools", tmp_path / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    _write_active_job_profile(tmp_path)
    _write_material_and_evidence(tmp_path)
    _write_policy(tmp_path / "policy.yaml")
    selected = _write_two_page_career(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PPF_POLICY_PATH", str(tmp_path / "policy.yaml"))
    monkeypatch.setattr(agent, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent, "_QUICK_RUN_DIR", tmp_path / "outputs/quick_runs")
    started = handle_quick_start({
        "meta": {"correlation_id": "two-page-rules-pipeline"}, "job_profile_id": "jp_quick_acceptance",
        "options": {"evidence_ids": selected, "use_llm": False},
    })
    assert started["status"] == "RUNNING"
    result = _wait_quick_run(started["run_id"], timeout=60.0)
    assert result["status"] == "DONE" and result["resume_pdf"], result
    assert result["traceability"]["resume_traceable"]
    assert result["resume_readiness"]["deliverable"] is False
    resume = tmp_path / result["traceability"]["resume_a"]
    lines = resume.read_text(encoding="utf-8").splitlines()
    claims = json.loads(resume.with_suffix(".trace.json").read_text(encoding="utf-8"))["claims"]
    # Verify independently located final body occurrences for visible project and work facts.
    traced = {
        lead[0]: "personal_profile:career.work.w-new.contributions:0",
        lead[1]: "personal_profile:career.work.w-new.contributions:1",
        tail[1]: "ec_routing:actions:0",
        tail[2]: "ec_routing:results:1",
    }
    for literal, fact_id in traced.items():
        entry, = [claim for claim in claims if claim.get("text") == literal]
        position = entry["render_line"]
        assert type(position) is int and 1 <= position <= len(lines)
        assert lines[position - 1].endswith(literal)
        assert entry["fact_id"] == fact_id
    script = tmp_path / "inspect_pdf.swift"
    script.write_text(r"""
import Foundation
import PDFKit
let args = CommandLine.arguments
guard let pdf = PDFDocument(url: URL(fileURLWithPath: args[1])),
      pdf.pageCount == 2, let first = pdf.page(at: 0), let second = pdf.page(at: 1)
else { fatalError("Expected a readable, naturally two-page PDF") }
let excerpts = try JSONDecoder().decode([[String]].self, from: Data(args[2].utf8))
for (number, page) in [first, second].enumerated() {
    let box = page.bounds(for: .mediaBox)
    precondition(abs(box.width - 595.3) < 3 && abs(box.height - 841.9) < 3, "Expected an A4 page")
    let text = page.string ?? ""
    for literal in excerpts[number] {
        let hits = pdf.findString(literal, withOptions: [])
        precondition(hits.count == 1 && hits[0].pages == [page] && text.contains(literal), "Missing/misplaced/duplicate: \(literal)")
        let bounds = hits[0].bounds(for: page)
        precondition(!bounds.isEmpty && box.contains(bounds), "Bounds outside the page: \(literal)")
        if number == 0 { precondition(bounds.minY >= box.midY, "Whole lead must be in the physical top half: \(literal)") }
    }
    for marker in ["ec_quick_acceptance", "ec_changes", "ec_fulfilment", "ec_routing", "Evidence trace", "first-screen-end"] {
        precondition(!text.contains(marker), "Internal markers must not print")
    }
}
""", encoding="utf-8")
    monkeypatch.setenv("SWIFT_MODULECACHE_PATH", str(tmp_path / "swift-cache"))
    inspected = subprocess.run(
        [swift, str(script), str(tmp_path / result["resume_pdf"]), json.dumps([lead, tail])],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if "no such module 'PDFKit'" in inspected.stderr:
        pytest.skip("This macOS Swift SDK does not provide PDFKit")
    assert inspected.returncode == 0, inspected.stdout + inspected.stderr
    # Selected text geometry is not a measurement of whole-document clipping or viewport layout.
