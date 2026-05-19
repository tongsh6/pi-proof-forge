import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  BadgeCheck,
  Clock3,
  Download,
  Eye,
  FileText,
  Languages,
  RefreshCw,
  Upload,
  UserRoundPen,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import {
  exportResumePdf,
  getProfile,
  getResumePreview,
  listResumes,
  updateProfile,
  uploadResume,
} from "@/lib/sidecar/api";
import type { ProfilePayload, ResumeListItem, ResumePreview } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";

type ProfileForm = {
  name: string;
  phone: string;
  email: string;
  city: string;
  current_position: string;
};

type UploadForm = {
  sourcePath: string;
  language: string;
  label: string;
};

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

function recordVerifyEvent(event: string, details: Record<string, unknown> = {}) {
  if (verifyScenario !== "resumes") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
}

function toProfileForm(profile: ProfilePayload | null): ProfileForm {
  return {
    name: profile?.name ?? "",
    phone: profile?.phone ?? "",
    email: profile?.email ?? "",
    city: profile?.city ?? "",
    current_position: profile?.current_position ?? "",
  };
}

function formatDate(value: string, locale: string): string {
  if (!value.trim()) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale);
}

function scoreTone(score: number): string {
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning";
  return "text-text-secondary";
}

function statusTone(status: string): string {
  if (status === "latest") return "border-success/40 bg-success/10 text-success";
  if (status === "uploaded") return "border-accent/40 bg-accent/10 text-accent";
  if (status === "low") return "border-warning/40 bg-warning/10 text-warning";
  return "border-border bg-bg-hover text-text-secondary";
}

