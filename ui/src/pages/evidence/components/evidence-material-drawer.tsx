import { useTranslation } from "react-i18next";
import { Sparkles, X } from "lucide-react";
import type { MaterialDocumentRef } from "@/lib/sidecar/api";
import type { MaterialSourceItem } from "@/lib/sidecar/types";
import { MaterialDocumentPicker } from "../material-document-picker";

type EvidenceMaterialDrawerProps = {
  materialSources: MaterialSourceItem[];
  selectedMaterialId: string;
  selectedMaterial: MaterialSourceItem | undefined;
  selectedDocument: MaterialDocumentRef | null;
  busy: boolean;
  draftState: "idle" | "generating";
  onSelectMaterial: (materialId: string) => void;
  onSelectDocument: (document: MaterialDocumentRef | null) => void;
  onClose: () => void;
  onGenerateDraft: () => void;
  onManualDraft: () => void;
  onOpenMaterialsPage: () => void;
  onOpenMaterialSourcesSettings: () => void;
};

/** 材料蒸馏抽屉：选材料/文档，生成草稿或进入人工审核。 */
export function EvidenceMaterialDrawer({
  materialSources,
  selectedMaterialId,
  selectedMaterial,
  selectedDocument,
  busy,
  draftState,
  onSelectMaterial,
  onSelectDocument,
  onClose,
  onGenerateDraft,
  onManualDraft,
  onOpenMaterialsPage,
  onOpenMaterialSourcesSettings,
}: EvidenceMaterialDrawerProps) {
  const { t } = useTranslation();
  return (
    <div
      className="fixed inset-0 z-[var(--z-drawer)] flex justify-end bg-black/50"
      data-testid="evidence-drawer-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
    >
      <aside
        aria-label={t("pages.evidence.materialSources.title")}
        aria-modal="true"
        className="flex h-full w-[560px] max-w-full flex-col gap-4 overflow-y-auto border-l border-border bg-bg-panel p-6 shadow-[var(--shadow-panel)]"
        data-testid="evidence-drawer"
        role="dialog"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">{t("pages.evidence.materialSources.title")}</h2>
            <p className="mt-1 text-sm text-text-secondary">{t("pages.evidence.materialSources.summaryHint")}</p>
          </div>
          <button
            aria-label={t("common.close")}
            className="page-icon-button"
            data-testid="evidence-drawer-close"
            onClick={onClose}
            type="button"
          >
            <X size={16} />
          </button>
        </div>
        {materialSources.length === 0 ? (
          <div className="rounded-card border border-border bg-bg-hover/50 p-4 text-sm text-text-secondary">
            <p>{t("pages.evidence.materialSources.empty")}</p>
            <button className="mt-3 text-sm text-accent underline" onClick={onOpenMaterialsPage} type="button">
              {t("pages.evidence.emptyState.uploadMaterial")}
            </button>
          </div>
        ) : (
          <>
            <label className="block text-sm text-text-primary">
              {t("pages.evidence.materialSources.select")}
              <select
                className="mt-2 w-full rounded-card border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                data-testid="evidence-drawer-material"
                disabled={busy}
                onChange={(event) => onSelectMaterial(event.target.value)}
                value={selectedMaterialId}
              >
                {materialSources.map((source) => (
                  <option key={source.material_id} value={source.material_id} disabled={![".md", ".txt"].includes(source.extension)}>
                    {source.label || source.filename}{source.source_mode === "referenced" ? ` · ${t("pages.evidence.materialSources.referenceBadge", { count: Number(source.file_count) || 0 })}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <MaterialDocumentPicker materialId={selectedMaterialId} onSelect={onSelectDocument} disabled={busy} />
            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
              <button
                className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="evidence-drawer-generate"
                disabled={busy || !selectedMaterialId || !selectedDocument}
                onClick={onGenerateDraft}
                type="button"
              >
                <Sparkles size={16} />
                {draftState === "generating" ? t("pages.evidence.actions.generatingDraft") : t("pages.evidence.actions.generateDraft")}
              </button>
              <button
                className="rounded-card border border-border px-4 py-2 text-sm text-text-primary disabled:opacity-50"
                disabled={busy || !selectedMaterial || ![".md", ".txt"].includes(selectedMaterial.extension)}
                onClick={onManualDraft}
                type="button"
              >
                {t("pages.evidence.actions.manualDraft")}
              </button>
            </div>
            <p className="text-xs text-text-muted">{t("pages.evidence.materialSources.segmentHint")}</p>
          </>
        )}
        <div className="mt-auto border-t border-border pt-4 text-xs text-text-secondary">
          <p>{t("pages.evidence.materialSources.referenceMoved")}</p>
          <button className="mt-1 text-accent underline" onClick={onOpenMaterialSourcesSettings} type="button">
            {t("pages.evidence.materialSources.referenceLink")}
          </button>
        </div>
      </aside>
    </div>
  );
}
