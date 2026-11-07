import type { QuickRunStageProgress, QuickRunStartResult } from "@/lib/sidecar/types";

export type LoadState = "loading" | "ready" | "error";
export type RunState = "idle" | "ready_to_run" | "running" | "done" | "error";
export type StageStatus = "waiting" | "running" | "done" | "error" | "skipped";

export const PIPELINE_STEPS = [
  { key: "extract", labelKey: "pages.quickRun.steps.extract" },
  { key: "match", labelKey: "pages.quickRun.steps.match" },
  { key: "generate", labelKey: "pages.quickRun.steps.generate" },
  { key: "evaluate", labelKey: "pages.quickRun.steps.evaluate" },
] as const;

export const SCORE_KEYS = ["K", "D", "S", "Q", "E", "R"] as const;
export const SCORE_MAX = 20;

export const stageStatusClass: Record<StageStatus, string> = {
  waiting: "border-border bg-bg-primary/60 text-text-secondary",
  skipped: "border-border bg-bg-primary/60 text-text-secondary",
  running: "border-accent bg-accent/10 text-text-primary",
  done: "border-success/50 bg-success/10 text-text-primary",
  error: "border-error/50 bg-error/10 text-text-primary",
};

export const failedStepAliases: Record<(typeof PIPELINE_STEPS)[number]["key"], string[]> = {
  extract: ["extract", "extraction", "evidence"],
  match: ["match", "matching", "scoring"],
  generate: ["generate", "generation"],
  evaluate: ["evaluate", "evaluation"],
};

export function getStageStatus(
  runState: RunState,
  status: string | null,
  failedStep: string,
  stepIndex: number,
  stages: QuickRunStageProgress[] | undefined,
  stepKey: string
): StageStatus {
  // RUNNING 时使用后端回写的真实阶段进度；没有进度时只让首阶段进行中，避免四个阶段同时转圈。
  if (runState === "running") {
    const stage = stages?.find((item) => item.key === stepKey);
    if (stage) return stage.status;
    return stepIndex === 0 ? "running" : "waiting";
  }
  if (status === "SKIPPED") {
    const stoppedIndex = PIPELINE_STEPS.findIndex(step => failedStepAliases[step.key].some(alias => failedStep.includes(alias)));
    return stoppedIndex >= 0 && stepIndex < stoppedIndex ? "done" : "skipped";
  }
  if (status === "DONE") {
    return "done";
  }
  if (runState === "error") {
    const failedIndex = PIPELINE_STEPS.findIndex((step) =>
      failedStepAliases[step.key].some((alias) => failedStep.includes(alias))
    );
    if (failedIndex === -1) return stepIndex === 0 ? "error" : "waiting";
    if (stepIndex < failedIndex) return "done";
    return stepIndex === failedIndex ? "error" : "waiting";
  }
  return "waiting";
}

export function formatTerminalLines(
  result: QuickRunStartResult | null, runError: string | null,
  labels: { needsReview: string; needsEvidence: string; notGenerated: string }
) {
  if (!result && !runError) return [];
  const lines: string[] = [];
  if (result) {
    lines.push(`[quick-run] run_id=${result.run_id} status=${result.status}`);
    if (result.reason) lines.push(`[quick-run] reason=${result.reason}`);
    if (result.run_record) lines.push(`[quick-run] run_record=${result.run_record}`);
    const stdout = result.stdout?.trim();
    const stderr = result.stderr?.trim();
    if (stdout) lines.push(...stdout.split(/\r?\n/));
    if (stderr) lines.push(...stderr.split(/\r?\n/).map((line) => `[stderr] ${line}`));
    if (result.resume_readiness) {
      const readiness = result.resume_readiness;
      lines.push(readiness.status === "NOT_GENERATED" ? labels.notGenerated : readiness.status === "NEEDS_EVIDENCE" ? labels.needsEvidence : labels.needsReview);
      lines.push(...readiness.reasons.map((reason) => `- ${reason}`));
    }
  }
  if (runError) lines.push(`[error] ${runError}`);
  return lines.slice(-80);
}

export function formatConfigValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
}
