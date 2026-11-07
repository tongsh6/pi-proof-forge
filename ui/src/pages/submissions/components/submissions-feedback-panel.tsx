import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import type {
  FeedbackIterationResult,
  FeedbackListResult,
  SubmissionListItem,
} from "@/lib/sidecar/types";
import type { LoadState } from "../submissions-helpers";
import { formatDate } from "../submissions-helpers";

type SubmissionsFeedbackPanelProps = {
  feedbackState: LoadState;
  feedbackRunId: string;
  feedbackList: FeedbackListResult | null;
  feedbackIteration: FeedbackIterationResult | null;
  managedFeedback: boolean;
  feedbackNotes: string;
  feedbackSource: "user_note" | "manual_recruiter";
  feedbackAction: string;
  selectedId: string | null;
  items: SubmissionListItem[];
  error: string | null;
  onNotesChange: (value: string) => void;
  onSourceChange: (value: "user_note" | "manual_recruiter") => void;
  onActionChange: (value: string) => void;
  onSelect: (submissionId: string) => void;
  onCreateFeedbackIteration: () => void;
  onNavigate: (path: string) => void;
};

/** 投递反馈区：选择记录、来源/动作、备注与历史迭代。 */
export function SubmissionsFeedbackPanel({
  feedbackState,
  feedbackRunId,
  feedbackList,
  feedbackIteration,
  managedFeedback,
  feedbackNotes,
  feedbackSource,
  feedbackAction,
  selectedId,
  items,
  error,
  onNotesChange,
  onSourceChange,
  onActionChange,
  onSelect,
  onCreateFeedbackIteration,
  onNavigate,
}: SubmissionsFeedbackPanelProps) {
  const { t, i18n } = useTranslation();
  return (
    <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.feedback.title")}</h2>
          <p className="mt-1 text-sm text-text-secondary">{t("pages.submissions.feedback.boundary")}</p>
        </div>
        <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={feedbackState === "loading" || !feedbackRunId || !feedbackList || (managedFeedback && !feedbackNotes.trim())} onClick={onCreateFeedbackIteration} type="button">
          <RotateCcw className={`h-4 w-4 ${feedbackState === "loading" ? "animate-spin" : ""}`} aria-hidden="true" />
          {feedbackState === "loading" ? t("pages.submissions.feedback.recording") : t("pages.submissions.feedback.create")}
        </button>
      </div>
      <label className="mt-4 block text-sm text-text-secondary">
        {t("pages.submissions.feedback.submission")}
        <select aria-label={t("pages.submissions.feedback.submission")} className="mt-1 w-full rounded-card border border-border bg-bg-primary p-2 text-text-primary"
          value={selectedId || ""} disabled={feedbackState === "loading"} onChange={event => { if (event.target.value) onSelect(event.target.value); }}>
          <option value="">{t("pages.submissions.feedback.chooseSubmission")}</option>
          {items.map(item => <option key={item.submission_id} value={item.submission_id}>{item.company || item.submission_id} · {item.position || "--"} · {formatDate(item.submitted_at, i18n.language)}</option>)}
        </select>
      </label>
      {managedFeedback && <div className="mt-3 space-y-3 text-sm">
        <p className="break-all text-text-secondary">{t("pages.submissions.checkMode.resumeVersion")}: {feedbackList?.source_binding?.resume_version_id || "--"}</p>
        <div className="grid gap-3 md:grid-cols-2">
          <label>{t("pages.submissions.feedback.source")}<select aria-label={t("pages.submissions.feedback.source")} className="mt-1 w-full rounded-card border border-border bg-bg-primary p-2"
            value={feedbackSource} onChange={event => onSourceChange(event.target.value as "user_note" | "manual_recruiter")}>
            <option value="user_note">{t("pages.submissions.feedback.sources.user_note")}</option><option value="manual_recruiter">{t("pages.submissions.feedback.sources.manual_recruiter")}</option>
          </select></label>
          <label>{t("pages.submissions.feedback.action")}<select aria-label={t("pages.submissions.feedback.action")} className="mt-1 w-full rounded-card border border-border bg-bg-primary p-2"
            value={feedbackAction} onChange={event => onActionChange(event.target.value)}>
            {(feedbackList?.supported_actions || []).map(action => <option key={action} value={action}>{t(`pages.submissions.feedback.actions.${action}`)}</option>)}
          </select></label>
        </div>
        <label className="block">{t("pages.submissions.feedback.notes")}<textarea aria-label={t("pages.submissions.feedback.notes")} maxLength={4000}
          className="mt-1 min-h-24 w-full rounded-card border border-border bg-bg-primary p-2" value={feedbackNotes} onChange={event => onNotesChange(event.target.value)} /></label>
        <p className="text-xs text-text-muted">{t("pages.submissions.feedback.planOnly")}</p>
      </div>}
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
      <details className="mt-3 text-xs text-text-secondary">
        <summary className="cursor-pointer select-none text-text-muted">{t("pages.submissions.technicalDetails")}</summary>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <p className="break-all"><span className="text-text-muted">{t("pages.submissions.feedback.record")}</span> {feedbackIteration?.record_path || "--"}</p>
          <p className="break-all"><span className="text-text-muted">{t("pages.submissions.feedback.snapshot")}</span> {feedbackIteration?.iteration.source_snapshot_path || "--"}</p>
        </div>
      </details>
      {(feedbackList?.iterations || []).map(record => <article key={record.iteration_id} className="mt-3 rounded-card border border-border p-3 text-sm">
        <p className="text-xs text-text-muted">{formatDate(record.created_at, i18n.language)} · {t(`pages.submissions.feedback.sources.${record.feedback_source || "user_note"}`)}</p>
        <p className="mt-2 whitespace-pre-wrap break-words">{record.user_notes}</p>
        <p className="mt-2 text-text-secondary">{record.selected_actions.map(action => t(`pages.submissions.feedback.actions.${action}`, {defaultValue:action})).join(" · ")}</p>
        {record.next_quick_run_candidate?.job_profile_id && <p className="mt-2 text-xs text-text-secondary">{t("pages.submissions.feedback.targetProfile")}: {record.next_quick_run_candidate.job_profile_id}</p>}
        {record.next_recommended_step === "quick_run" && <button type="button" onClick={() => onNavigate("/quick-run")} className="mt-2 inline-block text-accent underline">{t("pages.submissions.feedback.openQuickRun")}</button>}
        {record.next_recommended_step === "evidence" && <button type="button" onClick={() => onNavigate("/evidence")} className="mt-2 inline-block text-accent underline">{t("pages.submissions.feedback.openEvidence")}</button>}
        {record.next_recommended_step === "jobs" && <button type="button" onClick={() => onNavigate("/jobs")} className="mt-2 inline-block text-accent underline">{t("pages.submissions.feedback.openJobs")}</button>}
      </article>)}
      {feedbackState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
    </section>
  );
}
