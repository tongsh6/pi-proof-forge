import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Ban,
  Bot,
  Briefcase,
  CalendarCheck,
  CheckCircle2,
  CloudOff,
  Eye,
  FileText,
  HelpCircle,
  ThumbsUp,
  XCircle,
  FolderSearch,
  PlayCircle,
  RefreshCw,
  Send,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { getMaterialReadiness, getOverview, getSettings, listJobProfiles } from "@/lib/sidecar/api";
import { buttonClass, notify } from "@/lib/ui";
import type {
  OverviewActivity,
  OverviewFeedbackFunnel,
  OverviewGap,
  OverviewMetrics,
  OverviewTrendPoint,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SetupKey = "llm" | "resumes" | "evidence" | "jobs";
type SetupState = Record<SetupKey, boolean>;

/** 开始前清单：按用户旅程排序，每一步对应一个页面入口；页头主按钮指向第一个未完成项。 */
const SETUP_STEPS: Array<{ key: SetupKey; path: string }> = [
  { key: "llm", path: "/system-settings?section=llm" },
  { key: "resumes", path: "/resumes" },
  { key: "evidence", path: "/evidence" },
  { key: "jobs", path: "/jobs" },
];

/** 辅助读取：失败或未实现时返回 null，不影响总览主数据的加载状态。 */
async function readOptional<T>(call: () => Promise<T>): Promise<T | null> {
  try {
    return await call();
  } catch {
    return null;
  }
}

const metricCardKeys = [
  "evidence_count",
  "matched_jobs_count",
  "resume_count",
  "submission_count",
] as const;

/**
 * 投递进展：状态互斥，按“进展 → 终态 → 未知/未同步”排列。
 * 颜色只做辅助，每行都带图标、文字与计数；同色系用深浅区分相邻阶段。
 */
const FUNNEL_STATES: Array<{
  key: keyof OverviewFeedbackFunnel;
  icon: LucideIcon;
  bar: string;
  text: string;
}> = [
  { key: "delivered", icon: Send, bar: "bg-accent/45", text: "text-accent" },
  { key: "viewed", icon: Eye, bar: "bg-accent", text: "text-accent" },
  { key: "interested", icon: ThumbsUp, bar: "bg-success/55", text: "text-success" },
  { key: "interview", icon: CalendarCheck, bar: "bg-success", text: "text-success" },
  { key: "rejected", icon: XCircle, bar: "bg-error", text: "text-error" },
  { key: "closed", icon: Ban, bar: "bg-warning", text: "text-warning" },
  { key: "unknown", icon: HelpCircle, bar: "bg-text-muted", text: "text-text-secondary" },
  { key: "unsynced", icon: CloudOff, bar: "bg-border", text: "text-text-muted" },
];

/** 统计卡可点击进入对应页面；图标按指标区分。 */
const metricCardMeta: Record<
  (typeof metricCardKeys)[number],
  { path: string; icon: LucideIcon }
> = {
  evidence_count: { path: "/evidence", icon: FolderSearch },
  matched_jobs_count: { path: "/jobs", icon: Briefcase },
  resume_count: { path: "/resumes", icon: FileText },
  submission_count: { path: "/submissions", icon: Send },
};

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
  const [metrics, setMetrics] = useState<OverviewMetrics>({
    evidence_count: 0,
    matched_jobs_count: 0,
    resume_count: 0,
    submission_count: 0,
  });
  const [activities, setActivities] = useState<OverviewActivity[]>([]);
  const [trend, setTrend] = useState<OverviewTrendPoint[]>([]);
  const [gaps, setGaps] = useState<OverviewGap[]>([]);
  const [setup, setSetup] = useState<SetupState | null>(null);

  const hasLoadedRef = useRef(false);
  const [refreshing, setRefreshing] = useState(false);

  // 首次加载显示占位；之后的刷新保留已有内容，只在页头提示“刷新中”。
  const loadOverview = useCallback(async () => {
    if (hasLoadedRef.current) setRefreshing(true);
    else setLoadState("loading");
    setError(null);

    try {
      const result = await getOverview();
      setMetrics(result.metrics);
      setActivities(result.recent_activities);
      setTrend(result.match_trend);
      setGaps(result.gaps);
      const [settings, readiness, profiles] = await Promise.all([
        readOptional(() => getSettings()),
        readOptional(() => getMaterialReadiness()),
        readOptional(() => listJobProfiles()),
      ]);
      setSetup(
        settings && readiness && profiles
          ? {
              // 后端在未配置时也会给出默认 provider/model，只有密钥（或本地占位）保存过才算配置完成。
              llm: Boolean(settings.llm_config?.api_key?.configured),
              resumes: readiness.status === "ready",
              evidence: result.metrics.evidence_count > 0,
              jobs: profiles.items.length > 0,
            }
          : null
      );
      hasLoadedRef.current = true;
      setLoadState("ready");
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      if (hasLoadedRef.current) notify("error", t("common.refreshFailed"), message);
      else setLoadState("error");
    } finally {
      setRefreshing(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
  const funnel = useMemo(() => {
    const data = metrics.feedback_funnel;
    const rows = FUNNEL_STATES.map((state) => ({ ...state, count: data?.[state.key] ?? 0 }));
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    const synced = total - (data?.unsynced ?? 0);
    return { rows, total, synced, segments: rows.filter((row) => row.count > 0) };
  }, [metrics.feedback_funnel]);

  const nextStep = useMemo(
    () => (setup ? SETUP_STEPS.find((step) => !setup[step.key]) ?? null : null),
    [setup]
  );

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void loadOverview();
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [loadOverview]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.overview.title")}</h1>
          <p className="page-subtitle">{t("pages.overview.subtitle")}</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="page-icon-button"
            onClick={() => void loadOverview()}
            disabled={refreshing}
            title={t("common.refreshShortcut")}
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            <span className="sr-only">{refreshing ? t("common.refreshing") : t("pages.overview.refresh")}</span>
          </button>
          <button
            type="button"
            data-testid="overview-primary-action"
            onClick={() => navigate(nextStep ? nextStep.path : "/agent-run")}
            className={buttonClass.primary}
          >
            {nextStep ? <ArrowRight size={16} /> : <PlayCircle size={16} />}
            {nextStep ? t(`pages.overview.setup.steps.${nextStep.key}.action`) : t("pages.overview.startAgent")}
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
          <button
            type="button"
            onClick={() => void loadOverview()}
            className="mt-4 inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
          >
            <RefreshCw size={16} />
            {t("common.retry")}
          </button>
        </section>
      ) : null}

      {loadState === "ready" ? (
        <>
          {setup && nextStep ? (
            <section
              data-testid="overview-setup"
              className="rounded-panel border border-accent/40 bg-bg-panel p-5 shadow-[var(--shadow-panel)]"
            >
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.overview.setup.title")}</h2>
              <p className="mt-1 text-sm text-text-secondary">{t("pages.overview.setup.subtitle")}</p>
              <ol className="mt-4 grid gap-2 md:grid-cols-2">
                {SETUP_STEPS.map((step, index) => {
                  const done = setup[step.key];
                  return (
                    <li
                      key={step.key}
                      data-setup-step={step.key}
                      data-setup-done={done ? "true" : "false"}
                      className={`flex items-center gap-3 rounded-card border border-border px-4 py-3 ${done ? "opacity-60" : "bg-bg-primary/40"}`}
                    >
                      {done ? (
                        <CheckCircle2 size={18} className="shrink-0 text-success" />
                      ) : (
                        <span className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border border-text-muted text-[11px] text-text-muted">
                          {index + 1}
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-text-primary">{t(`pages.overview.setup.steps.${step.key}.label`)}</p>
                        <p className="mt-0.5 text-xs text-text-secondary">
                          {done ? t("pages.overview.setup.done") : t(`pages.overview.setup.steps.${step.key}.hint`)}
                        </p>
                      </div>
                      {!done ? (
                        <button type="button" className={buttonClass.secondary} onClick={() => navigate(step.path)}>
                          {t(`pages.overview.setup.steps.${step.key}.action`)}
                        </button>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            </section>
          ) : null}

          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {metricCardKeys.map((metricKey) => {
              const { path, icon: MetricIcon } = metricCardMeta[metricKey];
              const label = t(`pages.overview.metrics.${metricKey}.label`);
              return (
                <button
                  key={metricKey}
                  type="button"
                  onClick={() => navigate(path)}
                  aria-label={t("pages.overview.openMetric", { label })}
                  className="rounded-panel border border-border bg-bg-panel p-5 text-left shadow-[var(--shadow-panel)] transition-colors hover:border-accent/60 hover:bg-bg-hover/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-text-secondary">{label}</p>
                    <MetricIcon size={18} className="text-accent" />
                  </div>
                  <p className="mt-4 text-4xl font-semibold text-text-primary">
                    {metrics[metricKey]}
                  </p>
                  <p className="mt-2 text-sm text-text-secondary">
                    {t(`pages.overview.metrics.${metricKey}.hint`)}
                  </p>
                </button>
              );
            })}
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
                        {points.split(" ").map((point, index) => {
                          const [x, y] = point.split(",");
                          return (
                            <circle
                              key={`${index}-${point}`}
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
                        {trend.slice(-3).map((point, index) => (
                          <div
                            key={`${index}-${point.date}`}
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

              <article
                data-testid="overview-funnel"
                className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]"
              >
                <div className="border-b border-border pb-4">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.overview.funnel.title")}
                    </h2>
                    <button
                      type="button"
                      onClick={() => navigate("/submissions")}
                      className="text-xs text-accent underline-offset-2 hover:underline"
                    >
                      {t("pages.overview.funnel.open")}
                    </button>
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.overview.funnel.subtitle")}
                  </p>
                </div>
                <div className="pt-4">
                  {funnel.total > 0 ? (
                    <>
                      <p className="text-sm text-text-secondary">
                        {t("pages.overview.funnel.synced", {
                          synced: funnel.synced,
                          count: funnel.total,
                        })}
                      </p>
                      <div
                        className="mt-3 flex h-2.5 w-full gap-0.5 overflow-hidden rounded-chip bg-bg-primary"
                        role="img"
                        aria-label={t("pages.overview.funnel.barLabel")}
                      >
                        {funnel.segments.map((row) => (
                          <div
                            key={row.key}
                            data-funnel-segment={row.key}
                            className={`h-full rounded-sm ${row.bar}`}
                            style={{ width: `${(row.count / funnel.total) * 100}%` }}
                            title={`${t(`pages.overview.funnel.states.${row.key}`)} ${row.count}`}
                          />
                        ))}
                      </div>
                      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
                        {funnel.rows.map((row) => {
                          const RowIcon = row.icon;
                          return (
                            <li
                              key={row.key}
                              data-funnel-row={row.key}
                              className={`flex items-center justify-between gap-2 rounded-card border border-border px-3 py-2 text-sm ${
                                row.count === 0 ? "opacity-50" : ""
                              }`}
                            >
                              <span className="flex min-w-0 items-center gap-2 text-text-secondary">
                                <RowIcon size={14} className={`shrink-0 ${row.text}`} aria-hidden="true" />
                                <span className="truncate">
                                  {t(`pages.overview.funnel.states.${row.key}`)}
                                </span>
                              </span>
                              <span className="font-mono text-sm font-semibold text-text-primary">
                                {row.count}
                              </span>
                            </li>
                          );
                        })}
                      </ul>
                    </>
                  ) : (
                    <p className="text-sm text-text-secondary">{t("pages.overview.funnel.empty")}</p>
                  )}
                </div>
              </article>

              <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
                <div className="border-b border-border pb-4">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.overview.gaps.title")}
                    </h2>
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-chip border px-2.5 py-1 text-xs font-medium ${
                        gapSummary.total > 0
                          ? "border-error/40 bg-error/10 text-error"
                          : "border-success/40 bg-success/10 text-success"
                      }`}
                    >
                      {gapSummary.total > 0 ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
                      {gapSummary.total > 0
                        ? t("pages.overview.gapCount", { count: gapSummary.total })
                        : t("pages.overview.gapsClear")}
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
                  onClick={() => navigate("/evidence?status=gap")}
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
