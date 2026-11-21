import { useTranslation } from "react-i18next";
import type { Dispatch, SetStateAction } from "react";
import { Save as SaveIcon } from "lucide-react";
import type {
  ArtifactSummary,
  EvidenceDetail,
  EvidenceDraftPayload,
  EvidenceInferenceCandidate,
  EvidenceInferenceResult,
  EvidenceReconcileItem,
  EvidenceTriageDecision,
  MaterialSourceItem,
} from "@/lib/sidecar/types";
import type {
  EvidenceForm,
  EvidenceImportMode,
  LoadState,
  SaveState,
} from "../evidence-helpers";
import { EvidenceSourceMerge } from "../source-merge-panel";
import { EvidenceArtifactsPanel } from "./evidence-artifacts-panel";
import { EvidenceDetailView } from "./evidence-detail-view";
import { EvidenceDiagnosisPanel } from "./evidence-diagnosis-panel";
import { EvidenceReviewSection } from "./evidence-review-section";

type EvidenceDetailPanelProps = {
  detail: EvidenceDetail | null;
  form: EvidenceForm;
  editing: boolean;
  editMode: boolean;
  isDraft: boolean;
  selectedId: string | null;
  selectedStatus: string | undefined;
  detailState: LoadState;
  detailError: string | null;
  saveState: SaveState;
  deleteState: "idle" | "deleting";
  busy: boolean;
  generatedDraft: EvidenceDraftPayload | null;
  reviewTargetId: string | undefined;
  reviewMissingItems: (string | false)[];
  materialSources: MaterialSourceItem[];
  reconcileItem: EvidenceReconcileItem | undefined;
  inferenceCard: EvidenceInferenceResult["cards"][number] | undefined;
  inferenceEdits: Record<string, string>;
  inferenceBusy: boolean;
  showLowConfidence: boolean;
  previewArtifact: ArtifactSummary | null;
  importPath: string;
  importMode: EvidenceImportMode;
  importState: "idle" | "importing";
  setForm: Dispatch<SetStateAction<EvidenceForm>>;
  setEditMode: (editing: boolean) => void;
  draftFromForm: (draft: EvidenceDraftPayload) => EvidenceDraftPayload;
  onSave: () => void;
  onSaveReviewedDraft: (saveMode: "incomplete" | "eligible", factScope?: import("@/lib/sidecar/types").EvidenceFactScopeReview) => void;
  onDelete: () => void;
  onStartRereview: () => void;
  onMergeChange: (draft: EvidenceDraftPayload) => void;
  onInferenceDecision: (
    item: EvidenceReconcileItem,
    cardSha: string,
    candidate: EvidenceInferenceCandidate,
    action: "accept" | "reject",
    value?: string
  ) => void;
  onInferenceEditsChange: (
    updater: (current: Record<string, string>) => Record<string, string>
  ) => void;
  onShowLowConfidence: (value: boolean) => void;
  onChangeTriage: (item: EvidenceReconcileItem, decision: EvidenceTriageDecision | "") => void;
  onPreviewArtifact: (artifact: ArtifactSummary) => void;
  onArtifactDelete: (resourceId: string) => void;
  onImportPathChange: (value: string) => void;
  onImportModeChange: (mode: EvidenceImportMode) => void;
  onImport: () => void;
};

