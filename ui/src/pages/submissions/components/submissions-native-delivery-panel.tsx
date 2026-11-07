import { useTranslation } from "react-i18next";
import { PdfQualitySummary } from "@/components/pdf-quality-summary";
import { QualityReportPanel } from "@/components/quality-report";
import type { NativeLiepinObservation, NativePdfPreparation } from "@/lib/sidecar/api";
import type { FeedbackSyncResult } from "@/lib/sidecar/api";
import { buttonClass } from "@/lib/ui";
import type { QuickRunOption } from "../submissions-helpers";
import { PDF_STEPS } from "../submissions-helpers";

type SubmissionsNativeDeliveryPanelProps = {
  nativeSession: string;
  nativeSessionBusy: boolean;
  feedbackSync: FeedbackSyncResult | undefined;
  nativeAttachmentView: NativeLiepinObservation["attachment_view"];
  pdfStep: number;
  pdfQuickRunId: string;
  quickRunOptions: QuickRunOption[];
  nativePdf: NativePdfPreparation | null;
  nativePdfError: string;
  nativePdfPreview: string;
  previewedPdf: string;
  acceptPdfEffects: boolean;
  acceptAttachmentRemoval: boolean;
  autoAdvanceAvailable: boolean;
  autoAdvanceNotice: { text: string; tone: "success" | "warning" } | null;
  quotaBlocked: boolean;
  quotaReached: boolean;
  quotaCleaned: boolean;
  visibleUploadHints: string[];
  cleanupBusy: boolean;
  cleanupNotice: string;
  qualityDecisionNotice: string;
  existingPreparedRun: { quick: string; pdf: string } | null;
  onNativeSession: (action: "open" | "check" | "inspect") => void;
  onFeedbackSync: () => void;
  onCleanupOldAttachments: () => void;
  onDiagnoseAttachments: () => void;
  onPdfQuickRunChange: (value: string) => void;
  onPreparePdf: () => void;
  onDecideHighlight: (highlightId: string, action: "reject" | "select") => void;
  onAcceptPdfEffectsChange: (checked: boolean) => void;
  onAcceptAttachmentRemovalChange: (checked: boolean) => void;
  onAutoAdvance: () => void;
  onConfirmFinalSend: () => void;
  onCleanupQuotaAndRetry: () => void;
  onNativePdf: (action: "authorizeSingle" | "preview" | "prepare" | "upload" | "inspect" | "target" | "communicate" | "inspectChat" | "prepareResume" | "send" | "receipt" | "remove" | "recheckRemoval") => void;
  onReuploadMissing: () => void;
  onLoadExistingPrepared: () => void;
  onNavigate: (path: string) => void;
};

