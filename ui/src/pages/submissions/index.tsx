import { PdfQualitySummary } from '@/components/pdf-quality-summary';
import { QualityReportPanel } from '@/components/quality-report';
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  Image as ImageIcon,
  Mail,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  Timer,
  Trash2,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getErrorMessage } from "@/lib/errors";
import { buttonClass, confirmAction, notify } from "@/lib/ui";
import {
  checkChannelSession,
  clearChannelSession,
  createFeedbackIteration,
  getChannelSession,
  getSubmissionDetail,
  listResumes,
  listSubmissionFeedback,
  listSubmissions,
  retrySubmission,
  startSubmissionCheckMode,
  startChannelSession,
  openLiepinNativeSession,
  checkLiepinNativeSession,
  inspectLiepinNativeAttachments,
  cleanupLiepinNativeAttachments,
  syncLiepinFeedback,
  type NativeLiepinObservation,
  prepareLiepinPdf,
  authorizeSingleLiepinPdf,
  previewDailyPdf,
  uploadLiepinNativePdf,
  inspectUploadedLiepinPdf,
  inspectLiepinPdfTarget,
  startLiepinPdfCommunication,
  continueLiepinPdfDelivery,
  verifyNativePdfReceipt,
  removeLiepinNativePdfAttachment,
  recheckLiepinNativePdfRemoval,
  type NativePdfPreparation,
  type FeedbackSyncResult,
  decideQualityHighlight,
} from "@/lib/sidecar/api";
import type { ChannelSessionResult, FeedbackIterationResult, FeedbackListResult, SubmissionCheckModeResult, SubmissionDetail, SubmissionListItem } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type RetryStrategy = "same_channel" | "fallback_email";
type QuickRunOption = { id: string; label: string; updatedAt: string };

const defaultSubmissionChannel = "liepin";

/** PDF 投递步骤条：按阶段推导当前步骤；各按钮的启用逻辑不变，只决定哪一步显示为主按钮。 */
const PDF_STEPS = ["prepare", "review", "upload", "verify", "target", "resume", "send", "receipt"] as const;
function currentPdfStep(pdf: NativePdfPreparation | null, previewed: boolean, consented: boolean): number {
  if (!pdf) return 0;
  switch (pdf.phase as string) {
    case "prepared":
    case "not_submitted":
      return previewed && consented ? 2 : 1;
    case "in_flight":
    case "uploaded_unverified":
    case "unknown":
      return 3;
    case "attachment_verified":
      return 4;
    case "communication_started":
      return 5;
    case "resume_interaction_pending":
    case "delivery_in_flight":
      return 6;
    case "final_send_pending":
      return 7;
    case "success":
      return PDF_STEPS.length;
    default:
      return 0;
  }
}
const checkModeConfirmationItems = [
  "check_mode_no_real_submit",
  "selected_submission_channel",
  "selected_channel_job_lead",
  "selected_resume_pdf",
  "selected_channel_session_metadata",
  "may_use_channel_shared_session",
  "final_confirm_disabled_and_forbidden",
  "must_stop_before_final_confirm",
];

type StatItem = {
  key: "total" | "delivered" | "failed" | "fallback";
  value: number;
  icon: typeof Send;
  className: string;
};

function formatDate(value: string, locale: string): string {
  if (!value.trim()) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale);
}

function isDelivered(status: string): boolean {
  return status === "success" || status === "done";
}

function isFailed(status: string): boolean {
  return status === "failed";
}

function isFallback(item: SubmissionListItem): boolean {
  const combined = `${item.channel} ${item.status} ${item.error} ${item.last_step.detail}`.toLowerCase();
  return combined.includes("fallback") || item.channel.toLowerCase() === "email";
}

