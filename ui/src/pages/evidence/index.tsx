import { Sparkles } from "lucide-react";

import { EvidenceDetailPanel } from "./components/evidence-detail-panel";
import { EvidenceListPanel } from "./components/evidence-list-panel";
import { EvidenceMaterialDrawer } from "./components/evidence-material-drawer";
import { EvidencePageHeader } from "./components/evidence-page-header";
import { EvidenceSummaryBar } from "./components/evidence-summary-bar";
import { useEvidencePage } from "./use-evidence-page";

export function EvidencePage() {
  const {
    navigate,
    items,
    listTruncated,
    materialSources,
    selectedId,
    detail,
    form,
    setForm,
    isDraft,
    loadState,
    detailState,
    saveState,
    draftState,
    deleteState,
    importState,
    error,
    detailError,
    queryInput,
    setQueryInput,
    roleInput,
    setRoleInput,
    tagInput,
    setTagInput,
    importPath,
    setImportPath,
    importMode,
    setImportMode,
    selectedMaterialId,
    setSelectedMaterialId,
    generatedDraft,
    reviewTargetId,
    selectedDocument,
    setSelectedDocument,
    previewArtifact,
    setPreviewArtifact,
    isBusy,
    selectedMaterial,
    reviewMissingItems,
    loadDetail,
    refreshing,
    reconcileState,
    reconcileError,
    runReconcile,
    inference,
    inferenceState,
    inferenceError,
    inferenceNotice,
    inferenceBusy,
    inferenceEdits,
    setInferenceEdits,
    showLowConfidence,
    setShowLowConfidence,
    inferenceByCard,
    runInference,
    handleInferenceDecision,
    batchAcceptHighConfidence,
    problemFilter,
    setProblemFilter,
    materialDrawerOpen,
    setMaterialDrawerOpen,
    reconcileItemByCard,
    problemTagsFor,
    hasHighConfidenceCandidates,
    summaryCounts,
    filteredItems,
    changeTriage,
    editMode,
    setEditMode,
    editing,
    selectedStatus,
    loadEvidence,
    applyFilters,
    resetFilters,
    handleCreateDraft,
    draftFromForm,
    handleManualDraft,
    handleGenerateDraft,
    handleSaveReviewedDraft,
    handleSave,
    handleDelete,
    handleImport,
    handleArtifactDelete,
    startRereview,
    handleMergeChange,
    t,
  } = useEvidencePage();
  return (
    <div className="space-y-6">
      <EvidencePageHeader
        t={t}
        busy={isBusy}
        refreshing={refreshing}
        onRefresh={() => void loadEvidence()}
        onOpenDrawer={() => setMaterialDrawerOpen(true)}
        onCreateDraft={handleCreateDraft}
      />

      {loadState === "error" ? (
        <section className="rounded-panel border border-error/50 bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{error}</p>
        </section>
      ) : null}

      {loadState === "loading" ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-sm text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.loading")}
        </section>
      ) : null}

      {loadState === "ready" && items.length === 0 && !isDraft && !detail ? (
        <section className="rounded-panel border border-border bg-bg-panel p-8 text-center shadow-[var(--shadow-panel)]" data-testid="evidence-empty-state">
          <h2 className="text-base font-semibold text-text-primary">{t("pages.evidence.emptyState.title")}</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-text-secondary">{t("pages.evidence.emptyState.body")}</p>
          <div className="mt-4 flex items-center justify-center gap-2">
            {materialSources.length > 0 ? (
              <button className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white" onClick={() => setMaterialDrawerOpen(true)} type="button">
                <Sparkles size={16} />{t("pages.evidence.actions.distill")}
              </button>
            ) : (
              <button className="inline-flex items-center gap-2 rounded-card border border-accent px-4 py-2 text-sm text-accent" onClick={() => navigate("/resumes?section=materials")} type="button">
                {t("pages.evidence.emptyState.uploadMaterial")}
              </button>
            )}
            <button className="rounded-card border border-border px-4 py-2 text-sm text-text-primary" onClick={handleCreateDraft} type="button">
              {t("pages.evidence.actions.new")}
            </button>
          </div>
        </section>
      ) : null}

      {loadState === "ready" && !(items.length === 0 && !isDraft && !detail) ? (
        <>
          {items.length > 0 ? (
            <EvidenceSummaryBar
              summaryCounts={summaryCounts}
              problemFilter={problemFilter}
              onProblemFilterChange={setProblemFilter}
              reconcileState={reconcileState}
              reconcileError={reconcileError}
              onReconcile={() => void runReconcile()}
              inferenceState={inferenceState}
              inferenceBusy={inferenceBusy}
              inference={inference}
              inferenceNotice={inferenceNotice}
              inferenceError={inferenceError}
              hasHighConfidenceCandidates={hasHighConfidenceCandidates}
              onRunInference={() => void runInference()}
              onBatchAccept={() => void batchAcceptHighConfidence()}
            />
          ) : null}

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <EvidenceListPanel
              items={items}
              filteredItems={filteredItems}
              selectedId={selectedId}
              listTruncated={listTruncated}
              problemFilter={problemFilter}
              summaryCounts={summaryCounts}
              queryInput={queryInput}
              roleInput={roleInput}
              tagInput={tagInput}
              onProblemFilterChange={setProblemFilter}
              onQueryInputChange={setQueryInput}
              onRoleInputChange={setRoleInput}
              onTagInputChange={setTagInput}
              onApplyFilters={applyFilters}
              onResetFilters={resetFilters}
              onSelect={(evidenceId) => void loadDetail(evidenceId)}
              problemTagsFor={problemTagsFor}
            />
            <EvidenceDetailPanel
              detail={detail}
              form={form}
              editing={editing}
              editMode={editMode}
              isDraft={isDraft}
              selectedId={selectedId}
              selectedStatus={selectedStatus}
              detailState={detailState}
              detailError={detailError}
              saveState={saveState}
              deleteState={deleteState}
              busy={isBusy}
              generatedDraft={generatedDraft}
              reviewTargetId={reviewTargetId}
              reviewMissingItems={reviewMissingItems}
              materialSources={materialSources}
              reconcileItem={selectedId ? reconcileItemByCard.get(selectedId) : undefined}
              inferenceCard={selectedId ? inferenceByCard.get(selectedId) : undefined}
              inferenceEdits={inferenceEdits}
              inferenceBusy={inferenceBusy}
              showLowConfidence={showLowConfidence}
              previewArtifact={previewArtifact}
              importPath={importPath}
              importMode={importMode}
              importState={importState}
              setForm={setForm}
              setEditMode={setEditMode}
              draftFromForm={draftFromForm}
              onSave={() => void handleSave()}
              onSaveReviewedDraft={(saveMode) => void handleSaveReviewedDraft(saveMode)}
              onDelete={() => void handleDelete()}
              onStartRereview={startRereview}
              onMergeChange={handleMergeChange}
              onInferenceDecision={(item, cardSha, candidate, action, value) => void handleInferenceDecision(item, cardSha, candidate, action, value)}
              onInferenceEditsChange={setInferenceEdits}
              onShowLowConfidence={setShowLowConfidence}
              onChangeTriage={(item, decision) => void changeTriage(item, decision)}
              onPreviewArtifact={setPreviewArtifact}
              onArtifactDelete={(resourceId) => void handleArtifactDelete(resourceId)}
              onImportPathChange={setImportPath}
              onImportModeChange={setImportMode}
              onImport={() => void handleImport()}
            />
          </div>
        </>
      ) : null}

      {materialDrawerOpen ? (
        <EvidenceMaterialDrawer
          materialSources={materialSources}
          selectedMaterialId={selectedMaterialId}
          selectedMaterial={selectedMaterial}
          selectedDocument={selectedDocument}
          busy={isBusy}
          draftState={draftState}
          onSelectMaterial={setSelectedMaterialId}
          onSelectDocument={setSelectedDocument}
          onClose={() => setMaterialDrawerOpen(false)}
          onGenerateDraft={() => {
            void handleGenerateDraft().then(() => setMaterialDrawerOpen(false));
          }}
          onManualDraft={() => {
            handleManualDraft();
            setMaterialDrawerOpen(false);
          }}
          onOpenMaterialsPage={() => navigate("/resumes?section=materials")}
          onOpenMaterialSourcesSettings={() => navigate("/system-settings?section=materialSources")}
        />
      ) : null}
    </div>
  );
}
