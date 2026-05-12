import { useCallback, useEffect, useState } from "react";
import { Eye, RefreshCw, RotateCcw } from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { getSubmissionDetail, listSubmissions, retrySubmission } from "@/lib/sidecar/api";
import type { SubmissionDetail, SubmissionListItem } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";

function formatDate(value: string): string {
  if (!value.trim()) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusClassName(status: string): string {
  if (status === "success" || status === "done") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "blocked") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "failed") {
    return "border-error/40 bg-error/10 text-error";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

function detailText(item: SubmissionListItem): string {
  if (item.error) return item.error;
  if (item.last_step.detail) return item.last_step.detail;
  return "No detail";
}

export function SubmissionsPage() {
  const [items, setItems] = useState<SubmissionListItem[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [detailState, setDetailState] = useState<LoadState>("ready");

  const loadData = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const result = await listSubmissions();
      setItems(result.items);
      if (selectedId && !result.items.some((item) => item.submission_id === selectedId)) {
        setSelectedId(null);
        setDetail(null);
      }
      setLoadState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setLoadState("error");
    }
  }, [selectedId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleRetry = useCallback(async (submissionId: string) => {
    setRetryingId(submissionId);
    try {
      await retrySubmission(submissionId);
      await loadData();
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setRetryingId(null);
    }
  }, [loadData]);

  const handleSelect = useCallback(async (submissionId: string) => {
    setSelectedId(submissionId);
    setDetailState("loading");
    setError(null);
    try {
      const result = await getSubmissionDetail(submissionId);
      setDetail(result.submission);
      setDetailState("ready");
    } catch (nextError) {
      setDetail(null);
      setError(getErrorMessage(nextError));
      setDetailState("error");
    }
  }, []);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Submissions</h1>
          <p className="mt-2 text-sm text-text-secondary">Recent application attempts from sidecar logs.</p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void loadData()} type="button">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </header>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">Loading...</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}

      {loadState === "ready" ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.7fr)]">
          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">Submission Runs</h2>
            </div>
            <div className="divide-y divide-border">
              {items.map((item) => (
                <div key={item.submission_id} className="grid gap-4 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-base font-medium text-text-primary">{item.submission_id}</p>
                      <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(item.status)}`}>
                        {item.status || "unknown"}
                      </span>
                      {item.mode ? <span className="rounded-chip border border-border px-2 py-0.5 text-xs text-text-secondary">{item.mode}</span> : null}
                    </div>
                    <p className="mt-2 text-sm text-text-secondary">
                      {item.channel || "unknown channel"} · {formatDate(item.submitted_at)}
                    </p>
                    {item.job_url ? (
                      <p className="mt-2 break-all font-mono text-xs text-text-muted">{item.job_url}</p>
                    ) : null}
                    <div className="mt-3 grid gap-2 text-xs text-text-secondary md:grid-cols-2">
                      <div className="rounded-card border border-border bg-bg-primary/40 p-3">
                        <p className="text-text-muted">Last step</p>
                        <p className="mt-1 font-medium text-text-primary">{item.last_step.name || "--"} · {item.last_step.status || "--"}</p>
                        <p className="mt-1 break-words text-text-secondary">{detailText(item)}</p>
                      </div>
                      <div className="rounded-card border border-border bg-bg-primary/40 p-3">
                        <p className="text-text-muted">Rate limit</p>
                        <p className="mt-1 font-medium text-text-primary">{item.rate_limit_status || "--"}</p>
                        <p className="mt-1 break-words text-text-secondary">{item.rate_limit_detail || "--"}</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-start gap-2 md:justify-end">
                    <button className="inline-flex h-10 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={detailState === "loading" && selectedId === item.submission_id} onClick={() => void handleSelect(item.submission_id)} type="button">
                      <Eye className="h-4 w-4" aria-hidden="true" />
                      Details
                    </button>
                    <button className="inline-flex h-10 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void handleRetry(item.submission_id)} type="button">
                      <RotateCcw className="h-4 w-4" aria-hidden="true" />
                      {retryingId === item.submission_id ? "Retrying..." : "Retry"}
                    </button>
                  </div>
                </div>
              ))}
              {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">No submissions yet.</div> : null}
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">Run Detail</h2>
            </div>
            {detailState === "loading" ? <div className="p-5 text-sm text-text-secondary">Loading detail...</div> : null}
            {detailState === "error" ? <div className="p-5 text-sm text-error">{error}</div> : null}
            {detailState === "ready" && detail ? (
              <div className="space-y-5 p-5">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-text-primary">{detail.submission_id}</p>
                    <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(detail.status)}`}>
                      {detail.status || "unknown"}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-text-secondary">
                    {detail.channel || "unknown channel"} · {formatDate(detail.started_at)} → {formatDate(detail.ended_at)}
                  </p>
                </div>
                <div className="grid gap-2 text-xs text-text-secondary">
                  <p className="break-all"><span className="text-text-muted">Resume</span> {detail.resume_path || "--"}</p>
                  <p className="break-all"><span className="text-text-muted">Profile</span> {detail.profile_path || "--"}</p>
                  <p className="break-all"><span className="text-text-muted">JSON</span> {detail.log_json_path || "--"}</p>
                  <p className="break-all"><span className="text-text-muted">YAML</span> {detail.log_yaml_path || "--"}</p>
                </div>
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-text-primary">Steps</h3>
                  <div className="space-y-2">
                    {detail.steps.map((step, index) => (
                      <div key={`${step.name}-${index}`} className="rounded-card border border-border bg-bg-primary/40 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs text-text-muted">{String(index + 1).padStart(2, "0")}</span>
                          <span className="text-sm font-medium text-text-primary">{step.name || "--"}</span>
                          <span className={`rounded-chip border px-2 py-0.5 text-xs ${statusClassName(step.status)}`}>{step.status || "--"}</span>
                        </div>
                        <p className="mt-2 break-words text-xs text-text-secondary">{step.detail || "--"}</p>
                        {step.screenshot ? (
                          <p className="mt-2 break-all font-mono text-xs text-text-muted">
                            {step.screenshot_exists ? step.screenshot_path : `${step.screenshot} (missing)`}
                          </p>
                        ) : null}
                      </div>
                    ))}
                    {detail.steps.length === 0 ? <p className="text-sm text-text-secondary">No steps recorded.</p> : null}
                  </div>
                </div>
              </div>
            ) : null}
            {detailState === "ready" && !detail ? (
              <div className="p-5 text-sm text-text-secondary">Select a run to inspect its steps and log paths.</div>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
