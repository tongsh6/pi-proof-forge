import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import {
  listEvidence,
  listJobProfiles,
  getOverview,
} from "@/lib/sidecar/api";
import type {
  EvidenceListItem,
  JobProfileListItem,
  OverviewMetrics,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type RunState = "idle" | "configuring" | "ready_to_run";

const PIPELINE_STEPS = [
  { key: "extract", labelKey: "pages.quickRun.steps.extract" },
  { key: "match", labelKey: "pages.quickRun.steps.match" },
  { key: "generate", labelKey: "pages.quickRun.steps.generate" },
  { key: "evaluate", labelKey: "pages.quickRun.steps.evaluate" },
] as const;

export function QuickRunPage() {
  const { t } = useTranslation();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [runState, setRunState] = useState<RunState>("idle");
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
  const [evidenceCards, setEvidenceCards] = useState<EvidenceListItem[]>([]);
  const [jobProfiles, setJobProfiles] = useState<JobProfileListItem[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [copiedCommand, setCopiedCommand] = useState(false);

  const load = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const [overview, evidence, jobs] = await Promise.all([
        getOverview(),
        listEvidence(),
        listJobProfiles(),
      ]);
      setMetrics(overview.metrics);
      setEvidenceCards(evidence.items);
      setJobProfiles(jobs.items);
      if (jobs.items.length > 0 && !selectedProfileId) {
        setSelectedProfileId(jobs.items[0].job_profile_id);
      }
      setLoadState("ready");
    } catch (e) {
      setLoadState("error");
      setError(getErrorMessage(e));
    }
  }, [selectedProfileId]);

  useEffect(() => {
    void load();
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedProfile = jobProfiles.find(
    (jp) => jp.job_profile_id === selectedProfileId,
  );

  const eligibleCards = evidenceCards.filter((c) => c.status !== "draft");
  const canRun =
    runState === "ready_to_run" &&
    eligibleCards.length > 0 &&
    selectedProfileId !== "";

  const pipelineCliCommand = selectedProfile
    ? `python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/${selectedProfile.job_profile_id}.yaml`
    : "python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml";

  const agentCliCommand = selectedProfile
    ? `python3 -m tools.cli.entrypoints agent --policy policy.yaml --evidence-dir evidence_cards --job-profile job_profiles/${selectedProfile.job_profile_id}.yaml --run-id run-$(date +%s)`
    : `python3 -m tools.cli.entrypoints agent --policy policy.yaml --evidence-dir evidence_cards --job-profile job_profiles/jp-2026-001.yaml --run-id run-$(date +%s)`;

  const handleCopy = (text: string) => {
    void navigator.clipboard.writeText(text);
    setCopiedCommand(true);
    setTimeout(() => setCopiedCommand(false), 2000);
  };

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.quickRun.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.quickRun.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
        >
          {t("common.retry")}
        </button>
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

      {loadState === "ready" ? (
        <>
          {/* Pipeline Flow Diagram */}
          <section className="rounded-panel border border-border bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.quickRun.pipelineTitle")}
            </h2>
            <p className="mt-1 text-sm text-text-secondary">
              {t("pages.quickRun.pipelineSubtitle")}
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              {PIPELINE_STEPS.map((step, idx) => (
                <div key={step.key} className="flex items-center gap-3">
                  <div className="flex items-center gap-2 rounded-card border border-accent/30 bg-accent/5 px-4 py-3">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/15 text-xs font-bold text-accent">
                      {idx + 1}
                    </span>
                    <span className="text-sm font-medium text-text-primary">
                      {t(step.labelKey)}
                    </span>
                  </div>
                  {idx < PIPELINE_STEPS.length - 1 ? (
                    <span className="text-text-muted">→</span>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          {/* Resource Summary */}
          <section className="grid gap-4 md:grid-cols-3">
            <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.quickRun.evidenceCards")}
              </p>
              <p className="mt-3 text-3xl font-semibold text-text-primary">
                {metrics?.evidence_count ?? evidenceCards.length}
              </p>
              <p className="mt-1 text-sm text-text-secondary">
                {eligibleCards.length} eligible
              </p>
            </article>
            <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.quickRun.jobProfiles")}
              </p>
              <p className="mt-3 text-3xl font-semibold text-text-primary">
                {metrics?.matched_jobs_count ?? jobProfiles.length}
              </p>
              <p className="mt-1 text-sm text-text-secondary">
                {jobProfiles.filter((j) => j.status === "active").length} active
              </p>
            </article>
            <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.quickRun.resumes")}
              </p>
              <p className="mt-3 text-3xl font-semibold text-text-primary">
                {metrics?.resume_count ?? 0}
              </p>
              <p className="mt-1 text-sm text-text-secondary">
                generated versions
              </p>
            </article>
          </section>

          {/* Job Profile Selector */}
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.quickRun.selectProfile")}
            </h2>
            <p className="mt-1 text-sm text-text-secondary">
              {t("pages.quickRun.selectProfileHint")}
            </p>

            {jobProfiles.length === 0 ? (
              <p className="mt-4 text-sm text-text-secondary">
                {t("common.empty")}
              </p>
            ) : (
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {jobProfiles.map((jp) => {
                  const isSelected = jp.job_profile_id === selectedProfileId;
                  return (
                    <button
                      key={jp.job_profile_id}
                      type="button"
                      onClick={() => {
                        setSelectedProfileId(jp.job_profile_id);
                        setRunState("ready_to_run");
                      }}
                      className={`rounded-card border p-4 text-left transition-colors ${
                        isSelected
                          ? "border-accent bg-accent/10"
                          : "border-border hover:bg-bg-hover"
                      }`}
                    >
                      <p className="font-medium text-text-primary">
                        {jp.title}
                      </p>
                      <p className="mt-1 text-xs text-text-muted">
                        {jp.company || jp.business_domain || jp.job_profile_id}
                      </p>
                      {jp.keywords && jp.keywords.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {jp.keywords.slice(0, 5).map((kw) => (
                            <span
                              key={kw}
                              className="rounded-chip bg-bg-hover px-2 py-0.5 text-xs text-text-secondary"
                            >
                              {kw}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-2 flex gap-3 text-xs text-text-muted">
                        <span>Match: {jp.match_score}</span>
                        <span>Evidence: {jp.evidence_count}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* CLI Commands */}
          {canRun ? (
            <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.quickRun.runTitle")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {t("pages.quickRun.runSubtitle")}
              </p>

              <div className="mt-4 space-y-4">
                {/* Pipeline Command */}
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
                    {t("pages.quickRun.pipelineCommand")}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <code className="flex-1 rounded-card border border-border bg-bg-primary px-3 py-2.5 font-mono text-sm text-text-primary break-all">
                      {pipelineCliCommand}
                    </code>
                    <button
                      type="button"
                      onClick={() => handleCopy(pipelineCliCommand)}
                      className="shrink-0 rounded-card border border-accent/30 px-3 py-2 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                    >
                      {copiedCommand ? "Copied!" : "Copy"}
                    </button>
                  </div>
                </div>

                {/* Agent Command */}
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
                    {t("pages.quickRun.agentCommand")}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <code className="flex-1 rounded-card border border-border bg-bg-primary px-3 py-2.5 font-mono text-sm text-text-primary break-all">
                      {agentCliCommand}
                    </code>
                    <button
                      type="button"
                      onClick={() => handleCopy(agentCliCommand)}
                      className="shrink-0 rounded-card border border-accent/30 px-3 py-2 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                    >
                      Copy
                    </button>
                  </div>
                </div>

                <div className="rounded-card border border-accent/20 bg-accent/5 p-4">
                  <p className="text-sm text-text-primary">
                    <span className="font-medium">Selected:</span>{" "}
                    {selectedProfile?.title} · {eligibleCards.length} eligible
                    evidence cards
                  </p>
                  <p className="mt-1 text-xs text-text-secondary">
                    Run the command above in your terminal. Results will appear
                    in the Overview and Resumes pages.
                  </p>
                </div>
              </div>
            </section>
          ) : null}

          {/* Agent Run Link */}
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.quickRun.agentRunLink")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.quickRun.agentRunLinkHint")}
                </p>
              </div>
              <a
                href="/agent-run"
                className="shrink-0 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                {t("nav.agentRun")} →
              </a>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