function statusClassName(status: string): string {
  if (isDelivered(status)) {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "session_valid") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "blocked") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "waiting_for_manual_login" || status === "session_unknown" || status === "login_required") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "failed") {
    return "border-error/40 bg-error/10 text-error";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

function channelClassName(channel: string): string {
  if (channel.toLowerCase() === "email") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (channel.toLowerCase() === "liepin") {
    return "border-accent/40 bg-accent/10 text-accent";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

function channelLabel(item: SubmissionListItem, unknownChannel: string): string {
  const channel = item.channel || unknownChannel;
  return isFallback(item) && channel.toLowerCase() === "email" ? "Email ↩" : channel;
}

function submissionStatusLabel(status: string, t: (key: string, options?: Record<string, string>) => string): string {
  const normalized = status || "unknown";
  return t(`pages.submissions.status.${normalized}`, { defaultValue: normalized });
}

function screenshotSource(path: string): string | null {
  if (!path) return null;
  try {
    return convertFileSrc(path);
  } catch {
    return path;
  }
}

export function SubmissionsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedQuickRun = searchParams.get("quick_run_id");
  const consumedQuickRun = useRef<string | null | undefined>(undefined);
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<SubmissionListItem[]>([]);
  // 页内按任务分两个标签：投递一份 PDF / 记录与反馈；带 quick_run_id 深链时直接进投递标签。
  const [activeTab, setActiveTab] = useState<"deliver" | "records">(requestedQuickRun ? "deliver" : "records");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [detailState, setDetailState] = useState<LoadState>("ready");
  const [selectedScreenshotPath, setSelectedScreenshotPath] = useState<string | null>(null);
  const [selectedChannel, setSelectedChannel] = useState(defaultSubmissionChannel);
  const [channelSession, setChannelSession] = useState<ChannelSessionResult | null>(null);
  const [sessionState, setSessionState] = useState<LoadState>("loading");
  const [sessionAction, setSessionAction] = useState<string | null>(null);
  const [nativeSession, setNativeSession] = useState("not_opened");
  const [nativeSessionBusy, setNativeSessionBusy] = useState(false);
  const [nativeAttachmentView, setNativeAttachmentView] = useState<NativeLiepinObservation["attachment_view"]>();
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupNotice, setCleanupNotice] = useState("");
  const [pdfQuickRunId, setPdfQuickRunId] = useState("");
  const [quickRunOptions, setQuickRunOptions] = useState<QuickRunOption[]>([]);
  const [nativePdf, setNativePdf] = useState<NativePdfPreparation | null>(null);
  const [acceptPdfEffects, setAcceptPdfEffects] = useState(false);
  const [acceptAttachmentRemoval, setAcceptAttachmentRemoval] = useState(false);
  const [nativePdfError, setNativePdfError] = useState("");
  const [qualityDecisionNotice, setQualityDecisionNotice] = useState("");
  const [nativePdfPreview,setNativePdfPreview]=useState("");
  const decideHighlight = useCallback(async (highlightId: string, action: "reject" | "select") => {
    const report = nativePdf?.quality?.quality_report;
    if (!nativePdf?.run_id || !report?.resume_version) return;
    try {
      await decideQualityHighlight({run_id: nativePdf.run_id, resume_sha256: report.resume_version, highlight_id: highlightId, action});
      setQualityDecisionNotice(t("quality.report.decisionSaved"));
    } catch (error) {
      setQualityDecisionNotice(getErrorMessage(error));
    }
  }, [nativePdf, t]);
  const cleanupOldAttachments = useCallback(async () => {
    const confirmed = await confirmAction({
      title: "移除旧的 App 生成附件",
      description: "将删除猎聘账号中由本 App 命名规则生成的旧 PDF 附件；删除不可恢复。仅清理匹配命名规则的附件。",
      confirmLabel: "确认移除",
      tone: "danger",
    });
    if (!confirmed) return;
    setCleanupBusy(true); setCleanupNotice("");
    try {
      const result = await cleanupLiepinNativeAttachments();
      const hints = (result as unknown as {hints?: string[]}).hints || [];
      setCleanupNotice(hints.join("；") || result.status || "已完成");
      notify("success", "旧附件清理完成");
    } catch (error) {
      setCleanupNotice(getErrorMessage(error));
      notify("error", "旧附件清理失败", getErrorMessage(error));
    } finally {
      setCleanupBusy(false);
    }
  }, [t]);
  const [previewedPdf,setPreviewedPdf]=useState("");
  useEffect(() => {
    if (nativeSessionBusy || consumedQuickRun.current === requestedQuickRun) return;
    consumedQuickRun.current = requestedQuickRun;
    const valid = requestedQuickRun !== null && /^[A-Za-z0-9_-]{1,160}$/.test(requestedQuickRun);
    setPdfQuickRunId(valid ? requestedQuickRun : "");
    setNativePdf(null); setNativePdfPreview(""); setPreviewedPdf("");
    setAcceptPdfEffects(false); setAcceptAttachmentRemoval(false);
    setNativePdfError(requestedQuickRun && !valid ? t("pages.submissions.nativePdf.invalidLinkedRun") : "");
  }, [requestedQuickRun, nativeSessionBusy, t]);
  useEffect(() => {
    let cancelled = false;
    void listResumes().then((result) => {
      if (cancelled) return;
      const options: QuickRunOption[] = [];
      for (const item of result.items) {
        if (item.status !== "latest") continue;
        const match = /^resume_mr-(qr_[A-Za-z0-9]+)_[AB]$/.exec(item.name);
        if (!match) continue;
        options.push({id: match[1], label: `${item.company || "未命名岗位"} · ${item.name.replace(/^resume_mr-|_[AB]$/g, "")} · ${item.score || "--"}`, updatedAt: item.updated_at});
      }
      options.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
      setQuickRunOptions(options);
      setPdfQuickRunId((current) => current || requestedQuickRun || options[0]?.id || "");
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [requestedQuickRun]);

  const [checkModeResult, setCheckModeResult] = useState<SubmissionCheckModeResult | null>(null);
  const [checkModeState, setCheckModeState] = useState<LoadState>("ready");
  const [feedbackList, setFeedbackList] = useState<FeedbackListResult | null>(null);
  const [feedbackIteration, setFeedbackIteration] = useState<FeedbackIterationResult | null>(null);
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [feedbackSource, setFeedbackSource] = useState<"user_note" | "manual_recruiter">("user_note");
  const [feedbackAction, setFeedbackAction] = useState("acknowledge_and_skip");
  const selectionRef = useRef<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<LoadState>("ready");
  const [checkModeForm, setCheckModeForm] = useState({
    jobLeadId: "",
    resumeVersionId: "",
    resumePdfPath: "",
  });

  const stats = useMemo<StatItem[]>(() => [
    {
      key: "total",
      value: items.length,
      icon: Send,
      className: "border-accent/30 bg-accent/10 text-accent",
    },
    {
      key: "delivered",
      value: items.filter((item) => isDelivered(item.status)).length,
      icon: CheckCircle2,
      className: "border-success/30 bg-success/10 text-success",
    },
    {
      key: "failed",
      value: items.filter((item) => isFailed(item.status)).length,
      icon: XCircle,
      className: "border-error/30 bg-error/10 text-error",
    },
    {
      key: "fallback",
      value: items.filter(isFallback).length,
      icon: Mail,
      className: "border-warning/30 bg-warning/10 text-warning",
    },
  ], [items]);

  const screenshotSteps = useMemo(
    () => detail?.steps.filter((step) => step.screenshot) ?? [],
    [detail],
  );

  const selectedScreenshot = useMemo(
    () => screenshotSteps.find((step) => step.screenshot_path === selectedScreenshotPath) ?? screenshotSteps.find((step) => step.screenshot_exists) ?? null,
    [screenshotSteps, selectedScreenshotPath],
  );

  useEffect(() => {
    const firstScreenshot = screenshotSteps.find((step) => step.screenshot_exists);
    setSelectedScreenshotPath(firstScreenshot?.screenshot_path ?? null);
  }, [screenshotSteps]);

  const hasLoadedRef = useRef(false);
  const [refreshing, setRefreshing] = useState(false);

  // 首次加载显示占位；之后的重载保留各区块与详情，不整页回到 loading。
  const loadData = useCallback(async () => {
    if (hasLoadedRef.current) setRefreshing(true);
    else setLoadState("loading");
    setError(null);
    try {
      const result = await listSubmissions();
      setItems(result.items);
      if (selectedId && !result.items.some((item) => item.submission_id === selectedId)) {
        setSelectedId(null);
        setDetail(null);
      }
      hasLoadedRef.current = true;
      setLoadState("ready");
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      if (hasLoadedRef.current) notify("error", t("common.refreshFailed"), message);
      else setLoadState("error");
    } finally {
      setRefreshing(false);
    }
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const loadChannelSession = useCallback(async (channel = selectedChannel) => {
    setSessionState("loading");
    try {
      const result = await getChannelSession(channel);
      setChannelSession(result);
      setSessionState("ready");
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setSessionState("error");
    }
  }, [selectedChannel]);

  useEffect(() => {
    void loadChannelSession(selectedChannel);
  }, [loadChannelSession, selectedChannel]);

  const [feedbackSync, setFeedbackSync] = useState<FeedbackSyncResult | undefined>();
  const handleNativeSession = useCallback(async (action: "open" | "check" | "inspect") => {
    setNativeSessionBusy(true);
    setNativeAttachmentView(undefined);
    try {
      const result = await (action === "open" ? openLiepinNativeSession() : action === "inspect" ? inspectLiepinNativeAttachments() : checkLiepinNativeSession());
      setNativeSession(result.status);
      setNativeAttachmentView(result.attachment_view);
    } catch {
      setNativeSession("unavailable");
    } finally {
      setNativeSessionBusy(false);
    }
  }, []);

  const handleFeedbackSync = useCallback(async () => {
    // 只读同步平台投递进展；失败原因原样显示，不伪造状态。
    setNativeSessionBusy(true);setNativePdfError("");
    try {const result=await syncLiepinFeedback();setFeedbackSync(result);await loadData();}
    catch (error) {setNativePdfError(typeof error === "string" ? error : getErrorMessage(error));}
    finally {setNativeSessionBusy(false);}
  }, [loadData]);

  const handleNativePdf = useCallback(async (action: "authorizeSingle" | "preview" | "prepare" | "upload" | "inspect" | "target" | "communicate" | "inspectChat" | "prepareResume" | "send" | "receipt" | "remove" | "recheckRemoval") => {
    if (nativePdf?.recovery_only && ["upload","communicate","prepareResume","send","remove"].includes(action)) return;
    setNativeSessionBusy(true);setNativePdfError("");
    try {
      if (action === "prepare") {const result=await prepareLiepinPdf(pdfQuickRunId.trim());setNativePdf(result);setAcceptPdfEffects(false);setAcceptAttachmentRemoval(false);setNativePdfPreview("");setPreviewedPdf("");}
      else if(action === "preview" && nativePdf){const result=await previewDailyPdf(nativePdf.run_id);if(result.pdf_sha256!==nativePdf.pdf_sha256)throw new Error('resume_pdf_changed');setNativePdfPreview('data:application/pdf;base64,'+result.pdf_base64);setPreviewedPdf(nativePdf.run_id);}
      else if (action === "authorizeSingle" && nativePdf) setNativePdf(await authorizeSingleLiepinPdf(nativePdf.run_id));
      else if (action === "inspect" && nativePdf) setNativePdf(await inspectUploadedLiepinPdf(nativePdf.run_id));
      else if (action === "target" && nativePdf) setNativePdf(await inspectLiepinPdfTarget(nativePdf.run_id));
      else if (action === "communicate" && nativePdf) setNativePdf(await startLiepinPdfCommunication(nativePdf.run_id));
      else if (action === "inspectChat" && nativePdf) setNativePdf(await continueLiepinPdfDelivery(nativePdf.run_id,"inspect"));
      else if (action === "prepareResume" && nativePdf) setNativePdf(await continueLiepinPdfDelivery(nativePdf.run_id,"prepare"));
      else if (action === "send" && nativePdf) setNativePdf(await continueLiepinPdfDelivery(nativePdf.run_id,"send"));
      else if (action === "receipt" && nativePdf) {setNativePdf(await verifyNativePdfReceipt(nativePdf.run_id));await loadData();}
      else if (action === "recheckRemoval" && nativePdf) setNativePdf(await recheckLiepinNativePdfRemoval(nativePdf.run_id));
      else if (action === "remove" && nativePdf && acceptAttachmentRemoval) setNativePdf(await removeLiepinNativePdfAttachment(nativePdf.run_id,true));
      else if (action === "upload" && nativePdf && acceptPdfEffects && previewedPdf===nativePdf.run_id) setNativePdf(await uploadLiepinNativePdf(nativePdf.run_id,true));
    } catch (error) {
      const message=typeof error === "string" ? error : getErrorMessage(error);
      const contentErrors=['career_profile_unconfirmed','resume_content_incomplete','resume_regeneration_required','resume_generation_changed','resume_pdf_source_changed','resume_evidence_changed','resume_pdf_changed','pdf_generation_trace_invalid'];
      setNativePdfError(message.includes('daily_pdf_filename_too_long')?t('daily.reasons.daily_pdf_filename_too_long'):message.includes('daily_recovery_required')?t('pages.submissions.nativePdf.recoveryOnly'):message.includes('attachment_missing_on_platform')?t('pages.submissions.nativePdf.platformMissing'):message.includes('pdf_receipt_unconfirmed')?t('pages.submissions.nativePdf.receiptNotAvailable'):contentErrors.some(code=>message.includes(code))?t('pages.submissions.nativePdf.contentNotReady'):message);
    }
    finally {setNativeSessionBusy(false);}
  }, [pdfQuickRunId,nativePdf,acceptPdfEffects,acceptAttachmentRemoval,loadData,previewedPdf,t]);

  const handleStartSession = useCallback(async () => {
    setSessionAction("start");
    setError(null);
    try {
      const result = await startChannelSession(selectedChannel);
      setChannelSession(result);
      setSessionState("ready");
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      await loadChannelSession(selectedChannel);
      setSessionState("error");
    } finally {
      setSessionAction(null);
    }
  }, [selectedChannel, loadChannelSession]);

  const handleCheckSession = useCallback(async () => {
    setSessionAction("check");
    setError(null);
    try {
      const result = await checkChannelSession(
        selectedChannel,
      );
      setChannelSession(result);
      setSessionState("ready");
      return result;
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      await loadChannelSession(selectedChannel);
      setSessionState("error");
      return null;
    } finally {
      setSessionAction(null);
    }
  }, [selectedChannel, loadChannelSession]);

  const handleClearSession = useCallback(async () => {
    const confirmed = await confirmAction({
      title: t("confirmations.submissions.clearSession.title"),
      description: t("confirmations.submissions.clearSession.description"),
      confirmLabel: t("confirmations.submissions.clearSession.confirm"),
      tone: "danger",
    });
    if (!confirmed) return;
    setSessionAction("clear");
    setError(null);
    try {
      const result = await clearChannelSession(selectedChannel);
      setChannelSession(result);
      setSessionState("ready");
      notify("success", t("toasts.submissions.sessionCleared"));
    } catch (nextError) {
      setError(getErrorMessage(nextError));
      setSessionState("error");
    } finally {
      setSessionAction(null);
    }
  }, [selectedChannel]);

  const handleStartCheckMode = useCallback(async () => {
    setCheckModeState("loading");
    setError(null);
    try {
      const result = await startSubmissionCheckMode({
        channel: selectedChannel,
        job_lead_id: checkModeForm.jobLeadId.trim(),
        resume_version_id: checkModeForm.resumeVersionId.trim(),
        resume_pdf_path: checkModeForm.resumePdfPath.trim(),
        options: {
          preflight_confirmed: true,
          confirmed_no_real_submit: true,
          check_mode_no_real_submit: true,
          submit_enabled: false,
          confirmation_items: checkModeConfirmationItems,
          target_recovery_limit: 2,
          session_identity_accepted: true,
        },
      });
      setCheckModeResult(result);
      setCheckModeState("ready");
      await loadData();
      return result;
    } catch (nextError) {
      const message = getErrorMessage(nextError);
      setError(message);
      setCheckModeState("error");
      return null;
    }
  }, [checkModeForm, loadData, selectedChannel]);

  const feedbackRunId = selectedId || checkModeResult?.submission_id || "";
  const managedFeedback = Boolean(feedbackList?.source_binding?.status);
  useEffect(() => {
    let active = true;
    setFeedbackList(null); setFeedbackIteration(null); setFeedbackNotes("");
    setFeedbackSource("user_note"); setFeedbackAction("acknowledge_and_skip");
    if (!feedbackRunId) return;
    setFeedbackState("loading");
    void listSubmissionFeedback(feedbackRunId).then(result => {
      if (active) { setFeedbackList(result); setFeedbackState("ready"); }
    }).catch(error => {
      if (active) { setError(getErrorMessage(error)); setFeedbackState("error"); }
    });
    return () => { active = false; };
  }, [feedbackRunId]);

  const handleCreateFeedbackIteration = useCallback(async () => {
    if (!feedbackRunId || feedbackList?.source_run_id !== feedbackRunId) return null;
    setFeedbackState("loading"); setError(null);
    try {
      const result = await createFeedbackIteration({
        source_run_id: feedbackRunId,
        source_feedback_items: feedbackList.items,
        selected_actions: managedFeedback ? [feedbackAction] : ["prepare_next_check_mode"],
        feedback_source: feedbackSource,
        user_notes: managedFeedback ? feedbackNotes.trim() : "Prepare a guarded next check-mode iteration.",
      });
      const list = await listSubmissionFeedback(feedbackRunId);
      if (selectionRef.current && selectionRef.current !== feedbackRunId) return result;
      setFeedbackIteration(result); setFeedbackList(list); setFeedbackNotes(""); setFeedbackState("ready");
      notify("success", t("toasts.submissions.feedbackSaved"));
      return result;
    } catch (nextError) {
      setError(getErrorMessage(nextError)); setFeedbackState("error"); return null;
    }
  }, [feedbackRunId, feedbackList, managedFeedback, feedbackAction, feedbackSource, feedbackNotes]);

  const handleRetry = useCallback(async (submissionId: string, strategy: RetryStrategy = "same_channel") => {
    const confirmKey = strategy === "fallback_email" ? "retryFallback" : "retrySame";
    const confirmed = await confirmAction({
      title: t(`confirmations.submissions.${confirmKey}.title`),
      description: t(`confirmations.submissions.${confirmKey}.description`),
      confirmLabel: t(`confirmations.submissions.${confirmKey}.confirm`),
      tone: "danger",
    });
    if (!confirmed) return;
    setRetryingId(submissionId);
    try {
      await retrySubmission(submissionId, strategy);
      await loadData();
      notify("success", t("toasts.submissions.retryQueued"));
      if (selectedId === submissionId) {
        const result = await getSubmissionDetail(submissionId);
        setDetail(result.submission);
      }
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setRetryingId(null);
    }
  }, [loadData, selectedId]);

  const handleSelect = useCallback(async (submissionId: string) => {
    selectionRef.current = submissionId;
    setSelectedId(submissionId);
    setDetailState("loading");
    setError(null);
    try {
      const result = await getSubmissionDetail(submissionId);
      if (selectionRef.current !== submissionId) return;
      setDetail(result.submission);
      setDetailState("ready");
    } catch (nextError) {
      setDetail(null);
      setError(getErrorMessage(nextError));
      setDetailState("error");
    }
  }, []);

  const pdfStep = currentPdfStep(nativePdf, previewedPdf === nativePdf?.run_id, acceptPdfEffects);
  const stepClass = (step: number) => (pdfStep === step ? buttonClass.primary : buttonClass.secondary);

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void loadData();
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [loadData]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.submissions.title")}</h1>
          <p className="page-subtitle">{t("pages.submissions.subtitle")}</p>
        </div>
        <div className="page-actions">
          <div className="seg-tabs" role="tablist" data-testid="submissions-tabs">
            {(["deliver", "records"] as const).map((tab) => (
              <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)}>
                {t(`pages.submissions.tabs.${tab}`)}
              </button>
            ))}
          </div>
          <button className="page-icon-button" disabled={retryingId !== null || refreshing} onClick={() => void loadData()} type="button" title={t("common.refreshShortcut")}>
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
            <span className="sr-only">{refreshing ? t("common.refreshing") : t("pages.submissions.refresh")}</span>
          </button>
        </div>
      </header>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">{t("common.loading")}</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}

      {loadState === "ready" ? (
        <>
          <div className={activeTab === "deliver" ? "space-y-6" : "hidden"} data-testid="submissions-tab-deliver">
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.nativeSession.title")}</h2>
              <div className="flex gap-2">
                <button type="button" disabled={nativeSessionBusy} onClick={() => void handleNativeSession("open")}
                  className="rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50">{t("pages.submissions.nativeSession.open")}</button>
                <button type="button" disabled={nativeSessionBusy} onClick={() => void handleNativeSession("check")}
                  className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50">{t("pages.submissions.nativeSession.check")}</button>
                <button type="button" disabled={nativeSessionBusy || nativeSession !== "authenticated"} onClick={() => void handleNativeSession("inspect")}
                  className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50">{t("pages.submissions.nativeSession.inspect")}</button>
                <button type="button" disabled={nativeSessionBusy || nativeSession !== "authenticated"} onClick={() => void handleFeedbackSync()}
                  className="rounded-card border border-border px-3 py-2 text-sm text-text-primary disabled:opacity-50">{t("pages.submissions.platformFeedback.sync")}</button>
              </div>
            </div>
            <div className="mt-2 text-sm text-text-secondary">{t("pages.submissions.nativeSession.boundaryShort")}<details className="mt-1 text-xs text-text-muted"><summary className="cursor-pointer select-none text-accent">{t("common.learnMore")}</summary><p className="mt-1">{t("pages.submissions.nativeSession.boundary")}</p></details></div>
            <p className="mt-2 text-sm text-text-primary" role="status">{t(`pages.submissions.nativeSession.status.${nativeSession}`, {defaultValue:t("pages.submissions.nativeSession.status.unavailable")})}</p>
            <p className="mt-2 text-xs text-text-secondary" title={t("pages.submissions.platformFeedback.boundary")}>{t("pages.submissions.platformFeedback.boundaryShort")}</p>
            {feedbackSync && <p role="status" className="mt-2 text-sm text-text-primary">{feedbackSync.status === "records"
              ? t("pages.submissions.platformFeedback.summary", {matched: feedbackSync.matched.length, total: feedbackSync.submissions_total, unmatched: feedbackSync.unmatched_rows})
              : t("pages.submissions.platformFeedback.notFound")}</p>}
            {nativeAttachmentView && <div className="mt-3 text-sm text-text-secondary">
              <p>{t("pages.submissions.nativeSession.attachmentInputs", {count:nativeAttachmentView.inputs.length})}</p>
              {nativeAttachmentView.inputs.map((input, i) => <p key={`input-${i}`}>{input.accept || t("pages.submissions.nativeSession.acceptUnknown")}</p>)}
              {nativeAttachmentView.hints.map((hint, i) => <p key={`hint-${i}`}>{hint}</p>)}
            </div>}
            <div className="mt-4 border-t border-border pt-4 text-sm">
              <ol className="mb-4 flex flex-wrap items-center gap-2" aria-label={t("pages.submissions.nativePdf.stepsTitle")} data-testid="native-pdf-steps">
                {PDF_STEPS.map((step, index) => {
                  const state = index < pdfStep ? "done" : index === pdfStep ? "current" : "pending";
                  return (
                    <li
                      key={step}
                      aria-current={state === "current" ? "step" : undefined}
                      className={`inline-flex items-center gap-1.5 rounded-chip border px-2.5 py-1 text-xs ${
                        state === "done"
                          ? "border-success/40 bg-success/10 text-success"
                          : state === "current"
                            ? "border-accent bg-accent/10 font-medium text-accent"
                            : "border-border text-text-muted"
                      }`}
                    >
                      <span className="font-mono">{String(index + 1).padStart(2, "0")}</span>
                      {t(`pages.submissions.nativePdf.steps.${step}`)}
                    </li>
                  );
                })}
              </ol>
              <details className="mb-3 rounded-card border border-border bg-bg-primary/30 p-3">
                <summary className="cursor-pointer select-none text-xs text-text-secondary">附件维护（移除旧附件）</summary>
                <button type="button" disabled={nativeSessionBusy || cleanupBusy} onClick={()=>void cleanupOldAttachments()}
                  className={`mt-2 ${buttonClass.danger}`}>移除旧的 App 生成附件</button>
                {cleanupNotice && <p role="status" className="mt-2 text-xs text-text-secondary">{cleanupNotice}</p>}
              </details>
              <label className="block text-text-secondary">{t("pages.submissions.nativePdf.selectQuickRun", {defaultValue:"选择最近生成的简历 PDF"})}
                <select aria-label={t("pages.submissions.nativePdf.selectQuickRun", {defaultValue:"选择最近生成的简历 PDF"})} value={pdfQuickRunId} disabled={nativeSessionBusy}
                  onChange={event=>{setPdfQuickRunId(event.target.value);setNativePdf(null);setAcceptPdfEffects(false);setNativePdfPreview("");setPreviewedPdf("");}}
                  className="mt-1 w-full rounded-card border border-border bg-bg-primary px-3 py-2 text-text-primary">
                  <option value="">{t("pages.submissions.nativePdf.selectQuickRunPlaceholder", {defaultValue:"自动选择最近一次生成的 PDF"})}</option>
                  {quickRunOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                  {pdfQuickRunId && !quickRunOptions.some((option) => option.id === pdfQuickRunId) &&
                    <option value={pdfQuickRunId}>{t("pages.submissions.nativePdf.currentLinkedRun", {defaultValue:"当前链接任务"})}</option>}
                </select>
              </label>
              <button type="button" disabled={nativeSessionBusy || !pdfQuickRunId.trim()} onClick={()=>void handleNativePdf("prepare")}
                className={`mt-2 ${stepClass(0)}`}>{t("pages.submissions.nativePdf.prepare")}</button>
              {nativePdf && <div className="mt-3 space-y-2">
                <p>{nativePdf.company} · {nativePdf.position}</p>
                <PdfQualitySummary quality={nativePdf.quality}/>
                {nativePdf.quality?.quality_report&&<QualityReportPanel report={nativePdf.quality.quality_report} onHighlightDecision={decideHighlight}/>}
                {qualityDecisionNotice&&<p role="status" className="text-xs text-text-secondary">{qualityDecisionNotice}</p>}
                {nativePdf.pdf_filename&&<p className="break-all">PDF: {nativePdf.pdf_filename}</p>}
                <p className="font-mono text-xs text-text-muted" title={nativePdf.pdf_sha256}>{t("pages.submissions.pdfFingerprint")}: {nativePdf.pdf_sha256?.slice(0, 12)}…</p>
                <p role="status">{t(`pages.submissions.nativePdf.phase.${nativePdf.phase}`, {defaultValue:nativePdf.phase})}</p>
                {nativePdf.phase === "attachment_verified" && !nativePdf.single_delivery_authorized && !nativePdf.recovery_only &&
                  <button type="button" disabled={nativeSessionBusy} className={buttonClass.secondary} onClick={()=>void handleNativePdf("authorizeSingle")}>{t("pages.submissions.nativePdf.authorizeSingle")}</button>}
                {nativePdf.single_delivery_authorized&&<p>{t("pages.submissions.nativePdf.singleAuthorized")}</p>}
                {nativePdf.verification_error&&<p role="alert" className="text-warning">{t("pages.submissions.nativePdf.verificationPending")}</p>}
                {nativePdf.recovery_only&&<p role="status" className="text-warning">{t('pages.submissions.nativePdf.recoveryOnly')}</p>}
                <div className="flex flex-wrap gap-2">
                  {nativePdf.phase === "prepared" && <button type="button" disabled={nativeSessionBusy} className={buttonClass.secondary}
                    onClick={() => navigate("/agent-run")}>{t("pages.submissions.nativePdf.dailyCandidates")}</button>}
                  <button type="button" disabled={nativeSessionBusy} onClick={()=>void handleNativePdf('preview')} className={stepClass(1)}>{t('pages.submissions.nativePdf.preview')}</button>
                </div>
                {nativePdfPreview&&<iframe title={t('pages.submissions.nativePdf.preview')} src={nativePdfPreview} className="h-[650px] w-full rounded-card border border-border bg-white"/>}
                <label className="flex items-start gap-2 text-text-secondary">
                  <input type="checkbox" aria-label={t("pages.submissions.nativePdf.consent")} checked={acceptPdfEffects} disabled={nativeSessionBusy || nativePdf.recovery_only || previewedPdf!==nativePdf.run_id || !["prepared","not_submitted"].includes(nativePdf.phase)}
                    onChange={event=>setAcceptPdfEffects(event.target.checked)} /><span>{t("pages.submissions.nativePdf.consentShort")}<details className="mt-1 text-xs text-text-muted"><summary className="cursor-pointer select-none text-accent">{t("common.fullTerms")}</summary><p className="mt-1">{t("pages.submissions.nativePdf.consent")}</p></details></span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {pdfStep <= 1 && <button type="button" disabled={nativeSessionBusy} onClick={()=>void handleNativePdf('preview')} className={stepClass(1)}>{t('pages.submissions.nativePdf.preview')}</button>}
                  {pdfStep === 2 && <button type="button" disabled={nativeSessionBusy || nativePdf.recovery_only || previewedPdf!==nativePdf.run_id || !acceptPdfEffects || !["prepared","not_submitted"].includes(nativePdf.phase) || nativeSession !== "authenticated"}
                    onClick={()=>void handleNativePdf("upload")} className={stepClass(2)}>{t("pages.submissions.nativePdf.upload")}</button>}
                  {pdfStep === 3 && <button type="button" disabled={nativeSessionBusy || ["prepared","final_send_pending"].includes(nativePdf.phase)}
                    onClick={()=>void handleNativePdf("inspect")} className={stepClass(3)}>{t("pages.submissions.nativePdf.inspect")}</button>}
                  {pdfStep === 4 && <button type="button" disabled={nativeSessionBusy || nativePdf.phase !== "attachment_verified"}
                    onClick={()=>void handleNativePdf("target")} className={stepClass(4)}>{t("pages.submissions.nativePdf.target")}</button>}
                  {pdfStep === 5 && <button type="button" disabled={nativeSessionBusy || !["communication_started","resume_interaction_pending","final_send_pending"].includes(nativePdf.phase)}
                    onClick={()=>void handleNativePdf("inspectChat")} className={stepClass(5)}>{t("pages.submissions.nativePdf.inspectChat")}</button>}
                  {pdfStep === 6 && <button type="button" disabled={nativeSessionBusy || nativePdf.recovery_only || !nativePdf.can_confirm_send}
                    onClick={()=>void handleNativePdf("send")} className={stepClass(6)}>{t("pages.submissions.nativePdf.send")}</button>}
                  {pdfStep >= 7 && <button type="button" disabled={nativeSessionBusy || !["final_send_pending","success"].includes(nativePdf.phase)}
                    onClick={()=>void handleNativePdf("receipt")} className={stepClass(7)}>{t("pages.submissions.nativePdf.receipt")}</button>}
                </div>
                <details className="mt-2 rounded-card border border-border bg-bg-primary/30 p-3">
                  <summary className="cursor-pointer select-none text-xs text-text-secondary">{t("pages.submissions.nativePdf.moreActions", {defaultValue:"高级操作（诊断/重试）"})}</summary>
                  <div className="mt-2 flex flex-wrap gap-2">                <button type="button" disabled={nativeSessionBusy || nativePdf.recovery_only || previewedPdf!==nativePdf.run_id || !acceptPdfEffects || !["prepared","not_submitted"].includes(nativePdf.phase) || nativeSession !== "authenticated"}
                  onClick={()=>void handleNativePdf("upload")} className={stepClass(2)}>{t("pages.submissions.nativePdf.upload")}</button>
                <button type="button" disabled={nativeSessionBusy || ["prepared","final_send_pending"].includes(nativePdf.phase)}
                  onClick={()=>void handleNativePdf("inspect")} className={stepClass(3)}>{t("pages.submissions.nativePdf.inspect")}</button>
                <button type="button" disabled={nativeSessionBusy || nativePdf.phase !== "attachment_verified"}
                  onClick={()=>void handleNativePdf("target")} className={stepClass(4)}>{t("pages.submissions.nativePdf.target")}</button>
                <button type="button" disabled={nativeSessionBusy || nativePdf.recovery_only || nativePdf.phase !== "attachment_verified"}
                  onClick={()=>void handleNativePdf("communicate")} className={stepClass(4)}>{t("pages.submissions.nativePdf.communicate")}</button>
                <button type="button" disabled={nativeSessionBusy || !["communication_started","resume_interaction_pending","final_send_pending"].includes(nativePdf.phase)}
                  onClick={()=>void handleNativePdf("inspectChat")} className={stepClass(5)}>{t("pages.submissions.nativePdf.inspectChat")}</button>
                <button type="button" disabled={nativeSessionBusy || nativePdf.recovery_only || nativePdf.phase !== "communication_started"}
                  onClick={()=>void handleNativePdf("prepareResume")} className={stepClass(5)}>{t("pages.submissions.nativePdf.prepareResume")}</button>
                <button type="button" disabled={nativeSessionBusy || nativePdf.recovery_only || !nativePdf.can_confirm_send}
                  onClick={()=>void handleNativePdf("send")} className={stepClass(6)}>{t("pages.submissions.nativePdf.send")}</button>
                <button type="button" disabled={nativeSessionBusy || !["final_send_pending","success"].includes(nativePdf.phase)}
                  onClick={()=>void handleNativePdf("receipt")} className={stepClass(7)}>{t("pages.submissions.nativePdf.receipt")}</button>
                  </div>
                </details>
                {nativePdf.phase === "success" && nativePdf.platform_filename && <div className="mt-3 border-t border-border pt-3">
                  <p className="break-all">{t("pages.submissions.nativePdf.platformFile")}: {nativePdf.platform_filename}</p>
                  <p className="text-xs text-text-secondary">{t("pages.submissions.nativePdf.removeBoundary")}</p>
                  {nativePdf.platform_attachment_state === "missing_on_platform" && nativePdf.attachment_removal_state !== "removed" && <p role="status" className="text-warning">{t("pages.submissions.nativePdf.platformMissing")}</p>}
                  <label className="mt-2 flex items-center gap-2"><input type="checkbox" aria-label={t("pages.submissions.nativePdf.removeConsent")}
                    checked={acceptAttachmentRemoval} disabled={nativeSessionBusy || nativePdf.platform_attachment_state === "missing_on_platform" || ["in_flight","unknown","removed"].includes(nativePdf.attachment_removal_state || "")}
                    onChange={event=>setAcceptAttachmentRemoval(event.target.checked)} />{t("pages.submissions.nativePdf.removeConsent")}</label>
                  <button type="button" disabled={nativeSessionBusy || !acceptAttachmentRemoval || nativePdf.platform_attachment_state === "missing_on_platform" || ["in_flight","unknown","removed"].includes(nativePdf.attachment_removal_state || "")}
                    onClick={()=>void handleNativePdf("remove")} className={`mt-2 ${buttonClass.danger}`}>{t("pages.submissions.nativePdf.remove")}</button>
                  {nativePdf.attachment_removal_state === "unknown" && <button type="button" disabled={nativeSessionBusy}
                    onClick={()=>void handleNativePdf("recheckRemoval")} className={`ml-2 ${buttonClass.secondary}`}>{t("pages.submissions.nativePdf.recheckRemoval")}</button>}
                  {nativePdf.attachment_removal_state && <p role="status">{t(`pages.submissions.nativePdf.removal.${nativePdf.attachment_removal_state}`)}</p>}
                </div>}

              </div>}
              {nativePdfError && <p role="alert" className="mt-2 text-sm text-error">{nativePdfError}</p>}
            </div>
          </section>
          </div>

          <div className={activeTab === "records" ? "space-y-6" : "hidden"} data-testid="submissions-tab-records">
          <section className="stat-strip" data-testid="submissions-stats">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <span key={stat.key} className="inline-flex items-baseline gap-1.5">
                  <Icon className={`h-3.5 w-3.5 self-center ${stat.className.split(" ").find((name) => name.startsWith("text-")) ?? ""}`} aria-hidden="true" />
                  <strong>{stat.value}</strong>
                  {t(`pages.submissions.stats.${stat.key}`)}
                </span>
              );
            })}
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_440px]">
          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.runsTitle")}</h2>
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[640px]">
                <div className="grid grid-cols-[minmax(110px,1.05fr)_minmax(120px,1.05fr)_76px_118px_70px_58px] gap-3 border-b border-border px-5 py-3 text-xs font-medium uppercase tracking-[0.08em] text-text-muted">
                  <span>{t("pages.submissions.table.company")}</span>
                  <span>{t("pages.submissions.table.position")}</span>
                  <span>{t("pages.submissions.table.channel")}</span>
                  <span>{t("pages.submissions.table.date")}</span>
                  <span>{t("pages.submissions.table.status")}</span>
                  <span className="text-right">{t("pages.submissions.table.action")}</span>
                </div>
                <div className="divide-y divide-border">
                  {items.map((item) => (
                    <div key={item.submission_id} className={`grid grid-cols-[minmax(110px,1.05fr)_minmax(120px,1.05fr)_76px_118px_70px_58px] gap-3 px-5 py-4 text-sm ${selectedId === item.submission_id ? "bg-accent/5" : ""}`}>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-text-primary">{item.company || item.submission_id}</p>
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-text-primary">{item.position || "--"}</p>
                        <p className="mt-1 truncate text-xs text-text-secondary">{item.mode ? t(`codes.mode.${item.mode}`, { defaultValue: item.mode }) : "--"}</p>
                      </div>
                      <div className="min-w-0">
                        <span className={`inline-flex max-w-full rounded-chip border px-2 py-0.5 text-xs font-medium ${channelClassName(item.channel)}`}>
                          <span className="truncate">{t(`codes.platform.${item.channel}`, { defaultValue: channelLabel(item, t("pages.submissions.unknownChannel")) })}</span>
                        </span>
                      </div>
                      <p className="truncate text-text-secondary">{formatDate(item.submitted_at, i18n.language)}</p>
                      <div>
                        <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(item.status)}`}>
                          {submissionStatusLabel(item.status, t)}
                        </span>
                        {item.platform_feedback?.status && <p className="mt-1 truncate text-xs text-text-secondary">{t(`pages.submissions.platformFeedback.status.${item.platform_feedback.status}`, {defaultValue: item.platform_feedback.status})}{item.platform_feedback.time_label ? ` · ${item.platform_feedback.time_label}` : ""}</p>}
                      </div>
                      <div className="flex justify-end gap-2">
                        <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={detailState === "loading" && selectedId === item.submission_id} onClick={() => void handleSelect(item.submission_id)} title={t("pages.submissions.details")} type="button" aria-label={t("pages.submissions.details")}>
                          <Eye className="h-4 w-4" aria-hidden="true" />
                        </button>
                        <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null || item.retry_allowed === false} onClick={() => void handleRetry(item.submission_id)} title={item.retry_allowed === false ? t("pages.submissions.apiRetryBlocked") : retryingId === item.submission_id ? t("pages.submissions.retrying") : t("common.retry")} type="button" aria-label={retryingId === item.submission_id ? t("pages.submissions.retrying") : t("common.retry")}>
                          <RotateCcw className={`h-4 w-4 ${retryingId === item.submission_id ? "animate-spin" : ""}`} aria-hidden="true" />
                        </button>
                      </div>
                    </div>
                  ))}
                  {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.empty")}</div> : null}
                </div>
              </div>
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)] xl:sticky xl:top-[6.5rem] xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto">
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.detailTitle")}</h2>
            </div>
            {detailState === "loading" ? <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.loadingDetail")}</div> : null}
            {detailState === "error" ? <div className="p-5 text-sm text-error">{error}</div> : null}
            {detailState === "ready" && detail ? (
              <div className="space-y-5 p-5">
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-text-primary">{[detail.company, detail.position].filter(Boolean).join(" · ") || detail.submission_id}</p>
                    <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(detail.status)}`}>
                      {submissionStatusLabel(detail.status, t)}
                    </span>
                    {detail.mode ? <span className="rounded-chip border border-border px-2 py-0.5 text-xs text-text-secondary">{t(`codes.mode.${detail.mode}`, { defaultValue: detail.mode })}</span> : null}
                  </div>
                  <dl className="grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.company")}</dt>
                      <dd className="mt-1 truncate text-text-primary">{detail.company || "--"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.position")}</dt>
                      <dd className="mt-1 truncate text-text-primary">{detail.position || "--"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.channel")}</dt>
                      <dd className="mt-1 text-text-primary">{t(`codes.platform.${detail.channel}`, { defaultValue: channelLabel(detail, t("pages.submissions.unknownChannel")) })}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.browser")}</dt>
                      <dd className="mt-1 text-text-primary">{detail.browser_channel ? t(`codes.browser.${detail.browser_channel}`, { defaultValue: detail.browser_channel }) : "--"}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-xs text-text-muted">{t("pages.submissions.fields.submittedAt")}</dt>
                      <dd className="mt-1 text-text-primary">{formatDate(detail.started_at, i18n.language)} → {formatDate(detail.ended_at, i18n.language)}</dd>
                    </div>
                    {detail.job_url ? (
                      <div className="sm:col-span-2">
                        <dt className="text-xs text-text-muted">{t("pages.submissions.fields.jobUrl")}</dt>
                        <dd className="mt-1 break-all font-mono text-xs text-text-secondary">{detail.job_url}</dd>
                      </div>
                    ) : null}
                  </dl>
                </div>
                <div className="grid gap-2 border-t border-border pt-4 text-xs text-text-secondary">
                  {detail.resume_version_id ? <p>{t("pages.submissions.checkMode.resumeVersion")}: {detail.resume_version_id}</p> : null}
                  {detail.evidence?.status && <>
                    <p role="status">{t(`pages.submissions.evidence.${detail.evidence.status}`)}</p>
                    <p>{t(`pages.submissions.evidence.${detail.evidence.delivery_kind}`, {defaultValue: "--"})} · {t(`pages.submissions.evidence.${detail.evidence.receipt_source}`, {defaultValue: "--"})}</p>
                    <p className="break-all">{t("pages.submissions.evidence.resumeHash")}: {detail.evidence.resume_sha256 || "--"}</p>
                    <p className="break-all">{t("pages.submissions.evidence.receiptHash")}: {detail.evidence.receipt_sha256 || "--"}</p>
                  </>}

                  {detail.parent_run_id ? <button type="button" className="text-accent underline" onClick={() => navigate(`/agent-run?run_id=${encodeURIComponent(detail.parent_run_id ?? "")}`)}>{t("pages.submissions.openApproval")}</button> : null}
                  <details>
                    <summary className="cursor-pointer select-none text-text-muted">{t("pages.submissions.technicalDetails")}</summary>
                    <div className="mt-2 grid gap-2">
                      <p className="break-all"><span className="text-text-muted">ID</span> {detail.submission_id}</p>
                      <p className="break-all"><span className="text-text-muted">{t("pages.submissions.fields.resume")}</span> {detail.resume_path || "--"}</p>
                      <p className="break-all"><span className="text-text-muted">{t("pages.submissions.fields.profile")}</span> {detail.profile_path || "--"}</p>
                      <p className="break-all"><span className="text-text-muted">JSON</span> {detail.log_json_path || "--"}</p>
                      <p className="break-all"><span className="text-text-muted">YAML</span> {detail.log_yaml_path || "--"}</p>
                    </div>
                  </details>
                </div>
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-text-primary">{t("pages.submissions.timeline")}</h3>
                  <div className="space-y-3">
                    {detail.steps.map((step, index) => (
                      <div key={`${step.name}-${index}`} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
                        <div className="flex flex-col items-center">
                          <span className={`grid h-7 w-7 place-items-center rounded-full border text-[11px] ${statusClassName(step.status)}`}>
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          {index < detail.steps.length - 1 ? <span className="mt-2 h-full min-h-8 w-px bg-border" /> : null}
                        </div>
                        <div className="min-w-0 pb-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-text-primary">{step.name ? t(`codes.steps.${step.name}`, { defaultValue: step.name }) : "--"}</span>
                            <span className={`rounded-chip border px-2 py-0.5 text-xs ${statusClassName(step.status)}`}>{step.status || "--"}</span>
                          </div>
                          {/^\s*[{[]/.test(step.detail || "") ? (
                            <details className="mt-2 text-xs text-text-secondary">
                              <summary className="cursor-pointer select-none">{t("pages.submissions.detail.receiptReceived")}</summary>
                              <p className="mt-1 break-words font-mono">{step.detail}</p>
                            </details>
                          ) : (
                            <p className="mt-2 break-words text-xs text-text-secondary">{step.detail || "--"}</p>
                          )}
                        {step.screenshot ? (
                          <p className="mt-2 break-all font-mono text-xs text-text-muted">
                            {step.screenshot_exists ? step.screenshot_path : t("pages.submissions.missingScreenshot", { path: step.screenshot })}
                          </p>
                        ) : null}
                        </div>
                      </div>
                    ))}
                    {detail.steps.length === 0 ? <p className="text-sm text-text-secondary">{t("pages.submissions.noSteps")}</p> : null}
                  </div>
                </div>
                <div className="space-y-3 border-t border-border pt-4">
                  <h3 className="text-sm font-semibold text-text-primary">{t("pages.submissions.screenshots.title")}</h3>
                  {screenshotSteps.length > 0 ? (
                    <div className="grid gap-3">
                      <div className="grid gap-2 sm:grid-cols-2">
                        {screenshotSteps.map((step, index) => (
                          <button key={`${step.screenshot}-${index}`} className={`min-h-20 rounded-card border p-2 text-left hover:bg-bg-hover ${selectedScreenshot?.screenshot_path === step.screenshot_path ? "border-accent bg-accent/10" : "border-border bg-bg-primary/40"}`} disabled={!step.screenshot_exists} onClick={() => setSelectedScreenshotPath(step.screenshot_path)} type="button">
                            <div className="flex items-center gap-2 text-xs text-text-secondary">
                              <ImageIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
                              <span className="truncate">{step.name || step.screenshot}</span>
                            </div>
                            <p className="mt-2 truncate font-mono text-[11px] text-text-muted">{step.screenshot_exists ? step.screenshot : t("pages.submissions.screenshots.missing")}</p>
                          </button>
                        ))}
                      </div>
                      <div className="min-h-[180px] overflow-hidden rounded-card border border-border bg-bg-primary/50">
                        {selectedScreenshot?.screenshot_exists && selectedScreenshot.screenshot_path ? (
                          <img className="h-full max-h-[320px] w-full object-contain" src={screenshotSource(selectedScreenshot.screenshot_path) ?? undefined} alt={selectedScreenshot.name || t("pages.submissions.screenshots.preview")} />
                        ) : (
                          <div className="grid min-h-[180px] place-items-center text-sm text-text-secondary">{t("pages.submissions.screenshots.emptyPreview")}</div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-text-secondary">{t("pages.submissions.screenshots.empty")}</p>
                  )}
                </div>
                <div className="space-y-3 border-t border-border pt-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                    <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />
                    {t("pages.submissions.failure.title")}
                  </h3>
                  <p className="break-words text-sm text-text-secondary">{detail.error || (/^\s*[{[]/.test(detail.last_step.detail || "") ? "" : detail.last_step.detail) || t("pages.submissions.failure.empty")}</p>
                  <div className="grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
                    <button className="rounded-card border border-border bg-bg-primary/40 p-3 text-left hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null || detail.retry_allowed === false} onClick={() => void handleRetry(detail.submission_id, "same_channel")} type="button">
                      <p className="flex items-center gap-2 text-text-primary"><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("pages.submissions.retryStrategy.sameChannel")}</p>
                      <p className="mt-1">{detail.channel || t("pages.submissions.unknownChannel")}</p>
                    </button>
                    <button className="rounded-card border border-border bg-bg-primary/40 p-3 text-left hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null || detail.retry_allowed === false} onClick={() => void handleRetry(detail.submission_id, "fallback_email")} type="button">
                      <p className="flex items-center gap-2 text-text-primary"><Timer className="h-4 w-4" aria-hidden="true" />{t("pages.submissions.retryStrategy.fallbackEmail")}</p>
                      <p className="mt-1">{detail.rate_limit_detail || "--"}</p>
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
            {detailState === "ready" && !detail ? (
              <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.selectRun")}</div>
            ) : null}
          </section>
          </div>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.feedback.title")}</h2>
                <p className="mt-1 text-sm text-text-secondary">{t("pages.submissions.feedback.boundary")}</p>
              </div>
              <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={feedbackState === "loading" || !feedbackRunId || !feedbackList || (managedFeedback && !feedbackNotes.trim())} onClick={() => void handleCreateFeedbackIteration()} type="button">
                <RotateCcw className={`h-4 w-4 ${feedbackState === "loading" ? "animate-spin" : ""}`} aria-hidden="true" />
                {feedbackState === "loading" ? t("pages.submissions.feedback.recording") : t("pages.submissions.feedback.create")}
              </button>
            </div>
            <label className="mt-4 block text-sm text-text-secondary">
              {t("pages.submissions.feedback.submission")}
              <select aria-label={t("pages.submissions.feedback.submission")} className="mt-1 w-full rounded-card border border-border bg-bg-primary p-2 text-text-primary"
                value={selectedId || ""} disabled={feedbackState === "loading"} onChange={event => { if (event.target.value) void handleSelect(event.target.value); }}>
                <option value="">{t("pages.submissions.feedback.chooseSubmission")}</option>
                {items.map(item => <option key={item.submission_id} value={item.submission_id}>{item.company || item.submission_id} · {item.position || "--"} · {formatDate(item.submitted_at, i18n.language)}</option>)}
              </select>
            </label>
            {managedFeedback && <div className="mt-3 space-y-3 text-sm">
              <p className="break-all text-text-secondary">{t("pages.submissions.checkMode.resumeVersion")}: {feedbackList?.source_binding?.resume_version_id || "--"}</p>
              <div className="grid gap-3 md:grid-cols-2">
                <label>{t("pages.submissions.feedback.source")}<select aria-label={t("pages.submissions.feedback.source")} className="mt-1 w-full rounded-card border border-border bg-bg-primary p-2"
                  value={feedbackSource} onChange={event => setFeedbackSource(event.target.value as "user_note" | "manual_recruiter")}>
                  <option value="user_note">{t("pages.submissions.feedback.sources.user_note")}</option><option value="manual_recruiter">{t("pages.submissions.feedback.sources.manual_recruiter")}</option>
                </select></label>
                <label>{t("pages.submissions.feedback.action")}<select aria-label={t("pages.submissions.feedback.action")} className="mt-1 w-full rounded-card border border-border bg-bg-primary p-2"
                  value={feedbackAction} onChange={event => setFeedbackAction(event.target.value)}>
                  {(feedbackList?.supported_actions || []).map(action => <option key={action} value={action}>{t(`pages.submissions.feedback.actions.${action}`)}</option>)}
                </select></label>
              </div>
              <label className="block">{t("pages.submissions.feedback.notes")}<textarea aria-label={t("pages.submissions.feedback.notes")} maxLength={4000}
                className="mt-1 min-h-24 w-full rounded-card border border-border bg-bg-primary p-2" value={feedbackNotes} onChange={event => setFeedbackNotes(event.target.value)} /></label>
              <p className="text-xs text-text-muted">{t("pages.submissions.feedback.planOnly")}</p>
            </div>}
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.items")}</p>
                <p className="mt-1 text-text-primary">{feedbackList?.items.length ?? 0}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.action")}</p>
                <p className="mt-1 truncate text-text-primary">{feedbackIteration?.iteration.selected_actions.join(", ") || "--"}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.version")}</p>
                <p className="mt-1 truncate text-text-primary">{feedbackIteration?.iteration.new_resume_version_id_or_none || "--"}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.feedback.next")}</p>
                <p className="mt-1 truncate text-text-primary">{feedbackIteration?.iteration.next_recommended_step || "--"}</p>
              </div>
            </div>
            <details className="mt-3 text-xs text-text-secondary">
              <summary className="cursor-pointer select-none text-text-muted">{t("pages.submissions.technicalDetails")}</summary>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <p className="break-all"><span className="text-text-muted">{t("pages.submissions.feedback.record")}</span> {feedbackIteration?.record_path || "--"}</p>
                <p className="break-all"><span className="text-text-muted">{t("pages.submissions.feedback.snapshot")}</span> {feedbackIteration?.iteration.source_snapshot_path || "--"}</p>
              </div>
            </details>
            {(feedbackList?.iterations || []).map(record => <article key={record.iteration_id} className="mt-3 rounded-card border border-border p-3 text-sm">
              <p className="text-xs text-text-muted">{formatDate(record.created_at, i18n.language)} · {t(`pages.submissions.feedback.sources.${record.feedback_source || "user_note"}`)}</p>
              <p className="mt-2 whitespace-pre-wrap break-words">{record.user_notes}</p>
              <p className="mt-2 text-text-secondary">{record.selected_actions.map(action => t(`pages.submissions.feedback.actions.${action}`, {defaultValue:action})).join(" · ")}</p>
              {record.next_quick_run_candidate?.job_profile_id && <p className="mt-2 text-xs text-text-secondary">{t("pages.submissions.feedback.targetProfile")}: {record.next_quick_run_candidate.job_profile_id}</p>}
              {record.next_recommended_step === "quick_run" && <button type="button" onClick={() => navigate("/quick-run")} className="mt-2 inline-block text-accent underline">{t("pages.submissions.feedback.openQuickRun")}</button>}
              {record.next_recommended_step === "evidence" && <button type="button" onClick={() => navigate("/evidence")} className="mt-2 inline-block text-accent underline">{t("pages.submissions.feedback.openEvidence")}</button>}
              {record.next_recommended_step === "jobs" && <button type="button" onClick={() => navigate("/jobs")} className="mt-2 inline-block text-accent underline">{t("pages.submissions.feedback.openJobs")}</button>}
            </article>)}
            {feedbackState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
          </section>

          <details className="fold-section rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]" data-testid="submissions-advanced">
            <summary>
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-3">
                <span>{t("pages.submissions.advancedTools")}</span>
                <span className="text-sm font-normal text-text-secondary">{t("pages.submissions.advancedHint")}</span>
              </span>
            </summary>
            <div className="space-y-6 px-5 pb-5">
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.session.title")}</h2>
                <p className="mt-1 text-sm text-text-secondary" title={t("pages.submissions.session.manualBoundary")}>{t("pages.submissions.session.manualBoundaryShort")}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select className="h-9 rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={selectedChannel} onChange={(event) => setSelectedChannel(event.target.value)} aria-label={t("pages.submissions.session.channel")}>
                  {(channelSession?.supported_channels ?? [{ channel: defaultSubmissionChannel, label: "Liepin", login_url: "" }]).map((channel) => (
                    <option key={channel.channel} value={channel.channel}>{channel.label}</option>
                  ))}
                </select>
                <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null} onClick={() => void handleStartSession()} type="button">
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                  {sessionAction === "start" ? t("pages.submissions.session.starting") : t("pages.submissions.session.start")}
                </button>
                <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null} onClick={() => void handleCheckSession()} type="button">
                  <RefreshCw className={`h-4 w-4 ${sessionAction === "check" ? "animate-spin" : ""}`} aria-hidden="true" />
                  {t("pages.submissions.session.check")}
                </button>
                <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={sessionAction !== null || !channelSession?.session.clear_available} onClick={() => void handleClearSession()} title={t("pages.submissions.session.clear")} type="button" aria-label={t("pages.submissions.session.clear")}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.statusLabel")}</p>
                <p className={`mt-1 inline-flex rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(channelSession?.session.login_status ?? "unknown")}`}>
                  {t(`pages.submissions.session.status.${channelSession?.session.login_status ?? "unknown"}`, { defaultValue: channelSession?.session.login_status ?? "unknown" })}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.checkedAt")}</p>
                <p className="mt-1 truncate text-text-primary">{formatDate(channelSession?.session.checked_at ?? "", i18n.language)}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.identity")}</p>
                <p className="mt-1 truncate text-text-primary">{channelSession?.session.account_identity.display_name_or_nickname || channelSession?.session.account_identity.masked_phone_or_email_suffix || t("pages.submissions.session.identityUnknown")}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.session.storage")}</p>
                <p className="mt-1 truncate text-text-primary">{channelSession?.session.expires_or_unknown ?? "--"}</p>
              </div>
            </div>
            <details className="mt-3 text-xs text-text-secondary">
              <summary className="cursor-pointer select-none text-text-muted">{t("pages.submissions.technicalDetails")}</summary>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <p className="break-all"><span className="text-text-muted">{t("pages.submissions.session.path")}</span> {channelSession?.session.session_path || "--"}</p>
                <p className="break-all"><span className="text-text-muted">{t("pages.submissions.session.log")}</span> {channelSession?.artifact_paths.session_check_log || "--"}</p>
              </div>
            </details>
            {sessionState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
          </section>

          <details className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <summary className="cursor-pointer select-none px-5 py-4 text-lg font-semibold text-text-primary">
              {t("pages.submissions.checkMode.title")}
              <span className="ml-2 text-xs font-normal text-text-muted">{t("pages.submissions.checkMode.collapsedHint")}</span>
            </summary>
            <div className="px-5 pb-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm text-text-secondary">{t("pages.submissions.checkMode.boundary")}</p>
              </div>
              <button className="inline-flex h-9 items-center gap-2 rounded-card border border-border px-3 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={checkModeState === "loading" || channelSession?.session.login_status !== "session_valid" || !checkModeForm.jobLeadId.trim() || !checkModeForm.resumeVersionId.trim() || !checkModeForm.resumePdfPath.trim()} onClick={() => void handleStartCheckMode()} type="button">
                <Send className="h-4 w-4" aria-hidden="true" />
                {checkModeState === "loading" ? t("pages.submissions.checkMode.running") : t("pages.submissions.checkMode.start")}
              </button>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.jobLead")}</span>
                <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.jobLeadId} onChange={(event) => setCheckModeForm((current) => ({ ...current, jobLeadId: event.target.value }))} placeholder={t("pages.submissions.checkMode.jobLeadPlaceholder")} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.resumeVersion")}</span>
                <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.resumeVersionId} onChange={(event) => setCheckModeForm((current) => ({ ...current, resumeVersionId: event.target.value }))} placeholder={t("pages.submissions.checkMode.resumeVersionPlaceholder")} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-text-muted">{t("pages.submissions.checkMode.resume")}</span>
                <input className="h-9 w-full rounded-card border border-border bg-bg-primary px-3 text-sm text-text-primary" value={checkModeForm.resumePdfPath} onChange={(event) => setCheckModeForm((current) => ({ ...current, resumePdfPath: event.target.value }))} placeholder={t("pages.submissions.checkMode.resumePathPlaceholder")} />
              </label>
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.status")}</p>
                <p className={`mt-1 inline-flex rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(checkModeResult?.terminal_status ?? "unknown")}`}>
                  {checkModeResult?.terminal_status ?? "--"}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.jobLead")}</p>
                <p className="mt-1 truncate text-text-primary">{String((checkModeResult?.original_job_lead.job_lead_id ?? checkModeForm.jobLeadId) || "--")}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.resume")}</p>
                <p className="mt-1 truncate text-text-primary">{(checkModeResult?.resume_version_id ?? checkModeForm.resumeVersionId) || "--"}</p>
              </div>
              <div>
                <p className="text-xs text-text-muted">{t("pages.submissions.checkMode.submit")}</p>
                <p className="mt-1 text-text-primary">{checkModeResult?.final_submit_attempted ? t("pages.submissions.checkMode.attempted") : t("pages.submissions.checkMode.skipped")}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-text-secondary md:grid-cols-2">
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.checkMode.json")}</span> {checkModeResult?.log_json_path || "--"}</p>
              <p className="break-all"><span className="text-text-muted">{t("pages.submissions.checkMode.steps")}</span> {checkModeResult?.steps.map((step) => step.name).join(" -> ") || "--"}</p>
            </div>
            {checkModeState === "error" ? <p className="mt-3 text-sm text-error">{error}</p> : null}
            </div>
          </details>
            </div>
          </details>
          </div>
        </>
      ) : null}
    </div>
  );
}
