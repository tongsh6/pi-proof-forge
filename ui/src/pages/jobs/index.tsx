import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "react-i18next";
import {
  Briefcase,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Star,
  Tag,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import {
  convertJobLead,
  createJobProfile,
  listJobLeads,
  listJobProfiles,
  updateJobProfile,
} from "@/lib/sidecar/api";
import type {
  JobLeadListItem,
  JobLeadsFilters,
  JobProfileListItem,
  JobProfilesFilters,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type ActionState = "idle" | "creating" | "saving" | "converting";
type ActiveTab = "profiles" | "leads";

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;
const DEFAULT_PROFILE_FILTERS: JobProfilesFilters = { status: null, query: "", tags: [] };
const DEFAULT_LEAD_FILTERS: JobLeadsFilters = {
  source: null,
  status: null,
  favorited: null,
  query: "",
};
const statusOptions = ["active", "draft", "archived"] as const;
const leadStatusOptions = ["new", "qualified", "contacted", "archived"] as const;

function recordVerifyEvent(
  event: string,
  details: Record<string, unknown> = {}
) {
  if (verifyScenario !== "jobs") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
}

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

function statusTone(status: string): string {
  if (status === "active" || status === "qualified") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "draft" || status === "new") {
    return "border-border bg-bg-hover text-text-secondary";
  }
  if (status === "contacted") {
    return "border-accent/40 bg-accent/10 text-accent";
  }
  if (status === "archived") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  return "border-border bg-bg-hover text-text-secondary";
}

function sourceTone(source: string): string {
  if (source.toLowerCase().includes("liepin")) {
    return "border-accent/40 bg-accent/10 text-accent";
  }
  if (source.toLowerCase().includes("referral")) {
    return "border-success/40 bg-success/10 text-success";
  }
  return "border-border bg-bg-hover text-text-secondary";
}

function compactList(items: string[], fallback: string, limit = 5): string[] {
  if (items.length === 0) return [fallback];
  return items.slice(0, limit);
}

export function JobsPage() {
  const { t, i18n } = useTranslation();
  const [profiles, setProfiles] = useState<JobProfileListItem[]>([]);
  const [leads, setLeads] = useState<JobLeadListItem[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("profiles");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [actionState, setActionState] = useState<ActionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [statusInput, setStatusInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [leadQueryInput, setLeadQueryInput] = useState("");
  const [leadStatusInput, setLeadStatusInput] = useState("");
  const [leadFavoriteOnly, setLeadFavoriteOnly] = useState(false);
  const [profileFilters, setProfileFilters] = useState<JobProfilesFilters>(
    DEFAULT_PROFILE_FILTERS
  );
  const [leadFilters, setLeadFilters] = useState<JobLeadsFilters>(DEFAULT_LEAD_FILTERS);
  const [newTitle, setNewTitle] = useState("");
  const [newTags, setNewTags] = useState("");
  const [editingProfile, setEditingProfile] = useState<{
    title: string;
    tags: string;
    status: "active" | "draft" | "archived";
  }>({ title: "", tags: "", status: "draft" });
  const [convertingLeadId, setConvertingLeadId] = useState<string | null>(null);

  const loadData = useCallback(
    async (
      nextProfileFilters: JobProfilesFilters = profileFilters,
      nextLeadFilters: JobLeadsFilters = leadFilters
    ) => {
      setLoadState("loading");
      setError(null);
      try {
        const [profileResult, leadResult] = await Promise.all([
          listJobProfiles(nextProfileFilters),
          listJobLeads(nextLeadFilters),
        ]);
        setProfiles(profileResult.items);
        setLeads(leadResult.items);
        setSelectedProfileId((current) => {
          if (
            current &&
            profileResult.items.some((item) => item.job_profile_id === current)
          ) {
            return current;
          }
          return profileResult.items[0]?.job_profile_id ?? null;
        });
        setSelectedLeadId((current) => {
          if (current && leadResult.items.some((item) => item.job_lead_id === current)) {
            return current;
          }
          return leadResult.items[0]?.job_lead_id ?? null;
        });
        setLoadState("ready");
        recordVerifyEvent("jobs.load.ready", {
          profile_count: profileResult.items.length,
          lead_count: leadResult.items.length,
          active_profile_count: profileResult.items.filter(
            (item) => item.status === "active"
          ).length,
        });
      } catch (nextError) {
        setProfiles([]);
        setLeads([]);
        setSelectedProfileId(null);
        setSelectedLeadId(null);
        setError(getErrorMessage(nextError));
        setLoadState("error");
        recordVerifyEvent("jobs.load.error", {
          error: getErrorMessage(nextError),
        });
      }
    },
    [leadFilters, profileFilters]
  );

  useEffect(() => {
    void loadData(profileFilters, leadFilters);
  }, [leadFilters, loadData, profileFilters]);

  const selectedProfile = useMemo(
    () => profiles.find((item) => item.job_profile_id === selectedProfileId) ?? null,
    [profiles, selectedProfileId]
  );
  const selectedLead = useMemo(
    () => leads.find((item) => item.job_lead_id === selectedLeadId) ?? null,
    [leads, selectedLeadId]
  );
  const profileStats = useMemo(
    () => ({
      active: profiles.filter((item) => item.status === "active").length,
      averageMatch:
        profiles.length === 0
          ? 0
          : Math.round(
              profiles.reduce((total, item) => total + item.match_score, 0) /
                profiles.length
            ),
      evidence: profiles.reduce((total, item) => total + item.evidence_count, 0),
    }),
    [profiles]
  );

  useEffect(() => {
    if (!selectedProfile) return;
    setEditingProfile({
      title: selectedProfile.title,
      tags: selectedProfile.keywords.join(", "),
      status:
        selectedProfile.status === "active" ||
        selectedProfile.status === "draft" ||
        selectedProfile.status === "archived"
          ? selectedProfile.status
          : "draft",
    });
  }, [selectedProfile]);

  const isBusy = actionState !== "idle" || convertingLeadId !== null;

  const applyProfileFilters = useCallback(() => {
    setProfileFilters({
      status: statusInput || null,
      query: queryInput.trim(),
      tags: parseTagsInput(tagInput),
    });
  }, [queryInput, statusInput, tagInput]);

  const resetProfileFilters = useCallback(() => {
    setQueryInput("");
    setStatusInput("");
    setTagInput("");
    setProfileFilters(DEFAULT_PROFILE_FILTERS);
  }, []);

  const applyLeadFilters = useCallback(() => {
    setLeadFilters({
      source: null,
      status: leadStatusInput || null,
      favorited: leadFavoriteOnly ? true : null,
      query: leadQueryInput.trim(),
    });
  }, [leadFavoriteOnly, leadQueryInput, leadStatusInput]);

  const resetLeadFilters = useCallback(() => {
    setLeadQueryInput("");
    setLeadStatusInput("");
    setLeadFavoriteOnly(false);
    setLeadFilters(DEFAULT_LEAD_FILTERS);
  }, []);

  const handleCreateProfile = useCallback(async () => {
    if (!newTitle.trim()) {
      setError(t("pages.jobs.errors.titleRequired"));
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
      resetProfileFilters();
      await loadData(DEFAULT_PROFILE_FILTERS, leadFilters);
      setSelectedProfileId(created.job_profile_id);
      setActiveTab("profiles");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setActionState("idle");
    }
  }, [leadFilters, loadData, newTags, newTitle, resetProfileFilters, t]);

  const handleSaveProfile = useCallback(async () => {
    if (!selectedProfile) return;
    if (!editingProfile.title.trim()) {
      setError(t("pages.jobs.errors.titleRequired"));
      return;
    }
    setActionState("saving");
    setError(null);
    try {
      await updateJobProfile(selectedProfile.job_profile_id, {
        title: editingProfile.title.trim(),
        tags: parseTagsInput(editingProfile.tags),
        status: editingProfile.status,
      });
      await loadData(profileFilters, leadFilters);
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setActionState("idle");
    }
  }, [editingProfile, leadFilters, loadData, profileFilters, selectedProfile, t]);

  const handleConvertLead = useCallback(
    async (jobLeadId: string) => {
      setConvertingLeadId(jobLeadId);
      setError(null);
      try {
        const result = await convertJobLead(jobLeadId);
        resetProfileFilters();
        await loadData(DEFAULT_PROFILE_FILTERS, leadFilters);
        setSelectedProfileId(result.job_profile_id);
        setActiveTab("profiles");
      } catch (nextError) {
        setError(getErrorMessage(nextError));
      } finally {
        setConvertingLeadId(null);
      }
    },
    [leadFilters, loadData, resetProfileFilters]
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.jobs.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.jobs.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-50"
            disabled={isBusy}
            onClick={() => void loadData(profileFilters, leadFilters)}
            type="button"
          >
            <RefreshCw size={16} />
            {t("common.retry")}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            disabled={isBusy || !newTitle.trim()}
            onClick={() => void handleCreateProfile()}
            type="button"
          >
            <Plus size={16} />
            {actionState === "creating"
              ? t("pages.jobs.actions.creating")
              : t("pages.jobs.actions.newProfile")}
          </button>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-text-secondary">
              {t("pages.jobs.stats.profiles")}
            </p>
            <Briefcase size={18} className="text-accent" />
          </div>
          <p className="mt-4 text-4xl font-semibold text-text-primary">{profiles.length}</p>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.jobs.stats.active", { count: profileStats.active })}
          </p>
        </article>
        <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-text-secondary">
              {t("pages.jobs.stats.averageMatch")}
            </p>
            <CheckCircle2 size={18} className="text-success" />
          </div>
          <p className="mt-4 text-4xl font-semibold text-text-primary">
            {profileStats.averageMatch}
          </p>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.jobs.stats.evidence", { count: profileStats.evidence })}
          </p>
        </article>
        <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-text-secondary">
              {t("pages.jobs.stats.leads")}
            </p>
            <FileText size={18} className="text-warning" />
          </div>
          <p className="mt-4 text-4xl font-semibold text-text-primary">{leads.length}</p>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.jobs.stats.favorite", {
              count: leads.filter((lead) => lead.favorited).length,
            })}
          </p>
        </article>
      </section>

      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <input
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder={t("pages.jobs.newProfile.titlePlaceholder")}
            value={newTitle}
          />
          <input
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) => setNewTags(event.target.value)}
            placeholder={t("pages.jobs.newProfile.tagsPlaceholder")}
            value={newTags}
          />
          <button
            className="inline-flex items-center justify-center gap-2 rounded-card border border-accent px-4 py-2 text-sm text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
            disabled={isBusy || (!newTitle.trim() && !newTags.trim())}
            onClick={() => {
              setNewTitle("");
              setNewTags("");
            }}
            type="button"
          >
            {t("pages.jobs.actions.clearDraft")}
          </button>
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-2">
        <div className="flex rounded-card border border-border bg-bg-panel p-1">
          {(["profiles", "leads"] as const).map((tab) => (
            <button
              key={tab}
              className={`rounded-card px-4 py-2 text-sm transition-colors ${
                activeTab === tab
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
              }`}
              onClick={() => setActiveTab(tab)}
              type="button"
            >
              {t(`pages.jobs.tabs.${tab}`)}
            </button>
          ))}
        </div>
        {activeTab === "profiles" ? (
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                size={16}
              />
              <input
                className="w-72 rounded-card border border-border bg-bg-panel py-2 pl-9 pr-3 text-sm text-text-primary outline-none focus:border-accent"
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder={t("pages.jobs.filters.queryPlaceholder")}
                value={queryInput}
              />
            </div>
            <select
              className="rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
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
              className="w-64 rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
              onChange={(event) => setTagInput(event.target.value)}
              placeholder={t("pages.jobs.filters.tagsPlaceholder")}
              value={tagInput}
            />
            <button
              className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              disabled={isBusy}
              onClick={applyProfileFilters}
              type="button"
            >
              <Filter size={16} />
              {t("pages.jobs.filters.apply")}
            </button>
            <button
              className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover"
              onClick={resetProfileFilters}
              type="button"
            >
              {t("pages.jobs.filters.reset")}
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                size={16}
              />
              <input
                className="w-72 rounded-card border border-border bg-bg-panel py-2 pl-9 pr-3 text-sm text-text-primary outline-none focus:border-accent"
                onChange={(event) => setLeadQueryInput(event.target.value)}
                placeholder={t("pages.jobs.leads.searchPlaceholder")}
                value={leadQueryInput}
              />
            </div>
            <select
              className="rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
              onChange={(event) => setLeadStatusInput(event.target.value)}
              value={leadStatusInput}
            >
              <option value="">{t("pages.jobs.leads.allStatuses")}</option>
              {leadStatusOptions.map((status) => (
                <option key={status} value={status}>
                  {t(`pages.jobs.leadStatus.${status}`)}
                </option>
              ))}
            </select>
            <label className="inline-flex items-center gap-2 rounded-card border border-border px-3 py-2 text-sm text-text-primary">
              <input
                checked={leadFavoriteOnly}
                className="h-4 w-4 accent-accent"
                onChange={(event) => setLeadFavoriteOnly(event.target.checked)}
                type="checkbox"
              />
              {t("pages.jobs.leads.favoriteOnly")}
            </label>
            <button
              className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              disabled={isBusy}
              onClick={applyLeadFilters}
              type="button"
            >
              <Filter size={16} />
              {t("pages.jobs.filters.apply")}
            </button>
            <button
              className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover"
              onClick={resetLeadFilters}
              type="button"
            >
              {t("pages.jobs.filters.reset")}
            </button>
          </div>
        )}
      </section>

      {loadState === "loading" ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.loading")}
        </section>
      ) : null}
      {loadState === "error" ? (
        <section className="rounded-panel border border-error/50 bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{error}</p>
        </section>
      ) : null}
      {error && loadState === "ready" ? (
        <p className="text-sm text-error">{error}</p>
      ) : null}

      {loadState === "ready" && activeTab === "profiles" ? (
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="grid content-start gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            {profiles.map((profile) => {
              const selected = profile.job_profile_id === selectedProfileId;
              const tags = compactList(
                profile.keywords,
                t("pages.jobs.card.noTags"),
                4
              );
              return (
                <button
                  key={profile.job_profile_id}
                  className={`rounded-panel border bg-bg-panel p-5 text-left shadow-[var(--shadow-panel)] transition-colors ${
                    selected
                      ? "border-accent bg-accent/10"
                      : "border-border hover:bg-bg-hover/60"
                  }`}
                  disabled={isBusy}
                  onClick={() => setSelectedProfileId(profile.job_profile_id)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-text-primary">
                        {profile.title}
                      </p>
                      <p className="mt-1 text-sm text-text-secondary">
                        {profile.company || profile.business_domain || "--"}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-chip border px-2.5 py-1 text-xs ${statusTone(
                        profile.status
                      )}`}
                    >
                      {t(`pages.jobs.status.${profile.status}`, {
                        defaultValue: profile.status,
                      })}
                    </span>
                  </div>
                  <p className="mt-4 line-clamp-2 min-h-10 text-sm text-text-secondary">
                    {profile.source_jd || profile.tone || profile.job_profile_id}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {tags.map((tag) => (
                      <span
                        key={`${profile.job_profile_id}-${tag}`}
                        className="rounded-chip border border-border bg-bg-hover px-2.5 py-1 text-xs text-text-secondary"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  <div className="my-4 h-px bg-border" />
                  <div className="grid grid-cols-3 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-text-muted">
                        {t("pages.jobs.metrics.matchScore")}
                      </p>
                      <p className="mt-1 font-semibold text-accent">
                        {profile.match_score}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted">
                        {t("pages.jobs.metrics.evidence")}
                      </p>
                      <p className="mt-1 font-semibold text-text-primary">
                        {profile.evidence_count}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted">
                        {t("pages.jobs.metrics.resumes")}
                      </p>
                      <p className="mt-1 font-semibold text-text-primary">
                        {profile.resume_count}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
            {profiles.length === 0 ? (
              <div className="rounded-panel border border-border bg-bg-panel p-6 shadow-[var(--shadow-panel)] lg:col-span-2">
                <p className="text-base font-semibold text-text-primary">
                  {t("pages.jobs.empty.title")}
                </p>
                <p className="mt-2 text-sm text-text-secondary">
                  {t("pages.jobs.empty.subtitle")}
                </p>
              </div>
            ) : null}
          </div>

          <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.jobs.detailTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {selectedProfile?.job_profile_id ?? "--"}
                  </p>
                </div>
                <button
                  className="rounded-card border border-accent px-3 py-2 text-sm text-accent hover:bg-accent/10 disabled:opacity-50"
                  disabled={!selectedProfile || isBusy}
                  onClick={() => void handleSaveProfile()}
                  type="button"
                >
                  {actionState === "saving"
                    ? t("pages.jobs.actions.saving")
                    : t("pages.jobs.actions.save")}
                </button>
              </div>
            </div>
            {selectedProfile ? (
              <div className="space-y-5 pt-4">
                <label>
                  <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.title")}
                  </span>
                  <input
                    className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-xl font-semibold text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setEditingProfile((current) => ({
                        ...current,
                        title: event.target.value,
                      }))
                    }
                    value={editingProfile.title}
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label>
                    <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.filters.status")}
                    </span>
                    <select
                      className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                      disabled={isBusy}
                      onChange={(event) =>
                        setEditingProfile((current) => ({
                          ...current,
                          status: event.target.value as "active" | "draft" | "archived",
                        }))
                      }
                      value={editingProfile.status}
                    >
                      {statusOptions.map((status) => (
                        <option key={status} value={status}>
                          {t(`pages.jobs.status.${status}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div>
                    <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.updatedAt")}
                    </span>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatUpdatedAt(selectedProfile.updated_at, i18n.language)}
                    </p>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.businessDomain")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {selectedProfile.business_domain || "--"}
                    </p>
                  </div>
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.tone")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {selectedProfile.tone || "--"}
                    </p>
                  </div>
                </div>
                <label>
                  <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.keywords")}
                  </span>
                  <input
                    className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    disabled={isBusy}
                    onChange={(event) =>
                      setEditingProfile((current) => ({
                        ...current,
                        tags: event.target.value,
                      }))
                    }
                    value={editingProfile.tags}
                  />
                </label>
                {(
                  [
                    ["mustHave", selectedProfile.must_have],
                    ["niceToHave", selectedProfile.nice_to_have],
                    ["senioritySignal", selectedProfile.seniority_signal],
                  ] as const
                ).map(([key, values]) => (
                  <div key={key}>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t(`pages.jobs.fields.${key}`)}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {compactList(values, t("pages.jobs.card.noRequirements")).map(
                        (value) => (
                          <span
                            key={`${key}-${value}`}
                            className="rounded-chip border border-border bg-bg-hover px-2.5 py-1 text-xs text-text-secondary"
                          >
                            {value}
                          </span>
                        )
                      )}
                    </div>
                  </div>
                ))}
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.sourceJd")}
                  </p>
                  <p className="mt-2 break-words text-sm text-text-primary">
                    {selectedProfile.source_jd || "--"}
                  </p>
                </div>
              </div>
            ) : (
              <p className="pt-4 text-sm text-text-secondary">{t("common.empty")}</p>
            )}
          </aside>
        </section>
      ) : null}

      {loadState === "ready" && activeTab === "leads" ? (
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="overflow-hidden rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="grid grid-cols-[minmax(220px,1.1fr)_minmax(180px,0.8fr)_120px_120px_140px] border-b border-border px-5 py-3 text-xs uppercase tracking-[0.18em] text-text-muted">
              <span>{t("pages.jobs.leads.company")}</span>
              <span>{t("pages.jobs.leads.position")}</span>
              <span>{t("pages.jobs.leads.source")}</span>
              <span>{t("pages.jobs.leads.status")}</span>
              <span>{t("pages.jobs.leads.action")}</span>
            </div>
            <div className="divide-y divide-border">
              {leads.map((lead) => {
                const selected = lead.job_lead_id === selectedLeadId;
                return (
                  <button
                    key={lead.job_lead_id}
                    className={`grid w-full grid-cols-[minmax(220px,1.1fr)_minmax(180px,0.8fr)_120px_120px_140px] items-center gap-3 px-5 py-4 text-left transition-colors ${
                      selected ? "bg-accent/10" : "hover:bg-bg-hover/60"
                    }`}
                    disabled={isBusy}
                    onClick={() => setSelectedLeadId(lead.job_lead_id)}
                    type="button"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        {lead.favorited ? (
                          <Star className="shrink-0 text-warning" size={15} />
                        ) : null}
                        <p className="truncate text-sm font-medium text-text-primary">
                          {lead.company || "--"}
                        </p>
                      </div>
                      <p className="mt-1 text-xs text-text-muted">{lead.job_lead_id}</p>
                    </div>
                    <p className="truncate text-sm text-text-secondary">
                      {lead.position || "--"}
                    </p>
                    <span
                      className={`w-fit rounded-chip border px-2.5 py-1 text-xs ${sourceTone(
                        lead.source
                      )}`}
                    >
                      {lead.source || "--"}
                    </span>
                    <span
                      className={`w-fit rounded-chip border px-2.5 py-1 text-xs ${statusTone(
                        lead.status
                      )}`}
                    >
                      {t(`pages.jobs.leadStatus.${lead.status}`, {
                        defaultValue: lead.status,
                      })}
                    </span>
                    <span className="inline-flex w-fit items-center gap-2 rounded-card border border-border px-3 py-2 text-sm text-text-primary">
                      <ExternalLink size={15} />
                      {t("pages.jobs.leads.view")}
                    </span>
                  </button>
                );
              })}
              {leads.length === 0 ? (
                <div className="p-5 text-sm text-text-secondary">{t("common.empty")}</div>
              ) : null}
            </div>
          </div>

          <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.jobs.leads.detailTitle")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {selectedLead?.job_lead_id ?? "--"}
              </p>
            </div>
            {selectedLead ? (
              <div className="space-y-5 pt-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.leads.company")}
                  </p>
                  <p className="mt-2 text-xl font-semibold text-text-primary">
                    {selectedLead.company || "--"}
                  </p>
                  <p className="mt-2 text-sm text-text-secondary">
                    {selectedLead.position || "--"}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-text-muted">
                      <Tag size={14} />
                      {t("pages.jobs.leads.source")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {selectedLead.source || "--"}
                    </p>
                  </div>
                  <div className="rounded-card border border-border px-4 py-3">
                    <p className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-text-muted">
                      <Clock3 size={14} />
                      {t("pages.jobs.leads.updatedAt")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatUpdatedAt(selectedLead.updated_at, i18n.language)}
                    </p>
                  </div>
                </div>
                <div className="rounded-card border border-border bg-bg-primary p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.leads.followUp")}
                  </p>
                  <p className="mt-2 text-sm text-text-secondary">
                    {selectedLead.favorited
                      ? t("pages.jobs.leads.favoritedHint")
                      : t("pages.jobs.leads.defaultHint")}
                  </p>
                </div>
                <button
                  className="inline-flex w-full items-center justify-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  disabled={isBusy}
                  onClick={() => void handleConvertLead(selectedLead.job_lead_id)}
                  type="button"
                >
                  <Plus size={16} />
                  {convertingLeadId === selectedLead.job_lead_id
                    ? t("pages.jobs.actions.converting")
                    : t("pages.jobs.leads.convert")}
                </button>
              </div>
            ) : (
              <p className="pt-4 text-sm text-text-secondary">{t("common.empty")}</p>
            )}
          </aside>
        </section>
      ) : null}
    </div>
  );
}
