# User Journey Closed-Loop Validation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use explicit `Status` fields and checkbox syntax for tracking.

**Goal:** Build an automated acceptance system that verifies PiProofForge user scenarios from the user's first application actions through repeatable journey-level outcomes.

**Architecture:** Start from user-perspective scenario cases. Each case defines persona, user goal, entry point, user actions, expected system responses, expected results, fallback behavior, and validation levels. Journey contracts and automated tests are derived from approved cases, not from backend module assumptions.

**Tech Stack:** Python acceptance tests with `pytest`, existing `tools/` domain/orchestration modules, YAML/JSON fixtures, optional Playwright GUI smoke tests, shell runner under `scripts/acceptance/`.

---

## 1. Status Legend

| Status | Meaning | When to Use |
|--------|---------|-------------|
| `not_started` | Work is planned but no implementation has begun | Default state for new tasks |
| `in_progress` | Work has started and is actively being changed | Exactly one owner should be driving it |
| `blocked` | Work cannot continue without resolving a dependency | Must include blocker and unblock condition |
| `done` | Work is implemented and verified with evidence | Must include verification command/report |
| `deferred` | Work is intentionally postponed | Must include reason |

## 2. Overall Plan State

| Item | Status | Evidence | Notes |
|------|--------|----------|-------|
| Plan documented in project | `done` | `AIEF/docs/plans/2026-05-13-user-journey-closed-loop-validation.md` | This file is the source plan for the validation track |
| Project ledger references plan | `done` | `docs/project-ledger.md` | Ledger now lists this validation track in current priorities and evidence index |
| Scenario case catalog | `done` | `acceptance/scenario_cases.yaml` | Case 1 through feedback iteration are ready for implementation |
| Journey contract | `done` | `acceptance/journey_contract.yaml` + `tools/acceptance/journey_contract.py` | Contract loads selected ready cases, exact journey stages, required outputs, and report status fields |
| L1 business closed-loop validation | `in_progress` | `tests/acceptance/test_scenario_first_launch_configure_lm_studio.py` | Case 1 settings persistence, structured connection result, and run-page provider summaries are covered |
| L2 GUI journey smoke validation | `not_started` | None yet | Starts after L1 contract/report shape stabilizes |
| L3 external channel check-mode validation | `not_started` | Existing Liepin check-mode logs can seed fixtures | Keep real submit disabled |

## 2.1 Tracking Checklist

- [x] Status: `done` — Plan documented in project.
- [x] Status: `done` — Project ledger references plan.
- [x] Status: `done` — M-1 scenario case catalog.
- [x] Status: `done` — M0 journey contract derived from approved scenario cases.
- [ ] Status: `in_progress` — M1 headless business closed-loop validation.
- [x] Status: `done` — M2 acceptance report generator.
- [ ] Status: `not_started` — M3 GUI journey smoke validation.
- [ ] Status: `not_started` — M4 external channel check-mode validation.
- [x] Status: `done` — M5 unified acceptance runner.

## 3. Scenario-First Definition

The validation target is the user's scenario, not a backend pipeline. A scenario case must answer:

```text
Who is the user?
What does the user want to accomplish after opening the app?
Where does the user start?
What actions does the user take?
What should the system show or persist?
What result does the user get?
How do we verify that result?
What structured fallback is acceptable?
```

The GUI journey still matters, but it is evaluated through scenario cases:

```text
Overview
  -> Resumes
  -> Evidence
  -> Jobs
  -> Quick Run
  -> Agent Run
  -> Submissions
  -> Policy
  -> System Settings
```

Individual cases may cover different slices of this journey. For example, Case 1 starts in System Settings and ends when LM Studio configuration is saved and visible to later flows; it does not run resume generation or submission.

The first approved case is:

