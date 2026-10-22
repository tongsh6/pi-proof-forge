import { PdfQualitySummary } from '@/components/pdf-quality-summary';
import { QualityReportPanel } from '@/components/quality-report';
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  Circle,
  LoaderCircle,
  Play,
  RefreshCw,
} from "lucide-react";
import { getErrorMessage } from "@/lib/errors";
import { isLlmSecretConfigured } from "@/lib/llmConfig";
import { isQuickRunTerminal, trackQuickRun } from "@/lib/quick-run-tracker";
import { useTaskStore, type BackgroundTask } from "@/state/task-store";
import { confirmAction, notify } from "@/lib/ui";
import {
  checkQuickRunDirection,
  getSettings,
  getProfile,
  listEvidence,
  listEvidenceMaterialSources,
  listJobProfiles,
  startQuickRun,
  decideQualityHighlight,
} from "@/lib/sidecar/api";
import type {
  JobProfileListItem,
  EvidenceListItem,
  LlmConfig,
  MaterialSourceItem,
  QuickRunDirectionCheck,
  QuickRunStageProgress,
  QuickRunStartResult,
  ProfilePayload,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type RunState = "idle" | "ready_to_run" | "running" | "done" | "error";
type StageStatus = "waiting" | "running" | "done" | "error" | "skipped";

const PIPELINE_STEPS = [
  { key: "extract", labelKey: "pages.quickRun.steps.extract" },
  { key: "match", labelKey: "pages.quickRun.steps.match" },
  { key: "generate", labelKey: "pages.quickRun.steps.generate" },
  { key: "evaluate", labelKey: "pages.quickRun.steps.evaluate" },
] as const;

const SCORE_KEYS = ["K", "D", "S", "Q", "E", "R"] as const;
const SCORE_MAX = 20;

const stageStatusClass: Record<StageStatus, string> = {
  waiting: "border-border bg-bg-primary/60 text-text-secondary",
  skipped: "border-border bg-bg-primary/60 text-text-secondary",
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

export function getStageStatus(
  runState: RunState,
  status: string | null,
  failedStep: string,
  stepIndex: number,
  stages: QuickRunStageProgress[] | undefined,
  stepKey: string
): StageStatus {
  // RUNNING 时使用后端回写的真实阶段进度；没有进度时只让首阶段进行中，避免四个阶段同时转圈。
  if (runState === "running") {
    const stage = stages?.find((item) => item.key === stepKey);
    if (stage) return stage.status;
    return stepIndex === 0 ? "running" : "waiting";
  }
  if (status === "SKIPPED") {
    const stoppedIndex = PIPELINE_STEPS.findIndex(step => failedStepAliases[step.key].some(alias => failedStep.includes(alias)));
    return stoppedIndex >= 0 && stepIndex < stoppedIndex ? "done" : "skipped";
  }
  if (status === "DONE") {
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

function formatTerminalLines(
  result: QuickRunStartResult | null, runError: string | null,
  labels: { needsReview: string; needsEvidence: string; notGenerated: string }
) {
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
    if (result.resume_readiness) {
      const readiness = result.resume_readiness;
      lines.push(readiness.status === "NOT_GENERATED" ? labels.notGenerated : readiness.status === "NEEDS_EVIDENCE" ? labels.needsEvidence : labels.needsReview);
      lines.push(...readiness.reasons.map((reason) => `- ${reason}`));
    }
  }
  if (runError) lines.push(`[error] ${runError}`);
  return lines.slice(-80);
}

function formatConfigValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
}

export function QuickRunPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedProfileId = searchParams.get("job_profile_id");
  const [careerProfile, setCareerProfile] = useState<ProfilePayload | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [runState, setRunState] = useState<RunState>("idle");
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [eligibleEvidenceIds, setEligibleEvidenceIds] = useState<string[]>([]);
  const [materialSources, setMaterialSources] = useState<MaterialSourceItem[]>([]);
  const [selectedMaterialId, setSelectedMaterialId] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [jobProfiles, setJobProfiles] = useState<JobProfileListItem[]>([]);
  const [llmConfig, setLlmConfig] = useState<LlmConfig | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string>(requestedProfileId ?? "");
  const [resumePositioning, setResumePositioning] = useState("technical_depth");
  const [quickRunId, setQuickRunId] = useState<string | null>(null);
  const [quickRunStatus, setQuickRunStatus] = useState<string | null>(null);
  const [quickRunResult, setQuickRunResult] = useState<QuickRunStartResult | null>(null);
  const [qualityDecisionNotice, setQualityDecisionNotice] = useState("");
  const [runError, setRunError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  // 全局任务：页面切走后运行仍在进行，侧栏显示进度；回到页面时恢复计时或读回同一目标的结果。
  const task = useTaskStore((state) => state.tasks.quickRun);
  const restoredTaskRef = useRef<BackgroundTask | undefined>(undefined);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const quickRunInFlightRef = useRef(false);
  const [availableEvidence,setAvailableEvidence]=useState<EvidenceListItem[]>([]);
  const evidenceSelectionMade=useRef(false);
  const selectionVersion = useRef(0);
  const loadVersion = useRef(0);
  const clearResult = useCallback(() => {
    selectionVersion.current += 1;
    setQuickRunId(null); setQuickRunStatus(null); setQuickRunResult(null); setRunError(null);
    if (!quickRunInFlightRef.current) setRunState("ready_to_run");
  }, []);

  const decideHighlight = useCallback(async (highlightId: string, action: "reject" | "select") => {
    const report = quickRunResult?.quality_report;
    if (!quickRunResult?.run_id || !report?.resume_version) return;
    try {
      await decideQualityHighlight({run_id: quickRunResult.run_id, resume_sha256: report.resume_version, highlight_id: highlightId, action});
      setQualityDecisionNotice(t("quality.report.decisionSaved"));
    } catch (error) {
      setQualityDecisionNotice(getErrorMessage(error));
    }
  }, [quickRunResult, t]);

  useEffect(() => {
    if (requestedProfileId !== null) setSelectedProfileId(requestedProfileId);
    clearResult();
  }, [requestedProfileId, clearResult]);

  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    setLoadState("loading");
    setError(null);
    try {
      const [evidence, materials, jobs, settings, profile] = await Promise.all([
        listEvidence(undefined, { pageSize: 100 }),
        listEvidenceMaterialSources(),
        listJobProfiles(undefined, { pageSize: 100 }),
        getSettings(),
        getProfile(),
      ]);
      if (version !== loadVersion.current) return;
      // 带参目标可能不在第一页；沿原游标读取，不能把首屏外画像当成不存在。
      const profiles = [...jobs.items];
      let cursor = jobs.next_cursor;
      while (cursor) {
        const page = await listJobProfiles(undefined, { cursor, pageSize: 100 });
        if (version !== loadVersion.current) return;
        profiles.push(...page.items);
        cursor = page.next_cursor;
      }
      const evidenceItems = [...evidence.items];
      let evidenceCursor = evidence.next_cursor;
      while (evidenceCursor) {
        const page = await listEvidence(undefined, { cursor: evidenceCursor, pageSize: 100 });
        if (version !== loadVersion.current) return;
        evidenceItems.push(...page.items);
        evidenceCursor = page.next_cursor;
      }
      const eligibleEvidence = evidenceItems.filter(
        (item) => item.status === "saved_eligible" && item.candidate_pool_eligible !== false
      );
      const activeProfiles = profiles.filter((item) => item.status === "active" && item.source_jd?.trim());
      setEvidenceCount(eligibleEvidence.length);
      setAvailableEvidence(eligibleEvidence);
      setEligibleEvidenceIds(previous=>evidenceSelectionMade.current?previous.filter(id=>eligibleEvidence.some(item=>item.evidence_id===id)):eligibleEvidence.map(item=>item.evidence_id));
      setMaterialSources(materials.items);
      setJobProfiles(profiles);
      setLlmConfig(settings.llm_config);
      setCareerProfile(profile.profile);
      setSelectedProfileId(previous => requestedProfileId ?? (previous || activeProfiles[0]?.job_profile_id || ""));
      setLoadState("ready");
    } catch (e) {
      if (version !== loadVersion.current) return;
      setLoadState("error");
      setError(getErrorMessage(e));
    }
  }, [requestedProfileId]);

  useEffect(() => {
    void load();
    return () => { loadVersion.current += 1; selectionVersion.current += 1; };
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

  useEffect(() => {
    if (!task || restoredTaskRef.current === task) return;
    if (task.status === "running") {
      restoredTaskRef.current = task;
      if (!quickRunInFlightRef.current) {
        setRunState("running");
        setStartedAt(task.startedAt);
        if (task.runId) setQuickRunId(task.runId);
      }
      return;
    }
    if (quickRunInFlightRef.current || !selectedProfileId) return;
    restoredTaskRef.current = task;
    if (task.result && task.profileId === selectedProfileId && quickRunResult === null) {
      setQuickRunId(task.result.run_id);
      setQuickRunStatus(task.result.status);
      setQuickRunResult(task.result);
      setRunState(task.status === "done" ? "done" : "error");
      if (task.status === "error") setRunError(task.detail ?? null);
      setElapsedSeconds(Math.max(0, Math.floor(((task.finishedAt ?? task.startedAt) - task.startedAt) / 1000)));
    } else if (runState === "running") {
      // 本实例在等待别处启动的任务：失败则显示失败原因，否则回到可运行态。
      if (task.status === "error") {
        setRunState("error");
        setRunError(task.detail ?? null);
      } else {
        setRunState("ready_to_run");
      }
    }
  }, [task, selectedProfileId, quickRunResult, runState]);
  const activeJobProfiles = jobProfiles.filter((jp) => jp.status === "active" && jp.source_jd?.trim());
  const targetAvailable = selectedProfile?.status === "active" && Boolean(selectedProfile.source_jd?.trim());
  // 手工导入/未绑定已审核平台线索的画像不能走 App 内原生 PDF 投递，只能手动投递后记录。
  const manualDeliveryOnly = selectedProfile?.native_pdf_delivery?.supported === false;
  // 未做模型对位预检时展示规则预检结论；assessed（Quick Run 结果）优先，保持原有已评估提示不变。
  const selectedPrecheck = selectedProfile?.fit_precheck;
  const rulePrecheck = selectedPrecheck && selectedPrecheck.source === "rule" ? selectedPrecheck : null;
  const precheckStateLabel = rulePrecheck
    ? t(`pages.jobs.precheck.state.${rulePrecheck.state}`, { defaultValue: rulePrecheck.state })
    : "";
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
        : isLlmSecretConfigured(llmConfig)
          ? t("pages.systemSettings.llm.keyLocalOptional")
          : t("pages.systemSettings.secretMissing"),
    },
  ];
  // 不能启动时列出全部原因，供页头提示与按钮 title 使用。
  const startBlockers = [
    loadState !== "ready" && "loading",
    runState === "running" && "running",
    loadState === "ready" && careerProfile?.career_status?.ready !== true && "profileNotReady",
    loadState === "ready" && !targetAvailable && "targetUnavailable",
    loadState === "ready" && selectedMaterialId === "" && "materialRequired",
    loadState === "ready" && eligibleEvidenceIds.length === 0 && "evidenceRequired",
  ].filter((item): item is string => Boolean(item));
  const canStartRun = startBlockers.length === 0;
  const startBlockerText = startBlockers.map((key) => t(`reasons.quickRun.${key}`)).join("，");

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
    () => formatTerminalLines(quickRunResult, runError, {
      needsReview: t("pages.quickRun.needsReview"),
      notGenerated: t("pages.quickRun.notGenerated"),
      needsEvidence: t("pages.quickRun.needsEvidence"),
    }),
    [quickRunResult, runError, t]
  );

  const applyTerminalResult = useCallback((result: QuickRunStartResult, version: number, notifyUser: boolean) => {
    const finished = result.status === "DONE" || result.status === "SKIPPED";
    const reason = result.reason || `${result.status}${result.exit_code != null ? ` (${result.exit_code})` : ""}`;
    // 任务 store 与提醒在版本守卫之前完成：页面切走或目标变化后仍要收口全局任务。
    const taskStore = useTaskStore.getState();
    if (notifyUser) {
      if (finished) {
        notify("success", t("toasts.quickRun.done"));
      } else {
        notify("error", t("toasts.quickRun.failed"), reason);
      }
    }
    if (version !== selectionVersion.current) {
      if (finished) taskStore.finish("quickRun", result);
      else taskStore.fail("quickRun", reason);
      return;
    }
    if (finished) taskStore.finish("quickRun", result);
    else taskStore.fail("quickRun", reason);
    setQuickRunId(result.run_id);
    setQuickRunStatus(result.status);
    setQuickRunResult(result);
    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - (taskStore.tasks.quickRun?.startedAt ?? Date.now())) / 1000)));
    setRunState(finished ? "done" : "error");
    if (!finished) setRunError(reason);
  }, [t]);

  const handleStartQuickRun = useCallback(async () => {
    if (!canStartRun || quickRunInFlightRef.current) return;
    if (useTaskStore.getState().tasks.quickRun?.status === "running") return;
    quickRunInFlightRef.current = true;
    const version = selectionVersion.current;
    // 方向评估只给分析与建议：excluded 时由用户决定是否仍然运行，不强制阻断。
    // 预检本身失败时 fail-open，照常启动。
    let directionCheck: QuickRunDirectionCheck | null = null;
    if (useLlm) {
      // 规则模式不做方向评估；仅语义模式需要启动前建议。
      try {
        directionCheck = await checkQuickRunDirection({ job_profile_id: selectedProfileId });
      } catch {
        directionCheck = null;
      }
    }
    let directionAcknowledged = false;
    if (directionCheck?.requires_confirmation && directionCheck.direction) {
      const confirmed = await confirmAction({
        title: t("pages.quickRun.direction.confirmTitle"),
        description: t("pages.quickRun.direction.confirmDescription", {
          reason: directionCheck.direction.reason,
          preference: directionCheck.direction.preference?.text ?? "",
          quote: directionCheck.direction.jd_quote,
        }),
        confirmLabel: t("pages.quickRun.direction.confirmContinue"),
        cancelLabel: t("common.cancel"),
      });
      if (!confirmed) {
        quickRunInFlightRef.current = false;
        return;
      }
      directionAcknowledged = true;
    }
    const now = Date.now();
    const taskStore = useTaskStore.getState();
    taskStore.start({
      kind: "quickRun",
      label: `${t("pages.quickRun.title")} · ${selectedProfile?.title ?? selectedProfileId}`,
      path: "/quick-run",
      profileId: selectedProfileId,
    });
    setStartedAt(now);
    setElapsedSeconds(0);
    setRunState("running");
    setRunError(null);
    setQuickRunStatus(null);
    setQuickRunResult(null);
    setQuickRunId(null);
    try {
      const started = await startQuickRun({
        job_profile_id: selectedProfileId,
        options: {
          generate_resume: true,
          material_id: selectedMaterialId,
          evidence_ids: eligibleEvidenceIds,
          resume_positioning: resumePositioning,
          use_llm: useLlm,
          require_llm: useLlm,
          timeout_seconds: useLlm ? 1800 : 120,
          direction_acknowledged: directionAcknowledged,
        },
      });
      if (isQuickRunTerminal(started.status)) {
        // 兼容同步返回终态（旧后端或测试桩）：无需轮询，直接收口。
        applyTerminalResult(started, version, true);
        return;
      }
      if (version === selectionVersion.current) {
        setQuickRunId(started.run_id);
        setQuickRunStatus(started.status);
      }
      // 轮询不依赖本页挂载；切到其他页面后仍会继续更新全局任务与最终结果。
      const result = await trackQuickRun(started.run_id, {
        doneMessage: t("toasts.quickRun.done"),
        failedMessage: t("toasts.quickRun.failed"),
      });
      if (!result) {
        if (version !== selectionVersion.current) return;
        setRunState("error");
        setRunError(useTaskStore.getState().tasks.quickRun?.detail ?? t("toasts.quickRun.failed"));
        return;
      }
      applyTerminalResult(result, version, false);
    } catch (e) {
      const message = getErrorMessage(e);
      taskStore.fail("quickRun", message);
      notify("error", t("toasts.quickRun.failed"), message);
      if (version !== selectionVersion.current) return;
      setRunState("error");
      setRunError(message);
    } finally {
      quickRunInFlightRef.current = false;
      if (version !== selectionVersion.current) setRunState("ready_to_run");
    }
  }, [applyTerminalResult, canStartRun, eligibleEvidenceIds, resumePositioning, selectedProfileId, selectedProfile?.title, selectedMaterialId, useLlm, t]);


  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => { if (runState !== "running") { clearResult(); void load(); } };
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [load, runState, clearResult]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.quickRun.title")}</h1>
          <p className="page-subtitle">{t("pages.quickRun.subtitle")}</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="page-icon-button"
            onClick={() => { clearResult(); void load(); }}
            disabled={runState === "running"}
            title={t("common.refreshShortcut")}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">{t("common.refresh")}</span>
          </button>
          <button
            type="button"
            data-automation-id="quick-run-start"
            onClick={() => void handleStartQuickRun()}
            disabled={!canStartRun}
            title={canStartRun ? undefined : `${t("reasons.quickRun.title")}${startBlockerText}`}
            className="inline-flex h-10 items-center gap-2 rounded-card border border-accent bg-accent px-4 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {runState === "running" ? (
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="h-4 w-4" aria-hidden="true" />
            )}
            {runState === "running"
              ? t("pages.quickRun.running")
              : t("pages.quickRun.startRun")}
          </button>
        </div>
      </header>

      {loadState === "ready" && !canStartRun && runState !== "running" ? (
        <p
          role="status"
          data-testid="quick-run-blockers"
          className="rounded-card border border-warning/40 bg-warning/10 px-4 py-2 text-sm text-warning"
        >
          {t("reasons.quickRun.title")}
          {startBlockerText}
        </p>
      ) : null}

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
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
            <span className="text-text-muted">{t("pages.quickRun.providerSummary")}</span>
            {providerSummary.map((item) => (
              <span key={item.label}>
                <span className="text-text-muted">{item.label}</span> {item.value}
              </span>
            ))}
          </p>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <h2 className="text-lg font-semibold text-text-primary">
              {t("pages.quickRun.inputSummary")}
            </h2>
            <p role="status" className="mt-3 text-sm text-text-secondary">
              {t(careerProfile?.career_status?.ready ? "pages.quickRun.profileReady" : "pages.quickRun.profileRequired")}
              <button type="button" className="ml-3 text-accent underline" onClick={() => navigate("/resumes")}>{t("pages.quickRun.openProfile")}</button>
            </p>
            {!targetAvailable && <p role="alert" className="mt-2 text-sm text-warning">
              {t("pages.quickRun.targetUnavailable")}
              <button type="button" className="ml-3 text-accent underline" onClick={() => navigate("/jobs")}>{t("pages.quickRun.openJobs")}</button>
            </p>}
            <div className="mt-4 flex flex-wrap gap-3">
                <select
                  value={selectedProfileId}
                  disabled={runState === "running"}
                  onChange={(event) => {
                    setSelectedProfileId(event.target.value);
                    clearResult();
                    setSearchParams({ job_profile_id: event.target.value }, { replace: true });
                  }}
                  className="h-10 min-w-[280px] max-w-full rounded-card border border-border bg-bg-panel px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
                  aria-label={t("pages.quickRun.selectProfile")}
                >
                  {!targetAvailable ? (
                    <option value={selectedProfileId}>{t(selectedProfileId ? "pages.quickRun.targetUnavailable" : "common.empty")}</option>
                  ) : null}
                  {activeJobProfiles.map((profile) => {
                    const precheck = profile.fit_precheck;
                    const suffix = precheck && precheck.source === "rule"
                      ? t("pages.quickRun.fitBadgePrecheck", {
                          label: t(`pages.jobs.precheck.state.${precheck.state}`, { defaultValue: precheck.state }),
                        })
                      : profile.fit_state === "failed"
                        ? t("pages.quickRun.fitBadgeFailed", { count: profile.fit_failures ?? 0 })
                        : profile.fit_state === "unassessed"
                          ? t("pages.quickRun.fitBadgeUnassessed")
                          : "";
                    return (
                      <option key={profile.job_profile_id} value={profile.job_profile_id}>
                        {profile.company ? `${profile.company} · ${profile.title}` : profile.title}{suffix}
                        {profile.native_pdf_delivery?.supported === false ? ` ${t("pages.quickRun.manualDeliveryOnlyBadge")}` : ""}
                      </option>
                    );
                  })}
                </select>
                {selectedProfile && selectedProfile.fit_state === "failed" && !rulePrecheck &&
                  <p role="status" className="text-xs text-warning">
                    {t("pages.quickRun.fitHintFailed", { count: selectedProfile.fit_failures ?? 0 })}
                  </p>}
                {manualDeliveryOnly &&
                  <p role="status" data-testid="quick-run-manual-delivery-hint" className="text-xs text-warning">
                    {t("pages.quickRun.manualDeliveryHintShort")}
                  </p>}
                {selectedProfile && rulePrecheck &&
                  <p role="status" className="text-xs text-text-secondary">
                    {t("pages.quickRun.fitHintPrecheck", {
                      label: precheckStateLabel,
                      matched: rulePrecheck.matched_requirements ?? 0,
                      total: rulePrecheck.total_requirements ?? 0,
                    })}
                  </p>}
                {selectedProfile && selectedProfile.fit_state === "unassessed" && !rulePrecheck &&
                  <p role="status" className="text-xs text-text-secondary">
                    {t("pages.quickRun.fitHintUnassessed")}
                  </p>}
                <select
                  value={resumePositioning}
                  disabled={runState === "running"}
                  onChange={(event) => { setResumePositioning(event.target.value); clearResult(); }}
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
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-card border border-border bg-bg-primary/50 p-4">
                <p className="text-xs uppercase text-text-muted">
                  {t("pages.quickRun.materialSource")}
                </p>
                <select aria-label={t("pages.quickRun.materialSource")} value={selectedMaterialId}
                  disabled={runState === "running"} onChange={event => { setSelectedMaterialId(event.target.value); clearResult(); }}
                  className="mt-2 w-full rounded-card border border-border bg-bg-primary px-2 py-2 text-sm text-text-primary">
                  <option value="">{t("pages.quickRun.chooseMaterial")}</option>
                  {materialSources.map(material => <option key={material.material_id} value={material.material_id}>{material.label || material.material_id}</option>)}
                </select>
                <label className="mt-3 flex items-center gap-2 text-sm text-text-secondary">
                  <input type="checkbox" checked={useLlm} disabled={runState === "running"}
                    onChange={event => { setUseLlm(event.target.checked); clearResult(); }} />
                  {t("pages.quickRun.useLlm")}
                </label>
              </div>
              <div className="rounded-card border border-border bg-bg-primary/50 p-4">
                <p className="text-xs uppercase text-text-muted">
                  {t("pages.quickRun.traceableEvidence")}
                </p>
                <p className="mt-2 truncate text-sm font-medium text-text-primary">
                  {quickRunResult?.traceability?.evidence_card_ids.length
                    ? `${quickRunResult.traceability.evidence_card_ids.length} ${t("pages.quickRun.evidenceCards")}`
                    : `${evidenceCount} ${t("pages.quickRun.evidenceCards")}`}
                </p>
              </div>
            </div>
            <fieldset className="mt-4 rounded-card border border-border p-3"><legend className="px-2 text-sm">{t('pages.quickRun.evidenceSelection')} ({eligibleEvidenceIds.length}/{evidenceCount})</legend><div className="grid gap-2 md:grid-cols-2">{availableEvidence.map(item=><label key={item.evidence_id} className="flex items-start gap-2 text-sm text-text-secondary"><input data-evidence-id={item.evidence_id} type="checkbox" checked={eligibleEvidenceIds.includes(item.evidence_id)} disabled={runState==='running'} onChange={e=>{clearResult();evidenceSelectionMade.current=true;setEligibleEvidenceIds(ids=>e.target.checked?[...ids,item.evidence_id]:ids.filter(id=>id!==item.evidence_id));}}/>{item.title||item.evidence_id}</label>)}</div></fieldset>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            {runState === "running" ? (
              <p role="status" className="mb-4 text-xs text-text-secondary">
                {t("pages.quickRun.runningHint")}
              </p>
            ) : null}
            <div className="grid gap-3 xl:grid-cols-4">
              {PIPELINE_STEPS.map((step, index) => {
                const progressStages = task?.progress?.stages;
                const stageProgress = progressStages?.find((item) => item.key === step.key);
                const stageStatus = getStageStatus(
                  runState,
                  quickRunStatus,
                  quickRunResult?.failed_step ?? "",
                  index,
                  progressStages,
                  step.key
                );
                const stageSeconds = stageProgress?.elapsed_seconds;
                const stageText =
                  stageStatus === "running"
                    ? t("pages.quickRun.progress.running", { seconds: stageSeconds ?? elapsedSeconds })
                    : stageStatus === "done"
                      ? runState === "running" && typeof stageSeconds === "number"
                        ? t("pages.quickRun.progress.done", { seconds: stageSeconds })
                        : t("pages.quickRun.result")
                      : stageStatus === "error"
                        ? t("pages.quickRun.progress.failed")
                        : t(stageStatus === "skipped" ? "pages.quickRun.skipped" : "pages.quickRun.waiting");
                return (
                  <div key={step.key} className="flex items-center gap-3">
                    <div
                      data-stage={step.key}
                      data-stage-status={stageStatus}
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
                        {stageStatus === "waiting" || stageStatus === "skipped" ? (
                          <Circle className="h-5 w-5 text-text-muted" aria-hidden="true" />
                        ) : null}
                      </div>
                      <p className="mt-3 text-sm font-semibold text-text-primary">
                        {t(step.labelKey)}
                      </p>
                      <p className="mt-2 text-xs text-text-secondary">
                        {stageText}
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
              {quickRunResult && <div className="mt-4 space-y-2 text-sm">
                {quickRunResult.career_direction&&<div className={`rounded-card border p-3 ${quickRunResult.career_direction.status === "excluded" ? "border-warning/50 bg-warning/10" : "border-border"}`} data-testid="career-direction-result">
                  <p className="font-semibold">{t(`pages.quickRun.direction.${quickRunResult.career_direction.status}`)}</p>
                  <p>{quickRunResult.career_direction.reason}</p>
                  <p className="mt-2 text-xs text-text-secondary">{t('pages.quickRun.direction.preference')}：{quickRunResult.career_direction.preference.text}</p>
                  <blockquote className="mt-2 border-l-2 border-accent pl-2 text-xs">{quickRunResult.career_direction.jd_quote}</blockquote>
                  <p className="mt-2 text-xs text-text-secondary">{t('pages.quickRun.direction.advisory')}</p>
                </div>}
                <p>{t(quickRunResult.resume_readiness?.status === "NOT_GENERATED" ? "pages.quickRun.notGenerated" : quickRunResult.resume_readiness?.content_ready ? "pages.quickRun.reviewNext" : "pages.quickRun.needsEvidence")}</p>
                {quickRunResult.status === "DONE" && quickRunResult.resume_readiness?.content_ready === true &&
                  quickRunResult.traceability?.resume_traceable === true && quickRunResult.resume_pdf ?
                  (manualDeliveryOnly ? (
                    <div className="space-y-2">
                      <p className="text-xs text-warning" data-testid="quick-run-manual-delivery-result">
                        {t("pages.quickRun.manualDeliveryHint", { path: quickRunResult.resume_pdf })}
                      </p>
                      <button type="button" data-testid="quick-run-record-manual" className="rounded-card border border-border px-3 py-2 text-text-primary"
                        onClick={() => navigate("/jobs")}>{t("pages.quickRun.goRecordManual")}</button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <button type="button" data-testid="quick-run-prepare-pdf" className="rounded-card border border-accent px-3 py-2 text-accent"
                        onClick={() => navigate(`/submissions?quick_run_id=${encodeURIComponent(quickRunResult.run_id)}`)}>{t(quickRunResult.resume_readiness?.quality_passed === false ? "pages.quickRun.preparePdfAnyway" : "pages.quickRun.preparePdf")}</button>
                      {quickRunResult.resume_readiness?.quality_passed === false &&
                        <p className="text-xs text-warning">{t("pages.quickRun.qualityNotPassedCanContinue")}</p>}
                    </div>
                  )) :
                  <button type="button" className="text-accent underline" onClick={() => navigate(quickRunResult.status === "SKIPPED" ? "/jobs" : "/evidence")}>{t(quickRunResult.status === "SKIPPED" ? "pages.quickRun.chooseAnotherJob" : "pages.quickRun.openEvidence")}</button>}
              </div>}
              <div className="mt-4 h-[360px] overflow-auto rounded-card border border-border bg-bg-primary p-4 font-mono text-xs leading-6 text-text-secondary">
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
                  {t(quickRunResult?.semantic_review ? "pages.quickRun.semantic.fit" : "pages.quickRun.scoreLabels.total")}
                </p>
                <p className="mt-2 text-3xl font-semibold text-text-primary">
                  {quickRunResult?.score_total ?? "--"}
                </p>
              </div>
              {quickRunResult?.quality_report && (
                <div className="mt-5">
                  <QualityReportPanel report={quickRunResult.quality_report} onHighlightDecision={decideHighlight}/>
                  {qualityDecisionNotice && <p role="status" className="mt-2 text-xs text-text-secondary">{qualityDecisionNotice}</p>}
                </div>
              )}
              {quickRunResult?.semantic_review ? (
                <div className="mt-5 space-y-4" data-testid="quick-run-semantic-review">
                  <p className="text-xs text-text-secondary">{t("pages.quickRun.semantic.basis", { count: quickRunResult.semantic_review.reviewed_card_count ?? 0 })}</p>
                  <PdfQualitySummary quality={{status:'current',matching_score:quickRunResult.semantic_review.fit_score,
                    resume_score:quickRunResult.semantic_review.resume_score,expression_score:quickRunResult.semantic_review.expression_score,
                    content_ready:quickRunResult.resume_readiness?.content_ready,quality_passed:quickRunResult.resume_readiness?.quality_passed,
                    gap_tasks:quickRunResult.resume_readiness?.gap_tasks}}/>
                  <div className="max-h-[38rem] space-y-2 overflow-auto">
                    {quickRunResult.semantic_review.assessment_scope&&<p className="text-xs text-text-secondary">{t('quality.scope',{...quickRunResult.semantic_review.assessment_scope})}</p>}
                    {quickRunResult.semantic_review.requirements.map((row) => (
                      <details key={row.requirement_id} className="rounded-card border border-border p-3 text-xs">
                        <summary className="cursor-pointer break-words font-medium text-text-primary">{row.text.slice(0, 80)}{row.text.length > 80 ? "…" : ""}<span className="mt-1 block text-text-secondary">{t(`pages.quickRun.semantic.status.${row.resume_status}`)}</span></summary>
                        <p className="mt-3 break-words">{row.text}</p>
                        <p className="mt-2 text-text-secondary">{t("pages.quickRun.semantic.poolStatus")}: {t(`pages.quickRun.semantic.status.${row.status}`)}</p>
                        <p className="mt-2 break-words text-text-secondary">{row.reason}</p>
                        {row.checks?.map(check=><div className="mt-3 border-t border-border pt-2" key={check.requirement_id}>
                          <p className="break-words font-medium">{check.criterion}</p>
                          <p className="mt-1 text-text-secondary">{t('pages.quickRun.semantic.poolStatus')}: {t(`pages.quickRun.semantic.status.${check.status}`)} · {t('quality.inResume')}: {t(`pages.quickRun.semantic.status.${check.resume_status}`)}</p>
                          <p className="mt-1 break-words text-text-secondary">{check.reason}</p>
                        </div>)}
                        {row.citations.map((citation, index) => (
                          <blockquote key={`${citation.fact_id}-${index}`} className="mt-3 break-words border-l-2 border-accent pl-2 text-text-secondary">
                            <p>{citation.quote}</p>
                            <footer className="mt-1 text-text-muted">{citation.source_id} · {citation.field} · {t(citation.in_resume ? "pages.quickRun.semantic.present" : "pages.quickRun.semantic.absent")}</footer>
                          </blockquote>
                        ))}
                      </details>
                    ))}
                  </div>
                </div>
              ) : quickRunResult ? (
              <div className="mt-5 space-y-4">
                {scoreBars.map((item) => (
                  <div key={item.key}>
                    <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                      <span
                        className="truncate font-medium text-text-primary"
                        title={t(`pages.quickRun.scoreLabelsFull.${item.key}`)}
                      >
                        {item.key} · {t(`pages.quickRun.scoreLabelsFull.${item.key}`)}
                      </span>
                      <span className="shrink-0 text-text-secondary">{item.score}</span>
                    </div>
                    <div
                      className="h-2 overflow-hidden rounded-chip bg-bg-primary"
                      role="progressbar"
                      aria-label={t(`pages.quickRun.scoreLabelsFull.${item.key}`)}
                      aria-valuemin={0}
                      aria-valuemax={SCORE_MAX}
                      aria-valuenow={item.score}
                    >
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
              ) : null}
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
