import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Mail, Send, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getErrorMessage } from "@/lib/errors";
import { confirmAction, notify } from "@/lib/ui";
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
  diagnoseLiepinNativeAttachments,
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
import {
  autoAdvancePhases,
  checkModeConfirmationItems,
  currentPdfStep,
  defaultSubmissionChannel,
  isDelivered,
  isFailed,
  isFallback,
  parseExistingPreparedRun,
} from "./submissions-helpers";
import type {
  LoadState,
  NativePdfAction,
  QuickRunOption,
  RetryStrategy,
  StatItem,
} from "./submissions-helpers";


export function useSubmissionsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedQuickRun = searchParams.get("quick_run_id");
  const consumedQuickRun = useRef<string | null | undefined>(undefined);
  const { t } = useTranslation();
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
  const [autoAdvanceNotice, setAutoAdvanceNotice] = useState<{ text: string; tone: "success" | "warning" } | null>(null);
  // 清理旧附件成功后，后端仍保留上一次“已达上限”的 upload_hints；用本地一次性放行避免按钮继续锁死。
  const [quotaCleaned, setQuotaCleaned] = useState(false);
  // 同岗位已有进行中投递尝试时，后端会回传已固定版本；提供一键载入继续。
  const [existingPreparedRun, setExistingPreparedRun] = useState<{ quick: string; pdf: string } | null>(null);
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
  const diagnoseAttachments = useCallback(async () => {
    setCleanupBusy(true); setCleanupNotice("");
    try {
      const result = await diagnoseLiepinNativeAttachments();
      const hints = (result as unknown as {hints?: string[]}).hints || [];
      setCleanupNotice(hints.join("；") || result.status || "诊断完成");
    } catch (error) {
      setCleanupNotice(getErrorMessage(error));
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
      // 列表回填不得重新注入非法/未经验证的 quick_run_id（与上方校验保持一致）。
      const requestedValid =
        requestedQuickRun !== null && /^[A-Za-z0-9_-]{1,160}$/.test(requestedQuickRun);
      setPdfQuickRunId(
        (current) => current || (requestedValid ? requestedQuickRun : "") || options[0]?.id || ""
      );
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

  const formatNativePdfError = useCallback((error: unknown): string => {
    const message = typeof error === "string" ? error : getErrorMessage(error);
    if (message.includes("delivery_already_attempted")) {
      const parsed = parseExistingPreparedRun(message);
      setExistingPreparedRun(parsed);
      return parsed
        ? t("pages.submissions.nativePdf.errors.delivery_already_attempted_detail", {
            quick: parsed.quick,
            pdf: parsed.pdf || "--",
          })
        : t("pages.submissions.nativePdf.errors.delivery_already_attempted");
    }
    const contentErrors = ["career_profile_unconfirmed","resume_content_incomplete","resume_regeneration_required","resume_generation_changed","resume_pdf_source_changed","resume_evidence_changed","resume_pdf_changed","pdf_generation_trace_invalid"];
    // 后端/Host 业务错误码 → 可读说明；顺序与具体度无关，均为互斥错误码。
    const readableErrors: Array<[string, string]> = [
      ["pdf_upload_already_attempted", t("pages.submissions.nativePdf.errors.pdf_upload_already_attempted")],
      ["pdf_batch_authorization_required", t("pages.submissions.nativePdf.errors.pdf_batch_authorization_required")],
      ["account_effects_consent_required", t("pages.submissions.nativePdf.errors.account_effects_consent_required")],
      ["attachment_verification_required", t("pages.submissions.nativePdf.errors.attachment_verification_required")],
      ["pdf_target_verification_required", t("pages.submissions.nativePdf.errors.pdf_target_verification_required")],
      ["resume_target_unreviewed", t("pages.submissions.nativePdf.errors.resume_target_unreviewed")],
      ["pdf_job_review_required", t("pages.submissions.nativePdf.errors.pdf_job_review_required")],
      ["attachment_quota_reached", t("pages.submissions.nativePdf.errors.attachment_quota_reached")],
      ["attachment_current_state_mismatch", t("pages.submissions.nativePdf.errors.attachment_current_state_mismatch")],
      ["pdf_upload_not_dispatched", t("pages.submissions.nativePdf.errors.pdf_upload_not_dispatched")],
      ["ai_disclosure_not_confirmed", t("pages.submissions.nativePdf.errors.ai_disclosure_not_confirmed")],
      ["NATIVE_SESSION_LOGIN_REQUIRED", t("pages.submissions.nativePdf.errors.native_session_login_required")],
      ["NATIVE_SESSION_PAGE_NOT_READY", t("pages.submissions.nativePdf.errors.native_session_page_not_ready")],
      // 平台附件移除失败：evidence_unverified 可能带 :reason 后缀，includes 前缀匹配即可。
      ["attachment_removal_evidence_unverified", t("pages.submissions.nativePdf.errors.attachment_removal_evidence_unverified")],
      ["attachment_removal_success_required", t("pages.submissions.nativePdf.errors.attachment_removal_success_required")],
      ["attachment_removal_identity_unverified", t("pages.submissions.nativePdf.errors.attachment_removal_identity_unverified")],
      ["attachment_removal_already_attempted", t("pages.submissions.nativePdf.errors.attachment_removal_already_attempted")],
      ["attachment_removal_not_pending", t("pages.submissions.nativePdf.errors.attachment_removal_not_pending")],
    ];
    if (message.includes("quick_official_target_changed")) return t("daily.reasons.quick_official_target_changed");
    if (message.includes("daily_pdf_filename_too_long")) return t("daily.reasons.daily_pdf_filename_too_long");
    if (message.includes("daily_recovery_required")) return t("pages.submissions.nativePdf.recoveryOnly");
    if (message.includes("attachment_missing_on_platform")) return t("pages.submissions.nativePdf.platformMissing");
    if (message.includes("pdf_receipt_unconfirmed")) return t("pages.submissions.nativePdf.receiptNotAvailable");
    if (contentErrors.some((code) => message.includes(code))) return t("pages.submissions.nativePdf.contentNotReady");
    const readable = readableErrors.find(([code]) => message.includes(code));
    return readable ? readable[1] : message;
  }, [t]);

  /** 单步原生动作：只执行调用并落库，错误交给调用方统一映射；自动链每一步都用返回的 payload 判断。 */
  const performNativePdf = useCallback(async (action: NativePdfAction, currentPdf: NativePdfPreparation | null): Promise<NativePdfPreparation | null> => {
    if (currentPdf?.recovery_only && ["upload","communicate","prepareResume","send","remove"].includes(action)) return null;
    if (action === "prepare") {
      const result = await prepareLiepinPdf(pdfQuickRunId.trim());
      setNativePdf(result); setAcceptPdfEffects(false); setAcceptAttachmentRemoval(false);
      setNativePdfPreview(""); setPreviewedPdf(""); setAutoAdvanceNotice(null); setQuotaCleaned(false);
      setExistingPreparedRun(null);
      return result;
    }
    if (!currentPdf) return null;
    if (action === "preview") {
      const result = await previewDailyPdf(currentPdf.run_id);
      if (result.pdf_sha256 !== currentPdf.pdf_sha256) throw new Error("resume_pdf_changed");
      setNativePdfPreview("data:application/pdf;base64," + result.pdf_base64);
      setPreviewedPdf(currentPdf.run_id);
      return null;
    }
    if (action === "upload") {
      if (!acceptPdfEffects || previewedPdf !== currentPdf.run_id) return null;
      const result = await uploadLiepinNativePdf(currentPdf.run_id, true);
      setNativePdf(result);
      return result;
    }
    let result: NativePdfPreparation;
    if (action === "authorizeSingle") result = await authorizeSingleLiepinPdf(currentPdf.run_id);
    else if (action === "inspect") result = await inspectUploadedLiepinPdf(currentPdf.run_id);
    else if (action === "target") result = await inspectLiepinPdfTarget(currentPdf.run_id);
    else if (action === "communicate") result = await startLiepinPdfCommunication(currentPdf.run_id);
    else if (action === "inspectChat") result = await continueLiepinPdfDelivery(currentPdf.run_id, "inspect");
    else if (action === "prepareResume") result = await continueLiepinPdfDelivery(currentPdf.run_id, "prepare");
    else if (action === "send") result = await continueLiepinPdfDelivery(currentPdf.run_id, "send");
    else if (action === "remove") {
      if (!acceptAttachmentRemoval) return null;
      result = await removeLiepinNativePdfAttachment(currentPdf.run_id, true);
    } else if (action === "recheckRemoval") result = await recheckLiepinNativePdfRemoval(currentPdf.run_id);
    else if (action === "receipt") {
      result = await verifyNativePdfReceipt(currentPdf.run_id);
      setNativePdf(result);
      await loadData();
      return result;
    } else return null;
    setNativePdf(result);
    return result;
  }, [acceptAttachmentRemoval, acceptPdfEffects, loadData, pdfQuickRunId, previewedPdf]);

  const handleNativePdf = useCallback(async (action: NativePdfAction) => {
    setNativeSessionBusy(true); setNativePdfError(""); setAutoAdvanceNotice(null); setExistingPreparedRun(null);
    try {
      await performNativePdf(action, nativePdf);
    } catch (error) {
      setNativePdfError(formatNativePdfError(error));
    } finally { setNativeSessionBusy(false); }
  }, [formatNativePdfError, nativePdf, performNativePdf]);

  /** 自动推进：串行执行写操作直到“等待手动最终确认”；任何一步失败立即停止，不依赖 React 旧 state。 */
  const runAutoAdvance = useCallback(async () => {
    if (!nativePdf) return;
    const confirmed = await confirmAction({
      title: t("pages.submissions.nativePdf.autoAdvanceConfirmTitle"),
      description: t("pages.submissions.nativePdf.autoAdvanceConfirm"),
      confirmLabel: t("pages.submissions.nativePdf.autoAdvanceConfirmLabel"),
      tone: "default",
    });
    if (!confirmed) return;
    setNativeSessionBusy(true); setNativePdfError(""); setAutoAdvanceNotice(null);
    try {
      let current: NativePdfPreparation = nativePdf;
      if (nativePdf.attachment_bound === false && current.phase !== "prepared" && current.phase !== "not_submitted") {
        throw new Error("attachment_verification_required");
      }
      const run = async (action: NativePdfAction) => {
        const result = await performNativePdf(action, current);
        if (!result) throw new Error(t("pages.submissions.nativePdf.autoAdvanceUnavailable"));
        current = result;
      };
      // 可重复上传只信后端归一后的 can_retry_upload；旧后端未返回时按 phase 兼容。
      const canRetryUpload = current.phase === "not_submitted" ? current.can_retry_upload !== false : false;
      if (current.phase === "prepared" || canRetryUpload) {
        // 上传前先打开/检查 App 内猎聘会话，避免用户为同一条链路再单独点“检查会话”。
        await openLiepinNativeSession();
        const session = await checkLiepinNativeSession();
        setNativeSession(session.status);
        if (session.status !== "authenticated") throw new Error("NATIVE_SESSION_LOGIN_REQUIRED");
        await run("upload");
        if (current.phase === "not_submitted" || current.phase === "unknown") {
          // 上传脚本会以 not_submitted 结束而没有抛错；这里必须把“未进入后续阶段”变成可读错误，而不是静默停在原地。
          const quotaReached = (current.upload_hints || []).some((hint) => hint.includes("attachment_quota_reached"));
          if (quotaReached) setQuotaCleaned(false);
          throw new Error(quotaReached ? "attachment_quota_reached" : "pdf_upload_not_dispatched");
        }
      }
      if (current.phase === "uploaded_unverified") await run("inspect");
      if (current.phase === "attachment_verified" && !current.single_delivery_authorized) await run("authorizeSingle");
      if (current.phase === "attachment_verified") await run("communicate");
      if (current.phase === "communication_started") await run("inspectChat");
      if ((current.phase === "communication_started" || current.phase === "resume_interaction_pending") && !current.can_confirm_send) await run("prepareResume");
      if (current.phase === "resume_interaction_pending" && current.can_confirm_send) {
        setAutoAdvanceNotice({ tone: "success", text: t("pages.submissions.nativePdf.autoAdvanceReady") });
        notify("success", t("pages.submissions.nativePdf.autoAdvanceDone"));
      } else {
        setAutoAdvanceNotice({ tone: "warning", text: t("pages.submissions.nativePdf.autoAdvanceStopped") });
      }
    } catch (error) {
      const message = formatNativePdfError(error);
      setNativePdfError(message);
      notify("error", t("pages.submissions.nativePdf.autoAdvanceFailed"), message);
    } finally { setNativeSessionBusy(false); }
  }, [formatNativePdfError, nativePdf, performNativePdf, t]);

  /** 最终发送仍由人点击；发送完成后自动只读核验业务回执并刷新投递记录，失败不伪造成功。 */
  const confirmFinalSend = useCallback(async () => {
    if (!nativePdf?.can_confirm_send) return;
    setNativeSessionBusy(true); setNativePdfError(""); setAutoAdvanceNotice(null);
    try {
      const sent = await performNativePdf("send", nativePdf);
      if (!sent) throw new Error(t("pages.submissions.nativePdf.autoAdvanceUnavailable"));
      try {
        await performNativePdf("receipt", sent);
        notify("success", t("pages.submissions.nativePdf.finalConfirmSuccess"));
      } catch (receiptError) {
        const message = formatNativePdfError(receiptError);
        setNativePdfError(message);
        notify("error", t("pages.submissions.nativePdf.finalVerifyFailed"), message);
      }
    } catch (error) {
      const message = formatNativePdfError(error);
      setNativePdfError(message);
      notify("error", t("pages.submissions.nativePdf.finalConfirmFailed"), message);
    } finally { setNativeSessionBusy(false); }
  }, [formatNativePdfError, nativePdf, performNativePdf, t]);

  /** 载入后端回传的已固定投递流程，继续原来的沟通/确认进度。 */
  const loadExistingPreparedPdf = useCallback(async () => {
    const target = existingPreparedRun;
    if (!target) return;
    setNativeSessionBusy(true); setNativePdfError("");
    try {
      const result = await prepareLiepinPdf(target.quick);
      setPdfQuickRunId(target.quick);
      setNativePdf(result); setAcceptPdfEffects(false); setAcceptAttachmentRemoval(false);
      setNativePdfPreview(""); setPreviewedPdf(""); setQuotaCleaned(false); setExistingPreparedRun(null);
      setAutoAdvanceNotice({ tone: "success", text: t("pages.submissions.nativePdf.existingPreparedLoaded") });
    } catch (error) {
      setNativePdfError(formatNativePdfError(error));
    } finally { setNativeSessionBusy(false); }
  }, [existingPreparedRun, formatNativePdfError, t]);

  /** 平台附件在最终发送前被移除：重新上传同一份已批准 PDF，核验绑定后继续原投递。 */
  const reuploadMissingAttachment = useCallback(async () => {
    if (!nativePdf?.run_id || !nativePdf.can_reupload_attachment) return;
    const confirmed = await confirmAction({
      title: t("pages.submissions.nativePdf.reuploadMissingConfirmTitle"),
      description: t("pages.submissions.nativePdf.reuploadMissingConfirm"),
      confirmLabel: t("pages.submissions.nativePdf.reuploadMissingAction"),
      tone: "default",
    });
    if (!confirmed) return;
    setNativeSessionBusy(true); setNativePdfError(""); setAutoAdvanceNotice(null);
    try {
      const uploaded = await uploadLiepinNativePdf(nativePdf.run_id, true);
      setNativePdf(uploaded);
      let inspected = uploaded;
      // 投递进入沟通阶段后 phase 仍是 resume_interaction_pending；是否重新核验要看上传子状态。
      if (uploaded.upload_state === "uploaded_unverified" || uploaded.attachment_bound === false) {
        inspected = await inspectUploadedLiepinPdf(nativePdf.run_id);
        setNativePdf(inspected);
      }
      if (inspected.attachment_bound !== true || inspected.verification_error) {
        throw new Error("attachment_current_state_mismatch");
      }
      setAutoAdvanceNotice({ tone: "success", text: t("pages.submissions.nativePdf.reuploadMissingDone") });
    } catch (error) {
      const message = formatNativePdfError(error);
      setNativePdfError(message);
      notify("error", t("pages.submissions.nativePdf.reuploadMissingFailed"), message);
    } finally { setNativeSessionBusy(false); }
  }, [formatNativePdfError, nativePdf, t]);

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
  // 自动推进可用性：错误/终态/进行中阶段不做写操作；prepared/not_submitted 需已预览并勾选（会话由自动链自行打开/检查）；
  // not_submitted 是否可再次上传以后端 can_retry_upload 为准，不从原始上传状态自行推断。
  const uploadHints = nativePdf?.upload_hints ?? [];
  const quotaReached = uploadHints.some((hint) => hint.includes("attachment_quota_reached"));
  const quotaBlocked = quotaReached && !quotaCleaned;
  const visibleUploadHints = uploadHints.filter((hint) => !hint.startsWith("attachment_quota_reached"));
  const cleanupQuotaAndRetry = useCallback(async () => {
    await cleanupOldAttachments();
    setNativePdfError("");
    setQuotaCleaned(true);
    setAutoAdvanceNotice({ tone: "success", text: t("pages.submissions.nativePdf.quotaCleanupDone") });
  }, [cleanupOldAttachments, t]);
  const autoAdvanceAvailable = nativePdf !== null && !nativePdf.recovery_only && !nativePdf.can_confirm_send && !quotaBlocked
    && autoAdvancePhases.includes(nativePdf.phase)
    && !(nativePdf.phase === "not_submitted" && nativePdf.can_retry_upload === false)
    && (nativePdf.phase !== "prepared" && nativePdf.phase !== "not_submitted"
      || (previewedPdf === nativePdf.run_id && acceptPdfEffects));

  // ⌘R / pipf:refresh：壳层快捷键触发当前页重新加载。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void loadData();
    window.addEventListener("pipf:refresh", onRefresh);
    return () => window.removeEventListener("pipf:refresh", onRefresh);
  }, [loadData]);


  return {
    nativePdfPreview,
    previewedPdf,
    setNativePdfPreview,
    setPreviewedPdf,
    navigate,
    items,
    activeTab,
    setActiveTab,
    loadState,
    error,
    retryingId,
    selectedId,
    detail,
    detailState,
    selectedScreenshotPath,
    setSelectedScreenshotPath,
    selectedChannel,
    setSelectedChannel,
    channelSession,
    sessionState,
    sessionAction,
    nativeSession,
    nativeSessionBusy,
    nativeAttachmentView,
    cleanupBusy,
    cleanupNotice,
    pdfQuickRunId,
    setPdfQuickRunId,
    quickRunOptions,
    nativePdf,
    setNativePdf,
    acceptPdfEffects,
    setAcceptPdfEffects,
    acceptAttachmentRemoval,
    setAcceptAttachmentRemoval,
    nativePdfError,
    autoAdvanceNotice,
    quotaCleaned,
    existingPreparedRun,
    qualityDecisionNotice,
    decideHighlight,
    cleanupOldAttachments,
    diagnoseAttachments,
    checkModeResult,
    checkModeState,
    feedbackList,
    feedbackIteration,
    feedbackNotes,
    setFeedbackNotes,
    feedbackSource,
    setFeedbackSource,
    feedbackAction,
    setFeedbackAction,
    feedbackState,
    checkModeForm,
    setCheckModeForm,
    stats,
    screenshotSteps,
    refreshing,
    loadData,
    feedbackSync,
    handleNativeSession,
    handleFeedbackSync,
    handleNativePdf,
    runAutoAdvance,
    confirmFinalSend,
    loadExistingPreparedPdf,
    reuploadMissingAttachment,
    handleStartSession,
    handleCheckSession,
    handleClearSession,
    handleStartCheckMode,
    feedbackRunId,
    managedFeedback,
    handleCreateFeedbackIteration,
    handleRetry,
    handleSelect,
    pdfStep,
    quotaReached,
    quotaBlocked,
    visibleUploadHints,
    cleanupQuotaAndRetry,
    autoAdvanceAvailable,
    t,
  };
}
