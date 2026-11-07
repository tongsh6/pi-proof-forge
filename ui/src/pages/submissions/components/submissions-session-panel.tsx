import { useTranslation } from "react-i18next";
import { RefreshCw, Send, ShieldCheck, Trash2 } from "lucide-react";
import type { ChannelSessionResult, SubmissionCheckModeResult } from "@/lib/sidecar/types";
import type { LoadState } from "../submissions-helpers";
import { defaultSubmissionChannel, formatDate, statusClassName } from "../submissions-helpers";

type SubmissionsSessionPanelProps = {
  channelSession: ChannelSessionResult | null;
  sessionState: LoadState;
  selectedChannel: string;
  sessionAction: string | null;
  error: string | null;
  onSelectedChannelChange: (channel: string) => void;
  onStartSession: () => void;
  onCheckSession: () => void;
  onClearSession: () => void;
};

/** 高级工具：投递渠道登录会话的手动开始/检查/清除。 */
export function SubmissionsSessionPanel({
  channelSession,
  sessionState,
  selectedChannel,
  sessionAction,
  error,
  onSelectedChannelChange,
  onStartSession,
  onCheckSession,
  onClearSession,
}: SubmissionsSessionPanelProps) {
  const { t, i18n } = useTranslation();
  return (
    <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.session.title")}</h2>
          <p className="mt-1 text-sm text-text-secondary" title={t("pages.submissions.session.manualBoundary")}>{t("pages.submissions.session.manualBoundaryShort")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="h-9 rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={selectedChannel} onChange={(event) => onSelectedChannelChange(event.target.value)} aria-label={t("pages.submissions.session.channel")}>
            {(channelSession?.supported_channels ?? [{ channel: defaultSubmissionChannel, label: "Liepin", login_url: "" }]).map((channel) => (
              <option key={channel.channel} value={channel.channel}>{channel.label}</option>
            ))}
          </select>
          <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null} onClick={onStartSession} type="button">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {sessionAction === "start" ? t("pages.submissions.session.starting") : t("pages.submissions.session.start")}
          </button>
          <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null} onClick={onCheckSession} type="button">
            <RefreshCw className={`h-4 w-4 ${sessionAction === "check" ? "animate-spin" : ""}`} aria-hidden="true" />
            {t("pages.submissions.session.check")}
          </button>
          <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null || !channelSession?.session.clear_available} onClick={onClearSession} title={t("pages.submissions.session.clear")} type="button" aria-label={t("pages.submissions.session.clear")}>
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
      <details className="mt-3 text-xs text-text-secondary">
        <summary className="cursor-pointer select-none text-text-muted">{t("pages.submissions.technicalDetails")}</summary>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <p className="break-all"><span className="text-text-muted">{t("pages.submissions.session.path")}</span> {channelSession?.session.session_path || "--"}</p>
          <p className="break-all"><span className="text-text-muted">{t("pages.submissions.session.log")}</span> {channelSession?.artifact_paths.session_check_log || "--"}</p>
        </div>
      </details>
      {sessionState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
    </section>
  );
}

type SubmissionsCheckModePanelProps = {
  channelSession: ChannelSessionResult | null;
  checkModeState: LoadState;
  checkModeForm: { jobLeadId: string; resumeVersionId: string; resumePdfPath: string };
  checkModeResult: SubmissionCheckModeResult | null;
  error: string | null;
  onFormChange: (updater: (current: { jobLeadId: string; resumeVersionId: string; resumePdfPath: string }) => { jobLeadId: string; resumeVersionId: string; resumePdfPath: string }) => void;
  onStartCheckMode: () => void;
};

/** 高级工具：试运行检查模式（不真正投递）。 */
export function SubmissionsCheckModePanel({
  channelSession,
  checkModeState,
  checkModeForm,
  checkModeResult,
  error,
  onFormChange,
  onStartCheckMode,
}: SubmissionsCheckModePanelProps) {
  const { t } = useTranslation();
  return (
    <details className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
      <summary className="cursor-pointer select-none px-5 py-4 text-lg font-semibold text-text-primary">
        {t("pages.submissions.checkMode.title")}
        <span className="ml-2 text-xs font-normal text-text-muted">{t("pages.submissions.checkMode.collapsedHint")}</span>
      </summary>
      <div className="px-5 pb-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-text-secondary">{t("pages.submissions.checkMode.boundary")}</p>
        </div>
        <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={checkModeState === "loading" || channelSession?.session.login_status !== "session_valid" || !checkModeForm.jobLeadId.trim() || !checkModeForm.resumeVersionId.trim() || !checkModeForm.resumePdfPath.trim()} onClick={onStartCheckMode} type="button">
          <Send className="h-4 w-4" aria-hidden="true" />
          {checkModeState === "loading" ? t("pages.submissions.checkMode.running") : t("pages.submissions.checkMode.start")}
        </button>
      </div>
      <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
        <label className="space-y-1">
          <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.jobLead")}</span>
          <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.jobLeadId} onChange={(event) => onFormChange((current) => ({ ...current, jobLeadId: event.target.value }))} placeholder={t("pages.submissions.checkMode.jobLeadPlaceholder")} />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.resumeVersion")}</span>
          <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.resumeVersionId} onChange={(event) => onFormChange((current) => ({ ...current, resumeVersionId: event.target.value }))} placeholder={t("pages.submissions.checkMode.resumeVersionPlaceholder")} />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.resume")}</span>
          <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.resumePdfPath} onChange={(event) => onFormChange((current) => ({ ...current, resumePdfPath: event.target.value }))} placeholder={t("pages.submissions.checkMode.resumePathPlaceholder")} />
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
      </div>
    </details>
  );
}

