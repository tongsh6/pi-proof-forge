import { DailyDeliveryPanel } from "./daily-delivery";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  Square,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getErrorMessage } from "@/lib/errors";
import { isLlmSecretConfigured } from "@/lib/llmConfig";
import { confirmAction, notify } from "@/lib/ui";
import {
  getAgentRun,
  getPendingReview,
  getSettings,
  recheckReceipt,
  listJobProfiles,
  startAgentRun,
  stopAgentRun,
  submitReview,
} from "@/lib/sidecar/api";
import type {
  AgentRunSummary,
  AgentRunGetResult,
  JobProfileListItem,
  LlmConfig,
  ReviewCandidateItem,
  ReviewDeliveryResult,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SubmitState = "idle" | "submitting" | "done" | "error";
type AgentRunEvent = Record<string, unknown> & {
  event_type?: unknown;
  round_index?: unknown;
  payload?: unknown;
  timestamp?: unknown;
};
type GateRowStatus = "pass" | "fail" | "running" | "waiting";

const STATE_SEQUENCE = [
  "INIT",
  "DISCOVER",
  "SCORE",
  "GENERATE",
  "EVALUATE",
  "GATE",
  "REVIEW",
  "DELIVER",
  "LEARN",
  "DONE",
] as const;

type AgentState = (typeof STATE_SEQUENCE)[number];

const FINAL_STATUSES = new Set([
  "DONE",
  "DRY_RUN_COMPLETE",
  "REVIEWED_CHECK_ONLY",
  "DELIVERY_BLOCKED",
  "EXTERNAL_CONFIRMATION_ONLY",
  "REVIEW_SNAPSHOT_BLOCKED",
  "REVIEW_PENDING",
  "FAILED",
  "stopped",
]);

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isAgentState(value: string): value is AgentState {
  return STATE_SEQUENCE.includes(value as AgentState);
}

function eventState(event: AgentRunEvent): AgentState | null {
  const candidate = asString(event.event_type).toUpperCase();
  return isAgentState(candidate) ? candidate : null;
}

function formatDate(value: string | undefined, locale: string): string {
  if (!value) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale);
}

function formatConfigValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
}

function payloadOf(event: AgentRunEvent | undefined): Record<string, unknown> {
  return event && typeof event.payload === "object" && event.payload !== null
    ? (event.payload as Record<string, unknown>)
    : {};
}

function eventSummary(event: AgentRunEvent): string {
  const payload = payloadOf(event);
  const entries = Object.entries(payload).filter(([, value]) => value !== "");
  if (entries.length === 0) return "";
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join("  ");
}

function agentStateLabel(state: AgentState, t: (key: string) => string): string {
  return t(`pages.agentRun.states.${state}`);
}

function runStatusLabel(status: string | undefined, t: (key: string) => string): string {
  if (!status) return t("pages.agentRun.runStatuses.idle");
  const normalized = status.toLowerCase();
  if (normalized === "dry_run_complete") {
    return t("pages.agentRun.runStatuses.dryRunComplete");
  }
  if (normalized === "review_pending") {
    return t("pages.agentRun.runStatuses.reviewPending");
  }
  if (normalized === "delivery_blocked") return t("pages.agentRun.runStatuses.deliveryBlocked");
  if (normalized === "external_confirmation_only") return t("pages.agentRun.runStatuses.externalConfirmationOnly");
  if (normalized === "reviewed_check_only") return t("pages.agentRun.runStatuses.reviewedCheckOnly");
  if (normalized === "review_snapshot_blocked") return t("pages.agentRun.runStatuses.snapshotBlocked");
  if (normalized === "done") return t("pages.agentRun.runStatuses.done");
  if (normalized === "failed") return t("pages.agentRun.runStatuses.failed");
  if (normalized === "stopped") return t("pages.agentRun.runStatuses.stopped");
  if (normalized === "running") return t("pages.agentRun.runStatuses.running");
  if (normalized === "idle") return t("pages.agentRun.runStatuses.idle");
  return status;
}

