import { useTranslation } from "react-i18next";
import { RefreshCw, Sparkles } from "lucide-react";
import type { EvidenceInferenceResult } from "@/lib/sidecar/types";
import type { ProblemFilter, SummaryCount } from "../evidence-helpers";

type EvidenceSummaryBarProps = {
  summaryCounts: SummaryCount[];
  problemFilter: ProblemFilter;
  onProblemFilterChange: (filter: ProblemFilter) => void;
  reconcileState: "idle" | "running" | "error";
  reconcileError: string | null;
  onReconcile: () => void;
  inferenceState: "idle" | "running" | "error";
  inferenceBusy: boolean;
  inference: EvidenceInferenceResult | null;
  inferenceNotice: string;
  inferenceError: string | null;
  hasHighConfidenceCandidates: boolean;
  onRunInference: () => void;
  onBatchAccept: () => void;
};

/** 证据页对账汇总条：计数筛选、重新对账、字段推断与批量接受。 */
export function EvidenceSummaryBar({
  summaryCounts,
  problemFilter,
  onProblemFilterChange,
  reconcileState,
  reconcileError,
  onReconcile,
  inferenceState,
  inferenceBusy,
  inference,
  inferenceNotice,
  inferenceError,
  hasHighConfidenceCandidates,
  onRunInference,
  onBatchAccept,
}: EvidenceSummaryBarProps) {
  const { t } = useTranslation();
  return (
    <section className="rounded-panel border border-border bg-bg-panel px-4 py-3 shadow-[var(--shadow-panel)]" data-testid="evidence-summary" aria-label={t("pages.evidence.summary.title")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1" data-testid="evidence-summary-counts">
          {summaryCounts.map((entry) => (
            <button
              aria-pressed={problemFilter === entry.key}
              className={`rounded-card px-2 py-1 text-xs transition-colors ${problemFilter === entry.key ? "bg-bg-hover text-accent" : "text-text-secondary hover:bg-bg-hover"}`}
              data-testid={`evidence-summary-${entry.key}`}
              key={entry.key}
              onClick={() => onProblemFilterChange(entry.key)}
              type="button"
            >
              {entry.label}
              <span className="ml-1 font-mono text-text-primary">{entry.count}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="inline-flex items-center gap-1 rounded-card border border-border px-3 py-1.5 text-xs text-text-primary disabled:opacity-50"
            data-testid="evidence-reconcile-run"
            disabled={reconcileState === "running"}
            onClick={onReconcile}
            type="button"
          >
            <RefreshCw className={reconcileState === "running" ? "animate-spin" : ""} size={13} />
            {t("pages.evidence.reconcile.run")}
          </button>
          <button
            className="inline-flex items-center gap-1 rounded-card border border-border px-3 py-1.5 text-xs text-text-primary disabled:opacity-50"
            data-testid="evidence-inference-run"
            disabled={inferenceState === "running" || inferenceBusy}
            onClick={onRunInference}
            type="button"
          >
            <Sparkles size={13} />
            {t(inferenceState === "running" ? "pages.evidence.reconcile.inference.running" : "pages.evidence.reconcile.inference.run")}
          </button>
          {hasHighConfidenceCandidates ? (
            <button
              className="rounded-card border border-accent bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              data-testid="evidence-inference-batch"
              disabled={inferenceBusy}
              onClick={onBatchAccept}
              type="button"
            >
              {t("pages.evidence.reconcile.inference.batchAccept")}
            </button>
          ) : null}
        </div>
      </div>
      <p className="mt-2 text-xs text-text-muted" data-testid="evidence-summary-hint">
        {reconcileState === "running"
          ? t("pages.evidence.summary.running")
          : reconcileState === "error" && reconcileError
            ? reconcileError
            : inference && !inference.enabled
              ? t("pages.evidence.reconcile.inference.disabledHint")
              : t("pages.evidence.summary.hint")}
        {inferenceNotice ? <span className="ml-2 text-success" role="status">{inferenceNotice}</span> : null}
        {inferenceError ? <span className="ml-2 text-error" role="alert">{inferenceError}</span> : null}
      </p>
    </section>
  );
}
