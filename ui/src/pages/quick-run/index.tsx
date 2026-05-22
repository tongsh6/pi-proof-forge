import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  Circle,
  LoaderCircle,
  Play,
  RefreshCw,
  Square,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import {
  cancelQuickRun,
  getSettings,
  listEvidence,
  listEvidenceMaterialSources,
  listJobProfiles,
  startQuickRun,
} from "@/lib/sidecar/api";
import type {
  JobProfileListItem,
  LlmConfig,
  MaterialSourceItem,
  QuickRunStartResult,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type RunState = "idle" | "ready_to_run" | "running" | "done" | "error";
type StageStatus = "waiting" | "running" | "done" | "error";

const PIPELINE_STEPS = [
  { key: "extract", labelKey: "pages.quickRun.steps.extract" },
  { key: "match", labelKey: "pages.quickRun.steps.match" },
  { key: "generate", labelKey: "pages.quickRun.steps.generate" },
  { key: "evaluate", labelKey: "pages.quickRun.steps.evaluate" },
] as const;

const SCORE_KEYS = ["K", "D", "S", "Q", "E", "R"] as const;
const SCORE_MAX = 20;

const QUICK_RUN_TERMINAL_STATUSES = new Set([
  "DONE",
  "FAILED",
  "SKIPPED",
  "TIMEOUT",
  "stopped",
]);

const stageStatusClass: Record<StageStatus, string> = {
  waiting: "border-border bg-bg-primary/60 text-text-secondary",
  running: "border-accent bg-accent/10 text-text-primary",
  done: "border-success/50 bg-success/10 text-text-primary",
  error: "border-error/50 bg-error/10 text-text-primary",
};

const failedStepAliases: Record<(typeof PIPELINE_STEPS)[number]["key"], string[]> = {
  extract: ["extract", "extraction", "evidence"],
  match: ["match", "matching", "scoring"],
  generate: ["generate", "generation"],
  evaluate: ["evaluate", "evaluation"],
};

function getStageStatus(
  runState: RunState,
  status: string | null,
  failedStep: string,
  stepIndex: number
): StageStatus {
  if (runState === "running") {
    return stepIndex === 0 ? "running" : "waiting";
  }
  if (status === "DONE" || status === "SKIPPED") {
    return "done";
  }
  if (runState === "error") {
    const failedIndex = PIPELINE_STEPS.findIndex((step) =>
      failedStepAliases[step.key].some((alias) => failedStep.includes(alias))
    );
    if (failedIndex === -1) return stepIndex === 0 ? "error" : "waiting";
    if (stepIndex < failedIndex) return "done";
    return stepIndex === failedIndex ? "error" : "waiting";
  }
  return "waiting";
}

function formatTerminalLines(result: QuickRunStartResult | null, runError: string | null) {
  if (!result && !runError) return [];
  const lines: string[] = [];
  if (result) {
    lines.push(`[quick-run] run_id=${result.run_id} status=${result.status}`);
    if (result.reason) lines.push(`[quick-run] reason=${result.reason}`);
    if (result.run_record) lines.push(`[quick-run] run_record=${result.run_record}`);
    const stdout = result.stdout?.trim();
    const stderr = result.stderr?.trim();
    if (stdout) lines.push(...stdout.split(/\r?\n/));
    if (stderr) lines.push(...stderr.split(/\r?\n/).map((line) => `[stderr] ${line}`));
  }
  if (runError) lines.push(`[error] ${runError}`);
  return lines.slice(-80);
}

function formatConfigValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
}

