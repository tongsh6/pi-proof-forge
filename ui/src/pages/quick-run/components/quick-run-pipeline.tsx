import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle, ChevronRight, Circle, LoaderCircle } from "lucide-react";
import type { QuickRunStartResult } from "@/lib/sidecar/types";
import type { BackgroundTask } from "@/state/task-store";
import { PIPELINE_STEPS, getStageStatus, stageStatusClass } from "../quick-run-helpers";
import type { RunState } from "../quick-run-helpers";

type QuickRunPipelineProps = {
  runState: RunState;
  quickRunStatus: string | null;
  quickRunResult: QuickRunStartResult | null;
  task: BackgroundTask | undefined;
  elapsedSeconds: number;
};

/** Quick Run 四阶段进度条：状态与耗时来自后端回写的真实阶段进度。 */
export function QuickRunPipeline({
  runState,
  quickRunStatus,
  quickRunResult,
  task,
  elapsedSeconds,
}: QuickRunPipelineProps) {
  const { t } = useTranslation();
  return (
    <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
      {runState === "running" ? (
        <p role="status" className="mb-4 text-xs text-text-secondary">
          {t("pages.quickRun.runningHint")}
        </p>
      ) : null}
      <div className="grid gap-3 xl:grid-cols-4">
        {PIPELINE_STEPS.map((step, index) => {
          const progressStages = task?.progress?.stages;
          const stageProgress = progressStages?.find((item) => item.key === step.key);
          const stageStatus = getStageStatus(
            runState,
            quickRunStatus,
            quickRunResult?.failed_step ?? "",
            index,
            progressStages,
            step.key
          );
          const stageSeconds = stageProgress?.elapsed_seconds;
          const stageText =
            stageStatus === "running"
              ? t("pages.quickRun.progress.running", { seconds: stageSeconds ?? elapsedSeconds })
              : stageStatus === "done"
                ? runState === "running" && typeof stageSeconds === "number"
                  ? t("pages.quickRun.progress.done", { seconds: stageSeconds })
                  : t("pages.quickRun.result")
                : stageStatus === "error"
                  ? t("pages.quickRun.progress.failed")
                  : t(stageStatus === "skipped" ? "pages.quickRun.skipped" : "pages.quickRun.waiting");
          return (
            <div key={step.key} className="flex items-center gap-3">
              <div
                data-stage={step.key}
                data-stage-status={stageStatus}
                className={`min-h-[96px] flex-1 rounded-card border p-4 transition-colors ${stageStatusClass[stageStatus]}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium uppercase text-text-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {stageStatus === "done" ? (
                    <CheckCircle className="h-5 w-5 text-success" aria-hidden="true" />
                  ) : null}
                  {stageStatus === "running" ? (
                    <LoaderCircle className="h-5 w-5 animate-spin text-accent" aria-hidden="true" />
                  ) : null}
                  {stageStatus === "error" ? (
                    <AlertCircle className="h-5 w-5 text-error" aria-hidden="true" />
                  ) : null}
                  {stageStatus === "waiting" || stageStatus === "skipped" ? (
                    <Circle className="h-5 w-5 text-text-muted" aria-hidden="true" />
                  ) : null}
                </div>
                <p className="mt-3 text-sm font-semibold text-text-primary">
                  {t(step.labelKey)}
                </p>
                <p className="mt-2 text-xs text-text-secondary">
                  {stageText}
                </p>
              </div>
              {index < PIPELINE_STEPS.length - 1 ? (
                <ChevronRight className="hidden h-5 w-5 shrink-0 text-text-muted xl:block" aria-hidden="true" />
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
