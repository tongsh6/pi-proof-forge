import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import { listJobProfiles } from "@/lib/sidecar/api";
import type { JobProfileListItem, JobProfilesFilters } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";

const statusOptions = ["active", "draft", "archived"] as const;

function formatFallback(value: string, fallback: string): string {
  return value.trim() ? value : fallback;
}

function formatUpdatedAt(value: string, locale: string, fallback: string): string {
  if (!value.trim()) {
    return fallback;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return fallback;
  }

  return parsed.toLocaleString(locale);
}

function parseTagsInput(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function buildStatusTone(status: string): string {
  if (status === "active") {
    return "border-accent/40 bg-accent/10 text-accent";
  }
  if (status === "draft") {
    return "border-border bg-bg-hover text-text-secondary";
  }
  if (status === "archived") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  return "border-border bg-bg-hover text-text-secondary";
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-card border border-border bg-bg-hover/50 px-4 py-3">
      <p className="text-xs uppercase tracking-[0.18em] text-text-muted">{label}</p>
      <p className="mt-3 text-2xl font-semibold text-text-primary">{value}</p>
    </div>
  );
}

export function JobsPage() {
  const { t, i18n } = useTranslation();
  const emptyLabel = t("common.empty");
  const [items, setItems] = useState<JobProfileListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [statusInput, setStatusInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [filters, setFilters] = useState<JobProfilesFilters>({
    status: null,
    query: "",
    tags: [],
  });

  const loadJobs = useCallback(async (nextFilters: JobProfilesFilters) => {
    setLoadState("loading");
    setError(null);

    try {
      const result = await listJobProfiles(nextFilters);
      setItems(result.items);
      setSelectedId((current) => {
        if (current && result.items.some((item) => item.job_profile_id === current)) {
          return current;
        }
        return result.items[0]?.job_profile_id ?? null;
      });
      setLoadState("ready");
    } catch (nextError) {
      setItems([]);
      setSelectedId(null);
      setError(getErrorMessage(nextError));
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    void loadJobs(filters);
  }, [filters, loadJobs]);

  const selectedItem = useMemo(
    () => items.find((item) => item.job_profile_id === selectedId) ?? null,
    [items, selectedId]
  );

  const onApplyFilters = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFilters({
        status: statusInput || null,
        query: queryInput.trim(),
        tags: parseTagsInput(tagInput),
      });
    },
    [queryInput, statusInput, tagInput]
  );

  const onResetFilters = useCallback(() => {
    setQueryInput("");
    setStatusInput("");
    setTagInput("");
    setFilters({ status: null, query: "", tags: [] });
  }, []);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">{t("pages.jobs.title")}</h1>
          <p className="mt-2 text-sm text-text-secondary">{t("pages.jobs.subtitle")}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            onClick={() => void loadJobs(filters)}
            type="button"
          >
            {t("common.retry")}
          </button>
          <button
            className="rounded-card border border-border bg-bg-hover px-4 py-2 text-sm text-text-muted"
            disabled
            type="button"
          >
            {t("pages.jobs.newProfileDisabled")}
          </button>
        </div>
      </header>

      <section className="flex flex-wrap gap-3">
        <span className="rounded-chip border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.16em] text-accent">
          {t("pages.jobs.tabs.profiles")}
        </span>
        <span className="rounded-chip border border-border px-3 py-1.5 text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
          {t("pages.jobs.tabs.leads")}
        </span>
      </section>

      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <form className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_200px_minmax(0,0.9fr)_auto]" onSubmit={onApplyFilters}>
          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
              {t("pages.jobs.filters.query")}
            </span>
            <input
              className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent"
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder={t("pages.jobs.filters.queryPlaceholder")}
              type="text"
              value={queryInput}
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
              {t("pages.jobs.filters.status")}
            </span>
            <select
              className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent"
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
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.18em] text-text-muted">
              {t("pages.jobs.filters.tags")}
            </span>
            <input
              className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent"
              onChange={(event) => setTagInput(event.target.value)}
              placeholder={t("pages.jobs.filters.tagsPlaceholder")}
              type="text"
              value={tagInput}
            />
          </label>

          <div className="flex items-end gap-3">
            <button
              className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
              type="submit"
            >
              {t("pages.jobs.filters.apply")}
            </button>
            <button
              className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
              onClick={onResetFilters}
              type="button"
            >
              {t("pages.jobs.filters.reset")}
            </button>
          </div>
        </form>
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

      {loadState === "ready" && items.length === 0 ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-text-primary">{t("pages.jobs.empty.title")}</p>
          <p className="mt-2 text-sm text-text-secondary">{t("pages.jobs.empty.subtitle")}</p>
        </section>
      ) : null}

      {loadState === "ready" && items.length > 0 ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(360px,0.95fr)]">
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-4 px-1">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{t("pages.jobs.profileGridTitle")}</h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.jobs.profileCount", { count: items.length })}
                </p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
              {items.map((item) => {
                const isSelected = item.job_profile_id === selectedId;

                return (
                  <button
                    key={item.job_profile_id}
                    className={`rounded-panel border bg-bg-panel p-5 text-left shadow-[var(--shadow-panel)] transition-colors ${
                      isSelected
                        ? "border-accent/60 bg-accent/5"
                        : "border-border hover:bg-bg-hover/40"
                    }`}
                    onClick={() => setSelectedId(item.job_profile_id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-lg font-semibold text-text-primary">{item.title}</p>
                        <p className="mt-1 text-sm text-text-secondary">
                          {formatFallback(item.company, emptyLabel)}
                        </p>
                      </div>
                      <span
                        className={`rounded-chip border px-2.5 py-1 text-xs font-medium uppercase tracking-[0.14em] ${buildStatusTone(
                          item.status
                        )}`}
                      >
                        {t(`pages.jobs.status.${item.status}`, { defaultValue: item.status })}
                      </span>
                    </div>

                    <p className="mt-4 line-clamp-2 min-h-[2.5rem] text-sm text-text-secondary">
                      {item.must_have.length > 0
                        ? item.must_have.join(" · ")
                        : t("pages.jobs.card.noRequirements")}
                    </p>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {item.keywords.length > 0 ? (
                        item.keywords.slice(0, 4).map((keyword) => (
                          <span
                            key={`${item.job_profile_id}-${keyword}`}
                            className="rounded-chip bg-accent/10 px-2.5 py-1 text-xs text-accent"
                          >
                            {keyword}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-text-muted">{t("pages.jobs.card.noTags")}</span>
                      )}
                    </div>

                    <div className="mt-5 border-t border-border pt-4">
                      <div className="grid gap-3 sm:grid-cols-3">
                        <MetricCard label={t("pages.jobs.metrics.matchScore")} value={item.match_score} />
                        <MetricCard label={t("pages.jobs.metrics.evidence")} value={item.evidence_count} />
                        <MetricCard label={t("pages.jobs.metrics.resumes")} value={item.resume_count} />
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.jobs.detailTitle")}</h2>
              <p className="mt-1 text-sm text-text-secondary">
                {selectedItem?.job_profile_id ?? t("common.empty")}
              </p>
            </div>

            {selectedItem ? (
              <div className="space-y-5 pt-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="text-xl font-semibold text-text-primary">{selectedItem.title}</p>
                    <span
                      className={`rounded-chip border px-2.5 py-1 text-xs font-medium uppercase tracking-[0.14em] ${buildStatusTone(
                        selectedItem.status
                      )}`}
                    >
                      {t(`pages.jobs.status.${selectedItem.status}`, {
                        defaultValue: selectedItem.status,
                      })}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-text-secondary">
                    {formatFallback(selectedItem.company, emptyLabel)}
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.businessDomain")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatFallback(selectedItem.business_domain, emptyLabel)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.updatedAt")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatUpdatedAt(selectedItem.updated_at, i18n.language, emptyLabel)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.sourceJd")}
                    </p>
                    <p className="mt-2 break-all text-sm text-text-primary">
                      {formatFallback(selectedItem.source_jd, emptyLabel)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.jobs.fields.tone")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatFallback(selectedItem.tone, emptyLabel)}
                    </p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <MetricCard label={t("pages.jobs.metrics.matchScore")} value={selectedItem.match_score} />
                  <MetricCard label={t("pages.jobs.metrics.evidence")} value={selectedItem.evidence_count} />
                  <MetricCard label={t("pages.jobs.metrics.resumes")} value={selectedItem.resume_count} />
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.keywords")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selectedItem.keywords.length > 0 ? (
                      selectedItem.keywords.map((keyword) => (
                        <span
                          key={`${selectedItem.job_profile_id}-keyword-${keyword}`}
                          className="rounded-chip bg-accent/10 px-2.5 py-1 text-xs text-accent"
                        >
                          {keyword}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-text-secondary">{t("common.empty")}</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.mustHave")}
                  </p>
                  <div className="mt-2 space-y-2">
                    {selectedItem.must_have.length > 0 ? (
                      selectedItem.must_have.map((item) => (
                        <div
                          key={`${selectedItem.job_profile_id}-must-${item}`}
                          className="rounded-card border border-border px-3 py-2 text-sm text-text-primary"
                        >
                          {item}
                        </div>
                      ))
                    ) : (
                      <span className="text-sm text-text-secondary">{t("common.empty")}</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.niceToHave")}
                  </p>
                  <div className="mt-2 space-y-2">
                    {selectedItem.nice_to_have.length > 0 ? (
                      selectedItem.nice_to_have.map((item) => (
                        <div
                          key={`${selectedItem.job_profile_id}-nice-${item}`}
                          className="rounded-card border border-border px-3 py-2 text-sm text-text-primary"
                        >
                          {item}
                        </div>
                      ))
                    ) : (
                      <span className="text-sm text-text-secondary">{t("common.empty")}</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.jobs.fields.senioritySignal")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selectedItem.seniority_signal.length > 0 ? (
                      selectedItem.seniority_signal.map((item) => (
                        <span
                          key={`${selectedItem.job_profile_id}-signal-${item}`}
                          className="rounded-chip border border-border px-2.5 py-1 text-xs text-text-primary"
                        >
                          {item}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-text-secondary">{t("common.empty")}</span>
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