export function ResumesPage() {
  const { t, i18n } = useTranslation();
  const [profile, setProfile] = useState<ProfilePayload | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileForm>(() => toProfileForm(null));
  const [items, setItems] = useState<ResumeListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<ResumePreview | null>(null);
  const [previewStatus, setPreviewStatus] = useState<string | null>(null);
  const [uploadForm, setUploadForm] = useState<UploadForm>({
    sourcePath: "",
    language: "zh",
    label: "",
  });
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [exportPath, setExportPath] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const selectedIdRef = useRef<string | null>(null);

  const uploadedResumes = useMemo(
    () => items.filter((item) => item.status === "uploaded"),
    [items]
  );
  const generatedResumes = useMemo(
    () => items.filter((item) => item.status !== "uploaded"),
    [items]
  );
  const selectedResume = useMemo(
    () => items.find((item) => item.resume_id === selectedId) ?? null,
    [items, selectedId]
  );
  const missingFields = profile?.missing_fields ?? [];

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const loadPreview = useCallback(async (resumeId: string) => {
    selectedIdRef.current = resumeId;
    setSelectedId(resumeId);
    setPreviewStatus(null);
    try {
      const result = await getResumePreview(resumeId);
      if (selectedIdRef.current !== resumeId) {
        return;
      }
      setPreview(result.preview);
      setPreviewStatus(result.preview_status ?? null);
    } catch (nextError) {
      if (selectedIdRef.current !== resumeId) {
        return;
      }
      setPreview(null);
      setPreviewStatus(null);
      setError(getErrorMessage(nextError));
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const [profileResult, resumesResult] = await Promise.all([getProfile(), listResumes()]);
      setProfile(profileResult.profile);
      setProfileForm(toProfileForm(profileResult.profile));
      setItems(resumesResult.items);
      const preferredResume =
        resumesResult.items.find((item) => item.resume_id === selectedIdRef.current) ??
        resumesResult.items.find((item) => item.status !== "uploaded") ??
        resumesResult.items[0];
      if (preferredResume) {
        await loadPreview(preferredResume.resume_id);
      } else {
        setSelectedId(null);
        setPreview(null);
        setPreviewStatus(null);
      }
      setLoadState("ready");
      recordVerifyEvent("resumes.load.ready", {
        profile_completeness: profileResult.profile.completeness,
        resume_count: resumesResult.items.length,
        uploaded_count: resumesResult.items.filter((item) => item.status === "uploaded").length,
        generated_count: resumesResult.items.filter((item) => item.status !== "uploaded").length,
        has_preview: Boolean(preferredResume),
      });
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setLoadState("error");
      recordVerifyEvent("resumes.load.error", {
        error: getErrorMessage(nextError),
      });
    }
  }, [loadPreview]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSaveProfile = useCallback(async () => {
    setProfileSaving(true);
    setError(null);
    try {
      await updateProfile(profileForm);
      await loadData();
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setProfileSaving(false);
    }
  }, [loadData, profileForm]);

  const handleUpload = useCallback(async () => {
    if (!uploadForm.sourcePath.trim()) {
      setError(t("pages.resumes.errors.sourcePathRequired"));
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadResume({
        source_paths: [uploadForm.sourcePath.trim()],
        language: uploadForm.language || undefined,
        label: uploadForm.label.trim() || undefined,
      });
      setUploadForm({ sourcePath: "", language: "zh", label: "" });
      setShowUploadForm(false);
      await loadData();
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setUploading(false);
    }
  }, [loadData, t, uploadForm]);

  const handleExport = useCallback(async () => {
    if (!selectedId) {
      setError(t("pages.resumes.errors.selectResume"));
      return;
    }
    if (!exportPath.trim()) {
      setError(t("pages.resumes.errors.destinationRequired"));
      return;
    }
    setExporting(true);
    setError(null);
    try {
      await exportResumePdf({ resume_id: selectedId, destination: exportPath.trim() });
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setExporting(false);
    }
  }, [exportPath, selectedId, t]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.resumes.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.resumes.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            onClick={() => void loadData()}
            type="button"
          >
            <RefreshCw size={16} />
            {t("pages.resumes.refresh")}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            onClick={() => setShowUploadForm((current) => !current)}
            type="button"
          >
            <Upload size={16} />
            {t("pages.resumes.upload")}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            disabled={exporting || !selectedResume}
            onClick={() => void handleExport()}
            type="button"
          >
            <Download size={16} />
            {exporting ? t("pages.resumes.exporting") : t("pages.resumes.exportPdf")}
          </button>
        </div>
      </header>

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
        <section className="rounded-card border border-error/40 bg-error/10 px-4 py-3 text-sm text-error">
          {error}
        </section>
      ) : null}

      {loadState === "ready" ? (
        <div className="grid gap-5 xl:grid-cols-[320px_320px_minmax(0,1fr)]">
          <section className="space-y-5 rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-text-primary">
                  {t("pages.resumes.profile.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.resumes.profile.subtitle")}
                </p>
              </div>
              <button
                className="inline-flex h-10 w-10 items-center justify-center rounded-card border border-border text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
                disabled={profileSaving}
                onClick={() => void handleSaveProfile()}
                title={t("pages.resumes.profile.save")}
                type="button"
              >
                <UserRoundPen size={18} />
              </button>
            </div>

            <div className="rounded-card border border-border bg-bg-hover/40 p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-text-primary">
                  {t("pages.resumes.profile.completeness")}
                </span>
                <span className="text-lg font-semibold text-accent">
                  {profile?.completeness ?? 0}%
                </span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-bg-primary">
                <div
                  className="h-2 rounded-full bg-accent"
                  style={{ width: `${profile?.completeness ?? 0}%` }}
                />
              </div>
              <p className="mt-3 text-xs text-text-muted">
                {t("pages.resumes.profile.updatedAt", {
                  value: formatDate(profile?.updated_at ?? "", i18n.language),
                })}
              </p>
            </div>

            <div className="grid gap-3">
              {(["name", "email", "phone", "city", "current_position"] as const).map((field) => (
                <label key={field} className="space-y-1.5">
                  <span className="text-xs font-medium text-text-secondary">
                    {t(`pages.resumes.profile.fields.${field}`)}
                  </span>
                  <input
                    className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, [field]: event.target.value }))
                    }
                    type={field === "email" ? "email" : "text"}
                    value={profileForm[field]}
                  />
                </label>
              ))}
            </div>

            <div className="rounded-card border border-border bg-bg-primary/40 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                {missingFields.length > 0 ? (
                  <AlertTriangle size={16} className="text-warning" />
                ) : (
                  <BadgeCheck size={16} className="text-success" />
                )}
                {t("pages.resumes.profile.missingTitle")}
              </div>
              <p className="mt-2 text-sm text-text-secondary">
                {missingFields.length > 0
                  ? missingFields
                      .map((field) => t(`pages.resumes.profile.fields.${field}`))
                      .join(", ")
                  : t("pages.resumes.profile.noMissing")}
              </p>
            </div>
          </section>

          <section className="space-y-5 rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div>
              <h2 className="text-base font-semibold text-text-primary">
                {t("pages.resumes.uploaded.title")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {t("pages.resumes.uploaded.count", { count: uploadedResumes.length })}
              </p>
            </div>

            {showUploadForm ? (
              <div className="space-y-3 rounded-card border border-accent/30 bg-accent/5 p-4">
                <input
                  className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                  onChange={(event) =>
                    setUploadForm((current) => ({ ...current, sourcePath: event.target.value }))
                  }
                  placeholder={t("pages.resumes.uploaded.sourcePlaceholder")}
                  value={uploadForm.sourcePath}
                />
                <div className="grid gap-3 md:grid-cols-[96px_minmax(0,1fr)] xl:grid-cols-1">
                  <select
                    className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) =>
                      setUploadForm((current) => ({ ...current, language: event.target.value }))
                    }
                    value={uploadForm.language}
                  >
                    <option value="zh">zh</option>
                    <option value="en">en</option>
                  </select>
                  <input
                    className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) =>
                      setUploadForm((current) => ({ ...current, label: event.target.value }))
                    }
                    placeholder={t("pages.resumes.uploaded.labelPlaceholder")}
                    value={uploadForm.label}
                  />
                </div>
                <button
                  className="inline-flex w-full items-center justify-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  disabled={uploading}
                  onClick={() => void handleUpload()}
                  type="button"
                >
                  <Upload size={16} />
                  {uploading ? t("pages.resumes.uploaded.uploading") : t("pages.resumes.uploaded.submit")}
                </button>
              </div>
            ) : null}

            <div className="space-y-3">
              {uploadedResumes.map((item) => (
                <button
                  key={item.resume_id}
                  className={`w-full rounded-card border px-4 py-3 text-left transition-colors ${
                    item.resume_id === selectedId
                      ? "border-accent bg-accent/10"
                      : "border-border bg-bg-primary/30 hover:bg-bg-hover/60"
                  }`}
                  onClick={() => void loadPreview(item.resume_id)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-text-primary">{item.name}</p>
                      <p className="mt-1 truncate text-xs text-text-muted">{item.resume_id}</p>
                    </div>
                    <Languages size={16} className="shrink-0 text-accent" />
                  </div>
                  <p className="mt-3 text-xs text-text-secondary">
                    {formatDate(item.updated_at, i18n.language)}
                  </p>
                </button>
              ))}
              {uploadedResumes.length === 0 ? (
                <div className="rounded-card border border-border bg-bg-primary/30 p-5 text-sm text-text-secondary">
                  {t("pages.resumes.uploaded.empty")}
                </div>
              ) : null}
            </div>
          </section>

          <section className="space-y-5 rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-text-primary">
                  {t("pages.resumes.generated.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.resumes.generated.count", { count: generatedResumes.length })}
                </p>
              </div>
              <input
                className="min-w-[280px] rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent"
                onChange={(event) => setExportPath(event.target.value)}
                placeholder={t("pages.resumes.generated.destinationPlaceholder")}
                value={exportPath}
              />
            </div>

            <div className="grid gap-5 2xl:grid-cols-[minmax(280px,0.85fr)_minmax(0,1.15fr)]">
              <div className="space-y-3">
                {generatedResumes.map((item) => (
                  <button
                    key={item.resume_id}
                    className={`w-full rounded-card border px-4 py-3 text-left transition-colors ${
                      item.resume_id === selectedId
                        ? "border-accent bg-accent/10"
                        : "border-border bg-bg-primary/30 hover:bg-bg-hover/60"
                    }`}
                    onClick={() => void loadPreview(item.resume_id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-text-primary">
                          {item.name}
                        </p>
                        <p className="mt-1 truncate text-xs text-text-muted">
                          {item.company || item.job_profile_id || "--"}
                        </p>
                      </div>
                      <span className={`shrink-0 rounded-chip border px-2.5 py-1 text-xs ${statusTone(item.status)}`}>
                        {item.status}
                      </span>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-3 text-xs">
                      <span className={scoreTone(item.score)}>
                        {t("pages.resumes.generated.score", { score: item.score })}
                      </span>
                      <span className="text-text-muted">
                        {formatDate(item.updated_at, i18n.language)}
                      </span>
                    </div>
                  </button>
                ))}
                {generatedResumes.length === 0 ? (
                  <div className="rounded-card border border-border bg-bg-primary/30 p-5 text-sm text-text-secondary">
                    {t("pages.resumes.generated.empty")}
                  </div>
                ) : null}
              </div>

              <div className="min-h-[520px] rounded-card border border-border bg-[#f8fafc] p-6 text-[#334155] shadow-[var(--shadow-card)]">
                {preview ? (
                  <article className="mx-auto max-w-[720px] space-y-6">
                    <header className="border-b border-[#cbd5e1] pb-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h3 className="text-2xl font-bold text-[#0f172a]">{preview.name || "--"}</h3>
                          <p className="mt-2 text-sm text-[#475569]">
                            {[preview.contact.phone, preview.contact.email, preview.contact.city]
                              .filter(Boolean)
                              .join(" · ") || "--"}
                          </p>
                        </div>
                        <span className="inline-flex items-center gap-1 rounded-full bg-[#e0f2fe] px-3 py-1 text-xs font-medium text-[#0369a1]">
                          <Eye size={14} />
                          {t("pages.resumes.preview.label")}
                        </span>
                      </div>
                    </header>

                    <section>
                      <h4 className="text-sm font-bold uppercase tracking-wide text-[#0f172a]">
                        {t("pages.resumes.preview.summary")}
                      </h4>
                      <p className="mt-2 text-sm leading-6 text-[#334155]">
                        {preview.summary || "--"}
                      </p>
                    </section>

                    <section>
                      <h4 className="text-sm font-bold uppercase tracking-wide text-[#0f172a]">
                        {t("pages.resumes.preview.experience")}
                      </h4>
                      <div className="mt-3 space-y-4">
                        {preview.experience.map((item) => (
                          <div key={`${item.company}-${item.period}`} className="space-y-1">
                            <div className="flex flex-wrap items-baseline justify-between gap-2">
                              <p className="font-semibold text-[#0f172a]">{item.company}</p>
                              <p className="text-xs text-[#64748b]">{item.period}</p>
                            </div>
                            <p className="text-sm font-medium text-[#475569]">{item.title}</p>
                            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6">
                              {item.bullets.slice(0, 4).map((bullet) => (
                                <li key={bullet}>{bullet}</li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    </section>

                    <section>
                      <h4 className="text-sm font-bold uppercase tracking-wide text-[#0f172a]">
                        {t("pages.resumes.preview.skills")}
                      </h4>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {preview.skills.length > 0 ? (
                          preview.skills.map((skill) => (
                            <span key={skill} className="rounded-full bg-[#e2e8f0] px-3 py-1 text-xs text-[#334155]">
                              {skill}
                            </span>
                          ))
                        ) : (
                          <span className="text-sm text-[#64748b]">--</span>
                        )}
                      </div>
                    </section>
                  </article>
                ) : (
                  <div className="flex h-full min-h-[460px] flex-col items-center justify-center text-center">
                    {previewStatus === "pending" ? (
                      <Clock3 size={32} className="text-[#0369a1]" />
                    ) : (
                      <FileText size={32} className="text-[#64748b]" />
                    )}
                    <p className="mt-4 max-w-sm text-sm text-[#475569]">
                      {previewStatus === "pending"
                        ? t("pages.resumes.preview.pending")
                        : t("pages.resumes.preview.empty")}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