/** 投递标签页：原生会话状态、PDF 投递步骤、质量报告与投递动作。 */
export function SubmissionsNativeDeliveryPanel({
  nativeSession,
  nativeSessionBusy,
  feedbackSync,
  nativeAttachmentView,
  pdfStep,
  pdfQuickRunId,
  quickRunOptions,
  nativePdf,
  nativePdfError,
  nativePdfPreview,
  previewedPdf,
  acceptPdfEffects,
  acceptAttachmentRemoval,
  autoAdvanceAvailable,
  autoAdvanceNotice,
  quotaBlocked,
  quotaReached,
  quotaCleaned,
  visibleUploadHints,
  cleanupBusy,
  cleanupNotice,
  qualityDecisionNotice,
  existingPreparedRun,
  onNativeSession,
  onFeedbackSync,
  onCleanupOldAttachments,
  onDiagnoseAttachments,
  onPdfQuickRunChange,
  onPreparePdf,
  onDecideHighlight,
  onAcceptPdfEffectsChange,
  onAcceptAttachmentRemovalChange,
  onAutoAdvance,
  onConfirmFinalSend,
  onCleanupQuotaAndRetry,
  onNativePdf,
  onReuploadMissing,
  onLoadExistingPrepared,
  onNavigate,
}: SubmissionsNativeDeliveryPanelProps) {
  const { t } = useTranslation();
  return (
    <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.nativeSession.title")}</h2>
        <div className="flex gap-2">
          <button type="button" disabled={nativeSessionBusy} onClick={() => onNativeSession("open")}
            className="rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50">{t("pages.submissions.nativeSession.open")}</button>
          <button type="button" disabled={nativeSessionBusy} onClick={() => onNativeSession("check")}
            className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50">{t("pages.submissions.nativeSession.check")}</button>
          <button type="button" disabled={nativeSessionBusy || nativeSession !== "authenticated"} onClick={() => onNativeSession("inspect")}
            className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50">{t("pages.submissions.nativeSession.inspect")}</button>
          <button type="button" disabled={nativeSessionBusy || nativeSession !== "authenticated"} onClick={onFeedbackSync}
            className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50">{t("pages.submissions.platformFeedback.sync")}</button>
        </div>
      </div>
      <div className="mt-2 text-sm text-text-secondary">{t("pages.submissions.nativeSession.boundaryShort")}<details className="mt-1 text-xs text-text-muted"><summary className="cursor-pointer select-none text-accent">{t("common.learnMore")}</summary><p className="mt-1">{t("pages.submissions.nativeSession.boundary")}</p></details></div>
      <p className="mt-2 text-sm text-text-primary" role="status">{t(`pages.submissions.nativeSession.status.${nativeSession}`, {defaultValue:t("pages.submissions.nativeSession.status.unavailable")})}</p>
      <p className="mt-2 text-xs text-text-secondary" title={t("pages.submissions.platformFeedback.boundary")}>{t("pages.submissions.platformFeedback.boundaryShort")}</p>
      {feedbackSync && <p role="status" className="mt-2 text-sm text-text-primary">{feedbackSync.status === "records"
        ? t("pages.submissions.platformFeedback.summary", {matched: feedbackSync.matched.length, total: feedbackSync.submissions_total, unmatched: feedbackSync.unmatched_rows})
        : t("pages.submissions.platformFeedback.notFound")}</p>}
      {nativeAttachmentView && <div className="mt-3 text-sm text-text-secondary">
        <p>{t("pages.submissions.nativeSession.attachmentInputs", {count:nativeAttachmentView.inputs.length})}</p>
        {nativeAttachmentView.inputs.map((input, i) => <p key={`input-${i}`}>{input.accept || t("pages.submissions.nativeSession.acceptUnknown")}</p>)}
        {nativeAttachmentView.hints.map((hint, i) => <p key={`hint-${i}`}>{hint}</p>)}
      </div>}
      <div className="mt-4 border-t border-border pt-4 text-sm">
        <ol className="mb-4 flex flex-wrap items-center gap-2" aria-label={t("pages.submissions.nativePdf.stepsTitle")} data-testid="native-pdf-steps">
          {PDF_STEPS.map((step, index) => {
            const state = index < pdfStep ? "done" : index === pdfStep ? "current" : "pending";
            return (
              <li
                key={step}
                aria-current={state === "current" ? "step" : undefined}
                className={`inline-flex items-center gap-1.5 rounded-chip border px-2.5 py-1 text-xs ${
                  state === "done"
                    ? "border-success/40 bg-success/10 text-success"
                    : state === "current"
                      ? "border-accent bg-accent/10 font-medium text-accent"
                      : "border-border text-text-muted"
                }`}
              >
                <span className="font-mono">{String(index + 1).padStart(2, "0")}</span>
                {t(`pages.submissions.nativePdf.steps.${step}`)}
              </li>
            );
          })}
        </ol>
        <details className="mb-3 rounded-card border border-border bg-bg-primary/30 p-3">
          <summary className="cursor-pointer select-none text-xs text-text-secondary">附件维护（移除旧附件）</summary>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" disabled={nativeSessionBusy || cleanupBusy} onClick={()=>void onCleanupOldAttachments()}
              className={buttonClass.danger}>移除旧的 App 生成附件</button>
            <button type="button" disabled={nativeSessionBusy || cleanupBusy} onClick={()=>void onDiagnoseAttachments()}
              className={buttonClass.secondary}>诊断附件入口</button>
          </div>
          {cleanupNotice && <p role="status" className="mt-2 text-xs text-text-secondary">{cleanupNotice}</p>}
        </details>
        <label className="block text-text-secondary">{t("pages.submissions.nativePdf.selectQuickRun", {defaultValue:"选择最近生成的简历 PDF"})}
          <select aria-label={t("pages.submissions.nativePdf.selectQuickRun", {defaultValue:"选择最近生成的简历 PDF"})} value={pdfQuickRunId} disabled={nativeSessionBusy}
            onChange={event=>onPdfQuickRunChange(event.target.value)}
            className="mt-1 w-full rounded-card border border-border bg-bg-primary px-3 py-2 text-text-primary">
            <option value="">{t("pages.submissions.nativePdf.selectQuickRunPlaceholder", {defaultValue:"自动选择最近一次生成的 PDF"})}</option>
            {quickRunOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            {pdfQuickRunId && !quickRunOptions.some((option) => option.id === pdfQuickRunId) &&
              <option value={pdfQuickRunId}>{t("pages.submissions.nativePdf.currentLinkedRun", {defaultValue:"当前链接任务"})}</option>}
          </select>
        </label>
        <button type="button" disabled={nativeSessionBusy || !pdfQuickRunId.trim()} onClick={onPreparePdf}
          className={`mt-2 ${buttonClass.secondary}`}>{t("pages.submissions.nativePdf.prepare")}</button>
        {nativePdf && <div className="mt-3 space-y-2">
          <p>{nativePdf.company} · {nativePdf.position}</p>
          <PdfQualitySummary quality={nativePdf.quality}/>
          {nativePdf.quality?.quality_report&&<QualityReportPanel report={nativePdf.quality.quality_report} onHighlightDecision={onDecideHighlight}/>}
          {qualityDecisionNotice&&<p role="status" className="text-xs text-text-secondary">{qualityDecisionNotice}</p>}
          {nativePdf.pdf_filename&&<p className="break-all">PDF: {nativePdf.pdf_filename}</p>}
          <p className="font-mono text-xs text-text-muted" title={nativePdf.pdf_sha256}>{t("pages.submissions.pdfFingerprint")}: {nativePdf.pdf_sha256?.slice(0, 12)}…</p>
          <p role="status">{t(`pages.submissions.nativePdf.phase.${nativePdf.phase}`, {defaultValue:nativePdf.phase})}</p>
          {nativePdf.ai_disclosure_enabled&&<p className="text-xs text-text-secondary" data-testid="native-pdf-ai-disclosure">
            {nativePdf.ai_disclosure_sent
              ? t("pages.submissions.nativePdf.aiDisclosureSent")
              : t("pages.submissions.nativePdf.aiDisclosurePending")}
            {nativePdf.ai_disclosure_text&&<span className="mt-1 block text-text-muted" title={nativePdf.ai_disclosure_text}>{nativePdf.ai_disclosure_text}</span>}
          </p>}
          {nativePdf.single_delivery_authorized&&<p>{t("pages.submissions.nativePdf.singleAuthorized")}</p>}
          {nativePdf.verification_error&&<p role="alert" className="text-warning">{t("pages.submissions.nativePdf.verificationPending")}</p>}
          {nativePdf.recovery_only&&<p role="status" className="text-warning">{t('pages.submissions.nativePdf.recoveryOnly')}</p>}
          <div className="flex flex-wrap gap-2">
            {nativePdf.phase === "prepared" && <button type="button" disabled={nativeSessionBusy} className={buttonClass.secondary}
              onClick={() => onNavigate("/agent-run")}>{t("pages.submissions.nativePdf.dailyCandidates")}</button>}
            <button type="button" disabled={nativeSessionBusy} onClick={()=>onNativePdf('preview')} className={buttonClass.secondary}>{t('pages.submissions.nativePdf.preview')}</button>
            <button type="button" data-testid="pdf-auto-advance" title={t("pages.submissions.nativePdf.autoAdvanceHint")}
              disabled={nativeSessionBusy || !autoAdvanceAvailable} onClick={onAutoAdvance} className={buttonClass.primary}>
              {t("pages.submissions.nativePdf.autoAdvance")}</button>
            {nativePdf.can_confirm_send && !nativePdf.recovery_only && <button type="button" data-testid="pdf-final-confirm" disabled={nativeSessionBusy}
              onClick={onConfirmFinalSend} className={buttonClass.primary}>{t('pages.submissions.nativePdf.send')}</button>}
            {nativePdf.phase === "final_send_pending" && <button type="button" disabled={nativeSessionBusy}
              onClick={()=>onNativePdf("receipt")} className={buttonClass.primary}>{t("pages.submissions.nativePdf.receipt")}</button>}
          </div>
          <p className="text-xs text-text-muted">{t("pages.submissions.nativePdf.autoAdvanceHint")}</p>
          {nativePdfPreview&&<iframe title={t('pages.submissions.nativePdf.preview')} src={nativePdfPreview} className="h-[650px] w-full rounded-card border border-border bg-white"/>}
          <label className="flex items-start gap-2 text-text-secondary">
            <input type="checkbox" aria-label={t("pages.submissions.nativePdf.consent")} checked={acceptPdfEffects} disabled={nativeSessionBusy || nativePdf.recovery_only || previewedPdf!==nativePdf.run_id || !["prepared","not_submitted"].includes(nativePdf.phase)}
              onChange={event=>onAcceptPdfEffectsChange(event.target.checked)} /><span>{t("pages.submissions.nativePdf.consentShort")}<details className="mt-1 text-xs text-text-muted"><summary className="cursor-pointer select-none text-accent">{t("common.fullTerms")}</summary><p className="mt-1">{t("pages.submissions.nativePdf.consent")}</p></details></span>
          </label>
          {autoAdvanceNotice && <p role="status" data-testid="pdf-auto-advance-notice"
            className={`text-sm ${autoAdvanceNotice.tone === "success" ? "text-success" : "text-warning"}`}>{autoAdvanceNotice.text}</p>}
          {(nativePdf.phase === "not_submitted" || nativePdf.phase === "unknown") && <div data-testid="pdf-upload-hints"
            className={`rounded-card border p-3 text-xs ${nativePdf.phase === "unknown" || nativePdf.can_retry_upload === false ? "border-error/40 bg-error/10" : "border-warning/40 bg-warning/10"}`}>
            <p role="status" className={`text-sm font-medium ${nativePdf.phase === "unknown" || nativePdf.can_retry_upload === false ? "text-error" : "text-warning"}`}>
              {nativePdf.phase === "unknown" || nativePdf.can_retry_upload === false
                ? t("pages.submissions.nativePdf.uploadUnknownNoRetry")
                : t("pages.submissions.nativePdf.uploadNotSubmittedRetry")}</p>
            {quotaBlocked && <div className="mt-2 rounded-card border border-error/40 bg-error/10 p-3">
              <p role="alert" className="text-sm font-medium text-error">{t("pages.submissions.nativePdf.quotaReached")}</p>
              <button type="button" disabled={nativeSessionBusy || cleanupBusy}
                onClick={onCleanupQuotaAndRetry} className={`mt-2 ${buttonClass.secondary}`}>
                {t("pages.submissions.nativePdf.quotaCleanupAction")}</button>
            </div>}
            {quotaReached && quotaCleaned && <p role="status" className="mt-2 text-xs text-success">{t("pages.submissions.nativePdf.quotaCleanupDone")}</p>}
            {visibleUploadHints.length > 0 && <>
              <p className="mt-2 text-text-secondary">{t("pages.submissions.nativePdf.uploadHintsTitle")}</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-text-secondary">
                {visibleUploadHints.map((hint, index) => <li key={`upload-hint-${index}`} className="break-words">{hint}</li>)}
              </ul>
            </>}
            {typeof nativePdf.upload_attempts === "number" && nativePdf.upload_attempts > 0 &&
              <p className="mt-2 text-text-muted">{t("pages.submissions.nativePdf.uploadAttemptsLabel")} {nativePdf.upload_attempts}</p>}
            {quotaBlocked && <p className="mt-2 text-xs text-text-muted">{t("pages.submissions.nativePdf.quotaCleanupHint")}</p>}
          </div>}
          <details className="mt-2 rounded-card border border-border bg-bg-primary/30 p-3">
            <summary className="cursor-pointer select-none text-xs text-text-secondary">{t("pages.submissions.nativePdf.moreActions", {defaultValue:"高级操作（诊断/重试）"})}</summary>
            <p className="mt-2 text-xs text-text-muted">{t("pages.submissions.nativePdf.moreActionsHint")}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={nativeSessionBusy || ["prepared","final_send_pending"].includes(nativePdf.phase)}
                onClick={()=>onNativePdf("inspect")} className={buttonClass.secondary}>{t("pages.submissions.nativePdf.inspect")}</button>
              <button type="button" disabled={nativeSessionBusy || nativePdf.phase !== "attachment_verified"}
                onClick={()=>onNativePdf("target")} className={buttonClass.secondary}>{t("pages.submissions.nativePdf.target")}</button>
              <button type="button" disabled={nativeSessionBusy || !["communication_started","resume_interaction_pending","final_send_pending"].includes(nativePdf.phase)}
                onClick={()=>onNativePdf("inspectChat")} className={buttonClass.secondary}>{t("pages.submissions.nativePdf.inspectChat")}</button>
              <button type="button" disabled={nativeSessionBusy || !["final_send_pending","success"].includes(nativePdf.phase)}
                onClick={()=>onNativePdf("receipt")} className={buttonClass.secondary}>{t("pages.submissions.nativePdf.receipt")}</button>
            </div>
          </details>
          {nativePdf.phase === "success" && nativePdf.platform_filename && <div className="mt-3 border-t border-border pt-3">
            <p className="break-all">{t("pages.submissions.nativePdf.platformFile")}: {nativePdf.platform_filename}</p>
            <p className="text-xs text-text-secondary">{t("pages.submissions.nativePdf.removeBoundary")}</p>
            {nativePdf.platform_attachment_state === "missing_on_platform" && nativePdf.attachment_removal_state !== "removed" && <p role="status" className="text-warning">{t("pages.submissions.nativePdf.platformMissing")}</p>}
            <label className="mt-2 flex items-center gap-2"><input type="checkbox" aria-label={t("pages.submissions.nativePdf.removeConsent")}
              checked={acceptAttachmentRemoval} disabled={nativeSessionBusy || nativePdf.platform_attachment_state === "missing_on_platform" || ["in_flight","unknown","removed"].includes(nativePdf.attachment_removal_state || "")}
              onChange={event=>onAcceptAttachmentRemovalChange(event.target.checked)} />{t("pages.submissions.nativePdf.removeConsent")}</label>
            <button type="button" disabled={nativeSessionBusy || !acceptAttachmentRemoval || nativePdf.platform_attachment_state === "missing_on_platform" || ["in_flight","unknown","removed"].includes(nativePdf.attachment_removal_state || "")}
              onClick={()=>onNativePdf("remove")} className={`mt-2 ${buttonClass.danger}`}>{t("pages.submissions.nativePdf.remove")}</button>
            {nativePdf.attachment_removal_state === "unknown" && <button type="button" disabled={nativeSessionBusy}
              onClick={()=>onNativePdf("recheckRemoval")} className={`ml-2 ${buttonClass.secondary}`}>{t("pages.submissions.nativePdf.recheckRemoval")}</button>}
            {nativePdf.attachment_removal_state && <p role="status">{t(`pages.submissions.nativePdf.removal.${nativePdf.attachment_removal_state}`)}</p>}
          </div>}

        </div>}
        {nativePdfError && <p role="alert" className="mt-2 text-sm text-error">{nativePdfError}</p>}
        {nativePdf?.can_reupload_attachment && !nativePdf.recovery_only && <div role="status" data-testid="pdf-reupload-missing"
          className="mt-2 rounded-card border border-warning/40 bg-warning/10 p-3 text-sm">
          <p className="font-medium text-warning">{t("pages.submissions.nativePdf.reuploadMissingTitle")}</p>
          <p className="mt-1 text-text-secondary">{t("pages.submissions.nativePdf.reuploadMissingHint")}</p>
          <button type="button" disabled={nativeSessionBusy} onClick={onReuploadMissing}
            className={`mt-2 ${buttonClass.primary}`}>{t("pages.submissions.nativePdf.reuploadMissingAction")}</button>
        </div>}
        {existingPreparedRun && <div role="status" data-testid="pdf-existing-prepared"
          className="mt-2 rounded-card border border-warning/40 bg-warning/10 p-3 text-sm">
          <p className="text-warning">{t("pages.submissions.nativePdf.existingPreparedHint", {
            quick: existingPreparedRun.quick, pdf: existingPreparedRun.pdf || "--"})}</p>
          <button type="button" disabled={nativeSessionBusy} onClick={onLoadExistingPrepared}
            className={`mt-2 ${buttonClass.secondary}`}>{t("pages.submissions.nativePdf.loadPreparedPdf")}</button>
        </div>}
      </div>
    </section>
  );
}
