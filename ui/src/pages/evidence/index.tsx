import { MaterialDocumentPicker } from "./material-document-picker";
import { EvidenceSourceMerge } from "./source-merge-panel";
import type { MaterialDocumentRef } from "@/lib/sidecar/api";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
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
  X,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { confirmAction, notify } from "@/lib/ui";
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

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved";
type EvidenceImportMode = "create" | "append" | "replace";
type ProblemFilter =
  | "all" | "eligible" | "incomplete" | "legacy" | "untraceable"
  | "missing_time" | "duplicate" | "inference" | "needs_fill" | "triaged";

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


export function EvidencePage() {
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
  const candidateKey = (evidenceId: string, candidate: EvidenceInferenceCandidate) =>
    `${evidenceId}:${candidate.field}:${candidate.candidate_hash}`;
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
  const problemTagsFor = useCallback((evidenceId: string): string[] => {
    const tags: string[] = [];
    const item = reconcileItemByCard.get(evidenceId);
    if (item) {
      if (item.untraceable_results.length > 0) tags.push("untraceable");
      if (item.missing_fields.includes("time_range")) tags.push("missing_time");
      if (item.possible_duplicates.length > 0) tags.push("duplicate");
      if (item.triage && !item.triage.stale) tags.push(item.triage.decision === "needs_fill" ? "needs_fill" : "triaged");
    }
    if ((inferenceByCard.get(evidenceId)?.candidates ?? []).length > 0) tags.push("inference");
    return tags;
  }, [inferenceByCard, reconcileItemByCard]);
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
  const summaryCounts = useMemo<{ key: ProblemFilter; label: string; count: number }[]>(() => {
    const summary = reconcile?.summary;
    return [
      { key: "all", label: t("pages.evidence.summary.all"), count: summary?.total ?? items.length },
      { key: "eligible", label: t("pages.evidence.reconcile.pool.eligible"), count: summary?.eligible ?? 0 },
      { key: "incomplete", label: t("pages.evidence.reconcile.pool.incomplete"), count: summary?.incomplete ?? 0 },
      { key: "legacy", label: t("pages.evidence.reconcile.pool.legacy"), count: summary?.legacy ?? 0 },
      { key: "untraceable", label: t("pages.evidence.summary.untraceable"), count: summary?.untraceable_cards ?? 0 },
      { key: "missing_time", label: t("pages.evidence.summary.missingTime"), count: summary?.missing_time_range ?? 0 },
      { key: "duplicate", label: t("pages.evidence.summary.duplicate"), count: summary?.duplicate_cards ?? 0 },
      { key: "inference", label: t("pages.evidence.summary.inference"), count: inference?.summary.candidates ?? 0 },
      { key: "needs_fill", label: t("pages.evidence.summary.needsFill"), count: summary?.needs_fill ?? 0 },
      { key: "triaged", label: t("pages.evidence.summary.triaged"), count: summary?.triaged_out ?? 0 },
    ];
  }, [inference, items.length, reconcile, t]);
  const filteredItems = useMemo(() => {
    if (problemFilter === "all") return items;
    return items.filter((item) => {
      const tags = problemTagsFor(item.evidence_id);
      switch (problemFilter) {
        case "eligible": return item.candidate_pool_eligible === true;
        case "incomplete": return ["saved_incomplete", "needs_review"].includes(item.status);
        case "legacy": return !["saved_eligible", "ready", "pass"].includes(item.status);
        case "untraceable": return tags.includes("untraceable");
        case "missing_time": return tags.includes("missing_time");
        case "duplicate": return tags.includes("duplicate");
        case "inference": return tags.includes("inference");
        case "needs_fill": return tags.includes("needs_fill");
        case "triaged": return tags.includes("triaged");
        default: return true;
      }
    });
  }, [items, problemFilter, problemTagsFor]);

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
            data-testid="evidence-open-drawer"
            disabled={isBusy}
            onClick={() => setMaterialDrawerOpen(true)}
            type="button"
          >
            <Sparkles size={16} />
            {t("pages.evidence.actions.distill")}
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
          <section className="rounded-panel border border-border bg-bg-panel px-4 py-3 shadow-[var(--shadow-panel)]" data-testid="evidence-summary" aria-label={t("pages.evidence.summary.title")}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-1" data-testid="evidence-summary-counts">
                {summaryCounts.map((entry) => (
                  <button
                    aria-pressed={problemFilter === entry.key}
                    className={`rounded-card px-2 py-1 text-xs transition-colors ${problemFilter === entry.key ? "bg-bg-hover text-accent" : "text-text-secondary hover:bg-bg-hover"}`}
                    data-testid={`evidence-summary-${entry.key}`}
                    key={entry.key}
                    onClick={() => setProblemFilter(entry.key)}
                    type="button"
                  >
                    {entry.label}
                    <span className="ml-1 font-mono text-text-primary">{entry.count}</span>
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  className="inline-flex items-center gap-1 rounded-card border border-border px-3 py-1.5 text-xs text-text-primary disabled:opacity-50"
                  data-testid="evidence-reconcile-run"
                  disabled={reconcileState === "running"}
                  onClick={() => void runReconcile()}
                  type="button"
                >
                  <RefreshCw className={reconcileState === "running" ? "animate-spin" : ""} size={13} />
                  {t("pages.evidence.reconcile.run")}
                </button>
                <button
                  className="inline-flex items-center gap-1 rounded-card border border-border px-3 py-1.5 text-xs text-text-primary disabled:opacity-50"
                  data-testid="evidence-inference-run"
                  disabled={inferenceState === "running" || inferenceBusy}
                  onClick={() => void runInference()}
                  type="button"
                >
                  <Sparkles size={13} />
                  {t(inferenceState === "running" ? "pages.evidence.reconcile.inference.running" : "pages.evidence.reconcile.inference.run")}
                </button>
                {hasHighConfidenceCandidates ? (
                  <button
                    className="rounded-card border border-accent bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                    data-testid="evidence-inference-batch"
                    disabled={inferenceBusy}
                    onClick={() => void batchAcceptHighConfidence()}
                    type="button"
                  >
                    {t("pages.evidence.reconcile.inference.batchAccept")}
                  </button>
                ) : null}
              </div>
            </div>
            <p className="mt-2 text-xs text-text-muted" data-testid="evidence-summary-hint">
              {reconcileState === "running"
                ? t("pages.evidence.summary.running")
                : reconcileState === "error" && reconcileError
                  ? reconcileError
                  : inference && !inference.enabled
                    ? t("pages.evidence.reconcile.inference.disabledHint")
                    : t("pages.evidence.summary.hint")}
              {inferenceNotice ? <span className="ml-2 text-success" role="status">{inferenceNotice}</span> : null}
              {inferenceError ? <span className="ml-2 text-error" role="alert">{inferenceError}</span> : null}
            </p>
          </section>
          ) : null}

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <section className="overflow-hidden rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
              <div className="border-b border-border px-5 py-4">
                <div className="flex items-baseline gap-3">
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.evidence.listTitle")}
                  </h2>
                  <p className="text-sm text-text-secondary">
                    {t("pages.evidence.listCount", { count: filteredItems.length })}
                  </p>
                  {listTruncated ? (
                    <p className="text-xs text-warning" data-testid="evidence-list-truncated">
                      {t("pages.evidence.listTruncated", { count: items.length })}
                    </p>
                  ) : null}
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
                    aria-label={t("pages.evidence.summary.filterLabel")}
                    data-testid="evidence-problem-filter"
                    onChange={(event) => setProblemFilter(event.target.value as ProblemFilter)}
                    value={problemFilter}
                  >
                    {summaryCounts.map((entry) => (
                      <option key={entry.key} value={entry.key}>{entry.label}</option>
                    ))}
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

              {filteredItems.length === 0 ? (
                <div className="p-8 text-sm text-text-secondary" data-testid="evidence-list-empty-filter">
                  {t("pages.evidence.empty.filtered")}
                </div>
              ) : (
                <div className="max-h-[calc(100vh-20rem)] overflow-auto">
                  <table className="w-full min-w-[640px] table-fixed text-left">
                    <thead className="sticky top-0 z-10 bg-bg-panel text-xs uppercase tracking-[0.14em] text-text-muted">
                      <tr className="bg-bg-hover/70">
                        <th className="w-[36%] px-5 py-3 font-semibold">
                          {t("pages.evidence.fields.title")}
                        </th>
                        <th className="w-[17%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.timeRange")}
                        </th>
                        <th className="w-[19%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.role")}
                        </th>
                        <th className="w-[8%] px-3 py-3 font-semibold">
                          {t("pages.evidence.fields.sourceCount")}
                        </th>
                        <th className="w-[20%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.status")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredItems.map((item) => {
                        const isSelected = item.evidence_id === selectedId;
                        const tags = problemTagsFor(item.evidence_id);
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
                            </td>
                            <td className="whitespace-nowrap px-4 py-4 text-sm text-text-secondary">
                              <span className="inline-flex items-center gap-1.5">
                                {formatFallback(item.time_range)}
                                <span className="rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{item.time_range_level ?? "L1"}</span>
                              </span>
                            </td>
                            <td className="px-4 py-4 text-sm text-text-secondary">
                              <p className="truncate" title={formatFallback(item.role_scope)}>
                                {formatFallback(item.role_scope)}
                              </p>
                              <span className="mt-0.5 inline-block rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{item.role_scope_level ?? "L1"}</span>
                            </td>
                            <td className="px-3 py-4 text-sm text-text-secondary">
                              {item.source_document_count ? `${item.source_document_count} 份` : "—"}
                            </td>
                            <td className="px-4 py-4">
                              <div className="flex flex-wrap items-center gap-1">
                                {renderStatus(item.candidate_pool_eligible===false&&["ready","pass"].includes(item.status)?"needs_review":item.status)}
                                {tags.slice(0, 3).map((tag) => (
                                  <span key={tag} className="rounded border border-border px-1 py-0.5 text-[10px] text-text-muted">
                                    {t(`pages.evidence.summary.tags.${tag}`, { defaultValue: tag })}
                                  </span>
                                ))}
                                {tags.length > 3 ? <span className="text-[10px] text-text-muted">+{tags.length - 3}</span> : null}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

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
                    className="inline-flex items-center gap-1.5 rounded-card border border-accent bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="evidence-save"
                    disabled={isBusy || detailState!=="ready"}
                    onClick={() =>
                      generatedDraft
                        ? void handleSaveReviewedDraft("eligible")
                        : void handleSave()
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
                  {!editing ? (
                    <div className="space-y-4" data-testid="evidence-detail-view">
                      <div>
                        <h3 className="text-lg font-semibold text-text-primary">{form.title || t("pages.evidence.fields.title")}</h3>
                        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-text-secondary">
                          <span>{form.time_range || "—"}<span className="ml-1 rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{detail?.time_range_provenance?.level ?? "L1"}</span></span>
                          <span>·</span>
                          <span>{form.role_scope || "—"}<span className="ml-1 rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{detail?.role_scope_provenance?.level ?? "L1"}</span></span>
                        </p>
                        {detail?.source_documents?.length ? (
                          <p className="mt-1 truncate text-xs text-text-muted">
                            {t("pages.evidence.fields.sourceMaterials")}：{detail.source_documents.map((doc) => doc.label).join("、")}
                          </p>
                        ) : null}
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

                  {!editing && selectedId && reconcileItemByCard.has(selectedId) ? (() => {
                    const item = reconcileItemByCard.get(selectedId)!;
                    const card = inferenceByCard.get(selectedId);
                    const candidates = card?.candidates ?? [];
                    const cardSha = card?.card_sha256 ?? "";
                    const high = candidates.filter((candidate) => (candidate.confidence ?? 0) >= 0.5);
                    const low = candidates.filter((candidate) => (candidate.confidence ?? 0) < 0.5);
                    const renderCandidate = (candidate: EvidenceInferenceCandidate, lowConfidence = false) => {
                      const key = candidateKey(selectedId, candidate);
                      return (
                        <div className="mt-1 rounded-card border border-border bg-bg-primary/60 px-2 py-1 text-xs" data-testid="evidence-inference-candidate" data-field={candidate.field} key={key}>
                          <p className="text-text-primary">
                            {t(candidate.field === "time_range" ? "pages.evidence.reconcile.inference.time" : "pages.evidence.reconcile.inference.role")}：{candidate.value}
                            <span className="ml-2 text-text-muted">{candidate.level}{typeof candidate.confidence === "number" ? ` · ${candidate.confidence.toFixed(2)}` : ""}{lowConfidence ? ` · ${t("pages.evidence.reconcile.inference.lowConfidence")}` : ""}</span>
                          </p>
                          <p className="mt-0.5 truncate text-text-muted">{(candidate.evidence[0]?.excerpt || candidate.evidence[0]?.key || "").slice(0, 120)}</p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5" role="group" aria-label={t("pages.evidence.reconcile.inference.editLabel")}>
                            <input aria-label={t("pages.evidence.reconcile.inference.editLabel")} className="w-40 rounded-card border border-border bg-bg-primary px-2 py-1 text-xs"
                              value={inferenceEdits[key] ?? candidate.value}
                              onChange={(event) => setInferenceEdits((current) => ({ ...current, [key]: event.target.value }))} />
                            <button type="button" className="rounded-card border border-accent bg-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50" disabled={inferenceBusy}
                              onClick={() => void handleInferenceDecision(item, cardSha, candidate, "accept")}>{t("pages.evidence.reconcile.inference.accept")}</button>
                            <button type="button" className="rounded-card border border-border px-2 py-1 text-xs text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={inferenceBusy}
                              onClick={() => void handleInferenceDecision(item, cardSha, candidate, "accept", inferenceEdits[key] ?? candidate.value)}>{t("pages.evidence.reconcile.inference.acceptEdited")}</button>
                            <button type="button" className="rounded-card border border-warning/60 px-2 py-1 text-xs text-warning hover:bg-warning/10 disabled:opacity-50" disabled={inferenceBusy}
                              onClick={() => void handleInferenceDecision(item, cardSha, candidate, "reject")}>{t("pages.evidence.reconcile.inference.reject")}</button>
                          </div>
                        </div>
                      );
                    };
                    return (
                      <section className="rounded-card border border-warning/40 bg-bg-hover/40 p-3" data-testid="evidence-diagnosis">
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="text-sm font-semibold text-warning">{t("pages.evidence.diagnosis.title")}</h3>
                          <span className="text-[10px] text-text-muted">{t("pages.evidence.diagnosis.hint")}</span>
                        </div>
                        <p className="mt-2 text-xs text-text-secondary">{reconcileReasons(item).join(" · ")}</p>
                        {item.untraceable_results.length ? (
                          <div className="mt-2">
                            <p className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.untraceable")}</p>
                            <ul className="mt-0.5 list-disc pl-4 text-xs text-text-primary">{item.untraceable_results.slice(0, 3).map((row) => <li key={row}>{row}</li>)}</ul>
                          </div>
                        ) : null}
                        {item.verbatim_candidates.length ? (
                          <div className="mt-2">
                            <p className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.verbatim")}</p>
                            <ul className="mt-0.5 space-y-0.5 text-xs text-text-primary">{item.verbatim_candidates.slice(0, 3).map((row) => (
                              <li key={row.result}>{t("pages.evidence.reconcile.preview.verbatimLine", { text: row.verbatim, similarity: row.similarity.toFixed(2) })}</li>
                            ))}</ul>
                          </div>
                        ) : null}
                        {item.date_hints.length ? (
                          <div className="mt-2 flex flex-wrap items-center gap-1">
                            <span className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.dateHints")}</span>
                            {item.date_hints.slice(0, 4).map((hint) => <span className="rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-secondary" key={hint}>{hint}</span>)}
                          </div>
                        ) : null}
                        {item.possible_duplicates.length ? (
                          <p className="mt-2 text-xs text-text-secondary">{t("pages.evidence.reconcile.preview.duplicates", { ids: item.possible_duplicates.join("、") })}</p>
                        ) : null}
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                          <label className="text-[10px] text-text-muted" htmlFor="evidence-triage-select">{t("pages.evidence.reconcile.triage.label")}</label>
                          <select
                            className="w-36 truncate rounded-card border border-border bg-bg-primary px-2 py-1 text-xs"
                            data-testid="evidence-triage-select"
                            id="evidence-triage-select"
                            onChange={(event) => void changeTriage(item, event.target.value as EvidenceTriageDecision | "")}
                            value={item.triage && !item.triage.stale ? item.triage.decision : ""}
                          >
                            <option value="">{t("pages.evidence.reconcile.triage.none")}</option>
                            <option value="needs_fill">{t("pages.evidence.reconcile.triage.needs_fill")}</option>
                            <option value="not_for_display">{t("pages.evidence.reconcile.triage.not_for_display")}</option>
                            {item.possible_duplicates.length > 0 ? (
                              <option value="duplicate">{t("pages.evidence.reconcile.triage.duplicate", { id: item.possible_duplicates[0] })}</option>
                            ) : null}
                          </select>
                        </div>
                        {card && candidates.length ? (
                          <div className="mt-2" data-testid="evidence-inference-candidates">
                            <p className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.diagnosis")} · {t("pages.evidence.reconcile.inference.time")} / {t("pages.evidence.reconcile.inference.role")}</p>
                            {high.map((candidate) => renderCandidate(candidate))}
                            {low.length > 0 ? (showLowConfidence ? (
                              <>
                                {low.map((candidate) => renderCandidate(candidate, true))}
                                <button type="button" className="mt-1 text-xs text-text-muted underline" onClick={() => setShowLowConfidence(false)}>{t("pages.evidence.reconcile.inference.hideLow")}</button>
                              </>
                            ) : (
                              <button type="button" className="mt-1 text-xs text-text-muted underline" data-testid="evidence-inference-show-low" onClick={() => setShowLowConfidence(true)}>
                                {t("pages.evidence.reconcile.inference.showLow", { count: low.length })}
                              </button>
                            )) : null}
                          </div>
                        ) : null}
                      </section>
                    );
                  })() : null}

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
                  {selectedId && !isDraft ? (
                    <div className="mt-4 border-t border-border pt-3">
                      <button
                        className="w-full rounded-card border border-error/60 px-3 py-2 text-sm text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="evidence-delete"
                        disabled={deleteState === "deleting"}
                        onClick={() => void handleDelete()}
                        type="button"
                      >
                        {deleteState === "deleting" ? t("pages.evidence.actions.deleting") : t("pages.evidence.actions.delete")}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </aside>
          </div>
        </>
      ) : null}

      {materialDrawerOpen ? (
        <div
          className="fixed inset-0 z-[var(--z-drawer)] flex justify-end bg-black/50"
          data-testid="evidence-drawer-overlay"
          onClick={(event) => {
            if (event.target === event.currentTarget) setMaterialDrawerOpen(false);
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
                onClick={() => setMaterialDrawerOpen(false)}
                type="button"
              >
                <X size={16} />
              </button>
            </div>
            {materialSources.length === 0 ? (
              <div className="rounded-card border border-border bg-bg-hover/50 p-4 text-sm text-text-secondary">
                <p>{t("pages.evidence.materialSources.empty")}</p>
                <button className="mt-3 text-sm text-accent underline" onClick={() => navigate("/resumes?section=materials")} type="button">
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
                    disabled={isBusy}
                    onChange={(event) => setSelectedMaterialId(event.target.value)}
                    value={selectedMaterialId}
                  >
                    {materialSources.map((source) => (
                      <option key={source.material_id} value={source.material_id} disabled={![".md", ".txt"].includes(source.extension)}>
                        {source.label || source.filename}{source.source_mode === "referenced" ? ` · ${t("pages.evidence.materialSources.referenceBadge", { count: Number(source.file_count) || 0 })}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <MaterialDocumentPicker materialId={selectedMaterialId} onSelect={setSelectedDocument} disabled={isBusy} />
                <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
                  <button
                    className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="evidence-drawer-generate"
                    disabled={isBusy || !selectedMaterialId || !selectedDocument}
                    onClick={() => {
                      void handleGenerateDraft().then(() => setMaterialDrawerOpen(false));
                    }}
                    type="button"
                  >
                    <Sparkles size={16} />
                    {draftState === "generating" ? t("pages.evidence.actions.generatingDraft") : t("pages.evidence.actions.generateDraft")}
                  </button>
                  <button
                    className="rounded-card border border-border px-4 py-2 text-sm text-text-primary disabled:opacity-50"
                    disabled={isBusy || !selectedMaterial || ![".md", ".txt"].includes(selectedMaterial.extension)}
                    onClick={() => {
                      handleManualDraft();
                      setMaterialDrawerOpen(false);
                    }}
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
              <button className="mt-1 text-accent underline" onClick={() => navigate("/system-settings?section=materialSources")} type="button">
                {t("pages.evidence.materialSources.referenceLink")}
              </button>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
