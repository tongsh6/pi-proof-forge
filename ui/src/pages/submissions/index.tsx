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
              <div key={item.submission_id} className="flex items-start justify-between gap-4 px-5 py-4">
                <div>
                  <p className="text-base font-medium text-text-primary">{item.submission_id}</p>
                  <p className="mt-1 text-sm text-text-secondary">{item.channel} • {item.status}</p>
                  <p className="mt-1 text-xs text-text-muted">{formatDate(item.submitted_at)}</p>
                </div>
                <button className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null} onClick={() => void handleRetry(item.submission_id)} type="button">{retryingId === item.submission_id ? "Retrying..." : "Retry"}</button>
              </div>
            ))}
            {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">No submissions yet.</div> : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
