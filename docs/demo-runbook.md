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

## 2. Optional GUI Check

Run this only when a local desktop GUI validation is required:

```bash
bash scripts/acceptance/run-demo-readiness.sh --include-gui
```

This adds the existing native Quick Run verifier:

```bash
pnpm --dir ui run e2e:quick-run
```

Expected result:

- The readiness report still ends with `pass`.
- The `quick run native verifier` step is `pass`.
- GUI artifacts are under `ui/test-results/quick-run-native/`.

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
6. If the GUI check was enabled, open the Quick Run page and show the same
   pipeline state from the desktop UI.

## 4. Failure Handling

If the default check fails:

- Open `outputs/demo/<run_id>/readiness-report.md`.
- Use the failed step name and message as the first triage target.
- For `core demo` failures, open `outputs/demo/<run_id>/demo-report.md`.
- Do not proceed to GUI validation until the deterministic core demo passes.

If `--include-gui` fails after the core demo passed:

- Treat it as a GUI/native verifier issue, not a core pipeline failure.
- Inspect `ui/test-results/quick-run-native/tauri.log`.
- Keep `readiness-report.md` attached to the issue or handoff note.

## 5. Scope

This runbook verifies the local evidence-first demo. It does not perform real
submission, external job discovery, or final channel delivery.
