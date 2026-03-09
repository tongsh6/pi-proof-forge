import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import { getPendingReview, submitReview } from "@/lib/sidecar/api";
import type { ReviewCandidateItem } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SubmitState = "idle" | "submitting" | "done" | "error";

export function AgentRunPage() {
  const { t } = useTranslation();
  const [candidates, setCandidates] = useState<ReviewCandidateItem[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const loadPending = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const result = await getPendingReview();
      setCandidates(result.candidates ?? []);
      setLoadState("ready");
    } catch (e) {
      setCandidates([]);
      setLoadState("error");
      setError(getErrorMessage(e));
    }
  }, []);

  useEffect(() => {
    void loadPending();
  }, [loadPending]);

  const handleDecision = useCallback(
    async (jobLeadId: string, action: "approve" | "reject" | "skip") => {
      setSubmitState("submitting");
      setSubmitError(null);
      try {
        await submitReview([
          {
            job_lead_id: jobLeadId,
            action,
            decided_by: "user",
            decided_at: new Date().toISOString(),
          },
        ]);
        setSubmitState("done");
        void loadPending();
      } catch (e) {
        setSubmitState("error");
        setSubmitError(getErrorMessage(e));
      }
    },
    [loadPending]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">
          {t("pages.agentRun.title")}
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          {t("pages.agentRun.subtitle")}
        </p>
      </div>

      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.agentRun.pendingReview")}
            </h2>
            <p className="mt-1 text-sm text-text-secondary">
              {t("pages.agentRun.pendingReviewSubtitle")}
            </p>
          </div>
          <button
            type="button"
            className="rounded-card border border-border px-3 py-1.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-60"
            onClick={() => void loadPending()}
            disabled={loadState === "loading"}
          >
            {t("pages.agentRun.refresh")}
          </button>
        </div>

        {loadState === "loading" && (
          <p className="py-8 text-center text-sm text-text-muted">
            {t("common.loading")}
          </p>
        )}

        {loadState === "error" && (
          <div className="rounded-panel border border-error/50 bg-bg-panel p-4">
            <p className="text-sm font-medium text-error">{t("common.error")}</p>
            <p className="mt-2 text-sm text-text-secondary">{error}</p>
            <button
              type="button"
              className="mt-3 rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary hover:bg-bg-hover"
              onClick={() => void loadPending()}
            >
              {t("common.retry")}
            </button>
          </div>
        )}

        {loadState === "ready" && candidates.length === 0 && (
          <div className="py-8 text-center">
            <p className="text-sm font-medium text-text-primary">
              {t("pages.agentRun.emptyReview")}
            </p>
            <p className="mt-2 text-sm text-text-secondary">
              {t("pages.agentRun.emptyReviewHint")}
            </p>
          </div>
        )}

        {loadState === "ready" && candidates.length > 0 && (
          <ul className="space-y-4 pt-4">
            {candidates.map((c) => (
              <li
                key={c.job_lead_id}
                className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-border bg-bg-primary/40 p-4"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-text-primary">
                    {c.company} · {c.position}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-text-muted">
                    <span>
                      {t("pages.agentRun.matchScore")}: {c.matching_score}
                    </span>
                    <span>
                      {t("pages.agentRun.evalScore")}: {c.evaluation_score}
                    </span>
                    <span>
                      {t("pages.agentRun.round")}: {c.round_index}
                    </span>
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    className="rounded-card border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-60"
                    onClick={() => handleDecision(c.job_lead_id, "approve")}
                    disabled={submitState === "submitting"}
                  >
                    {t("pages.agentRun.approve")}
                  </button>
                  <button
                    type="button"
                    className="rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-60"
                    onClick={() => handleDecision(c.job_lead_id, "reject")}
                    disabled={submitState === "submitting"}
                  >
                    {t("pages.agentRun.reject")}
                  </button>
                  <button
                    type="button"
                    className="rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-hover disabled:opacity-60"
                    onClick={() => handleDecision(c.job_lead_id, "skip")}
                    disabled={submitState === "submitting"}
                  >
                    {t("pages.agentRun.skip")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {submitState === "error" && submitError && (
          <p className="mt-4 text-sm text-error">{submitError}</p>
        )}
      </section>
    </div>
  );
}