| Case | Status | Priority | User Goal |
|------|--------|----------|-----------|
| `first_launch_configure_lm_studio` | `ready_for_implementation` | P0 | Configure LM Studio as the local LLM provider after first launch |
| `setup_profile_and_material_library` | `ready_for_implementation` | P0 | Set up personal profile, uploaded resume, and text material library |
| `generate_review_and_complete_evidence_card` | `ready_for_implementation` | P0 | Generate a strict-JSON Evidence Card draft from uploaded Markdown with local LLM, review it, and save eligible evidence |
| `setup_job_target` | `ready_for_implementation` | P0 | Create a job target from pasted JD, parse it with local LLM, review it, and link an accessible source URL to a Job Lead |
| `quick_run_generate_and_evaluate_resume` | `ready_for_implementation` | P0 | Run one Quick Run that matches evidence to a job target, generates a fact-preserving resume, exports PDF, evaluates it, and records artifacts |
| `agent_run_guided_batch` | `ready_for_implementation` | P0 | Run a guarded multi-candidate Agent Run batch with visible decisions, generated artifacts for passed candidates, and no real submit |
| `channel_session_setup` | `ready_for_implementation` | P0 | Configure or refresh a channel shared session through manual login, requiring positive login signals before saving it as valid, showing session metadata and safe account identity when available, supporting per-channel clear, and without storing credentials or bypassing verification |
| `submission_check_mode` | `ready_for_implementation` | P0 | Run a channel-abstracted check-mode submission rehearsal; P0 validates the Liepin adapter while keeping the contract generic, requiring visible usable session metadata in preflight, routing wrong-account sessions back to session setup, and allowing rate-limited configurable bounded target recovery with explicit diff-based user confirmation, resume-target mismatch warning, regeneration next-action, and original/final target traceability before safe attachment checks |
| `feedback_iteration_after_check_mode` | `ready_for_implementation` | P0 | Use scorecard/gap/check-mode feedback to choose a user-approved iteration action, preserve source artifacts, update evidence/job/resume artifacts, compare versions, and prepare the next safe check-mode run |

## 4. Acceptance Levels

| Level | Name | Status | Purpose | Pass Condition |
|-------|------|--------|---------|----------------|
| L1 | Scenario Data/API Validation | `not_started` | Verify scenario data can be persisted and read through backend/sidecar contracts | Case-specific backend checks pass or return structured blocked state |
| L2 | User Visible Scenario | `not_started` | Verify the user can complete the scenario through GUI-visible controls | Required page controls, feedback, save state, and cross-page summaries are visible |
| L3 | Local/External Integration | `not_started` | Verify real local or external dependency integration safely | Case-specific real integration succeeds or reports a structured blocked state |

For Case 1, L3 means a real local request to LM Studio's OpenAI-compatible models endpoint. It must never be silently converted into a generic failure if LM Studio is not running.

## 5. Target File Map

| Path | Status | Responsibility |
|------|--------|----------------|
| `acceptance/scenario_cases.yaml` | `done` | User-perspective scenario case catalog; Case 1 through feedback iteration are ready for implementation |
| `acceptance/journey_contract.yaml` | `done` | Machine-readable execution contract derived from selected approved scenario cases |
| `tools/acceptance/__init__.py` | `done` | Package marker for acceptance helpers |
| `tools/acceptance/journey_contract.py` | `done` | Load and validate the journey contract |
| `tools/acceptance/journey_report.py` | `done` | Build JSON/Markdown acceptance reports from test results |
| `tests/acceptance/fixtures/scenarios/` | `in_progress` | Stable fixture data grouped by `case_id` |
| `tests/acceptance/test_scenario_first_launch_configure_lm_studio.py` | `in_progress` | Case 1 L1/L2 acceptance tests for LM Studio configuration |
| `tests/acceptance/test_gui_journey_smoke.py` | `not_started` | L2 smoke test for page-level journey continuity |
| `tests/acceptance/test_liepin_check_mode_journey.py` | `not_started` | L3 check-mode channel acceptance test |
| `scripts/acceptance/run-acceptance.sh` | `done` | One-command runner for L1/L2/L3 validation |
| `outputs/acceptance/<run_id>/acceptance-report.json` | `done` | Machine-readable level summary generated by the runner |
| `outputs/acceptance/<run_id>/acceptance-report.md` | `done` | Human-readable level summary generated by the runner |
| `outputs/acceptance/<run_id>/journey-report.json` | `done` | Machine-readable journey report generated by the runner |
| `outputs/acceptance/<run_id>/journey-report.md` | `done` | Human-readable journey summary generated by the runner |

