import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import {
  createEvidence,
  deleteEvidence,
  getEvidence,
  listEvidence,
  updateEvidence,
} from "@/lib/sidecar/api";
import type { EvidenceDetail, EvidenceListItem } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved";

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

function formatFallback(value: string): string {
  return value.trim() ? value : "--";
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

export function EvidencePage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [form, setForm] = useState<EvidenceForm>(() => toForm(null));
  const [isDraft, setIsDraft] = useState(false);
  const [listState, setListState] = useState<LoadState>("loading");
  const [detailState, setDetailState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [deleteState, setDeleteState] = useState<"idle" | "deleting">("idle");
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);

  const isBusy = saveState === "saving" || deleteState === "deleting";

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const loadDetail = useCallback(async (evidenceId: string) => {
    selectedIdRef.current = evidenceId;
    setSelectedId(evidenceId);
    setDetailState("loading");
    setDetailError(null);

    try {
      const result = await getEvidence(evidenceId);
      if (selectedIdRef.current !== evidenceId) {
        return;
      }
      setDetail(result.evidence);
      setForm(toForm(result.evidence));
      setIsDraft(false);
      setDetailState("ready");
    } catch (error) {
      if (selectedIdRef.current !== evidenceId) {
        return;
      }
      setDetail(null);
      setForm(toForm(null));
      setDetailState("error");
      setDetailError(getErrorMessage(error));
    }
  }, []);

  const loadEvidence = useCallback(async (preferredEvidenceId?: string | null) => {
    setListState("loading");
    setListError(null);

    try {
      const result = await listEvidence();
      setItems(result.items);
      setListState("ready");

      const preferredItem =
        result.items.find(
          (item) => item.evidence_id === (preferredEvidenceId ?? selectedIdRef.current)
        ) ?? result.items[0];

      if (preferredItem) {
        await loadDetail(preferredItem.evidence_id);
      } else {
        setSelectedId(null);
        setDetail(null);
        setForm(toForm(null));
        setIsDraft(true);
        setDetailState("ready");
      }
    } catch (error) {
      setItems([]);
      setListState("error");
      setListError(getErrorMessage(error));
    }
  }, [loadDetail]);

  useEffect(() => {
    void loadEvidence();
  }, [loadEvidence]);

  const handleCreateDraft = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
    setForm(toForm(null));
    setDetailError(null);
    setDetailState("ready");
    setIsDraft(true);
    setSaveState("idle");
  }, []);

  const handleSave = useCallback(async () => {
    if (!form.title.trim()) {
      setDetailError("Title is required.");
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
    } catch (error) {
      setSaveState("idle");
      setDetailError(getErrorMessage(error));
    }
  }, [form, isDraft, loadEvidence, selectedId]);

  const handleDelete = useCallback(async () => {
    if (!selectedId || isDraft) return;
    setDeleteState("deleting");
    setDetailError(null);
    try {
      await deleteEvidence(selectedId);
      await loadEvidence();
      setDeleteState("idle");
    } catch (error) {
      setDeleteState("idle");
      setDetailError(getErrorMessage(error));
    }
  }, [isDraft, loadEvidence, selectedId]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
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
            className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            disabled={isBusy}
            onClick={() => void loadEvidence()}
            type="button"
          >
            {t("common.retry")}
          </button>
          <button
            className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
            disabled={isBusy}
            onClick={handleCreateDraft}
            type="button"
          >
            New Evidence
          </button>
        </div>
      </header>

      {listState === "loading" ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.loading")}
        </section>
      ) : null}

      {listState === "error" ? (
        <section className="rounded-panel border border-error/50 bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{listError}</p>
        </section>
      ) : null}

      {listState === "ready" ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.9fr)]">
          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.evidence.listTitle")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.evidence.listCount", { count: items.length })}
                </p>
              </div>
              <button
                className="rounded-card border border-border px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
                disabled={isBusy}
                onClick={handleCreateDraft}
                type="button"
              >
                New
              </button>
            </div>
            {items.length === 0 ? (
              <div className="p-5 text-sm text-text-secondary">{t("common.empty")}</div>
            ) : (
              <div className="divide-y divide-border">
                {items.map((item) => {
                  const isSelected = item.evidence_id === selectedId;
                  return (
                    <button
                      key={item.evidence_id}
                      className={`flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition-colors ${
                        isSelected ? "bg-accent/10" : "hover:bg-bg-hover/60"
                      }`}
                      disabled={isBusy}
                      onClick={() => void loadDetail(item.evidence_id)}
                      type="button"
                    >
                      <div className="space-y-2">
                        <div>
                          <p className="text-base font-medium text-text-primary">{item.title}</p>
                          <p className="text-xs text-text-muted">{item.evidence_id}</p>
                        </div>
                        <div className="flex flex-wrap gap-2 text-xs text-text-secondary">
                          <span>{formatFallback(item.time_range)}</span>
                          <span>•</span>
                          <span>{formatFallback(item.role_scope)}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-accent">{item.score}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.16em] text-text-muted">
                          {item.status}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.evidence.detailTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {selectedId ?? (isDraft ? "new evidence" : t("common.empty"))}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-card border border-border px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isBusy}
                    onClick={() => void handleSave()}
                    type="button"
                  >
                    {saveState === "saving" ? "Saving..." : "Save"}
                  </button>
                  <button
                    className="rounded-card border border-error/50 px-3 py-2 text-sm text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!selectedId || isDraft || deleteState === "deleting"}
                    onClick={() => void handleDelete()}
                    type="button"
                  >
                    {deleteState === "deleting" ? "Deleting..." : "Delete"}
                  </button>
                </div>
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
              <div className="pt-4">
                <p className="text-sm font-medium text-error">{detailError}</p>
              </div>
            ) : null}

            {detailState === "ready" && (detail || isDraft) ? (
              <div className="space-y-5 pt-4">
                <div>
                  <input
                    className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-xl font-semibold text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, title: event.target.value }))
                    }
                    placeholder="Evidence title"
                    type="text"
                    value={form.title}
                  />
                  <p className="mt-1 text-sm text-text-secondary">
                    {detail?.evidence_id ?? "draft"}
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <label>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.evidence.fields.timeRange")}
                    </p>
                    <input
                      className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                      disabled={isBusy}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, time_range: event.target.value }))
                      }
                      type="text"
                      value={form.time_range}
                    />
                  </label>
                  <label>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.evidence.fields.role")}
                    </p>
                    <input
                      className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                      disabled={isBusy}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, role_scope: event.target.value }))
                      }
                      type="text"
                      value={form.role_scope}
                    />
                  </label>
                </div>

                <label>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.context")}
                  </p>
                  <textarea
                    className="mt-2 min-h-24 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, context: event.target.value }))
                    }
                    value={form.context}
                  />
                </label>

                <label>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.actions")}
                  </p>
                  <textarea
                    className="mt-2 min-h-24 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, actions: event.target.value }))
                    }
                    value={form.actions}
                  />
                </label>

                <label>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.results")}
                  </p>
                  <textarea
                    className="mt-2 min-h-24 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, results: event.target.value }))
                    }
                    value={form.results}
                  />
                </label>

                <label>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.stack")}
                  </p>
                  <input
                    className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, stackText: event.target.value }))
                    }
                    type="text"
                    value={form.stackText}
                  />
                </label>

                <label>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.tags")}
                  </p>
                  <input
                    className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, tagsText: event.target.value }))
                    }
                    type="text"
                    value={form.tagsText}
                  />
                </label>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.artifacts")}
                  </p>
                  {detail?.artifacts.length ? (
                    <div className="mt-3 space-y-2">
                      {detail.artifacts.map((artifact) => (
                        <div
                          key={
                            artifact.resource_id ??
                            artifact.filename ??
                            `${detail.evidence_id}-artifact-${artifact.mime_type ?? "unknown"}`
                          }
                          className="rounded-card border border-border px-3 py-2"
                        >
                          <p className="text-sm text-text-primary">
                            {artifact.filename ?? t("pages.evidence.artifactFallback")}
                          </p>
                          <p className="mt-1 text-xs text-text-secondary">
                            {artifact.mime_type ?? "--"}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-text-secondary">{t("common.empty")}</p>
                  )}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}

      {saveState === "saved" ? (
        <p className="text-sm text-success">Saved.</p>
      ) : null}
    </div>
  );
}
