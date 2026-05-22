# PiProofForge Demo Runbook

This runbook defines the repeatable local demo path. It is intentionally short:
run the readiness check first, then present the generated artifacts and, when
needed, the desktop Quick Run flow.

## 1. Pre-Demo Check

Default deterministic check:

```bash
bash scripts/acceptance/run-demo-readiness.sh
```

This runs the local evidence-first sample pipeline and writes:

- `outputs/demo/<run_id>/readiness-report.json`
- `outputs/demo/<run_id>/readiness-report.md`
- `outputs/demo/<run_id>/demo-report.json`
- `outputs/demo/<run_id>/demo-report.md`

Expected result:

- `readiness-report.md` status is `pass`.
- The `core demo` step is `pass`.
- The demo report lists Evidence Card, Matching Report, A/B Markdown Resume,
  Scorecard, Run Record, and required pipeline events.

## 2. GUI Check

There is currently no demo readiness GUI flag. A GUI gate must be implemented
as external real-page automation.

## 3. Demo Order

1. Show the readiness report:
   `outputs/demo/<run_id>/readiness-report.md`
2. Show traceability in the demo report:
   `outputs/demo/<run_id>/demo-report.md`
3. Open the generated matching report:
   `matching_reports/mr-<run_id>.yaml`
4. Open generated resumes:
   `outputs/<run_id>/resume_mr-<run_id>_A.md`
   and `outputs/<run_id>/resume_mr-<run_id>_B.md`
5. Open the scorecard:
   `outputs/scorecards/scorecard_mr-<run_id>_A.md`
6. Open the Quick Run page manually only as a demo aid; do not claim this as
   automated acceptance until the external GUI driver exists.

## 4. Failure Handling

If the default check fails:

- Open `outputs/demo/<run_id>/readiness-report.md`.
- Use the failed step name and message as the first triage target.
- For `core demo` failures, open `outputs/demo/<run_id>/demo-report.md`.
- Do not proceed to GUI validation until the deterministic core demo passes.

If GUI validation is needed after the core demo passed:

- Add or run an external real-page automation driver.
- Keep `readiness-report.md` attached to the issue or handoff note.

## 5. Scope

This runbook verifies the local evidence-first demo. It does not perform real
submission, external job discovery, or final channel delivery.