## 6. Phase Roadmap

| Phase | Status | Goal | Exit Evidence |
|-------|--------|------|---------------|
| M-1 | `done` | Define user-perspective scenario cases before writing automated checks | `acceptance/scenario_cases.yaml` contains approved cases with statuses |
| M0 | `done` | Define the journey contract and report schema from approved cases | `acceptance/journey_contract.yaml` validates against selected `case_id` |
| M1 | `in_progress` | Implement L1 selected-scenario validation | Case 1 L1 settings persistence, structured blocked check, and run-page provider summary checks pass; optional live L3-local remains |
| M2 | `done` | Generate structured acceptance reports | JSON and Markdown reports are produced under `outputs/acceptance/` |
| M3 | `not_started` | Implement L2 GUI journey smoke validation | GUI smoke test passes with mock sidecar data |
| M4 | `not_started` | Implement L3 external check-mode validation | Liepin check-mode acceptance passes without final submit |
| M5 | `done` | Wire all levels into a single acceptance runner | `bash scripts/acceptance/run-acceptance.sh --level L1` exits 0 and writes acceptance + journey reports |

## 7. Detailed Steps

### M-1: Scenario Case Definition

**Phase Status:** `done`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M-1.1 | `done` | Define scenario case structure from user perspective | Case fields include persona, goal, entry point, actions, responses, results, fallback, validation | `acceptance/scenario_cases.yaml` contains these fields |
| M-1.2 | `done` | Define Case 1: first launch and LM Studio configuration | `first_launch_configure_lm_studio` | Case status is `ready_for_implementation` |
| M-1.3 | `done` | Define Case 2: personal profile and material library preparation | `setup_profile_and_material_library` | Case status is `ready_for_implementation` |
| M-1.4 | `done` | Define Case 3: evidence card generation, review, and completion | `generate_review_and_complete_evidence_card` | Case status is `ready_for_implementation` |
| M-1.5 | `done` | Define Case 4: job target setup | `setup_job_target` | Case status is `ready_for_implementation` |
| M-1.6 | `done` | Define Case 5: Quick Run generation and evaluation | `quick_run_generate_and_evaluate_resume` | Case status is `ready_for_implementation` |
| M-1.7 | `done` | Define Case 6+: Agent Run, channel session setup, submission check, and feedback iteration | `agent_run_guided_batch`, `channel_session_setup`, `submission_check_mode`, `feedback_iteration_after_check_mode` | All four cases are `ready_for_implementation` |

### M0: Journey Contract

**Phase Status:** `done`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M0.1 | `done` | Create `acceptance/journey_contract.yaml` from approved scenario cases | Contract with selected `case_id`, stages, artifacts, and acceptance rules | `python3 -m pytest tests/acceptance/test_journey_contract.py -q` |
| M0.2 | `done` | Create `tools/acceptance/journey_contract.py` | Typed loader and validation errors | Unit test rejects missing required stages |
| M0.3 | `done` | Define required journey stages | `overview`, `resumes`, `evidence`, `jobs`, `quick_run`, `agent_run`, `submissions`, `policy`, `system_settings` | Test confirms exact order |
| M0.4 | `done` | Define required scenario outputs | Case-specific saved settings, structured connection result, visible summaries, or generated artifacts | Test confirms each selected case has required outputs |
| M0.5 | `done` | Add contract status fields | Each contract rule supports `status`, `evidence`, `message` in reports | Test confirms rule status/evidence/message fields |

### M1: Selected Scenario Validation

