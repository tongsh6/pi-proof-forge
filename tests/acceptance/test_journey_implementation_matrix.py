from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tools.check_execution_roadmap import RoadmapError, check_execution_roadmap


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "acceptance" / "journey_implementation_matrix.yaml"
ROADMAP_PATH = ROOT / "docs" / "execution-roadmap.md"


def test_journey_implementation_matrix_selects_one_next_step() -> None:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    steps = matrix["steps"]
    next_steps = [step for step in steps if step["status"] == "next"]

    assert matrix["current_focus"] == "authorized_external_l3_live_run"
    assert [step["id"] for step in next_steps] == ["authorized_external_l3_live_run"]
    assert next_steps[0]["acceptance"]["depth"] == "deep_required"


def test_journey_implementation_matrix_is_anchored_to_vision_and_design() -> None:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))

    assert matrix["vision_alignment"]["source"] == "PLAN.md"
    assert matrix["vision_alignment"]["closed_loop"] == [
        "raw_materials",
        "evidence_cards",
        "explainable_matching",
        "fact_preserving_resume_generation",
        "scorecard_gap_feedback",
        "submission_feedback_iteration",
    ]
    assert matrix["system_design_alignment"]["constitution"] == "constitution.md"
    assert (
        matrix["system_design_alignment"]["core_spec"]
        == "openspec/specs/pi-proof-forge-core.md"
    )
    assert (
        matrix["system_design_alignment"]["gui_pages"]
        == [
            "overview",
            "resumes",
            "evidence",
            "jobs",
            "quick_run",
            "agent_run",
            "submissions",
            "policy",
            "system_settings",
        ]
    )
    for step in matrix["steps"]:
        assert step["vision_link"], step["id"]
        assert step["design_refs"], step["id"]


def test_journey_implementation_matrix_locks_completed_steps_to_evidence() -> None:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))

    for step in matrix["steps"]:
        if step["status"] in {"verified_native", "deep_verified"}:
            assert step["acceptance"]["script"]
            assert step["acceptance"]["evidence"], step["id"]
        if step["status"] == "deep_verified":
            assert step["acceptance"]["depth"] == "deep"


def test_execution_roadmap_mentions_current_focus_and_script() -> None:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")
    next_step = next(step for step in matrix["steps"] if step["status"] == "next")

    assert matrix["current_focus"] in roadmap
    assert next_step["acceptance"]["script"] in roadmap
    assert "一次只推进一个 journey step" in roadmap
    assert "Evidence Cards" in roadmap
    assert "No Fabrication" in roadmap
    assert "Spec-First" in roadmap
    assert "TDD" in roadmap
    assert "Quick Run 是 4 阶段" in roadmap
    assert "Agent Run 是 10 状态机" in roadmap


def test_execution_roadmap_checker_passes_current_repo() -> None:
    check_execution_roadmap(ROOT)


def test_execution_roadmap_checker_rejects_missing_next(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    matrix_dir = root / "acceptance"
    docs_dir = root / "docs"
    matrix_dir.mkdir(parents=True)
    docs_dir.mkdir()
    (docs_dir / "execution-roadmap.md").write_text(
        ROADMAP_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (docs_dir / "acceptance-depth.md").write_text(
        (ROOT / "docs" / "acceptance-depth.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "constitution.md").write_text(
        (ROOT / "constitution.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    for step in matrix["steps"]:
        if step["status"] == "next":
            step["status"] = "not_started"
    (matrix_dir / "journey_implementation_matrix.yaml").write_text(
        yaml.safe_dump(matrix, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(RoadmapError, match="exactly one"):
        check_execution_roadmap(root)


def test_execution_roadmap_checker_requires_external_page_acceptance_guardrail(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    matrix_dir = root / "acceptance"
    docs_dir = root / "docs"
    matrix_dir.mkdir(parents=True)
    docs_dir.mkdir()
    (matrix_dir / "journey_implementation_matrix.yaml").write_text(
        MATRIX_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (docs_dir / "execution-roadmap.md").write_text(
        ROADMAP_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (docs_dir / "acceptance-depth.md").write_text(
        (ROOT / "docs" / "acceptance-depth.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    constitution = (ROOT / "constitution.md").read_text(encoding="utf-8").replace(
        "外部自动化驱动真实页面",
        "真实页面自动化",
    )
    (root / "constitution.md").write_text(constitution, encoding="utf-8")

    with pytest.raises(RoadmapError, match="外部自动化驱动真实页面"):
        check_execution_roadmap(root)
