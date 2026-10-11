import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Clock3,
  ExternalLink,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Star,
  Tag,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { confirmAction, notify } from "@/lib/ui";
import {
  convertJobLead,
  createJobProfile,
  fetchLiepinJobDetail,
  generateJobProfileDraft,
  listJobLeads,
  listJobProfiles,
  prepareLiepinDefault,
  recordManualSubmission,
  saveJobProfileDraft,
  searchLiepinJobs,
  updateJobProfile,
} from "@/lib/sidecar/api";
import type {
  JobProfileDraftPayload,
  JobLeadListItem,
  JobLeadsFilters,
  JobProfileListItem,
  JobProfilesFilters,
  LiepinSearchResult,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type ActionState = "idle" | "creating" | "saving" | "converting";
type DraftState = "idle" | "generating";
type ActiveTab = "profiles" | "leads";

const DEFAULT_PROFILE_FILTERS: JobProfilesFilters = { status: null, query: "", tags: [] };
const DEFAULT_LEAD_FILTERS: JobLeadsFilters = {
  source: null,
  status: null,
  favorited: null,
  query: "",
  company_size_max: null,
};
const leadSizeOptions = [
  { value: "99", key: "sizeUnder100" },
  { value: "499", key: "sizeUnder500" },
] as const;
const statusOptions = ["active", "draft", "archived"] as const;
const leadStatusOptions = ["draft", "new", "qualified", "contacted", "archived"] as const;

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
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<JobProfileListItem[]>([]);
  const [leads, setLeads] = useState<JobLeadListItem[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("profiles");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [actionState, setActionState] = useState<ActionState>("idle");
  const [draftState, setDraftState] = useState<DraftState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [statusInput, setStatusInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [leadQueryInput, setLeadQueryInput] = useState("");
  const [leadStatusInput, setLeadStatusInput] = useState("");
  const [leadSizeInput, setLeadSizeInput] = useState("");
  const [leadFavoriteOnly, setLeadFavoriteOnly] = useState(false);
  const [profileFilters, setProfileFilters] = useState<JobProfilesFilters>(
    DEFAULT_PROFILE_FILTERS
  );
  const [leadFilters, setLeadFilters] = useState<JobLeadsFilters>(DEFAULT_LEAD_FILTERS);
  const [newTitle, setNewTitle] = useState("");
  const [newTags, setNewTags] = useState("");
  const [jdText, setJdText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [boundLeadId, setBoundLeadId] = useState<string | null>(null);
  const [boundProfileId, setBoundProfileId] = useState<string | null>(null);
  const [fetchingDetail, setFetchingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [preparingReview, setPreparingReview] = useState(false);
  const [preparationError, setPreparationError] = useState<string | null>(null);
  const [generatedDraft, setGeneratedDraft] =
    useState<JobProfileDraftPayload | null>(null);
  const [draftKeywords, setDraftKeywords] = useState("");
  const [draftMustHave, setDraftMustHave] = useState("");
  const [editingProfile, setEditingProfile] = useState<{
    title: string;
    tags: string;
    status: "active" | "draft" | "archived";
  }>({ title: "", tags: "", status: "draft" });
  const [convertingLeadId, setConvertingLeadId] = useState<string | null>(null);
  const [liepinKeyword, setLiepinKeyword] = useState("");
  const [liepinSearching, setLiepinSearching] = useState(false);
  const [liepinSearchResult, setLiepinSearchResult] = useState<LiepinSearchResult | null>(null);
  const [liepinSearchError, setLiepinSearchError] = useState<string | null>(null);

  const hasLoadedRef = useRef(false);
  const [refreshing, setRefreshing] = useState(false);
  // 新建画像区块默认收起；没有任何画像、或已有解析草稿/绑定线索时自动展开。
  const [createOpen, setCreateOpen] = useState(false);
  // 画像详情默认只读；切换画像时退出编辑态。
  const [profileEditing, setProfileEditing] = useState(false);
  // 手动投递记录表单（画像详情只读视图内的折叠区块）。
  const [manualDeliveredAt, setManualDeliveredAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [manualNote, setManualNote] = useState("");
  const [manualSaving, setManualSaving] = useState(false);

  // 首次加载显示占位；之后的重载保留列表与详情，不整页回到 loading。
  const loadData = useCallback(
    async (
      nextProfileFilters: JobProfilesFilters = profileFilters,
      nextLeadFilters: JobLeadsFilters = leadFilters
    ) => {
      if (hasLoadedRef.current) setRefreshing(true);
      else setLoadState("loading");
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
        hasLoadedRef.current = true;
        setLoadState("ready");
      } catch (nextError) {
        const message = getErrorMessage(nextError);
        setError(message);
        if (hasLoadedRef.current) {
          notify("error", t("common.refreshFailed"), message);
        } else {
          setProfiles([]);
          setLeads([]);
          setSelectedProfileId(null);
          setSelectedLeadId(null);
          setLoadState("error");
        }
      } finally {
        setRefreshing(false);
      }
    },
    [leadFilters, profileFilters] // eslint-disable-line react-hooks/exhaustive-deps
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

  const isBusy =
    actionState !== "idle" || draftState !== "idle" || convertingLeadId !== null || liepinSearching || fetchingDetail || preparingReview;

  useEffect(() => { setPreparationError(null); }, [selectedLeadId]);

  const handlePrepareReview = useCallback(async () => {
    if (!selectedLead || preparingReview) return;
    setPreparingReview(true);
    setPreparationError(null);
    try {
      const result = await prepareLiepinDefault(selectedLead.job_lead_id);
      if (result.status === "ready" && result.run_id) {
        navigate(`/agent-run?run_id=${encodeURIComponent(result.run_id)}`);
      } else {
        setPreparationError(t(`pages.jobs.liepinPreparation.codes.${result.code}`, {
          defaultValue: t("pages.jobs.liepinPreparation.failed"),
        }));
      }
    } catch {
      setPreparationError(t("pages.jobs.liepinPreparation.failed"));
    } finally {
      setPreparingReview(false);
    }
  }, [selectedLead, preparingReview, navigate, t]);

  const clearJdDraft = useCallback((clearText = true) => {
    setGeneratedDraft(null);
    setDraftKeywords("");
    setBoundLeadId(null);
    setBoundProfileId(null);
    setDetailError(null);
    if (clearText) {
      setJdText("");
      setSourceUrl("");
    }
  }, []);

  const handleSelectProfile = useCallback((profileId: string) => {
    if (profileId !== selectedProfileId || (boundProfileId && profileId !== boundProfileId)) {
      clearJdDraft();
    }
    setSelectedProfileId(profileId);
  }, [boundProfileId, clearJdDraft, selectedProfileId]);

  const handleSelectLead = useCallback((leadId: string) => {
    if (leadId !== selectedLeadId || (boundLeadId && leadId !== boundLeadId)) {
      clearJdDraft();
    }
    setSelectedLeadId(leadId);
  }, [boundLeadId, clearJdDraft, selectedLeadId]);

  useEffect(() => {
    if (!boundLeadId) return;
    const changedLead = activeTab === "leads" && selectedLeadId && selectedLeadId !== boundLeadId;
    const changedProfile = activeTab === "profiles" && boundProfileId && selectedProfileId && selectedProfileId !== boundProfileId;
    if (changedLead || changedProfile) clearJdDraft();
  }, [activeTab, boundLeadId, boundProfileId, clearJdDraft, selectedLeadId, selectedProfileId]);

  const handleFetchLiepinDetail = useCallback(async () => {
    if (!selectedLead) return;
    // 已有手动输入的 JD 文本且不属于当前线索时，覆盖前先确认。
    if (jdText.trim() && !(boundLeadId && boundLeadId === selectedLead.job_lead_id)) {
      const confirmed = await confirmAction({
        title: t("confirmations.jobs.overwriteJd.title"),
        description: t("confirmations.jobs.overwriteJd.description"),
        confirmLabel: t("confirmations.jobs.overwriteJd.confirm"),
        tone: "danger",
      });
      if (!confirmed) return;
    }
    setFetchingDetail(true);
    setDetailError(null);
    try {
      const result = await fetchLiepinJobDetail(selectedLead.job_lead_id);
      if (result.status !== "pass") {
        setDetailError(t(`pages.jobs.liepinDetail.codes.${result.code}`, {
          defaultValue: t("pages.jobs.liepinDetail.failed"),
        }));
        return;
      }
      setJdText(result.jd_text);
      setSourceUrl(result.source_url);
      setBoundLeadId(result.job_lead_id);
      setBoundProfileId(result.job_profile_id || null);
      setSelectedProfileId(result.job_profile_id || null);
      setGeneratedDraft(null);
      setError(null);
      notify("success", t("toasts.jobs.detailFetched"));
      setLeads((current) => current.map((lead) => lead.job_lead_id === result.job_lead_id ? {
        ...lead,
        source_jd: result.jd_text,
        source_url: result.source_url,
        source_jd_sha256: result.source_jd_sha256,
        jd_status: result.jd_status,
        job_profile_id: result.job_profile_id,
      } : lead));
    } catch {
      setDetailError(t("pages.jobs.liepinDetail.failed"));
    } finally {
      setFetchingDetail(false);
    }
  }, [boundLeadId, jdText, selectedLead, t]);

  const handleLiepinSearch = useCallback(async () => {
    if (!liepinKeyword.trim()) return;
    setLiepinSearching(true);
    setLiepinSearchError(null);
    setLiepinSearchResult(null);
    try {
      const result = await searchLiepinJobs(liepinKeyword.trim());
      setLiepinSearchResult(result);
      if (result.status === "pass") {
        try {
          const refreshed = await listJobLeads(leadFilters);
          setLeads(refreshed.items);
          setSelectedLeadId((current) => refreshed.items.some((item) => item.job_lead_id === current)
            ? current : refreshed.items[0]?.job_lead_id ?? null);
        } catch {
          setLiepinSearchError(t("pages.jobs.liepinSearch.refreshError"));
        }
      }
    } catch {
      setLiepinSearchError(t("pages.systemSettings.liepinApi.requestError"));
    } finally {
      setLiepinSearching(false);
    }
  }, [leadFilters, liepinKeyword, t]);

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
      company_size_max: leadSizeInput ? Number(leadSizeInput) : null,
    });
  }, [leadFavoriteOnly, leadQueryInput, leadSizeInput, leadStatusInput]);

  const resetLeadFilters = useCallback(() => {
    setLeadQueryInput("");
    setLeadStatusInput("");
    setLeadSizeInput("");
    setLeadFavoriteOnly(false);
    setLeadFilters(DEFAULT_LEAD_FILTERS);
  }, []);

  useEffect(() => {
    if (loadState === "ready" && profiles.length === 0) setCreateOpen(true);
  }, [loadState, profiles.length]);
  useEffect(() => {
    setProfileEditing(false);
  }, [selectedProfileId]);
  useEffect(() => {
    if (boundLeadId || generatedDraft) setCreateOpen(true);
  }, [boundLeadId, generatedDraft]);

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
      clearJdDraft();
      resetProfileFilters();
      await loadData(DEFAULT_PROFILE_FILTERS, leadFilters);
      setSelectedProfileId(created.job_profile_id);
      setActiveTab("profiles");
      notify("success", t("toasts.jobs.created"));
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setActionState("idle");
    }
  }, [clearJdDraft, leadFilters, loadData, newTags, newTitle, resetProfileFilters, t]);

  const handleGenerateProfileDraft = useCallback(async () => {
    if (!jdText.trim()) {
      setError(t("pages.jobs.errors.jdRequired"));
      return;
    }
    setDraftState("generating");
    setError(null);
    try {
      const result = await generateJobProfileDraft({
        jd_text: jdText.trim(),
        source_url: sourceUrl.trim() || undefined,
        job_lead_id: boundLeadId || undefined,
      });
      if (!result.draft) {
        setError(result.message);
        return;
      }
      setGeneratedDraft(result.draft);
      setDraftKeywords(result.draft.keywords.join(", "));
      setDraftMustHave(result.draft.must_have.join("\n"));
      if (boundLeadId) setSelectedProfileId(boundProfileId);
      setActiveTab("profiles");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setDraftState("idle");
    }
  }, [boundLeadId, boundProfileId, jdText, sourceUrl, t]);

  const handleManualDraft = useCallback(() => {
    const lead = leads.find((item) => item.job_lead_id === boundLeadId);
    setError(null);
    setGeneratedDraft({ target_role: lead?.position ?? "", source_jd: jdText,
      source_url: sourceUrl, jd_summary: "", keywords: [], must_have: [], nice_to_have: [], seniority_signal: [] });
    setDraftKeywords("");
    setDraftMustHave("");
    if (boundLeadId) setSelectedProfileId(boundProfileId);
    setActiveTab("profiles");
  }, [boundLeadId, boundProfileId, jdText, leads, sourceUrl]);

  const draftFromEditor = useCallback(
    (draft: JobProfileDraftPayload): JobProfileDraftPayload => ({
      ...draft,
      keywords: parseTagsInput(draftKeywords),
      must_have: draftMustHave.split("\n").map((value) => value.trim()).filter(Boolean),
      source_jd: jdText.trim() || draft.source_jd,
      source_url: sourceUrl.trim() || draft.source_url,
      job_lead_id: boundLeadId || undefined,
      job_profile_id: boundProfileId || undefined,
    }),
    [boundLeadId, boundProfileId, draftKeywords, draftMustHave, jdText, sourceUrl]
  );

  const handleSaveReviewedDraft = useCallback(
    async (saveMode: "incomplete" | "complete") => {
      if (!generatedDraft) return;
      setActionState("saving");
      setError(null);
      try {
        const result = await saveJobProfileDraft({
          draft: draftFromEditor(generatedDraft),
          job_lead_id: boundLeadId || undefined,
          job_profile_id: boundProfileId || undefined,
          save_mode: saveMode,
          review: { decision: "approved", reviewed_at: new Date().toISOString() },
        });
        setGeneratedDraft(null);
        if (boundLeadId) setBoundProfileId(result.job_profile_id);
        resetProfileFilters();
        await loadData(DEFAULT_PROFILE_FILTERS, leadFilters);
        setSelectedProfileId(result.job_profile_id);
        setActiveTab("profiles");
        notify("success", t(saveMode === "complete" ? "toasts.jobs.saved" : "toasts.jobs.draftSaved"));
      } catch (nextError) {
        setError(getErrorMessage(nextError));
      } finally {
        setActionState("idle");
      }
    },
    [boundLeadId, boundProfileId, draftFromEditor, generatedDraft, leadFilters, loadData, resetProfileFilters] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleSaveProfile = useCallback(async () => {
    if (!selectedProfile) return;
    if (!editingProfile.title.trim()) {
      setError(t("pages.jobs.errors.titleRequired"));
      return;
    }
    if (editingProfile.status === "archived" && selectedProfile.status !== "archived") {
      const confirmed = await confirmAction({
        title: t("confirmations.jobs.archiveProfile.title"),
        description: t("confirmations.jobs.archiveProfile.description"),
        confirmLabel: t("confirmations.jobs.archiveProfile.confirm"),
        tone: "danger",
      });
      if (!confirmed) return;
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
      notify("success", t("toasts.jobs.saved"));
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
        if (boundLeadId && boundLeadId === jobLeadId) {
          setBoundProfileId(result.job_profile_id);
        } else {
          clearJdDraft();
        }
        resetProfileFilters();
        await loadData(DEFAULT_PROFILE_FILTERS, leadFilters);
        setSelectedProfileId(result.job_profile_id);
        setActiveTab("profiles");
        notify("success", t("toasts.jobs.converted"));
      } catch (nextError) {
        setError(getErrorMessage(nextError));
      } finally {
        setConvertingLeadId(null);
      }
    },
    [boundLeadId, clearJdDraft, leadFilters, loadData, resetProfileFilters]
  );

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void loadData(profileFilters, leadFilters);
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [loadData, profileFilters, leadFilters]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.jobs.title")}</h1>
          <p className="page-subtitle">{t("pages.jobs.subtitle")}</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="page-icon-button"
            disabled={isBusy || refreshing}
            onClick={() => void loadData(profileFilters, leadFilters)}
            title={t("common.refreshShortcut")}
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            <span className="sr-only">{refreshing ? t("common.refreshing") : t("common.refresh")}</span>
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="jobs-open-create"
            disabled={isBusy}
            onClick={() => {
              setCreateOpen(true);
              if (typeof document !== "undefined") {
                document.getElementById("jobs-create")?.scrollIntoView({ block: "start", behavior: "smooth" });
                document.getElementById("jobs-create-jd")?.focus();
              }
            }}
            type="button"
          >
            <Plus size={16} />
            {t("pages.jobs.actions.newProfile")}
          </button>
        </div>
      </header>

      <section className="stat-strip" data-testid="jobs-stats">
        <span><strong>{profiles.length}</strong>{t("pages.jobs.stats.profiles")} · {t("pages.jobs.stats.active", { count: profileStats.active })}</span>
        <span><strong>{profileStats.averageMatch}</strong>{t("pages.jobs.stats.averageMatch")} · {t("pages.jobs.stats.evidence", { count: profileStats.evidence })}</span>
        <span><strong>{leads.length}</strong>{t("pages.jobs.stats.leads")} · {t("pages.jobs.stats.favorite", { count: leads.filter((lead) => lead.favorited).length })}</span>
      </section>

      <details
        id="jobs-create"
        data-testid="jobs-create"
        className="fold-section rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]"
        open={createOpen}
        onToggle={(event) => setCreateOpen(event.currentTarget.open)}
      >
        <summary>
          <span className="flex min-w-0 flex-wrap items-baseline gap-x-3">
            <span>{t("pages.jobs.create.title")}</span>
            <span className="text-sm font-normal text-text-secondary">{t("pages.jobs.create.hint")}</span>
          </span>
        </summary>
        <div className="px-5 pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              {t("pages.jobs.jdDraft.title")}
            </h2>
            <p className="mt-1 text-sm text-text-secondary">
              {t("pages.jobs.jdDraft.subtitle")}
            </p>
          </div>
          {generatedDraft ? (
            <span className={`rounded-chip border px-2.5 py-1 text-xs ${statusTone(
              generatedDraft.missing_items?.length ? "draft" : "active"
            )}`}>
              {generatedDraft.missing_items?.length
                ? t("pages.jobs.jdDraft.incomplete")
                : t("pages.jobs.jdDraft.ready")}
            </span>
          ) : null}
        </div>
        {boundLeadId ? (
          <div className="mt-4 rounded-card border border-accent/40 bg-accent/10 p-3 text-sm">
            <p className="text-text-primary">{t("pages.jobs.jdDraft.boundSource")}: {boundLeadId}{boundProfileId ? ` → ${boundProfileId}` : ""}</p>
            <p className="mt-1 text-text-secondary">{t("pages.jobs.jdDraft.boundHint")}</p>
            <button className="mt-2 text-accent underline disabled:opacity-50" disabled={isBusy} onClick={() => clearJdDraft(false)} type="button">
              {t("pages.jobs.jdDraft.unbind")}
            </button>
          </div>
        ) : null}
        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(220px,0.45fr)]">
          <textarea
            id="jobs-create-jd"
            className="min-h-28 rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            disabled={isBusy}
            onChange={(event) => {
              setJdText(event.target.value);
              setGeneratedDraft(null);
            }}
            placeholder={t("pages.jobs.jdDraft.jdPlaceholder")}
            readOnly={Boolean(boundLeadId)}
            value={jdText}
          />
          <div className="grid content-start gap-3">
            <input
              className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
              disabled={isBusy}
              onChange={(event) => {
                setSourceUrl(event.target.value);
                setGeneratedDraft(null);
              }}
              placeholder={t("pages.jobs.jdDraft.sourceUrlPlaceholder")}
              readOnly={Boolean(boundLeadId)}
              value={sourceUrl}
            />
            <button
              className="inline-flex items-center justify-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              disabled={isBusy || !jdText.trim()}
              onClick={() => void handleGenerateProfileDraft()}
              type="button"
            >
              <Sparkles size={16} />
              {draftState === "generating"
                ? t("pages.jobs.actions.generatingDraft")
                : t("pages.jobs.actions.generateDraft")}
            </button>
            <button className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={isBusy || (!jdText && !sourceUrl && !generatedDraft && !boundLeadId)} onClick={() => clearJdDraft()} type="button">
              {t("pages.jobs.jdDraft.clear")}
            </button>
            <button className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50"
              disabled={isBusy || !jdText.trim()} onClick={handleManualDraft} type="button">
              {t("pages.jobs.actions.manualDraft")}
            </button>
            {generatedDraft ? (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                <button
                  className="rounded-card border border-border px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-50"
                  disabled={isBusy}
                  onClick={() => void handleSaveReviewedDraft("incomplete")}
                  type="button"
                >
                  {t("pages.jobs.actions.saveIncomplete")}
                </button>
                <button
                  className="rounded-card border border-success bg-success px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  disabled={isBusy}
                  onClick={() => void handleSaveReviewedDraft("complete")}
                  type="button"
                >
                  {t("pages.jobs.actions.saveComplete")}
                </button>
              </div>
            ) : null}
          </div>
        </div>
        {generatedDraft ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-card border border-border bg-bg-primary/50 p-3">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.jobs.fields.title")}
              </p>
              <input
                aria-label={t("pages.jobs.jdDraft.reviewTitle")}
                className="mt-2 w-full rounded-card border border-border bg-bg-hover px-2 py-1 text-sm text-text-primary"
                disabled={isBusy}
                value={generatedDraft.target_role}
                onChange={(event) => setGeneratedDraft((current) => current ? { ...current, target_role: event.target.value } : current)}
              />
            </div>
            <div className="rounded-card border border-border bg-bg-primary/50 p-3">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.jobs.fields.keywords")}
              </p>
              <input
                aria-label={t("pages.jobs.jdDraft.reviewKeywords")}
                className="mt-2 w-full rounded-card border border-border bg-bg-hover px-2 py-1 text-sm text-text-primary"
                disabled={isBusy}
                value={draftKeywords}
                onChange={(event) => setDraftKeywords(event.target.value)}
              />
            </div>
            <div className="rounded-card border border-border bg-bg-primary/50 p-3">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.jobs.jdDraft.missing")}
              </p>
              <p className="mt-2 text-sm text-text-primary">
                {[
                  !generatedDraft.target_role.trim() && t("pages.jobs.jdDraft.reviewTitle"),
                  !generatedDraft.jd_summary.trim() && t("pages.jobs.jdDraft.reviewSummary"),
                  !draftMustHave.trim() && t("pages.jobs.jdDraft.reviewMustHave"),
                  !draftKeywords.trim() && t("pages.jobs.jdDraft.reviewKeywords"),
                ].filter(Boolean).join(", ") ||
                  t("pages.jobs.jdDraft.none")}
              </p>
            </div>
            <label className="rounded-card border border-border bg-bg-primary/50 p-3 text-xs text-text-muted">
              {t("pages.jobs.jdDraft.reviewSummary")}
              <textarea aria-label={t("pages.jobs.jdDraft.reviewSummary")} disabled={isBusy}
                className="mt-2 min-h-24 w-full rounded-card bg-bg-hover px-2 py-1 text-sm text-text-primary"
                value={generatedDraft.jd_summary}
                onChange={(event) => setGeneratedDraft((current) => current ? { ...current, jd_summary: event.target.value } : current)} />
            </label>
            <label className="rounded-card border border-border bg-bg-primary/50 p-3 text-xs text-text-muted">
              {t("pages.jobs.jdDraft.reviewMustHave")}
              <textarea aria-label={t("pages.jobs.jdDraft.reviewMustHave")} disabled={isBusy}
                className="mt-2 min-h-24 w-full rounded-card bg-bg-hover px-2 py-1 text-sm text-text-primary"
                value={draftMustHave} onChange={(event) => setDraftMustHave(event.target.value)} />
            </label>
          </div>
        ) : null}
        </div>
        <details className="border-t border-border">
          <summary className="cursor-pointer select-none px-5 py-3 text-sm text-text-secondary">{t("pages.jobs.create.titleOnly")}</summary>
          <div className="px-5 pb-5">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
          <input
            id="jobs-create-title"
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            aria-label={t("pages.jobs.newProfile.titlePlaceholder")}
            onChange={(event) => setNewTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && newTitle.trim() && !isBusy) void handleCreateProfile();
            }}
            placeholder={t("pages.jobs.newProfile.titlePlaceholder")}
            value={newTitle}
          />
          <input
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            aria-label={t("pages.jobs.newProfile.tagsPlaceholder")}
            onChange={(event) => setNewTags(event.target.value)}
            placeholder={t("pages.jobs.newProfile.tagsPlaceholder")}
            value={newTags}
          />
          <button
            className="inline-flex items-center justify-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="jobs-create-submit"
            disabled={isBusy || !newTitle.trim()}
            title={!newTitle.trim() ? t("reasons.jobs.titleRequired") : isBusy ? t("reasons.jobs.busy") : undefined}
            onClick={() => void handleCreateProfile()}
            type="button"
          >
            <Plus size={16} />
            {actionState === "creating" ? t("pages.jobs.actions.creating") : t("pages.jobs.actions.create")}
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-50"
            disabled={isBusy || (!newTitle.trim() && !newTags.trim() && !jdText && !generatedDraft && !boundLeadId)}
            onClick={() => {
              void (async () => {
                const hasContent = Boolean(jdText.trim() || generatedDraft || newTitle.trim() || newTags.trim());
                if (hasContent) {
                  const confirmed = await confirmAction({
                    title: t("confirmations.jobs.clearDraft.title"),
                    description: t("confirmations.jobs.clearDraft.description"),
                    confirmLabel: t("confirmations.jobs.clearDraft.confirm"),
                    tone: "danger",
                  });
                  if (!confirmed) return;
                }
                setNewTitle("");
                setNewTags("");
                clearJdDraft();
              })();
            }}
            type="button"
          >
            {t("pages.jobs.actions.clearDraft")}
          </button>
        </div>
          </div>
        </details>
      </details>

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
          <form
            className="flex flex-wrap items-center gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              applyProfileFilters();
            }}
          >
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                size={16}
              />
              <input
                className="w-72 rounded-card border border-border bg-bg-panel py-2 pl-9 pr-3 text-sm text-text-primary outline-none focus:border-accent"
                aria-label={t("pages.jobs.filters.queryPlaceholder")}
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
              aria-label={t("pages.jobs.filters.tagsPlaceholder")}
              onChange={(event) => setTagInput(event.target.value)}
              placeholder={t("pages.jobs.filters.tagsPlaceholder")}
              value={tagInput}
            />
            <button
              className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              disabled={isBusy}
              type="submit"
            >
              <Filter size={16} />
              {t("pages.jobs.filters.apply")}
            </button>
            <button
              className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
              disabled={isBusy}
              onClick={resetProfileFilters}
              type="button"
            >
              {t("pages.jobs.filters.reset")}
            </button>
          </form>
        ) : (
          <form
            className="flex flex-wrap items-center gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              applyLeadFilters();
            }}
          >
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                size={16}
              />
              <input
                className="w-72 rounded-card border border-border bg-bg-panel py-2 pl-9 pr-3 text-sm text-text-primary outline-none focus:border-accent"
                aria-label={t("pages.jobs.leads.searchPlaceholder")}
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
            <select
              aria-label={t("pages.jobs.leads.companySize")}
              className="rounded-card border border-border bg-bg-panel px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
              data-testid="lead-size-filter"
              onChange={(event) => setLeadSizeInput(event.target.value)}
              value={leadSizeInput}
            >
              <option value="">{t("pages.jobs.leads.allSizes")}</option>
              {leadSizeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {t(`pages.jobs.leads.${option.key}`)}
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
              type="submit"
            >
              <Filter size={16} />
              {t("pages.jobs.filters.apply")}
            </button>
            <button
              className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
              disabled={isBusy}
              onClick={resetLeadFilters}
              type="button"
            >
              {t("pages.jobs.filters.reset")}
            </button>
          </form>
        )}
      </section>

      {activeTab === "leads" ? (
        <details className="fold-section rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]" data-testid="jobs-liepin-search">
          <summary>
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-3">
              <span>{t("pages.jobs.liepinSearch.title")}</span>
              <span className="text-sm font-normal text-text-secondary">{t("pages.jobs.liepinSearch.subtitle")}</span>
            </span>
          </summary>
          <div className="space-y-3 px-5 pb-5">
          <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => {
            event.preventDefault();
            if (!isBusy) void handleLiepinSearch();
          }}>
            <label className="min-w-56 flex-1 text-sm text-text-primary">
              {t("pages.jobs.liepinSearch.keyword")}
              <input
                className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 outline-none focus:border-accent"
                disabled={isBusy}
                onChange={(event) => setLiepinKeyword(event.target.value)}
                placeholder={t("pages.jobs.liepinSearch.placeholder")}
                value={liepinKeyword}
              />
            </label>
            <button className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={isBusy || !liepinKeyword.trim()} type="submit">
              <Search size={16} />
              {t(`pages.jobs.liepinSearch.${liepinSearching ? "searching" : "search"}`)}
            </button>
          </form>
          <p className="text-xs text-text-muted">{t("pages.jobs.liepinSearch.settingsHint")}</p>
          {liepinSearchResult ? (
            <p className={`text-sm ${liepinSearchResult.status === "pass" ? "text-text-secondary" : "text-error"}`} role="status">
              {liepinSearchResult.status === "blocked"
                ? t(`pages.systemSettings.liepinApi.codes.${liepinSearchResult.code}`, {
                    defaultValue: t("pages.systemSettings.liepinApi.requestBlocked"),
                  })
                : liepinSearchResult.received_count === 0
                  ? t("pages.jobs.liepinSearch.empty")
                  : t("pages.jobs.liepinSearch.success", {
                      received: liepinSearchResult.received_count,
                      imported: liepinSearchResult.imported_count,
                    })}
            </p>
          ) : null}
          {liepinSearchError ? <p className="text-sm text-error" role="alert">{liepinSearchError}</p> : null}
          </div>
        </details>
      ) : null}

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
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_420px]">
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
                  onClick={() => handleSelectProfile(profile.job_profile_id)}
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
                    <span className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
                      {profile.import_mode === "manual" ? (
                        <span className="rounded-chip border border-border px-2 py-1 text-xs text-text-secondary" data-testid="profile-manual-import">
                          {t("pages.jobs.manualImport")}
                          {profile.platform ? ` · ${t(`codes.platform.${profile.platform}`, { defaultValue: profile.platform })}` : ""}
                        </span>
                      ) : null}
                      <span
                        className={`rounded-chip border px-2.5 py-1 text-xs ${statusTone(
                          profile.status
                        )}`}
                      >
                        {t(`pages.jobs.status.${profile.status}`, {
                          defaultValue: profile.status,
                        })}
                      </span>
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

          <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto">
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
                <div className="flex items-center gap-2">
                  {profileEditing ? (
                    <>
                      <button
                        className="rounded-card border border-accent bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                        disabled={!selectedProfile || isBusy}
                        onClick={() => void handleSaveProfile().then(() => setProfileEditing(false))}
                        type="button"
                      >
                        {actionState === "saving"
                          ? t("pages.jobs.actions.saving")
                          : t("pages.jobs.actions.save")}
                      </button>
                      <button
                        className="rounded-card border border-border px-3 py-2 text-sm text-text-secondary hover:bg-bg-hover"
                        onClick={() => setProfileEditing(false)}
                        type="button"
                      >
                        {t("pages.jobs.actions.cancelEdit")}
                      </button>
                    </>
                  ) : (
                    <button
                      className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
                      data-testid="job-edit-profile"
                      disabled={!selectedProfile || isBusy}
                      onClick={() => setProfileEditing(true)}
                      type="button"
                    >
                      {t("pages.jobs.actions.edit")}
                    </button>
                  )}
                </div>
              </div>
            </div>
            <button type="button" data-testid="job-generate-resume" className="mt-3 rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50"
              disabled={isBusy || selectedProfile?.status !== "active" || !selectedProfile?.source_jd?.trim()}
              onClick={() => { if (selectedProfile?.status === "active" && selectedProfile.source_jd?.trim()) navigate(`/quick-run?job_profile_id=${encodeURIComponent(selectedProfile.job_profile_id)}`); }}>
              {t("pages.jobs.actions.generateResume")}
            </button>
            {selectedProfile && !profileEditing ? (
              <div className="space-y-4 pt-4" data-testid="job-profile-view">
                <div>
                  <h3 className="text-xl font-semibold text-text-primary">{selectedProfile.title}</h3>
                  <p className="mt-1 text-sm text-text-secondary">
                    {[selectedProfile.company, selectedProfile.company_size, formatUpdatedAt(selectedProfile.updated_at, i18n.language)].filter(Boolean).join(" · ")}
                  </p>
                  {selectedProfile.import_mode === "manual" ? (
                    <p className="mt-1 text-xs text-text-muted">
                      {t("pages.jobs.manualImport")}
                      {selectedProfile.platform ? ` · ${t(`codes.platform.${selectedProfile.platform}`, { defaultValue: selectedProfile.platform })}` : ""}
                      {selectedProfile.source_recorded_at ? ` · ${t("pages.jobs.sourceRecordedAt")} ${formatUpdatedAt(selectedProfile.source_recorded_at, i18n.language)}` : ""}
                    </p>
                  ) : null}
                  <span className={`mt-2 inline-flex rounded-chip border px-2.5 py-1 text-xs ${statusTone(selectedProfile.status)}`}>
                    {t(`pages.jobs.status.${selectedProfile.status}`)}
                  </span>
                </div>
                {(
                  [
                    ["keywords", selectedProfile.keywords, t("pages.jobs.card.noTags")],
                    ["mustHave", selectedProfile.must_have, t("pages.jobs.card.noRequirements")],
                  ] as const
                ).map(([key, values, fallback]) => (
                  <div key={key}>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">{t(`pages.jobs.fields.${key}`)}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {compactList(values, fallback).map((value) => (
                        <span key={`${key}-${value}`} className="rounded-chip border border-border bg-bg-hover px-2.5 py-1 text-xs text-text-secondary">
                          {value}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
                <details className="rounded-card border border-border">
                  <summary className="cursor-pointer select-none px-3 py-2 text-sm">{t("pages.jobs.detail.generation")}</summary>
                  <div className="space-y-3 px-3 pb-3 text-sm">
                    {(
                      [
                        ["businessDomain", selectedProfile.business_domain || "--"],
                        ["tone", selectedProfile.tone || "--"],
                        ["niceToHave", compactList(selectedProfile.nice_to_have, t("pages.jobs.card.noRequirements")).join("、")],
                        ["senioritySignal", compactList(selectedProfile.seniority_signal, t("pages.jobs.card.noRequirements")).join("、")],
                      ] as const
                    ).map(([key, value]) => (
                      <p key={key}>
                        <span className="text-text-muted">{t(`pages.jobs.fields.${key}`)}</span>
                        <span className="ml-2 text-text-primary">{value}</span>
                      </p>
                    ))}
                  </div>
                </details>
                <details className="rounded-card border border-border">
                  <summary className="cursor-pointer select-none px-3 py-2 text-sm">{t("pages.jobs.fields.sourceJd")}</summary>
                  <p className="whitespace-pre-wrap break-words px-3 pb-3 text-sm text-text-primary">{selectedProfile.source_jd || "--"}</p>
                </details>
                <details className="rounded-card border border-border" data-testid="job-manual-submission">
                  <summary className="cursor-pointer select-none px-3 py-2 text-sm">{t("pages.jobs.manualSubmission.title")}</summary>
                  <div className="space-y-3 px-3 pb-3 text-sm">
                    <p className="text-xs text-text-secondary">{t("pages.jobs.manualSubmission.hint")}</p>
                    <label className="block">
                      <span className="text-xs text-text-muted">{t("pages.jobs.manualSubmission.deliveredAt")}</span>
                      <input
                        type="date"
                        aria-label={t("pages.jobs.manualSubmission.deliveredAt")}
                        className="mt-1 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                        value={manualDeliveredAt}
                        disabled={manualSaving}
                        onChange={(event) => setManualDeliveredAt(event.target.value)}
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-text-muted">{t("pages.jobs.manualSubmission.note")}</span>
                      <textarea
                        aria-label={t("pages.jobs.manualSubmission.note")}
                        className="mt-1 min-h-16 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                        placeholder={t("pages.jobs.manualSubmission.notePlaceholder")}
                        maxLength={2000}
                        value={manualNote}
                        disabled={manualSaving}
                        onChange={(event) => setManualNote(event.target.value)}
                      />
                    </label>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        data-testid="job-manual-submission-save"
                        className="rounded-card border border-accent bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                        disabled={manualSaving || !manualDeliveredAt}
                        onClick={() => {
                          void (async () => {
                            setManualSaving(true);
                            try {
                              await recordManualSubmission({
                                job_profile_id: selectedProfile.job_profile_id,
                                delivered_at: `${manualDeliveredAt}T12:00:00+08:00`,
                                note: manualNote,
                              });
                              setManualNote("");
                              notify("success", t("toasts.jobs.manualRecorded"));
                            } catch (error) {
                              setError(getErrorMessage(error));
                            } finally {
                              setManualSaving(false);
                            }
                          })();
                        }}
                      >
                        {manualSaving ? t("pages.jobs.manualSubmission.saving") : t("pages.jobs.manualSubmission.submit")}
                      </button>
                      <button type="button" className="text-sm text-accent underline" onClick={() => navigate("/submissions")}>
                        {t("pages.jobs.manualSubmission.open")}
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            ) : null}
            {selectedProfile && profileEditing ? (
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
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_420px]">
          <div className="overflow-x-auto rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
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
                    onClick={() => handleSelectLead(lead.job_lead_id)}
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
                      {lead.company_size || lead.financing_stage ? (
                        <p className="mt-1 truncate text-xs text-text-muted">
                          {[lead.company_size, lead.financing_stage].filter(Boolean).join(" · ")}
                        </p>
                      ) : null}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm text-text-secondary">{lead.position || "--"}</p>
                      <p className="mt-1 text-xs text-text-muted">
                        {lead.salary || t("pages.jobs.leads.notProvided")} · {lead.location || t("pages.jobs.leads.notProvided")}
                      </p>
                      {lead.jd_status === "summary_only" ? <p className="mt-1 text-xs text-warning">{t("pages.jobs.leads.summaryOnly")}</p> : null}
                    </div>
                    <span
                      className={`w-fit rounded-chip border px-2.5 py-1 text-xs ${sourceTone(
                        lead.source
                      )}`}
                    >
                      {lead.import_mode === "manual"
                        ? `${t("pages.jobs.manualImport")}${lead.platform ? ` · ${t(`codes.platform.${lead.platform}`, { defaultValue: lead.platform })}` : ""}`
                        : lead.source ? t(`codes.source.${lead.source}`, { defaultValue: lead.source }) : "--"}
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

          <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto">
            <div className="border-b border-border pb-4">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.jobs.leads.detailTitle")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {selectedLead?.import_mode === "manual"
                  ? `${t("pages.jobs.manualImport")}${selectedLead.platform ? ` · ${t(`codes.platform.${selectedLead.platform}`, { defaultValue: selectedLead.platform })}` : ""}`
                  : selectedLead?.source ? t(`codes.source.${selectedLead.source}`, { defaultValue: selectedLead.source }) : "--"}
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
                  <p className="mt-2 text-sm text-text-secondary">
                    {t("pages.jobs.leads.salary")}: {selectedLead.salary || t("pages.jobs.leads.notProvided")}
                    {" · "}{t("pages.jobs.leads.location")}: {selectedLead.location || t("pages.jobs.leads.notProvided")}
                    {selectedLead.company_size ? ` · ${t("pages.jobs.leads.companySize")}: ${[selectedLead.company_size, selectedLead.financing_stage, selectedLead.industry].filter(Boolean).join(" / ")}` : null}
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
                {selectedLead.jd_status === "summary_only" ? (
                  <p className="rounded-card border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{t("pages.jobs.leads.summaryHint")}</p>
                ) : null}
                {selectedLead.platform === "liepin" ? (
                  <div className="space-y-2">
                    <button
                      className={`w-full rounded-card border px-3 py-2 text-sm disabled:opacity-50 ${selectedLead.jd_status === "complete_reviewed" ? "border-border text-text-primary hover:bg-bg-hover" : "border-accent bg-accent font-medium text-white hover:opacity-90"}`}
                      disabled={isBusy}
                      onClick={() => void handleFetchLiepinDetail()}
                      type="button"
                    >
                      {t(`pages.jobs.liepinDetail.${fetchingDetail ? "fetching" : "fetch"}`)}
                    </button>
                    <p className="text-xs text-text-muted">{t("pages.jobs.liepinDetail.hint")}</p>
                    {detailError ? <p className="text-sm text-error" role="alert">{detailError}</p> : null}
                  </div>
                ) : null}
                {selectedLead.source === "liepin_official" ? (
                  <div className="space-y-2 rounded-card border border-border p-3">
                    <button
                      type="button"
                      className="w-full rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
                      disabled={isBusy || selectedLead.jd_status !== "complete_reviewed" || !selectedLead.job_profile_id}
                      onClick={() => void handlePrepareReview()}
                    >
                      {t(`pages.jobs.liepinPreparation.${preparingReview ? "preparing" : "prepare"}`)}
                    </button>
                    <p className="text-xs text-text-muted">{t("pages.jobs.liepinPreparation.hint")}</p>
                    {preparationError ? <p className="text-sm text-error" role="alert">{preparationError}</p> : null}
                  </div>
                ) : null}
                {selectedLead.url?.startsWith("https://") ? (
                  <a className="inline-flex items-center gap-2 break-all text-sm text-accent underline" href={selectedLead.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink size={15} />{t("pages.jobs.leads.sourceLink")}
                  </a>
                ) : null}
                {selectedLead.fetched_at ? (
                  <p className="text-xs text-text-muted">{t("pages.jobs.leads.fetchedAt")}: {formatUpdatedAt(selectedLead.fetched_at, i18n.language)}</p>
                ) : null}
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
                  className={`inline-flex w-full items-center justify-center gap-2 rounded-card border px-4 py-2 text-sm font-medium disabled:opacity-50 ${selectedLead.jd_status === "complete_reviewed" || selectedLead.platform !== "liepin" ? "border-accent bg-accent text-white" : "border-border text-text-primary hover:bg-bg-hover"}`}
                  data-convert-primary={selectedLead.jd_status === "complete_reviewed" || selectedLead.platform !== "liepin" ? "true" : "false"}
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
