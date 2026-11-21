import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getErrorMessage } from "@/lib/errors";
import { confirmAction, notify } from "@/lib/ui";
import type { MaterialDocumentRef } from "@/lib/sidecar/api";
import {
  confirmEvidenceInference,
  createEvidence,
  deleteEvidence,
  generateEvidenceDraft,
  getEvidence,
  importEvidence,
  inferEvidenceFields,
  listEvidenceMaterialSources,
  listEvidence,
  reconcileEvidence,
  saveEvidenceDraft,
  setEvidenceTriage,
  updateEvidence,
} from "@/lib/sidecar/api";
import type {
  ArtifactSummary,
  EvidenceDraftPayload,
  EvidenceDetail,
  EvidenceFilters,
  EvidenceInferenceCandidate,
  EvidenceInferenceResult,
  EvidenceListItem,
  EvidenceReconcileItem,
  EvidenceReconcileResult,
  EvidenceTriageDecision,
  MaterialSourceItem,
} from "@/lib/sidecar/types";
import {
  DEFAULT_FILTERS,
  buildProblemTags,
  buildSummaryCounts,
  filterEvidenceItems,
  parseCommaList,
  toForm,
} from "./evidence-helpers";
import type {
  EvidenceForm,
  EvidenceImportMode,
  LoadState,
  ProblemFilter,
  SaveState,
} from "./evidence-helpers";
import { hasSourceAppend } from "./source-merge";