**Phase Status:** `in_progress`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M1.1 | `done` | Create fixture directory `tests/acceptance/fixtures/scenarios/first_launch_configure_lm_studio/` | Stable local provider fixture values | `test_scenario_first_launch_configure_lm_studio.py` loads fixture without network |
| M1.2 | `done` | Implement L1 settings persistence check for Case 1 | LM Studio provider/base_url/api_key/model config can be saved and read | Test confirms `settings.update` / `settings.get` returns saved masked config |
| M1.3 | `done` | Implement structured connection result check for Case 1 | Success or `BLOCKED_LOCAL_PROVIDER` result | Test confirms unavailable LM Studio is structured, not a generic crash |
| M1.4 | `done` | Implement saved config summary checks for Quick Run and Agent Run | Both pages read active provider metadata through `settings.get` and render provider/base_url/model/secret status without exposing raw secret | `python3 -m pytest tests/unit/gui/test_quick_run_page_contract.py tests/unit/gui/test_agent_run_page_contract.py tests/acceptance/test_scenario_first_launch_configure_lm_studio.py tests/acceptance/test_journey_contract.py -q`; `pnpm --dir ui run e2e:agent-run`; `pnpm --dir ui run e2e:quick-run` |
| M1.5 | `not_started` | Implement Case 1 L3-local optional check | Real request to `http://127.0.0.1:1234/v1/models` when enabled | Test reports PASS or BLOCKED_LOCAL_PROVIDER |

### M2: Acceptance Report

**Phase Status:** `done`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M2.1 | `done` | Create `tools/acceptance/journey_report.py` | Report model for levels, phases, steps, and evidence paths | `test_journey_report_serializes_json_deterministically` |
| M2.2 | `done` | Add Markdown report rendering | `journey-report.md` with PASS/FAIL/BLOCKED rows | `test_journey_report_markdown_contains_status_rows` |
| M2.3 | `done` | Include stage-level failure messages | Failures identify stage and missing artifact | `test_artifact_check_failure_names_phase_and_missing_artifact` |
| M2.4 | `done` | Write reports under timestamped output directory | `outputs/acceptance/<timestamp>/` | `test_write_journey_report_outputs_json_and_markdown` |

### M3: GUI Journey Smoke

**Phase Status:** `not_started`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M3.1 | `not_started` | Define mock sidecar payloads for journey pages | Overview stats, evidence list, jobs, run status, submissions detail | Test loads mock data without real sidecar |
| M3.2 | `not_started` | Add GUI smoke test for 9-page navigation | Test visits pages in journey order | Test fails if route or nav label is missing |
| M3.3 | `not_started` | Verify key visible state per page | Each page exposes at least one journey-specific signal | Test names the page that failed |
| M3.4 | `not_started` | Verify Submissions detail can open | Detail panel shows steps/log paths/status | Test fails if details are inaccessible |
| M3.5 | `blocked` | Validate against `.pen` if Pencil MCP is available | Optional design-asset confirmation | Blocked by current Pencil MCP transport issue recorded in project ledger |

### M4: External Channel Check-mode

**Phase Status:** `not_started`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M4.1 | `not_started` | Select or create a validated low-risk job lead fixture | Check-mode target with expected jobId/recruiter when available | Fixture has no requirement for real submit |
| M4.2 | `not_started` | Run Liepin channel in check-mode only | Submission log records login check, target verify, chat send resume, submit skipped | Test fails if submit is not skipped |
| M4.3 | `not_started` | Classify external failures | `login_required`, `job_unavailable`, `rate_limited`, `target_mismatch`, or `channel_unavailable` | Report groups failure under L3, not L1 |
| M4.4 | `not_started` | Add safety assertions | PDF/jobId/recruiter safety gates remain enforced | Test confirms unsafe submit cannot proceed |

### M5: Unified Runner

**Phase Status:** `done`

| Step | Status | Action | Output | Verification |
|------|--------|--------|--------|--------------|
| M5.1 | `done` | Create `scripts/acceptance/run-acceptance.sh` | Runs L1 by default; L2/L3 gated by flags or environment | Shell exits non-zero on failure |
| M5.2 | `done` | Add runner modes | `--level L1`, `--level L2`, `--level L3`, `--all` | Command help documents modes |
| M5.3 | `done` | Write combined acceptance report | Aggregated JSON/Markdown report | Report includes each level status |
| M5.4 | `done` | Document expected command in project ledger | Ledger points to runner and report location | New sessions can discover how to verify the journey |

## 8. Recommended Execution Order

