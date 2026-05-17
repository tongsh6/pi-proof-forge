import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle, Copy, Play, Square } from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import {
  cancelQuickRun,
  listEvidence,
  listJobProfiles,
  getOverview,
  startQuickRun,
} from "@/lib/sidecar/api";
import type {
  EvidenceListItem,
  JobProfileListItem,
  OverviewMetrics,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type RunState = "idle" | "ready_to_run" | "running" | "done" | "error";

const PIPELINE_STEPS = [
  { key: "extract", labelKey: "pages.quickRun.steps.extract" },
  { key: "match", labelKey: "pages.quickRun.steps.match" },
  { key: "generate", labelKey: "pages.quickRun.steps.generate" },
  { key: "evaluate", labelKey: "pages.quickRun.steps.evaluate" },
] as const;

const QUICK_RUN_TERMINAL_STATUSES = new Set([
  "DONE",
  "FAILED",
  "SKIPPED",
  "TIMEOUT",
  "stopped",
]);

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

function recordVerifyEvent(
  event: string,
  details: Record<string, unknown> = {}
) {
  if (verifyScenario !== "quick-run") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
}

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
  const [quickRunId, setQuickRunId] = useState<string | null>(null);
  const [quickRunStatus, setQuickRunStatus] = useState<string | null>(null);
  const [quickRunRecord, setQuickRunRecord] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const quickRunInFlightRef = useRef(false);
  const verifyStartedRef = useRef(false);

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
      recordVerifyEvent("quick_run.load.ready", {
        evidence_count: evidence.items.length,
        job_profile_count: jobs.items.length,
        selected_profile_id:
          selectedProfileId || jobs.items[0]?.job_profile_id || null,
      });
      setLoadState("ready");
    } catch (e) {
      setLoadState("error");
      setError(getErrorMessage(e));
      recordVerifyEvent("quick_run.load.error", {
        error: getErrorMessage(e),
      });
    }
  }, [selectedProfileId]);

  useEffect(() => {
    void load();
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedProfile = jobProfiles.find(
    (jp) => jp.job_profile_id === selectedProfileId,
  );

  const eligibleCards = evidenceCards.filter((c) => c.status !== "draft");
  const canShowRunPanel = selectedProfileId !== "";
  const canStartRun = canShowRunPanel && runState !== "running";
  const canCancelRun =
    quickRunId !== null &&
    quickRunStatus !== null &&
    !QUICK_RUN_TERMINAL_STATUSES.has(quickRunStatus);

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

  const handleStartQuickRun = useCallback(async () => {
    if (!selectedProfileId || quickRunInFlightRef.current) return;
    quickRunInFlightRef.current = true;
    setRunState("running");
    setRunError(null);
    setQuickRunStatus(null);
    setQuickRunRecord(null);
    recordVerifyEvent("quick_run.start.request", {
      selected_profile_id: selectedProfileId,
    });
    try {
      const result = await startQuickRun({
        job_profile_id: selectedProfileId,
        options: { generate_resume: true },
      });
      setQuickRunId(result.run_id);
      setQuickRunStatus(result.status);
      setQuickRunRecord(result.run_record ?? null);
      setRunState(
        result.status === "DONE" || result.status === "SKIPPED" ? "done" : "error"
      );
      if (result.status !== "DONE" && result.status !== "SKIPPED") {
        setRunError(
          `${result.status}${result.exit_code != null ? ` (${result.exit_code})` : ""}`
        );
      }
      recordVerifyEvent("quick_run.start.result", {
        run_id: result.run_id,
        status: result.status,
        run_record: result.run_record ?? null,
      });
    } catch (e) {
      setRunState("error");
      setRunError(getErrorMessage(e));
      recordVerifyEvent("quick_run.start.error", {
        error: getErrorMessage(e),
      });
    } finally {
      quickRunInFlightRef.current = false;
    }
  }, [selectedProfileId]);

  const handleCancelQuickRun = async () => {
    if (!quickRunId) return;
    setRunError(null);
    try {
      await cancelQuickRun(quickRunId);
      setQuickRunStatus("stopped");
      setRunState("idle");
    } catch (e) {
      setRunError(getErrorMessage(e));
    }
  };

  useEffect(() => {
    if (
      verifyScenario !== "quick-run" ||
      verifyStartedRef.current ||
      loadState !== "ready" ||
      runState === "running"
    ) {
      return;
    }

    if (!selectedProfileId) {
      recordVerifyEvent("quick_run.autorun.blocked", {
        reason: "missing_profile",
        job_profile_count: jobProfiles.length,
      });
      return;
    }

    verifyStartedRef.current = true;
    window.setTimeout(() => {
      const button = document.querySelector<HTMLButtonElement>(
        '[data-automation-id="quick-run-start"]'
      );
      recordVerifyEvent("quick_run.autorun.click", {
        selected_profile_id: selectedProfileId,
        has_button: Boolean(button),
        button_disabled: button?.disabled ?? null,
      });
      button?.click();
      if (!quickRunInFlightRef.current) {
        recordVerifyEvent("quick_run.autorun.direct_fallback", {
          selected_profile_id: selectedProfileId,
        });
        void handleStartQuickRun();
      }
    }, 250);
  }, [handleStartQuickRun, jobProfiles.length, loadState, runState, selectedProfileId]);

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
                        setQuickRunId(null);
                        setQuickRunStatus(null);
                        setQuickRunRecord(null);
                        setRunError(null);
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

          {/* Quick Run */}
          {canShowRunPanel ? (
            <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.quickRun.runTitle")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {t("pages.quickRun.runSubtitle")}
              </p>

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  data-automation-id="quick-run-start"
                  onClick={() => void handleStartQuickRun()}
                  disabled={!canStartRun}
                  className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Play className="h-4 w-4" aria-hidden="true" />
                  {runState === "running"
                    ? t("pages.quickRun.running")
                    : t("pages.quickRun.startRun")}
                </button>
                {canCancelRun ? (
                  <button
                    type="button"
                    onClick={() => void handleCancelQuickRun()}
                    className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover"
                  >
                    <Square className="h-4 w-4" aria-hidden="true" />
                    {t("pages.quickRun.cancelRun")}
                  </button>
                ) : null}
              </div>

              {quickRunStatus ? (
                <div
                  className={`mt-4 flex items-start gap-3 rounded-card border p-4 ${
                    runState === "done"
                      ? "border-success/30 bg-success/5"
                      : "border-error/30 bg-error/5"
                  }`}
                >
                  {runState === "done" ? (
                    <CheckCircle className="mt-0.5 h-4 w-4 text-success" aria-hidden="true" />
                  ) : (
                    <AlertCircle className="mt-0.5 h-4 w-4 text-error" aria-hidden="true" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary">
                      {t("pages.quickRun.runStatus", {
                        status: quickRunStatus,
                        runId: quickRunId,
                      })}
                    </p>
                    {quickRunRecord ? (
                      <p className="mt-1 break-all text-xs text-text-secondary">
                        {quickRunRecord}
                      </p>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {runError ? (
                <p className="mt-3 text-sm text-error">{runError}</p>
              ) : null}

              <div className="mt-5 space-y-4">
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
                      className="inline-flex shrink-0 items-center gap-1 rounded-card border border-accent/30 px-3 py-2 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                    >
                      <Copy className="h-3.5 w-3.5" aria-hidden="true" />
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
                      className="inline-flex shrink-0 items-center gap-1 rounded-card border border-accent/30 px-3 py-2 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                    >
                      <Copy className="h-3.5 w-3.5" aria-hidden="true" />
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
                    {t("pages.quickRun.selectedHint")}
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