export function useEvidencePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // 允许从总览等页面带 ?status=gap 直接进入已筛选列表。
  const initialStatus = searchParams.get("status") ?? "";
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  // 列表单次最多取 100 张（后端上限）；超出时列表与对账全量计数会不一致，需要明示。
  const [listTruncated, setListTruncated] = useState(false);
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

  const isBusy =
    saveState === "saving" ||
    draftState === "generating" ||
    deleteState === "deleting" ||
    importState === "importing";
  const selectedMaterial = materialSources.find((source) => source.material_id === selectedMaterialId);
  const reviewMissingItems = generatedDraft ? [
    !form.title.trim() && "missing_title",
    (!form.results.length || form.results.some(value => !value.trim())) && "missing_results",
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

  const [inference, setInference] = useState<EvidenceInferenceResult | null>(null);
  const [inferenceState, setInferenceState] = useState<"idle" | "running" | "error">("idle");
  const [inferenceError, setInferenceError] = useState<string | null>(null);
  const [inferenceNotice, setInferenceNotice] = useState("");
  const [inferenceBusy, setInferenceBusy] = useState(false);
  const [inferenceEdits, setInferenceEdits] = useState<Record<string, string>>({});
  const [showLowConfidence, setShowLowConfidence] = useState(false);
  const inferenceByCard = useMemo(
    () => new Map((inference?.cards ?? []).map((card) => [card.card_id, card])),
    [inference],
  );
  const runInference = useCallback(async () => {
    setInferenceState("running");
    setInferenceError(null);
    try {
      setInference(await inferEvidenceFields());
      setInferenceState("idle");
    } catch (reason) {
      setInferenceState("error");
      setInferenceError(getErrorMessage(reason));
    }
  }, []);
  const recordInferenceDecision = useCallback((evidenceId: string, candidateHash: string, cardSha?: string) => {
    setInference((current) => {
      if (!current) return current;
      const cards = current.cards.map((card) => card.card_id === evidenceId
        ? { ...card, card_sha256: cardSha ?? card.card_sha256,
          candidates: card.candidates.filter((entry) => entry.candidate_hash !== candidateHash) }
        : card);
      const candidates = cards.flatMap((card) => card.candidates);
      return { ...current, cards, summary: { ...current.summary,
        candidates: candidates.length,
        cards_with_candidates: cards.filter((card) => card.candidates.length > 0).length,
        time_candidates: candidates.filter((candidate) => candidate.field === "time_range").length,
        role_candidates: candidates.filter((candidate) => candidate.field === "role_scope").length,
      } };
    });
  }, []);
  const handleInferenceDecision = useCallback(async (
    item: EvidenceReconcileItem,
    cardSha: string,
    candidate: EvidenceInferenceCandidate,
    action: "accept" | "reject",
    value?: string,
  ) => {
    setInferenceBusy(true);
    setInferenceError(null);
    try {
      const result = await confirmEvidenceInference({
        evidence_id: item.evidence_id,
        card_sha256: cardSha,
        field: candidate.field,
        action,
        ...(value ? { value } : {}),
      });
      recordInferenceDecision(item.evidence_id, candidate.candidate_hash, result.card_sha256);
      setInferenceNotice(t(action === "accept" ? "pages.evidence.reconcile.inference.accepted" : "pages.evidence.reconcile.inference.rejected"));
      await runReconcile();
      if (selectedIdRef.current === item.evidence_id) await loadDetail(item.evidence_id).catch(() => null);
    } catch (reason) {
      setInferenceError(getErrorMessage(reason));
    } finally {
      setInferenceBusy(false);
    }
  }, [loadDetail, runReconcile, recordInferenceDecision, t]);
  const batchAcceptHighConfidence = useCallback(async () => {
    if (!inference) return;
    setInferenceBusy(true);
    setInferenceError(null);
    setInferenceNotice("");
    const updatedIds = new Set<string>();
    try {
      for (const card of inference.cards) {
        const item = reconcile?.items.find((entry) => entry.evidence_id === card.card_id);
        if (!item) continue;
        let cardSha = card.card_sha256;
        for (const candidate of card.candidates.filter((entry) => (entry.confidence ?? 0) >= 0.5)) {
          const result = await confirmEvidenceInference({
            evidence_id: card.card_id, card_sha256: cardSha,
            field: candidate.field, action: "accept",
          });
          cardSha = result.card_sha256 ?? cardSha;
          recordInferenceDecision(card.card_id, candidate.candidate_hash, cardSha);
          updatedIds.add(card.card_id);
        }
      }
      setInferenceNotice(t("pages.evidence.reconcile.inference.batchAccepted"));
    } catch (reason) {
      setInferenceError(getErrorMessage(reason));
    } finally {
      await runReconcile();
      const currentId = selectedIdRef.current;
      if (currentId && updatedIds.has(currentId)) await loadDetail(currentId).catch(() => null);
      setInferenceBusy(false);
    }
  }, [inference, reconcile, recordInferenceDecision, runReconcile, loadDetail, t]);

  const [problemFilter, setProblemFilter] = useState<ProblemFilter>("all");
  const [materialDrawerOpen, setMaterialDrawerOpen] = useState(false);
  const reconcileItemByCard = useMemo(
    () => new Map((reconcile?.items ?? []).map((item) => [item.evidence_id, item])),
    [reconcile],
  );
  const problemTagsFor = useCallback(
    (evidenceId: string): string[] =>
      buildProblemTags(evidenceId, { reconcileItemByCard, inferenceByCard }),
    [inferenceByCard, reconcileItemByCard]
  );
  // 进入页面自动对账一次；失败后不重试（否则 sidecar 不可用时会变成紧密请求循环），由“重新对账”按钮手动触发。
  const autoReconciledRef = useRef(false);
  useEffect(() => {
    if (loadState !== "ready" || autoReconciledRef.current) return;
    autoReconciledRef.current = true;
    void runReconcile();
  }, [loadState, runReconcile]);
  useEffect(() => {
    if (!materialDrawerOpen || typeof window === "undefined") return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMaterialDrawerOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [materialDrawerOpen]);
  const hasHighConfidenceCandidates = (inference?.cards ?? []).some(
    (card) => card.candidates.some((candidate) => (candidate.confidence ?? 0) >= 0.5),
  );
  const summaryCounts = useMemo(
    () => buildSummaryCounts(t, { itemsLength: items.length, reconcile, inference }),
    [inference, items.length, reconcile, t]
  );
  const filteredItems = useMemo(
    () => filterEvidenceItems(items, problemFilter, problemTagsFor),
    [items, problemFilter, problemTagsFor]
  );

  const changeTriage = useCallback(
    async (item: EvidenceReconcileItem, decision: EvidenceTriageDecision | "") => {
      try {
        await setEvidenceTriage(item.evidence_id, decision, decision === "duplicate" ? { duplicate_of: item.possible_duplicates[0] } : {});
        await runReconcile();
      } catch (reason) {
        notify("error", getErrorMessage(reason));
      }
    },
    [runReconcile]
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
          listEvidence(evidenceFilters, { pageSize: 100 }),
          listEvidenceMaterialSources(),
        ]);
        setItems(result.items);
        setListTruncated(Boolean(result.next_cursor));
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
    const draft: EvidenceDraftPayload = { title: "", context: "", actions: [], results: [],
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
    async (saveMode: "incomplete" | "eligible", factScope?: import("@/lib/sidecar/types").EvidenceFactScopeReview) => {
      if (!generatedDraft || detailState!=="ready") return;
      setSaveState("saving");
      setDetailError(null);
      try {
        const draft = draftFromForm(generatedDraft);
        let mergeSources = false;
        if (reviewTargetId) {
          if (detail?.evidence_id !== reviewTargetId) throw new Error("evidence_review_changed");
          mergeSources = hasSourceAppend(detail, draft);
        }
        if (factScope && (!reviewTargetId || !detail?.source_sha256 || mergeSources || saveMode !== "eligible")) {
          throw new Error("fact_scope_review_required");
        }
        const result = await saveEvidenceDraft({
          draft,
          evidence_id: reviewTargetId,
          expected_sha256: reviewTargetId ? detail?.source_sha256 : undefined,
          save_mode: saveMode,
          review: { decision: "approved", reviewed_at: new Date().toISOString(), merge_sources: mergeSources, ...(factScope ? {fact_scope:factScope} : {}) },
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

  const startRereview = useCallback(() => {
    if (!detail) return;
    setReviewTargetId(detail.evidence_id);
    setGeneratedDraft({
      title: form.title,
      context: form.context,
      time_range: form.time_range,
      role_scope: form.role_scope,
      actions: form.actions,
      results: form.results,
      stack: parseCommaList(form.stackText),
      tags: parseCommaList(form.tagsText),
      source_material_ids: detail.source_material_ids!,
      source_documents: detail.source_documents || [],
      field_sources: detail.field_sources || [],
      artifacts: detail.source_material_ids!.map((id) => ({ type: "text_document", ref: id, label: id })),
      status: "draft_ready_for_review",
      candidate_pool_eligible: false,
    });
  }, [detail, form]);

  const handleMergeChange = useCallback(
    (draft: EvidenceDraftPayload) => {
      setGeneratedDraft(draft);
      updateFormFromDraft(draft);
    },
    [updateFormFromDraft]
  );

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void loadEvidence();
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [loadEvidence]);


  return {
    reviewTargetId,
    selectedDocument,
    setSelectedDocument,
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
  };
}
