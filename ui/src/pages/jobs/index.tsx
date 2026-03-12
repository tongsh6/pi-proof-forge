import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import {
  convertJobLead,
  createJobProfile,
  deleteJobProfile,
  listJobLeads,
  listJobProfiles,
  updateJobProfile,
} from "@/lib/sidecar/api";
import type {
  JobLeadListItem,
  JobProfileListItem,
  JobProfilesFilters,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type ActionState = "idle" | "creating" | "saving" | "deleting" | "converting";
const DEFAULT_FILTERS: JobProfilesFilters = { status: null, query: "", tags: [] };

const statusOptions = ["active", "draft", "archived"] as const;

function parseTagsInput(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function formatUpdatedAt(value: string, locale: string): string {
  if (!value.trim()) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale);
}

function tone(status: string): string {
  if (status === "active") return "border-accent/40 bg-accent/10 text-accent";
  if (status === "draft") return "border-border bg-bg-hover text-text-secondary";
  if (status === "archived") return "border-warning/40 bg-warning/10 text-warning";
  return "border-border bg-bg-hover text-text-secondary";
}

export function JobsPage() {
  const { t, i18n } = useTranslation();
  const [profiles, setProfiles] = useState<JobProfileListItem[]>([]);
  const [leads, setLeads] = useState<JobLeadListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [actionState, setActionState] = useState<ActionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [statusInput, setStatusInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [filters, setFilters] = useState<JobProfilesFilters>(DEFAULT_FILTERS);
  const [newTitle, setNewTitle] = useState("");
  const [newTags, setNewTags] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editTags, setEditTags] = useState("");
  const [convertingLeadId, setConvertingLeadId] = useState<string | null>(null);

  const loadData = useCallback(async (nextFilters: JobProfilesFilters) => {
    setLoadState("loading");
    setError(null);
    try {
      const [profileResult, leadResult] = await Promise.all([
        listJobProfiles(nextFilters),
        listJobLeads(),
      ]);
      setProfiles(profileResult.items);
      setLeads(leadResult.items);
      setSelectedId((current) => {
        if (current && profileResult.items.some((item) => item.job_profile_id === current)) {
          return current;
        }
        return profileResult.items[0]?.job_profile_id ?? null;
      });
      setLoadState("ready");
    } catch (nextError) {
      setProfiles([]);
      setLeads([]);
      setSelectedId(null);
      setError(getErrorMessage(nextError));
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    void loadData(filters);
  }, [filters, loadData]);

  const selected = useMemo(
    () => profiles.find((item) => item.job_profile_id === selectedId) ?? null,
    [profiles, selectedId]
  );

  useEffect(() => {
    setEditTitle(selected?.title ?? "");
    setEditTags(selected?.keywords.join(", ") ?? "");
  }, [selected]);

  const onApplyFilters = useCallback(() => {
      setFilters({
        status: statusInput || null,
        query: queryInput.trim(),
        tags: parseTagsInput(tagInput),
      });
    }, [queryInput, statusInput, tagInput]);

  const resetFilters = useCallback(() => {
    setQueryInput("");
    setStatusInput("");
    setTagInput("");
    setFilters(DEFAULT_FILTERS);
  }, []);

  const handleCreateProfile = useCallback(async () => {
    if (!newTitle.trim()) {
      setError("Profile title is required.");
      return;
    }
    setActionState("creating");
    setError(null);
    try {
      const created = await createJobProfile({
        title: newTitle.trim(),
        description: "",
        tags: parseTagsInput(newTags),
        status: "draft",
      });
      setNewTitle("");
      setNewTags("");
      resetFilters();
      await loadData(DEFAULT_FILTERS);
      setSelectedId(created.job_profile_id);
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setActionState("idle");
    }
  }, [loadData, newTags, newTitle, resetFilters]);

  const handleSaveProfile = useCallback(async () => {
    if (!selected) return;
    if (!editTitle.trim()) {
      setError("Profile title is required.");
      return;
    }
    setActionState("saving");
    setError(null);
    try {
      await updateJobProfile(selected.job_profile_id, {
        title: editTitle.trim(),
        tags: parseTagsInput(editTags),
        status: selected.status as "active" | "draft" | "archived",
      });
      await loadData(filters);
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setActionState("idle");
    }
  }, [editTags, editTitle, filters, loadData, selected]);

  const handleStatusChange = useCallback(
    async (status: "active" | "draft" | "archived") => {
      if (!selected) return;
      setActionState("saving");
      setError(null);
      try {
        await updateJobProfile(selected.job_profile_id, {
          title: editTitle.trim() || selected.title,
          tags: parseTagsInput(editTags),
          status,
        });
        await loadData(filters);
      } catch (nextError) {
        setError(getErrorMessage(nextError));
      } finally {
        setActionState("idle");
      }
    },
    [editTags, editTitle, filters, loadData, selected]
  );

  const handleDelete = useCallback(async () => {
    if (!selected) return;
    setActionState("deleting");
    setError(null);
    try {
      await deleteJobProfile(selected.job_profile_id);
      await loadData(filters);
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setActionState("idle");
    }
  }, [filters, loadData, selected]);

  const handleConvertLead = useCallback(
    async (jobLeadId: string) => {
      setConvertingLeadId(jobLeadId);
      setError(null);
      try {
        const result = await convertJobLead(jobLeadId);
        resetFilters();
        await loadData(DEFAULT_FILTERS);
        setSelectedId(result.job_profile_id);
      } catch (nextError) {
        setError(getErrorMessage(nextError));
      } finally {
        setConvertingLeadId(null);
      }
    },
    [loadData, resetFilters]
  );

  const isBusy = actionState !== "idle" || convertingLeadId !== null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">{t("pages.jobs.title")}</h1>
          <p className="mt-2 text-sm text-text-secondary">{t("pages.jobs.subtitle")}</p>
        </div>
        <button
          className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-50"
          disabled={isBusy}
          onClick={() => void loadData(filters)}
          type="button"
        >
          {t("common.retry")}
        </button>
      </header>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px_minmax(0,1fr)_auto] rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <input
          className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
          onChange={(event) => setQueryInput(event.target.value)}
          placeholder={t("pages.jobs.filters.queryPlaceholder")}
          value={queryInput}
        />
        <select
          className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
          onChange={(event) => setStatusInput(event.target.value)}
          value={statusInput}
        >
          <option value="">{t("pages.jobs.filters.allStatuses")}</option>
          {statusOptions.map((status) => (
            <option key={status} value={status}>
              {t(`pages.jobs.status.${status}`)}
            </option>
          ))}
        </select>
        <input
          className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
          onChange={(event) => setTagInput(event.target.value)}
          placeholder={t("pages.jobs.filters.tagsPlaceholder")}
          value={tagInput}
        />
        <button
          className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={isBusy}
          onClick={onApplyFilters}
          type="button"
        >
          {t("pages.jobs.filters.apply")}
        </button>
      </section>

      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <input
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="New profile title"
            value={newTitle}
          />
          <input
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) => setNewTags(event.target.value)}
            placeholder="Python, Go, Kafka"
            value={newTags}
          />
          <button
            className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            disabled={isBusy || !newTitle.trim()}
            onClick={() => void handleCreateProfile()}
            type="button"
          >
            {actionState === "creating" ? "Creating..." : "New Profile"}
          </button>
        </div>
      </section>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">{t("common.loading")}</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}

      {loadState === "ready" ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)_minmax(280px,0.8fr)]">
          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">Profiles</h2>
            </div>
            <div className="divide-y divide-border">
              {profiles.map((item) => (
                <button
                  key={item.job_profile_id}
                  className={`flex w-full items-start justify-between gap-4 px-5 py-4 text-left ${
                    item.job_profile_id === selectedId ? "bg-accent/10" : "hover:bg-bg-hover/60"
                  }`}
                  disabled={isBusy}
                  onClick={() => setSelectedId(item.job_profile_id)}
                  type="button"
                >
                  <div>
                    <p className="text-base font-medium text-text-primary">{item.title}</p>
                    <p className="mt-1 text-xs text-text-muted">{item.job_profile_id}</p>
                    <p className="mt-2 text-sm text-text-secondary">{item.company || "--"}</p>
                  </div>
                  <span className={`rounded-chip border px-2.5 py-1 text-xs ${tone(item.status)}`}>
                    {item.status}
                  </span>
                </button>
              ))}
              {profiles.length === 0 ? <div className="p-5 text-sm text-text-secondary">{t("common.empty")}</div> : null}
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">Profile Detail</h2>
                <p className="mt-1 text-sm text-text-secondary">{selected?.job_profile_id ?? "--"}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
                  disabled={!selected || isBusy}
                  onClick={() => void handleSaveProfile()}
                  type="button"
                >
                  {actionState === "saving" ? "Saving..." : "Save"}
                </button>
                <button
                  className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
                  disabled={!selected || isBusy}
                  onClick={() =>
                    void handleStatusChange(selected?.status === "active" ? "draft" : "active")
                  }
                  type="button"
                >
                  {selected?.status === "active" ? "Set Draft" : "Set Active"}
                </button>
                <button
                  className="rounded-card border border-error/50 px-3 py-2 text-sm text-error hover:bg-error/10 disabled:opacity-50"
                  disabled={!selected || isBusy}
                  onClick={() => void handleDelete()}
                  type="button"
                >
                  {actionState === "deleting" ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
            {selected ? (
              <div className="space-y-4 pt-4">
                <input
                  className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-xl font-semibold text-text-primary outline-none focus:border-accent"
                  onChange={(event) => setEditTitle(event.target.value)}
                  type="text"
                  value={editTitle}
                />
                <p className="text-sm text-text-secondary">{selected.company || "--"}</p>
                <p className="text-sm text-text-secondary">
                  Updated {formatUpdatedAt(selected.updated_at, i18n.language)}
                </p>
                <label className="space-y-2">
                  <span className="text-xs uppercase tracking-[0.18em] text-text-muted">Tags</span>
                  <input
                    className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) => setEditTags(event.target.value)}
                    type="text"
                    value={editTags}
                  />
                </label>
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Match</p>
                    <p className="mt-2 text-2xl font-semibold text-text-primary">{selected.match_score}</p>
                  </div>
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Evidence</p>
                    <p className="mt-2 text-2xl font-semibold text-text-primary">{selected.evidence_count}</p>
                  </div>
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Resumes</p>
                    <p className="mt-2 text-2xl font-semibold text-text-primary">{selected.resume_count}</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="pt-4 text-sm text-text-secondary">{t("common.empty")}</p>
            )}
          </section>

          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">Leads</h2>
            </div>
            <div className="divide-y divide-border">
              {leads.map((lead) => (
                <div key={lead.job_lead_id} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-base font-medium text-text-primary">{lead.position}</p>
                      <p className="mt-1 text-sm text-text-secondary">{lead.company || "--"}</p>
                      <p className="mt-1 text-xs text-text-muted">{lead.source}</p>
                    </div>
                    <button
                      className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
                      disabled={isBusy}
                      onClick={() => void handleConvertLead(lead.job_lead_id)}
                      type="button"
                    >
                      {convertingLeadId === lead.job_lead_id ? "Converting..." : "Convert"}
                    </button>
                  </div>
                </div>
              ))}
              {leads.length === 0 ? <div className="p-5 text-sm text-text-secondary">{t("common.empty")}</div> : null}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
