import { useCallback, useEffect, useMemo, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  Image as ImageIcon,
  Mail,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  Timer,
  Trash2,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import {
  checkChannelSession,
  clearChannelSession,
  createFeedbackIteration,
  getChannelSession,
  getSubmissionDetail,
  listSubmissionFeedback,
  listSubmissions,
  retrySubmission,
  startSubmissionCheckMode,
  startChannelSession,
} from "@/lib/sidecar/api";
import type { ChannelSessionResult, FeedbackIterationResult, FeedbackListResult, SubmissionCheckModeResult, SubmissionDetail, SubmissionListItem } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type RetryStrategy = "same_channel" | "fallback_email";

const defaultSubmissionChannel = "liepin";
const checkModeConfirmationItems = [
  "check_mode_no_real_submit",
  "selected_submission_channel",
  "selected_channel_job_lead",
  "selected_resume_pdf",
  "selected_channel_session_metadata",
  "may_use_channel_shared_session",
  "final_confirm_disabled_and_forbidden",
  "must_stop_before_final_confirm",
];

type StatItem = {
  key: "total" | "delivered" | "failed" | "fallback";
  value: number;
  icon: typeof Send;
  className: string;
};

function formatDate(value: string, locale: string): string {
  if (!value.trim()) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale);
}

function isDelivered(status: string): boolean {
  return status === "success" || status === "done";
}

function isFailed(status: string): boolean {
  return status === "failed";
}

function isFallback(item: SubmissionListItem): boolean {
  const combined = `${item.channel} ${item.status} ${item.error} ${item.last_step.detail}`.toLowerCase();
  return combined.includes("fallback") || item.channel.toLowerCase() === "email";
}

