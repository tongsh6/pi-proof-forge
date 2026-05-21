from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ALLOWED_STATUSES = {
    "not_started",
    "implemented_shallow",
    "verified_contract",
    "verified_native",
    "deep_verified",
    "blocked",
    "next",
}
VERIFIED_STATUSES = {"verified_native", "deep_verified"}
DEPENDENCY_READY_STATUSES = {"verified_native", "deep_verified"}
REQUIRED_VISION_LOOP = (
    "raw_materials",
    "evidence_cards",
    "explainable_matching",
    "fact_preserving_resume_generation",
    "scorecard_gap_feedback",
    "submission_feedback_iteration",
)
REQUIRED_GUI_PAGES = (
    "overview",
    "resumes",
    "evidence",
    "jobs",
    "quick_run",
    "agent_run",
    "submissions",
    "policy",
    "system_settings",
)


class RoadmapError(ValueError):
    pass


def check_execution_roadmap(root: Path) -> None:
    matrix_path = root / "acceptance" / "journey_implementation_matrix.yaml"
    roadmap_path = root / "docs" / "execution-roadmap.md"
    depth_path = root / "docs" / "acceptance-depth.md"

    matrix = _load_mapping(matrix_path)
    if not roadmap_path.exists():
        raise RoadmapError("docs/execution-roadmap.md is missing")
    if not depth_path.exists():
        raise RoadmapError("docs/acceptance-depth.md is missing")

    if matrix.get("roadmap") != "docs/execution-roadmap.md":
        raise RoadmapError("matrix.roadmap must point to docs/execution-roadmap.md")
    if matrix.get("depth_standard") != "docs/acceptance-depth.md":
        raise RoadmapError("matrix.depth_standard must point to docs/acceptance-depth.md")
    _check_alignment_anchors(matrix)

    steps = _require_list(matrix, "steps")
    if not steps:
        raise RoadmapError("matrix.steps must not be empty")

    parsed_steps = [_require_step(step) for step in steps]
    ids = [step["id"] for step in parsed_steps]
    if len(ids) != len(set(ids)):
        raise RoadmapError("step ids must be unique")

    by_id = {step["id"]: step for step in parsed_steps}
    next_steps = [step for step in parsed_steps if step["status"] == "next"]
    if len(next_steps) != 1:
        raise RoadmapError("matrix must contain exactly one status: next step")

    current_focus = _require_str(matrix, "current_focus")
    if next_steps[0]["id"] != current_focus:
        raise RoadmapError("matrix.current_focus must match the only next step")

    orders = [step["order"] for step in parsed_steps]
    if orders != sorted(orders):
        raise RoadmapError("steps must be sorted by journey order")

    for step in parsed_steps:
        _check_step_contract(step, by_id)

    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    if current_focus not in roadmap_text:
        raise RoadmapError("execution-roadmap.md must mention current_focus")
    if next_steps[0]["acceptance"]["script"] not in roadmap_text:
        raise RoadmapError("execution-roadmap.md must mention next acceptance script")
    for required_phrase in (
        "Evidence Cards",
        "No Fabrication",
        "Spec-First",
        "TDD",
        "Quick Run 是 4 阶段",
        "Agent Run 是 10 状态机",
    ):
        if required_phrase not in roadmap_text:
            raise RoadmapError(
                f"execution-roadmap.md must mention design anchor: {required_phrase}"
            )


def _check_alignment_anchors(matrix: dict[str, Any]) -> None:
    vision = _require_mapping(matrix, "vision_alignment")
    if _require_str(vision, "source") != "PLAN.md":
        raise RoadmapError("vision_alignment.source must be PLAN.md")
    closed_loop = tuple(_require_list(vision, "closed_loop"))
    if closed_loop != REQUIRED_VISION_LOOP:
        raise RoadmapError("vision_alignment.closed_loop must match project vision order")

    design = _require_mapping(matrix, "system_design_alignment")
    required_refs = {
        "constitution": "constitution.md",
        "core_spec": "openspec/specs/pi-proof-forge-core.md",
        "agent_design": "openspec/changes/autonomous-agent-delivery-loop/design.md",
        "gui_design": "ui/design/DESIGN.md",
    }
    for key, expected in required_refs.items():
        if _require_str(design, key) != expected:
            raise RoadmapError(f"system_design_alignment.{key} must be {expected}")
    gui_pages = tuple(_require_list(design, "gui_pages"))
    if gui_pages != REQUIRED_GUI_PAGES:
        raise RoadmapError("system_design_alignment.gui_pages must match DESIGN.md order")


def _check_step_contract(step: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    status = step["status"]
    acceptance = _require_mapping(step, "acceptance")
    script = _require_str(acceptance, "script")
    depth = _require_str(acceptance, "depth")
    evidence = _require_list(acceptance, "evidence")
    covers = _require_list(acceptance, "covers")

    if not script:
        raise RoadmapError(f"{step['id']} acceptance script must not be empty")
    if not covers:
        raise RoadmapError(f"{step['id']} acceptance.covers must not be empty")

    if status in VERIFIED_STATUSES and not evidence:
        raise RoadmapError(f"{step['id']} verified step must include evidence")
    if status == "deep_verified" and depth != "deep":
        raise RoadmapError(f"{step['id']} deep_verified step must use depth: deep")
    if status == "verified_native" and depth not in {"native", "deep"}:
        raise RoadmapError(f"{step['id']} verified_native step must use native/deep depth")
    if status == "next" and depth != "deep_required":
        raise RoadmapError(f"{step['id']} next step must require deep acceptance")
    if status == "blocked" and not step.get("blocker"):
        raise RoadmapError(f"{step['id']} blocked step must include blocker")

    for dependency_id in step.get("depends_on", []) or []:
        if dependency_id not in by_id:
            raise RoadmapError(f"{step['id']} depends on unknown step {dependency_id}")
        dependency = by_id[dependency_id]
        if status == "next" and dependency["status"] not in DEPENDENCY_READY_STATUSES:
            raise RoadmapError(
                f"{step['id']} cannot be next before {dependency_id} is verified"
            )
        if dependency["order"] >= step["order"]:
            raise RoadmapError(f"{step['id']} dependency {dependency_id} must come earlier")


def _require_step(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RoadmapError("each step must be a mapping")
    step_id = _require_str(raw, "id")
    order = raw.get("order")
    if not isinstance(order, int) or order < 1:
        raise RoadmapError(f"{step_id}.order must be a positive integer")
    status = _require_str(raw, "status")
    if status not in ALLOWED_STATUSES:
        raise RoadmapError(f"{step_id}.status is invalid")
    _ = _require_str(raw, "journey_stage")
    _ = _require_str(raw, "owner_surface")
    _ = _require_str(raw, "user_goal")
    _ = _require_str(raw, "vision_link")
    design_refs = _require_list(raw, "design_refs")
    if not design_refs:
        raise RoadmapError(f"{step_id}.design_refs must not be empty")
    return raw


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RoadmapError(f"{path} is missing")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RoadmapError(f"{path} must contain a YAML mapping")
    return loaded


def _require_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise RoadmapError(f"{key} must be a mapping")
    return value


def _require_list(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise RoadmapError(f"{key} must be a list")
    return value


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RoadmapError(f"{key} must be a non-empty string")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    check_execution_roadmap(Path(args.root).resolve())
    print("PASS execution roadmap")


if __name__ == "__main__":
    main()