export function QuickRunPage() {
  const { t } = useTranslation();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [runState, setRunState] = useState<RunState>("idle");
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [eligibleEvidenceIds, setEligibleEvidenceIds] = useState<string[]>([]);
  const [materialSources, setMaterialSources] = useState<MaterialSourceItem[]>([]);
  const [jobProfiles, setJobProfiles] = useState<JobProfileListItem[]>([]);
  const [llmConfig, setLlmConfig] = useState<LlmConfig | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [resumePositioning, setResumePositioning] = useState("technical_depth");
  const [quickRunId, setQuickRunId] = useState<string | null>(null);
  const [quickRunStatus, setQuickRunStatus] = useState<string | null>(null);
  const [quickRunResult, setQuickRunResult] = useState<QuickRunStartResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const quickRunInFlightRef = useRef(false);

  const load = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const [evidence, materials, jobs, settings] = await Promise.all([
        listEvidence(),
        listEvidenceMaterialSources(),
        listJobProfiles(),
        getSettings(),
      ]);
      const eligibleEvidence = evidence.items.filter(
        (item) => item.status === "saved_eligible"
      );
      const activeProfiles = jobs.items.filter((item) => item.status === "active");
      setEvidenceCount(eligibleEvidence.length);
      setEligibleEvidenceIds(eligibleEvidence.map((item) => item.evidence_id));
      setMaterialSources(materials.items);
      setJobProfiles(jobs.items);
      setLlmConfig(settings.llm_config);
      if (activeProfiles.length > 0 && !selectedProfileId) {
        setSelectedProfileId(activeProfiles[0].job_profile_id);
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

  useEffect(() => {
    if (runState !== "running" || startedAt === null) return undefined;
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    }, 500);
    return () => window.clearInterval(timer);
  }, [runState, startedAt]);

  const selectedProfile = jobProfiles.find(
    (jp) => jp.job_profile_id === selectedProfileId,
  );
  const activeJobProfiles = jobProfiles.filter((jp) => jp.status === "active");
  const providerSummary = [
    {
      label: t("pages.quickRun.provider"),
      value: formatConfigValue(llmConfig?.provider),
    },
    {
      label: t("pages.quickRun.model"),
      value: formatConfigValue(llmConfig?.model),
    },
    {
      label: t("pages.quickRun.baseUrl"),
      value: formatConfigValue(llmConfig?.base_url),
    },
    {
      label: t("pages.quickRun.secretStatus"),
      value: llmConfig?.api_key.configured
        ? t("pages.systemSettings.secretConfigured")
        : t("pages.systemSettings.secretMissing"),
    },
  ];
  const canStartRun =
    selectedProfileId !== "" && eligibleEvidenceIds.length > 0 && runState !== "running";
  const canCancelRun =
    quickRunId !== null &&
    quickRunStatus !== null &&
    !QUICK_RUN_TERMINAL_STATUSES.has(quickRunStatus);

  const scoreBars = useMemo(
    () =>
      SCORE_KEYS.map((key) => {
        const score = quickRunResult?.score_breakdown?.[key]?.score ?? 0;
        return {
          key,
          score,
          reason: quickRunResult?.score_breakdown?.[key]?.reason ?? "",
          width: `${Math.min(100, Math.max(0, (score / SCORE_MAX) * 100))}%`,
        };
      }),
    [quickRunResult]
  );

  const terminalLines = useMemo(
    () => formatTerminalLines(quickRunResult, runError),
    [quickRunResult, runError]
  );

  const handleStartQuickRun = useCallback(async () => {
    if (!selectedProfileId || quickRunInFlightRef.current) return;
    quickRunInFlightRef.current = true;
    const now = Date.now();
    setStartedAt(now);
    setElapsedSeconds(0);
    setRunState("running");
    setRunError(null);
    setQuickRunStatus(null);
    setQuickRunResult(null);
    try {
      const result = await startQuickRun({
        job_profile_id: selectedProfileId,
        options: {
          generate_resume: true,
          evidence_ids: eligibleEvidenceIds,
          resume_positioning: resumePositioning,
          use_llm: true,
          require_llm: true,
        },
      });
      setQuickRunId(result.run_id);
      setQuickRunStatus(result.status);
      setQuickRunResult(result);
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - now) / 1000)));
      setRunState(
        result.status === "DONE" || result.status === "SKIPPED" ? "done" : "error"
      );
      if (result.status !== "DONE" && result.status !== "SKIPPED") {
        setRunError(
          `${result.status}${result.exit_code != null ? ` (${result.exit_code})` : ""}`
        );
      }
    } catch (e) {
      setRunState("error");
      setRunError(getErrorMessage(e));
    } finally {
      quickRunInFlightRef.current = false;
    }
  }, [eligibleEvidenceIds, resumePositioning, selectedProfileId]);

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

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.quickRun.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.quickRun.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedProfileId}
            onChange={(event) => {
              setSelectedProfileId(event.target.value);
              setRunState("ready_to_run");
              setQuickRunId(null);
              setQuickRunStatus(null);
              setQuickRunResult(null);
              setRunError(null);
            }}
            className="h-10 min-w-[280px] rounded-card border border-border bg-bg-panel px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
            aria-label={t("pages.quickRun.selectProfile")}
          >
            {activeJobProfiles.length === 0 ? (
              <option value="">{t("common.empty")}</option>
            ) : null}
            {activeJobProfiles.map((profile) => (
              <option key={profile.job_profile_id} value={profile.job_profile_id}>
                {profile.title}
              </option>
            ))}
          </select>
          <select
            value={resumePositioning}
            onChange={(event) => setResumePositioning(event.target.value)}
            className="h-10 min-w-[220px] rounded-card border border-border bg-bg-panel px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
            aria-label={t("pages.quickRun.resumePositioning")}
          >
            <option value="technical_depth">
              {t("pages.quickRun.positioningOptions.technicalDepth")}
            </option>
            <option value="delivery_owner">
              {t("pages.quickRun.positioningOptions.deliveryOwner")}
            </option>
          </select>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex h-10 w-10 items-center justify-center rounded-card border border-border text-text-primary transition-colors hover:bg-bg-hover"
            aria-label={t("common.retry")}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-automation-id="quick-run-start"
            onClick={() => void handleStartQuickRun()}
            disabled={!canStartRun}
            className="inline-flex h-10 items-center gap-2 rounded-card border border-accent bg-accent px-4 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
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
              className="inline-flex h-10 items-center gap-2 rounded-card border border-border px-4 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover"
            >
              <Square className="h-4 w-4" aria-hidden="true" />
              {t("pages.quickRun.cancelRun")}
            </button>
          ) : null}
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

      {loadState === "ready" ? (
        <>
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.quickRun.providerSummary")}
            </h2>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {providerSummary.map((item) => (
                <div
                  className="rounded-card border border-border bg-bg-primary/50 p-4"
                  key={item.label}
                >
                  <p className="text-xs uppercase text-text-muted">{item.label}</p>
                  <p className="mt-2 truncate text-sm font-medium text-text-primary">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.quickRun.inputSummary")}
            </h2>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-card border border-border bg-bg-primary/50 p-4">
                <p className="text-xs uppercase text-text-muted">
                  {t("pages.quickRun.materialSource")}
                </p>
                <p className="mt-2 truncate text-sm font-medium text-text-primary">
                  {materialSources[0]?.label || materialSources[0]?.material_id || "--"}
                </p>
              </div>
              <div className="rounded-card border border-border bg-bg-primary/50 p-4">
                <p className="text-xs uppercase text-text-muted">
                  {t("pages.quickRun.selectedProfile")}
                </p>
                <p className="mt-2 truncate text-sm font-medium text-text-primary">
                  {selectedProfile?.title ?? "--"}
                </p>
              </div>
              <div className="rounded-card border border-border bg-bg-primary/50 p-4">
                <p className="text-xs uppercase text-text-muted">
                  {t("pages.quickRun.traceableEvidence")}
                </p>
                <p className="mt-2 truncate text-sm font-medium text-text-primary">
                  {quickRunResult?.traceability?.evidence_card_ids.length
                    ? quickRunResult.traceability.evidence_card_ids.join(", ")
                    : `${evidenceCount} ${t("pages.quickRun.evidenceCards")}`}
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="grid gap-3 xl:grid-cols-4">
              {PIPELINE_STEPS.map((step, index) => {
                const stageStatus = getStageStatus(
                  runState,
                  quickRunStatus,
                  quickRunResult?.failed_step ?? "",
                  index
                );
                return (
                  <div key={step.key} className="flex items-center gap-3">
                    <div
                      className={`min-h-[96px] flex-1 rounded-card border p-4 transition-colors ${stageStatusClass[stageStatus]}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-medium uppercase text-text-muted">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        {stageStatus === "done" ? (
                          <CheckCircle className="h-5 w-5 text-success" aria-hidden="true" />
                        ) : null}
                        {stageStatus === "running" ? (
                          <LoaderCircle className="h-5 w-5 animate-spin text-accent" aria-hidden="true" />
                        ) : null}
                        {stageStatus === "error" ? (
                          <AlertCircle className="h-5 w-5 text-error" aria-hidden="true" />
                        ) : null}
                        {stageStatus === "waiting" ? (
                          <Circle className="h-5 w-5 text-text-muted" aria-hidden="true" />
                        ) : null}
                      </div>
                      <p className="mt-3 text-sm font-semibold text-text-primary">
                        {t(step.labelKey)}
                      </p>
                      <p className="mt-2 text-xs text-text-secondary">
                        {stageStatus === "running"
                          ? t("pages.quickRun.elapsed", { seconds: elapsedSeconds })
                          : stageStatus === "done"
                            ? t("pages.quickRun.result")
                            : t("pages.quickRun.waiting")}
                      </p>
                    </div>
                    {index < PIPELINE_STEPS.length - 1 ? (
                      <ChevronRight className="hidden h-5 w-5 shrink-0 text-text-muted xl:block" aria-hidden="true" />
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.quickRun.stageOutput")}
                  </h2>
                  <p className="mt-1 text-xs text-text-secondary">
                    {quickRunStatus
                      ? t("pages.quickRun.runStatus", {
                          status: quickRunStatus,
                          runId: quickRunId,
                        })
                      : `${selectedProfile?.title ?? ""} · ${evidenceCount} ${t(
                          "pages.quickRun.evidenceCards"
                        )}`}
                  </p>
                </div>
              </div>
              <div className="mt-4 h-[360px] overflow-auto rounded-card border border-border bg-[#050A16] p-4 font-mono text-xs leading-6 text-text-secondary">
                {terminalLines.length > 0 ? (
                  terminalLines.map((line, index) => (
                    <p key={`${index}-${line}`} className="whitespace-pre-wrap break-words">
                      <span className="text-text-muted">
                        {String(index + 1).padStart(3, "0")}
                      </span>{" "}
                      {line}
                    </p>
                  ))
                ) : (
                  <p className="text-text-muted">{t("pages.quickRun.noLogs")}</p>
                )}
              </div>
            </article>

            <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.quickRun.scores")}
              </h2>
              <div className="mt-4 rounded-card border border-border bg-bg-primary/60 p-4">
                <p className="text-xs uppercase text-text-muted">
                  {t("pages.quickRun.scoreLabels.total")}
                </p>
                <p className="mt-2 text-3xl font-semibold text-text-primary">
                  {quickRunResult?.score_total ?? "--"}
                </p>
              </div>
              <div className="mt-5 space-y-4">
                {scoreBars.map((item) => (
                  <div key={item.key}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-text-primary">{item.key}</span>
                      <span className="text-text-secondary">{item.score}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-chip bg-bg-primary">
                      <div
                        className="h-full rounded-chip bg-accent"
                        style={{ width: item.width }}
                      />
                    </div>
                    {item.reason ? (
                      <p className="mt-1 line-clamp-2 text-xs text-text-muted">
                        {item.reason}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
              {quickRunResult?.score_total == null ? (
                <p className="mt-5 text-xs text-text-secondary">
                  {t("pages.quickRun.scoreLabels.empty")}
                </p>
              ) : null}
            </aside>
          </section>
        </>
      ) : null}
    </div>
  );
}