/** 证据详情栏：只读/编辑、模型草稿复核、对账发现、产物与删除。 */
export function EvidenceDetailPanel({
  detail,
  form,
  editing,
  editMode,
  isDraft,
  selectedId,
  selectedStatus,
  detailState,
  detailError,
  saveState,
  deleteState,
  busy,
  generatedDraft,
  reviewTargetId,
  reviewMissingItems,
  materialSources,
  reconcileItem,
  inferenceCard,
  inferenceEdits,
  inferenceBusy,
  showLowConfidence,
  previewArtifact,
  importPath,
  importMode,
  importState,
  setForm,
  setEditMode,
  draftFromForm,
  onSave,
  onSaveReviewedDraft,
  onDelete,
  onStartRereview,
  onMergeChange,
  onInferenceDecision,
  onInferenceEditsChange,
  onShowLowConfidence,
  onChangeTriage,
  onPreviewArtifact,
  onArtifactDelete,
  onImportPathChange,
  onImportModeChange,
  onImport,
}: EvidenceDetailPanelProps) {
  const { t } = useTranslation();
  const scopeSourceAmbiguous = detail?.source_error === "fact_scope_source_not_unique";
  return (
    <aside
      className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto"
      data-testid="evidence-detail-panel"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">
            {t("pages.evidence.sections.detail")}
          </h2>
          <p className="mt-1 text-xs text-text-muted">
            {isDraft ? t("pages.evidence.status.draft") : selectedStatus ? t(`pages.evidence.status.${selectedStatus}`, { defaultValue: selectedStatus }) : "--"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!editing ? (
            <button
              className="rounded-card border border-border px-3 py-1.5 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="evidence-edit"
              disabled={!selectedId || detailState !== "ready" || busy}
              onClick={() => setEditMode(true)}
              type="button"
            >
              {t("pages.evidence.actions.edit")}
            </button>
          ) : null}
          {editMode && !isDraft && !generatedDraft && !reviewTargetId ? (
            <button
              className="rounded-card border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-bg-hover"
              onClick={() => setEditMode(false)}
              type="button"
            >
              {t("pages.evidence.actions.cancelEdit")}
            </button>
          ) : null}
          {editing ? (
          <button
            className="inline-flex items-center gap-1.5 rounded-card border border-accent bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="evidence-save"
            disabled={busy || detailState!=="ready"}
            onClick={() =>
              generatedDraft
                ? onSaveReviewedDraft("eligible")
                : onSave()
            }
            title={t("pages.evidence.actions.save")}
            type="button"
          >
            <SaveIcon size={14} />
            {t("pages.evidence.actions.save")}
          </button>
          ) : null}
        </div>
      </div>

      {detailState === "loading" ? (
        <p className="pt-4 text-sm text-text-secondary">{t("common.loading")}</p>
      ) : null}

      {detailState === "error" ? (
        <div className="pt-4">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{detailError}</p>
        </div>
      ) : null}

      {detailState === "ready" && detailError ? (
        <p className="pt-4 text-sm font-medium text-error">{detailError}</p>
      ) : null}

      {detailState === "ready" && (detail || isDraft) ? (
        <div className="space-y-4 pt-4">
          {!!detail?.source_error&&<p role="alert" className="text-sm text-warning">{t(scopeSourceAmbiguous ? 'factScope.sourceNotUnique' : 'sourceMerge.changed')}</p>}
          {!generatedDraft && !!detail?.source_material_ids?.length && <button type="button" disabled={busy} className="rounded-card border border-accent px-3 py-2 text-sm text-accent" onClick={onStartRereview}>{t('materialDocument.reReview')}</button>}
          {generatedDraft ? (
            <EvidenceReviewSection
              key={reviewTargetId ?? "new"}
              scopeDraft={reviewTargetId&&detail?.evidence_id===reviewTargetId&&(!detail.source_error||scopeSourceAmbiguous)
                ? draftFromForm(generatedDraft) : undefined}
              sourceError={detail?.source_error}
              reviewedScopes={detail?.fact_scope_review}
              generatedDraft={generatedDraft}
              reviewMissingItems={reviewMissingItems}
              busy={busy}
              onSaveReviewedDraft={onSaveReviewedDraft}
            />
          ) : null}

          {generatedDraft&&reviewTargetId&&<EvidenceSourceMerge key={reviewTargetId} draft={draftFromForm(generatedDraft)} materials={materialSources} disabled={busy} onChange={onMergeChange}/>}
          <EvidenceDetailView
            detail={detail}
            form={form}
            editing={editing}
            busy={busy}
            setForm={setForm}
          />

          {!editing && selectedId && reconcileItem ? (
            <EvidenceDiagnosisPanel
              item={reconcileItem}
              card={inferenceCard}
              inferenceEdits={inferenceEdits}
              inferenceBusy={inferenceBusy}
              showLowConfidence={showLowConfidence}
              onInferenceEditsChange={onInferenceEditsChange}
              onShowLowConfidence={onShowLowConfidence}
              onInferenceDecision={onInferenceDecision}
              onChangeTriage={onChangeTriage}
            />
          ) : null}

          <EvidenceArtifactsPanel
            generatedDraft={generatedDraft}
            artifacts={detail?.artifacts ?? []}
            previewArtifact={previewArtifact}
            importPath={importPath}
            importMode={importMode}
            importState={importState}
            selectedId={selectedId}
            busy={busy}
            onPreviewArtifact={onPreviewArtifact}
            onArtifactDelete={onArtifactDelete}
            onImportPathChange={onImportPathChange}
            onImportModeChange={onImportModeChange}
            onImport={onImport}
          />

          <details className="text-xs text-text-secondary">
            <summary className="cursor-pointer select-none text-text-muted">{t("pages.evidence.sections.technical")}</summary>
            <div className="mt-2 grid gap-1">
              <p className="break-all"><span className="text-text-muted">ID</span> {selectedId ?? "--"}</p>
              <p className="break-all"><span className="text-text-muted">{t("pages.evidence.fields.sourceMaterials")}</span> {(detail?.source_material_ids ?? []).join(", ") || "--"}</p>
            </div>
          </details>

          {saveState === "saved" ? (
            <p className="text-sm text-success">
              {t("pages.evidence.actions.saved")}
            </p>
          ) : null}
          {selectedId && !isDraft ? (
            <div className="mt-4 border-t border-border pt-3">
              <button
                className="w-full rounded-card border border-error/60 px-3 py-2 text-sm text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="evidence-delete"
                disabled={deleteState === "deleting"}
                onClick={onDelete}
                type="button"
              >
                {deleteState === "deleting" ? t("pages.evidence.actions.deleting") : t("pages.evidence.actions.delete")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