function statusClassName(status: string): string {
  if (isDelivered(status)) {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "session_valid") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "blocked") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "waiting_for_manual_login" || status === "session_unknown" || status === "login_required") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "failed") {
    return "border-error/40 bg-error/10 text-error";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

function channelClassName(channel: string): string {
  if (channel.toLowerCase() === "email") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (channel.toLowerCase() === "liepin") {
    return "border-accent/40 bg-accent/10 text-accent";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

function channelLabel(item: SubmissionListItem, unknownChannel: string): string {
  const channel = item.channel || unknownChannel;
  return isFallback(item) && channel.toLowerCase() === "email" ? "Email ↩" : channel;
}

function detailText(item: SubmissionListItem, fallback: string): string {
  if (item.error) return item.error;
  if (item.last_step.detail) return item.last_step.detail;
  return fallback;
}

function submissionStatusLabel(status: string, t: (key: string, options?: Record<string, string>) => string): string {
  const normalized = status || "unknown";
  return t(`pages.submissions.status.${normalized}`, { defaultValue: normalized });
}

function screenshotSource(path: string): string | null {
  if (!path) return null;
  try {
    return convertFileSrc(path);
  } catch {
    return path;
  }
}

export function SubmissionsPage() {
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<SubmissionListItem[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [detailState, setDetailState] = useState<LoadState>("ready");
  const [selectedScreenshotPath, setSelectedScreenshotPath] = useState<string | null>(null);
  const [selectedChannel, setSelectedChannel] = useState(defaultSubmissionChannel);
  const [channelSession, setChannelSession] = useState<ChannelSessionResult | null>(null);
  const [sessionState, setSessionState] = useState<LoadState>("loading");
  const [sessionAction, setSessionAction] = useState<string | null>(null);
  const [checkModeResult, setCheckModeResult] = useState<SubmissionCheckModeResult | null>(null);
  const [checkModeState, setCheckModeState] = useState<LoadState>("ready");
  const [feedbackList, setFeedbackList] = useState<FeedbackListResult | null>(null);
  const [feedbackIteration, setFeedbackIteration] = useState<FeedbackIterationResult | null>(null);
  const [feedbackState, setFeedbackState] = useState<LoadState>("ready");
  const [checkModeForm, setCheckModeForm] = useState({
    jobLeadId: "",
    resumeVersionId: "",
    resumePdfPath: "",
  });

  const stats = useMemo<StatItem[]>(() => [
    {
      key: "total",
      value: items.length,
      icon: Send,
      className: "border-accent/30 bg-accent/10 text-accent",
    },
    {
      key: "delivered",
      value: items.filter((item) => isDelivered(item.status)).length,
      icon: CheckCircle2,
      className: "border-success/30 bg-success/10 text-success",
    },
    {
      key: "failed",
      value: items.filter((item) => isFailed(item.status)).length,
      icon: XCircle,
      className: "border-error/30 bg-error/10 text-error",
    },
    {
      key: "fallback",
      value: items.filter(isFallback).length,
      icon: Mail,
      className: "border-warning/30 bg-warning/10 text-warning",
    },
  ], [items]);

  const screenshotSteps = useMemo(
    () => detail?.steps.filter((step) => step.screenshot) ?? [],
    [detail],
  );

  const selectedScreenshot = useMemo(
    () => screenshotSteps.find((step) => step.screenshot_path === selectedScreenshotPath) ?? screenshotSteps.find((step) => step.screenshot_exists) ?? null,
    [screenshotSteps, selectedScreenshotPath],
  );

  useEffect(() => {
    const firstScreenshot = screenshotSteps.find((step) => step.screenshot_exists);
    setSelectedScreenshotPath(firstScreenshot?.screenshot_path ?? null);
  }, [screenshotSteps]);

  const loadData = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const result = await listSubmissions();
      setItems(result.items);
      if (selectedId && !result.items.some((item) => item.submission_id === selectedId)) {
        setSelectedId(null);
        setDetail(null);
      }
      setLoadState("ready");
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setLoadState("error");
    }
  }, [selectedId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const loadChannelSession = useCallback(async (channel = selectedChannel) => {
    setSessionState("loading");
    try {
      const result = await getChannelSession(channel);
      setChannelSession(result);
      setSessionState("ready");
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setSessionState("error");
    }
  }, [selectedChannel]);

  useEffect(() => {
    void loadChannelSession(selectedChannel);
  }, [loadChannelSession, selectedChannel]);

  const handleStartSession = useCallback(async () => {
    setSessionAction("start");
    setError(null);
    try {
      const result = await startChannelSession(selectedChannel);
      setChannelSession(result);
      setSessionState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setSessionState("error");
    } finally {
      setSessionAction(null);
    }
  }, [selectedChannel]);

  const handleCheckSession = useCallback(async (
    loginSignals: Record<string, unknown> = {
      login_required: true,
    },
    accountIdentity?: Record<string, unknown>,
  ) => {
    setSessionAction("check");
    setError(null);
    try {
      const result = await checkChannelSession(
        selectedChannel,
        loginSignals,
        accountIdentity,
      );
      setChannelSession(result);
      setSessionState("ready");
      return result;
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setSessionState("error");
      return null;
    } finally {
      setSessionAction(null);
    }
  }, [selectedChannel]);

  const handleClearSession = useCallback(async () => {
    setSessionAction("clear");
    setError(null);
    try {
      const result = await clearChannelSession(selectedChannel);
      setChannelSession(result);
      setSessionState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setSessionState("error");
    } finally {
      setSessionAction(null);
    }
  }, [selectedChannel]);

  const handleStartCheckMode = useCallback(async () => {
    setCheckModeState("loading");
    setError(null);
    try {
      const result = await startSubmissionCheckMode({
        channel: selectedChannel,
        job_lead_id: checkModeForm.jobLeadId.trim(),
        resume_version_id: checkModeForm.resumeVersionId.trim(),
        resume_pdf_path: checkModeForm.resumePdfPath.trim(),
        options: {
          preflight_confirmed: true,
          confirmed_no_real_submit: true,
          check_mode_no_real_submit: true,
          submit_enabled: false,
          confirmation_items: checkModeConfirmationItems,
          target_recovery_limit: 2,
          session_identity_accepted: true,
        },
      });
      setCheckModeResult(result);
      setCheckModeState("ready");
      await loadData();
      return result;
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setCheckModeState("error");
      return null;
    }
  }, [checkModeForm, loadData, selectedChannel]);

  const handleCreateFeedbackIteration = useCallback(async (sourceRunId?: string) => {
    const runId = sourceRunId || checkModeResult?.submission_id;
    if (!runId) return null;
    setFeedbackState("loading");
    setError(null);
    try {
      const list = await listSubmissionFeedback(runId);
      setFeedbackList(list);
      const result = await createFeedbackIteration({
        source_run_id: runId,
        source_feedback_items: list.items,
        selected_actions: ["prepare_next_check_mode"],
        user_notes: "Prepare a guarded next check-mode iteration.",
      });
      setFeedbackIteration(result);
      setFeedbackState("ready");
      return result;
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setFeedbackState("error");
      return null;
    }
  }, [checkModeResult?.submission_id]);

  const handleRetry = useCallback(async (submissionId: string, strategy: RetryStrategy = "same_channel") => {
    setRetryingId(submissionId);
    try {
      await retrySubmission(submissionId, strategy);
      await loadData();
      if (selectedId === submissionId) {
        const result = await getSubmissionDetail(submissionId);
        setDetail(result.submission);
      }
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setRetryingId(null);
    }
  }, [loadData, selectedId]);

  const handleSelect = useCallback(async (submissionId: string) => {
    setSelectedId(submissionId);
    setDetailState("loading");
    setError(null);
    try {
      const result = await getSubmissionDetail(submissionId);
      setDetail(result.submission);
      setDetailState("ready");
    } catch (nextError) {
      setDetail(null);
      setError(getErrorMessage(nextError));
      setDetailState("error");
    }
  }, []);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">{t("pages.submissions.title")}</h1>
          <p className="mt-2 text-sm text-text-secondary">{t("pages.submissions.subtitle")}</p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void loadData()} type="button">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t("pages.submissions.refresh")}
        </button>
      </header>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">{t("common.loading")}</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}

      {loadState === "ready" ? (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <div key={stat.key} className="rounded-card border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm text-text-secondary">{t(`pages.submissions.stats.${stat.key}`)}</p>
                      <p className="mt-2 text-2xl font-semibold text-text-primary">{stat.value}</p>
                    </div>
                    <span className={`grid h-10 w-10 place-items-center rounded-card border ${stat.className}`}>
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                  </div>
                </div>
              );
            })}
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.session.title")}</h2>
                <p className="mt-1 text-sm text-text-secondary">{t("pages.submissions.session.manualBoundary")}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select className="h-9 rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={selectedChannel} onChange={(event) => setSelectedChannel(event.target.value)} aria-label={t("pages.submissions.session.channel")}>
                  {(channelSession?.supported_channels ?? [{ channel: defaultSubmissionChannel, label: "Liepin", login_url: "" }]).map((channel) => (
                    <option key={channel.channel} value={channel.channel}>{channel.label}</option>
                  ))}
                </select>
                <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null} onClick={() => void handleStartSession()} type="button">
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                  {sessionAction === "start" ? t("pages.submissions.session.starting") : t("pages.submissions.session.start")}
                </button>
                <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null} onClick={() => void handleCheckSession()} type="button">
                  <RefreshCw className={`h-4 w-4 ${sessionAction === "check" ? "animate-spin" : ""}`} aria-hidden="true" />
                  {t("pages.submissions.session.check")}
                </button>
                <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null || !channelSession?.session.clear_available} onClick={() => void handleClearSession()} title={t("pages.submissions.session.clear")} type="button" aria-label={t("pages.submissions.session.clear")}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.statusLabel")}</p>
                <p className={`mt-1 inline-flex rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(channelSession?.session.login_status ?? "unknown")}`}>
                  {t(`pages.submissions.session.status.${channelSession?.session.login_status ?? "unknown"}`, { defaultValue: channelSession?.session.login_status ?? "unknown" })}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.checkedAt")}</p>
                <p className="mt-1 truncate text-text-primary">{formatDate(channelSession?.session.checked_at ?? "", i18n.language)}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.identity")}</p>
                <p className="mt-1 truncate text-text-primary">{channelSession?.session.account_identity.display_name_or_nickname || channelSession?.session.account_identity.masked_phone_or_email_suffix || t("pages.submissions.session.identityUnknown")}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.storage")}</p>
                <p className="mt-1 truncate text-text-primary">{channelSession?.session.expires_or_unknown ?? "--"}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-text-secondary md:grid-cols-2">
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.session.path")}</span> {channelSession?.session.session_path || "--"}</p>
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.session.log")}</span> {channelSession?.artifact_paths.session_check_log || "--"}</p>
            </div>
            {sessionState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.checkMode.title")}</h2>
                <p className="mt-1 text-sm text-text-secondary">{t("pages.submissions.checkMode.boundary")}</p>
              </div>
              <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={checkModeState === "loading" || channelSession?.session.login_status !== "session_valid" || !checkModeForm.jobLeadId.trim() || !checkModeForm.resumeVersionId.trim() || !checkModeForm.resumePdfPath.trim()} onClick={() => void handleStartCheckMode()} type="button">
                <Send className="h-4 w-4" aria-hidden="true" />
                {checkModeState === "loading" ? t("pages.submissions.checkMode.running") : t("pages.submissions.checkMode.start")}
              </button>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.jobLead")}</span>
                <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.jobLeadId} onChange={(event) => setCheckModeForm((current) => ({ ...current, jobLeadId: event.target.value }))} placeholder={t("pages.submissions.checkMode.jobLeadPlaceholder")} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.resumeVersion")}</span>
                <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.resumeVersionId} onChange={(event) => setCheckModeForm((current) => ({ ...current, resumeVersionId: event.target.value }))} placeholder={t("pages.submissions.checkMode.resumeVersionPlaceholder")} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.resume")}</span>
                <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.resumePdfPath} onChange={(event) => setCheckModeForm((current) => ({ ...current, resumePdfPath: event.target.value }))} placeholder={t("pages.submissions.checkMode.resumePathPlaceholder")} />
              </label>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.status")}</p>
                <p className={`mt-1 inline-flex rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(checkModeResult?.terminal_status ?? "unknown")}`}>
                  {checkModeResult?.terminal_status ?? "--"}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.jobLead")}</p>
                <p className="mt-1 truncate text-text-primary">{String((checkModeResult?.original_job_lead.job_lead_id ?? checkModeForm.jobLeadId) || "--")}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.resume")}</p>
                <p className="mt-1 truncate text-text-primary">{(checkModeResult?.resume_version_id ?? checkModeForm.resumeVersionId) || "--"}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.submit")}</p>
                <p className="mt-1 text-text-primary">{checkModeResult?.final_submit_attempted ? t("pages.submissions.checkMode.attempted") : t("pages.submissions.checkMode.skipped")}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-text-secondary md:grid-cols-2">
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.checkMode.json")}</span> {checkModeResult?.log_json_path || "--"}</p>
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.checkMode.steps")}</span> {checkModeResult?.steps.map((step) => step.name).join(" -> ") || "--"}</p>
            </div>
            {checkModeState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.feedback.title")}</h2>
                <p className="mt-1 text-sm text-text-secondary">{t("pages.submissions.feedback.boundary")}</p>
              </div>
              <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={feedbackState === "loading" || !checkModeResult?.submission_id} onClick={() => void handleCreateFeedbackIteration()} type="button">
                <RotateCcw className={`h-4 w-4 ${feedbackState === "loading" ? "animate-spin" : ""}`} aria-hidden="true" />
                {feedbackState === "loading" ? t("pages.submissions.feedback.recording") : t("pages.submissions.feedback.create")}
              </button>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.items")}</p>
                <p className="mt-1 text-text-primary">{feedbackList?.items.length ?? 0}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.action")}</p>
                <p className="mt-1 truncate text-text-primary">{feedbackIteration?.iteration.selected_actions.join(", ") || "--"}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.version")}</p>
                <p className="mt-1 truncate text-text-primary">{feedbackIteration?.iteration.new_resume_version_id_or_none || "--"}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.next")}</p>
                <p className="mt-1 truncate text-text-primary">{feedbackIteration?.iteration.next_recommended_step || "--"}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-text-secondary md:grid-cols-2">
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.feedback.record")}</span> {feedbackIteration?.record_path || "--"}</p>
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.feedback.snapshot")}</span> {feedbackIteration?.iteration.source_snapshot_path || "--"}</p>
            </div>
            {feedbackState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(390px,0.64fr)]">
          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.runsTitle")}</h2>
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[640px]">
                <div className="grid grid-cols-[minmax(110px,1.05fr)_minmax(120px,1.05fr)_76px_118px_70px_58px] gap-3 border-b border-border px-5 py-3 text-xs font-medium uppercase tracking-[0.08em] text-text-muted">
                  <span>{t("pages.submissions.table.company")}</span>
                  <span>{t("pages.submissions.table.position")}</span>
                  <span>{t("pages.submissions.table.channel")}</span>
                  <span>{t("pages.submissions.table.date")}</span>
                  <span>{t("pages.submissions.table.status")}</span>
                  <span className="text-right">{t("pages.submissions.table.action")}</span>
                </div>
                <div className="divide-y divide-border">
                  {items.map((item) => (
                    <div key={item.submission_id} className={`grid grid-cols-[minmax(110px,1.05fr)_minmax(120px,1.05fr)_76px_118px_70px_58px] gap-3 px-5 py-4 text-sm ${selectedId === item.submission_id ? "bg-accent/5" : ""}`}>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-text-primary">{item.company || item.submission_id}</p>
                        <p className="mt-1 truncate font-mono text-xs text-text-muted">{item.submission_id}</p>
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-text-primary">{item.position || "--"}</p>
                        <p className="mt-1 truncate text-xs text-text-secondary">{item.mode || "--"}</p>
                      </div>
                      <div className="min-w-0">
                        <span className={`inline-flex max-w-full rounded-chip border px-2 py-0.5 text-xs font-medium ${channelClassName(item.channel)}`}>
                          <span className="truncate">{channelLabel(item, t("pages.submissions.unknownChannel"))}</span>
                        </span>
                      </div>
                      <p className="truncate text-text-secondary">{formatDate(item.submitted_at, i18n.language)}</p>
                      <div>
                        <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(item.status)}`}>
                          {submissionStatusLabel(item.status, t)}
                        </span>
                      </div>
                      <div className="flex justify-end gap-2">
                        <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={detailState === "loading" && selectedId === item.submission_id} onClick={() => void handleSelect(item.submission_id)} title={t("pages.submissions.details")} type="button" aria-label={t("pages.submissions.details")}>
                          <Eye className="h-4 w-4" aria-hidden="true" />
                        </button>
                        <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void handleRetry(item.submission_id)} title={retryingId === item.submission_id ? t("pages.submissions.retrying") : t("common.retry")} type="button" aria-label={retryingId === item.submission_id ? t("pages.submissions.retrying") : t("common.retry")}>
                          <RotateCcw className={`h-4 w-4 ${retryingId === item.submission_id ? "animate-spin" : ""}`} aria-hidden="true" />
                        </button>
                      </div>
                      <div className="col-span-6 grid gap-2 text-xs text-text-secondary md:grid-cols-2">
                        <p className="truncate"><span className="text-text-muted">{t("pages.submissions.lastStep")}</span> {item.last_step.name || "--"} · {item.last_step.status || "--"} · {detailText(item, t("pages.submissions.noDetail"))}</p>
                        <p className="truncate"><span className="text-text-muted">{t("pages.submissions.rateLimit")}</span> {item.rate_limit_status || "--"} · {item.rate_limit_detail || "--"}</p>
                      </div>
                    </div>
                  ))}
                  {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.empty")}</div> : null}
                </div>
              </div>
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.detailTitle")}</h2>
            </div>
            {detailState === "loading" ? <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.loadingDetail")}</div> : null}
            {detailState === "error" ? <div className="p-5 text-sm text-error">{error}</div> : null}
            {detailState === "ready" && detail ? (
              <div className="space-y-5 p-5">
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-text-primary">{detail.submission_id}</p>
                    <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(detail.status)}`}>
                      {submissionStatusLabel(detail.status, t)}
                    </span>
                    {detail.mode ? <span className="rounded-chip border border-border px-2 py-0.5 text-xs text-text-secondary">{detail.mode}</span> : null}
                  </div>
                  <dl className="grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.company")}</dt>
                      <dd className="mt-1 truncate text-text-primary">{detail.company || "--"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.position")}</dt>
                      <dd className="mt-1 truncate text-text-primary">{detail.position || "--"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.channel")}</dt>
                      <dd className="mt-1 text-text-primary">{channelLabel(detail, t("pages.submissions.unknownChannel"))}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.browser")}</dt>
                      <dd className="mt-1 text-text-primary">{detail.browser_channel || "--"}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.submittedAt")}</dt>
                      <dd className="mt-1 text-text-primary">{formatDate(detail.started_at, i18n.language)} → {formatDate(detail.ended_at, i18n.language)}</dd>
                    </div>
                    {detail.job_url ? (
                      <div className="sm:col-span-2">
                        <dt className="text-xs text-text-muted">{t("pages.submissions.fields.jobUrl")}</dt>
                        <dd className="mt-1 break-all font-mono text-xs text-text-secondary">{detail.job_url}</dd>
                      </div>
                    ) : null}
                  </dl>
                </div>
                <div className="grid gap-2 border-t border-border pt-4 text-xs text-text-secondary">
                  <p className="break-all"><span className="text-text-muted">{t("pages.submissions.fields.resume")}</span> {detail.resume_path || "--"}</p>
                  <p className="break-all"><span className="text-text-muted">{t("pages.submissions.fields.profile")}</span> {detail.profile_path || "--"}</p>
                  <p className="break-all"><span className="text-text-muted">JSON</span> {detail.log_json_path || "--"}</p>
                  <p className="break-all"><span className="text-text-muted">YAML</span> {detail.log_yaml_path || "--"}</p>
                </div>
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-text-primary">{t("pages.submissions.timeline")}</h3>
                  <div className="space-y-3">
                    {detail.steps.map((step, index) => (
                      <div key={`${step.name}-${index}`} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
                        <div className="flex flex-col items-center">
                          <span className={`grid h-7 w-7 place-items-center rounded-full border text-[11px] ${statusClassName(step.status)}`}>
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          {index < detail.steps.length - 1 ? <span className="mt-2 h-full min-h-8 w-px bg-border" /> : null}
                        </div>
                        <div className="min-w-0 pb-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-text-primary">{step.name || "--"}</span>
                            <span className={`rounded-chip border px-2 py-0.5 text-xs ${statusClassName(step.status)}`}>{step.status || "--"}</span>
                          </div>
                          <p className="mt-2 break-words text-xs text-text-secondary">{step.detail || "--"}</p>
                        {step.screenshot ? (
                          <p className="mt-2 break-all font-mono text-xs text-text-muted">
                            {step.screenshot_exists ? step.screenshot_path : t("pages.submissions.missingScreenshot", { path: step.screenshot })}
                          </p>
                        ) : null}
                        </div>
                      </div>
                    ))}
                    {detail.steps.length === 0 ? <p className="text-sm text-text-secondary">{t("pages.submissions.noSteps")}</p> : null}
                  </div>
                </div>
                <div className="space-y-3 border-t border-border pt-4">
                  <h3 className="text-sm font-semibold text-text-primary">{t("pages.submissions.screenshots.title")}</h3>
                  {screenshotSteps.length > 0 ? (
                    <div className="grid gap-3">
                      <div className="grid gap-2 sm:grid-cols-2">
                        {screenshotSteps.map((step, index) => (
                          <button key={`${step.screenshot}-${index}`} className={`min-h-20 rounded-card border p-2 text-left hover:bg-bg-hover ${selectedScreenshot?.screenshot_path === step.screenshot_path ? "border-accent bg-accent/10" : "border-border bg-bg-primary/40"}`} disabled={!step.screenshot_exists} onClick={() => setSelectedScreenshotPath(step.screenshot_path)} type="button">
                            <div className="flex items-center gap-2 text-xs text-text-secondary">
                              <ImageIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
                              <span className="truncate">{step.name || step.screenshot}</span>
                            </div>
                            <p className="mt-2 truncate font-mono text-[11px] text-text-muted">{step.screenshot_exists ? step.screenshot : t("pages.submissions.screenshots.missing")}</p>
                          </button>
                        ))}
                      </div>
                      <div className="min-h-[180px] overflow-hidden rounded-card border border-border bg-bg-primary/50">
                        {selectedScreenshot?.screenshot_exists && selectedScreenshot.screenshot_path ? (
                          <img className="h-full max-h-[320px] w-full object-contain" src={screenshotSource(selectedScreenshot.screenshot_path) ?? undefined} alt={selectedScreenshot.name || t("pages.submissions.screenshots.preview")} />
                        ) : (
                          <div className="grid min-h-[180px] place-items-center text-sm text-text-secondary">{t("pages.submissions.screenshots.emptyPreview")}</div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-text-secondary">{t("pages.submissions.screenshots.empty")}</p>
                  )}
                </div>
                <div className="space-y-3 border-t border-border pt-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                    <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />
                    {t("pages.submissions.failure.title")}
                  </h3>
                  <p className="break-words text-sm text-text-secondary">{detail.error || detail.last_step.detail || t("pages.submissions.failure.empty")}</p>
                  <div className="grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
                    <button className="rounded-card border border-border bg-bg-primary/40 p-3 text-left hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void handleRetry(detail.submission_id, "same_channel")} type="button">
                      <p className="flex items-center gap-2 text-text-primary"><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("pages.submissions.retryStrategy.sameChannel")}</p>
                      <p className="mt-1">{detail.channel || t("pages.submissions.unknownChannel")}</p>
                    </button>
                    <button className="rounded-card border border-border bg-bg-primary/40 p-3 text-left hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void handleRetry(detail.submission_id, "fallback_email")} type="button">
                      <p className="flex items-center gap-2 text-text-primary"><Timer className="h-4 w-4" aria-hidden="true" />{t("pages.submissions.retryStrategy.fallbackEmail")}</p>
                      <p className="mt-1">{detail.rate_limit_detail || "--"}</p>
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
            {detailState === "ready" && !detail ? (
              <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.selectRun")}</div>
            ) : null}
          </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
