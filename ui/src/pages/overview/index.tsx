import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  FileText,
  FolderSearch,
  PlayCircle,
  RefreshCw,
  Send,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { getOverview } from "@/lib/sidecar/api";
import type { OverviewActivity, OverviewGap, OverviewTrendPoint } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

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

const activityIconMap: Record<OverviewActivity["type"], LucideIcon> = {
  resume_generated: FileText,
  submission_sent: Send,
  evidence_imported: FolderSearch,
  agent_run_completed: Bot,
};

function recordVerifyEvent(
  event: string,
  details: Record<string, unknown> = {}
) {
  if (verifyScenario !== "overview") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
}

function buildTrendPath(
  trend: OverviewTrendPoint[],
  width: number,
  height: number,
  padding: number
): { trendPath: string; areaPath: string; points: string } {
  if (trend.length === 0) {
    return { trendPath: "", areaPath: "", points: "" };
  }

  const scores = trend.map((point) => point.score);
  const minScore = Math.min(...scores, 40);
  const maxScore = Math.max(...scores, 100);
  const scoreRange = Math.max(1, maxScore - minScore);
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  const coords = trend.map((point, index) => {
    const x =
      trend.length === 1
        ? width / 2
        : padding + (index / (trend.length - 1)) * chartWidth;
    const normalized = (point.score - minScore) / scoreRange;
    const y = padding + (1 - normalized) * chartHeight;
    return [Number(x.toFixed(2)), Number(y.toFixed(2))] as const;
  });

  const trendPath = coords
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`)
    .join(" ");
  const [firstX] = coords[0];
  const [lastX] = coords[coords.length - 1];
  const areaPath = `${trendPath} L ${lastX} ${height - padding} L ${firstX} ${
    height - padding
  } Z`;
  const points = coords.map(([x, y]) => `${x},${y}`).join(" ");

  return { trendPath, areaPath, points };
}

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
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
      recordVerifyEvent("overview.load.ready", {
        evidence_count: result.metrics.evidence_count,
        matched_jobs_count: result.metrics.matched_jobs_count,
        resume_count: result.metrics.resume_count,
        submission_count: result.metrics.submission_count,
        activity_count: result.recent_activities.length,
        trend_count: result.match_trend.length,
        gap_count: result.gaps.length,
      });
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setLoadState("error");
      recordVerifyEvent("overview.load.error", {
        error: getErrorMessage(nextError),
      });
    }
  }, []);

  const gapSummary = useMemo(
    () => ({
      total: gaps.length,
      high: gaps.filter((gap) => gap.severity === "high").length,
      medium: gaps.filter((gap) => gap.severity === "medium").length,
      low: gaps.filter((gap) => gap.severity === "low").length,
    }),
    [gaps]
  );
  const { trendPath, areaPath, points } = useMemo(
    () => buildTrendPath(trend, 320, 180, 20),
    [trend]
  );

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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void loadOverview()}
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
          >
            <RefreshCw size={16} />
            {t("pages.overview.refresh")}
          </button>
          <button
            type="button"
            onClick={() => navigate("/agent-run")}
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            <PlayCircle size={16} />
            {t("pages.overview.startAgent")}
          </button>
        </div>
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
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-text-secondary">
                    {t(`pages.overview.metrics.${metricKey}.label`)}
                  </p>
                  <CheckCircle2 size={18} className="text-accent" />
                </div>
                <p className="mt-4 text-4xl font-semibold text-text-primary">
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
                      className="flex gap-3 rounded-card border border-border bg-bg-primary px-4 py-3"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-card border border-accent/30 bg-accent/10 text-accent">
                        {(() => {
                          const Icon = activityIconMap[activity.type] ?? Activity;
                          return <Icon size={18} />;
                        })()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs font-medium text-accent">
                            {t(`pages.overview.activityTypes.${activity.type}`)}
                          </span>
                          <span className="shrink-0 text-xs text-text-muted">
                            {new Date(activity.timestamp).toLocaleString(i18n.language)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-text-primary">
                          {activity.description}
                        </p>
                      </div>
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
                <div className="pt-4">
                  {trend.length > 0 ? (
                    <div>
                      <svg
                        aria-label={t("pages.overview.matchTrend.chartLabel")}
                        className="h-48 w-full"
                        role="img"
                        viewBox="0 0 320 180"
                      >
                        <defs>
                          <linearGradient id="overview-trend-fill" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.28" />
                            <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.02" />
                          </linearGradient>
                        </defs>
                        <path d={areaPath} fill="url(#overview-trend-fill)" />
                        <path
                          d={trendPath}
                          fill="none"
                          stroke="#38BDF8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="3"
                        />
                        {points.split(" ").map((point) => {
                          const [x, y] = point.split(",");
                          return (
                            <circle
                              key={point}
                              cx={x}
                              cy={y}
                              fill="#071023"
                              r="4"
                              stroke="#22D3EE"
                              strokeWidth="2"
                            />
                          );
                        })}
                      </svg>
                      <div className="mt-3 grid gap-2">
                        {trend.slice(-3).map((point) => (
                          <div
                            key={point.date}
                            className="flex items-center justify-between text-sm"
                          >
                            <span className="text-text-secondary">{point.date}</span>
                            <span className="font-medium text-text-primary">
                              {point.score}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-text-secondary">
                      {t("pages.overview.matchTrend.empty")}
                    </p>
                  )}
                </div>
              </article>

              <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
                <div className="border-b border-border pb-4">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.overview.gaps.title")}
                    </h2>
                    <span className="inline-flex items-center gap-1.5 rounded-chip border border-error/40 bg-error/10 px-2.5 py-1 text-xs font-medium text-error">
                      <AlertTriangle size={14} />
                      {t("pages.overview.gapCount", { count: gapSummary.total })}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.overview.gaps.subtitle")}
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-4">
                  {(["high", "medium", "low"] as const).map((severity) => (
                    <div
                      key={severity}
                      className={`rounded-card border px-3 py-2 text-center ${severityToneMap[severity]}`}
                    >
                      <p className="text-lg font-semibold">{gapSummary[severity]}</p>
                      <p className="text-xs">{t(`pages.overview.severity.${severity}`)}</p>
                    </div>
                  ))}
                </div>
                <div className="space-y-3 pt-4">
                  {gaps.length > 0 ? (
                    gaps.map((gap) => (
                      <div
                        key={gap.gap_id}
                        className="rounded-card border border-border bg-bg-primary px-4 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium text-text-primary">
                            {gap.description}
                          </p>
                          <span
                            className={`rounded-chip border px-2.5 py-1 text-xs font-medium ${severityToneMap[gap.severity]}`}
                          >
                            {t(`pages.overview.severity.${gap.severity}`)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-text-secondary">
                          {gap.suggested_action}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-text-secondary">
                      {t("pages.overview.gaps.none")}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => navigate("/evidence")}
                  className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
                >
                  <TrendingUp size={16} />
                  {t("pages.overview.viewAllGaps")}
                </button>
              </article>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
