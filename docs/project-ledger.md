# Project Ledger

Last updated: 2026-05-22

## Current Acceptance Policy

- Scenario acceptance for GUI behavior must be driven by external automation against the real page, real browser boundary, or real Tauri desktop shell.
- Production pages must not contain acceptance-only environment branches, self-starting flows, page event logging hooks, or verifier controllers.
- Repository scripts must not expose embedded GUI acceptance entrypoints.
- Audit code may aggregate real artifacts, but it must not substitute for real-page scenario automation.

## Current Mainline

- System Settings: LLM provider defaults, model discovery, save/reload, masked secret behavior, and blocked local-provider failure path are covered by scenario and contract tests.
- Resumes and Evidence: material library inputs feed the evidence-first workflow and Evidence Card review contracts.
- Jobs: pasted JD text can create reviewed job targets for downstream matching and runs.
- Quick Run: selected eligible Evidence Cards and complete Job Profiles produce matching, resume, PDF, scorecard, and gap artifacts with traceability.
- Agent Run: guided batch stops at review state, writes review queue artifacts, and keeps delivery disabled before approval.
- Submissions: channel session setup, check mode, submit-skipped logging, and feedback iteration are represented by sidecar contracts and real artifacts.
- Closed-loop audit reads durable artifacts from `outputs/quick_runs`, `outputs/agent_runs`, `outputs/submissions`, and `outputs/feedback_iterations`.
- External L3: `run-acceptance --level L3` now writes a guarded live blocker or real-channel result record; missing explicit authorization or missing separate final-submit confirmation never attempts external submission.
- External L3 handoff: validation records include an `operator_handoff` package with required env presence, pre-run checklist, forbidden inputs, and a redacted command template for a future authorized live run.

## Verification Anchors

- `constitution.md`
- `docs/acceptance-depth.md`
- `docs/execution-roadmap.md`
- `acceptance/journey_implementation_matrix.yaml`
- `tools/acceptance/acceptance_runner.py`
- `tests/acceptance/test_acceptance_runner.py`
- `tests/unit/gui/test_native_verifier_contract.py`

## Last Verified Commands

- `python3 -m pytest tests/ -q`
- `pnpm --dir ui build`
- `cargo check --manifest-path ui/src-tauri/Cargo.toml`
- `python3 tools/check_execution_roadmap.py --root .`
