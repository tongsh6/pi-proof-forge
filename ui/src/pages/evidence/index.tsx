import { MaterialDocumentPicker } from "./material-document-picker";
import { EvidenceSourceMerge } from "./source-merge-panel";
import type { MaterialDocumentRef } from "@/lib/sidecar/api";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { Save as SaveIcon } from "lucide-react";
import {
  FileUp,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { confirmAction, notify } from "@/lib/ui";
import {
  createEvidence,
  deleteEvidence,
  generateEvidenceDraft,
  getEvidence,
  importEvidence,
  listEvidenceMaterialSources,
  listEvidence,
  reconcileEvidence,
  saveEvidenceDraft,
  updateEvidence,
} from "@/lib/sidecar/api";
import type {
  ArtifactSummary,
  EvidenceDraftPayload,
  EvidenceDetail,
  EvidenceFilters,
  EvidenceListItem,
  EvidenceReconcileItem,
  EvidenceReconcileResult,
  MaterialSourceItem,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved";
type EvidenceImportMode = "create" | "append" | "replace";

type EvidenceForm = {
  title: string;
  time_range: string;
  context: string;
  role_scope: string;
  actions: string;
  results: string;
  stackText: string;
  tagsText: string;
};

const DEFAULT_FILTERS: EvidenceFilters = {
  query: "",
  status: null,
  role: null,
  tags: [],
  date_range: null,
};

function parseCommaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function toForm(detail: EvidenceDetail | null): EvidenceForm {
  return {
    title: detail?.title ?? "",
    time_range: detail?.time_range ?? "",
    context: detail?.context ?? "",
    role_scope: detail?.role_scope ?? "",
    actions: detail?.actions ?? "",
    results: detail?.results ?? "",
    stackText: detail?.stack.join(", ") ?? "",
    tagsText: detail?.tags.join(", ") ?? "",
  };
}

function formatFallback(value: string): string {
  return value.trim() ? value : "--";
}

function formatBytes(value: number | undefined): string {
  if (!value || value <= 0) return "--";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 102.4) / 10} KB`;
  return `${Math.round(value / 1024 / 102.4) / 10} MB`;
}

function statusTone(status: string): string {
  if (status === "ready" || status === "pass") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (
    status === "gap" ||
    status === "needs_review" ||
    status === "saved_incomplete"
  ) {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "draft" || status === "draft_incomplete") {
    return "border-border bg-bg-hover text-text-secondary";
  }
  if (status === "saved_eligible" || status === "draft_ready_for_review") {
    return "border-success/40 bg-success/10 text-success";
  }
  return "border-accent/40 bg-accent/10 text-accent";
}

function selectedArtifactCount(detail: EvidenceDetail | null): number {
  return detail?.artifacts.length ?? 0;
}

export function EvidencePage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  // 允许从总览等页面带 ?status=gap 直接进入已筛选列表。
  const initialStatus = searchParams.get("status") ?? "";
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  const [materialSources, setMaterialSources] = useState<MaterialSourceItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [form, setForm] = useState<EvidenceForm>(() => toForm(null));
  const [isDraft, setIsDraft] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [detailState, setDetailState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [draftState, setDraftState] = useState<"idle" | "generating">("idle");
  const [deleteState, setDeleteState] = useState<"idle" | "deleting">("idle");
  const [importState, setImportState] = useState<"idle" | "importing">("idle");
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [evidenceFilters, setEvidenceFilters] = useState<EvidenceFilters>(() =>
    initialStatus ? { ...DEFAULT_FILTERS, status: initialStatus } : DEFAULT_FILTERS
  );
  const [queryInput, setQueryInput] = useState("");
  const [statusInput, setStatusInput] = useState(initialStatus);
  const [roleInput, setRoleInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [importPath, setImportPath] = useState("");
  const [importMode, setImportMode] = useState<EvidenceImportMode>("append");
  const [selectedMaterialId, setSelectedMaterialId] = useState("");
  const [selectedDocument,setSelectedDocument]=useState<MaterialDocumentRef|null>(null);
  const [reviewTargetId,setReviewTargetId]=useState<string|undefined>(undefined);
  const [generatedDraft, setGeneratedDraft] =
    useState<EvidenceDraftPayload | null>(null);
  const [previewArtifact, setPreviewArtifact] = useState<ArtifactSummary | null>(null);
  const selectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const evidenceStats = useMemo(
    () => ({
      total: items.length,
      ready: items.filter((item) => item.candidate_pool_eligible === true)
        .length,
      gaps: items.filter(
        (item) => item.status === "gap" || item.status === "needs_review"
      ).length,
      artifacts: generatedDraft?.artifacts.length ?? selectedArtifactCount(detail),
    }),
    [detail, generatedDraft, items]
  );

  const isBusy =
    saveState === "saving" ||
    draftState === "generating" ||
    deleteState === "deleting" ||
    importState === "importing";
  const selectedMaterial = materialSources.find((source) => source.material_id === selectedMaterialId);
  const reviewMissingItems = generatedDraft ? [
    !form.title.trim() && "missing_title",
    !form.results.trim() && "missing_results",
    !generatedDraft.artifacts.length && "missing_artifacts",
    !generatedDraft.source_material_ids.length && "missing_source_material_ids",
  ].filter(Boolean) : [];

  const loadDetail = useCallback(async (evidenceId: string) => {
    selectedIdRef.current = evidenceId;
    setSelectedId(evidenceId);
    setGeneratedDraft(null);setReviewTargetId(undefined);
    setDetailState("loading");
    setDetailError(null);

    try {
      const result = await getEvidence(evidenceId);
      if (selectedIdRef.current !== evidenceId) return null;
      setDetail(result.evidence);
      setPreviewArtifact(result.evidence.artifacts[0] ?? null);
      setForm(toForm(result.evidence));
      setIsDraft(false);
      setGeneratedDraft(null);setReviewTargetId(undefined);
      setDetailState("ready");
      return result.evidence;
    } catch (nextError) {
      if (selectedIdRef.current !== evidenceId) return null;
        setDetail(null);
        setPreviewArtifact(null);
        setForm(toForm(null));
      setDetailState("error");
      setDetailError(getErrorMessage(nextError));
      return null;
    }
  }, []);

  const hasLoadedRef = useRef(false);
  const [refreshing, setRefreshing] = useState(false);
  const [reconcile, setReconcile] = useState<EvidenceReconcileResult | null>(null);
  const [reconcileState, setReconcileState] = useState<"idle" | "running" | "error">("idle");
  const [reconcileError, setReconcileError] = useState<string | null>(null);
  const runReconcile = useCallback(async () => {
    setReconcileState("running");
    setReconcileError(null);
    try {
      setReconcile(await reconcileEvidence());
      setReconcileState("idle");
    } catch (reason) {
      setReconcileState("error");
      setReconcileError(getErrorMessage(reason));
    }
  }, []);
  const reconcileProblems = useMemo(() => {
    const items = reconcile?.items ?? [];
    const weight = (item: EvidenceReconcileItem) =>
      (item.untraceable_results.length > 0 ? 4 : 0) + (!item.has_source ? 2 : 0) + item.missing_fields.length + (item.possible_duplicates.length > 0 ? 1 : 0);
    return items.filter((item) => weight(item) > 0).sort((a, b) => weight(b) - weight(a));
  }, [reconcile]);
  const reconcileReasons = useCallback(
    (item: EvidenceReconcileItem) => {
      const reasons: string[] = [];
      if (item.untraceable_results.length > 0) reasons.push(t("pages.evidence.reconcile.reasons.untraceable", { count: item.untraceable_results.length }));
      if (!item.has_source) reasons.push(t("pages.evidence.reconcile.reasons.noSource"));
      if (item.missing_fields.includes("time_range"))
        reasons.push(
          item.date_hints.length > 0
            ? t("pages.evidence.reconcile.reasons.missingTimeHint", { hints: item.date_hints.slice(0, 3).join("、") })
            : t("pages.evidence.reconcile.reasons.missingTime")
        );
      if (item.missing_fields.includes("role_scope")) reasons.push(t("pages.evidence.reconcile.reasons.missingRole"));
      if (item.missing_fields.includes("results")) reasons.push(t("pages.evidence.reconcile.reasons.missingResults"));
      if (item.missing_fields.includes("artifacts")) reasons.push(t("pages.evidence.reconcile.reasons.missingArtifacts"));
      if (item.possible_duplicates.length > 0) reasons.push(t("pages.evidence.reconcile.reasons.duplicate", { ids: item.possible_duplicates.join("、") }));
      return reasons;
    },
    [t]
  );
  // 详情栏默认只读；新建草稿、模型草稿、重审时自动进入编辑态，切换卡片或保存成功后退出。
  const [editMode, setEditMode] = useState(false);
  useEffect(() => {
    setEditMode(false);
  }, [selectedId]);
  useEffect(() => {
    if (saveState === "saved") setEditMode(false);
  }, [saveState]);
  const editing = editMode || isDraft || Boolean(generatedDraft) || Boolean(reviewTargetId);
  const selectedStatus = items.find((item) => item.evidence_id === selectedId)?.status;

  // 首次加载显示占位；保存/删除后的重载保留列表与详情面板，不整页回到 loading。
  const loadEvidence = useCallback(
    async (preferredEvidenceId?: string | null) => {
      if (hasLoadedRef.current) setRefreshing(true);
      else setLoadState("loading");
      setError(null);
      try {
        const [result, materialResult] = await Promise.all([
          listEvidence(evidenceFilters),
          listEvidenceMaterialSources(),
        ]);
        setItems(result.items);
        setMaterialSources(materialResult.items);
        setSelectedMaterialId((current) => {
          if (
            current &&
            materialResult.items.some((item) => item.material_id === current)
          ) {
            return current;
          }
          return (
            materialResult.items.find((item) => item.extension === ".md")
              ?.material_id ?? ""
          );
        });
        const preferredItem =
          result.items.find(
            (item) =>
              item.evidence_id === (preferredEvidenceId ?? selectedIdRef.current)
          ) ?? result.items[0];

        if (preferredItem) {
          await loadDetail(preferredItem.evidence_id);
        }
        if (!preferredItem) {
          setSelectedId(null);
          setDetail(null);
          setPreviewArtifact(null);
          setForm(toForm(null));
          setIsDraft(true);
          setGeneratedDraft(null);setReviewTargetId(undefined);
          setDetailState("ready");
        }
        hasLoadedRef.current = true;
        setLoadState("ready");
      } catch (nextError) {
        const message = getErrorMessage(nextError);
        setError(message);
        if (hasLoadedRef.current) {
          notify("error", t("common.refreshFailed"), message);
        } else {
          setItems([]);
          setSelectedId(null);
          setDetail(null);
          setPreviewArtifact(null);
          setLoadState("error");
        }
      } finally {
        setRefreshing(false);
      }
    },
    [evidenceFilters, loadDetail] // eslint-disable-line react-hooks/exhaustive-deps
  );

  useEffect(() => {
    void loadEvidence();
  }, [loadEvidence]);

  const applyFilters = useCallback(() => {
    setEvidenceFilters({
      query: queryInput.trim(),
      status: statusInput || null,
      role: roleInput.trim() || null,
      tags: parseCommaList(tagInput),
      date_range: null,
    });
  }, [queryInput, roleInput, statusInput, tagInput]);

  const resetFilters = useCallback(() => {
    setQueryInput("");
    setStatusInput("");
    setRoleInput("");
    setTagInput("");
    setEvidenceFilters(DEFAULT_FILTERS);
  }, []);

  const handleCreateDraft = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
    setPreviewArtifact(null);
    setForm(toForm(null));
    setDetailError(null);
    setDetailState("ready");
    setIsDraft(true);
    setGeneratedDraft(null);setReviewTargetId(undefined);
    setSaveState("idle");
    setImportMode("create");
  }, []);

  const updateFormFromDraft = useCallback((draft: EvidenceDraftPayload) => {
    setForm({
      title: draft.title,
      time_range: draft.time_range ?? "",
      context: draft.context,
      role_scope: draft.role_scope ?? "",
      actions: draft.actions,
      results: draft.results,
      stackText: draft.stack.join(", "),
      tagsText: draft.tags.join(", "),
    });
  }, []);

  const draftFromForm = useCallback(
    (draft: EvidenceDraftPayload): EvidenceDraftPayload => ({
      ...draft,
      title: form.title.trim(),
      time_range: form.time_range,
      context: form.context,
      role_scope: form.role_scope,
      actions: form.actions,
      results: form.results,
      stack: parseCommaList(form.stackText),
      tags: parseCommaList(form.tagsText),
    }),
    [form]
  );

  const handleManualDraft = useCallback(() => {
    if (!selectedMaterial || ![".md", ".txt"].includes(selectedMaterial.extension)) return;
    const draft: EvidenceDraftPayload = { title: "", context: "", actions: "", results: "",
      stack: [], tags: [], source_material_ids: [selectedMaterial.material_id],
      artifacts: [{ type: selectedMaterial.extension === ".md" ? "markdown_document" : "text_document",
        ref: selectedMaterial.material_id, label: selectedMaterial.label || selectedMaterial.filename }],
      status: "draft_incomplete", candidate_pool_eligible: false,
      source_documents:selectedDocument?[selectedDocument]:[] };
    selectedIdRef.current = null;
    setReviewTargetId(undefined);setGeneratedDraft(draft);
    updateFormFromDraft(draft);
    setSelectedId(null);
    setDetail(null);
    setPreviewArtifact(null);
    setIsDraft(true);
    setDetailState("ready");
    setDetailError(null);
  }, [selectedMaterial, selectedDocument, updateFormFromDraft]);

  const handleGenerateDraft = useCallback(async () => {
    const materialId =
      selectedMaterialId ||
      materialSources.find((source) => source.extension === ".md")?.material_id ||
      "";
    if (!materialId) {
      setDetailError(t("pages.evidence.errors.selectMaterial"));
      return;
    }
    setDraftState("generating");
    setDetailError(null);
    try {
      const result = await generateEvidenceDraft([materialId],selectedDocument?.document_id);
      if (!result.draft) {
        setDetailError(result.message);
        setDraftState("idle");
        return;
      }
      setReviewTargetId(undefined);setGeneratedDraft(result.draft);
      updateFormFromDraft(result.draft);
      setSelectedId(null);
      setDetail(null);
      setPreviewArtifact(null);
      setIsDraft(true);
      setDetailState("ready");
      setDraftState("idle");
      notify("info", t("toasts.evidence.draftGenerated"));
    } catch (nextError) {
      setDraftState("idle");
      setDetailError(getErrorMessage(nextError));
    }
  }, [materialSources, selectedMaterialId, selectedDocument, t, updateFormFromDraft]);

  const handleSaveReviewedDraft = useCallback(
    async (saveMode: "incomplete" | "eligible") => {
      if (!generatedDraft || detailState!=="ready") return;
      setSaveState("saving");
      setDetailError(null);
      try {
        const result = await saveEvidenceDraft({
          draft: draftFromForm(generatedDraft),
          evidence_id: reviewTargetId,
          expected_sha256: reviewTargetId ? detail?.source_sha256 : undefined,
          save_mode: saveMode,
          review: { decision: "approved", reviewed_at: new Date().toISOString(), merge_sources: Boolean(generatedDraft.field_sources?.length) },
        });
        setGeneratedDraft(null);setReviewTargetId(undefined);
        await loadEvidence(result.evidence_id);
        setSaveState("saved");
        notify("success", t("toasts.evidence.draftSaved"));
      } catch (nextError) {
        setSaveState("idle");
        setDetailError(getErrorMessage(nextError));
      }
    },
    [draftFromForm, generatedDraft, loadEvidence, reviewTargetId, detailState, detail]
  );

  const handleSave = useCallback(async () => {
    if (!form.title.trim()) {
      setDetailError(t("pages.evidence.errors.titleRequired"));
      setSaveState("idle");
      return;
    }
    const payload = {
      title: form.title.trim(),
      time_range: form.time_range,
      context: form.context,
      role_scope: form.role_scope,
      actions: form.actions,
      results: form.results,
      stack: parseCommaList(form.stackText),
      tags: parseCommaList(form.tagsText),
    };
    setSaveState("saving");
    setDetailError(null);
    try {
      if (isDraft || !selectedId) {
        const created = await createEvidence(payload);
        await loadEvidence(created.evidence_id);
      } else {
        await updateEvidence(selectedId, payload);
        await loadEvidence(selectedId);
      }
      setSaveState("saved");
      notify("success", t("toasts.evidence.saved"));
    } catch (nextError) {
      setSaveState("idle");
      setDetailError(getErrorMessage(nextError));
    }
  }, [form, isDraft, loadEvidence, selectedId, t]);

  const handleDelete = useCallback(async () => {
    if (!selectedId || isDraft) return;
    const confirmed = await confirmAction({
      title: t("confirmations.evidence.deleteCard.title"),
      description: t("confirmations.evidence.deleteCard.description"),
      confirmLabel: t("confirmations.evidence.deleteCard.confirm"),
      tone: "danger",
    });
    if (!confirmed) return;
    setDeleteState("deleting");
    setDetailError(null);
    try {
      await deleteEvidence(selectedId);
      setDeleteState("idle");
      await loadEvidence();
      notify("success", t("toasts.evidence.deleted"));
    } catch (nextError) {
      setDeleteState("idle");
      setDetailError(getErrorMessage(nextError));
    }
  }, [isDraft, loadEvidence, selectedId]);

  const handleImport = useCallback(
    async (mode: EvidenceImportMode = importMode) => {
      const sourcePath = importPath.trim();
      if (!sourcePath) {
        setDetailError(t("pages.evidence.errors.sourcePathRequired"));
        return;
      }
      if (mode !== "create" && !selectedId) {
        setDetailError(t("pages.evidence.errors.selectEvidence"));
        return;
      }

      setImportState("importing");
      setDetailError(null);
      try {
        const result = await importEvidence({
          source_paths: [sourcePath],
          mode,
          target_evidence_id: mode === "create" ? null : selectedId,
        });
        setImportPath("");
        setImportMode("append");
        setImportState("idle");
        await loadEvidence(result.evidence_id);
        notify("success", t("toasts.evidence.imported"));
      } catch (nextError) {
        setImportState("idle");
        setDetailError(getErrorMessage(nextError));
      }
    },
    [importMode, importPath, loadEvidence, selectedId, t]
  );

  const handleArtifactDelete = useCallback(
    async (resourceId: string) => {
      if (!selectedId || !detail) return;
      const confirmed = await confirmAction({
        title: t("confirmations.evidence.deleteArtifact.title"),
        description: t("confirmations.evidence.deleteArtifact.description"),
        confirmLabel: t("confirmations.evidence.deleteArtifact.confirm"),
        tone: "danger",
      });
      if (!confirmed) return;
      const remainingArtifacts = detail.artifacts
        .map((artifact) => artifact.resource_id ?? "")
        .filter((artifactId) => artifactId && artifactId !== resourceId);

      setSaveState("saving");
      setDetailError(null);
      try {
        await updateEvidence(selectedId, { artifacts: remainingArtifacts });
        await loadEvidence(selectedId);
        setSaveState("saved");
        notify("success", t("toasts.evidence.artifactRemoved"));
      } catch (nextError) {
        setSaveState("idle");
        setDetailError(getErrorMessage(nextError));
      }
    },
    [detail, loadEvidence, selectedId]
  );

  const renderStatus = (status: string) => {
    const normalized = status || "ready";
    const label =
      normalized === "ready"
        ? t("pages.evidence.status.ready")
        : t(`pages.evidence.status.${normalized}`, { defaultValue: normalized });
    return (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone(
          normalized
        )}`}
      >
        {label}
      </span>
    );
  };

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
            onClick={() => setPreviewArtifact(artifact)}
            type="button"
            title={t("pages.evidence.artifacts.preview")}
          >
            <FileUp size={15} />
          </button>
          <button
            className="rounded-card border border-border p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
            type="button"
            title={t("pages.evidence.artifacts.reupload")}
            onClick={() => setImportMode("replace")}
          >
            <RotateCcw size={15} />
          </button>
          <button
            className="rounded-card border border-error/40 p-2 text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!resourceId || isBusy}
            onClick={() => void handleArtifactDelete(resourceId)}
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

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void loadEvidence();
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [loadEvidence]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.evidence.title")}</h1>
          <p className="page-subtitle">{t("pages.evidence.subtitle")}</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="page-icon-button"
            disabled={isBusy || refreshing}
            onClick={() => void loadEvidence()}
            title={t("common.refreshShortcut")}
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            <span className="sr-only">{refreshing ? t("common.refreshing") : t("pages.evidence.actions.refresh")}</span>
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isBusy}
            onClick={() => {
              setImportMode(selectedId ? "append" : "create");
              void handleImport(selectedId ? "append" : "create");
            }}
            type="button"
          >
            <Upload size={16} />
            {importState === "importing"
              ? t("pages.evidence.actions.importing")
              : t("pages.evidence.actions.import")}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isBusy}
            onClick={handleCreateDraft}
            type="button"
          >
            <Plus size={16} />
            {t("pages.evidence.actions.new")}
          </button>
        </div>
      </header>

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

      {loadState === "ready" ? (
        <>
          <section className="stat-strip" data-testid="evidence-stats">
            {[
              ["total", evidenceStats.total],
              ["ready", evidenceStats.ready],
              ["gaps", evidenceStats.gaps],
              ["artifacts", evidenceStats.artifacts],
            ].map(([key, value]) => (
              <span key={key}>
                <strong>{value}</strong>
                {t(`pages.evidence.stats.${key}`)}
              </span>
            ))}
          </section>


          <details
            className="fold-section rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]"
            open={items.length === 0}
            data-testid="evidence-material-fold"
          >
            <summary>
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-3">
                <h2 className="text-base font-semibold text-text-primary">
                  {t("pages.evidence.materialSources.title")}
                </h2>
                <span className="text-sm font-normal text-text-secondary">
                  {t("pages.evidence.materialSources.count", { count: materialSources.length })} · {t("pages.evidence.materialSources.summaryHint")}
                </span>
              </span>
            </summary>
            <div className="px-5 pb-5">
            {materialSources.length > 0 ? (
            <>
            <div className="flex flex-wrap items-center gap-3">
              <select
                className="min-w-[220px] rounded-card border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                disabled={isBusy || materialSources.length === 0}
                onChange={(event) => setSelectedMaterialId(event.target.value)}
                value={selectedMaterialId}
              >
                <option value="">
                  {t("pages.evidence.materialSources.selectPlaceholder")}
                </option>
                {materialSources.map((source) => (
                  <option
                    key={source.material_id}
                    disabled={![".md", ".txt"].includes(source.extension)}
                    value={source.material_id}
                  >
                    {source.label || source.filename}
                  </option>
                ))}
              </select>
              <button
                className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isBusy || !selectedMaterialId || !selectedDocument}
                onClick={() => void handleGenerateDraft()}
                type="button"
              >
                <Sparkles size={16} />
                {draftState === "generating"
                  ? t("pages.evidence.actions.generatingDraft")
                  : t("pages.evidence.actions.generateDraft")}
              </button>
              <button type="button" disabled={isBusy || !selectedMaterial || ![".md", ".txt"].includes(selectedMaterial.extension)}
                className="rounded-card border border-border px-4 py-2 text-sm text-text-primary disabled:opacity-50"
                onClick={handleManualDraft}>{t("pages.evidence.actions.manualDraft")}</button>
            </div>
            <MaterialDocumentPicker materialId={selectedMaterialId} onSelect={setSelectedDocument} disabled={isBusy}/>
            </>
            ) : null}
            {materialSources.length === 0 ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-bg-primary/30 p-4 text-sm text-text-secondary">
                <span>{t("pages.evidence.materialSources.empty")}</span>
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
                  onClick={() => {
                    if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
                      window.dispatchEvent(new CustomEvent("pipf:navigate", { detail: "/resumes" }));
                    }
                  }}
                >
                  {t("pages.evidence.materialSources.goUpload")}
                </button>
              </div>
            ) : !selectedDocument ? (
              <p className="mt-3 text-xs text-text-muted">{t("pages.evidence.materialSources.stepsHint")}</p>
            ) : null}
            </div>
          </details>

          <details
            className="fold-section rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]"
            data-testid="evidence-reconcile-fold"
            onToggle={(event) => {
              if ((event.currentTarget as HTMLDetailsElement).open && !reconcile && reconcileState !== "running") void runReconcile();
            }}
          >
            <summary>
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-3">
                <h2 className="text-base font-semibold text-text-primary">{t("pages.evidence.reconcile.title")}</h2>
                <span className="text-sm font-normal text-text-secondary">
                  {reconcile
                    ? t("pages.evidence.reconcile.summaryLine", {
                        eligible: reconcile.summary.eligible,
                        incomplete: reconcile.summary.incomplete,
                        legacy: reconcile.summary.legacy,
                        untraceable: reconcile.summary.untraceable_cards,
                        missingTime: reconcile.summary.missing_time_range,
                        duplicates: reconcile.summary.duplicate_cards,
                      })
                    : t("pages.evidence.reconcile.hint")}
                </span>
              </span>
            </summary>
            <div className="space-y-3 px-5 pb-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-text-muted">{t("pages.evidence.reconcile.scope")}</p>
                <button
                  aria-label={t("pages.evidence.reconcile.run")}
                  className="page-icon-button"
                  data-testid="evidence-reconcile-run"
                  disabled={reconcileState === "running"}
                  onClick={() => void runReconcile()}
                  title={t("pages.evidence.reconcile.run")}
                  type="button"
                >
                  <RefreshCw className={reconcileState === "running" ? "animate-spin" : ""} size={15} />
                </button>
              </div>
              {reconcileState === "error" && reconcileError ? <p className="text-sm text-error">{reconcileError}</p> : null}
              {reconcile && reconcileProblems.length === 0 ? (
                <p className="text-sm text-text-secondary">{t("pages.evidence.reconcile.clean")}</p>
              ) : null}
              {reconcile && reconcileProblems.length > 0 ? (
                <ul className="divide-y divide-border" data-testid="evidence-reconcile-list">
                  {reconcileProblems.slice(0, 30).map((item) => (
                    <li className="flex items-start justify-between gap-3 py-2" key={item.evidence_id}>
                      <div className="min-w-0">
                        <p className="truncate text-sm text-text-primary">
                          {item.title || item.evidence_id}
                          <span className="ml-2 text-xs text-text-muted">{t(`pages.evidence.reconcile.pool.${item.pool_status}`, { defaultValue: item.pool_status })}</span>
                        </p>
                        <p className="mt-0.5 text-xs text-text-muted">{reconcileReasons(item).join(" · ")}</p>
                      </div>
                      <button
                        className="shrink-0 rounded-card border border-border px-3 py-1 text-xs text-text-primary hover:bg-bg-hover"
                        onClick={() => void loadDetail(item.evidence_id)}
                        type="button"
                      >
                        {t("pages.evidence.reconcile.view")}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {reconcile && reconcileProblems.length > 30 ? (
                <p className="text-xs text-text-muted">{t("pages.evidence.reconcile.more", { count: reconcileProblems.length - 30 })}</p>
              ) : null}
            </div>
          </details>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_420px]">
            <section className="overflow-hidden rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
              <div className="border-b border-border px-5 py-4">
                <div className="flex items-baseline gap-3">
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.evidence.listTitle")}
                  </h2>
                  <p className="text-sm text-text-secondary">
                    {t("pages.evidence.listCount", { count: items.length })}
                  </p>
                </div>
                <form
                  className="mt-3 flex flex-wrap items-center gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    applyFilters();
                  }}
                >
                  <label className="relative min-w-[220px] flex-1">
                    <Search
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                      size={16}
                    />
                    <input
                      className="w-full rounded-card border border-border bg-bg-hover py-2 pl-9 pr-3 text-sm text-text-primary outline-none focus:border-accent"
                      onChange={(event) => setQueryInput(event.target.value)}
                      placeholder={t("pages.evidence.filters.queryPlaceholder")}
                      type="text"
                      value={queryInput}
                    />
                  </label>
                  <select
                    className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    aria-label={t("pages.evidence.fields.status")}
                    onChange={(event) => setStatusInput(event.target.value)}
                    value={statusInput}
                  >
                    <option value="">{t("pages.evidence.filters.allStatuses")}</option>
                    <option value="ready">{t("pages.evidence.status.ready")}</option>
                    <option value="draft">{t("pages.evidence.status.draft")}</option>
                    <option value="gap">{t("pages.evidence.status.gap")}</option>
                  </select>
                  <input
                    className="w-36 rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) => setRoleInput(event.target.value)}
                    placeholder={t("pages.evidence.filters.rolePlaceholder")}
                    type="text"
                    value={roleInput}
                  />
                  <input
                    className="w-44 rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) => setTagInput(event.target.value)}
                    placeholder={t("pages.evidence.filters.tagsPlaceholder")}
                    type="text"
                    value={tagInput}
                  />
                  <button
                    className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
                    type="submit"
                  >
                    {t("pages.evidence.actions.apply")}
                  </button>
                  <button
                    className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
                    onClick={resetFilters}
                    type="button"
                  >
                    {t("pages.evidence.actions.reset")}
                  </button>
                </form>
              </div>

              {items.length === 0 ? (
                <div className="p-8 text-sm text-text-secondary">
                  {t("pages.evidence.empty.list")}
                </div>
              ) : (
                <div className="max-h-[calc(100vh-20rem)] overflow-auto">
                  <table className="w-full min-w-[640px] table-fixed text-left">
                    <thead className="sticky top-0 z-10 bg-bg-panel text-xs uppercase tracking-[0.14em] text-text-muted">
                      <tr className="bg-bg-hover/70">
                        <th className="w-[40%] px-5 py-3 font-semibold">
                          {t("pages.evidence.fields.title")}
                        </th>
                        <th className="w-[16%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.timeRange")}
                        </th>
                        <th className="w-[20%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.role")}
                        </th>
                        <th className="w-[8%] px-4 py-3 font-semibold">
                          {t("pages.evidence.score")}
                        </th>
                        <th className="w-[16%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.status")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {items.map((item) => {
                        const isSelected = item.evidence_id === selectedId;
                        return (
                          <tr
                            key={item.evidence_id}
                            className={`cursor-pointer transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/40 ${
                              isSelected ? "bg-accent/10" : "hover:bg-bg-hover/50"
                            }`}
                            aria-selected={isSelected}
                            tabIndex={0}
                            onClick={() => void loadDetail(item.evidence_id)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                void loadDetail(item.evidence_id);
                              }
                            }}
                          >
                            <td className="px-5 py-4">
                              <p className="truncate text-sm font-medium text-text-primary" title={item.title}>
                                {item.title}
                              </p>
                              <p className="mt-1 truncate font-mono text-xs text-text-muted">
                                {item.evidence_id}
                              </p>
                            </td>
                            <td className="whitespace-nowrap px-4 py-4 text-sm text-text-secondary">
                              {formatFallback(item.time_range)}
                            </td>
                            <td className="px-4 py-4 text-sm text-text-secondary">
                              <p className="truncate" title={formatFallback(item.role_scope)}>
                                {formatFallback(item.role_scope)}
                              </p>
                            </td>
                            <td className="px-4 py-4 text-sm font-semibold text-accent">
                              {item.score}
                            </td>
                            <td className="px-4 py-4">{renderStatus(item.candidate_pool_eligible===false&&["ready","pass"].includes(item.status)?"needs_review":item.status)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto">
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
                      disabled={!selectedId || detailState !== "ready" || isBusy}
                      onClick={() => setEditMode(true)}
                      type="button"
                    >
                      {t("pages.evidence.actions.edit")}
                    </button>
                  ) : null}
                  {editMode && !isDraft && !generatedDraft && !reviewTargetId ? (
                    <button
                      className="rounded-card border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-bg-hover"
                      onClick={() => {
                        setEditMode(false);
                        setForm(toForm(detail));
                      }}
                      type="button"
                    >
                      {t("pages.evidence.actions.cancelEdit")}
                    </button>
                  ) : null}
                  {editing ? (
                  <button
                    className="rounded-card border border-border p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isBusy || detailState!=="ready"}
                    onClick={() =>
                      generatedDraft
                        ? void handleSaveReviewedDraft("eligible")
                        : void handleSave()
                    }
                    title={t("pages.evidence.actions.save")}
                    aria-label={t("pages.evidence.actions.save")}
                    type="button"
                  >
                    <SaveIcon size={16} />
                  </button>
                  ) : null}
                  <button
                    className="rounded-card border border-error/50 p-2 text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!selectedId || isDraft || deleteState === "deleting"}
                    onClick={() => void handleDelete()}
                    title={t("pages.evidence.actions.delete")}
                    aria-label={t("pages.evidence.actions.delete")}
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
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
                  {!!detail?.source_error&&<p role="alert" className="text-sm text-warning">{t('sourceMerge.changed')}</p>}
                  {!generatedDraft && !!detail?.source_material_ids?.length && <button type="button" disabled={isBusy} className="rounded-card border border-accent px-3 py-2 text-sm text-accent" onClick={()=>{setReviewTargetId(detail.evidence_id);setGeneratedDraft({title:form.title,context:form.context,time_range:form.time_range,role_scope:form.role_scope,actions:form.actions,results:form.results,stack:parseCommaList(form.stackText),tags:parseCommaList(form.tagsText),source_material_ids:detail.source_material_ids!,source_documents:detail.source_documents||[],field_sources:detail.field_sources||[],artifacts:detail.source_material_ids!.map(id=>({type:'text_document',ref:id,label:id})),status:'draft_ready_for_review',candidate_pool_eligible:false});}}>{t('materialDocument.reReview')}</button>}
                  {generatedDraft ? (
                    <section className="rounded-card border border-success/40 bg-success/10 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-text-primary">
                            {t("pages.evidence.review.title")}
                          </p>
                          <p className="mt-1 text-xs text-text-secondary">
                            {t("pages.evidence.review.source", {
                              count: generatedDraft.source_material_ids.length,
                            })}
                          </p>
                        </div>
                        {renderStatus(
                          reviewMissingItems.length
                            ? "draft_incomplete"
                            : "draft_ready_for_review"
                        )}
                      </div>
                      {reviewMissingItems.length ? (
                        <p className="mt-3 text-xs text-warning">
                          {t("pages.evidence.review.missing", {
                            items: reviewMissingItems.join(", "),
                          })}
                        </p>
                      ) : (
                        <p className="mt-3 text-xs text-success">
                          {t("pages.evidence.review.eligible")}
                        </p>
                      )}
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        <button
                          className="rounded-card border border-border px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={isBusy}
                          onClick={() => void handleSaveReviewedDraft("incomplete")}
                          type="button"
                        >
                          {t("pages.evidence.actions.saveIncomplete")}
                        </button>
                        <button
                          className="rounded-card border border-success bg-success px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={isBusy}
                          onClick={() => void handleSaveReviewedDraft("eligible")}
                          type="button"
                        >
                          {t("pages.evidence.actions.saveEligible")}
                        </button>
                      </div>
                    </section>
                  ) : null}

                  {generatedDraft&&reviewTargetId&&<EvidenceSourceMerge key={reviewTargetId} draft={draftFromForm(generatedDraft)} materials={materialSources} disabled={isBusy} onChange={draft=>{setGeneratedDraft(draft);updateFormFromDraft(draft);}}/>}
                  {!editing&&!!detail?.field_sources?.length&&<details className="rounded-card border border-border p-3"><summary className="cursor-pointer text-sm text-accent">{t('sourceMerge.bound')}</summary>{detail.field_sources.map((s,i)=><p key={i} className="mt-2 whitespace-pre-wrap break-words text-xs text-text-secondary">{s.value}<br/>{detail.source_documents?.find(d=>d.document_id===s.document_id&&d.material_id===s.material_id)?.label}</p>)}</details>}
                  {!editing ? (
                    <div className="space-y-4" data-testid="evidence-detail-view">
                      <div>
                        <h3 className="text-lg font-semibold text-text-primary">{form.title || t("pages.evidence.fields.title")}</h3>
                        <p className="mt-1 text-sm text-text-secondary">{[form.time_range, form.role_scope].filter(Boolean).join(" · ") || "--"}</p>
                      </div>
                      {(
                        [
                          ["context", form.context, "text-text-primary"],
                          ["actions", form.actions, "text-text-primary"],
                          ["results", form.results, "text-success"],
                        ] as const
                      ).map(([field, value, className]) => (
                        <div key={field}>
                          <p className="text-xs uppercase tracking-[0.16em] text-text-muted">{t(`pages.evidence.fields.${field}`)}</p>
                          <p className={`mt-1 whitespace-pre-wrap break-words text-sm ${className}`}>{value || "--"}</p>
                        </div>
                      ))}
                      {form.stackText || form.tagsText ? (
                        <div className="flex flex-wrap gap-2">
                          {parseCommaList(`${form.stackText},${form.tagsText}`).map((item) => (
                            <span key={item} className="rounded-chip border border-border bg-bg-hover px-2.5 py-1 text-xs text-text-secondary">
                              {item}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {editing ? (
                  <>
                  <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
                    <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
                      {t("pages.evidence.fields.title")}
                    </span>
                    <input
                      className="mt-2 w-full bg-transparent text-base font-semibold text-text-primary outline-none"
                      disabled={isBusy}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          title: event.target.value,
                        }))
                      }
                      placeholder={t("pages.evidence.fields.title")}
                      type="text"
                      value={form.title}
                    />
                  </label>

                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                    <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
                      <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
                        {t("pages.evidence.fields.timeRange")}
                      </span>
                      <input
                        className="mt-2 w-full bg-transparent text-sm text-text-primary outline-none"
                        disabled={isBusy}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            time_range: event.target.value,
                          }))
                        }
                        type="text"
                        value={form.time_range}
                      />
                    </label>
                    <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
                      <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
                        {t("pages.evidence.fields.role")}
                      </span>
                      <input
                        className="mt-2 w-full bg-transparent text-sm text-text-primary outline-none"
                        disabled={isBusy}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            role_scope: event.target.value,
                          }))
                        }
                        type="text"
                        value={form.role_scope}
                      />
                    </label>
                  </div>

                  {[
                    ["context", "min-h-20"],
                    ["actions", "min-h-24"],
                    ["results", "min-h-24 text-success"],
                  ].map(([field, className]) => (
                    <label
                      key={field}
                      className="block rounded-card border border-border bg-bg-hover/50 p-3"
                    >
                      <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
                        {t(`pages.evidence.fields.${field}`)}
                      </span>
                      <textarea
                        className={`mt-2 w-full resize-y bg-transparent text-sm outline-none ${className}`}
                        disabled={isBusy}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            [field]: event.target.value,
                          }))
                        }
                        value={form[field as keyof EvidenceForm]}
                      />
                    </label>
                  ))}

                  <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
                    <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
                      {t("pages.evidence.fields.stackTags")}
                    </span>
                    <input
                      className="mt-2 w-full bg-transparent text-sm text-text-primary outline-none"
                      disabled={isBusy}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          stackText: event.target.value,
                        }))
                      }
                      type="text"
                      value={form.stackText}
                    />
                    <input
                      className="mt-3 w-full bg-transparent text-sm text-text-secondary outline-none"
                      disabled={isBusy}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          tagsText: event.target.value,
                        }))
                      }
                      placeholder={t("pages.evidence.fields.tags")}
                      type="text"
                      value={form.tagsText}
                    />
                  </label>
                  </>
                  ) : null}

                  <section className="rounded-card border border-border bg-bg-hover/50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-text-primary">
                          {t("pages.evidence.artifacts.title")}
                        </h3>
                        <p className="mt-1 text-xs text-text-secondary">
                          {t("pages.evidence.artifacts.size", {
                            count:
                              generatedDraft?.artifacts.length ??
                              detail?.artifacts.length ??
                              0,
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
                      ) : detail?.artifacts.length ? (
                        detail.artifacts.map(renderArtifact)
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
                        onChange={(event) => setImportPath(event.target.value)}
                        placeholder={t("pages.evidence.artifacts.sourcePlaceholder")}
                        type="text"
                        value={importPath}
                      />
                      <div className="grid gap-2 sm:grid-cols-[1fr_auto] xl:grid-cols-1">
                        <select
                          className="rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                          onChange={(event) =>
                            setImportMode(event.target.value as EvidenceImportMode)
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
                          disabled={isBusy}
                          onClick={() => void handleImport()}
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
                </div>
              ) : null}
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}
