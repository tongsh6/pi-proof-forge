
import { SubmissionsDetailPanel } from "./components/submissions-detail-panel";
import { SubmissionsFeedbackPanel } from "./components/submissions-feedback-panel";
import { SubmissionsNativeDeliveryPanel } from "./components/submissions-native-delivery-panel";
import { SubmissionsPageHeader } from "./components/submissions-page-header";
import { SubmissionsRunsPanel, SubmissionsStatsStrip } from "./components/submissions-records-panel";
import { SubmissionsCheckModePanel, SubmissionsSessionPanel } from "./components/submissions-session-panel";
import { useSubmissionsPage } from "./use-submissions-page";

export function SubmissionsPage() {
  const {
    navigate,
    items,
    activeTab,
    setActiveTab,
    loadState,
    error,
    retryingId,
    selectedId,
    detail,
    detailState,
    selectedScreenshotPath,
    setSelectedScreenshotPath,
    selectedChannel,
    setSelectedChannel,
    channelSession,
    sessionState,
    sessionAction,
    nativeSession,
    nativeSessionBusy,
    nativeAttachmentView,
    cleanupBusy,
    cleanupNotice,
    pdfQuickRunId,
    setPdfQuickRunId,
    quickRunOptions,
    nativePdf,
    setNativePdf,
    acceptPdfEffects,
    setAcceptPdfEffects,
    acceptAttachmentRemoval,
    setAcceptAttachmentRemoval,
    nativePdfError,
    autoAdvanceNotice,
    quotaCleaned,
    existingPreparedRun,
    qualityDecisionNotice,
    decideHighlight,
    cleanupOldAttachments,
    diagnoseAttachments,
    checkModeResult,
    checkModeState,
    feedbackList,
    feedbackIteration,
    feedbackNotes,
    setFeedbackNotes,
    feedbackSource,
    setFeedbackSource,
    feedbackAction,
    setFeedbackAction,
    feedbackState,
    checkModeForm,
    setCheckModeForm,
    stats,
    screenshotSteps,
    refreshing,
    loadData,
    feedbackSync,
    handleNativeSession,
    handleFeedbackSync,
    handleNativePdf,
    runAutoAdvance,
    confirmFinalSend,
    loadExistingPreparedPdf,
    reuploadMissingAttachment,
    handleStartSession,
    handleCheckSession,
    handleClearSession,
    handleStartCheckMode,
    feedbackRunId,
    managedFeedback,
    handleCreateFeedbackIteration,
    handleRetry,
    handleSelect,
    pdfStep,
    quotaReached,
    quotaBlocked,
    visibleUploadHints,
    cleanupQuotaAndRetry,
    autoAdvanceAvailable,
    t,
    nativePdfPreview,
    previewedPdf,
    setNativePdfPreview,
    setPreviewedPdf,
  } = useSubmissionsPage();
  return (
    <div className="space-y-6">
      <SubmissionsPageHeader
        activeTab={activeTab}
        onTabChange={setActiveTab}
        refreshing={refreshing}
        retryingId={retryingId}
        loadState={loadState}
        error={error}
        onRefresh={() => void loadData()}
      />

      {loadState === "ready" ? (
        <>
          <div className={activeTab === "deliver" ? "space-y-6" : "hidden"} data-testid="submissions-tab-deliver">
            <SubmissionsNativeDeliveryPanel
              nativeSession={nativeSession}
              nativeSessionBusy={nativeSessionBusy}
              feedbackSync={feedbackSync}
              nativeAttachmentView={nativeAttachmentView}
              pdfStep={pdfStep}
              pdfQuickRunId={pdfQuickRunId}
              quickRunOptions={quickRunOptions}
              nativePdf={nativePdf}
              nativePdfError={nativePdfError}
              nativePdfPreview={nativePdfPreview}
              previewedPdf={previewedPdf}
              acceptPdfEffects={acceptPdfEffects}
              acceptAttachmentRemoval={acceptAttachmentRemoval}
              autoAdvanceAvailable={autoAdvanceAvailable}
              autoAdvanceNotice={autoAdvanceNotice}
              quotaBlocked={quotaBlocked}
              quotaReached={quotaReached}
              quotaCleaned={quotaCleaned}
              visibleUploadHints={visibleUploadHints}
              cleanupBusy={cleanupBusy}
              cleanupNotice={cleanupNotice}
              qualityDecisionNotice={qualityDecisionNotice}
              existingPreparedRun={existingPreparedRun}
              onNativeSession={(action) => void handleNativeSession(action)}
              onFeedbackSync={() => void handleFeedbackSync()}
              onCleanupOldAttachments={() => void cleanupOldAttachments()}
              onDiagnoseAttachments={() => void diagnoseAttachments()}
              onPdfQuickRunChange={(value) => {
                setPdfQuickRunId(value);
                setNativePdf(null);
                setAcceptPdfEffects(false);
                setNativePdfPreview("");
                setPreviewedPdf("");
              }}
              onPreparePdf={() => void handleNativePdf("prepare")}
              onDecideHighlight={(highlightId, action) => void decideHighlight(highlightId, action)}
              onAcceptPdfEffectsChange={setAcceptPdfEffects}
              onAcceptAttachmentRemovalChange={setAcceptAttachmentRemoval}
              onAutoAdvance={() => runAutoAdvance()}
              onConfirmFinalSend={() => confirmFinalSend()}
              onCleanupQuotaAndRetry={() => void cleanupQuotaAndRetry()}
              onNativePdf={(action) => void handleNativePdf(action)}
              onReuploadMissing={() => void reuploadMissingAttachment()}
              onLoadExistingPrepared={() => void loadExistingPreparedPdf()}
              onNavigate={(path) => navigate(path)}
            />
          </div>

          <div className={activeTab === "records" ? "space-y-6" : "hidden"} data-testid="submissions-tab-records">
            <SubmissionsStatsStrip stats={stats} />

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_440px]">
              <SubmissionsRunsPanel
                items={items}
                selectedId={selectedId}
                detailState={detailState}
                retryingId={retryingId}
                onSelect={(submissionId) => void handleSelect(submissionId)}
                onRetry={(submissionId) => void handleRetry(submissionId)}
              />
              <SubmissionsDetailPanel
                detail={detail}
                detailState={detailState}
                error={error}
                retryingId={retryingId}
                screenshotSteps={screenshotSteps}
                selectedScreenshotPath={selectedScreenshotPath}
                onSelectScreenshot={setSelectedScreenshotPath}
                onRetry={(submissionId, strategy) => void handleRetry(submissionId, strategy)}
                onOpenApproval={(runId) => navigate(`/agent-run?run_id=${encodeURIComponent(runId)}`)}
              />
            </div>
          </div>

          <SubmissionsFeedbackPanel
            feedbackState={feedbackState}
            feedbackRunId={feedbackRunId}
            feedbackList={feedbackList}
            feedbackIteration={feedbackIteration}
            managedFeedback={managedFeedback}
            feedbackNotes={feedbackNotes}
            feedbackSource={feedbackSource}
            feedbackAction={feedbackAction}
            selectedId={selectedId}
            items={items}
            error={error}
            onNotesChange={setFeedbackNotes}
            onSourceChange={setFeedbackSource}
            onActionChange={setFeedbackAction}
            onSelect={(submissionId) => void handleSelect(submissionId)}
            onCreateFeedbackIteration={() => void handleCreateFeedbackIteration()}
            onNavigate={(path) => navigate(path)}
          />

          <details className="fold-section rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]" data-testid="submissions-advanced">
            <summary>
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-3">
                <span>{t("pages.submissions.advancedTools")}</span>
                <span className="text-sm font-normal text-text-secondary">{t("pages.submissions.advancedHint")}</span>
              </span>
            </summary>
            <div className="space-y-6 px-5 pb-5">
              <SubmissionsSessionPanel
                channelSession={channelSession}
                sessionState={sessionState}
                selectedChannel={selectedChannel}
                sessionAction={sessionAction}
                error={error}
                onSelectedChannelChange={setSelectedChannel}
                onStartSession={() => void handleStartSession()}
                onCheckSession={() => void handleCheckSession()}
                onClearSession={() => void handleClearSession()}
              />
              <SubmissionsCheckModePanel
                channelSession={channelSession}
                checkModeState={checkModeState}
                checkModeForm={checkModeForm}
                checkModeResult={checkModeResult}
                error={error}
                onFormChange={setCheckModeForm}
                onStartCheckMode={() => void handleStartCheckMode()}
              />
            </div>
          </details>
        </>
      ) : null}
    </div>
  );
}
