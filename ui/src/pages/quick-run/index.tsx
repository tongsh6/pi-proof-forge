import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
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
  QuickRunStartResult,
  ProfilePayload,
} from "@/lib/sidecar/types";
import {
  SCORE_KEYS,
  SCORE_MAX,
  formatConfigValue,
  formatTerminalLines,
} from "./quick-run-helpers";
import type { LoadState, RunState } from "./quick-run-helpers";
import { QuickRunInputSection } from "./components/quick-run-input-section";
import { QuickRunOutputPanel } from "./components/quick-run-output-panel";
import { QuickRunPageHeader } from "./components/quick-run-page-header";
import { QuickRunPipeline } from "./components/quick-run-pipeline";
import { QuickRunScoresPanel } from "./components/quick-run-scores-panel";

export { getStageStatus } from "./quick-run-helpers";

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
  const officialCaptureRequired = selectedProfile?.native_pdf_delivery?.reason === "quick_official_capture_required";
  const manualDeliveryOnly = selectedProfile?.native_pdf_delivery?.supported === false && !officialCaptureRequired;
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
    loadState === "ready" && officialCaptureRequired && "officialCaptureRequired",
    loadState === "ready" && selectedMaterialId === "" && "materialRequired",
    loadState === "ready" && eligibleEvidenceIds.length === 0 && "evidenceRequired",
  ].filter((item): item is string => Boolean(item));
  const canStartRun = startBlockers.length === 0;
  const startBlockerText = startBlockers.map((key) => t(key === "officialCaptureRequired" ? "pages.quickRun.officialCaptureRequired" : `reasons.quickRun.${key}`)).join("，");

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
          // 语义评审失败时回退规则模式继续生成，而不是让整次 Quick Run 失败；
          // 结果页/日志会显式提示「语义评审失败，本次没有有效语义结果」。
          require_llm: false,
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
      const detail = getErrorMessage(e);
      const message = detail === "quick_official_capture_required"
        ? t("pages.quickRun.officialCaptureRequired")
        : detail === "job_profile_official_source_unverified"
          ? t("pages.quickRun.officialSourceUnverified")
          : detail;
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
      <QuickRunPageHeader
        running={runState === "running"}
        canStartRun={canStartRun}
        startBlockerText={startBlockerText}
        onRefresh={() => { clearResult(); void load(); }}
        onStart={() => void handleStartQuickRun()}
      />

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
          <QuickRunInputSection
            providerSummary={providerSummary}
            profileReady={careerProfile?.career_status?.ready === true}
            targetAvailable={targetAvailable}
            onOpenProfile={() => navigate("/resumes")}
            onOpenJobs={() => navigate("/jobs")}
            selectedProfileId={selectedProfileId}
            selectedProfile={selectedProfile}
            activeJobProfiles={activeJobProfiles}
            rulePrecheck={rulePrecheck}
            precheckStateLabel={precheckStateLabel}
            manualDeliveryOnly={manualDeliveryOnly}
            resumePositioning={resumePositioning}
            selectedMaterialId={selectedMaterialId}
            materialSources={materialSources}
            useLlm={useLlm}
            quickRunResult={quickRunResult}
            evidenceCount={evidenceCount}
            availableEvidence={availableEvidence}
            eligibleEvidenceIds={eligibleEvidenceIds}
            runState={runState}
            onSelectedProfileChange={(value) => {
              setSelectedProfileId(value);
              clearResult();
              setSearchParams({ job_profile_id: value }, { replace: true });
            }}
            onResumePositioningChange={(value) => {
              setResumePositioning(value);
              clearResult();
            }}
            onSelectedMaterialChange={(value) => {
              setSelectedMaterialId(value);
              clearResult();
            }}
            onUseLlmChange={(checked) => {
              setUseLlm(checked);
              clearResult();
            }}
            onToggleEvidence={(evidenceId, checked) => {
              clearResult();
              evidenceSelectionMade.current = true;
              setEligibleEvidenceIds((ids) =>
                checked ? [...ids, evidenceId] : ids.filter((id) => id !== evidenceId)
              );
            }}
          />

          <QuickRunPipeline
            runState={runState}
            quickRunStatus={quickRunStatus}
            quickRunResult={quickRunResult}
            task={task}
            elapsedSeconds={elapsedSeconds}
          />

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <QuickRunOutputPanel
              quickRunStatus={quickRunStatus}
              quickRunId={quickRunId}
              selectedProfileTitle={selectedProfile?.title ?? ""}
              evidenceCount={evidenceCount}
              quickRunResult={quickRunResult}
              terminalLines={terminalLines}
              manualDeliveryOnly={manualDeliveryOnly}
              platformDefaultOnly={selectedProfile?.native_pdf_delivery?.reason === "platform_default_only"}
              onNavigate={(path) => navigate(path)}
            />

            <QuickRunScoresPanel
              quickRunResult={quickRunResult}
              scoreBars={scoreBars}
              qualityDecisionNotice={qualityDecisionNotice}
              onHighlightDecision={(highlightId, action) => void decideHighlight(highlightId, action)}
            />
          </section>
        </>
      ) : null}
    </div>
  );
}