function latestStateIndex(events: AgentRunEvent[], status: string): number {
  if (status === "stopped") return STATE_SEQUENCE.indexOf("DONE");
  const eventIndexes = events
    .map(eventState)
    .filter((state): state is AgentState => state !== null)
    .map((state) => STATE_SEQUENCE.indexOf(state));
  return eventIndexes.length > 0 ? Math.max(...eventIndexes) : 0;
}

function stateClassName(isDone: boolean, isActive: boolean): string {
  if (isDone) {
    return "border-success/40 bg-success/10 text-success";
  }
  if (isActive) {
    return "border-accent/50 bg-accent/10 text-accent";
  }
  return "border-border bg-bg-primary/60 text-text-muted";
}

function gateStatusClassName(status: GateRowStatus): string {
  if (status === "pass") return "border-success/40 bg-success/10 text-success";
  if (status === "fail") return "border-error/40 bg-error/10 text-error";
  if (status === "running") return "border-accent/40 bg-accent/10 text-accent";
  return "border-border bg-bg-primary/60 text-text-secondary";
}

export function AgentRunPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedRunId = searchParams.get("run_id");
  const [jobProfiles, setJobProfiles] = useState<JobProfileListItem[]>([]);
  // 页内两个标签：每日受控投递（主线）/ 自主运行（本地演练）；带 run_id 深链时进入自主运行。
  const [activeTab, setActiveTab] = useState<"daily" | "agent">(requestedRunId ? "agent" : "daily");
  const [llmConfig, setLlmConfig] = useState<LlmConfig | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRunSummary | null>(null);
  const [deliveryBatch, setDeliveryBatch] = useState<AgentRunGetResult["delivery_batch"]>(null);
  const [events, setEvents] = useState<AgentRunEvent[]>([]);
  const [candidates, setCandidates] = useState<ReviewCandidateItem[]>([]);
  const [nativePdfQuickRunId, setNativePdfQuickRunId] = useState<string | null>(null);
  const [deliveryResults, setDeliveryResults] = useState<ReviewDeliveryResult[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [runState, setRunState] = useState<LoadState>("ready");
  const [error, setError] = useState<string | null>(null);
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const agentRunInFlightRef = useRef(false);

  const loadProfiles = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const [result, settings] = await Promise.all([
        listJobProfiles(),
        getSettings(),
      ]);
      setJobProfiles(result.items);
      setLlmConfig(settings.llm_config);
      if (!selectedProfileId && result.items.length > 0) {
        setSelectedProfileId(result.items[0].job_profile_id);
      }
      setLoadState("ready");
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setLoadState("error");
    }
  }, [selectedProfileId]);

  const loadPending = useCallback(
    async (runId: string | null = currentRunId) => {
      try {
        const result = await getPendingReview(runId ?? undefined);
        setNativePdfQuickRunId(result.native_pdf_quick_run_id ?? null);
        setCandidates(result.candidates ?? []);
        setDeliveryResults(result.delivery_results ?? []);
      } catch {
        setCandidates([]);
        setNativePdfQuickRunId(null);
      }
    },
    [currentRunId]
  );

  const loadRun = useCallback(
    async (runId: string) => {
      setRunState("loading");
      setError(null);
      try {
        const result = await getAgentRun(runId);
        setRun(result.run);
        setDeliveryBatch(result.delivery_batch);
        if (result.run.job_profile_id) setSelectedProfileId(result.run.job_profile_id);
        setEvents(result.events as AgentRunEvent[]);
        setRunState("ready");
        await loadPending(runId);
      } catch (nextError) {
        setRunState("error");
        setError(getErrorMessage(nextError));
      }
    },
    [loadPending]
  );

  useEffect(() => {
    void loadProfiles();
  }, [loadProfiles]);

  useEffect(() => {
    if (requestedRunId) {
      if (currentRunId !== requestedRunId) {
        setCurrentRunId(requestedRunId);
        setRun(null);
        setCandidates([]);
        setDeliveryResults([]);
        void loadRun(requestedRunId);
      }
      return;
    }
    if (currentRunId) return;
    let active = true;
    void getPendingReview().then((result) => {
      if (!active || (!result.candidates?.length && !result.delivery_results?.length)) return;
      setCurrentRunId(result.run_id);
      void loadRun(result.run_id);
    }).catch(() => {});
    return () => { active = false; };
  }, [currentRunId, requestedRunId, loadRun]);

  const selectedProfile = jobProfiles.find(
    (profile) => profile.job_profile_id === selectedProfileId
  );
  const providerSummary = [
    {
      label: t("pages.agentRun.provider"),
      value: formatConfigValue(llmConfig?.provider),
    },
    {
      label: t("pages.agentRun.model"),
      value: formatConfigValue(llmConfig?.model),
    },
    {
      label: t("pages.agentRun.baseUrl"),
      value: formatConfigValue(llmConfig?.base_url),
    },
    {
      label: t("pages.agentRun.secretStatus"),
      value: llmConfig?.api_key.configured
        ? t("pages.systemSettings.secretConfigured")
        : isLlmSecretConfigured(llmConfig)
          ? t("pages.systemSettings.llm.keyLocalOptional")
          : t("pages.systemSettings.secretMissing"),
    },
  ];
  const activeIndex = latestStateIndex(events, run?.status ?? "");
  const activeState = STATE_SEQUENCE[activeIndex];
  const isRunBusy =
    runState === "loading" ||
    Boolean(run && !FINAL_STATUSES.has(run.status));

  const eventByState = useMemo(() => {
    const map = new Map<AgentState, AgentRunEvent>();
    events.forEach((event) => {
      const state = eventState(event);
      if (state) map.set(state, event);
    });
    return map;
  }, [events]);

  const gateRows = useMemo(() => {
    const scorePayload = payloadOf(eventByState.get("SCORE"));
    const evaluatePayload = payloadOf(eventByState.get("EVALUATE"));
    const gatePayload = payloadOf(eventByState.get("GATE"));
    const matchingTotal = asNumber(scorePayload.matching_total);
    const evaluationTotal = asNumber(evaluatePayload.evaluation_total);
    const gateResult = asString(gatePayload.result);
    const gateResultLabel =
      gateResult === "pass" || gateResult === "fail"
        ? t(`pages.agentRun.gateStatus.${gateResult}`)
        : gateResult;
    const hasGate = eventByState.has("GATE");

    return [
      {
        key: "matching",
        status: matchingTotal === null ? "waiting" : "pass",
        detail:
          matchingTotal === null
            ? t("pages.agentRun.gates.notRecorded")
            : `${t("pages.agentRun.gates.score")} ${matchingTotal}`,
      },
      {
        key: "evaluation",
        status: evaluationTotal === null ? "waiting" : "pass",
        detail:
          evaluationTotal === null
            ? t("pages.agentRun.gates.notRecorded")
            : `${t("pages.agentRun.gates.score")} ${evaluationTotal}`,
      },
      {
        key: "channel",
        status: hasGate && gateResult !== "fail" ? "pass" : "waiting",
        detail: hasGate
          ? t("pages.agentRun.gates.observed")
          : t("pages.agentRun.gates.notRecorded"),
      },
      {
        key: "exclusion",
        status: gateResult === "fail" ? "fail" : hasGate ? "pass" : "waiting",
        detail: gateResult
          ? `${t("pages.agentRun.gates.result")} ${gateResultLabel}`
          : t("pages.agentRun.gates.notRecorded"),
      },
    ] satisfies Array<{
      key: "matching" | "evaluation" | "channel" | "exclusion";
      status: GateRowStatus;
      detail: string;
    }>;
  }, [eventByState, t]);

  const handleStart = useCallback(async () => {
    if (!selectedProfileId || agentRunInFlightRef.current) return;
    agentRunInFlightRef.current = true;
    setRunState("loading");
    setError(null);
    setSubmitError(null);
    try {
      const result = await startAgentRun({
        job_profile_id: selectedProfileId,
        options: {
          execute_guided_batch: true,
          preflight_confirmed: true,
          confirmed_no_real_submit: true,
          max_rounds: 2,
          max_candidates: 2,
          max_passed_candidates: 2,
          max_generated_resumes: 2,
          submit_enabled: false,
        },
      });
      setCurrentRunId(result.run_id);
      setSearchParams({ run_id: result.run_id }, { replace: true });
      await loadRun(result.run_id);
      notify("success", t("toasts.agentRun.started"));
    } catch (nextError) {
      setRunState("error");
      setError(getErrorMessage(nextError));
    } finally {
      agentRunInFlightRef.current = false;
    }
  }, [loadRun, selectedProfileId, setSearchParams]);

  const handleRefreshRun = useCallback(async () => {
    if (currentRunId) {
      await loadRun(currentRunId);
    } else {
      await loadProfiles();
    }
  }, [currentRunId, loadProfiles, loadRun]);

  const handleStop = useCallback(async () => {
    if (!currentRunId) return;
    const confirmed = await confirmAction({
      title: t("confirmations.agentRun.stop.title"),
      description: t("confirmations.agentRun.stop.description"),
      confirmLabel: t("confirmations.agentRun.stop.confirm"),
      tone: "danger",
    });
    if (!confirmed) return;
    setRunState("loading");
    setError(null);
    try {
      await stopAgentRun(currentRunId);
      await loadRun(currentRunId);
      notify("success", t("toasts.agentRun.stopped"));
    } catch (nextError) {
      setRunState("error");
      setError(getErrorMessage(nextError));
    }
  }, [currentRunId, loadRun]);

  const handleDecision = useCallback(
    async (jobLeadId: string, action: "approve" | "reject" | "skip") => {
      if (nativePdfQuickRunId) return;
      // 批准可能触发投递，拒绝不可撤销；跳过不需要确认。
      if (action !== "skip") {
        const confirmed = await confirmAction({
          title: t(`confirmations.agentRun.${action}.title`),
          description: t(`confirmations.agentRun.${action}.description`),
          confirmLabel: t(`confirmations.agentRun.${action}.confirm`),
          tone: action === "reject" ? "danger" : "default",
        });
        if (!confirmed) return;
      }
      setSubmitState("submitting");
      setSubmitError(null);
      try {
        const result = await submitReview(
          [
            {
              job_lead_id: jobLeadId,
              action,
              decided_by: "user",
              decided_at: new Date().toISOString(),
            },
          ],
          currentRunId ?? undefined
        );
        setDeliveryResults(result.delivery_results ?? []);
        setSubmitState("done");
        if (currentRunId) await loadRun(currentRunId);
        else await loadPending();
        notify("success", t("toasts.agentRun.decisionSubmitted"));
      } catch (nextError) {
        setSubmitState("error");
        setSubmitError(getErrorMessage(nextError));
      }
    },
    [currentRunId, loadPending, loadRun, nativePdfQuickRunId]
  );

  const handleRecheckReceipt = useCallback(async (leadId: string) => {
    if (!currentRunId) return;
    setSubmitState("submitting");
    setSubmitError(null);
    try {
      const result = await recheckReceipt(currentRunId, leadId);
      if (result.status !== "ready") {
        setSubmitState("error");
        setSubmitError(t("pages.agentRun.receiptUnavailable"));
        return;
      }
      setSubmitState("done");
      await loadRun(currentRunId);
    } catch {
      setSubmitState("error");
      setSubmitError(t("pages.agentRun.receiptUnavailable"));
    }
  }, [currentRunId, loadRun, t]);

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void handleRefreshRun();
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [handleRefreshRun]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.agentRun.title")}</h1>
          <p className="page-subtitle">{t("pages.agentRun.subtitle")}</p>
        </div>
        <div className="page-actions">
          <div className="seg-tabs" role="tablist" data-testid="agent-run-tabs">
            {(["daily", "agent"] as const).map((tab) => (
              <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)}>
                {t(`pages.agentRun.tabs.${tab}`)}
              </button>
            ))}
          </div>
          <button
            className="page-icon-button"
            disabled={runState === "loading" || loadState === "loading"}
            onClick={() => void handleRefreshRun()}
            type="button"
            title={t("common.refreshShortcut")}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">{t("pages.agentRun.refresh")}</span>
          </button>
        </div>
      </header>

      {loadState === "loading" ? (
        <p className="text-sm text-text-secondary">{t("common.loading")}</p>
      ) : null}
      {error ? <p role="alert" className="text-sm text-error">{error}</p> : null}

      <div className={activeTab === "daily" ? "" : "hidden"} data-testid="agent-run-tab-daily">
        <DailyDeliveryPanel />
      </div>

      <div className={activeTab === "agent" ? "space-y-6" : "hidden"} data-testid="agent-run-tab-agent">
      <div className="flex flex-wrap items-center gap-2">
            <select
              className="h-10 min-w-[220px] rounded-card border border-border bg-bg-panel px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
              value={selectedProfileId}
              onChange={(event) => setSelectedProfileId(event.target.value)}
              disabled={loadState === "loading" || isRunBusy}
              aria-label={t("pages.agentRun.jobProfile")}
            >
              {jobProfiles.map((profile) => (
                <option key={profile.job_profile_id} value={profile.job_profile_id}>
                  {profile.title || profile.job_profile_id}
                </option>
              ))}
            </select>
            <button
              className="inline-flex h-10 items-center gap-2 rounded-card border border-accent/50 bg-accent/10 px-4 text-sm font-medium text-accent hover:bg-accent/20 disabled:opacity-50"
              data-automation-id="agent-run-start"
              disabled={!selectedProfileId || isRunBusy}
              onClick={() => void handleStart()}
              type="button"
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              {t("pages.agentRun.startDryRun")}
            </button>
            <button
              className="inline-flex h-10 items-center gap-2 rounded-card border border-error/50 px-3 text-sm text-error hover:bg-error/10 disabled:opacity-50"
              disabled={!currentRunId || !run || FINAL_STATUSES.has(run.status)}
              onClick={() => void handleStop()}
              type="button"
            >
              <Square className="h-4 w-4" aria-hidden="true" />
              {t("pages.agentRun.stop")}
            </button>
      </div>

      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
        <span className="text-text-muted">{t("pages.agentRun.providerSummary")}</span>
        {providerSummary.map((item) => (
          <span key={item.label}>
            <span className="text-text-muted">{item.label}</span> {item.value}
          </span>
        ))}
      </p>

      {run || runState === "loading" || currentRunId ? (
      <>
      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <p className="text-xs uppercase tracking-[0.08em] text-text-muted">
              {t("pages.agentRun.runId")}
            </p>
            <p className="mt-2 truncate font-mono text-sm text-text-primary">
              {run?.run_id ?? t("pages.agentRun.noRun")}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.08em] text-text-muted">
              {t("pages.agentRun.jobProfile")}
            </p>
            <p className="mt-2 truncate text-sm text-text-primary">
              {selectedProfile?.title ?? (selectedProfileId || "--")}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.08em] text-text-muted">
              {t("pages.agentRun.startedAt")}
            </p>
            <p className="mt-2 text-sm text-text-primary">
              {formatDate(run?.started_at, i18n.language)}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.08em] text-text-muted">
              {t("pages.agentRun.currentRound")}
            </p>
            <p className="mt-2 text-sm text-text-primary">
              {run && typeof run.round === "number" ? `${run.round} / ${run.options.max_rounds ?? 1}` : "--"}
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-text-primary">
            {t("pages.agentRun.statusMachine")}
          </h2>
          <span className="rounded-chip border border-border bg-bg-primary px-3 py-1 text-xs font-medium text-text-secondary">
            {runStatusLabel(run?.status, t)}
          </span>
        </div>
        {deliveryBatch ? <p className="mb-4 rounded-card border border-border p-3 text-sm text-text-secondary">
          {t("pages.agentRun.batchAuthorized")}: {deliveryBatch.authorized_max}
          {" · "}{t("pages.agentRun.batchConsumed")}: {deliveryBatch.consumed}
          {" · "}{t("pages.agentRun.batchConfirmed")}: {deliveryBatch.confirmed}
          {" · "}{t("pages.agentRun.batchRemaining")}: {deliveryBatch.remaining}
        </p> : null}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5 xl:grid-cols-10">
          {STATE_SEQUENCE.map((state) => {
            const wasObserved = eventByState.has(state);
            const isActive =
              state === activeState && !FINAL_STATUSES.has(run?.status ?? "");
            const isDone = wasObserved && !isActive;
            const Icon = isDone ? CheckCircle2 : isActive ? Loader2 : Circle;
            return (
              <div
                className={`min-h-[76px] rounded-card border p-3 ${stateClassName(isDone, isActive)}`}
                key={state}
              >
                <Icon
                  className={`h-4 w-4 ${isActive ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                <p className="mt-3 truncate text-xs font-semibold">
                  {agentStateLabel(state, t)}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_420px]">
        <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-accent" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.agentRun.gateTitle")}
            </h2>
          </div>
          <div className="space-y-3">
            {gateRows.map((row) => (
              <div
                className="flex items-center justify-between gap-4 rounded-card border border-border bg-bg-primary/40 p-4"
                key={row.key}
              >
                <div>
                  <p className="font-medium text-text-primary">
                    {t(`pages.agentRun.gates.${row.key}`)}
                  </p>
                  <p className="mt-1 text-sm text-text-secondary">{row.detail}</p>
                </div>
                <span
                  className={`rounded-chip border px-3 py-1 text-xs font-medium ${gateStatusClassName(
                    row.status
                  )}`}
                >
                  {t(`pages.agentRun.gateStatus.${row.status}`)}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-6 border-t border-border pt-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-text-primary">
                  {t("pages.agentRun.pendingReview")}
                </h3>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.agentRun.pendingReviewSubtitle")}
                </p>
              </div>
              <span className="rounded-chip border border-border bg-bg-primary px-3 py-1 text-xs text-text-secondary">
                {candidates.length}
              </span>
            </div>
            {candidates.length === 0 ? (
              <div className="rounded-card border border-border bg-bg-primary/40 p-4">
                <p className="text-sm font-medium text-text-primary">
                  {t("pages.agentRun.emptyReview")}
                </p>
                <p className="mt-2 text-sm text-text-secondary">
                  {t("pages.agentRun.emptyReviewHint")}
                </p>
              </div>
            ) : (
              <ul className="space-y-3">
                {candidates.map((candidate) => (
                  <li
                    className="rounded-card border border-border bg-bg-primary/40 p-4"
                    key={candidate.job_lead_id}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-text-primary">
                          {candidate.company} / {candidate.position}
                        </p>
                        <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-text-muted">
                          <span>
                            {t("pages.agentRun.matchScore")}:{" "}
                            {candidate.matching_score ?? t("pages.agentRun.notEvaluated")}
                          </span>
                          <span>
                            {t("pages.agentRun.evalScore")}:{" "}
                            {candidate.evaluation_score ?? t("pages.agentRun.notEvaluated")}
                          </span>
                          <span>
                            {t("pages.agentRun.round")}: {candidate.round_index}
                          </span>
                          <span>{t("pages.agentRun.resumeVersion")}: {candidate.resume_version}</span>
                          <span>{t(candidate.delivery_kind === "platform_default" ? "pages.agentRun.platformDefaultResume" : "pages.agentRun.generatedPdfResume")}</span>
                        </p>
                        {candidate.snapshot_status === "ready" ? (
                          <details className="mt-3">
                            <summary className="cursor-pointer text-sm text-accent">{t("pages.agentRun.snapshotPreview")}</summary>
                            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-text-secondary">{candidate.resume_preview}</pre>
                          </details>
                        ) : <p className="mt-2 text-xs text-error">{t("pages.agentRun.snapshotInvalid")}</p>}
                      </div>
                      <div className="flex shrink-0 gap-2">
                        {nativePdfQuickRunId ? <button type="button" className="rounded-card border border-accent px-3 py-1.5 text-xs text-accent"
                          onClick={() => navigate(`/submissions?quick_run_id=${encodeURIComponent(nativePdfQuickRunId)}`)}>{t("pages.agentRun.reviewNativePdf")}</button> : <>
                        <button
                          className="rounded-card border border-success/50 bg-success/10 px-3 py-1.5 text-xs font-medium text-success hover:bg-success/20 disabled:opacity-60"
                          disabled={submitState === "submitting" || candidate.snapshot_status !== "ready"}
                          onClick={() =>
                            void handleDecision(candidate.job_lead_id, "approve")
                          }
                          type="button"
                        >
                          {t(candidate.status === "approved" ? "pages.agentRun.continueApproved" : "pages.agentRun.approve")}
                        </button>
                        <button
                          className="rounded-card border border-error/50 px-3 py-1.5 text-xs font-medium text-error hover:bg-error/10 disabled:opacity-60"
                          disabled={submitState === "submitting" || candidate.status === "approved"}
                          onClick={() =>
                            void handleDecision(candidate.job_lead_id, "reject")
                          }
                          type="button"
                        >
                          {t("pages.agentRun.reject")}
                        </button>
                        <button
                          className="rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-bg-hover disabled:opacity-60"
                          disabled={submitState === "submitting" || candidate.status === "approved"}
                          onClick={() =>
                            void handleDecision(candidate.job_lead_id, "skip")
                          }
                          type="button"
                        >
                          {t("pages.agentRun.skip")}
                        </button>
                        </>}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {submitState === "error" && submitError ? (
              <p className="mt-4 text-sm text-error">{submitError}</p>
            ) : null}
            {deliveryResults.length > 0 ? (
              <div className="mt-4 space-y-2" role="status">
                <h4 className="text-sm font-medium">{t("pages.agentRun.reviewResults")}</h4>
                <p className="text-sm text-text-secondary">
                  {t("pages.agentRun.appVerifiedCount")}: {run?.app_verified_deliveries ?? 0}
                  {" · "}{t("pages.agentRun.externalConfirmedCount")}: {run?.externally_confirmed_deliveries ?? 0}
                </p>
                {deliveryResults.map((result) => (
                  <div key={result.job_lead_id} className="space-y-2 text-sm text-text-secondary">
                    {result.job_lead_id}: {t(`pages.agentRun.deliveryCodes.${result.code}`, {defaultValue: t("pages.agentRun.deliveryCodes.other")})}
                    {(result.status === "unknown" || result.receipt_source === "website_history") && result.submission_id ? (
                      <div>
                        <button type="button" className="rounded-card border border-accent px-3 py-1 text-accent disabled:opacity-50"
                          disabled={submitState === "submitting"} onClick={() => void handleRecheckReceipt(result.job_lead_id)}>
                          {t("pages.agentRun.recheckReceipt")}
                        </button>
                        <p className="mt-1 text-xs text-text-muted">{t("pages.agentRun.recheckReceiptHint")}</p>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </section>

        <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:self-start">
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.agentRun.eventStream")}
            </h2>
          </div>
          {runState === "loading" ? (
            <p className="p-5 text-sm text-text-secondary">{t("common.loading")}</p>
          ) : null}
          {runState === "error" ? (
            <div className="p-5 text-sm text-error">
              <XCircle className="mb-2 h-5 w-5" aria-hidden="true" />
              {error}
            </div>
          ) : null}
          {runState === "ready" && events.length === 0 ? (
            <p className="p-5 text-sm text-text-secondary">
              {t("pages.agentRun.noEvents")}
            </p>
          ) : null}
          {runState === "ready" && events.length > 0 ? (
            <ol className="max-h-[560px] divide-y divide-border overflow-y-auto">
              {events.map((event, index) => {
                const state = eventState(event);
                return (
                  <li className="px-5 py-4" key={`${event.event_type}-${index}`}>
                    <div className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-accent" />
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center justify-between gap-3">
                          <span className="font-mono text-xs text-text-muted">
                            {formatDate(asString(event.timestamp), i18n.language)}
                          </span>
                          <span className="rounded-chip border border-border bg-bg-primary px-2 py-0.5 text-[11px] text-text-secondary">
                            {t("pages.agentRun.round")}{" "}
                            {String(event.round_index ?? 0)}
                          </span>
                        </p>
                        <p className="mt-2 font-medium text-text-primary">
                          {state
                            ? agentStateLabel(state, t)
                            : asString(event.event_type) ||
                              t("pages.agentRun.eventFallback")}
                        </p>
                        {eventSummary(event) ? (
                          <p className="mt-1 break-words font-mono text-xs text-text-secondary">
                            {eventSummary(event)}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : null}
        </section>
      </div>
      </>
      ) : (
      <section className="rounded-panel border border-dashed border-border bg-bg-panel p-8 text-center" data-testid="agent-run-empty">
        <p className="text-base font-medium text-text-primary">{t("pages.agentRun.noRunTitle")}</p>
        <p className="mt-2 text-sm text-text-secondary">{t("pages.agentRun.noRunHint")}</p>
      </section>
      )}
      </div>
    </div>
  );
}
