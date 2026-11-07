import { useTranslation } from "react-i18next";
import { FileUp, RotateCcw, Trash2, Upload } from "lucide-react";
import type {
  ArtifactSummary,
  EvidenceDraftPayload,
} from "@/lib/sidecar/types";
import { formatBytes } from "../evidence-helpers";
import type { EvidenceImportMode } from "../evidence-helpers";

type EvidenceArtifactsPanelProps = {
  generatedDraft: EvidenceDraftPayload | null;
  artifacts: ArtifactSummary[];
  previewArtifact: ArtifactSummary | null;
  importPath: string;
  importMode: EvidenceImportMode;
  importState: "idle" | "importing";
  selectedId: string | null;
  busy: boolean;
  onPreviewArtifact: (artifact: ArtifactSummary) => void;
  onArtifactDelete: (resourceId: string) => void;
  onImportPathChange: (value: string) => void;
  onImportModeChange: (mode: EvidenceImportMode) => void;
  onImport: () => void;
};

/** 详情面板「产物」区：草稿产物、已存产物、预览摘要与导入表单。 */
export function EvidenceArtifactsPanel({
  generatedDraft,
  artifacts,
  previewArtifact,
  importPath,
  importMode,
  importState,
  selectedId,
  busy,
  onPreviewArtifact,
  onArtifactDelete,
  onImportPathChange,
  onImportModeChange,
  onImport,
}: EvidenceArtifactsPanelProps) {
  const { t } = useTranslation();

  const renderArtifact = (artifact: ArtifactSummary) => {
    const resourceId = artifact.resource_id ?? "";
    return (
      <div
        key={artifact.resource_id ?? artifact.filename}
        className="rounded-card border border-border bg-bg-hover/50 p-3"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-text-primary">
              {artifact.filename ?? t("pages.evidence.artifactFallback")}
            </p>
            <p className="mt-1 text-xs text-text-secondary">
              {artifact.mime_type || "--"} · {formatBytes(artifact.size_bytes)}
            </p>
            <p className="mt-1 text-xs text-text-muted">
              {artifact.created_at || "--"}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              className="rounded-card border border-border p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
              onClick={() => onPreviewArtifact(artifact)}
              type="button"
              title={t("pages.evidence.artifacts.preview")}
            >
              <FileUp size={15} />
            </button>
            <button
              className="rounded-card border border-border p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
              type="button"
              title={t("pages.evidence.artifacts.reupload")}
              onClick={() => onImportModeChange("replace")}
            >
              <RotateCcw size={15} />
            </button>
            <button
              className="rounded-card border border-error/40 p-2 text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!resourceId || busy}
              onClick={() => onArtifactDelete(resourceId)}
              type="button"
              title={t("pages.evidence.artifacts.delete")}
              aria-label={t("pages.evidence.artifacts.delete")}
            >
              <Trash2 size={15} />
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <section className="rounded-card border border-border bg-bg-hover/50 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">
            {t("pages.evidence.artifacts.title")}
          </h3>
          <p className="mt-1 text-xs text-text-secondary">
            {t("pages.evidence.artifacts.size", {
              count: generatedDraft?.artifacts.length ?? artifacts.length ?? 0,
            })}
          </p>
        </div>
      </div>
      <div className="mt-3 grid gap-2">
        {generatedDraft?.artifacts.length ? (
          generatedDraft.artifacts.map((artifact) => (
            <div
              key={`${artifact.type}-${artifact.ref}`}
              className="rounded-card border border-border bg-bg-panel/60 p-3"
            >
              <p className="truncate text-sm font-medium text-text-primary">
                {artifact.label}
              </p>
              <p className="mt-1 font-mono text-xs text-text-muted">
                {artifact.type} · {artifact.ref}
              </p>
            </div>
          ))
        ) : artifacts.length ? (
          artifacts.map(renderArtifact)
        ) : (
          <p className="rounded-card border border-dashed border-border p-3 text-sm text-text-secondary">
            {t("pages.evidence.artifacts.empty")}
          </p>
        )}
      </div>
      {previewArtifact ? (
        <div className="mt-3 rounded-card border border-accent/40 bg-accent/10 p-3">
          <p className="text-xs uppercase tracking-[0.16em] text-accent">
            {t("pages.evidence.artifacts.preview")}
          </p>
          <p className="mt-2 truncate text-sm font-medium text-text-primary">
            {previewArtifact.filename ??
              t("pages.evidence.artifactFallback")}
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            {previewArtifact.mime_type || "--"} ·{" "}
            {formatBytes(previewArtifact.size_bytes)}
          </p>
          <p className="mt-1 font-mono text-xs text-text-muted">
            {previewArtifact.resource_id ?? "--"}
          </p>
        </div>
      ) : null}
      <details className="mt-3">
        <summary className="cursor-pointer select-none text-xs text-text-muted">{t("pages.evidence.artifacts.importTitle")}</summary>
      <div className="mt-2 grid gap-2">
        <input
          className="rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
          onChange={(event) => onImportPathChange(event.target.value)}
          placeholder={t("pages.evidence.artifacts.sourcePlaceholder")}
          type="text"
          value={importPath}
        />
        <div className="grid gap-2 sm:grid-cols-[1fr_auto] xl:grid-cols-1">
          <select
            className="rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) =>
              onImportModeChange(event.target.value as EvidenceImportMode)
            }
            value={importMode}
          >
            <option value="create">
              {t("pages.evidence.artifacts.modeCreate")}
            </option>
            <option value="append" disabled={!selectedId}>
              {t("pages.evidence.artifacts.modeAppend")}
            </option>
            <option value="replace" disabled={!selectedId}>
              {t("pages.evidence.artifacts.modeReplace")}
            </option>
          </select>
          <button
            className="inline-flex items-center justify-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy}
            onClick={onImport}
            type="button"
          >
            <Upload size={16} />
            {importState === "importing"
              ? t("pages.evidence.actions.importing")
              : t("pages.evidence.actions.import")}
          </button>
        </div>
      </div>
      </details>
    </section>
  );
}
