import { useCallback, useEffect, useState } from "react";
import { getErrorMessage } from "@/lib/errors";
import { listSubmissions, retrySubmission } from "@/lib/sidecar/api";
import type { SubmissionListItem } from "@/lib/sidecar/types";

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

  const loadData = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const result = await listSubmissions();
      setItems(result.items);
      setLoadState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setLoadState("error");
    }
  }, []);

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

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Submissions</h1>
          <p className="mt-2 text-sm text-text-secondary">Recent application attempts from sidecar logs.</p>
        </div>
        <button className="rounded-card border border-border px-4 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void loadData()} type="button">Refresh</button>
      </header>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">Loading...</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}

      {loadState === "ready" ? (
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
                <button className="h-10 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void handleRetry(item.submission_id)} type="button">{retryingId === item.submission_id ? "Retrying..." : "Retry"}</button>
              </div>
            ))}
            {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">No submissions yet.</div> : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
