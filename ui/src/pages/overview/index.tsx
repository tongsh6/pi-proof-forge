import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import { getOverview } from "@/lib/sidecar/api";
import type { OverviewActivity, OverviewGap, OverviewTrendPoint } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";

const metricCardKeys = [
  "evidence_count",
  "matched_jobs_count",
  "resume_count",
  "submission_count",
] as const;

const severityToneMap = {
  high: "text-error border-error/40 bg-error/10",
  medium: "text-warning border-warning/40 bg-warning/10",
  low: "text-accent border-accent/40 bg-accent/10",
} as const;

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Record<(typeof metricCardKeys)[number], number>>({
    evidence_count: 0,
    matched_jobs_count: 0,
    resume_count: 0,
    submission_count: 0,
  });
  const [activities, setActivities] = useState<OverviewActivity[]>([]);
  const [trend, setTrend] = useState<OverviewTrendPoint[]>([]);
  const [gaps, setGaps] = useState<OverviewGap[]>([]);

  const loadOverview = useCallback(async () => {
    setLoadState("loading");
    setError(null);

    try {
      const result = await getOverview();
      setMetrics(result.metrics);
      setActivities(result.recent_activities);
      setTrend(result.match_trend);
      setGaps(result.gaps);
      setLoadState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.overview.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.overview.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadOverview()}
          className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
        >
          {t("common.retry")}
        </button>
      </header>

      {loadState === "loading" ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.loading")}
        </section>
      ) : null}

      {loadState === "error" ? (
        <section className="rounded-panel border border-error/50 bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{error}</p>
        </section>
      ) : null}

      {loadState === "ready" ? (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {metricCardKeys.map((metricKey) => (
              <article
                key={metricKey}
                className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]"
              >
                <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                  {t(`pages.overview.metrics.${metricKey}.label`)}
                </p>
                <p className="mt-4 text-4xl font-semibold tracking-tight text-text-primary">
                  {metrics[metricKey]}
                </p>
                <p className="mt-2 text-sm text-text-secondary">
                  {t(`pages.overview.metrics.${metricKey}.hint`)}
                </p>
              </article>
            ))}
          </section>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_380px]">
            <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="border-b border-border pb-4">
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.overview.recentActivity.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.overview.recentActivity.subtitle")}
                </p>
              </div>
              <div className="space-y-3 pt-4">
                {activities.length > 0 ? (
                  activities.map((activity) => (
                    <div
                      key={activity.activity_id}
                      className="rounded-card border border-border px-4 py-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="rounded-chip bg-accent/10 px-2.5 py-1 text-xs uppercase tracking-[0.14em] text-accent">
                          {t(`pages.overview.activityTypes.${activity.type}`)}
                        </span>
                        <span className="text-xs text-text-muted">
                          {new Date(activity.timestamp).toLocaleString(i18n.language)}
                        </span>
                      </div>
                      <p className="mt-3 text-sm text-text-primary">
                        {activity.description}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-text-secondary">{t("common.empty")}</p>
                )}
              </div>
            </article>

            <div className="space-y-6">
              <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
                <div className="border-b border-border pb-4">
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.overview.matchTrend.title")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.overview.matchTrend.subtitle")}
                  </p>
                </div>
                <div className="space-y-3 pt-4">
                  {trend.length > 0 ? (
                    trend.map((point) => (
                      <div key={point.date}>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-text-secondary">{point.date}</span>
                          <span className="font-medium text-text-primary">{point.score}</span>
                        </div>
                        <div className="mt-2 h-2 rounded-full bg-bg-hover">
                          <div
                            className="h-2 rounded-full bg-gradient-to-r from-accent to-accent-cyan"
                            style={{ width: `${Math.max(8, Math.min(point.score, 100))}%` }}
                          />
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-text-secondary">{t("common.empty")}</p>
                  )}
                </div>
              </article>

              <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
                <div className="border-b border-border pb-4">
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.overview.gaps.title")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.overview.gaps.subtitle")}
                  </p>
                </div>
                <div className="space-y-3 pt-4">
                  {gaps.length > 0 ? (
                    gaps.map((gap) => (
                      <div
                        key={gap.gap_id}
                        className="rounded-card border px-4 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium text-text-primary">
                            {gap.description}
                          </p>
                          <span
                            className={`rounded-chip border px-2.5 py-1 text-xs uppercase tracking-[0.14em] ${severityToneMap[gap.severity]}`}
                          >
                            {gap.severity}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-text-secondary">
                          {gap.suggested_action}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-text-secondary">{t("common.empty")}</p>
                  )}
                </div>
              </article>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
