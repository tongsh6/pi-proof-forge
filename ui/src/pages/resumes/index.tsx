import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

function toProfileForm(profile: ProfilePayload | null): ProfileForm {
  return {
    name: profile?.name ?? "",
    phone: profile?.phone ?? "",
    email: profile?.email ?? "",
    city: profile?.city ?? "",
    current_position: profile?.current_position ?? "",
  };
}

export function ResumesPage() {
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
  const [exportPath, setExportPath] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const selectedIdRef = useRef<string | null>(null);

  const selectedResume = useMemo(
    () => items.find((item) => item.resume_id === selectedId) ?? null,
    [items, selectedId]
  );

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const loadPreview = useCallback(async (resumeId: string) => {
    selectedIdRef.current = resumeId;
    setSelectedId(resumeId);
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
        resumesResult.items[0];
      if (preferredResume) {
        await loadPreview(preferredResume.resume_id);
      } else {
        setSelectedId(null);
        setPreview(null);
        setPreviewStatus(null);
      }
      setLoadState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setLoadState("error");
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
      setError("Source path is required.");
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
      await loadData();
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setUploading(false);
    }
  }, [loadData, uploadForm]);

  const handleExport = useCallback(async () => {
    if (!selectedId) {
      setError("Select a resume first.");
      return;
    }
    if (!exportPath.trim()) {
      setError("Destination path is required.");
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
  }, [exportPath, selectedId]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Resumes</h1>
          <p className="mt-2 text-sm text-text-secondary">Profile editor, resume assets, preview, upload and export.</p>
        </div>
        <button className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover" onClick={() => void loadData()} type="button">Refresh</button>
      </header>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">Loading...</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}

      {loadState === "ready" ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)_minmax(320px,0.9fr)]">
          <section className="space-y-6 rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-text-primary">Profile</h2>
                <button className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={profileSaving} onClick={() => void handleSaveProfile()} type="button">
                  {profileSaving ? "Saving..." : "Save Profile"}
                </button>
              </div>
              <p className="mt-2 text-sm text-text-secondary">Completeness: {profile?.completeness ?? 0}%</p>
            </div>

            <div className="grid gap-4">
              {(["name", "email", "phone", "city", "current_position"] as const).map((field) => (
                <label key={field} className="space-y-2">
                  <span className="text-xs uppercase tracking-[0.18em] text-text-muted">{field.replace("_", " ")}</span>
                  <input
                    className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, [field]: event.target.value }))
                    }
                    type="text"
                    value={profileForm[field]}
                  />
                </label>
              ))}
            </div>

            <div className="border-t border-border pt-5">
              <h3 className="text-base font-semibold text-text-primary">Upload Resume</h3>
              <div className="mt-4 grid gap-3">
                <input
                  className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                  onChange={(event) => setUploadForm((current) => ({ ...current, sourcePath: event.target.value }))}
                  placeholder="Absolute source path, e.g. /Users/.../resume.pdf"
                  value={uploadForm.sourcePath}
                />
                <div className="grid gap-3 md:grid-cols-[140px_minmax(0,1fr)_auto]">
                  <select
                    className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) => setUploadForm((current) => ({ ...current, language: event.target.value }))}
                    value={uploadForm.language}
                  >
                    <option value="zh">zh</option>
                    <option value="en">en</option>
                  </select>
                  <input
                    className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                    onChange={(event) => setUploadForm((current) => ({ ...current, label: event.target.value }))}
                    placeholder="Optional label"
                    value={uploadForm.label}
                  />
                  <button className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={uploading} onClick={() => void handleUpload()} type="button">
                    {uploading ? "Uploading..." : "Upload"}
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">Resume Assets</h2>
            </div>
            <div className="divide-y divide-border">
              {items.map((item) => (
                <button key={item.resume_id} className={`flex w-full items-start justify-between gap-4 px-5 py-4 text-left ${item.resume_id === selectedId ? "bg-accent/10" : "hover:bg-bg-hover/60"}`} onClick={() => void loadPreview(item.resume_id)} type="button">
                  <div>
                    <p className="text-base font-medium text-text-primary">{item.name}</p>
                    <p className="mt-1 text-xs text-text-muted">{item.resume_id}</p>
                    <p className="mt-2 text-sm text-text-secondary">{item.job_profile_id || "--"}</p>
                  </div>
                  <span className="rounded-chip border border-border px-2.5 py-1 text-xs text-text-secondary">{item.status}</span>
                </button>
              ))}
              {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">No resumes yet.</div> : null}
            </div>
          </section>

          <section className="space-y-5 rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-text-primary">Preview</h2>
              <button className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={exporting || !selectedResume} onClick={() => void handleExport()} type="button">
                {exporting ? "Exporting..." : "Export PDF"}
              </button>
            </div>
            <input
              className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
              onChange={(event) => setExportPath(event.target.value)}
              placeholder="Destination path, e.g. /Users/.../resume.pdf"
              value={exportPath}
            />
            {preview ? (
              <div className="space-y-4">
                <div>
                  <p className="text-xl font-semibold text-text-primary">{preview.name}</p>
                  <p className="mt-2 text-sm text-text-secondary">{preview.summary || "--"}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Skills</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {preview.skills.map((skill) => (
                      <span key={skill} className="rounded-chip bg-accent/10 px-2.5 py-1 text-xs text-accent">{skill}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Experience</p>
                  <div className="mt-2 space-y-3">
                    {preview.experience.map((item) => (
                      <div key={`${item.company}-${item.period}`} className="rounded-card border border-border px-3 py-3">
                        <p className="text-sm font-medium text-text-primary">{item.company}</p>
                        <p className="mt-1 text-xs text-text-muted">{item.title} {item.period}</p>
                        {item.bullets.slice(0, 2).map((bullet) => (
                          <p key={bullet} className="mt-2 text-sm text-text-secondary">- {bullet}</p>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-text-secondary">
                {previewStatus === "pending" ? "Preview pending for uploaded raw file." : "No preview selected."}
              </p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