| Order | Status | Work | Reason |
|-------|--------|------|--------|
| 1 | `done` | M-1.1-M-1.7 | Define user scenarios before deriving automated tests |
| 2 | `done` | M0.1-M0.5 | Establish the case-aware definition of done before implementation |
| 3 | `in_progress` | M1.1-M1.7 | Prove selected cases without GUI fragility where possible |
| 4 | `done` | M2.1-M2.4 | Make acceptance results auditable |
| 5 | `done` | M5.1-M5.4 for selected case/L1 only | Provide a stable one-command verifier per case |
| 6 | `not_started` | M3.1-M3.4 | Add GUI visibility after case L1 stabilizes |
| 7 | `blocked` | M3.5 | Resume when Pencil MCP can open `ui/design/piproofforge.pen` |
| 8 | `not_started` | M4.1-M4.4 | Add external check-mode last because it depends on session/platform state |

## 9. Milestone Definition of Done

| Milestone | Status | Done Criteria |
|-----------|--------|---------------|
| M-1 Done | `done` | Scenario case catalog contains all first-batch cases with `ready_for_implementation` status |
| M0 Done | `done` | Contract exists, validates, and is derived from an approved `case_id` |
| M1 Done | `in_progress` | Selected scenario L1 settings, structured connection checks, and run-page provider summaries pass locally; optional L3-local live request remains |
| M2 Done | `done` | Reports include level, phase, step, status, evidence, and failure message |
| M3 Done | `not_started` | GUI smoke verifies all 9 pages and Submissions detail with mock sidecar data |
| M4 Done | `not_started` | Check-mode channel run proves external path without final submit |
| M5 Done | `done` | One command runs the selected levels and writes acceptance reports |

## 10. Risk Register

| Risk | Status | Impact | Mitigation |
|------|--------|--------|------------|
| Acceptance test becomes too broad and flaky | `not_started` | False failures block delivery | Keep L1 focused on one selected scenario; isolate L3 as optional/external |
| GUI test depends on live sidecar state | `not_started` | Hard-to-debug UI failures | Use mock sidecar payloads for L2 smoke |
| Real platform changes break L3 | `not_started` | External validation becomes noisy | Mark L3 separately; never let it obscure selected-scenario L1 status |
| Pencil MCP unavailable | `blocked` | Cannot verify `.pen` design asset against latest implementation | Keep M3.5 blocked until MCP transport works; do not block L1 |
| Contract duplicates implementation details | `not_started` | Maintenance cost rises | Contract should define outputs and stage semantics, not internal call order |

## 11. Reporting Format

The final Markdown report should use this shape:

```text
# User Journey Acceptance Report

Run ID: acceptance-YYYYMMDD-HHMMSS
Overall: PASS | FAIL | BLOCKED

| Level | Status | Evidence |
|-------|--------|----------|
| L1 Scenario Data/API Validation | PASS | outputs/acceptance/... |
| L2 User Visible Scenario | PASS | outputs/acceptance/... |
| L3 Local/External Integration | BLOCKED | BLOCKED_LOCAL_PROVIDER |

## Stage Results

| Case | Check | Status | Evidence | Message |
|------|-------|--------|----------|---------|
| first_launch_configure_lm_studio | settings_saved | PASS | outputs/acceptance/... | LM Studio config persisted |
| first_launch_configure_lm_studio | connection_test | BLOCKED | outputs/acceptance/... | LM Studio unavailable at 127.0.0.1:1234 |
| first_launch_configure_lm_studio | quick_run_summary | PASS | outputs/acceptance/... | Quick Run can read provider summary |
```

## 12. Current Next Action

| Priority | Status | Action | Owner |
|----------|--------|--------|-------|
| P0 | `done` | Define next feedback iteration case after submission check-mode | Completed 2026-05-17 |
| P0 | `done` | Implement M0 case-aware journey contract after approved scenario cases | Completed 2026-05-17 |
| P0 | `in_progress` | Implement M1 selected-case acceptance test | Case 1 settings persistence + structured connection check completed 2026-05-20; Quick Run / Agent Run provider summary checks completed 2026-05-21 |
| P1 | `done` | Implement M2 report generator | Completed 2026-05-20 |
| P1 | `done` | Wire L1 into acceptance runner | Completed 2026-05-21 |
| P2 | `not_started` | Implement GUI smoke and external check-mode | Unassigned |
