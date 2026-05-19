import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "react-i18next";
import {
  FileUp,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import {
  createEvidence,
  deleteEvidence,
  getEvidence,
  importEvidence,
  listEvidence,
  updateEvidence,
} from "@/lib/sidecar/api";
import type {
  ArtifactSummary,
  EvidenceDetail,
  EvidenceFilters,
  EvidenceListItem,
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

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;
const DEFAULT_FILTERS: EvidenceFilters = {
  query: "",
  status: null,
  role: null,
  tags: [],
  date_range: null,
};

function recordVerifyEvent(
  event: string,
  details: Record<string, unknown> = {}
) {
  if (verifyScenario !== "evidence") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
}

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
  if (status === "gap" || status === "needs_review") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "draft") {
    return "border-border bg-bg-hover text-text-secondary";
  }
  return "border-accent/40 bg-accent/10 text-accent";
}

function selectedArtifactCount(detail: EvidenceDetail | null): number {
  return detail?.artifacts.length ?? 0;
}

export function EvidencePage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [form, setForm] = useState<EvidenceForm>(() => toForm(null));
  const [isDraft, setIsDraft] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [detailState, setDetailState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [deleteState, setDeleteState] = useState<"idle" | "deleting">("idle");
  const [importState, setImportState] = useState<"idle" | "importing">("idle");
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [evidenceFilters, setEvidenceFilters] =
    useState<EvidenceFilters>(DEFAULT_FILTERS);
  const [queryInput, setQueryInput] = useState("");
  const [statusInput, setStatusInput] = useState("");
  const [roleInput, setRoleInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [importPath, setImportPath] = useState("");
  const [importMode, setImportMode] = useState<EvidenceImportMode>("append");
  const [previewArtifact, setPreviewArtifact] = useState<ArtifactSummary | null>(null);
  const selectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const evidenceStats = useMemo(
    () => ({
      total: items.length,
      ready: items.filter((item) => item.status === "ready" || item.status === "pass")
        .length,
      gaps: items.filter(
        (item) => item.status === "gap" || item.status === "needs_review"
      ).length,
      artifacts: selectedArtifactCount(detail),
    }),
    [detail, items]
  );

  const isBusy =
    saveState === "saving" ||
    deleteState === "deleting" ||
    importState === "importing";

  const loadDetail = useCallback(async (evidenceId: string) => {
    selectedIdRef.current = evidenceId;
    setSelectedId(evidenceId);
    setDetailState("loading");
    setDetailError(null);

    try {
      const result = await getEvidence(evidenceId);
      if (selectedIdRef.current !== evidenceId) return null;
      setDetail(result.evidence);
      setPreviewArtifact(result.evidence.artifacts[0] ?? null);
      setForm(toForm(result.evidence));
      setIsDraft(false);
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

  const loadEvidence = useCallback(
    async (preferredEvidenceId?: string | null) => {
      setLoadState("loading");
      setError(null);
      try {
        const result = await listEvidence(evidenceFilters);
        setItems(result.items);
        const preferredItem =
          result.items.find(
            (item) =>
              item.evidence_id === (preferredEvidenceId ?? selectedIdRef.current)
          ) ?? result.items[0];

        const loadedDetail = preferredItem
          ? await loadDetail(preferredItem.evidence_id)
          : null;
        if (!preferredItem) {
          setSelectedId(null);
          setDetail(null);
          setPreviewArtifact(null);
          setForm(toForm(null));
          setIsDraft(true);
          setDetailState("ready");
        }
        setLoadState("ready");
        recordVerifyEvent("evidence.load.ready", {
          card_count: result.items.length,
          selected_id: preferredItem?.evidence_id ?? null,
          artifact_count: selectedArtifactCount(loadedDetail),
        });
      } catch (nextError) {
        setItems([]);
        setSelectedId(null);
        setDetail(null);
        setPreviewArtifact(null);
        setError(getErrorMessage(nextError));
        setLoadState("error");
        recordVerifyEvent("evidence.load.error", {
          error: getErrorMessage(nextError),
        });
      }
    },
    [evidenceFilters, loadDetail]
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
    setSaveState("idle");
    setImportMode("create");
  }, []);

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
    } catch (nextError) {
      setSaveState("idle");
      setDetailError(getErrorMessage(nextError));
    }
  }, [form, isDraft, loadEvidence, selectedId, t]);

  const handleDelete = useCallback(async () => {
    if (!selectedId || isDraft) return;
    setDeleteState("deleting");
    setDetailError(null);
    try {
      await deleteEvidence(selectedId);
      setDeleteState("idle");
      await loadEvidence();
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
      const remainingArtifacts = detail.artifacts
        .map((artifact) => artifact.resource_id ?? "")
        .filter((artifactId) => artifactId && artifactId !== resourceId);

      setSaveState("saving");
      setDetailError(null);
      try {
        await updateEvidence(selectedId, { artifacts: remainingArtifacts });
        await loadEvidence(selectedId);
        setSaveState("saved");
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
            className="rounded-card border border-error/40 p-2 text-error transition-colors hover:bg-error/10"
            disabled={!resourceId || isBusy}
            onClick={() => void handleArtifactDelete(resourceId)}
            type="button"
            title={t("pages.evidence.artifacts.delete")}
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>
    </div>
    );
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.evidence.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.evidence.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isBusy}
            onClick={() => void loadEvidence()}
            type="button"
          >
            <RefreshCw size={16} />
            {t("pages.evidence.actions.refresh")}
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
          <section className="grid gap-4 lg:grid-cols-4">
            {[
              ["total", evidenceStats.total],
              ["ready", evidenceStats.ready],
              ["gaps", evidenceStats.gaps],
              ["artifacts", evidenceStats.artifacts],
            ].map(([key, value]) => (
              <div
                key={key}
                className="rounded-panel border border-border bg-bg-panel p-4 shadow-[var(--shadow-panel)]"
              >
                <p className="text-xs uppercase tracking-[0.16em] text-text-muted">
                  {t(`pages.evidence.stats.${key}`)}
                </p>
                <p className="mt-2 text-2xl font-semibold text-text-primary">
                  {value}
                </p>
              </div>
            ))}
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-4 shadow-[var(--shadow-panel)]">
            <div className="grid gap-3 xl:grid-cols-[minmax(240px,1.4fr)_180px_180px_minmax(220px,1fr)_auto_auto]">
              <label className="relative">
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
                onChange={(event) => setStatusInput(event.target.value)}
                value={statusInput}
              >
                <option value="">{t("pages.evidence.filters.allStatuses")}</option>
                <option value="ready">{t("pages.evidence.status.ready")}</option>
                <option value="draft">{t("pages.evidence.status.draft")}</option>
                <option value="gap">{t("pages.evidence.status.gap")}</option>
              </select>
              <input
                className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                onChange={(event) => setRoleInput(event.target.value)}
                placeholder={t("pages.evidence.filters.rolePlaceholder")}
                type="text"
                value={roleInput}
              />
              <input
                className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                onChange={(event) => setTagInput(event.target.value)}
                placeholder={t("pages.evidence.filters.tagsPlaceholder")}
                type="text"
                value={tagInput}
              />
              <button
                className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
                onClick={applyFilters}
                type="button"
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
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <section className="overflow-hidden rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.evidence.listTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.evidence.listCount", { count: items.length })}
                  </p>
                </div>
              </div>

              {items.length === 0 ? (
                <div className="p-8 text-sm text-text-secondary">
                  {t("pages.evidence.empty.list")}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full table-fixed text-left">
                    <thead className="bg-bg-hover/70 text-xs uppercase tracking-[0.14em] text-text-muted">
                      <tr>
                        <th className="w-[36%] px-5 py-3 font-semibold">
                          {t("pages.evidence.fields.title")}
                        </th>
                        <th className="w-[18%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.timeRange")}
                        </th>
                        <th className="w-[20%] px-4 py-3 font-semibold">
                          {t("pages.evidence.fields.role")}
                        </th>
                        <th className="w-[10%] px-4 py-3 font-semibold">
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
                            className={`cursor-pointer transition-colors ${
                              isSelected ? "bg-accent/10" : "hover:bg-bg-hover/50"
                            }`}
                            onClick={() => void loadDetail(item.evidence_id)}
                          >
                            <td className="px-5 py-4">
                              <p className="truncate text-sm font-medium text-text-primary">
                                {item.title}
                              </p>
                              <p className="mt-1 text-xs text-text-muted">
                                {item.evidence_id}
                              </p>
                            </td>
                            <td className="px-4 py-4 text-sm text-text-secondary">
                              {formatFallback(item.time_range)}
                            </td>
                            <td className="px-4 py-4 text-sm text-text-secondary">
                              {formatFallback(item.role_scope)}
                            </td>
                            <td className="px-4 py-4 text-sm font-semibold text-accent">
                              {item.score}
                            </td>
                            <td className="px-4 py-4">{renderStatus(item.status)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.evidence.sections.detail")}
                  </h2>
                  <p className="mt-1 font-mono text-xs text-text-muted">
                    {selectedId ?? (isDraft ? "draft" : "--")}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-card border border-border p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isBusy}
                    onClick={() => void handleSave()}
                    title={t("pages.evidence.actions.save")}
                    type="button"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    className="rounded-card border border-error/50 p-2 text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!selectedId || isDraft || deleteState === "deleting"}
                    onClick={() => void handleDelete()}
                    title={t("pages.evidence.actions.delete")}
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

                  <section className="rounded-card border border-border bg-bg-hover/50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-text-primary">
                          {t("pages.evidence.artifacts.title")}
                        </h3>
                        <p className="mt-1 text-xs text-text-secondary">
                          {t("pages.evidence.artifacts.size", {
                            count: detail?.artifacts.length ?? 0,
                          })}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2">
                      {detail?.artifacts.length ? (
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
                    <div className="mt-3 grid gap-2">
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
                  </section>

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
