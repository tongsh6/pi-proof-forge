import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Image as ImageIcon,
  RotateCcw,
  Timer,
} from "lucide-react";
import type { SubmissionDetail } from "@/lib/sidecar/types";
import type { LoadState, RetryStrategy } from "../submissions-helpers";
import {
  channelLabel,
  formatDate,
  screenshotSource,
  statusClassName,
  submissionStatusLabel,
} from "../submissions-helpers";

type ScreenshotStep = { name?: string; screenshot: string; screenshot_path: string; screenshot_exists: boolean };

type SubmissionsDetailPanelProps = {
  detail: SubmissionDetail | null;
  detailState: LoadState;
  error: string | null;
  retryingId: string | null;
  screenshotSteps: ScreenshotStep[];
  selectedScreenshotPath: string | null;
  onSelectScreenshot: (path: string) => void;
  onRetry: (submissionId: string, strategy?: RetryStrategy) => void;
  onOpenApproval: (runId: string) => void;
};

/** 投递详情侧栏：基础信息、时间线、截图、失败原因与重试动作。 */
export function SubmissionsDetailPanel({
  detail,
  detailState,
  error,
  retryingId,
  screenshotSteps,
  selectedScreenshotPath,
  onSelectScreenshot,
  onRetry,
  onOpenApproval,
}: SubmissionsDetailPanelProps) {
  const { t, i18n } = useTranslation();
  const selectedScreenshot = screenshotSteps.find((step) => step.screenshot_path === selectedScreenshotPath) ?? screenshotSteps[0];
  return (
    <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.detailTitle")}</h2>
      </div>
      {detailState === "loading" ? <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.loadingDetail")}</div> : null}
      {detailState === "error" ? <div className="p-5 text-sm text-error">{error}</div> : null}
      {detailState === "ready" && detail ? (
        <div className="space-y-5 p-5">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-base font-semibold text-text-primary">{[detail.company, detail.position].filter(Boolean).join(" · ") || detail.submission_id}</p>
              <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(detail.status)}`}>
                {submissionStatusLabel(detail.status, t)}
              </span>
              {detail.mode ? <span className="rounded-chip border border-border px-2 py-0.5 text-xs text-text-secondary">{t(`codes.mode.${detail.mode}`, { defaultValue: detail.mode })}</span> : null}
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
                <dd className="mt-1 text-text-primary">{t(`codes.platform.${detail.channel}`, { defaultValue: channelLabel(detail, t("pages.submissions.unknownChannel")) })}</dd>
              </div>
              <div>
                <dt className="text-xs text-text-muted">{t("pages.submissions.fields.browser")}</dt>
                <dd className="mt-1 text-text-primary">{detail.browser_channel ? t(`codes.browser.${detail.browser_channel}`, { defaultValue: detail.browser_channel }) : "--"}</dd>
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
            {detail.resume_version_id ? <p>{t("pages.submissions.checkMode.resumeVersion")}: {detail.resume_version_id}</p> : null}
            {detail.evidence?.status && <>
              <p role="status">{t(`pages.submissions.evidence.${detail.evidence.status}`)}</p>
              <p>{t(`pages.submissions.evidence.${detail.evidence.delivery_kind}`, {defaultValue: "--"})} · {t(`pages.submissions.evidence.${detail.evidence.receipt_source}`, {defaultValue: "--"})}</p>
              <p className="break-all">{t("pages.submissions.evidence.resumeHash")}: {detail.evidence.resume_sha256 || "--"}</p>
              <p className="break-all">{t("pages.submissions.evidence.receiptHash")}: {detail.evidence.receipt_sha256 || "--"}</p>
            </>}

            {detail.parent_run_id ? <button type="button" className="text-accent underline" onClick={() => onOpenApproval(detail.parent_run_id ?? "")}>{t("pages.submissions.openApproval")}</button> : null}
            <details>
              <summary className="cursor-pointer select-none text-text-muted">{t("pages.submissions.technicalDetails")}</summary>
              <div className="mt-2 grid gap-2">
                <p className="break-all"><span className="text-text-muted">ID</span> {detail.submission_id}</p>
                <p className="break-all"><span className="text-text-muted">{t("pages.submissions.fields.resume")}</span> {detail.resume_path || "--"}</p>
                <p className="break-all"><span className="text-text-muted">{t("pages.submissions.fields.profile")}</span> {detail.profile_path || "--"}</p>
                <p className="break-all"><span className="text-text-muted">JSON</span> {detail.log_json_path || "--"}</p>
                <p className="break-all"><span className="text-text-muted">YAML</span> {detail.log_yaml_path || "--"}</p>
              </div>
            </details>
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
                      <span className="text-sm font-medium text-text-primary">{step.name ? t(`codes.steps.${step.name}`, { defaultValue: step.name }) : "--"}</span>
                      <span className={`rounded-chip border px-2 py-0.5 text-xs ${statusClassName(step.status)}`}>{step.status || "--"}</span>
                    </div>
                    {/^\s*[{[]/.test(step.detail || "") ? (
                      <details className="mt-2 text-xs text-text-secondary">
                        <summary className="cursor-pointer select-none">{t("pages.submissions.detail.receiptReceived")}</summary>
                        <p className="mt-1 break-words font-mono">{step.detail}</p>
                      </details>
                    ) : (
                      <p className="mt-2 break-words text-xs text-text-secondary">{step.detail || "--"}</p>
                    )}
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
                    <button key={`${step.screenshot}-${index}`} className={`min-h-20 rounded-card border p-2 text-left hover:bg-bg-hover ${selectedScreenshot?.screenshot_path === step.screenshot_path ? "border-accent bg-accent/10" : "border-border bg-bg-primary/40"}`} disabled={!step.screenshot_exists} onClick={() => onSelectScreenshot(step.screenshot_path)} type="button">
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
            <p className="break-words text-sm text-text-secondary">{detail.error || (/^\s*[{[]/.test(detail.last_step.detail || "") ? "" : detail.last_step.detail) || t("pages.submissions.failure.empty")}</p>
            <div className="grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
              <button className="rounded-card border border-border bg-bg-primary/40 p-3 text-left hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null || detail.retry_allowed === false} onClick={() => onRetry(detail.submission_id, "same_channel")} type="button">
                <p className="flex items-center gap-2 text-text-primary"><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("pages.submissions.retryStrategy.sameChannel")}</p>
                <p className="mt-1">{detail.channel || t("pages.submissions.unknownChannel")}</p>
              </button>
              <button className="rounded-card border border-border bg-bg-primary/40 p-3 text-left hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null || detail.retry_allowed === false} onClick={() => onRetry(detail.submission_id, "fallback_email")} type="button">
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
  );
}
